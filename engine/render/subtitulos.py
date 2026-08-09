"""Los subtítulos del formato largo: MEDIDOS, no estimados.

Pablo, 8-ago-2026, mirando el devocional de nueve minutos: *"subtítulos durante todo el
audio"*. El video sólo tenía texto en el título y en el cierre.

**LA PIEZA QUE HACE QUE ESTO SEA POSIBLE YA ESTABA CONSTRUIDA**, y es lo que separa a
estos subtítulos de los de cualquier generador: `Alineacion` —el `/with-timestamps` de
ElevenLabs— dice en qué segundo termina de decirse CADA CARACTER del pedido. El
narrador de cuentos ya la usaba para cortar la toma continua por escena. Acá se usa
para lo mismo, un orden de magnitud más fino: dónde empieza y dónde termina cada
renglón que se lee en pantalla.

La alternativa —repartir la duración de un bloque entre sus palabras a prorrata— se
descarta y no por elegancia: un bloque de este formato dura cuatro minutos, y la voz
del nicho está elegida por sus pausas largas (`bill`, 138,8 palabras por minuto, con
pausas de 0,68 s). Prorratear sobre un audio lleno de silencios acumula el error dentro
del bloque, y para el minuto tres el renglón va medio segundo adelantado. **Con la
alineación no hay deriva posible: cada renglón sale del reloj del propio audio.**

POR QUÉ ASS Y NO `drawtext`, que es lo que usa todo el resto del render:

Un devocional de veinte minutos son ~350 renglones. Con `drawtext` eso es un filtro de
350 capas con `enable='between(t,…)'` — un `-filter_complex` de cientos de miles de
caracteres que ffmpeg evalúa entero en cada uno de los 12.000 cuadros. Con un archivo
`.ass` es UN filtro, libass hace el trabajo, y el archivo queda además en disco para
subirlo como pista de subtítulos si algún día se quiere.

**Lo que NO cambia es el tratamiento**, y eso es deliberado: blanco, contorno negro
grueso, sin caja. Es la decisión del 7-ago-2026 —la caja tapa la imagen, que es lo
único que hay para mirar— y acá se reusa el mismo `CONTORNO` del render de shorts en
vez de inventar un número nuevo. Si algún día se cambia el grosor, se cambia en un solo
lugar y cambian los dos formatos.

**Y el ancho no se elige: se calcula.** El 7-ago-2026 el CTA del devocional salió con
la última palabra cortada por el borde de abajo porque el largo de línea era un número
puesto a mano. Acá `caracteres_por_linea()` sale del ancho del cuadro y del tamaño de
letra con la misma proporción de DejaVu que usa `video.py` (0,58 del tamaño por
carácter). Cambiar el tamaño de letra reajusta el corte solo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from engine.core.exceptions import DomainError
from engine.core.interfaces import Alineacion
from engine.render.video import CONTORNO, _envolver

logger = logging.getLogger(__name__)

#: Alto de la letra del subtítulo, en píxeles de un cuadro de 1080 de alto.
#:
#: **Grande a propósito**: Pablo, 8-ago-2026, *"grande, que se lea de lejos"*. Un video
#: devocional de veinte minutos se mira en una tele desde el sillón o en un teléfono
#: apoyado en la mesa de luz, no a treinta centímetros como un short en el feed.
#:
#: 64 px es el 5,9 % del alto del cuadro. Con dos renglones el bloque ocupa ~15 % de la
#: pantalla: se lee de lejos y todavía deja ver el paisaje, que es la mitad del
#: producto.
TAMANO_SUBTITULO = 64

#: Ancho de un carácter de DejaVu Sans Bold, como fracción del tamaño de letra.
#: Es el mismo 0,58 que usa `video.py` para calcular cuánto entra en una línea.
ANCHO_DE_CARACTER = 0.58

#: Qué fracción del ancho del cuadro puede ocupar el texto. El resto es margen.
#: El mismo 0,82 del render de shorts: sin margen el texto toca el borde y se lee peor.
ANCHO_UTIL = 0.82

#: Cuántos renglones puede tener un subtítulo. Dos.
#:
#: Con tres, el bloque de texto empieza a competir con la imagen; con uno, los cortes
#: caen a mitad de frase todo el tiempo porque no entra una oración corta entera.
RENGLONES = 2

#: A qué altura del cuadro termina el bloque de subtítulos, desde abajo.
#:
#: 100 px sobre el borde inferior. Queda debajo del centro de la imagen y **arriba de
#: donde vive la invitación** (`h*0.88-text_h`): los dos textos del video nunca se
#: pisan porque tampoco suenan al mismo tiempo, pero el margen deja eso garantizado
#: aunque en el futuro se solapen.
MARGEN_INFERIOR = 100

#: Lo menos que puede durar un subtítulo en pantalla.
#:
#: Un renglón de dos palabras que dura 0,4 s parpadea. Cuando el trozo medido dura
#: menos, se lo junta con el siguiente en vez de estirarlo: estirarlo lo desincronizaría
#: de la voz, que es justamente lo que este módulo existe para evitar.
MINIMO_EN_PANTALLA_S = 1.2

#: Cortes que valen como final de renglón. En orden de preferencia.
FIN_DE_FRASE = ".!?…"
PAUSA = ",;:—"


@dataclass(frozen=True, slots=True)
class Subtitulo:
    """Un renglón (o dos) en pantalla, con los segundos MEDIDOS del audio."""

    texto: str
    desde_s: float
    hasta_s: float

    @property
    def duracion_s(self) -> float:
        return self.hasta_s - self.desde_s


def caracteres_por_linea(ancho: int, tamano: int = TAMANO_SUBTITULO) -> int:
    """Cuántos caracteres entran en un renglón sin salirse del cuadro.

    Se calcula, no se elige. Es la corrección del 7-ago-2026 aplicada de entrada:
    aquel día el texto se salió del cuadro porque el largo de línea era una constante
    escrita a mano que nadie había vuelto a mirar cuando el cuadro cambió de forma.
    """
    return max(1, int(ancho * ANCHO_UTIL / (ANCHO_DE_CARACTER * tamano)))


def _trozos(texto: str, maximo: int) -> list[tuple[int, int]]:
    """Los índices `[desde, hasta)` de cada subtítulo dentro del texto.

    Corta donde el texto ya respira —punto, y si no hay, coma— y nunca parte una
    palabra. Es la misma regla que usa el narrador para partir en bloques, a otra
    escala: el corte que no se nota es el que el autor ya había puesto.
    """
    trozos: list[tuple[int, int]] = []
    inicio = 0
    corte_blando: int | None = None
    i = 0
    n = len(texto)

    while i < n:
        if texto[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not texto[j].isspace():
            j += 1  # j: fin de la palabra actual

        largo = j - inicio
        ultimo = texto[j - 1]

        if largo >= maximo:
            # Ya no entra: se cierra en el último respiro que hubo, o en la palabra
            # anterior si el trozo entero venía sin puntuación.
            fin = corte_blando if corte_blando and corte_blando > inicio else i
            fin = fin if fin > inicio else j
            trozos.append((inicio, fin))
            inicio = fin
            while inicio < n and texto[inicio].isspace():
                inicio += 1
            corte_blando = None
            i = inicio
            continue

        if ultimo in FIN_DE_FRASE:
            trozos.append((inicio, j))
            inicio = j
            while inicio < n and texto[inicio].isspace():
                inicio += 1
            corte_blando = None
            i = inicio
            continue

        if ultimo in PAUSA:
            corte_blando = j

        i = j
        while i < n and texto[i].isspace():
            i += 1

    if inicio < n:
        trozos.append((inicio, n))
    return [(a, b) for a, b in trozos if texto[a:b].strip()]


def subtitulos_de(
    texto: str,
    marcas: Alineacion,
    *,
    offset_s: float = 0.0,
    maximo: int,
) -> list[Subtitulo]:
    """Los subtítulos de un bloque narrado, con los tiempos leídos del audio.

    `offset_s` es cuánto audio va antes de este bloque: los tiempos de la alineación
    son relativos al pedido y el video es uno solo.

    **El texto tiene que estar adentro de la alineación tal cual.** Lo está: el bloque
    se manda como `dirección + texto + colchón` y la alineación devuelve los caracteres
    del pedido completo, así que el texto aparece entero y una sola vez. Si no
    apareciera, el subtítulo saldría corrido y **eso no se ve mirando un fotograma** —
    hay que escuchar—, así que falla acá en vez de salir mal en silencio.
    """
    if not texto.strip():
        return []
    base = marcas.texto.find(texto)
    if base < 0:
        raise DomainError(
            "La alineación del audio no contiene el texto que se narró: los "
            f"subtítulos saldrían corridos. Texto: {texto[:60]!r}…"
        )

    subs: list[Subtitulo] = []
    for desde_i, hasta_i in _trozos(texto, maximo):
        i, j = base + desde_i, base + hasta_i
        desde = marcas.fin_s[i - 1] if i > 0 else 0.0
        hasta = marcas.fin_s[j - 1]
        pedazo = Subtitulo(
            texto=texto[desde_i:hasta_i].strip(),
            desde_s=offset_s + desde,
            hasta_s=offset_s + hasta,
        )
        # Un renglón que parpadea se junta con el anterior, nunca se estira: estirarlo
        # lo despegaría de la voz, que es lo único que este módulo garantiza.
        if subs and pedazo.duracion_s < MINIMO_EN_PANTALLA_S:
            previo = subs.pop()
            pedazo = Subtitulo(
                texto=f"{previo.texto} {pedazo.texto}",
                desde_s=previo.desde_s,
                hasta_s=pedazo.hasta_s,
            )
        subs.append(pedazo)
    return subs


def _tiempo(segundos: float) -> str:
    """`H:MM:SS.cc`, que es como ASS escribe el tiempo (centésimas, no milésimas)."""
    segundos = max(0.0, segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    return f"{int(horas)}:{int(minutos):02d}:{seg:05.2f}"


def _escapar(texto: str) -> str:
    """El texto listo para un renglón de ASS.

    En ASS la barra invertida y las llaves son sintaxis —`{\\an8}` mueve el texto—, así
    que un texto que las traiga se ejecutaría en vez de leerse. Los devocionales en
    inglés no las usan; esto está para que el día que aparezca una, el video no salga
    con un renglón invisible.
    """
    return texto.replace("\\", "/").replace("{", "(").replace("}", ")")


def escribir_ass(
    subtitulos: list[Subtitulo],
    destino: str | Path,
    *,
    ancho: int,
    alto: int,
    tamano: int = TAMANO_SUBTITULO,
    fuente: str = "DejaVu Sans",
) -> Path:
    """Escribe el `.ass` y devuelve su ruta.

    Los cuatro valores del estilo que importan, y por qué:

    - `BorderStyle=1` con `Outline=CONTORNO` y `Shadow=0` → **contorno, sin caja**. Es
      la decisión del 7-ago-2026 y la misma constante del render de shorts. Con
      `BorderStyle=3` ASS dibuja el recuadro opaco que justamente se sacó.
    - `Alignment=2` con `MarginV` → abajo y centrado, donde la vista ya los busca.
    - `PlayResX/PlayResY` iguales al video → `Fontsize` en píxeles reales del cuadro.
      Sin esto libass escala contra 384×288 y la letra sale cuatro veces más chica.
    - `MarginL/R` iguales al margen que deja `ANCHO_UTIL` → aunque libass decida
      reenvolver un renglón, no lo puede llevar contra el borde.
    """
    salida = Path(destino)
    salida.parent.mkdir(parents=True, exist_ok=True)
    margen = int(ancho * (1 - ANCHO_UTIL) / 2)
    por_linea = caracteres_por_linea(ancho, tamano)

    cabecera = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {ancho}",
            f"PlayResY: {alto}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding",
            # Blanco opaco, contorno negro al 85 % (alpha 0x26), sin sombra y sin caja:
            # el mismo tratamiento que el título y el cierre.
            f"Style: Devocional,{fuente},{tamano},&H00FFFFFF,&H00FFFFFF,&H26000000,"
            f"&H00000000,-1,0,0,0,100,100,0,0,1,{CONTORNO},0,2,"
            f"{margen},{margen},{MARGEN_INFERIOR},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text",
        ]
    )

    renglones = []
    for s in subtitulos:
        # Sin recorte: si un trozo cae en tres renglones —una palabra larga puede
        # empujar la envoltura— se muestran los tres. Un renglón de más se ve; una
        # frase a la que le falta el final se lee mal y nadie se entera mirando un
        # fotograma. Que entre en dos es el objetivo de `maximo`, no una garantía que
        # se pueda cumplir cortando texto.
        lineas = _envolver(_escapar(s.texto), por_linea)
        # **NUEVE campos, ni uno más**: Layer, Start, End, Style, Name, MarginL,
        # MarginR, Effect, Text. libass parte en ocho comas y todo lo que sigue es el
        # texto, así que un campo de más no da error: **se ve escrito en pantalla.**
        # Pasó el 8-ago-2026 con un `0` de más en `Effect`, y los 20 renglones de la
        # muestra salieron empezando con una coma: `,The dawn is breaking`. No lo
        # cazó ningún test —el `.ass` era válido y ffmpeg no se quejó—, se vio
        # MIRANDO un fotograma.
        renglones.append(
            f"Dialogue: 0,{_tiempo(s.desde_s)},{_tiempo(s.hasta_s)},Devocional,,0,0,,"
            + "\\N".join(lineas)
        )

    salida.write_text("\n".join([cabecera, *renglones, ""]), encoding="utf-8")
    logger.info(
        "Subtítulos: %s renglones · hasta %s caracteres por línea · %s px",
        len(subtitulos), por_linea, tamano,
    )
    return salida
