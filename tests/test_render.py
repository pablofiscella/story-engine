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


# --- cómo se ve y CUÁNDO aparece -------------------------------------------------


@sin_ffmpeg
def test_el_texto_lleva_contorno_y_no_caja(tmp_path) -> None:
    """La caja negra tapaba la ilustración, que es lo que hay que mirar. Con un
    contorno grueso el texto se lee igual sobre las zonas claras y las oscuras."""
    filtro = ShortRenderer()._texto("Dino", tmp_path / "t.txt", y="0", tope=88)

    assert "borderw=" in filtro and "bordercolor=" in filtro
    assert "box=1" not in filtro and "boxcolor" not in filtro


@sin_ffmpeg
async def test_la_pregunta_aparece_cuando_se_dice_no_antes(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El cierre narra primero la moraleja y después la pregunta. Si el texto está
    desde el arranque del tramo, decora; si entra con lo que se escucha, se lee."""
    from engine.render.video import ADELANTO_DEL_CIERRE_S

    story = await _lista(tmp_path, tema_dinos, estilo_3d, dino, tuca)
    moraleja = story.closing_audio[0].duration_s

    filtro = ShortRenderer()._texto(
        story.closing_question, tmp_path / "c.txt", y="h*0.80", tope=64,
        desde=moraleja - ADELANTO_DEL_CIERRE_S,
    )
    assert f"enable='gte(t,{moraleja - ADELANTO_DEL_CIERRE_S:.3f})'" in filtro
    assert moraleja - ADELANTO_DEL_CIERRE_S > 0  # hay moraleja antes de la pregunta


@sin_ffmpeg
def test_sin_hora_de_entrada_el_texto_esta_desde_el_principio(tmp_path) -> None:
    """El título tiene que verse apenas arranca: son los segundos que deciden si se
    quedan."""
    filtro = ShortRenderer()._texto("Dino", tmp_path / "t.txt", y="0", tope=88)
    assert "enable=" not in filtro


# --- las transiciones -------------------------------------------------------------


def test_las_imagenes_se_cruzan_en_vez_de_saltar() -> None:
    """Seis fotos que cambian de golpe se ven como una presentación de diapositivas.
    El motor viejo tenía este mismo cruce en el camino de Remotion y lo perdió en el
    de ffmpeg, donde los tramos se pegaban con `concat -c copy`."""
    from engine.render.video import TRANSICION_S, _encadenar

    cadena = _encadenar(["[a]", "[b]", "[c]"], [5.0, 4.0, 3.0])
    assert cadena.count("xfade") == 2
    assert f"duration={TRANSICION_S}" in cadena
    assert cadena.endswith("[vcrudo]")


def test_cada_cruce_arranca_donde_termina_su_escena() -> None:
    """El offset mal calculado es lo que desincroniza la imagen del audio: la escena
    se iría antes o después de lo que dura su narración."""
    from engine.render.video import TRANSICION_S, _encadenar

    cadena = _encadenar(["[a]", "[b]", "[c]"], [5.0, 4.0, 3.0])
    offsets = [float(x.split("offset=")[1].split("[")[0]) for x in cadena.split(";")]
    assert offsets == [5.0 - TRANSICION_S, 9.0 - TRANSICION_S]


def test_una_sola_escena_no_necesita_cruce() -> None:
    from engine.render.video import _encadenar

    assert "xfade" not in _encadenar(["[a]"], [5.0])


@sin_ffmpeg
async def test_el_video_no_puede_durar_menos_que_el_audio(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """`-shortest` corta el stream más largo: si el video queda corto, le come el
    final a la narración. Pasó por el último `xfade`, que acorta el resultado en
    `TRANSICION_S` — la última frase perdía una sílaba."""
    import subprocess

    from engine.core.constants import COLA_FINAL_S, PAUSA_ENTRE_ESCENAS_S, TITULO_S

    story = await _lista(tmp_path, tema_dinos, estilo_3d, dino, tuca)
    salida = ShortRenderer().render(story, tmp_path / "corto.mp4")

    # Cuando la narración se grabó de una sola toma no hay silencio entre escenas: el
    # aire ya está adentro del audio.
    pausa = 0.0 if story.continuous_narration else PAUSA_ENTRE_ESCENAS_S
    audio = TITULO_S + COLA_FINAL_S
    audio += sum(e.audio_duration_s + pausa for e in story.scenes)
    audio += sum(t.duration_s for t in story.closing_audio)

    real = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(salida)],
        capture_output=True, text=True, check=True).stdout.strip())
    assert real >= audio - 0.15, f"el video ({real:.2f}s) corta el audio ({audio:.2f}s)"


# --- el título, ahora hablado -----------------------------------------------------


async def _con_titulo(tmp_path, tema, estilo, dino, tuca, titulo="Dino aprende a compartir"):
    story = await StoryEngine(text_provider=FakeTextProvider()).generate(
        theme=tema, style=estilo, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca], title=titulo,
    )
    await SceneIllustrator(FakeImageProvider()).illustrate(story, tmp_path / "img")
    await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path / "audio")
    return story


@sin_ffmpeg
async def test_el_video_con_titulo_hablado_no_corta_el_audio(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """La placa tiene que durar lo que tarda en decirse el título.

    Antes duraba dos segundos fijos y el render le anteponía dos segundos de silencio
    al audio. Con el título hablado, dejar ese silencio correría el cuento entero y
    `-shortest` le comería el final: es el mismo error del último `xfade`, por otra
    puerta.
    """
    import subprocess

    from engine.core.constants import COLA_FINAL_S, PAUSA_ENTRE_ESCENAS_S, TITULO_S

    story = await _con_titulo(tmp_path, tema_dinos, estilo_3d, dino, tuca)
    salida = ShortRenderer().render(story, tmp_path / "corto.mp4")

    pausa = 0.0 if story.continuous_narration else PAUSA_ENTRE_ESCENAS_S
    dur_titulo = sum(t.duration_s for t in story.title_audio)
    audio = max(TITULO_S, dur_titulo) + COLA_FINAL_S
    audio += sum(e.audio_duration_s + pausa for e in story.scenes)
    audio += sum(t.duration_s for t in story.closing_audio)

    real = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(salida)],
        capture_output=True, text=True, check=True).stdout.strip())
    assert story.title_audio, "el título se narró"
    assert real >= audio - 0.15, f"el video ({real:.2f}s) corta el audio ({audio:.2f}s)"


@sin_ffmpeg
async def test_sin_titulo_narrado_la_placa_sigue_siendo_muda(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El camino viejo tiene que seguir funcionando.

    Un proveedor sin alineación narra escena por escena y no deja título hablado; ahí
    el render vuelve a la placa de duración fija con su silencio adelante, que es como
    venía andando.
    """
    import subprocess

    story = await _con_titulo(tmp_path, tema_dinos, estilo_3d, dino, tuca)
    story.title_audio = []

    salida = ShortRenderer().render(story, tmp_path / "mudo.mp4")

    real = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(salida)],
        capture_output=True, text=True, check=True).stdout.strip())
    assert real > 0


@sin_ffmpeg
def test_el_cierre_se_ancla_por_ABAJO_y_no_por_arriba(tmp_path) -> None:
    """La última palabra del CTA quedó cortada por el borde inferior (7-ago-2026).

    El texto del cierre se posicionaba con `y="h*0.80"`, que es dónde EMPIEZA el
    bloque. Como crece hacia abajo, cada línea de más lo empuja fuera del cuadro. Con
    los cuentos no se vio nunca: su pregunta final entra en dos líneas de español. La
    invitación del primer devocional —*"If your mind has been loud lately, type AMEN so
    I can pray for you by name"*— ocupa **cinco**, y salió con "name." partida al medio
    por el borde.

    No es una imperfección estética: el nicho se eligió por su 1,718 % de comentarios,
    el más alto de los cinco medidos, y lo único ilegible del video era justo la línea
    que los pide.

    Anclar por `text_h` lo arregla para cualquier largo **sin estimar** cuánto mide una
    línea de DejaVu. Ahí estaba el error de fondo: el tamaño de letra sí se calculaba
    (por el ANCHO), pero el alto del bloque se daba por sentado.
    """
    from engine.render.video import Y_DEL_CIERRE, _envolver

    assert "text_h" in Y_DEL_CIERRE, "el cierre volvió a anclarse por el borde de arriba"

    invitacion = "If your mind has been loud lately, type AMEN so I can pray for you by name."
    assert len(_envolver(invitacion)) >= 5, "el caso que lo rompió ya no se parte igual"


@sin_ffmpeg
def test_el_cierre_termina_dentro_del_cuadro_con_cualquier_largo(tmp_path) -> None:
    """La otra mitad: el arreglo no puede depender de estimar cuánto mide una línea.

    El primer intento de este test comparaba contra una altura de bloque calculada a
    mano (`lineas * fontsize + espaciado`) y daba 11,6 px de diferencia. Estaba mal
    planteado: **esa cuenta es exactamente la que el bug demostró que no se puede
    hacer** — ffmpeg dibuja una línea más alta que su `fontsize`, y por eso los 1912
    px "calculados" del cierre roto en realidad se salían del cuadro.

    Lo que sí se puede afirmar sin estimar nada: con el ancla escrita como
    `<fracción de h> - text_h`, el bloque TERMINA en esa fracción sea cual sea su
    altura, y la fracción es menor que 1. El que mide `text_h` es ffmpeg.
    """
    from engine.render.video import Y_DEL_CIERRE

    assert Y_DEL_CIERRE.endswith("-text_h"), (
        "el cierre tiene que anclarse por donde TERMINA el bloque"
    )
    fraccion = float(Y_DEL_CIERRE.removesuffix("-text_h").removeprefix("h*"))
    assert 0.5 < fraccion < 1.0, f"el cierre termina en h*{fraccion}, fuera del cuadro"
