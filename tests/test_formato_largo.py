"""El formato largo: una imagen fija, texto y audio.

Pablo, 8-ago-2026, después de mirar los canales del nicho: *"Los últimos videos tienen
sólo una imagen y sólo texto y audio"*. Los 8 canales del nicho que hacen formato largo
tienen una mediana de 31 a 158 minutos, y **es el formato que más vistas junta por
video**.

Los dos casos reales que fijan estos tests, los dos medidos contra la cuenta de verdad
el 8-ago-2026:

1. **ElevenLabs corta en 5.000 caracteres por pedido**: *"Request text length (209000)
   exceeds the maximum text length of 5000 characters. Please use Studio for long form
   TTS."* Un devocional de diez minutos son ~8.300 caracteres: **no entra en un
   pedido**, y uno de cuarenta necesita siete. Es la razón de existir del narrador de
   bloques.
2. **`previous_text` no existe en `eleven_v3`**: *"Providing previous_text or next_text
   is not yet supported with the 'eleven_v3' model"*. O sea que la costura entre
   bloques no se puede pedir: hay que cortar por donde el texto ya respira, que es el
   final de una escena.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from engine.core.enums import (
    AgeRange,
    AspectRatio,
    EducationalValue,
    Language,
    SpiritualNeed,
    StoryStatus,
)
from engine.core.exceptions import DomainError
from engine.core.models.character import Appearance, Character
from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.core.models.theme import Palette, Theme
from engine.generators.devotional import profile_for
from engine.generators.devotional_planner import (
    RITMO_LARGO_S,
    DevotionalPlanner,
    instrucciones_distintas,
)
from engine.generators.planner import StoryPlanner
from engine.generators.still_narrator import (
    LIMITE_DE_PEDIDO,
    StillNarrator,
    caracteres_de,
)
from engine.prompts.devocional import DIRECCION_LARGA
from engine.prompts.voz import DIRECCION as DIRECCION_DE_CUENTOS
from engine.providers.fake import FakeVoiceProvider
from engine.render.still import COLA_DEL_TITULO_S, StillRenderer
from engine.render.video import CONTORNO

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def devocional_largo(historia: Story) -> Story:
    """Seis escenas largas, con título, promesa e invitación."""
    historia.metadata.title = "A Prayer For When Your Mind Won't Stop"
    historia.moral = "Peace is not the absence of the storm."
    historia.closing_question = (
        "If your mind has been loud lately, type AMEN so I can pray for you by name."
    )
    historia.scenes = [
        Scene.from_plan(p, narration=t)
        for p, t in zip(
            historia.plan.scenes,
            [
                "Before this day unfolds, stop for one moment.",
                "The weight you carry tonight has a name.",
                "Father, I hand over what I cannot fix.",
                "The quiet does not always answer on time.",
                "Mercy arrives before the circumstance changes.",
                "Rest now. You are not carrying this alone.",
            ],
            strict=True,
        )
    ]
    historia.advance_to(StoryStatus.PLANNED)
    historia.advance_to(StoryStatus.WRITTEN)
    return historia


def _png(destino: Path, ancho: int = 1536, alto: int = 1024) -> Path:
    """Una imagen del tamaño real de la que devuelve el generador."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"color=c=#2E4A6B:s={ancho}x{alto}", "-frames:v", "1", str(destino)],
        check=True, capture_output=True,
    )
    return destino


def _ffprobe(mp4: Path) -> dict:
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-of", "json", str(mp4)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(salida.stdout)


# --- El planificador en formato largo ---------------------------------------------
#: La figura en pantalla y el tema, mínimos, para planificar sin tocar proveedores.
_ORANTE = Character(
    id="orante",
    name="the one who prays",
    appearance=Appearance(species="human figure", description="a distant silhouette"),
)
_TEMA = Theme(
    id="amanecer",
    name="Quiet dawn",
    description="wide quiet landscapes",
    palette=Palette(primary="#F5C77E", secondary="#2E4A6B", accent="#FFF6E5"),
    locations=["a hilltop above a wide valley", "an empty shoreline at dawn"],
)


def _plan_largo(need: SpiritualNeed, duracion: float = 540.0, ritmo: float = RITMO_LARGO_S):
    return DevotionalPlanner().create_plan(
        theme=_TEMA, need=need, duration_s=duracion,
        speaker=_ORANTE, language=Language.EN, ritmo_s=ritmo,
    )


@pytest.mark.parametrize("need", list(SpiritualNeed))
def test_ningun_devocional_largo_repite_una_sola_instruccion(need: SpiritualNeed) -> None:
    """EL test de este archivo, y el que faltaba el 8-ago-2026 a la mañana.

    Con el ritmo de 15 s, un devocional de nueve minutos pedía **36 escenas** y el
    perfil de `manana` tiene **8 instrucciones distintas**. El planificador rellenó
    repitiendo la misma orden numerada —`"#14: Name waking up already carrying
    yesterday"`— y el escritor devolvió catorce textos casi iguales, todos empezando
    con *"You wake up…"*.

    Eso no es un problema de prosa: es textualmente lo que la política de YouTube del
    16-jul-2026 castiga con el canal entero, *"characters put in the same situation
    over and over again with the same outcome"*. Lo cazó el verificador de guion en su
    primer trabajo real, con 25 muletillas.

    Dos escenas con la misma instrucción son dos escenas iguales. Acá no puede haber
    ninguna, para ninguna de las diez necesidades.
    """
    plan = _plan_largo(need)
    propositos = [s.purpose for s in plan.scenes]
    assert len(set(propositos)) == len(propositos)


def test_el_perfil_dice_cuantas_escenas_distintas_puede_llenar() -> None:
    """El techo no es una opinión sobre el largo ideal: está escrito en el perfil.

    Y la palanca para hacer devocionales más largos queda dicha: escribirle más
    `deepenings` al perfil, no subir la duración y esperar que el escritor invente.
    """
    perfil = profile_for(SpiritualNeed.MORNING)
    assert instrucciones_distintas(perfil) == 8  # 6 propósitos + 2 variantes de PROBLEM
    assert len(_plan_largo(SpiritualNeed.MORNING).scenes) <= 8


def test_pedir_mas_largo_de_lo_que_el_perfil_aguanta_falla_diciendo_la_palanca() -> None:
    """Falla antes de escribir una palabra, y el mensaje dice qué hacer.

    Es lo contrario de lo que pasó el 8-ago-2026: el planificador aceptó en silencio y
    el problema apareció recién leyendo 36 escenas generadas.
    """
    with pytest.raises(DomainError, match="más variantes al perfil"):
        _plan_largo(SpiritualNeed.MORNING, duracion=1200.0)


def test_el_tope_de_90s_no_mueve_a_los_cuentos(
    tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """`MAX_SCENE_DURATION_S` pasó de 20 a 90 y los cuentos tienen que salir idénticos.

    Nunca era el tope que mandaba en un cuento: ahí manda `SCENE_PACING_S` (4 a 8 s por
    escena según la edad), que es mucho más chico. Este test lo fija para que subirlo
    no se pueda convertir en una regresión silenciosa del otro producto.
    """
    plan = StoryPlanner().create_plan(
        theme=tema_dinos,
        value=EducationalValue.SHARING,
        age_range=AgeRange.PRESCHOOL,
        duration_s=30.0,
        protagonist=dino,
        companion=tuca,
    )
    assert len(plan.scenes) == 6
    assert all(s.duration_s <= 8.0 for s in plan.scenes)


def test_la_direccion_de_voz_es_corta_o_el_narrador_la_LEE() -> None:
    """El defecto más caro del 8-ago-2026, y el único que sólo se vio transcribiendo.

    Con 235 caracteres, `eleven_v3` leyó la dirección de escena en voz alta: los
    primeros catorce segundos del devocional eran el narrador diciendo *"calm, low,
    unhurried voice, speaking quietly to one person…"*. No lo vio ningún test, ni el
    guardián de toma cortada (el audio llegó entero, sólo que decía de más), ni el
    verificador de guion (mira el texto, no el audio).

    Medido con la misma frase y la misma voz: hasta 112 caracteres la actúa; con 202 y
    con 235 la lee. La de los cuentos, que anda hace meses, tiene 164. El tope de este
    test es ése, y la constante se queda bastante más abajo.

    No son los puntos adentro del corchete: se probó sacándolos y a 202 siguió
    leyéndola. Es el largo.
    """
    assert len(DIRECCION_LARGA) <= len(DIRECCION_DE_CUENTOS)
    assert DIRECCION_LARGA.startswith("[") and DIRECCION_LARGA.endswith("]")


# --- El límite de 5.000 caracteres ------------------------------------------------
def test_ninguna_escena_se_parte_al_armar_los_bloques() -> None:
    """Partir una escena pondría el corte adentro de una frase, que es donde se oye.

    El corte entre bloques cae donde el texto ya respira —el punto final de una
    escena— porque `previous_text` no se puede usar con `eleven_v3` y no hay forma de
    pedirle al modelo que siga la prosodia del bloque anterior.
    """
    escenas = ["a" * 2000, "b" * 2000, "c" * 2000]
    bloques = StillNarrator(FakeVoiceProvider(), bloque_objetivo=3500)._armar_bloques(escenas)

    assert len(bloques) == 3
    for bloque in bloques:
        assert len(set(bloque.replace(" ", ""))) == 1  # ninguna se mezcló ni se cortó


def test_los_bloques_entran_en_el_tope() -> None:
    escenas = [f"Escena {i} " + "palabra " * 60 for i in range(20)]
    bloques = StillNarrator(FakeVoiceProvider(), bloque_objetivo=3500)._armar_bloques(escenas)

    assert all(len(b) <= 3500 for b in bloques)
    assert " ".join(bloques).split() == " ".join(escenas).split()  # no se perdió nada


async def test_un_bloque_que_no_entra_en_un_pedido_falla_con_un_mensaje_claro(
    devocional_largo: Story, tmp_path: Path
) -> None:
    """Antes de gastar, no después.

    Si el bloque objetivo se sube por encima del límite de la API, el error tiene que
    decir qué pasó y cuál es la perilla — no un 400 de ElevenLabs.
    """
    devocional_largo.scenes[0].narration = "x" * (LIMITE_DE_PEDIDO + 100)
    narrador = StillNarrator(FakeVoiceProvider(), bloque_objetivo=LIMITE_DE_PEDIDO + 500)

    with pytest.raises(DomainError, match="máximo por pedido"):
        await narrador.narrate(devocional_largo, tmp_path)


def test_se_puede_saber_el_costo_antes_de_gastarlo(devocional_largo: Story) -> None:
    """Pablo, 8-ago-2026: *"antes de generar algo largo, calculá cuánto cuesta y
    decímelo"*. Con 30.000 caracteres por media hora, estimar mal es un mes de cuota.
    """
    cuenta = caracteres_de(devocional_largo)
    a_mano = (
        len(devocional_largo.metadata.title) + 1  # el punto que se le agrega
        + sum(len(e.narration) for e in devocional_largo.scenes)
        + len(devocional_largo.moral)
        + len(devocional_largo.closing_question)
    )
    assert cuenta == a_mano


# --- El narrador de bloques -------------------------------------------------------
async def test_el_titulo_y_el_cierre_se_piden_SOLOS(
    devocional_largo: Story, tmp_path: Path
) -> None:
    """Sin alineación por caracter, la única forma de saber cuánto dura una frase es
    pedirla sola y medirla — y el render necesita esos dos números para saber cuánto
    dejar el título y cuándo hacer aparecer el pedido de comentario.
    """
    voz = FakeVoiceProvider()
    cuerpo = await StillNarrator(voz).narrate(devocional_largo, tmp_path)

    assert len(devocional_largo.title_audio) == 1
    assert len(devocional_largo.closing_audio) == 1
    assert devocional_largo.metadata.title[:20].lower() in voz.llamadas[0]["text"].lower()
    assert "AMEN" in voz.llamadas[-1]["text"]
    # Las seis escenas entran en un bloque solo: son cortas.
    assert len(cuerpo) == 1
    assert all(Path(t.path).is_file() and t.duration_s > 0 for t in cuerpo)


async def test_la_direccion_de_actuacion_va_en_TODOS_los_bloques(
    devocional_largo: Story, tmp_path: Path
) -> None:
    """Para el modelo cada pedido es un texto nuevo: el bloque 2 sin dirección vuelve a
    leer como un noticiero."""
    voz = FakeVoiceProvider()
    devocional_largo.scenes = [
        e.model_copy(update={"narration": "palabra " * 12}) for e in devocional_largo.scenes
    ]
    await StillNarrator(voz, direccion="[calm]", bloque_objetivo=200).narrate(
        devocional_largo, tmp_path
    )

    assert len(voz.llamadas) > 3
    assert all(x["text"].startswith("[calm]") for x in voz.llamadas)


async def test_el_audio_no_se_cuelga_de_ninguna_escena(
    devocional_largo: Story, tmp_path: Path
) -> None:
    """Un bloque no es una escena. Colgarlo de `scenes[0].audio` dejaría escrito que
    ese archivo es de la primera escena, que es justo lo que no es."""
    await StillNarrator(FakeVoiceProvider()).narrate(devocional_largo, tmp_path)
    assert all(not e.audio for e in devocional_largo.scenes)


# --- El render --------------------------------------------------------------------
async def test_el_mp4_sale_horizontal_y_dura_lo_que_el_audio(
    devocional_largo: Story, tmp_path: Path
) -> None:
    """El único test que mira el producto: se renderiza de verdad y se mide con ffprobe.

    Horizontal y no vertical porque esto no compite en un feed: se deja puesto para
    dormirse o para rezar a la mañana, y se mira en una tele o en un teléfono acostado.
    Los 8 canales del nicho que hacen largo publican en 16:9.
    """
    cuerpo = await StillNarrator(FakeVoiceProvider()).narrate(devocional_largo, tmp_path)
    mp4 = StillRenderer().render(
        devocional_largo,
        tmp_path / "largo.mp4",
        imagen=_png(tmp_path / "fondo.png"),
        cuerpo=cuerpo,
    )

    datos = _ffprobe(mp4)
    video = next(s for s in datos["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1920, 1080)
    assert next(s for s in datos["streams"] if s["codec_type"] == "audio")

    hablado = sum(
        t.duration_s
        for t in [*devocional_largo.title_audio, *cuerpo, *devocional_largo.closing_audio]
    )
    # El video dura lo hablado más la cola. Un segundo de tolerancia: ffmpeg redondea
    # al cuadro y el audio se rellena con `apad`.
    assert abs(float(datos["format"]["duration"]) - (hablado + 1.2)) < 1.0
    assert devocional_largo.status is StoryStatus.RENDERED


async def test_el_titulo_se_va_y_la_invitacion_llega_al_final(
    devocional_largo: Story, tmp_path: Path
) -> None:
    """Los dos textos y sus ventanas, leídos del filtro que se le pasa a ffmpeg.

    El medio va SIN texto a propósito: esto se escucha, muchas veces con los ojos
    cerrados. Es una DECISIÓN, no una medición — de los 14 canales se midió que ninguno
    sube pista de subtítulos, y eso no dice nada sobre texto quemado en el cuadro.

    Y el tratamiento del texto es el que Pablo eligió el 5-ago mirando el primer short
    —*"sólo texto con borde negro"*, sin caja—: se reusa `CONTORNO` de `render/video.py`
    en vez de inventar otro, que es la única forma de que los dos productos se vean de
    la misma familia.
    """
    cuerpo = await StillNarrator(FakeVoiceProvider()).narrate(devocional_largo, tmp_path)
    # La imagen se arma ANTES de espiar: `_png` también invoca a ffmpeg, y el espía se
    # quedaba con esa llamada en vez de con la del render.
    fondo = _png(tmp_path / "fondo.png")
    llamada: dict = {}

    import engine.render.still as modulo

    original = modulo.subprocess.run

    def espiar(cmd, **kw):
        llamada["filtro"] = cmd[cmd.index("-filter_complex") + 1]
        return original(cmd, **kw)

    modulo.subprocess.run = espiar
    try:
        StillRenderer().render(
            devocional_largo, tmp_path / "largo.mp4", imagen=fondo, cuerpo=cuerpo
        )
    finally:
        modulo.subprocess.run = original

    filtro = llamada["filtro"]
    dur_titulo = devocional_largo.title_audio[0].duration_s
    assert f"lte(t,{dur_titulo + COLA_DEL_TITULO_S:.3f})" in filtro
    assert "gte(t," in filtro  # la invitación aparece tarde, no desde el principio
    # El cierre se ancla por donde TERMINA el bloque: la corrección del 7-ago-2026.
    assert "h*0.88-text_h" in filtro
    # El tratamiento que eligió Pablo el 5-ago mirando el primer short —*"sólo texto con
    # borde negro"*, sin caja—: se REUSA `CONTORNO` de `render/video.py` en vez de
    # inventar otro. Es la única forma de que los dos productos se vean de la misma
    # familia, y de que cambiarlo una vez lo cambie en los dos.
    assert "fontcolor=white" in filtro
    assert f"borderw={CONTORNO}" in filtro
    assert "box=" not in filtro


async def test_sin_imagen_no_se_invoca_a_ffmpeg(
    devocional_largo: Story, tmp_path: Path
) -> None:
    """Se llega a este paso con media hora de TTS ya pagada: el error tiene que
    entenderse sin leer treinta líneas de jerga de ffmpeg."""
    cuerpo = await StillNarrator(FakeVoiceProvider()).narrate(devocional_largo, tmp_path)

    with pytest.raises(DomainError, match="No está la imagen"):
        StillRenderer().render(
            devocional_largo, tmp_path / "x.mp4", imagen=tmp_path / "no-existe.png",
            cuerpo=cuerpo,
        )


def test_sin_audio_no_se_invoca_a_ffmpeg(devocional_largo: Story, tmp_path: Path) -> None:
    with pytest.raises(DomainError, match="narrar antes de renderizar"):
        StillRenderer().render(
            devocional_largo, tmp_path / "x.mp4",
            imagen=_png(tmp_path / "fondo.png"), cuerpo=[],
        )


def test_el_vertical_sigue_disponible() -> None:
    """El render fijo es horizontal por defecto, no por imposición: el mismo formato en
    9:16 es un short de imagen fija, que es el otro producto del nicho."""
    assert StillRenderer(aspect=AspectRatio.VERTICAL)._ancho == 1080
