"""El narrador: le pone voz a la historia y mide cuánto dura.

Todo corre contra un proveedor falso que devuelve WAV de verdad, con la duración que
le correspondería al texto. Eso permite probar el guardián de duración —el caso que
importa— sin gastar en TTS.

Varios de estos tests existen por bugs reales de los audiolibros de
Casatridimensional, que usan el mismo proveedor. Están anotados uno por uno.
"""

from __future__ import annotations

import wave

import pytest

from engine.core.enums import AudioKind, EducationalValue, StoryStatus
from engine.core.exceptions import DomainError, ProviderError
from engine.core.models import Character, Style, Theme
from engine.core.models.character import Voice
from engine.core.models.scene import DialogueLine
from engine.engine import StoryEngine
from engine.generators.narrator import (
    StoryNarrator,
    duracion_de_wav,
    para_decir,
    tasa_real,
)
from engine.providers.fake import FakeTextProvider, FakeVoiceProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _escrita(tema, estilo, dino, tuca):
    return await StoryEngine(text_provider=FakeTextProvider()).generate(
        theme=tema, style=estilo, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )


# --- el camino feliz -------------------------------------------------------------


async def test_narra_todas_las_escenas(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    story = await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)

    assert story.status is StoryStatus.NARRATED
    assert all(e.audio for e in story.scenes)
    assert all(t.duration_s > 0 for e in story.scenes for t in e.audio)
    assert len(list(tmp_path.glob("*.wav"))) == len(story.scenes)


async def test_la_duracion_se_MIDE_del_archivo(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El corazón del módulo: no se estima, se abre el WAV y se lee."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)

    for escena in story.scenes:
        for pista in escena.audio:
            with wave.open(pista.path, "rb") as w:
                real = w.getnframes() / w.getframerate()
            assert abs(pista.duration_s - real) < 0.01


async def test_el_render_usa_la_duracion_real_y_no_la_del_plan(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Si el render usa la del plan, la imagen cambia antes de que termine la frase."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    antes = [e.real_duration_s for e in story.scenes]
    assert antes == [e.duration_s for e in story.scenes]  # sin audio, manda el plan

    await StoryNarrator(FakeVoiceProvider(palabras_por_s=1.5)).narrate(story, tmp_path)
    for escena in story.scenes:
        assert escena.real_duration_s == escena.audio_duration_s
        assert escena.real_duration_s != escena.duration_s


# --- las voces -------------------------------------------------------------------


async def test_la_narracion_la_lee_el_narrador_no_un_personaje(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Quien cuenta el cuento no está adentro del cuento."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)

    for escena in story.scenes:
        narracion = escena.audio[0]
        assert narracion.kind is AudioKind.NARRATION
        assert narracion.character_id is None
        assert narracion.text == escena.narration


async def test_el_dialogo_hablado_lo_dice_su_personaje(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    con_voz = tuca.model_copy(update={"voice": Voice(provider_voice_id="voz-de-rexo")})
    story.characters[1].character = con_voz
    story.scenes[1].dialogue = [DialogueLine(character_id=tuca.id, text="¿Puedo jugar?")]

    prov = FakeVoiceProvider()
    await StoryNarrator(prov).narrate(story, tmp_path)

    dialogo = story.scenes[1].audio[1]
    assert dialogo.kind is AudioKind.DIALOGUE
    assert dialogo.character_id == tuca.id
    assert dialogo.voice_id == "voz-de-rexo"
    assert any(ll["voice_id"] == "voz-de-rexo" for ll in prov.llamadas)


async def test_el_globo_que_solo_se_lee_no_se_sintetiza(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """`spoken=False` es un globo en pantalla: se LEE, no se dice. Sintetizarlo
    sería pagar por audio que nadie escucha y desincronizar el video."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    story.scenes[1].dialogue = [
        DialogueLine(character_id=tuca.id, text="¿Puedo jugar?", spoken=False)
    ]
    await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)

    assert len(story.scenes[1].audio) == 1
    assert story.scenes[1].audio[0].kind is AudioKind.NARRATION


async def test_no_puede_hablar_alguien_que_no_esta_en_el_elenco(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    story.scenes[1].dialogue = [DialogueLine(character_id="fantasma", text="hola")]
    with pytest.raises(DomainError, match="fantasma"):
        await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)


# --- el guardián de duración -----------------------------------------------------


async def test_una_toma_cortada_no_pasa(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """EL error más caro: cuando el TTS devuelve la mitad del audio no falla —
    devuelve un WAV válido, más corto. El archivo existe, el pipeline sigue, y el
    problema se descubre escuchando el producto terminado."""

    class DevuelveLaMitad(FakeVoiceProvider):
        async def synthesize(self, text, **kw):
            # se corta lo que se DICE, no la dirección de actuación
            import re

            dicho = re.sub(r"\[[^\]]*\]", "", text).split()
            return await super().synthesize(" ".join(dicho[: max(1, len(dicho) // 4)]), **kw)

    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    with pytest.raises(ProviderError, match="cortada"):
        await StoryNarrator(DevuelveLaMitad()).narrate(story, tmp_path)


async def test_una_voz_lenta_avisa_pero_no_frena(
    tmp_path, caplog, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Apurar la voz para que entre suena peor que la escena un poco más larga. El
    narrador deja rastro y el render decide."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    with caplog.at_level("WARNING"):
        await StoryNarrator(FakeVoiceProvider(palabras_por_s=1.2)).narrate(story, tmp_path)

    assert story.status is StoryStatus.NARRATED
    assert "el audio dura" in caplog.text


async def test_la_tasa_real_se_puede_medir(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Si todas las escenas se pasan, el problema no es de una escena: es que la
    constante con la que escribe el escritor no coincide con la voz. Esto permite
    ajustarla con un número medido en vez de con intuición."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await StoryNarrator(FakeVoiceProvider(palabras_por_s=2.08)).narrate(story, tmp_path)

    assert abs(tasa_real(story) - 2.08) < 0.05


async def test_narrar_sin_escenas_avisa_bien(historia) -> None:
    with pytest.raises(DomainError, match="antes de narrarla"):
        await StoryNarrator(FakeVoiceProvider()).narrate(historia, "/tmp/nada")


async def test_narrar_sin_proveedor_avisa_bien(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    with pytest.raises(RuntimeError, match="no tiene proveedor de voz"):
        await StoryEngine().narrate(story, "/tmp/nada")


# --- el texto que se dice no es el que se ve -------------------------------------


@pytest.mark.parametrize(
    ("escrito", "dicho"),
    [
        ("«Dino miró el cielo»", "Dino miró el cielo"),  # se leía como ">>"
        ("**Dino** saltó", "Dino saltó"),
        ("Dino  saltó   feliz", "Dino saltó feliz"),
    ],
)
def test_limpia_lo_que_se_lee_mal_en_voz_alta(escrito: str, dicho: str) -> None:
    """Las comillas angulares las lee como ">>" — pasó en los audiolibros."""
    assert para_decir(escrito) == dicho


@pytest.mark.parametrize(
    "texto",
    [
        "Y entonces… ¡apareció!",
        "Había una vez... un dino chiquitito",
        "¿Sabés qué pasó? ¡Se perdió!",
        "—¡Ay, no! —gritó Toti",
    ],
)
def test_no_toca_lo_que_marca_el_RITMO(texto: str) -> None:
    """Los puntos suspensivos hacen que el modelo tome aire, y los signos de
    exclamación le levantan el tono. Son la herramienta principal para que un cuento
    no suene a noticiero. Este código los borraba: aplanaba justo lo que hay que
    exagerar."""
    assert para_decir(texto) == texto


async def test_el_subtitulo_conserva_la_puntuacion_linda(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Limpiar para el TTS no puede ensuciar lo que se ve en pantalla."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    story.scenes[0].narration = "«Dino» saltó feliz."
    story.scenes[0].subtitle = "«Dino» saltó feliz."

    prov = FakeVoiceProvider()
    await StoryNarrator(prov).narrate(story, tmp_path)

    assert "«" not in prov.llamadas[0]["text"]  # lo que se dice
    assert "«" in story.scenes[0].subtitle  # lo que se ve


# --- medir --------------------------------------------------------------------


def test_medir_un_wav_de_duracion_conocida() -> None:
    from engine.providers.fake import _wav_silencioso

    assert duracion_de_wav(_wav_silencioso(2.5)) == pytest.approx(2.5, abs=0.01)


# --- el tiempo no se cuenta solo en palabras -------------------------------------


def test_al_escritor_se_le_prohibe_el_dialogo_entrecomillado() -> None:
    """MEDIDO contra ElevenLabs (5-ago-2026): la misma idea narrada tarda 2.90 pal/s
    sin comillas y 1.72 con comillas — un 68% más. El modelo ACTÚA el diálogo, con
    pausas y cambio de tono. Una escena real se pasó +54% por esto.

    Y no hace falta: para el diálogo está `DialogueLine`, que además le pone la voz
    del personaje en vez de la del narrador.
    """
    from engine.core.enums import AgeRange, Language
    from engine.prompts.narration import system_prompt

    prompt = system_prompt(
        language=Language.ES_AR, age_range=AgeRange.PRESCHOOL, value_moral="compartir"
    )
    assert "NO escribas diálogo entrecomillado" in prompt


def test_la_concurrencia_respeta_el_limite_del_plan() -> None:
    """Medido: con 4 en paralelo ElevenLabs devuelve 429 "maximum of 3 concurrent
    requests". Se recupera con reintentos, pero es tiempo y cuota tirados."""
    from engine.generators.narrator import CONCURRENCIA

    assert CONCURRENCIA <= 3


def test_al_escritor_se_le_pide_que_escriba_para_leer_en_voz_alta() -> None:
    """La receta de cuento infantil de Pablo (5-jul-2026): los puntos suspensivos
    hacen tomar aire, las exclamaciones levantan el tono y los diminutivos suavizan.
    Sin eso el modelo lee como un noticiero, aunque la voz sea buena."""
    from engine.core.enums import AgeRange, Language
    from engine.prompts.narration import system_prompt

    prompt = system_prompt(
        language=Language.ES_AR, age_range=AgeRange.PRESCHOOL, value_moral="compartir"
    )
    assert "SE LEA EN VOZ ALTA" in prompt
    assert "Puntos suspensivos" in prompt


def test_la_direccion_de_actuacion_va_en_toda_escena() -> None:
    """Sin el contexto de "esto es un cuento infantil argentino", el modelo lee
    plano. Es la diferencia entre una voz buena y una narración."""
    from engine.core.enums import Emotion, NarrativeBeat
    from engine.prompts.voz import DIRECCION, direccion_de_escena

    primera = direccion_de_escena(NarrativeBeat.HOOK, Emotion.CURIOSITY, es_primera=True)
    otra = direccion_de_escena(NarrativeBeat.FAILURE, Emotion.SADNESS, es_primera=False)

    assert DIRECCION in primera and DIRECCION in otra
    assert "[warmly] [slows down]" in primera  # la apertura, confirmada al oído
    assert "[sadly]" in otra
