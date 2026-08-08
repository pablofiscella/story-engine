"""El render del formato LARGO: UNA imagen fija, texto y audio. Nada más.

Es el otro render del motor, y es el más simple de los dos justamente porque el
formato lo es. Pablo, 8-ago-2026, mirando los canales del nicho: *"Los últimos videos
tienen sólo una imagen y sólo texto y audio"*.

QUÉ DESAPARECE RESPECTO DEL SHORT, y no es poco:

    storyboard · verificador de anatomía · continuidad entre imágenes ·
    fundido cruzado · una imagen por escena · la pausa entre escenas

Todo eso existe para que SEIS imágenes cuenten una historia sin contradecirse. Con una
sola no hay nada que encadenar: no hay continuidad que romper ni anatomía que contar
más de una vez. **El formato barato del nicho es barato por esto**, no por la
resolución: [The Gentle Bible](https://youtube.com/@thegentlebible) lee el Evangelio de
Juan cuatro horas sobre un óleo fijo y saca 156.271 vistas por video con 78 videos.

**HORIZONTAL Y NO VERTICAL.** El short es 9:16 porque compite en un feed; esto es un
video de YouTube que alguien deja puesto para dormirse o para rezar a la mañana, y se
mira en una tele o en un teléfono acostado. Los 8 canales del nicho que hacen formato
largo (medidos el 8-ago-2026: mediana de 31 a 158 minutos) publican en 16:9.

LAS TRES COSAS QUE SE VEN, y cuándo:

    el título      mientras se dice, sobre la imagen
    (nada)         todo el cuerpo del devocional: la imagen sola
    la invitación  cuando empieza a decirse, y hasta el final

**El medio va sin texto a propósito**, y es la diferencia más grande con el short. Un
short lleva subtítulo permanente porque se mira sin sonido en un feed; esto se ESCUCHA
—con los ojos cerrados, la mitad de las veces— y un cartel que cambia cada minuto es
exactamente lo que impide que alguien se duerma con esto puesto.

**Y es una decisión, no una medición: hay que decirlo así.** De los 14 canales se midió
que **ninguno sube subtítulos propios** (`caption: false` en los 14), y eso NO es lo
mismo — una pista de subtítulos que se prende y se apaga no dice nada sobre si el video
lleva texto quemado en el cuadro. Sobre eso no hay dato. Si Pablo quiere el texto del
devocional en pantalla, es agregar una capa más con el mismo `_texto()`: el tratamiento
ya es el correcto y está resuelto acá abajo.

Se hereda tal cual del short lo que ya se ganó ahí, porque son los mismos errores:

1. **El audio se concatena re-codificando, nunca con `-c copy`** — copiar corta el
   final de cada pista.
2. **La normalización va al final, sobre el audio ya armado** — por tramo deja cada
   bloque con un volumen distinto.
3. **El texto se ancla por donde TERMINA el bloque** (`h*0.88-text_h`). Es la
   corrección del 7-ago-2026: anclado por arriba, la invitación del devocional se
   salía del cuadro por abajo, y era la única línea ilegible del video — justo la que
   pide el comentario que sostiene el nicho.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from engine.core.constants import COLA_FINAL_S
from engine.core.enums import AspectRatio, StoryStatus
from engine.core.exceptions import DomainError
from engine.core.models.audio import AudioTrack
from engine.core.models.story import Story
from engine.render.video import (
    CONTORNO,
    FUENTE,
    LOUDNESS,
    TAMANO,
    Y_DEL_CIERRE,
    _envolver,
)

logger = logging.getLogger(__name__)

#: Cuadros por segundo. **10 y no 30**, y es la decisión que hace viable el formato.
#:
#: La imagen no cambia nunca: los 30 cuadros de cada segundo son idénticos, así que
#: veinte de cada treinta son trabajo de codificación por nada. Medido sobre el
#: devocional de prueba, bajar a 10 corta el tiempo de render sin que se vea ninguna
#: diferencia — no hay movimiento que pueda quedar entrecortado. YouTube acepta 10 fps
#: sin objetar; lo que no acepta es un video de una hora que tardó dos en salir.
FPS_IMAGEN_FIJA = 10

#: Cuánto queda el título en pantalla después de que se termina de decir.
#:
#: El short lo saca apenas se dice porque cada segundo cuenta. Acá no: quien llega a un
#: devocional de media hora lo eligió por el título, y dejarlo dos segundos más es lo
#: que le confirma que abrió lo que buscaba.
COLA_DEL_TITULO_S = 2.0

#: Cuánto antes de que la voz lo diga aparece la invitación.
#:
#: Un segundo, igual que en el short y por la misma razón: si el texto está desde el
#: principio decora, y si aparece cuando se dice, se lee. En un video largo importa
#: más todavía — el texto que estuvo cuarenta minutos en pantalla ya no lo mira nadie.
ADELANTO_DE_LA_INVITACION_S = 1.0

#: Cuántos caracteres entran cómodos en una línea, en horizontal.
#:
#: Más que en el short (20) porque el cuadro es el doble de ancho y la mitad de alto:
#: con 20 la invitación ocupaba cinco renglones en una pantalla apaisada, que se lee
#: peor que dos renglones largos.
LARGO_DE_LINEA_ANCHA = 38


class StillRenderer:
    """Arma el MP4 largo: una imagen quieta, la narración entera y dos textos."""

    def __init__(
        self, *, aspect: AspectRatio = AspectRatio.HORIZONTAL, fps: int = FPS_IMAGEN_FIJA
    ) -> None:
        if shutil.which("ffmpeg") is None:
            raise DomainError("Falta ffmpeg: el render lo necesita para armar el video.")
        self._ancho, self._alto = TAMANO[aspect]
        self._fps = fps

    def render(
        self,
        story: Story,
        dest: str | Path,
        *,
        imagen: str | Path,
        cuerpo: list[AudioTrack],
    ) -> Path:
        """Devuelve la ruta del MP4.

        `imagen` y `cuerpo` vienen por parámetro y no de `story` a propósito: en este
        formato la imagen no pertenece a ninguna escena y un bloque de audio tampoco.
        Colgarlos de `story.scenes[0]` sería dejar escrito que esa imagen es de la
        primera escena, que es exactamente lo que no es.
        """
        png = Path(imagen)
        self._verificar(story, png, cuerpo)
        salida = Path(dest)
        salida.parent.mkdir(parents=True, exist_ok=True)

        pistas = [*story.title_audio, *cuerpo, *story.closing_audio]
        total = sum(t.duration_s for t in pistas) + COLA_FINAL_S

        # --- cuándo se ve cada texto -------------------------------------------
        titulo_hasta = sum(t.duration_s for t in story.title_audio) + COLA_DEL_TITULO_S
        invitacion_desde = max(
            0.0,
            total - COLA_FINAL_S
            - sum(t.duration_s for t in story.closing_audio)
            - ADELANTO_DE_LA_INVITACION_S,
        )

        capas = [self._encuadrar()]
        if story.metadata.title:
            capas.append(
                self._texto(
                    story.metadata.title,
                    salida.parent / "_titulo_largo.txt",
                    y="h*0.12",
                    tope=72,
                    hasta=titulo_hasta,
                )
            )
        if story.closing_question:
            capas.append(
                self._texto(
                    story.closing_question,
                    salida.parent / "_invitacion_larga.txt",
                    y=Y_DEL_CIERRE,
                    tope=52,
                    desde=invitacion_desde,
                )
            )
        arranque = max(0.0, total - COLA_FINAL_S)
        capas.append(f"fade=t=out:st={arranque:.3f}:d={COLA_FINAL_S}")

        # --- el audio: los bloques pegados, y recién ahí normalizado ------------
        entradas = ["-loop", "1", "-t", f"{total:.3f}", "-i", str(png)]
        entradas += [x for t in pistas for x in ("-i", t.path)]
        pegado = "".join(f"[{i}:a]" for i in range(1, len(pistas) + 1))
        filtro = (
            f"[0:v]{','.join(capas)}[video];"
            f"{pegado}concat=n={len(pistas)}:v=0:a=1[unido];"
            f"[unido]apad=pad_dur={COLA_FINAL_S},{LOUDNESS}[audio]"
        )

        logger.info(
            "Render fijo: %s pista(s) · %.1f min · %sx%s a %s fps",
            len(pistas), total / 60, self._ancho, self._alto, self._fps,
        )
        subprocess.run(
            ["ffmpeg", "-y", *entradas, "-filter_complex", filtro,
             "-map", "[video]", "-map", "[audio]",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "23",
             "-r", str(self._fps),
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(salida)],
            check=True, capture_output=True,
        )
        # Sólo si venía de narrar. Re-renderizar algo ya renderizado es normal en este
        # formato —se cambia la imagen o el texto de pantalla sin tocar el audio— y no
        # tiene por qué romper por el rótulo.
        if story.status is StoryStatus.NARRATED:
            story.advance_to(StoryStatus.RENDERED)
        story.metadata.touch()
        return salida

    # ------------------------------------------------------------------------
    def _encuadrar(self) -> str:
        return (
            f"scale={self._ancho}:{self._alto}:force_original_aspect_ratio=increase,"
            f"crop={self._ancho}:{self._alto},setsar=1"
        )

    def _texto(
        self,
        texto: str,
        archivo: Path,
        *,
        y: str,
        tope: int,
        desde: float | None = None,
        hasta: float | None = None,
    ) -> str:
        """Un texto legible sobre la imagen, que ENTRA en el cuadro y aparece a tiempo.

        `desde` y `hasta` son lo que este render agrega al del short: allá los textos
        viven en su propio tramo de video, acá hay un solo tramo de cuarenta minutos y
        la ventana de cada texto es lo único que los separa.
        """
        lineas = _envolver(texto, LARGO_DE_LINEA_ANCHA)
        mas_larga = max(len(x) for x in lineas)
        tam = min(tope, int(self._ancho * 0.82 / (0.58 * mas_larga)))

        archivo.write_text("\n".join(lineas), encoding="utf-8")
        ventana = ""
        if desde is not None and hasta is not None:
            ventana = f":enable='between(t,{desde:.3f},{hasta:.3f})'"
        elif desde is not None:
            ventana = f":enable='gte(t,{desde:.3f})'"
        elif hasta is not None:
            ventana = f":enable='lte(t,{hasta:.3f})'"
        return (
            f"drawtext=fontfile={FUENTE}:textfile={archivo}:"
            f"fontcolor=white:fontsize={tam}:line_spacing=14:text_align=C:"
            f"borderw={CONTORNO}:bordercolor=black@0.85:"
            f"x=(w-text_w)/2:y={y}{ventana}"
        )

    def _verificar(self, story: Story, imagen: Path, cuerpo: list[AudioTrack]) -> None:
        """Falla antes de invocar a ffmpeg, con un mensaje que se entiende.

        Vale más acá que en el short: un devocional largo llega a este paso con media
        hora de TTS ya pagada, y un error de ffmpeg de treinta líneas de jerga sobre
        algo ya gastado es la peor forma de enterarse.
        """
        if not imagen.is_file():
            raise DomainError(f"No está la imagen del video: {imagen}")
        if not cuerpo:
            raise DomainError("No hay audio del cuerpo: hay que narrar antes de renderizar.")
        faltan = [t.path for t in cuerpo if not Path(t.path).is_file()]
        if faltan:
            raise DomainError(f"Faltan archivos de audio en el disco: {faltan}")
        if not Path(FUENTE).exists():
            raise DomainError(f"Falta la tipografía {FUENTE}: el título y el cierre la usan.")
        if story.closing_question and not story.closing_audio:
            # No es fatal —el video sale igual— pero sí es un aviso: la invitación se
            # vería sin que nadie la diga, y en este nicho esa línea es el producto.
            logger.warning(
                "El guion tiene invitación pero no se narró: va a aparecer escrita y muda."
            )
