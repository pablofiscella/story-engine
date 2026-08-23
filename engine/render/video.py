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

from engine.core.constants import (
    COLA_FINAL_S,
    PAUSA_ENTRE_ESCENAS_S,
    TITULO_S,
    ZOOM_POR_ESCENA,
)
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
#: Fundido de entrada y salida de CADA tramo de audio, en segundos.
#:
#: Los tramos se concatenan de golpe, y un audio que no termina exactamente en cero produce un
#: salto de señal que se oye como un CLIC en cada corte. Pablo, 13-ago-2026: *"en los dos
#: videos senti que en el audio se corta como si cada escena fuera un audio distinto que se
#: corta con un pequeño ruido entre imagen e imagen"*. Era literal: cada escena ES un audio
#: distinto, y se notaba la costura.
#:
#: Veinte milisegundos no se perciben como fundido pero llevan la señal a cero en los bordes,
#: que es lo único que hace falta para que el corte deje de sonar.
FUNDIDO_TRAMO_S = 0.02

#: Cuánto antes de que la voz lo diga aparece el texto del cierre.
#:
#: No desde el principio del tramo: la pregunta tiene que entrar junto con lo que se
#: escucha. Si está desde el arranque, decora; si aparece cuando se dice, se lee.
ADELANTO_DEL_CIERRE_S = 1.0


#: Cuántos caracteres entran cómodos en una línea de un cuadro vertical.
LARGO_DE_LINEA = 20

#: Cuánto se le tolera a ffmpeg antes de darlo por colgado, por segundo de video.
#:
#: POR QUÉ EXISTE (20-ago-2026). Esta llamada no tenía `timeout`, y un ffmpeg que se
#: traba **no se destraba nunca**: uno lanzado por un test el 16-ago quedó huérfano y
#: siguió corriendo **87 horas**, quemando un core entero de los cuatro de la máquina,
#: sobre archivos temporales que pytest había borrado hacía días. Se descubrió buscando
#: por qué otras cosas iban lentas: el `load average` estaba en 12 con 4 CPUs.
#:
#: El número es GENEROSO a propósito. El timeout no está para cortar un render lento
#: —eso sería peor que el problema: rompería trabajo bueno— sino para que uno colgado
#: no viva para siempre. Medido el 20-ago-2026 en esta máquina: el render del test
#: `test_el_video_no_puede_durar_menos_que_el_audio` pasó de **15 minutos sin
#: terminar** para un short de menos de un minuto. O sea que la tolerancia tiene que
#: estar MUY por encima de lo que uno esperaría, o el arreglo se convierte en un bug.
SEGUNDOS_DE_RENDER_POR_SEGUNDO_DE_VIDEO = 120
#: Piso, para que un video de cinco segundos no herede un timeout ridículo.
TIMEOUT_MINIMO_S = 1800
#: Techo. Más de dos horas para un short no es lentitud, es un cuelgue.
TIMEOUT_MAXIMO_S = 7200


def _timeout_de(duracion_s: float) -> float:
    """Cuánto esperar a ffmpeg para un video de esta duración."""
    return min(TIMEOUT_MAXIMO_S,
               max(TIMEOUT_MINIMO_S,
                   duracion_s * SEGUNDOS_DE_RENDER_POR_SEGUNDO_DE_VIDEO))


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


def _morir_con_el_padre() -> None:
    """Le pide al kernel que mate este proceso cuando muera el que lo lanzó.

    `PR_SET_PDEATHSIG` es una llamada de Linux: la promesa la cumple el kernel, no Python.
    Por eso vale aunque al padre lo maten con SIGKILL, que es cuando ningún `except`, ningún
    `finally` y ningún handler de señales llegan a correr.

    Es lo que faltaba el 20-ago-2026 —cuando un ffmpeg quedó 87 horas quemando un core— y lo
    que hizo que el 22-ago volvieran a aparecer dos, uno con 32 horas de CPU, lanzados por el
    mismo test y sobre archivos temporales que pytest ya había borrado.

    Si algo falla —otro sistema operativo, libc distinta— no se rompe el render: se pierde
    sólo esta protección, que es exactamente lo que había antes. **El precio de ese `except`
    es que la protección puede dejar de andar sin avisar**, así que se comprueba a mano:

        # se lanza un ffmpeg eterno, se mata al PADRE con SIGKILL y se mira ESE pid
        p = subprocess.Popen(["ffmpeg", "-f", "lavfi", "-i", "testsrc", "-t", "99999",
                              "-preset", "veryslow", "/tmp/x.mp4"],
                             preexec_fn=_morir_con_el_padre)

    Y se mira **el pid exacto** con `kill -0`, nunca `pgrep`: al comprobarlo el 22-ago-2026
    dio dos falsos negativos seguidos, uno porque `pgrep -f testsrc` se matcheaba a sí mismo
    y otro porque contaba un ffmpeg que había sobrevivido a la prueba anterior.
    """
    try:
        import ctypes
        import signal

        PR_SET_PDEATHSIG = 1
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGKILL)
    except Exception:
        pass


class ShortRenderer:
    """Arma el MP4 de una historia ya ilustrada y narrada."""

    def __init__(self, *, aspect: AspectRatio = AspectRatio.VERTICAL, fps: int = FPS,
                 clips: dict[int, str | Path] | None = None) -> None:
        """`clips` reemplaza la imagen fija de una escena por un video ya animado.

        La clave es el índice de la escena (0 para la primera). Lo que no esté en el
        diccionario sigue saliendo de `escena.image_path`, así que un cuento se puede
        animar A MEDIAS: si una escena sale mal, se rehace sola y las otras no se tocan.

        Pablo, 21-ago-2026: *"antes pasame los clips separados así podés cambiar si uno
        salió mal"*. Ese pedido es la razón de que esto sea un diccionario por escena y
        no un interruptor de "animado sí/no".
        """
        if shutil.which("ffmpeg") is None:
            raise DomainError("Falta ffmpeg: el render lo necesita para armar el video.")
        self._ancho, self._alto = TAMANO[aspect]
        self._fps = fps
        self._clips = {int(k): str(v) for k, v in (clips or {}).items()}

    def render(self, story: Story, dest: str | Path) -> Path:
        """Devuelve la ruta del MP4."""
        self._verificar(story)
        salida = Path(dest)
        salida.parent.mkdir(parents=True, exist_ok=True)

        entradas: list[str] = []
        filtros: list[str] = []
        tramos: list[str] = []

        # --- el título, sobre la primera imagen ---------------------------------
        # También con el margen del cruce: si no, el título se ve 0.4s menos.
        arg_titulo, filtro_titulo = self._fuente(
            0, story.scenes[0].image_path, TITULO_S + TRANSICION_S, 0)
        entradas += arg_titulo
        # SIN RESPALDO A PROPÓSITO. Antes decía `or "Un cuento"` y por eso dos cuentos
        # se publicaron con ese cartel: el título nunca se generaba y nadie se enteró
        # hasta verlo en YouTube. Un video sin título no se arma; falla acá.
        if not (story.metadata.title or "").strip():
            raise ValueError(
                "La historia no tiene título y el cartel de apertura lo necesita. "
                "Lo escribe StoryWriter._titular()."
            )
        placa = self._texto(
            story.metadata.title,
            salida.parent / "_titulo.txt",
            y="h*0.10",
            tope=88,
        )
        filtros.append(f"[0:v]{filtro_titulo},{placa}[titulo]")
        tramos.append("[titulo]")

        # --- las escenas ---------------------------------------------------------
        # Cada tramo se genera MÁS LARGO que su escena, porque el cruce con el
        # siguiente se come `TRANSICION_S`. Sin ese margen la imagen se iría antes de
        # que termine su narración.
        duraciones = [e.real_duration_s + PAUSA_ENTRE_ESCENAS_S for e in story.scenes]
        for i, escena in enumerate(story.scenes, start=1):
            largo = duraciones[i - 1] + TRANSICION_S
            arg, filtro = self._fuente(i - 1, escena.image_path, largo, i)
            entradas += arg
            filtros.append(f"[{i}:v]{filtro}[v{i}]")
            tramos.append(f"[v{i}]")

        # --- el cierre, sobre la última imagen -----------------------------------
        cierre_s = sum(t.duration_s for t in story.closing_audio) + COLA_FINAL_S
        idx_cierre = len(story.scenes) + 1
        # También con el margen del cruce: el último `xfade` acorta el resultado en
        # `TRANSICION_S`, y si el video queda más corto que el audio, `-shortest` le
        # corta el final a la narración. Pasó: la última frase perdía una sílaba.
        arg_cierre, filtro_cierre = self._fuente(
            len(story.scenes) - 1, story.scenes[-1].image_path,
            cierre_s + TRANSICION_S, idx_cierre)
        entradas += arg_cierre
        # La moraleja se dice primero y la pregunta después: el texto entra un
        # segundo antes de que empiece la pregunta hablada.
        antes_de_la_pregunta = sum(t.duration_s for t in story.closing_audio[:-1])
        pregunta = self._texto(
            story.closing_question,
            salida.parent / "_cierre.txt",
            y="h*0.80",
            tope=64,
            desde=max(0.0, antes_de_la_pregunta - ADELANTO_DEL_CIERRE_S),
        )
        filtros.append(f"[{idx_cierre}:v]{filtro_cierre},{pregunta}[cierre]")
        tramos.append("[cierre]")

        # --- el audio -------------------------------------------------------------
        pistas = [t.path for e in story.scenes for t in e.audio]
        pausas = [PAUSA_ENTRE_ESCENAS_S] * len(pistas)
        pistas += [t.path for t in story.closing_audio]
        pausas += [0.0] * len(story.closing_audio)
        if pausas:
            pausas[-1] = COLA_FINAL_S

        base = idx_cierre + 1
        entradas += [x for p in pistas for x in ("-i", p)]
        for j, pausa in enumerate(pausas):
            # `adelay` mete el silencio ANTES y `apad` DESPUÉS. Se usa apad porque la
            # pausa es el aire que queda al terminar de hablar, no antes de empezar.
            # El fundido de salida va con el truco de dar vuelta el audio, aplicarle un
            # fundido de ENTRADA y volverlo a dar vuelta: así no hace falta saber cuánto dura
            # el tramo para saber dónde empieza el final.
            filtros.append(
                f"[{base + j}:a]afade=t=in:st=0:d={FUNDIDO_TRAMO_S},"
                f"areverse,afade=t=in:st=0:d={FUNDIDO_TRAMO_S},areverse,"
                f"apad=pad_dur={pausa:.3f}[a{j}]"
            )

        cadena_v = _encadenar(tramos, [TITULO_S, *duraciones])
        # El fundido al negro arranca cuando arranca la cola: se apaga mientras suena
        # el último silencio, en vez de cortar en la última sílaba.
        # Cada cruce consume `TRANSICION_S` y cada tramo se generó con ese margen de
        # más: los dos efectos se cancelan y el video dura exactamente lo que el audio.
        total = TITULO_S + sum(duraciones) + cierre_s
        arranque = max(0.0, total - COLA_FINAL_S)
        cadena_v += f";[vcrudo]fade=t=out:st={arranque:.3f}:d={COLA_FINAL_S}[video]"

        cadena_a = (
            "".join(f"[a{j}]" for j in range(len(pistas)))
            + f"concat=n={len(pistas)}:v=0:a=1[unido];"
            # LA VOZ ARRANCA DE UNA, sobre la placa. Antes se le anteponía un silencio del
            # largo del título para que la narración cayera al terminar la placa — y eso dejaba
            # el video empezando MUDO. Pablo, 13-ago-2026: *"comienza unos segundos sin decir
            # nada"*. En el feed de Shorts esos son los segundos que deciden si alguien se
            # queda: el propio Studio marca la retención de los primeros segundos como lo que
            # hay que mejorar.
            #
            # No hay nada que sincronizar: la placa se dibuja SOBRE la primera imagen del
            # cuento, así que la primera narración le corresponde igual.
            f"[unido]{LOUDNESS}[audio]"
        )
        filtro = ";".join([*filtros, cadena_v, cadena_a])

        # `timeout` NO es opcional acá: sin él, un ffmpeg trabado sobrevive al proceso
        # que lo lanzó y queda huérfano para siempre — no hay nadie que lo espere ni que
        # lo mate. Ya pasó: ver SEGUNDOS_DE_RENDER_POR_SEGUNDO_DE_VIDEO.
        #
        # Con el timeout solo NO ALCANZA, y volvió a pasar el 22-ago-2026: dos ffmpeg
        # huérfanos del MISMO test, uno con 32 horas de CPU. `subprocess.run` mata al hijo
        # ante cualquier EXCEPCIÓN —timeout incluido—, pero si al padre lo matan con SIGKILL
        # no corre ningún `except`: el proceso muere sin ejecutar una línea más y el ffmpeg
        # queda solo, quemando un core sobre archivos que ya nadie va a leer.
        #
        # Por eso además va `PR_SET_PDEATHSIG`: se lo pide el KERNEL, no Python, así que
        # funciona aunque al padre lo maten de la forma más brutal. Es la única defensa que
        # no depende de que alcancemos a ejecutar algo.
        try:
            subprocess.run(
                ["ffmpeg", "-y", *entradas, "-filter_complex", filtro,
                 "-map", "[video]", "-map", "[audio]",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
                 "-c:a", "aac", "-b:a", "128k", "-shortest", str(salida)],
                check=True, capture_output=True, timeout=_timeout_de(total),
                preexec_fn=_morir_con_el_padre,
            )
        except subprocess.TimeoutExpired as e:
            # El mensaje dice cuánto se esperó y para qué video: sin eso, quien lo vea en
            # un log no puede distinguir «se colgó» de «le quedó corto el tiempo».
            raise DomainError(
                f"ffmpeg no terminó de armar el video en {e.timeout:.0f}s "
                f"(el video dura {total:.1f}s). Se lo dio por colgado y se lo mató."
            ) from e
        if story.status is StoryStatus.NARRATED:
            story.advance_to(StoryStatus.RENDERED)
        story.metadata.touch()
        return salida

    # ------------------------------------------------------------------------
    def _fuente(self, indice_escena: int, imagen: str, largo: float,
                orden: int) -> tuple[list[str], str]:
        """Los argumentos de entrada y el filtro de UN tramo.

        Con imagen fija es lo de siempre: `-loop 1 -t` y el zoom lento de cámara.

        Con clip animado hay dos diferencias, y las dos importan:

        - **No se le pone zoom.** El clip ya se mueve; encima un zoompan da un mareo.
        - **El último cuadro se CONGELA** hasta completar el tramo (`tpad=stop_mode=clone`).
          Wan genera 5,0 s exactos y una escena dura eso más la pausa: sobra medio segundo.
          Las otras dos salidas son peores — repetir el clip mete un salto visible en el
          medio de la escena, y estirarlo con `setpts` lo pone en cámara lenta.
        """
        clip = self._clips.get(indice_escena)
        if not clip:
            return (["-loop", "1", "-t", f"{largo:.3f}", "-i", imagen],
                    self._encuadrar(largo, orden))
        return (["-i", clip],
                f"{self._encuadrar()},"
                f"tpad=stop_mode=clone:stop_duration={largo:.3f},"
                f"trim=duration={largo:.3f},setpts=PTS-STARTPTS")

    # ------------------------------------------------------------------------
    def _encuadrar(self, dur_s: float | None = None, indice: int = 0) -> str:
        """El filtro de video de UN tramo: encuadre vertical y, si se sabe cuánto dura,
        movimiento de cámara.

        Sin `dur_s` no hay movimiento — el zoom necesita saber cuántos cuadros tiene el
        tramo para repartir el recorrido.

        DOS COSAS DE `zoompan` QUE NO SON OPCIONALES, y las dos costaron un render entero:

        - **`d=1`.** Con `d=N`, zoompan REPITE cada cuadro de entrada N veces; como la
          entrada de una imagen fija ya trae todos sus cuadros (`-loop 1 -t`), un cuento de
          48 s salió de OCHO MINUTOS. El avance se controla con `on`, el número de cuadro
          que va saliendo, no con `d`.
        - **`fps` ANTES del filtro**, no sólo dentro. La entrada de una imagen viene a
          25 fps: sin fijarla antes, el tramo dura 5/6 de lo que debía (medido: 4,167 s
          donde iban 5,000).

        Se escala más grande ANTES de mover: hacer zoom sobre el tamaño final deja los
        bordes pixelados.
        """
        base = (
            f"scale={self._ancho}:{self._alto}:force_original_aspect_ratio=increase,"
            f"crop={self._ancho}:{self._alto},setsar=1,fps={self._fps}"
        )
        if not dur_s or ZOOM_POR_ESCENA <= 0:
            return base

        cuadros = max(2, int(dur_s * self._fps))
        paso = ZOOM_POR_ESCENA / cuadros
        tope = 1 + ZOOM_POR_ESCENA
        # Alterna acercarse y alejarse: ocho escenas con el mismo movimiento se leen como
        # un efecto puesto encima, no como cámara.
        if indice % 2 == 0:
            z = f"min(1+{paso:.6f}*on,{tope:.3f})"
        else:
            z = f"max({tope:.3f}-{paso:.6f}*on,1.0)"
        ancho, alto = int(self._ancho * 1.4), int(self._alto * 1.4)
        return (
            f"fps={self._fps},"
            f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},"
            f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={self._ancho}x{self._alto}:fps={self._fps},setsar=1"
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
