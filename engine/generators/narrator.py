"""El narrador: le pone voz a la historia, y MIDE cuánto dura.

Genera una pista por cada cosa que se dice: la narración de cada escena con la voz
del narrador, y cada línea de diálogo hablado con la voz de su personaje. Los globos
que solo se leen en pantalla (`spoken=False`) no se sintetizan — no se dicen.

**Lo que hace distinto a este módulo: mide.** El plan le da a cada escena una
duración y el escritor escribe para esa duración usando 2.5 palabras por segundo.
Es una estimación calibrada, pero el audio real dura lo que dura. Si el render usa
la estimación, la imagen cambia antes de que el narrador termine la frase o queda un
silencio al final. Por eso cada pista se mide al generarla y de ahí en adelante manda
la medición.

Tampoco corrige por su cuenta. Si una escena se pasa, avisa y sigue: apurar la voz
para que entre suena peor que la escena un poco más larga, y **si se pasan todas no
es un problema de una escena sino de la calibración** — para eso está `tasa_real()`,
que devuelve las palabras por segundo medidas para poder ajustar la constante con
datos en vez de con intuición.

Las escenas se narran en paralelo: a diferencia de las imágenes, acá no hay anclas
que encadenen una con la anterior.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import statistics
import struct
import unicodedata
import wave
from pathlib import Path

from engine.core.constants import (
    NARRATION_OVERFLOW_TOLERANCE,
    WORDS_PER_SECOND,
)
from engine.core.enums import AudioKind, StoryStatus
from engine.core.exceptions import DomainError, ProviderError
from engine.core.interfaces import Alineacion, VoiceProvider
from engine.core.models.audio import AudioTrack
from engine.core.models.character import Voice
from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.core.retry import con_reintentos
from engine.prompts import voz as prompts_voz

logger = logging.getLogger(__name__)

#: Cuántas escenas se narran a la vez.
#:
#: TRES y no más: es el límite del plan de ElevenLabs, medido contra la cuenta real
#: (5-ago-2026) — con 4 devuelve *"maximum of 3 concurrent requests"*. Con reintentos
#: se recupera, pero es tiempo y cuota tirados a propósito.
CONCURRENCIA = 3

#: Qué fracción del audio esperado hay que recibir para creerle a la toma.
#:
#: Detecta el corte, que es el error más caro de todos: cuando el proveedor devuelve
#: la mitad del audio NO falla — devuelve un WAV válido, más corto. El archivo existe,
#: el pipeline sigue, y el problema aparece escuchando el producto terminado. Pasó de
#: verdad en los audiolibros de Casatridimensional, y por eso allá hay un QA de
#: duración con piso además de techo.
#:
#: 0.5 es holgado a propósito: una voz lenta o una frase con pausas largas no puede
#: disparar la alarma. Lo que buscamos es la toma partida al medio, no la lenta.
PISO_DE_TOMA = 0.5

#: Cuántas veces se le pide de nuevo una toma que llegó cortada.
#: Frenar la producción entera por una toma mala es justo lo que no puede pasar
#: cuando esto corre solo, diez veces por día.
INTENTOS_DE_TOMA = 3

#: Cuánto silencio tiene que haber ANTES de la primera palabra.
#:
#: v3 a veces arranca la toma justo encima de la primera consonante y se come su
#: explosión. Lo escuchó Pablo en el short: *"el comienzo del video parece que dijera
#: nano salto, era dino salto"*. La D es una oclusiva —su ataque dura milisegundos— y
#: sin ellos suena como una N.
#:
#: Medido sobre las ocho tomas de ese cuento: la que sonaba mal tenía **0 ms** y las
#: siete que sonaban bien, entre 222 y 496 ms. Y no es determinista: la misma frase
#: pedida de nuevo salió con 194 ms. Por eso no alcanza con pedirla distinto —hay que
#: MIRAR el audio que llegó y volver a pedirlo si nació cortado.
ATAQUE_MINIMO_MS = 60

#: Cuánto puede una toma hablar más rápido que el resto de la historia antes de que
#: sea sospechosa de estar cortada.
#:
#: El piso de arriba detecta el corte grosero —media frase—; esto detecta el que se
#: come el final de la última palabra, que suena peor de lo que parece y que no baja
#: la duración lo suficiente como para disparar el piso.
DESVIO_SOSPECHOSO = 0.25


class StoryNarrator:
    """Convierte una historia escrita en una historia narrada."""

    def __init__(
        self,
        provider: VoiceProvider,
        *,
        narrator_voice: Voice | None = None,
        transcriber: object | None = None,
    ) -> None:
        self._provider = provider
        #: Con qué se ESCUCHA la toma para verificar que dijo lo que decía el texto.
        #: Opcional: sin él, el narrador funciona exactamente como antes.
        self._transcriber = transcriber
        #: La voz que lee la narración. Es del NARRADOR, no de un personaje: quien
        #: cuenta el cuento no está adentro del cuento.
        self._voz = narrator_voice or Voice(description="cálida y tranquila, de cuento infantil")

    async def narrate(self, story: Story, dest_dir: str | Path, *, de_una_toma: bool = True) -> Story:
        """Narra todas las escenas y deja la historia en NARRATED.

        Por defecto el cuento se graba de UNA SOLA TOMA y después se corta. Ver
        `_narrar_de_una_toma`: es lo que separa un cuento de seis relatos pegados.
        """
        if not story.scenes:
            raise DomainError("La historia no tiene escenas: hay que escribirla antes de narrarla.")

        destino = Path(dest_dir)
        destino.mkdir(parents=True, exist_ok=True)
        personajes = story.characters_by_id

        if de_una_toma and _sabe_alinear(self._provider):
            await self._narrar_de_una_toma(story, destino)
            await self._narrar_dialogos(story, destino, personajes)
        else:
            limite = asyncio.Semaphore(CONCURRENCIA)

            async def una(escena: Scene) -> None:
                async with limite:
                    escena.audio = await self._narrar_escena(escena, destino, personajes)

            await asyncio.gather(*(una(e) for e in story.scenes))
            story.closing_audio = await self._narrar_cierre(story, destino)

        self._avisar_tomas_apuradas(story)
        self._avisar_desvios(story)
        if story.status is not StoryStatus.NARRATED:
            story.advance_to(StoryStatus.NARRATED)
        story.metadata.touch()
        return story

    async def _narrar_de_una_toma(self, story: Story, destino: Path) -> None:
        """Graba el cuento ENTERO en una sola toma y después lo corta por escena.

        Es la diferencia entre un cuento y seis relatos pegados. Pablo, escuchando el
        short hecho con una toma por escena: *"al ser tarjeta y audio, tarjeta y audio
        parece que todo fuera de relatos distintos. Creo que debería ser un relato
        continuo"*. Tenía razón y la causa era exactamente ésa: pedir cada escena por
        separado hace que el modelo le ponga entonación de arranque y de cierre a cada
        una, porque para él cada pedido es un texto completo.

        Acá va todo junto, con las etiquetas de emoción INTERCALADAS —que es como v3
        cambia de tono sin cortar el relato— y el corte se hace después, con la
        alineación por caracter que devuelve el proveedor. Los tiempos no se estiman:
        se miden sobre el audio que llegó.

        De arrastre desaparecen los dos problemas del arranque y del final: una sola
        toma tiene un solo comienzo y un solo final, así que hay un solo lugar donde el
        modelo puede comerse una sílaba, en vez de dieciséis.
        """
        trozos: list[str] = [prompts_voz.DIRECCION]

        # El TÍTULO va primero, y se dice. La placa existía desde el primer render y
        # nadie la leía: Pablo, mirando el segundo lote, *"aparece el título pero no
        # habla en ningún video"*. Va adentro de la toma continua y no como pedido
        # aparte por la misma razón que las escenas: dos pedidos son dos
        # interpretaciones, y el título pegado al gancho con otra entonación suena a
        # locutor anunciando en vez de a alguien que empieza a contar un cuento.
        titulo = _titulo_dicho(story)
        if titulo:
            trozos += [prompts_voz.APERTURA, prompts_voz.COLCHON_INICIAL, titulo]

        for i, escena in enumerate(story.scenes):
            etiqueta = prompts_voz.etiqueta_de_escena(
                escena.beat, escena.emotion, es_primera=(i == 0)
            )
            if etiqueta:
                trozos.append(etiqueta)
            # El colchón va UNA vez, delante de lo primero que se dice: es para que el
            # modelo no arranque encima de la primera consonante, y eso pasa en el
            # arranque de la toma, no en cada frase.
            if i == 0 and not titulo:
                trozos.append(prompts_voz.COLCHON_INICIAL)
            trozos.append(_limpio(escena.narration))

        cierres = [t for t in (story.moral, story.closing_question) if t]
        if cierres:
            # El cierre ya no es el cuento: el narrador le habla al chico que mira.
            trozos.append(prompts_voz.APERTURA)
            trozos += [_limpio(t) for t in cierres]

        pedido = " ".join(t for t in trozos if t) + COLCHON_FINAL
        audio, marcas = await self._toma_continua(pedido)

        desde = 0.0
        if titulo:
            # Si el título no se puede ubicar en la alineación, se sigue sin él: el
            # cuento entero ya está grabado y perderlo por la placa sería tirar el
            # trabajo pagado. El render vuelve solo a la placa muda.
            try:
                hasta = marcas.fin_de(titulo)
            except ValueError as e:
                logger.warning("No se pudo ubicar el título en el audio (%s): la placa va muda.", e)
            else:
                ruta = destino / "titulo.wav"
                ruta.write_bytes(_recortar(audio, desde, hasta))
                story.title_audio = [
                    AudioTrack(
                        path=str(ruta),
                        text=story.metadata.title or "",
                        duration_s=round(hasta - desde, 3),
                        kind=AudioKind.NARRATION,
                        character_id=None,
                        voice_id=self._voz.provider_voice_id or "",
                    )
                ]
                desde = hasta

        for escena in story.scenes:
            hasta = marcas.fin_de(_limpio(escena.narration))
            ruta = destino / f"escena_{escena.index:02d}_narracion.wav"
            ruta.write_bytes(_recortar(audio, desde, hasta))
            escena.audio = [
                AudioTrack(
                    path=str(ruta),
                    text=escena.narration,
                    duration_s=round(hasta - desde, 3),
                    kind=AudioKind.NARRATION,
                    character_id=None,
                    voice_id=self._voz.provider_voice_id or "",
                )
            ]
            desde = hasta

        pistas: list[AudioTrack] = []
        for n, texto in enumerate(cierres):
            ultimo = n == len(cierres) - 1
            hasta = marcas.duracion_s if ultimo else marcas.fin_de(_limpio(texto))
            ruta = destino / f"cierre_{n}.wav"
            ruta.write_bytes(_recortar(audio, desde, hasta))
            pistas.append(
                AudioTrack(
                    path=str(ruta),
                    text=texto,
                    duration_s=round(hasta - desde, 3),
                    kind=AudioKind.NARRATION,
                    character_id=None,
                    voice_id=self._voz.provider_voice_id or "",
                )
            )
            desde = hasta
        story.closing_audio = pistas

        # Que el render no meta silencio entre escenas: el aire ya está adentro de la
        # toma, donde el narrador lo puso. Agregarle 0,45s a cada corte volvería a
        # partir en pedazos justo lo que se grabó de corrido.
        story.continuous_narration = True

    async def _toma_continua(self, pedido: str) -> tuple[bytes, Alineacion]:
        """La toma del cuento entero, con los mismos guardianes que una toma suelta.

        Grabar de una sola vez no vuelve infalible al proveedor: la toma puede llegar
        cortada o nacer encima de la primera consonante igual que antes. Lo que cambia
        es que ahora hay UN solo lugar donde puede pasar en vez de dieciséis — y que si
        pasa, se pierde el cuento entero, así que el guardián importa más, no menos.
        """
        audio, marcas = b"", Alineacion([], [])
        #: La mejor toma descartada SÓLO por pronunciación. Si se agotan los intentos
        #: se usa ésta: un cuento entero que dice "Nino" en la primera palabra es
        #: peor que uno que dice "Dino", pero es muchísimo mejor que ningún cuento.
        de_reserva: tuple[bytes, Alineacion] | None = None

        for intento in range(1, INTENTOS_DE_TOMA + 1):
            audio, marcas = await con_reintentos(
                lambda: self._provider.synthesize_aligned(  # type: ignore[attr-defined]
                    pedido,
                    voice_id=self._voz.provider_voice_id,
                    speed=self._voz.speed,
                    audio_format="wav",
                ),
                al_reintentar=lambda n, e: logger.warning(
                    "El proveedor de voz falló narrando el cuento entero (%s). Reintento %s.",
                    e, n,
                ),
            )
            duracion = duracion_de_wav(audio) if audio else 0.0
            ataque = ataque_ms(audio) if audio else 0.0
            if _toma_entera(pedido, duracion) and ataque >= ATAQUE_MINIMO_MS:
                if not (mal := await self._mal_dicha(audio, pedido)):
                    return audio, marcas
                motivo = mal
                de_reserva = de_reserva or (audio, marcas)
            else:
                motivo = (
                    f"le falta el final (dura {duracion:.1f}s)"
                    if not _toma_entera(pedido, duracion)
                    else f"nace cortada: {ataque:.0f} ms antes de la primera palabra"
                )
            logger.warning(
                "La toma del cuento entero %s. Se pide de nuevo (%s de %s).",
                motivo, intento, INTENTOS_DE_TOMA,
            )
            if olvidar := getattr(self._provider, "olvidar", None):
                olvidar(pedido, voice_id=self._voz.provider_voice_id,
                        speed=self._voz.speed, audio_format="wav")

        if de_reserva is not None:
            logger.warning(
                "Las %s tomas se entendieron mal en la primera palabra (%s). Se usa la "
                "primera: el cuento sale igual.",
                INTENTOS_DE_TOMA, motivo,
            )
            return de_reserva

        raise ProviderError(
            f"La narración del cuento entero llegó cortada {INTENTOS_DE_TOMA} veces "
            f"seguidas: {motivo}."
        )

    async def _mal_dicha(self, audio: bytes, pedido: str) -> str:
        """Por qué la toma NO dice lo que decía el texto, o cadena vacía si está bien.

        **Verifica la primera palabra, que es donde falló las tres veces.** Pablo lo
        escuchó sobre el mismo nombre: primero *"nano"*, después *"Maqueno"*, y el
        texto siempre decía "Dino". La duración y el silencio inicial se pueden medir
        con la stdlib; que la D se haya convertido en N, no — el WAV es idéntico de
        sano. La única forma de saberlo es escuchar la toma, y para eso está el
        transcriptor.

        Medido sobre 24 tomas de la misma frase (7-ago-2026), contando cuántas
        arrancaron diciendo "Dino" de verdad:

        | estabilidad | bien | lo que se entendió cuando falló |
        |---|---|---|
        | 0.3 | 4 de 8 | Patatendo, Lino, Vino, Nino |
        | 0.5 | 5 de 8 | Podino, Unadino, Vino |
        | 0.7 | 6 de 8 | Vino |

        O sea que **la estabilidad no es la causa**: mejora la probabilidad y no la
        arregla, ni siquiera en 0.7. Lo que sí sirve es que NO es determinista —la
        misma frase pedida de nuevo sale bien— así que acá el reintento es un
        reintento de verdad, a diferencia del de la toma que nacía cortada.

        Si no hay transcriptor, o si transcribir falla, la toma pasa: un guardián que
        no puede mirar no frena nada.
        """
        if self._transcriber is None:
            return ""
        try:
            dicho = await self._transcriber.transcribe(audio)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001 — verificar es una mejora, no un requisito
            logger.warning("No se pudo verificar la pronunciación (%s). La toma pasa.", e)
            return ""

        esperada, oida = _primera_palabra(pedido), _primera_palabra(dicho)
        if not esperada or not oida or esperada == oida:
            return ""
        return f"se entiende '{oida}' donde el texto dice '{esperada}'"

    async def _narrar_dialogos(self, story: Story, destino: Path, personajes) -> None:
        """Los diálogos, que NO entran en la toma continua.

        Cada personaje tiene su voz: no se pueden grabar junto con la narración, que es
        de otra. Van después, y se suman a las pistas de su escena.
        """
        for escena in story.scenes:
            if escena.dialogue:
                escena.audio += await self._narrar_dialogo_de(escena, destino, personajes)

    async def _narrar_cierre(self, story: Story, destino: Path) -> list[AudioTrack]:
        """La moraleja y la pregunta final.

        No son parte del cuento: el cuento ya terminó. Son lo que se le dice a quien
        mira, y la pregunta es lo que convierte a un espectador en un comentario.

        Existían en el modelo desde el primer día y ningún módulo las usaba, así que
        el video terminaba en la última palabra de la historia, en seco.
        """
        pistas: list[AudioTrack] = []
        for n, texto in enumerate(t for t in (story.moral, story.closing_question) if t):
            pistas.append(
                await self._pista(
                    texto,
                    voz=self._voz,
                    kind=AudioKind.NARRATION,
                    character_id=None,
                    ruta=destino / f"cierre_{n}.wav",
                    # El cierre se dice más lento y más cálido que el cuento: es el
                    # momento en que el narrador le habla al chico, no a la historia.
                    entonacion=f"{prompts_voz.DIRECCION} {prompts_voz.APERTURA}",
                )
            )
        return pistas

    # ------------------------------------------------------------------------
    async def _narrar_escena(self, escena: Scene, destino: Path, personajes) -> list[AudioTrack]:
        """Las pistas de una escena, en el orden en que suenan.

        Primero la narración y después el diálogo: el narrador presenta la situación
        y recién ahí habla el personaje.
        """
        pistas: list[AudioTrack] = []

        pistas.append(
            await self._pista(
                escena.narration,
                voz=self._voz,
                kind=AudioKind.NARRATION,
                character_id=None,
                ruta=destino / f"escena_{escena.index:02d}_narracion.wav",
                entonacion=prompts_voz.direccion_de_escena(
                    escena.beat, escena.emotion, es_primera=escena.index == 0
                ),
            )
        )

        pistas += await self._narrar_dialogo_de(escena, destino, personajes)
        return pistas

    async def _narrar_dialogo_de(
        self, escena: Scene, destino: Path, personajes
    ) -> list[AudioTrack]:
        """Lo que dicen los personajes, cada uno con su voz."""
        pistas: list[AudioTrack] = []
        hablados = [d for d in escena.dialogue if d.spoken]
        for n, linea in enumerate(hablados):
            personaje = personajes.get(linea.character_id)
            if personaje is None:
                raise DomainError(
                    f"Escena {escena.index}: habla '{linea.character_id}', que no está "
                    "en el elenco de la historia."
                )
            pistas.append(
                await self._pista(
                    linea.text,
                    voz=personaje.voice,
                    kind=AudioKind.DIALOGUE,
                    character_id=personaje.id,
                    ruta=destino / f"escena_{escena.index:02d}_dialogo_{n}.wav",
                    entonacion=prompts_voz.direccion_de_escena(
                        escena.beat,
                        linea.emotion or escena.emotion_for(personaje.id),
                        es_primera=False,
                    ),
                )
            )
        return pistas

    async def _pista(
        self,
        texto: str,
        *,
        voz: Voice,
        kind: AudioKind,
        character_id: str | None,
        ruta: Path,
        entonacion: str = "",
    ) -> AudioTrack:
        decible = para_decir(texto)
        # La etiqueta va DESPUÉS de limpiar y no cuenta como texto: es una instrucción
        # de actuación, no algo que se diga. Si el modelo no la entiende, el proveedor
        # la saca — acá no hay que acordarse.
        pedido = prompts_voz.con_entonacion(decible, entonacion)

        # Una toma cortada NO es un error del proveedor: devuelve 200 y un WAV válido,
        # más corto. Por eso no alcanza con `con_reintentos`, que sólo reacciona a las
        # excepciones. Se pide de nuevo hasta que llegue entera, porque frenar la
        # producción por una toma mala es justo lo que no puede pasar cuando esto corre
        # solo diez veces por día.
        audio, duracion = b"", 0.0
        for intento in range(1, INTENTOS_DE_TOMA + 1):
            audio = await con_reintentos(
                lambda: self._provider.synthesize(
                    pedido,
                    voice_id=voz.provider_voice_id,
                    speed=voz.speed,
                    audio_format="wav",
                ),
                al_reintentar=lambda n, e: logger.warning(
                    "%s: el proveedor de voz falló (%s). Reintento %s.", ruta.name, e, n
                ),
            )
            duracion = duracion_de_wav(audio) if audio else 0.0
            ataque = ataque_ms(audio) if audio else 0.0
            if _toma_entera(decible, duracion) and ataque >= ATAQUE_MINIMO_MS:
                break
            motivo = (
                f"le falta el final (dura {duracion:.1f}s)"
                if not _toma_entera(decible, duracion)
                else f"nace cortada: {ataque:.0f} ms de silencio antes de la primera palabra"
            )
            logger.warning(
                "%s: la toma %s. Se pide de nuevo (%s de %s).",
                ruta.name, motivo, intento, INTENTOS_DE_TOMA,
            )
            # Si hay un caché delante, la toma mala quedó guardada y pedirla de nuevo
            # devuelve la MISMA: tres intentos idénticos y a fallar. Se le pide que la
            # tire. Con `getattr` porque el Protocol de VoiceProvider no lo exige: un
            # proveedor sin caché no tiene nada que olvidar.
            if olvidar := getattr(self._provider, "olvidar", None):
                olvidar(pedido, voice_id=voz.provider_voice_id, speed=voz.speed,
                        audio_format="wav")
        else:
            raise ProviderError(
                f"La toma '{ruta.name}' llegó cortada {INTENTOS_DE_TOMA} veces seguidas: "
                f"{motivo}. Para decir {len(decible.split())} palabras hacen falta unos "
                f"{len(decible.split()) / WORDS_PER_SECOND:.1f}s."
            )

        ruta.write_bytes(audio)
        return AudioTrack(
            kind=kind,
            character_id=character_id,
            text=texto,
            path=str(ruta),
            duration_s=duracion,
            voice_id=voz.provider_voice_id or "",
        )

    def _avisar_tomas_apuradas(self, story: Story) -> None:
        """Marca la toma que dice sus palabras MÁS RÁPIDO que las demás.

        Es cómo se ve una toma cortada desde afuera: el archivo tiene el largo de
        casi toda la frase, así que el piso absoluto no la detecta, pero le falta el
        final. Pablo lo escuchó: *"hay una parte que dice pelotita de colore y es de
        colores, se corta antes"*. Esa toma iba a 2.99 palabras por segundo cuando el
        resto de la historia iba a 2.38.

        Se compara contra la MEDIANA de la propia historia y no contra una constante:
        la velocidad depende de la voz, del modelo y de los ajustes, y lo que importa
        no es cuán rápido habla sino que una toma se salga del resto.
        """
        tasas = [
            (e.index, len(t.text.split()) / t.duration_s)
            for e in story.scenes
            for t in e.audio
            if t.duration_s > 0
        ]
        if len(tasas) < 3:
            return  # con dos tomas no hay "resto de la historia" contra qué comparar
        mediana = statistics.median(v for _, v in tasas)
        for indice, tasa in tasas:
            if tasa > mediana * (1 + DESVIO_SOSPECHOSO):
                logger.warning(
                    "Escena %s: la narración va a %.2f palabras por segundo y el resto "
                    "de la historia a %.2f. Puede haber salido cortada.",
                    indice, tasa, mediana,
                )

    def _avisar_desvios(self, story: Story) -> None:
        """Deja rastro de las escenas donde el audio no entra en lo planeado.

        No corrige: apurar la voz para que entre suena peor que la escena un poco más
        larga, y el que sabe qué hacer con eso es el render.
        """
        for escena in story.scenes:
            tope = escena.duration_s * NARRATION_OVERFLOW_TOLERANCE
            if escena.audio_duration_s > tope:
                logger.warning(
                    "Escena %s: el audio dura %.1fs y la escena planeaba %.1fs.",
                    escena.index,
                    escena.audio_duration_s,
                    escena.duration_s,
                )


# --------------------------------------------------------------------------- utils
#: Lo que se le agrega al final de cada toma para que no se coma la última palabra.
#:
#: ElevenLabs v3 trunca el final, y no al azar: la misma frase se corta SIEMPRE.
#: Lo escuchó Pablo — *"dice pelotita de colore y es de colores, se corta antes"*— y
#: se midió con la frase exacta: 3,8s tal cual (cortada) contra **5,3s con un punto
#: extra al final** (entera). Los puntos suspensivos dan lo mismo (5,1s).
#:
#: Un punto de más no se pronuncia, así que no cambia lo que se dice: solo le da al
#: modelo el margen que necesita para terminar la palabra.
COLCHON_FINAL = " ."

#: Lo que hay que arreglar del texto ANTES de mandarlo a decir.
#:
#: El texto que se DICE no es el que se VE. Las comillas angulares las lee como
#: ">>" —pasó en los audiolibros— y los asteriscos de markdown no son nada.
#:
#: **Lo que NO se toca: los puntos suspensivos.** Son la herramienta principal para
#: el ritmo de un cuento: el modelo baja la velocidad y toma aire donde hay "...".
#: Convertirlos en punto —que es lo que hacía este código— aplana justamente lo que
#: hay que exagerar. Igual los signos de exclamación y de pregunta, que son los que
#: levantan el tono.
_PARA_DECIR: tuple[tuple[str, str], ...] = (
    ("«", ""),
    ("»", ""),
    ("*", ""),
)


def para_decir(texto: str) -> str:
    """El texto listo para el TTS: sin los signos que se leen mal en voz alta.

    Deliberadamente conservador: casi todo signo que un cuentacuentos usaría está
    ahí para marcar el ritmo, y limpiarlo de más deja la lectura plana.

    Termina agregando `COLCHON_FINAL` — ver por qué ahí abajo.
    """
    return _limpio(texto) + COLCHON_FINAL


def _primera_palabra(texto: str) -> str:
    """La primera palabra que se DICE, en minúsculas y sin tildes.

    Saca las etiquetas de actuación —`[warmly]` no se pronuncia— y toda la puntuación,
    incluida la coma del colchón inicial. De `"[warmly] [slows down] , Dino, el
    dinosaurio bebé"` devuelve `"dino"`.

    Sin tildes porque la transcripción y el guion no siempre coinciden en acentuar, y
    una tilde de diferencia no es una palabra mal dicha.
    """
    sin_etiquetas = re.sub(r"\[[^\]]*\]", " ", texto)
    plano = "".join(
        c for c in unicodedata.normalize("NFD", sin_etiquetas.lower())
        if unicodedata.category(c) != "Mn"
    )
    palabras = re.findall(r"[a-z0-9ñ]+", plano)
    return palabras[0] if palabras else ""


def _titulo_dicho(story: Story) -> str:
    """El título tal como entra en la toma, o vacío si la historia no tiene.

    Lleva punto al final aunque el título no lo tenga: sin él, el modelo lo pega con
    la primera frase del cuento y se pierde el respiro entre *cómo se llama* y *cómo
    empieza*. Un punto no se pronuncia — es la misma herramienta que el colchón final.
    """
    titulo = _limpio(story.metadata.title or "")
    if not titulo:
        return ""
    return titulo if titulo[-1] in ".!?…" else titulo + "."


def _limpio(texto: str) -> str:
    """El texto arreglado para decirse, SIN el colchón del final.

    Va aparte porque cuando el cuento se graba de una sola toma, el colchón se pone una
    vez al final de todo y no después de cada frase: doce puntos de más adentro de un
    relato continuo son doce pausas que nadie pidió.
    """
    limpio = texto
    for viejo, nuevo in _PARA_DECIR:
        limpio = limpio.replace(viejo, nuevo)
    return " ".join(limpio.split()).replace(" ,", ",").replace(" .", ".")


def _toma_entera(texto: str, duracion_s: float) -> bool:
    """Si la toma trae todo el audio que debería.

    No alcanza con que el proveedor no falle: devolver medio audio es un WAV
    perfectamente válido, con HTTP 200. Si nadie compara contra lo que debería durar,
    el corte se descubre escuchando el producto terminado.
    """
    return duracion_s >= (len(texto.split()) / WORDS_PER_SECOND) * PISO_DE_TOMA


def duracion_de_wav(audio: bytes) -> float:
    """Segundos que dura un WAV, leídos de su cabecera.

    `wave` es stdlib: medir no cuesta una dependencia. Es la razón por la que el
    motor pide WAV y no mp3 aunque pese más.
    """
    with wave.open(io.BytesIO(audio), "rb") as w:
        if not (fps := w.getframerate()):
            raise ProviderError("El audio no declara frecuencia de muestreo: no se puede medir.")
        return round(w.getnframes() / fps, 3)


def _sabe_alinear(provider: object) -> bool:
    """Si a este proveedor se le puede pedir el audio con los tiempos de cada caracter.

    No alcanza con mirar si tiene el método: un envoltorio —el caché, por ejemplo— lo
    tiene SIEMPRE, y sólo puede cumplirlo si el proveedor que envuelve también lo tiene.
    Por eso quien envuelve declara `alinea`, y esa respuesta le gana al método.
    """
    if not hasattr(provider, "synthesize_aligned"):
        return False
    return bool(getattr(provider, "alinea", True))


def _recortar(audio: bytes, desde_s: float, hasta_s: float) -> bytes:
    """El pedazo del WAV que va de `desde_s` a `hasta_s`.

    Es lo que convierte una toma continua en las pistas por escena que el render
    espera. Cortar no rompe la continuidad: los pedazos se vuelven a pegar en el mismo
    orden y sin silencio en el medio, así que suena igual que la toma original — sólo
    que ahora se sabe en qué segundo cambia la imagen.
    """
    with wave.open(io.BytesIO(audio), "rb") as w:
        canales, ancho, fps = w.getnchannels(), w.getsampwidth(), w.getframerate()
        w.setpos(min(w.getnframes(), max(0, int(desde_s * fps))))
        marcos = w.readframes(max(0, int((hasta_s - desde_s) * fps)))

    salida = io.BytesIO()
    with wave.open(salida, "wb") as w:
        w.setnchannels(canales)
        w.setsampwidth(ancho)
        w.setframerate(fps)
        w.writeframes(marcos)
    return salida.getvalue()


def ataque_ms(audio: bytes) -> float:
    """Milisegundos de silencio antes de la primera palabra de la toma.

    Cero significa que el audio empieza encima de la primera consonante, y ahí la D de
    "Dino" pierde su explosión y suena "nano". Es lo único que distingue esa toma de una
    buena: dura lo que tiene que durar y el proveedor la dio por buena.

    El umbral es relativo al pico de la propia toma y no un valor fijo, porque el volumen
    depende de la voz y de los ajustes. Si el WAV no se puede medir, devuelve infinito:
    esto es un guardián, y un guardián que no sabe no frena la producción.
    """
    with wave.open(io.BytesIO(audio), "rb") as w:
        if w.getsampwidth() != 2 or not (fps := w.getframerate()):
            return float("inf")
        canales = w.getnchannels() or 1
        muestras = struct.unpack(f"<{w.getnframes() * canales}h", w.readframes(w.getnframes()))

    if not muestras:
        return 0.0
    umbral = max(200, max(max(muestras), -min(muestras)) // 50)
    for i, valor in enumerate(muestras):
        if abs(valor) >= umbral:
            return round(i / canales / fps * 1000, 1)
    return float("inf")  # toda la toma es silencio; de eso se ocupa el piso de duración


def tasa_real(story: Story) -> float:
    """Palabras por segundo MEDIDAS en el audio de esta historia.

    Existe para poder ajustar `WORDS_PER_SECOND` con datos en vez de con intuición.
    Si da sistemáticamente por debajo de la constante, todas las escenas se van a
    pasar de largo y no hay arreglo escena por escena que alcance: hay que recalibrar.
    """
    palabras = sum(len(t.text.split()) for e in story.scenes for t in e.audio)
    segundos = sum(e.audio_duration_s for e in story.scenes)
    return round(palabras / segundos, 2) if segundos else 0.0
