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

from engine.core.enums import AspectRatio, StoryStatus
from engine.core.exceptions import DomainError
from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.generators.still_narrator import (
    LIMITE_DE_PEDIDO,
    StillNarrator,
    caracteres_de,
)
from engine.providers.fake import FakeVoiceProvider
from engine.render.still import COLA_DEL_TITULO_S, StillRenderer

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
    cerrados, y un cartel que cambia cada quince segundos es lo que impide que alguien
    se duerma con esto puesto. Ninguno de los 14 canales del nicho sube subtítulos.
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
