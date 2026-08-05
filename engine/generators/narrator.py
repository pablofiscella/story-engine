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
import wave
from pathlib import Path

from engine.core.constants import (
    NARRATION_OVERFLOW_TOLERANCE,
    WORDS_PER_SECOND,
)
from engine.core.enums import AudioKind, StoryStatus
from engine.core.exceptions import DomainError, ProviderError
from engine.core.interfaces import VoiceProvider
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


class StoryNarrator:
    """Convierte una historia escrita en una historia narrada."""

    def __init__(self, provider: VoiceProvider, *, narrator_voice: Voice | None = None) -> None:
        self._provider = provider
        #: La voz que lee la narración. Es del NARRADOR, no de un personaje: quien
        #: cuenta el cuento no está adentro del cuento.
        self._voz = narrator_voice or Voice(description="cálida y tranquila, de cuento infantil")

    async def narrate(self, story: Story, dest_dir: str | Path) -> Story:
        """Narra todas las escenas y deja la historia en NARRATED."""
        if not story.scenes:
            raise DomainError("La historia no tiene escenas: hay que escribirla antes de narrarla.")

        destino = Path(dest_dir)
        destino.mkdir(parents=True, exist_ok=True)
        personajes = story.characters_by_id

        limite = asyncio.Semaphore(CONCURRENCIA)

        async def una(escena: Scene) -> None:
            async with limite:
                escena.audio = await self._narrar_escena(escena, destino, personajes)

        await asyncio.gather(*(una(e) for e in story.scenes))
        story.closing_audio = await self._narrar_cierre(story, destino)

        self._avisar_desvios(story)
        if story.status is not StoryStatus.NARRATED:
            story.advance_to(StoryStatus.NARRATED)
        story.metadata.touch()
        return story

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
        if not audio:
            raise ProviderError(f"El proveedor de voz devolvió audio vacío para '{ruta.name}'.")

        duracion = duracion_de_wav(audio)
        _verificar_toma_entera(decible, duracion, ruta)

        ruta.write_bytes(audio)
        return AudioTrack(
            kind=kind,
            character_id=character_id,
            text=texto,
            path=str(ruta),
            duration_s=duracion,
            voice_id=voz.provider_voice_id or "",
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
    """
    limpio = texto
    for viejo, nuevo in _PARA_DECIR:
        limpio = limpio.replace(viejo, nuevo)
    return " ".join(limpio.split()).replace(" ,", ",").replace(" .", ".")


def _verificar_toma_entera(texto: str, duracion_s: float, ruta: Path) -> None:
    """Rechaza una toma que llegó cortada.

    No alcanza con que el proveedor no falle: devolver medio audio es un WAV
    perfectamente válido. Si nadie compara contra lo que debería durar, el corte se
    descubre escuchando el producto terminado.
    """
    esperado = len(texto.split()) / WORDS_PER_SECOND
    if duracion_s < esperado * PISO_DE_TOMA:
        raise ProviderError(
            f"La toma '{ruta.name}' dura {duracion_s:.1f}s y para decir {len(texto.split())} "
            f"palabras hacen falta unos {esperado:.1f}s. Llegó cortada."
        )


def duracion_de_wav(audio: bytes) -> float:
    """Segundos que dura un WAV, leídos de su cabecera.

    `wave` es stdlib: medir no cuesta una dependencia. Es la razón por la que el
    motor pide WAV y no mp3 aunque pese más.
    """
    with wave.open(io.BytesIO(audio), "rb") as w:
        if not (fps := w.getframerate()):
            raise ProviderError("El audio no declara frecuencia de muestreo: no se puede medir.")
        return round(w.getnframes() / fps, 3)


def tasa_real(story: Story) -> float:
    """Palabras por segundo MEDIDAS en el audio de esta historia.

    Existe para poder ajustar `WORDS_PER_SECOND` con datos en vez de con intuición.
    Si da sistemáticamente por debajo de la constante, todas las escenas se van a
    pasar de largo y no hay arreglo escena por escena que alcance: hay que recalibrar.
    """
    palabras = sum(len(t.text.split()) for e in story.scenes for t in e.audio)
    segundos = sum(e.audio_duration_s for e in story.scenes)
    return round(palabras / segundos, 2) if segundos else 0.0
