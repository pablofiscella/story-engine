"""No pagar dos veces por lo mismo.

El caso real: se pagaron 27 imágenes para las 6 que quedaron en el producto, porque
cada corrección rehacía la historia entera.

Y el caso contrario, que es peor: un caché que ignora un parámetro no falla —
devuelve algo viejo con cara de nuevo. Pasó con el TTS de Casatridimensional, cuyo
caché no llevaba la voz en la clave: se cambió la voz por defecto y los videos
"nuevos" siguieron sonando con la anterior.
"""

from __future__ import annotations

import pytest

from engine.core.enums import EducationalValue
from engine.core.models import Character, Style, Theme
from engine.engine import StoryEngine
from engine.generators.illustrator import SceneIllustrator
from engine.generators.narrator import StoryNarrator
from engine.providers.cache import CachedImageProvider, CachedVoiceProvider
from engine.providers.fake import FakeImageProvider, FakeTextProvider, FakeVoiceProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _escrita(tema, estilo, dino, tuca):
    return await StoryEngine(text_provider=FakeTextProvider()).generate(
        theme=tema, style=estilo, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )


# --- lo que ahorra ---------------------------------------------------------------


async def test_el_mismo_pedido_no_se_paga_dos_veces(tmp_path) -> None:
    interno = FakeImageProvider()
    cache = CachedImageProvider(interno, tmp_path)

    a = await cache.generate_image("un dino verde", width=1024, height=1536)
    b = await cache.generate_image("un dino verde", width=1024, height=1536)

    assert a == b
    assert len(interno.llamadas) == 1  # el proveedor real se llamó UNA vez
    assert (cache.hits, cache.misses) == (1, 1)


async def test_rehacer_una_escena_no_vuelve_a_pagar_las_otras(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """EL caso que costó 4,5x: se corregía la escena 4 y se pagaban las seis."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    interno = FakeImageProvider()
    cache = CachedImageProvider(interno, tmp_path / "cache")

    await SceneIllustrator(cache).illustrate(story, tmp_path / "1")
    primera_vuelta = len(interno.llamadas)
    assert primera_vuelta == len(story.scenes)

    # se corrige UNA escena y se vuelve a ilustrar todo
    story.scenes[4].image_prompt += " EXTRA: se ofrecen la pelota mirándose a los ojos"
    await SceneIllustrator(cache).illustrate(story, tmp_path / "2")

    assert len(interno.llamadas) == primera_vuelta + 1  # solo la que cambió
    assert cache.hits == len(story.scenes) - 1


async def test_tambien_ahorra_en_la_voz(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El TTS se paga por caracter: rehacer una historia pagaba las seis narraciones."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    interno = FakeVoiceProvider()
    cache = CachedVoiceProvider(interno, tmp_path / "cache")

    await StoryNarrator(cache).narrate(story, tmp_path / "1")
    await StoryNarrator(cache).narrate(story, tmp_path / "2")

    tomas = len(story.scenes) + 2  # las escenas + moraleja + pregunta de cierre
    assert len(interno.llamadas) == tomas  # la segunda vuelta fue gratis
    assert cache.hits == tomas


async def test_dice_cuanto_ahorro(tmp_path) -> None:
    """Una promesa de ahorro sin número no sirve para decidir nada."""
    cache = CachedImageProvider(FakeImageProvider(), tmp_path)
    for _ in range(4):
        await cache.generate_image("igual")
    assert "3 de 4" in cache.ahorro and "75%" in cache.ahorro


# --- lo que NO puede confundir ---------------------------------------------------


async def test_otra_voz_es_otro_audio(tmp_path) -> None:
    """EL bug del caché viejo: sin la voz en la clave, cambiar la voz por defecto
    devolvía los audios de la anterior como si fueran nuevos."""
    interno = FakeVoiceProvider()
    cache = CachedVoiceProvider(interno, tmp_path)

    await cache.synthesize("Dino saltó feliz.", voice_id="valeria")
    await cache.synthesize("Dino saltó feliz.", voice_id="lizy")

    assert len(interno.llamadas) == 2
    assert cache.hits == 0


async def test_otro_modelo_es_otro_resultado(tmp_path) -> None:
    class ConFirma(FakeVoiceProvider):
        def __init__(self, firma):
            super().__init__()
            self.cache_fingerprint = firma

    a, b = ConFirma("eleven_v3"), ConFirma("eleven_multilingual_v2")
    await CachedVoiceProvider(a, tmp_path).synthesize("hola")
    await CachedVoiceProvider(b, tmp_path).synthesize("hola")

    assert len(a.llamadas) == 1 and len(b.llamadas) == 1


async def test_otra_ancla_es_otra_imagen(tmp_path) -> None:
    """La misma escena con otro personaje de referencia da otra imagen. Devolver la
    vieja rompería justamente lo que las anclas vienen a garantizar."""
    interno = FakeImageProvider()
    cache = CachedImageProvider(interno, tmp_path)

    await cache.generate_image("la escena", reference_images=[b"ancla-dino"])
    await cache.generate_image("la escena", reference_images=[b"ancla-rexo"])

    assert len(interno.llamadas) == 2


async def test_otro_tamano_es_otra_imagen(tmp_path) -> None:
    """Un short es 9:16 y un libro es A4: no es la misma imagen recortada."""
    interno = FakeImageProvider()
    cache = CachedImageProvider(interno, tmp_path)

    await cache.generate_image("la escena", width=1024, height=1536)
    await cache.generate_image("la escena", width=1024, height=1024)

    assert len(interno.llamadas) == 2


def test_los_proveedores_reales_declaran_su_firma() -> None:
    """Sin firma, el caché no puede distinguir un modelo de otro."""
    from engine.providers.elevenlabs import ElevenLabsProvider
    from engine.providers.openai import OpenAIProvider

    assert "gpt-image-2" in OpenAIProvider("k").cache_fingerprint
    # v2 y no v3: v3 deformaba la primera palabra de cada tramo y no acepta `previous_text`.
    assert "eleven_multilingual_v2" in ElevenLabsProvider("k").cache_fingerprint
    assert ElevenLabsProvider("k", stability=0.5).cache_fingerprint != (
        ElevenLabsProvider("k", stability=0.75).cache_fingerprint
    )
