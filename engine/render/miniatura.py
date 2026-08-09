"""La portada del video largo: lo único que decide el clic.

Pablo, 9-ago-2026: *"Hay que configurar en el video largo de YouTube la imagen que se
pone en la portada del video. Esa tiene que convencer."*

**Por qué esto importa más acá que en un Short**, y es la razón de que el módulo exista:
un Short se muestra solo en el feed —aparece, y quien no lo quiere lo desliza—, pero un
video largo hay que **elegirlo** de una grilla de doce competidores, y lo único que
decide esa elección es la miniatura. Sin una propia, YouTube elige un fotograma al azar:
en este formato, un paisaje quieto con un subtítulo cortado a la mitad.

QUÉ ES UNA PLANTILLA Y POR QUÉ NO UN DISEÑO POR VIDEO
------------------------------------------------------
Medido el 8-ago-2026 sobre los 14 canales del nicho (ver el diario): los que funcionan
usan **una plantilla, no un diseño por video**. Daily Prayer y Morning Grace Daily
repiten **la misma imagen de fondo** en todas sus miniaturas y sólo les cambian el
texto; Morning Grace Daily hizo 25.400 suscriptores con 3 videos en 44 días haciendo
eso. The Gentle Bible va **sin una sola letra**.

Así que acá la composición **no se elige por video**: es siempre la misma —gancho grande
arriba del centro, bajada abajo— y lo único que cambia es el texto y la imagen. Eso es
lo que hace que un canal se reconozca de un vistazo en una grilla, que es exactamente el
momento en que se lo reconoce o no se lo abre.

LA IMAGEN ES UNA DE LAS DEL VIDEO, Y ES LA PRIMERA
---------------------------------------------------
No se genera ninguna imagen nueva: las del formato largo **ya están pagadas** (US$ 0,005
cada una) y ya están en disco. Se usa la **primera**, que es la que se ve al abrir el
video: una miniatura que muestra algo que el video no tiene es la forma más barata de
enseñarle a YouTube que tu canal decepciona. Ver `IMAGEN_DE_PORTADA`.

EL TÍTULO DEL VIDEO NO ES EL TEXTO DE LA MINIATURA
---------------------------------------------------
Es el hallazgo que cambió el diseño. El título real del primer devocional es *"Before
This Day Begins — A Morning Prayer For A Tired Heart"*: 51 caracteres. Puesto entero en
1280×720 la letra queda en 38 px, y en el feed —donde la miniatura se ve a **210 px de
ancho**, o sea a un sexto— eso son 6 px: ilegible, que es lo mismo que no tener texto,
pero encima tapando el paisaje.

Los títulos del nicho tienen forma de **gancho + bajada** separados por una raya, y el
nuestro también. Así que la raya se aprovecha: el gancho va grande (lo que se lee en
chico) y la bajada chica (lo que se lee si la miniatura ya te frenó). Ver
`partir_titulo`, que también resuelve los títulos sin raya.

EL TRATAMIENTO ES EL DEL RESTO DEL MOTOR: BLANCO CON CONTORNO, SIN CAJA
------------------------------------------------------------------------
`CONTORNO`, `FUENTE` y la fórmula del tamaño salen de `render.video` y `render.still`,
no se vuelven a elegir acá. La caja negra se sacó del motor el 7-ago-2026 porque tapaba
la ilustración, y una miniatura donde el paisaje está tapado no vende el paisaje.

**El contorno se escala con la letra, y ese número sí es nuevo.** En el video el título
va en 72 px con 8 px de contorno; acá la letra es el doble de grande, y 8 px sobre 150
se ve fino — al achicarse a un sexto, el borde desaparece antes que la letra y el blanco
se come contra un cielo claro. Se mantiene la **proporción** (`CONTORNO / 72`), que es
lo que se ve igual, y no el número, que es lo que se vería distinto.

**Y la imagen se oscurece un punto.** No es una caja detrás del texto: es tratamiento
fotográfico sobre el cuadro entero (`VELO`). Los cuatro paisajes de este formato son
amaneceres —cielos claros, amarillos— y el blanco sobre amarillo claro es el único caso
donde el contorno solo no alcanza. Se verificó mirando, que es la única forma.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from engine.core.exceptions import DomainError
from engine.render.video import CONTORNO, FUENTE, _envolver

logger = logging.getLogger(__name__)

#: Medida de la miniatura. **1280×720**, que es lo que recomienda YouTube.
#:
#: El mínimo que acepta son 640 px de ancho, pero la miniatura no se usa sólo en la
#: grilla: en la página del video, en la búsqueda de una tele y en el panel de Studio se
#: muestra grande. 1280 es el ancho que ya cubre todos esos usos sin pesar.
MEDIDA = (1280, 720)

#: Lo que pesa como máximo una miniatura de YouTube. **2 MB**, y lo rechaza si se pasa.
LIMITE_BYTES = 2 * 1024 * 1024

#: Cuál de las imágenes del video va en la portada. **La primera.**
#:
#: Es la que se ve al abrir el video: la miniatura promete exactamente lo que se entrega
#: en el primer segundo. Es un índice y no una elección "la más linda" a propósito —
#: elegir la más linda pide un criterio que nadie puede escribir, y es lo que convierte
#: una plantilla en un diseño por video.
IMAGEN_DE_PORTADA = 0

#: Cuánto se oscurece la imagen debajo del texto, y cuánto se le sube el color.
#:
#: Los paisajes de este formato son amaneceres: cielos claros y amarillos, que es el
#: peor fondo posible para letra blanca. Bajar el brillo un 12 % le devuelve el contraste
#: al blanco sin apagar el amanecer —que es lo que se está vendiendo— y la saturación
#: compensa lo que el brillo se lleva.
#:
#: **No es una caja**: se aplica al cuadro entero, como un filtro de cámara. La caja
#: negra detrás del texto se sacó del motor el 7-ago-2026 y no vuelve por la ventana.
VELO = "eq=brightness=-0.12:saturation=1.12"

#: Cuántos caracteres entran en una línea del gancho.
#:
#: **Chico a propósito**: cuanto más corta la línea, más grande sale la letra, y el
#: tamaño es lo único que sobrevive al achique del feed. Con 14 el gancho del primer
#: devocional ("Before This Day Begins") entra en dos renglones de 11 y 10.
LARGO_DEL_GANCHO = 14

#: Cuántos caracteres entran en una línea de la bajada.
LARGO_DE_LA_BAJADA = 30

#: Lo más grande que puede salir cada texto, en píxeles.
#:
#: El gancho llega al tope casi siempre y está bien: es el que se lee a 210 px. La
#: bajada tiene tope bajo **para que no compita** — dos textos del mismo tamaño son dos
#: textos que nadie jerarquiza en el cuarto de segundo que dura una mirada.
#:
#: **120 y no 150**, y se supo mirando: con 150 el gancho de dos renglones ocupaba 330
#: de los 720 px de alto y no quedaba paisaje que mirar. La miniatura tiene que vender
#: el título *y* la imagen; una que es sólo un cartel se parece a las que uno saltea.
TOPE_DEL_GANCHO = 120
TOPE_DE_LA_BAJADA = 44

#: Dónde va cada bloque, en alto del cuadro. **El gancho arriba y la bajada al pie.**
#:
#: La primera versión anclaba el gancho por donde TERMINA (`h*0.46-text_h`), copiando a
#: `Y_DEL_CIERRE`. Se vio mirando que **la primera línea salía cortada por el borde de
#: arriba**: allá el problema era un bloque que crecía hacia abajo y se iba del cuadro
#: por abajo, y acá el mismo anclaje lo empuja hacia afuera por arriba. La lección es que
#: un anclaje no se hereda con el número: se hereda con la dirección en la que el texto
#: crece y con el borde que hay que cuidar.
#:
#: Anclados a los dos bordes opuestos —el gancho por arriba, la bajada por el pie— cada
#: bloque tiene su margen garantizado y no hay forma de que uno empuje al otro.
#:
#: El pie es 0,82 y no 0,88 como en el video por una razón que sólo existe acá: **YouTube
#: dibuja el cartelito de la duración en la esquina inferior derecha** de toda miniatura,
#: y ése es un elemento que no está en el archivo pero sí en la grilla.
Y_DEL_GANCHO = "h*0.07"
Y_DE_LA_BAJADA = "h*0.82-text_h"

#: Separadores de título que parten gancho y bajada, en orden de preferencia.
#:
#: La raya larga es la que usa el motor al titular; el guion suelto y los dos puntos
#: están porque el nicho los usa igual ("Psalm 91: The Prayer That Covers You").
SEPARADORES = ("—", " - ", " – ", ": ", " | ")

#: Cuántos caracteres puede tener un título para ir entero como gancho, sin bajada.
#:
#: Arriba de esto, un título sin raya se parte igual: 30 caracteres en dos renglones ya
#: obligan a bajar la letra hasta donde el feed se la come.
GANCHO_SOLO_HASTA = 30


def partir_titulo(titulo: str) -> tuple[str, str]:
    """Devuelve `(gancho, bajada)` para el título de un video.

    El caso real, y el que fija el test: *"Before This Day Begins — A Morning Prayer For
    A Tired Heart"* se parte en *"Before This Day Begins"* y *"A Morning Prayer For A
    Tired Heart"*. Es exactamente la forma que tienen los títulos del nicho, así que
    partir por la raya no es una heurística que adivina: es leer la estructura que el
    propio título ya declara.

    Un título corto y sin raya va entero de gancho y sin bajada — que es la miniatura de
    The Gentle Bible, la del canal con más vistas por video de los 14.

    Uno largo y sin raya se parte por la palabra más cercana a la mitad: es el peor caso
    y sale razonable, pero conviene titular con raya.
    """
    limpio = " ".join(titulo.split())
    if not limpio:
        raise DomainError("El video no tiene título: la miniatura no tendría qué decir.")

    for sep in SEPARADORES:
        if sep in limpio:
            gancho, _, bajada = limpio.partition(sep)
            gancho, bajada = gancho.strip(" -–—:|"), bajada.strip(" -–—:|")
            if gancho and bajada:
                return gancho, bajada

    if len(limpio) <= GANCHO_SOLO_HASTA:
        return limpio, ""

    palabras = limpio.split()
    mitad = len(limpio) / 2
    corte, mejor = 1, None
    for i in range(1, len(palabras)):
        distancia = abs(len(" ".join(palabras[:i])) - mitad)
        if mejor is None or distancia < mejor:
            corte, mejor = i, distancia
    return " ".join(palabras[:corte]), " ".join(palabras[corte:])


def miniatura_de(video: str | Path) -> Path:
    """Dónde va la miniatura de un video: al lado, con el mismo nombre y `.jpg`.

    Es una **convención y no una configuración** para que el publicador la encuentre sin
    que nadie tenga que anotarla en ningún lado. El 6-ago-2026 costó una vuelta entera
    que el scheduler le pasara al publicador el NOMBRE del archivo donde esperaba una
    URL; un dato que se deriva no se puede pasar mal.
    """
    return Path(video).with_suffix(".jpg")


def render_miniatura(
    titulo: str,
    imagen: str | Path,
    dest: str | Path,
    *,
    calidad: int = 3,
) -> Path:
    """Compone la portada y devuelve su ruta.

    `imagen` es una de las que el video ya usa —no se genera ninguna— y `titulo` es el
    del video, que se parte solo en gancho y bajada.

    El caso real del 9-ago-2026: `fondo1.png` (1536×1024, el valle al amanecer) más
    *"Before This Day Begins — A Morning Prayer For A Tired Heart"* dan un JPG de
    1280×720 de unos 200 KB, bien debajo de los 2 MB que YouTube acepta.
    """
    if shutil.which("ffmpeg") is None:
        raise DomainError("Falta ffmpeg: la miniatura se compone con él.")
    origen = Path(imagen)
    if not origen.is_file():
        raise DomainError(f"No está la imagen de la portada: {origen}")
    if not Path(FUENTE).exists():
        raise DomainError(f"Falta la tipografía {FUENTE}: la miniatura la usa.")

    salida = Path(dest)
    salida.parent.mkdir(parents=True, exist_ok=True)
    gancho, bajada = partir_titulo(titulo)
    ancho, alto = MEDIDA

    # El mismo encuadre que el video: se agranda hasta cubrir y se recorta al centro.
    # Las imágenes del generador vienen en 3:2 y el cuadro es 16:9, así que sin el
    # recorte quedarían bandas — y una banda negra en una grilla de miniaturas se lee
    # como un video mal hecho antes de que nadie lea el título.
    filtros = [
        f"scale={ancho}:{alto}:force_original_aspect_ratio=increase",
        f"crop={ancho}:{alto}",
        VELO,
        _texto(gancho, salida.parent / "_mini_gancho.txt",
               largo=LARGO_DEL_GANCHO, tope=TOPE_DEL_GANCHO, y=Y_DEL_GANCHO, ancho=ancho),
    ]
    if bajada:
        filtros.append(
            _texto(bajada, salida.parent / "_mini_bajada.txt",
                   largo=LARGO_DE_LA_BAJADA, tope=TOPE_DE_LA_BAJADA,
                   y=Y_DE_LA_BAJADA, ancho=ancho)
        )

    logger.info(
        "Miniatura: «%s» / «%s» sobre %s → %sx%s",
        gancho, bajada or "—", origen.name, ancho, alto,
    )
    _componer(origen, salida, filtros, calidad)

    # Un JPG de 1280×720 no llega a 2 MB ni con calidad máxima, pero el límite es de
    # YouTube y el que lo rompe se entera al publicar, no al renderizar. Se baja la
    # calidad hasta entrar en vez de fallar: una portada un punto menos nítida es
    # infinitamente mejor que un video sin portada.
    while salida.stat().st_size > LIMITE_BYTES and calidad < 31:
        calidad += 4
        logger.warning(
            "La miniatura pesa %.1f MB y el límite de YouTube son 2 MB: se rehace con "
            "calidad %s.", salida.stat().st_size / 1024 / 1024, calidad,
        )
        _componer(origen, salida, filtros, calidad)
    if salida.stat().st_size > LIMITE_BYTES:
        raise DomainError(
            f"La miniatura pesa {salida.stat().st_size / 1024 / 1024:.1f} MB y no baja "
            f"de los 2 MB que acepta YouTube ni con la peor calidad."
        )
    return salida


def _componer(origen: Path, salida: Path, filtros: list[str], calidad: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(origen),
         "-vf", ",".join(filtros), "-frames:v", "1", "-q:v", str(calidad), str(salida)],
        check=True, capture_output=True,
    )


def envolver_parejo(texto: str, largo: int) -> list[str]:
    """Parte el texto en líneas de largo parecido, sin usar más líneas que las necesarias.

    `_envolver` es voraz: llena cada renglón hasta donde entra y lo que sobra cae al
    siguiente. En un párrafo no se nota; en un texto de tres palabras deja **una palabra
    sola en el último renglón**, que fue lo que se vio mirando la primera miniatura —
    *"A Morning Prayer For A Tired"* arriba y *"Heart"* solo abajo.

    Acá importa más que en el video porque el bloque es corto y está centrado: un
    renglón con una sola palabra corta el bloque en una escalera y se lee como un error
    de maquetación, que es justo la impresión que no puede dar la portada.

    Se prueba a acortar el renglón mientras no haga falta una línea más, y se queda con
    el reparto más parejo. El resultado para el caso real: *"A Morning Prayer"* /
    *"For A Tired Heart"*.
    """
    base = _envolver(texto, largo)
    mejor, dispersion = base, _dispersion(base)
    for corto in range(largo - 1, 0, -1):
        prueba = _envolver(texto, corto)
        if len(prueba) != len(base):
            break
        if (d := _dispersion(prueba)) < dispersion:
            mejor, dispersion = prueba, d
    return mejor


def _dispersion(lineas: list[str]) -> int:
    """Cuánto se diferencian el renglón más largo y el más corto."""
    return max(len(x) for x in lineas) - min(len(x) for x in lineas)


def _texto(texto: str, archivo: Path, *, largo: int, tope: int, y: str, ancho: int) -> str:
    """Un bloque de texto de la plantilla, con el tratamiento del motor.

    El tamaño sale de la misma fórmula que usa el render largo: el ancho útil dividido
    por lo que ocupa la línea más larga. `0.58` es el ancho medio de un caracter de
    DejaVu Bold en proporción a su altura, medido en el motor.
    """
    lineas = envolver_parejo(texto, largo)
    mas_larga = max(len(x) for x in lineas)
    tam = min(tope, int(ancho * 0.82 / (0.58 * mas_larga)))
    archivo.write_text("\n".join(lineas), encoding="utf-8")
    return (
        f"drawtext=fontfile={FUENTE}:textfile={archivo}:"
        f"fontcolor=white:fontsize={tam}:line_spacing=10:text_align=C:"
        f"borderw={contorno_para(tam)}:bordercolor=black@0.85:"
        f"x=(w-text_w)/2:y={y}"
    )


def contorno_para(tam: int) -> int:
    """El contorno que le corresponde a una letra de este tamaño.

    Mantiene la proporción del motor —8 px sobre una letra de 72— en vez del número.
    Es lo que hace que el tratamiento se vea igual cuando la letra es del doble de
    grande, que es lo que significa "el mismo tratamiento".
    """
    return max(CONTORNO, round(tam * CONTORNO / 72))
