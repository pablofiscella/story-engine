"""El render: de la historia narrada al MP4 vertical.

Junta lo que ya existe —las imágenes y las pistas de audio— y arma el short. Todo
lo que decide acá ya venía decidido: cuánto dura cada escena lo dijo el audio, qué
se ve lo dijo el ilustrador, qué se lee lo dijo el escritor.

**La duración de cada escena la manda el AUDIO, no el plan.** Es la regla que
sostiene el módulo: `Scene.real_duration_s` devuelve la duración medida del audio si
existe y la del plan si todavía no se narró. Usar la del plan haría que la imagen
cambie mientras el narrador sigue hablando.

El short tiene tres partes y no una, porque un cuento no es una lista de escenas:

    título  ·  las escenas, con aire entre una y otra  ·  el cierre

Las tres salieron de escuchar el primer short terminado (Pablo, 5-ago-2026):
*"entre cada texto parece que se junta mucho el audio. Al final corta abrupto. Creo
que tiene que tener un título al comienzo y un cierre como un ejemplo de vida."*

- **El aire entre escenas** existe porque sin él la última palabra de una escena y la
  primera de la siguiente quedan pegadas, y el cuento suena apurado.
- **El cierre** es la moraleja y la pregunta final. Estaban en el modelo desde el
  primer día y ningún módulo las usaba: el video terminaba en la última palabra de la
  historia. La pregunta además es lo que convierte a un espectador en un comentario.
- **La cola y el fundido** existen porque cortar en seco en la última sílaba se siente
  roto aunque el cuento esté completo.

Dos decisiones más que salieron de errores del motor viejo:

1. **El audio se concatena re-codificando, nunca con `-c copy`.** Copiar los streams
   es más rápido pero corta el final de cada pista: en los reels viejos los diálogos
   se cortaban justo al pasar de una escena a la siguiente.
2. **La normalización de volumen va al final, sobre el audio ya armado.** Por tramo
   deja cada escena con un volumen distinto; y sin normalizar el audio queda en
   −20 dB y en el feed se escucha flojo.

FFmpeg se invoca por línea de comandos a propósito: es la única dependencia externa
del motor y no queremos un binding que haya que compilar.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from engine.core.constants import COLA_FINAL_S, PAUSA_ENTRE_ESCENAS_S, TITULO_S
from engine.core.enums import AspectRatio, StoryStatus
from engine.core.exceptions import DomainError
from engine.core.models.story import Story

#: Medidas del short. 1080×1920 es lo que pide YouTube Shorts, Reels y TikTok.
TAMANO: dict[AspectRatio, tuple[int, int]] = {
    AspectRatio.VERTICAL: (1080, 1920),
    AspectRatio.HORIZONTAL: (1920, 1080),
    AspectRatio.SQUARE: (1080, 1080),
    AspectRatio.PORTRAIT: (1080, 1350),
}

#: Volumen de destino. −16 LUFS es el estándar de las plataformas: sin esto el audio
#: sale a −20 dB y en el feed se escucha flojo contra todo lo demás.
LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=11"

#: Tipografía del título y del cierre. DejaVu está en cualquier Linux y tiene los
#: acentos y signos de apertura del español, que es más de lo que se puede decir de
#: varias fuentes "lindas".
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

FPS = 30

#: Grosor del contorno del texto, en píxeles.
#:
#: Reemplaza a la caja negra que había antes: la caja tapaba la ilustración, que es
#: justamente lo que hay que mirar. Un contorno grueso se lee igual sobre las zonas
#: claras y sobre las oscuras de un dibujo infantil.
CONTORNO = 8

#: Cuánto dura el fundido entre una imagen y la siguiente.
#:
#: Seis fotos que se cambian de golpe se ven como una presentación de diapositivas.
#: Con un cruce corto el cuento fluye. Corto a propósito: más de medio segundo en un
#: short se siente lento, porque la escena entera dura cinco.
TRANSICION_S = 0.4

#: Cuánto antes de que la voz lo diga aparece el texto del cierre.
#:
#: No desde el principio del tramo: la pregunta tiene que entrar junto con lo que se
#: escucha. Si está desde el arranque, decora; si aparece cuando se dice, se lee.
ADELANTO_DEL_CIERRE_S = 1.0


#: Cuántos caracteres entran cómodos en una línea de un cuadro vertical.
LARGO_DE_LINEA = 20

#: Dónde va el texto del cierre. **Se fija dónde TERMINA el bloque, no dónde empieza.**
#:
#: Decía `h*0.80` —el borde de arriba— y el texto crece hacia abajo, así que cada línea
#: de más lo empujaba fuera del cuadro. Con los cuentos nunca falló porque su pregunta
#: final entra en dos líneas; la invitación del devocional ocupa cinco y el 7-ago-2026
#: salió con la última palabra cortada por el borde inferior.
#:
#: Restarle `text_h` deja el final del bloque clavado al 88 % del alto para cualquier
#: cantidad de líneas, y sin que nadie tenga que estimar cuánto mide una línea de
#: DejaVu — que es justamente lo que se estimaba mal. Con dos líneas da y≈1534 contra
#: los 1536 de antes: los cuentos ya publicados no se mueven.
Y_DEL_CIERRE = "h*0.88-text_h"


def _envolver(texto: str, largo: int = LARGO_DE_LINEA) -> list[str]:
    """Parte el texto en líneas sin cortar palabras."""
    lineas: list[str] = []
    actual = ""
    for palabra in texto.split():
        if actual and len(actual) + 1 + len(palabra) > largo:
            lineas.append(actual)
            actual = palabra
        else:
            actual = f"{actual} {palabra}".strip()
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _encadenar(tramos: list[str], duraciones: list[float]) -> str:
    """Los tramos de video, unidos con un fundido cruzado entre cada par.

    `xfade` cruza de a dos, así que hay que encadenarlo: el resultado de un cruce es
    la entrada del siguiente. El `offset` es CUÁNDO empieza el cruce medido desde el
    principio del acumulado, y por eso va sumando las duraciones.

    Se usa esto y no `concat` porque seis fotos que se cambian de golpe se ven como
    una presentación de diapositivas. El motor viejo tenía el mismo cruce (0.4s) en
    el camino de Remotion y lo perdió en el camino de ffmpeg, donde los tramos se
    pegaban con `concat -c copy`.
    """
    if len(tramos) == 1:
        return f"{tramos[0]}null[vcrudo]"

    partes: list[str] = []
    acumulado = duraciones[0]
    anterior = tramos[0]
    for i, tramo in enumerate(tramos[1:], start=1):
        etiqueta = "[vcrudo]" if i == len(tramos) - 1 else f"[x{i}]"
        offset = max(0.0, acumulado - TRANSICION_S)
        partes.append(
            f"{anterior}{tramo}xfade=transition=fade:"
            f"duration={TRANSICION_S}:offset={offset:.3f}{etiqueta}"
        )
        acumulado += duraciones[i] if i < len(duraciones) else 0.0
        anterior = etiqueta
    return ";".join(partes)


class ShortRenderer:
    """Arma el MP4 de una historia ya ilustrada y narrada."""

    def __init__(self, *, aspect: AspectRatio = AspectRatio.VERTICAL, fps: int = FPS) -> None:
        if shutil.which("ffmpeg") is None:
            raise DomainError("Falta ffmpeg: el render lo necesita para armar el video.")
        self._ancho, self._alto = TAMANO[aspect]
        self._fps = fps

    def render(self, story: Story, dest: str | Path) -> Path:
        """Devuelve la ruta del MP4."""
        self._verificar(story)
        salida = Path(dest)
        salida.parent.mkdir(parents=True, exist_ok=True)

        entradas: list[str] = []
        filtros: list[str] = []
        tramos: list[str] = []

        # --- el título, sobre la primera imagen ---------------------------------
        # La placa dura lo que tarda en DECIRSE el título, con `TITULO_S` de piso para
        # que se alcance a leer. Antes duraba dos segundos fijos y el video arrancaba
        # con dos segundos de silencio mirando un cartel: Pablo, mirando el segundo
        # lote, *"aparece el título pero no habla en ningún video"*.
        dur_titulo = sum(t.duration_s for t in story.title_audio)
        titulo_s = max(TITULO_S, dur_titulo)
        # También con el margen del cruce: si no, el título se ve 0.4s menos.
        entradas += [
            "-loop", "1", "-t", f"{titulo_s + TRANSICION_S:.3f}",
            "-i", story.scenes[0].image_path,
        ]
        placa = self._texto(
            story.metadata.title or "Un cuento",
            salida.parent / "_titulo.txt",
            y="h*0.10",
            tope=88,
        )
        filtros.append(f"[0:v]{self._encuadrar()},{placa}[titulo]")
        tramos.append("[titulo]")

        # --- las escenas ---------------------------------------------------------
        # Cada tramo se genera MÁS LARGO que su escena, porque el cruce con el
        # siguiente se come `TRANSICION_S`. Sin ese margen la imagen se iría antes de
        # que termine su narración.
        # Si el cuento se grabó de una sola toma, el aire entre escenas ya está adentro
        # del audio: agregarle silencio lo vuelve a partir en pedazos.
        pausa = 0.0 if story.continuous_narration else PAUSA_ENTRE_ESCENAS_S
        duraciones = [e.real_duration_s + pausa for e in story.scenes]
        for i, escena in enumerate(story.scenes, start=1):
            largo = duraciones[i - 1] + TRANSICION_S
            entradas += ["-loop", "1", "-t", f"{largo:.3f}", "-i", escena.image_path]
            filtros.append(f"[{i}:v]{self._encuadrar()}[v{i}]")
            tramos.append(f"[v{i}]")

        # --- el cierre, sobre la última imagen -----------------------------------
        cierre_s = sum(t.duration_s for t in story.closing_audio) + COLA_FINAL_S
        idx_cierre = len(story.scenes) + 1
        # También con el margen del cruce: el último `xfade` acorta el resultado en
        # `TRANSICION_S`, y si el video queda más corto que el audio, `-shortest` le
        # corta el final a la narración. Pasó: la última frase perdía una sílaba.
        entradas += [
            "-loop", "1", "-t", f"{cierre_s + TRANSICION_S:.3f}",
            "-i", story.scenes[-1].image_path,
        ]
        # La moraleja se dice primero y la pregunta después: el texto entra un
        # segundo antes de que empiece la pregunta hablada.
        antes_de_la_pregunta = sum(t.duration_s for t in story.closing_audio[:-1])
        pregunta = self._texto(
            story.closing_question,
            salida.parent / "_cierre.txt",
            # **Anclado ABAJO, no arriba.** Decía `h*0.80`, que es dónde EMPIEZA el
            # bloque: el texto crece hacia abajo, así que cuantas más líneas tiene, más
            # se sale del cuadro. Con los cuentos nunca se notó porque su pregunta final
            # entra en dos líneas de español. La invitación del devocional —"If your
            # mind has been loud lately, type AMEN so I can pray for you by name"— ocupa
            # cinco, y el 7-ago-2026 salió con la última palabra CORTADA por el borde de
            # abajo. Justo esa línea: el nicho se eligió por su 1,718 % de comentarios,
            # y el CTA que los pide era lo único ilegible del video.
            #
            # `text_h` lo resuelve para cualquier largo: se fija dónde TERMINA el bloque
            # y ffmpeg calcula el resto. Con dos líneas cae en y≈1534 contra los 1536 de
            # antes, así que los cuentos que ya salieron no se mueven.
            y=Y_DEL_CIERRE,
            tope=64,
            desde=max(0.0, antes_de_la_pregunta - ADELANTO_DEL_CIERRE_S),
        )
        filtros.append(f"[{idx_cierre}:v]{self._encuadrar()},{pregunta}[cierre]")
        tramos.append("[cierre]")

        # --- el audio -------------------------------------------------------------
        # El título primero, si se narró. Lo que sobra de placa —cuando el título se
        # dice más rápido que el piso de lectura— se rellena con silencio detrás, para
        # que la primera escena entre justo cuando la imagen cambia.
        pistas = [t.path for t in story.title_audio]
        pausas = [titulo_s - dur_titulo] if story.title_audio else []
        pistas += [t.path for e in story.scenes for t in e.audio]
        pausas += [pausa] * (len(pistas) - len(pausas))
        pistas += [t.path for t in story.closing_audio]
        pausas += [0.0] * len(story.closing_audio)
        if pausas:
            pausas[-1] = COLA_FINAL_S

        base = idx_cierre + 1
        entradas += [x for p in pistas for x in ("-i", p)]
        for j, pausa in enumerate(pausas):
            # `adelay` mete el silencio ANTES y `apad` DESPUÉS. Se usa apad porque la
            # pausa es el aire que queda al terminar de hablar, no antes de empezar.
            filtros.append(f"[{base + j}:a]apad=pad_dur={pausa:.3f}[a{j}]")

        cadena_v = _encadenar(tramos, [titulo_s, *duraciones])
        # El fundido al negro arranca cuando arranca la cola: se apaga mientras suena
        # el último silencio, en vez de cortar en la última sílaba.
        # Cada cruce consume `TRANSICION_S` y cada tramo se generó con ese margen de
        # más: los dos efectos se cancelan y el video dura exactamente lo que el audio.
        total = titulo_s + sum(duraciones) + cierre_s
        arranque = max(0.0, total - COLA_FINAL_S)
        cadena_v += f";[vcrudo]fade=t=out:st={arranque:.3f}:d={COLA_FINAL_S}[video]"

        # Cuando el título se narra, su pista YA ocupa la placa y no hay que anteponer
        # nada. El silencio de antes existía porque la placa era muda: meterlo igual
        # correría el cuento entero y la última escena se quedaría sin imagen.
        placa_muda = (
            ""
            if story.title_audio
            else f"[unido]adelay={int(titulo_s * 1000)}|{int(titulo_s * 1000)}[conplaca];"
        )
        entrada_loudness = "[unido]" if story.title_audio else "[conplaca]"
        cadena_a = (
            "".join(f"[a{j}]" for j in range(len(pistas)))
            + f"concat=n={len(pistas)}:v=0:a=1[unido];"
            + placa_muda
            + f"{entrada_loudness}{LOUDNESS}[audio]"
        )
        filtro = ";".join([*filtros, cadena_v, cadena_a])

        subprocess.run(
            ["ffmpeg", "-y", *entradas, "-filter_complex", filtro,
             "-map", "[video]", "-map", "[audio]",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(salida)],
            check=True, capture_output=True,
        )
        if story.status is StoryStatus.NARRATED:
            story.advance_to(StoryStatus.RENDERED)
        story.metadata.touch()
        return salida

    # ------------------------------------------------------------------------
    def _encuadrar(self) -> str:
        return (
            f"scale={self._ancho}:{self._alto}:force_original_aspect_ratio=increase,"
            f"crop={self._ancho}:{self._alto},setsar=1,fps={self._fps}"
        )

    def _texto(
        self, texto: str, archivo: Path, *, y: str, tope: int, desde: float | None = None
    ) -> str:
        """Un texto legible sobre cualquier imagen, que ENTRA en el cuadro.

        Dos cosas que parecen detalle y no lo son:

        - **Se parte en líneas y el tamaño se calcula.** Con un tamaño fijo, un
          título de 27 caracteres se sale del cuadro por los dos lados: el primer
          short decía "no y la pelota de color".
        - **Contorno y no caja.** La caja negra tapa la ilustración, que es lo que
          hay que mirar. Con un contorno grueso el texto se lee igual sobre las
          zonas claras y sobre las oscuras, y la imagen se sigue viendo entera.

        `desde` retrasa la aparición: el texto del cierre entra un segundo antes de
        que la voz lo diga, no desde el principio del tramo. Que aparezca junto con
        lo que se escucha es lo que hace que se lea en vez de decorar.
        """
        lineas = _envolver(texto)
        # DejaVu Sans Bold ocupa ~0.58 del tamaño por carácter. Se deja margen a cada
        # lado para que la caja no toque el borde del cuadro.
        mas_larga = max(len(x) for x in lineas)
        tam = min(tope, int(self._ancho * 0.82 / (0.58 * mas_larga)))

        # `textfile` y no `text`: el texto de un cuento tiene comillas, dos puntos,
        # signos de apertura y saltos de línea, y cada uno necesita su propio escape
        # dentro de un filtro de ffmpeg. Con el texto en un archivo no hay nada que
        # escapar. El primer intento con `text=` salió "ino y la pelota dencolore".
        archivo.write_text("\n".join(lineas), encoding="utf-8")
        aparicion = f":enable='gte(t,{desde:.3f})'" if desde is not None else ""
        return (
            f"drawtext=fontfile={FUENTE}:textfile={archivo}:"
            # `text_align=C` centra las LÍNEAS entre sí. Sin esto, el bloque queda
            # centrado en el cuadro pero la segunda línea alineada a la izquierda.
            f"fontcolor=white:fontsize={tam}:line_spacing=14:text_align=C:"
            f"borderw={CONTORNO}:bordercolor=black@0.85:"
            f"x=(w-text_w)/2:y={y}{aparicion}"
        )

    def _verificar(self, story: Story) -> None:
        """Falla antes de invocar a ffmpeg, con un mensaje que se entiende.

        Un error de ffmpeg son treinta líneas de jerga; esto dice qué falta.
        """
        if not story.scenes:
            raise DomainError("La historia no tiene escenas: no hay nada que renderizar.")
        sin_imagen = [e.index for e in story.scenes if not e.image_path]
        if sin_imagen:
            raise DomainError(f"Las escenas {sin_imagen} no tienen imagen: hay que ilustrarlas.")
        sin_audio = [e.index for e in story.scenes if not e.audio]
        if sin_audio:
            raise DomainError(f"Las escenas {sin_audio} no tienen audio: hay que narrarlas.")
        faltan = [e.image_path for e in story.scenes if not Path(e.image_path).exists()]
        if faltan:
            raise DomainError(f"Faltan archivos de imagen en el disco: {faltan}")
        if not Path(FUENTE).exists():
            raise DomainError(f"Falta la tipografía {FUENTE}: el título y el cierre la usan.")
