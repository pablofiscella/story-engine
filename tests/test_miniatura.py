"""La portada del video largo: la imagen con la que se lo elige.

Pablo, 9-ago-2026: *"Hay que configurar en el video largo de YouTube la imagen que se
pone en la portada del video. Esa tiene que convencer. Quizás buscar algo que represente
a la marca con un título del video."*

EL CASO REAL QUE FIJAN ESTOS TESTS, y es el primer video del canal Grace This Morning:

    título   "Before This Day Begins — A Morning Prayer For A Tired Heart"  (51 caracteres)
    imagen   fondo1.png, 1536×1024, el valle al amanecer — la primera del video
    video    18:28, publicado el 9-ago-2026 08:08 como pJM8YaBwZsE
    salida   1280×720, 183 KB, muy por debajo de los 2 MB que acepta YouTube

**Los dos defectos que estos tests existen para que no vuelvan, y los dos se
encontraron MIRANDO la imagen, no corriendo nada:**

1. **El gancho salía cortado por el borde de arriba.** La primera versión anclaba el
   bloque por donde TERMINA, copiando el `Y_DEL_CIERRE` del video —donde ese anclaje
   es la corrección del 7-ago para que el CTA no se saliera por ABAJO—. El mismo
   anclaje, en el otro borde, produce el mismo defecto en espejo.
   `test_el_gancho_no_se_corta_contra_el_borde` lo mide en los píxeles.
2. **La bajada dejaba una palabra sola en el último renglón** (*"…For A Tired"* /
   *"Heart"*), porque el envoltorio del motor es voraz. En un párrafo no se nota; en un
   bloque de tres palabras centrado se lee como un error de maquetación.

Y el dato que decide todo el diseño: en el feed la miniatura se ve a unos **210 px de
ancho**, un sexto del archivo. Un título de 51 caracteres puesto entero queda en letra
de 6 px reales: ilegible, o sea igual que no tener texto pero encima tapando el paisaje.
Por eso el título se parte en gancho y bajada.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.core.exceptions import DomainError
from engine.render.miniatura import (
    LIMITE_BYTES,
    MEDIDA,
    TOPE_DEL_GANCHO,
    contorno_para,
    envolver_parejo,
    miniatura_de,
    partir_titulo,
    render_miniatura,
)
from engine.render.video import CONTORNO

#: El título del primer devocional del canal, tal como se publicó.
TITULO_REAL = "Before This Day Begins — A Morning Prayer For A Tired Heart"


def _png(destino: Path, color: str = "#2E4A6B", ancho: int = 1536, alto: int = 1024) -> Path:
    """Una imagen del tamaño real de la que devuelve el generador.

    Color sólido y oscuro a propósito: contra un fondo parejo, cualquier píxel claro de
    la imagen terminada **es** texto, y eso es lo que permite medir si el texto se sale
    del cuadro sin tener que mirarlo.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"color=c={color}:s={ancho}x{alto}", "-frames:v", "1", str(destino)],
        check=True, capture_output=True,
    )
    return destino


def _pixeles(imagen: Path) -> tuple[list[tuple[int, int, int]], int, int]:
    """La imagen como lista de píxeles RGB, con su ancho y su alto."""
    crudo = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(imagen), "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    ancho, alto = MEDIDA
    return [tuple(crudo[i:i + 3]) for i in range(0, len(crudo), 3)], ancho, alto


def _hay_texto_en_la_fila(pixeles, ancho: int, fila: int, umbral: int = 200) -> bool:
    """Si algún píxel de esa fila es claro, o sea blanco de letra sobre fondo oscuro."""
    inicio = fila * ancho
    return any(min(p) > umbral for p in pixeles[inicio:inicio + ancho])


# --- Cómo se parte el título ------------------------------------------------------

def test_el_titulo_real_se_parte_en_gancho_y_bajada() -> None:
    """La raya del título ya declara dónde termina el gancho: se le hace caso.

    No es una heurística que adivina — los títulos del nicho tienen esta forma y el
    nuestro se escribió con ella.
    """
    assert partir_titulo(TITULO_REAL) == (
        "Before This Day Begins",
        "A Morning Prayer For A Tired Heart",
    )


def test_un_titulo_corto_y_sin_raya_va_entero_de_gancho() -> None:
    """Es la miniatura de The Gentle Bible, el canal con más vistas por video de los 14."""
    assert partir_titulo("Psalm 23") == ("Psalm 23", "")


def test_un_titulo_largo_sin_raya_se_parte_por_la_mitad() -> None:
    """El peor caso: sale razonable en vez de salir en letra de 6 px."""
    gancho, bajada = partir_titulo(
        "A Prayer For When Your Mind Will Not Stop Running Tonight"
    )
    assert gancho and bajada
    assert abs(len(gancho) - len(bajada)) < 14


def test_los_dos_puntos_tambien_parten() -> None:
    """El nicho titula así: «Psalm 91: The Prayer That Covers You»."""
    assert partir_titulo("Psalm 91: The Prayer That Covers You") == (
        "Psalm 91", "The Prayer That Covers You",
    )


def test_un_video_sin_titulo_falla_diciendo_por_que() -> None:
    with pytest.raises(DomainError, match="no tiene título"):
        partir_titulo("   ")


# --- El reparto de los renglones --------------------------------------------------

def test_la_bajada_no_deja_una_palabra_sola(caplog) -> None:
    """El defecto que se vio mirando: «Heart» solo en el último renglón.

    El envoltorio voraz del motor llenaba el primer renglón hasta el tope y tiraba la
    última palabra sola abajo. Con el mismo número de renglones se reparte parejo.
    """
    assert envolver_parejo("A Morning Prayer For A Tired Heart", 30) == [
        "A Morning Prayer",
        "For A Tired Heart",
    ]


def test_repartir_parejo_no_gasta_un_renglon_de_mas() -> None:
    """Un renglón de más es letra más chica, y el tamaño es lo único que sobrevive al feed."""
    for largo in (12, 14, 20, 30):
        texto = "Before This Day Begins"
        assert len(envolver_parejo(texto, largo)) == len(
            [x for x in _voraz(texto, largo)]
        )


def _voraz(texto: str, largo: int) -> list[str]:
    from engine.render.video import _envolver
    return _envolver(texto, largo)


# --- El tratamiento es el del motor -----------------------------------------------

def test_el_contorno_crece_con_la_letra_manteniendo_la_proporcion() -> None:
    """«El mismo tratamiento» es la proporción, no el número.

    En el video el título va en 72 px con `CONTORNO` de 8. Con la letra del doble de
    grande, 8 px se ven finos y al achicar la miniatura el borde desaparece antes que la
    letra: el blanco se come contra un cielo claro, que es el fondo de todo este nicho.
    """
    assert contorno_para(72) == CONTORNO
    assert contorno_para(144) == CONTORNO * 2
    assert contorno_para(20) == CONTORNO, "nunca menos que el del motor"


def test_la_miniatura_no_lleva_caja(tmp_path: Path) -> None:
    """La caja negra se sacó del motor el 7-ago-2026 y no vuelve por la ventana.

    Tapa la imagen, y en una portada la imagen es la mitad de lo que vende.
    """
    from engine.render.miniatura import _texto
    filtro = _texto(
        "Before This Day Begins", tmp_path / "t.txt",
        largo=14, tope=TOPE_DEL_GANCHO, y="h*0.07", ancho=MEDIDA[0],
    )
    assert "box=1" not in filtro
    assert "boxcolor" not in filtro
    assert "fontcolor=white" in filtro
    assert "bordercolor=black" in filtro


# --- La imagen terminada ----------------------------------------------------------

def test_la_miniatura_mide_1280x720_y_entra_en_el_limite(tmp_path: Path) -> None:
    """Las dos condiciones que YouTube impone y que se conocen al publicar, no al render."""
    salida = render_miniatura(TITULO_REAL, _png(tmp_path / "fondo.png"), tmp_path / "m.jpg")
    pixeles, ancho, alto = _pixeles(salida)
    assert (ancho, alto) == (1280, 720)
    assert len(pixeles) == ancho * alto
    assert salida.stat().st_size < LIMITE_BYTES


def test_el_gancho_no_se_corta_contra_el_borde(tmp_path: Path) -> None:
    """EL test de este archivo: el defecto que sólo se veía mirando, ahora medido.

    La primera versión anclaba el gancho por donde TERMINA y la línea de arriba salía
    cortada por el borde superior. Contra un fondo sólido oscuro, un píxel claro en la
    primera fila **es** una letra que se salió del cuadro.

    Se miran los cuatro bordes: el de arriba por el gancho, el de abajo por la bajada, y
    los laterales porque un título de una sola palabra muy larga también se escapa.
    """
    salida = render_miniatura(TITULO_REAL, _png(tmp_path / "fondo.png"), tmp_path / "m.jpg")
    pixeles, ancho, alto = _pixeles(salida)

    assert not _hay_texto_en_la_fila(pixeles, ancho, 0), "el gancho se sale por arriba"
    assert not _hay_texto_en_la_fila(pixeles, ancho, alto - 1), "la bajada se sale por abajo"
    laterales = [p for f in range(alto) for p in (pixeles[f * ancho], pixeles[f * ancho + ancho - 1])]
    assert not any(min(p) > 200 for p in laterales), "el texto toca un borde lateral"


def test_el_texto_esta_de_verdad_en_la_imagen(tmp_path: Path) -> None:
    """Que no se corte no sirve de nada si no se dibujó.

    Es el hueco del 6-ago-2026 en versión chica: que el dato exista no prueba que se
    use. Sobre un fondo sólido, la miniatura tiene que tener píxeles blancos —el texto—
    y tienen que estar arriba (el gancho) y abajo (la bajada).
    """
    salida = render_miniatura(TITULO_REAL, _png(tmp_path / "fondo.png"), tmp_path / "m.jpg")
    pixeles, ancho, alto = _pixeles(salida)
    arriba = any(_hay_texto_en_la_fila(pixeles, ancho, f) for f in range(int(alto * 0.10), int(alto * 0.40)))
    abajo = any(_hay_texto_en_la_fila(pixeles, ancho, f) for f in range(int(alto * 0.60), int(alto * 0.85)))
    assert arriba, "no se dibujó el gancho"
    assert abajo, "no se dibujó la bajada"


def test_sin_imagen_falla_antes_de_invocar_a_ffmpeg(tmp_path: Path) -> None:
    with pytest.raises(DomainError, match="No está la imagen"):
        render_miniatura(TITULO_REAL, tmp_path / "no-existe.png", tmp_path / "m.jpg")


def test_la_miniatura_va_al_lado_del_video_con_su_mismo_nombre() -> None:
    """Una convención, no una configuración: un dato que se deriva no se puede pasar mal.

    El 6-ago-2026 costó una vuelta entera que el scheduler le pasara al publicador el
    NOMBRE del archivo donde esperaba una URL.
    """
    assert miniatura_de("/tmp/campanias_out/grace_morning.mp4") == Path(
        "/tmp/campanias_out/grace_morning.jpg"
    )
