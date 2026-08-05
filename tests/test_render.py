"""El render: de la historia narrada al MP4.

No se prueba el archivo (evaluar un video en un test no tiene sentido). Se prueba lo
que el render DECIDE: qué duración usa para cada escena y que falle claro cuando
falta algo, antes de invocar a ffmpeg.
"""

from __future__ import annotations

import shutil

import pytest

from engine.core.enums import AspectRatio, EducationalValue
from engine.core.exceptions import DomainError
from engine.core.models import Character, Style, Theme
from engine.engine import StoryEngine
from engine.generators.illustrator import SceneIllustrator
from engine.generators.narrator import StoryNarrator
from engine.providers.fake import FakeImageProvider, FakeTextProvider, FakeVoiceProvider
from engine.render.video import TAMANO, ShortRenderer

pytestmark = pytest.mark.anyio

sin_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="no hay ffmpeg")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _lista(tmp_path, tema, estilo, dino, tuca, *, palabras_por_s=2.5):
    story = await StoryEngine(text_provider=FakeTextProvider()).generate(
        theme=tema, style=estilo, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )
    await SceneIllustrator(FakeImageProvider()).illustrate(story, tmp_path / "img")
    await StoryNarrator(FakeVoiceProvider(palabras_por_s=palabras_por_s)).narrate(
        story, tmp_path / "audio"
    )
    return story


@sin_ffmpeg
async def test_cada_escena_dura_lo_que_dura_su_AUDIO(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """La regla que sostiene el módulo. Si el render usara la duración del plan, la
    imagen cambiaría mientras el narrador sigue hablando."""
    story = await _lista(tmp_path, tema_dinos, estilo_3d, dino, tuca, palabras_por_s=1.5)

    for escena in story.scenes:
        assert escena.real_duration_s == escena.audio_duration_s
        assert escena.real_duration_s != escena.duration_s  # la voz lenta se nota


@sin_ffmpeg
async def test_el_short_es_vertical(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    assert TAMANO[AspectRatio.VERTICAL] == (1080, 1920)
    r = ShortRenderer()
    assert (r._ancho, r._alto) == (1080, 1920)


@sin_ffmpeg
async def test_sin_imagenes_avisa_que_hay_que_ilustrar(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Un error de ffmpeg son treinta líneas de jerga; esto dice qué falta."""
    story = await StoryEngine(text_provider=FakeTextProvider()).generate(
        theme=tema_dinos, style=estilo_3d, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )
    with pytest.raises(DomainError, match="ilustrarlas"):
        ShortRenderer().render(story, tmp_path / "x.mp4")


@sin_ffmpeg
async def test_sin_audio_avisa_que_hay_que_narrar(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await StoryEngine(text_provider=FakeTextProvider()).generate(
        theme=tema_dinos, style=estilo_3d, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )
    await SceneIllustrator(FakeImageProvider()).illustrate(story, tmp_path / "img")
    with pytest.raises(DomainError, match="narrarlas"):
        ShortRenderer().render(story, tmp_path / "x.mp4")


@sin_ffmpeg
async def test_si_falta_un_archivo_en_disco_lo_dice(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _lista(tmp_path, tema_dinos, estilo_3d, dino, tuca)
    story.scenes[2].image_path = "/no/existe.png"
    with pytest.raises(DomainError, match="Faltan archivos"):
        ShortRenderer().render(story, tmp_path / "x.mp4")


def test_el_volumen_se_normaliza_al_estandar_de_las_plataformas() -> None:
    """Sin esto el audio sale en −20 dB y en el feed se escucha flojo. Y va al FINAL,
    sobre el audio ya armado: por tramo deja cada escena con otro volumen."""
    from engine.render.video import LOUDNESS

    assert "I=-16" in LOUDNESS


# --- el texto tiene que ENTRAR en el cuadro --------------------------------------


def test_un_titulo_largo_se_parte_en_lineas() -> None:
    """El primer short decía "no y la pelota de color": el título de 27 caracteres
    se salía del cuadro por los dos lados porque el tamaño era fijo."""
    from engine.render.video import _envolver

    lineas = _envolver("Dino y la pelota de colores")
    assert len(lineas) > 1
    assert all(len(x) <= 20 for x in lineas)
    assert " ".join(lineas) == "Dino y la pelota de colores"  # no se pierde nada


def test_no_corta_palabras_al_medio() -> None:
    from engine.render.video import _envolver

    original = "¿Y vos, qué compartís con tus amigos?"
    lineas = _envolver(original)
    assert " ".join(lineas) == original
    assert all(x == x.strip() for x in lineas)


def test_una_palabra_mas_larga_que_la_linea_no_desaparece() -> None:
    """Un nombre de tema largo no puede tragarse el título."""
    from engine.render.video import _envolver

    assert _envolver("supercalifragilisticoespialidoso") == [
        "supercalifragilisticoespialidoso"
    ]


@sin_ffmpeg
def test_el_texto_largo_usa_una_letra_mas_chica(tmp_path) -> None:
    """Si el tamaño no baja con el largo, partir en líneas no alcanza."""
    r = ShortRenderer()
    corto = r._texto("Dino", tmp_path / "a.txt", y="0", tope=88)
    largo = r._texto("Dino y la pelota de colores brillantes", tmp_path / "b.txt", y="0", tope=88)
    assert int(corto.split("fontsize=")[1].split(":")[0]) == 88
    assert int(largo.split("fontsize=")[1].split(":")[0]) < 88


@sin_ffmpeg
def test_el_texto_va_a_un_ARCHIVO_y_no_al_filtro(tmp_path) -> None:
    """El texto de un cuento tiene comillas, dos puntos y signos de apertura, y cada
    uno necesita su escape dentro de un filtro de ffmpeg. Con el texto en un archivo
    no hay nada que escapar. El primer intento con `text=` salió "ino y la pelota
    dencolore": el salto de línea se comió el espacio."""
    destino = tmp_path / "t.txt"
    filtro = ShortRenderer()._texto("Dino: el que no compartía", destino, y="0", tope=88)

    assert f"textfile={destino}" in filtro
    assert ":text=" not in filtro
    assert destino.read_text(encoding="utf-8").replace("\n", " ") == "Dino: el que no compartía"
