"""El narrador del formato LARGO: una imagen fija, una voz, media hora.

Es el hermano de `narrator.py` para el otro formato del nicho. El de cuentos graba
**una sola toma** y la corta por escena con la alineación por caracter, porque la
imagen cambia y hay que saber exactamente cuándo. Acá la imagen NO cambia nunca, y esa
única diferencia se lleva puesta media arquitectura:

- **No hace falta alineación.** No hay nada que sincronizar: lo único que se necesita
  es el audio en orden.
- **No hace falta una toma sola.** Y menos mal, porque **no entra**: ver
  `LIMITE_DE_PEDIDO`.
- **No hace falta pausa entre escenas.** Las "escenas" del formato largo son párrafos
  de un mismo texto corrido; el silencio lo pone la puntuación.

POR QUÉ EXISTE, con el dato que lo justifica: los 14 canales del nicho devocional
medidos el 8-ago-2026 tienen DOS formatos, y **el que más vistas junta por video es el
largo** — la mediana de los 30 más vistos va de 31 a 158 minutos en 8 de los 14.
[The Gentle Bible](https://youtube.com/@thegentlebible) lee el Evangelio de Juan
durante cuatro horas sobre un óleo fijo y saca 156.271 vistas por video. Pablo,
mirándolos: *"Los últimos videos tienen sólo una imagen y sólo texto y audio"*.

**EL LÍMITE QUE DEFINE EL MÓDULO, medido contra la cuenta real el 8-ago-2026:**

    Request text length (209000) exceeds the maximum text length of 5000 characters.
    Please use Studio for long form TTS.

O sea que un devocional de diez minutos —unos 8.300 caracteres— **no se puede pedir de
una sola vez**, y uno de cuarenta minutos necesita siete pedidos. No es un detalle de
implementación: es la razón por la que este módulo existe en vez de subirle una
constante al narrador de cuentos.

**Y `previous_text` no es la salida.** ElevenLabs tiene ese parámetro justamente para
coser dos pedidos con la misma prosodia, y con `eleven_v3` devuelve, textual:
*"Providing previous_text or next_text is not yet supported with the 'eleven_v3'
model"*. Sí anda en `eleven_multilingual_v2`, que además **cuesta exactamente lo
mismo** (los dos: 366 caracteres → 101 créditos, medido). No se cambia igual, y la
razón no es técnica: **las cinco tomas de voz que Pablo tiene para elegir se grabaron
con v3**, y cambiar de modelo cambia cómo suena `bill`. Elegir una voz escuchando y
después cambiarle el modelo por atrás es tirar la elección.

Así que la costura se resuelve donde se puede resolver sin cambiar el producto:
**cortando por donde el texto ya respira**. Un bloque nunca parte una escena al medio,
y entre bloque y bloque queda el silencio de un punto final — que es exactamente el
aire que hay entre dos párrafos de un devocional. Con imagen fija, además, no hay nada
en pantalla que delate el corte.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from engine.core.enums import AudioKind, StoryStatus
from engine.core.exceptions import DomainError
from engine.core.interfaces import VoiceProvider
from engine.core.models.audio import AudioTrack
from engine.core.models.story import Story
from engine.core.retry import con_reintentos
from engine.generators.narrator import (
    COLCHON_FINAL,
    PISO_DE_TOMA,
    _limpio,
    _titulo_dicho,
    duracion_de_wav,
)
from engine.prompts import voz as prompts_voz

logger = logging.getLogger(__name__)

#: Cuántos caracteres acepta ElevenLabs en UN pedido. Medido contra la cuenta real el
#: 8-ago-2026 pidiendo 209.000 y leyendo el error, que lo dice con el número.
#:
#: No se deduce del plan ni de la documentación: se preguntó. Un pedido que se pasa
#: falla con 400 y **no gasta créditos**, así que averiguarlo salió gratis.
LIMITE_DE_PEDIDO = 5000

#: A cuántos caracteres se apunta por bloque.
#:
#: Bien abajo del límite duro por dos razones que se suman: al texto se le agregan la
#: dirección de actuación y el colchón final —que también cuentan— y un bloque que
#: raspa el techo obliga a partir una escena al medio, que es justo lo que este módulo
#: evita. Con 3.500, un devocional de diez minutos entra en tres bloques y uno de
#: cuarenta en once.
BLOQUE_OBJETIVO = 3500

#: Cuántos bloques se piden a la vez. **UNO.**
#:
#: El plan acepta tres concurrentes (medido el 5-ago-2026), pero acá no se usa: los
#: bloques son partes de un mismo relato y pedirlos en paralelo no ahorra nada que
#: valga el riesgo de que uno falle a mitad de camino y queden huecos numerados en el
#: medio del devocional. Un devocional largo se genera una vez y se publica muchas.
CONCURRENCIA = 1


class StillNarrator:
    """Narra un guion largo en bloques, para un video de imagen fija."""

    def __init__(
        self,
        provider: VoiceProvider,
        *,
        direccion: str = "",
        bloque_objetivo: int = BLOQUE_OBJETIVO,
    ) -> None:
        self._provider = provider
        #: La dirección de actuación, entre corchetes, que va al principio de CADA
        #: bloque. En cada uno y no sólo en el primero: para el modelo cada pedido es
        #: un texto nuevo, y el bloque 2 sin dirección vuelve a leer como un noticiero.
        self._direccion = direccion
        self._bloque = bloque_objetivo

    async def narrate(self, story: Story, dest_dir: str | Path) -> list[AudioTrack]:
        """Narra el guion. Devuelve las pistas del CUERPO, en orden y ya medidas.

        El título y el cierre no vienen en esa lista: se dejan en `story.title_audio` y
        `story.closing_audio`, igual que en los cuentos. **Y se piden en su propio
        bloque**, que es la decisión menos obvia del método: mezclados adentro del
        primero y del último no se sabría cuánto duran, y el render necesita ese número
        para saber cuánto tiempo dejar el título en pantalla y cuándo hacer aparecer el
        pedido de comentario. Sin alineación por caracter —que este formato no usa— la
        única forma de saber cuánto dura una frase es pedirla sola y medirla.

        No toca `story.scenes[i].audio` a propósito: en este formato un bloque no
        corresponde a una escena, así que colgarlo de una sería mentir sobre lo que ese
        archivo contiene.
        """
        if not story.scenes:
            raise DomainError("El guion no tiene escenas: no hay nada que narrar.")

        destino = Path(dest_dir)
        destino.mkdir(parents=True, exist_ok=True)
        limite = asyncio.Semaphore(CONCURRENCIA)

        async def pedir(nombre: str, texto: str) -> AudioTrack:
            async with limite:
                return await self._un_bloque(nombre, texto, destino)

        if titulo := _titulo_dicho(story):
            story.title_audio = [
                await pedir("titulo", prompts_voz.COLCHON_INICIAL + " " + titulo)
            ]

        bloques = self._armar_bloques([_limpio(e.narration) for e in story.scenes])
        logger.info(
            "Formato largo: %s escenas en %s bloque(s) de hasta %s caracteres.",
            len(story.scenes), len(bloques), self._bloque,
        )
        cuerpo = [await pedir(f"bloque_{i:02d}", texto) for i, texto in enumerate(bloques)]

        # El cierre va en UNA pista y no en dos —promesa e invitación juntas— porque
        # se dicen seguidas y partirlas metería un corte de prosodia justo antes de la
        # línea que pide el comentario, que es la que sostiene el nicho.
        if cierre := " ".join(_limpio(t) for t in (story.moral, story.closing_question) if t):
            story.closing_audio = [await pedir("cierre", cierre)]

        _marcar_narrada(story)
        story.metadata.touch()
        return cuerpo

    # ------------------------------------------------------------------ estructura
    def _armar_bloques(self, piezas: list[str]) -> list[str]:
        """Junta las escenas en bloques que entren en un pedido.

        **Ninguna escena se parte.** Si una sola no entrara en un bloque, se manda
        igual y sola: partir una escena al medio pondría el corte adentro de una
        frase, que es el único lugar donde se escucharía.
        """
        bloques: list[str] = []
        actual: list[str] = []
        largo = 0

        for pieza in piezas:
            costo = len(pieza) + 1
            if actual and largo + costo > self._bloque:
                bloques.append(" ".join(actual))
                actual, largo = [], 0
            actual.append(pieza)
            largo += costo
        if actual:
            bloques.append(" ".join(actual))
        return bloques

    # ---------------------------------------------------------------------- pedido
    async def _un_bloque(self, nombre: str, texto: str, destino: Path) -> AudioTrack:
        """Pide un bloque, lo mide y lo guarda.

        El guardián de toma cortada es el mismo que el de los cuentos y por la misma
        razón medida: cuando el proveedor devuelve la mitad del audio **no falla** —
        devuelve un WAV válido, más corto—, y el problema aparece escuchando el
        producto terminado. En un devocional de cuarenta minutos, escucharlo entero
        para descubrirlo cuesta cuarenta minutos.
        """
        pedido = " ".join(x for x in (self._direccion, texto) if x) + COLCHON_FINAL
        if len(pedido) > LIMITE_DE_PEDIDO:
            raise DomainError(
                f"El bloque «{nombre}» pide {len(pedido)} caracteres y el máximo por "
                f"pedido es {LIMITE_DE_PEDIDO}. Hay que bajar `bloque_objetivo`."
            )

        audio = await con_reintentos(
            lambda: self._provider.synthesize(pedido, audio_format="wav"),
            al_reintentar=lambda n, e: logger.warning(
                "Bloque %s: la voz falló (%s). Reintento %s.", nombre, e, n
            ),
        )
        ruta = destino / f"{nombre}.wav"
        ruta.write_bytes(audio)
        duracion = duracion_de_wav(audio)

        esperado = len(texto) / _CARACTERES_POR_SEGUNDO
        if duracion < esperado * PISO_DE_TOMA:
            logger.warning(
                "Bloque %s: llegaron %.1fs para %s caracteres (se esperaban ~%.0fs). "
                "La toma puede haber venido cortada.",
                nombre, duracion, len(texto), esperado,
            )

        logger.info("Bloque %s: %s caracteres · %.1fs", nombre, len(texto), duracion)
        return AudioTrack(
            kind=AudioKind.NARRATION,
            text=texto,
            path=str(ruta),
            duration_s=duracion,
        )


#: Caracteres hablados por segundo, para saber si una toma llegó entera.
#:
#: Sale de las cinco tomas de voz del 7-ago-2026: `bill` dice 138,8 palabras por
#: minuto, y una palabra inglesa de devocional promedia ~5,6 caracteres con su espacio.
#: Da ~13 caracteres por segundo. Es una estimación y se usa sólo como PISO —para
#: detectar la toma partida al medio—, nunca para calcular una duración: eso se mide.
_CARACTERES_POR_SEGUNDO = 13.0


def _marcar_narrada(story: Story) -> None:
    """Deja la historia en NARRATED, y no rompe si ya venía más adelante.

    **Volver a narrar un devocional YA renderizado es normal acá**, y ésa es la
    diferencia con los cuentos: se arregla la dirección de voz o se cambia la voz, y hay
    que rehacer sólo el audio de una pieza que ya existe. La máquina de estados va en un
    solo sentido a propósito —no se puede renderizar lo que no se narró— pero eso es un
    piso, no un techo: que el rótulo esté más adelante no es motivo para tirar diez
    minutos de TTS recién pagado.

    Pasó el 8-ago-2026, con el audio ya generado y guardado: `InvalidStateTransitionError:
    No se puede pasar de 'rendered' a 'narrated'`. El audio estaba bien; lo que estaba
    mal era romper por la etiqueta.
    """
    if story.status in (StoryStatus.NARRATED, StoryStatus.RENDERED, StoryStatus.PUBLISHED):
        logger.info(
            "La historia ya estaba en '%s': se rehizo el audio y se deja el estado como "
            "está.", story.status.value,
        )
        return
    story.advance_to(StoryStatus.NARRATED)


def caracteres_de(story: Story) -> int:
    """Cuántos caracteres de TTS pide este guion. Se paga por esto.

    Existe para poder decir el costo ANTES de gastarlo, que es lo que pidió Pablo el
    8-ago-2026: *"antes de generar algo largo, calculá cuánto cuesta y decímelo"*. Con
    30.000 caracteres por media hora de audio, la diferencia entre estimar y medir es
    la diferencia entre un video y un mes de cuota.

    Cuenta lo mismo que se va a mandar —título, escenas, promesa e invitación— pero no
    la dirección de actuación ni el colchón, que dependen de en cuántos bloques caiga.
    El error es de menos de un 2 %.
    """
    piezas = [_titulo_dicho(story)]
    piezas += [_limpio(e.narration) for e in story.scenes]
    piezas += [_limpio(t) for t in (story.moral, story.closing_question) if t]
    return sum(len(p) for p in piezas if p)
