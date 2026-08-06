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
    # las seis escenas + la moraleja + la pregunta de cierre
    assert len(list(tmp_path.glob("*.wav"))) == len(story.scenes) + 2


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


async def test_una_toma_cortada_se_pide_de_nuevo_sola(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Frenar la producción entera por una toma mala es justo lo que no puede pasar
    cuando esto corre solo. Y no alcanza con los reintentos por excepción: una toma
    cortada llega con HTTP 200 y un WAV perfectamente válido."""
    class FallaLaPrimera(FakeVoiceProvider):
        """La primera toma vuelve con una palabra; el resto, enteras."""

        def __init__(self):
            super().__init__()
            self.cortadas = 0

        async def synthesize(self, text, **kw):
            if self.cortadas == 0 and not self.llamadas:
                self.cortadas += 1
                return await super().synthesize("una", **kw)
            return await super().synthesize(text, **kw)

    prov = FallaLaPrimera()
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await StoryNarrator(prov).narrate(story, tmp_path)  # no explota

    assert prov.cortadas == 1
    assert all(t.duration_s > 0 for e in story.scenes for t in e.audio)


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
    from engine.generators.narrator import COLCHON_FINAL

    assert para_decir(escrito) == dicho + COLCHON_FINAL


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
    from engine.generators.narrator import COLCHON_FINAL

    assert para_decir(texto) == texto + COLCHON_FINAL


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



# --- el cierre --------------------------------------------------------------------


async def test_la_moraleja_y_la_pregunta_se_narran(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Existían en el modelo desde el primer día y ningún módulo las usaba: el video
    terminaba en la última palabra del cuento, en seco. Y la pregunta es lo que
    convierte a un espectador en un comentario."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)

    dichos = [t.text for t in story.closing_audio]
    assert dichos == [story.moral, story.closing_question]
    assert all(t.duration_s > 0 for t in story.closing_audio)


async def test_el_cierre_se_dice_con_el_tono_de_la_apertura(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Es el momento en que el narrador le habla al chico, no a la historia."""
    from engine.prompts.voz import APERTURA

    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeVoiceProvider()
    await StoryNarrator(prov).narrate(story, tmp_path)

    del_cierre = [ll for ll in prov.llamadas if story.moral in ll["text"]]
    assert del_cierre and APERTURA in del_cierre[0]["text"]


async def test_una_historia_sin_moraleja_no_inventa_cierre(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    story.moral = ""
    story.closing_question = ""
    await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)
    assert story.closing_audio == []


async def test_marca_la_toma_que_habla_mas_rapido_que_el_resto(
    tmp_path, caplog, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Así se ve una toma cortada desde afuera: el archivo tiene casi todo el largo
    de la frase —así que el piso absoluto no la agarra— pero le falta el final. Lo
    escuchó Pablo: "dice pelotita de colore y es de colores, se corta antes". Esa
    toma iba a 2.99 palabras por segundo y el resto de la historia a 2.38."""

    class UnaSaleCorta(FakeVoiceProvider):
        """A la quinta toma se le come el final: queda por encima del piso —así que
        no se reintenta— pero por debajo de lo que dura decirla entera."""

        async def synthesize(self, text, **kw):
            import re

            if len(self.llamadas) == 4:
                dicho = re.sub(r"\[[^\]]*\]", "", text).split()
                return await super().synthesize(" ".join(dicho[: int(len(dicho) * 0.7)]), **kw)
            return await super().synthesize(text, **kw)

    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    with caplog.at_level("WARNING"):
        await StoryNarrator(UnaSaleCorta()).narrate(story, tmp_path)

    assert "puede haber salido cortada" in caplog.text.lower()


async def test_una_historia_pareja_no_dispara_falsas_alarmas(
    tmp_path, caplog, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Si avisa de todo, no sirve para nada."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    with caplog.at_level("WARNING"):
        await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)
    assert "cortada" not in caplog.text.lower()


def test_el_texto_lleva_un_colchon_para_que_no_se_coma_el_final() -> None:
    """ElevenLabs v3 trunca la última palabra, y siempre la misma: "pelotita de
    colore" en vez de "colores". Medido con la frase exacta: 3,8s tal cual contra
    5,3s con un punto extra. Un punto de más no se pronuncia."""
    from engine.generators.narrator import COLCHON_FINAL

    assert para_decir("Dino saltó.").endswith(COLCHON_FINAL)
    assert "Dino saltó." in para_decir("Dino saltó.")


async def test_el_colchon_no_ensucia_lo_que_queda_guardado(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Es un truco para el proveedor, no parte del cuento: la pista guarda el texto
    tal como se escribió."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await StoryNarrator(FakeVoiceProvider()).narrate(story, tmp_path)

    for escena in story.scenes:
        assert escena.audio[0].text == escena.narration
        assert not escena.audio[0].text.endswith(" .")

async def test_una_toma_que_NACE_CORTADA_se_pide_de_nuevo(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El caso que escuchó Pablo: "el comienzo del video parece que dijera nano salto,
    era dino salto". La toma dura lo que tiene que durar y el proveedor la dio por
    buena — pero empieza encima de la D y se come su explosión.

    Medido sobre las ocho tomas de ese cuento: la mala tenía 0 ms de silencio inicial
    y las siete buenas, entre 222 y 496 ms."""

    class ArrancaEncima(FakeVoiceProvider):
        """La primera toma empieza con sonido en la muestra 0; el resto, normales."""

        def __init__(self) -> None:
            super().__init__()
            self.sin_ataque = 0

        async def synthesize(self, text, **kw):
            audio = await super().synthesize(text, **kw)
            if self.sin_ataque == 0:
                self.sin_ataque += 1
                return _con_sonido_desde_el_principio(audio)
            return audio

    prov = ArrancaEncima()
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await StoryNarrator(prov).narrate(story, tmp_path)  # no explota: la pide de nuevo

    assert prov.sin_ataque == 1
    assert all(t.duration_s > 0 for e in story.scenes for t in e.audio)


def test_el_ataque_se_mide_en_milisegundos() -> None:
    """La medición es lo único que separa esa toma de una buena, así que se testea sola."""
    from engine.generators.narrator import ataque_ms
    from engine.providers.fake import _wav_silencioso

    assert ataque_ms(_con_sonido_desde_el_principio(_wav_silencioso(1.0))) == 0.0
    assert ataque_ms(_wav_silencioso(1.0)) == float("inf")  # todo silencio: no es su tema


def _con_sonido_desde_el_principio(wav: bytes) -> bytes:
    """El mismo WAV pero con sonido fuerte desde la primera muestra."""
    import io
    import struct
    import wave

    with wave.open(io.BytesIO(wav), "rb") as w:
        params, marcos = w.getparams(), w.readframes(w.getnframes())
    ruido = struct.pack(f"<{len(marcos) // 2}h", *([9000] * (len(marcos) // 2)))
    salida = io.BytesIO()
    with wave.open(salida, "wb") as w:
        w.setparams(params)
        w.writeframes(ruido)
    return salida.getvalue()

def test_el_pedido_lleva_un_colchon_ANTES_del_texto() -> None:
    """Para que v3 no arranque encima de la primera consonante: "Dino" sonaba "nano".
    Medido con la misma frase: sin nada delante, entre 0 y 194 ms de silencio inicial
    según la toma; con una coma, 602 ms. Una coma no se pronuncia."""
    from engine.prompts.voz import COLCHON_INICIAL, con_entonacion

    con_etiqueta = con_entonacion("Dino saltó.", "[warmly]")
    assert con_etiqueta == f"[warmly] {COLCHON_INICIAL} Dino saltó."

    # y también cuando la escena no lleva etiqueta de emoción
    assert con_entonacion("Dino saltó.", "") == f"{COLCHON_INICIAL} Dino saltó."
