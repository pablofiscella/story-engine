"""El render del formato LARGO: pocas imágenes, subtítulos y audio.

Es el otro render del motor, y es el más simple de los dos justamente porque el
formato lo es. Pablo, 8-ago-2026, mirando los canales del nicho: *"Los últimos videos
tienen sólo una imagen y sólo texto y audio"*.

QUÉ DESAPARECE RESPECTO DEL SHORT, y no es poco:

    storyboard · verificador de anatomía · continuidad entre imágenes ·
    una imagen por escena · la pausa entre escenas

Todo eso existe para que SEIS imágenes cuenten una historia sin contradecirse. Acá las
imágenes **no cuentan nada**: son ambientes, paisajes de la misma hora del día, y por
eso pueden rotar sin que haya continuidad que romper ni anatomía que contar dos veces.
**El formato barato del nicho es barato por esto**, no por la resolución:
[The Gentle Bible](https://youtube.com/@thegentlebible) lee el Evangelio de Juan cuatro
horas sobre un óleo fijo y saca 156.271 vistas por video con 78 videos.

**LAS IMÁGENES ROTAN, y no siempre fue así.** El primer devocional largo salió con una
sola, nueve minutos. Pablo, mirándolo: *"que las imágenes vayan rotando, una cada cinco
minutos más o menos"*. A US$ 0,005 cada una, veinte minutos de video cuestan **dos
centavos** de imagen: la rotación es gratis comparada con la voz, que es el 95 % del
costo. Ver `IMAGEN_CADA_S`.

**HORIZONTAL Y NO VERTICAL.** El short es 9:16 porque compite en un feed; esto es un
video de YouTube que alguien deja puesto para dormirse o para rezar a la mañana, y se
mira en una tele o en un teléfono acostado. Los 8 canales del nicho que hacen formato
largo (medidos el 8-ago-2026: mediana de 31 a 158 minutos) publican en 16:9.

LO QUE SE VE, y cuándo:

    el título      los primeros segundos, arriba — SIN que nadie lo diga
    los subtítulos todo el cuerpo, abajo, sincronizados con la voz
    la invitación  cuando empieza a decirse, y hasta el final

**Los subtítulos son la corrección del 8-ago-2026.** Este módulo decía acá que el medio
iba sin texto a propósito —"esto se escucha con los ojos cerrados"— y aclaraba, bien,
que era una decisión y no una medición: de los 14 canales se midió que ninguno sube
pista de subtítulos, y eso no dice nada sobre texto quemado en el cuadro. Pablo decidió
lo contrario y ahora el cuerpo va subtitulado de punta a punta. Los tiempos **no se
estiman**: salen de la alineación por caracter de ElevenLabs, la misma pieza con la que
el narrador de cuentos corta su toma continua. Ver `render.subtitulos`.

**Y el título ya no se dice en voz alta.** Ninguno de los cinco canales del nicho que se
transcribieron lo hace. Como no hay audio del título, cuánto queda en pantalla se
calcula por velocidad de lectura: ver `LECTURA_POR_SEGUNDO`.

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
import math
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from engine.core.constants import COLA_FINAL_S
from engine.core.enums import AspectRatio, StoryStatus
from engine.core.exceptions import DomainError
from engine.core.models.story import Story
from engine.generators.narrator import _limpio
from engine.generators.still_narrator import NarracionLarga
from engine.render.subtitulos import (
    RENGLONES as RENGLONES_POR_SUBTITULO,
)
from engine.render.subtitulos import (
    Subtitulo,
    caracteres_por_linea,
    escribir_ass,
    subtitulos_de,
)
from engine.render.video import (
    CONTORNO,
    FUENTE,
    LOUDNESS,
    TAMANO,
    Y_DEL_CIERRE,
    _encadenar,
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

#: Cuánto queda el título en pantalla después de que se termina de leer.
#:
#: El short lo saca apenas se dice porque cada segundo cuenta. Acá no: quien llega a un
#: devocional de media hora lo eligió por el título, y dejarlo dos segundos más es lo
#: que le confirma que abrió lo que buscaba.
COLA_DEL_TITULO_S = 2.0

#: Caracteres que alguien lee por segundo en una pantalla, para un título grande.
#:
#: Existe porque **el título ya no se narra** y antes su placa duraba lo que tardaba en
#: decirse. Sin audio hay que estimar, y acá estimar está bien: si sobra un segundo el
#: título se ve un segundo de más, que no rompe nada. No se usa para nada que tenga que
#: caer sincronizado — eso se mide con la alineación.
#:
#: 12 c/s es lectura cómoda para un texto grande y centrado, más lento que los ~20 c/s
#: de lectura de corrido: acá el espectador recién abrió el video y todavía está
#: acomodándose.
LECTURA_POR_SEGUNDO = 12.0

#: Lo menos que dura el título en pantalla, por corto que sea.
TITULO_MINIMO_S = 6.0

#: Cada cuánto cambia la imagen. **Cinco minutos.**
#:
#: Pablo, 8-ago-2026, mirando el devocional de una sola imagen: *"que las imágenes vayan
#: rotando, una cada cinco minutos más o menos"*. En veinte minutos son cuatro.
#:
#: No hay storyboard ni verificador de anatomía detrás de esto, y es lo que lo hace
#: barato: **las imágenes de este formato no son escenas, son ambientes**. Ninguna
#: continúa a la anterior, así que no hay continuidad que romper. Cuatro imágenes de
#: calidad `low` cuestan US$ 0,02 contra los US$ 0,72 de voz de un video de veinte
#: minutos — el 2,7 % del costo.
IMAGEN_CADA_S = 300.0

#: Cuánto dura el fundido cruzado entre una imagen y la siguiente. **Dos segundos.**
#:
#: Diez veces más largo que el del short (0,4 s), y por la razón contraria: allá la
#: escena dura cinco segundos y medio segundo de cruce se siente lento; acá la imagen
#: estuvo cinco minutos quieta y un cruce corto se ve como un corte de cámara. Lo que
#: se está vendiendo es quietud.
TRANSICION_LARGA_S = 2.0

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
    """Arma el MP4 largo: paisajes que rotan, la narración entera y su texto."""

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
        imagenes: Sequence[str | Path],
        narracion: NarracionLarga,
    ) -> Path:
        """Devuelve la ruta del MP4.

        `imagenes` y `narracion` vienen por parámetro y no de `story` a propósito: en
        este formato una imagen no pertenece a ninguna escena y un bloque de audio
        tampoco. Colgarlos de `story.scenes[0]` sería dejar escrito que esa imagen es de
        la primera escena, que es exactamente lo que no es.

        Se aceptan las imágenes que haya: con una, el video queda como el del 8-ago; con
        cuatro, rotan. `cuantas_imagenes()` dice cuántas pedir para una duración dada.
        """
        pngs = [Path(x) for x in imagenes]
        self._verificar(story, pngs, narracion)
        salida = Path(dest)
        salida.parent.mkdir(parents=True, exist_ok=True)

        pistas = narracion.pistas
        total = sum(t.duration_s for t in pistas) + COLA_FINAL_S

        # --- las imágenes, repartidas y encadenadas -----------------------------
        # Cada tramo se genera MÁS LARGO que su parte, porque el cruce con el siguiente
        # se come `TRANSICION_LARGA_S`. Es el mismo margen que usa el short y por la
        # misma razón: sin él la imagen se va antes de tiempo.
        parte = total / len(pngs)
        entradas: list[str] = []
        filtros: list[str] = []
        tramos: list[str] = []
        for i, png in enumerate(pngs):
            entradas += [
                "-loop", "1", "-t", f"{parte + TRANSICION_LARGA_S:.3f}", "-i", str(png)
            ]
            filtros.append(f"[{i}:v]{self._encuadrar()}[v{i}]")
            tramos.append(f"[v{i}]")
        cadena_v = _encadenar(tramos, [parte] * len(pngs), TRANSICION_LARGA_S)

        # --- cuándo se ve cada texto -------------------------------------------
        # El título ya no se narra: su placa dura lo que se tarda en LEERLO.
        titulo_hasta = _lectura_s(story.metadata.title or "") + COLA_DEL_TITULO_S
        invitacion_desde = self._cuando_la_invitacion(story, narracion, total)

        capas: list[str] = []
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
        # Los subtítulos van DESPUÉS del título y de la invitación en la cadena, así que
        # si alguna vez se solaparan, el renglón medido queda arriba y no tapado.
        if subs := self._subtitulos(story, narracion):
            ass = escribir_ass(
                subs, salida.parent / "_subtitulos.ass",
                ancho=self._ancho, alto=self._alto,
            )
            capas.append(f"ass=filename={_para_filtro(ass)}")
        arranque = max(0.0, total - COLA_FINAL_S)
        capas.append(f"fade=t=out:st={arranque:.3f}:d={COLA_FINAL_S}")

        # --- el audio: los bloques pegados, y recién ahí normalizado ------------
        base = len(pngs)
        entradas += [x for t in pistas for x in ("-i", t.path)]
        pegado = "".join(f"[{base + i}:a]" for i in range(len(pistas)))
        filtro = ";".join(
            [
                *filtros,
                f"{cadena_v};[vcrudo]{','.join(capas)}[video]",
                f"{pegado}concat=n={len(pistas)}:v=0:a=1[unido]",
                f"[unido]apad=pad_dur={COLA_FINAL_S},{LOUDNESS}[audio]",
            ]
        )

        logger.info(
            "Render largo: %s imagen(es) de %.1f min · %s pista(s) · %.1f min · "
            "%s subtítulos · %sx%s a %s fps",
            len(pngs), parte / 60, len(pistas), total / 60, len(subs),
            self._ancho, self._alto, self._fps,
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
    def _cuando_la_invitacion(
        self, story: Story, narracion: NarracionLarga, total: float
    ) -> float:
        """En qué segundo aparece la placa del CTA. **Medido, no estimado.**

        Y es una corrección, no un refinamiento. El cálculo anterior restaba la
        duración del cierre ENTERO —promesa más invitación— y le sacaba un segundo más
        de adelanto, así que la placa entraba **mientras todavía se estaba diciendo la
        promesa**. Con el medio del video sin texto eso no molestaba a nadie: la placa
        aparecía sobre la imagen sola. Con subtítulos, el renglón de la promesa y la
        placa del CTA se dibujan **a la misma altura y al mismo tiempo**, y quedan los
        dos ilegibles. Se vio mirando un fotograma de la muestra a los 67 s.

        Que es, otra vez, el error del 7-ago-2026: el CTA —la línea que pide el
        comentario, o sea la que sostiene el nicho— siendo lo único que no se puede
        leer del video.

        Con la alineación del bloque del cierre se sabe **en qué segundo exacto termina
        de decirse la promesa**, que es exactamente cuando el subtítulo de la promesa se
        va y cuando empieza a decirse la invitación. Ya no hace falta adelantarla: el
        adelanto existía para que el texto entrara "cuando se dice", y ahora entra
        cuando se dice.
        """
        fin_del_cuerpo = sum(b.pista.duration_s for b in narracion.cuerpo)
        if narracion.cierre and story.moral:
            try:
                return fin_del_cuerpo + narracion.cierre.marcas.fin_de(_limpio(story.moral))
            except ValueError as e:
                logger.warning(
                    "No se pudo ubicar la promesa en el audio del cierre (%s): la "
                    "invitación se ubica por duración, como antes.", e,
                )
        return max(
            0.0,
            total - COLA_FINAL_S
            - sum(t.duration_s for t in story.closing_audio)
            - ADELANTO_DE_LA_INVITACION_S,
        )

    def _subtitulos(self, story: Story, narracion: NarracionLarga) -> list[Subtitulo]:
        """Los renglones de todo el cuerpo, con los segundos medidos del audio.

        El `offset` de cada bloque es cuánto audio va antes: los tiempos de la
        alineación son relativos a su pedido y el video es uno solo.

        **Del cierre se subtitula la promesa pero NO la invitación**, y no es un
        olvido: la invitación ya se dibuja grande y sola con `Y_DEL_CIERRE`, que es el
        tratamiento que se le da al CTA porque es la línea que sostiene el nicho.
        Subtitularla además sería el mismo texto dos veces en pantalla.
        """
        ancho = caracteres_por_linea(self._ancho)
        maximo = ancho * RENGLONES_POR_SUBTITULO
        subs: list[Subtitulo] = []
        offset = 0.0
        for bloque in narracion.cuerpo:
            subs += subtitulos_de(
                bloque.pista.text, bloque.marcas, offset_s=offset, maximo=maximo
            )
            offset += bloque.pista.duration_s
        if narracion.cierre and story.moral:
            subs += subtitulos_de(
                _limpio(story.moral),
                narracion.cierre.marcas,
                offset_s=offset,
                maximo=maximo,
            )
        return subs

    def _encuadrar(self) -> str:
        # `fps` acá y no sólo en la salida: `xfade` exige que los dos tramos que cruza
        # tengan el mismo framerate, y sin fijarlo un PNG en bucle entra a 25.
        return (
            f"scale={self._ancho}:{self._alto}:force_original_aspect_ratio=increase,"
            f"crop={self._ancho}:{self._alto},setsar=1,fps={self._fps}"
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

    def _verificar(
        self, story: Story, imagenes: list[Path], narracion: NarracionLarga
    ) -> None:
        """Falla antes de invocar a ffmpeg, con un mensaje que se entiende.

        Vale más acá que en el short: un devocional largo llega a este paso con media
        hora de TTS ya pagada, y un error de ffmpeg de treinta líneas de jerga sobre
        algo ya gastado es la peor forma de enterarse.
        """
        if not imagenes:
            raise DomainError("No hay ninguna imagen: el video no tendría qué mostrar.")
        if faltan := [str(p) for p in imagenes if not p.is_file()]:
            raise DomainError(f"No están estas imágenes del video: {faltan}")
        if not narracion.cuerpo:
            raise DomainError("No hay audio del cuerpo: hay que narrar antes de renderizar.")
        if faltan := [t.path for t in narracion.pistas if not Path(t.path).is_file()]:
            raise DomainError(f"Faltan archivos de audio en el disco: {faltan}")
        if not Path(FUENTE).exists():
            raise DomainError(f"Falta la tipografía {FUENTE}: el título y el cierre la usan.")
        if story.closing_question and not story.closing_audio:
            # No es fatal —el video sale igual— pero sí es un aviso: la invitación se
            # vería sin que nadie la diga, y en este nicho esa línea es el producto.
            logger.warning(
                "El guion tiene invitación pero no se narró: va a aparecer escrita y muda."
            )


def cuantas_imagenes(duracion_s: float, cada_s: float = IMAGEN_CADA_S) -> int:
    """Cuántas imágenes pedir para un devocional de esta duración.

    Se redondea hacia arriba y nunca baja de una: un video de siete minutos lleva dos
    —una de cinco y otra de dos— antes que una sola quieta siete minutos. El "más o
    menos" del pedido de Pablo vive acá: con veinte minutos exactos da cuatro, y con
    veintidós da cinco de 4,4 minutos, no cuatro de cinco y una de dos.
    """
    return max(1, math.ceil(duracion_s / cada_s))


def _lectura_s(texto: str) -> float:
    """Cuánto tarda alguien en leer un título en pantalla."""
    return max(TITULO_MINIMO_S, len(texto) / LECTURA_POR_SEGUNDO)


def _para_filtro(ruta: Path) -> str:
    """Una ruta escrita para adentro de un `-filter_complex`.

    En la sintaxis de filtros de ffmpeg los dos puntos separan parámetros y la barra
    invertida escapa: una ruta con cualquiera de los dos rompe el filtro entero con un
    error que habla de otra cosa. Las rutas del motor no los traen, pero el `.ass` se
    escribe al lado del MP4 y ese destino lo elige quien llama.
    """
    return str(ruta).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
