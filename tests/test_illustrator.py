"""El ilustrador y su mecanismo de anclas.

Lo que se prueba no es la imagen —no se puede evaluar en un test— sino que cada
escena RECIBA las referencias correctas. Ahí se juega la consistencia visual, y es
verificable de forma determinista.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.core.enums import EducationalValue, StoryStatus
from engine.core.exceptions import DomainError
from engine.core.models import Character, Style, Theme
from engine.engine import StoryEngine
from engine.generators.illustrator import SceneIllustrator
from engine.providers.fake import FakeImageProvider, FakeTextProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _historia_escrita(tema: Theme, estilo: Style, dino: Character, tuca: Character):
    motor = StoryEngine(text_provider=FakeTextProvider())
    return await motor.generate(
        theme=tema, style=estilo, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )


async def test_ilustra_todas_las_escenas(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _historia_escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path)

    assert len(prov.llamadas) == len(story.scenes)
    assert all(e.image_path for e in story.scenes)
    assert all(Path(e.image_path).is_file() for e in story.scenes)
    assert story.status is StoryStatus.ILLUSTRATED


async def test_la_primera_escena_no_tiene_ancla_de_personaje(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Nadie fue dibujado todavía: no hay de dónde copiar."""
    story = await _historia_escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path)
    assert prov.llamadas[0]["refs"] == []


async def test_las_escenas_siguientes_reciben_el_ancla(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """ESTE es el test que importa: sin esto el protagonista muta entre escenas."""
    story = await _historia_escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path)

    primera = prov.llamadas[0]
    # todas las llamadas posteriores llevan al menos una referencia
    assert all(c["refs"] for c in prov.llamadas[1:])
    # y la referencia del protagonista es EXACTAMENTE la primera imagen generada
    imagen_ancla = FakeImageProvider.PNG + b"1"
    assert any(imagen_ancla in c["refs"] for c in prov.llamadas[1:])
    assert primera["refs"] == []


async def test_el_ancla_de_un_personaje_es_su_primera_aparicion(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _historia_escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path)

    # la escena donde aparece el compañero por primera vez
    idx_companero = next(i for i, e in enumerate(story.scenes) if tuca.id in e.character_ids)
    # a partir de ahí, las escenas con el compañero llevan DOS anclas (prota + compa)
    posteriores = [
        c
        for e, c in zip(story.scenes, prov.llamadas, strict=True)
        if tuca.id in e.character_ids and e.index > idx_companero
    ]
    assert all(len(c["refs"]) >= 2 for c in posteriores)


async def test_el_ancla_de_estilo_va_siempre_y_primero(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El estilo marca el 'cómo se dibuja'; va antes que el 'quién es'."""
    ref = tmp_path / "estilo.png"
    ref.write_bytes(FakeImageProvider.PNG + b"ESTILO")
    estilo = estilo_3d.model_copy(update={"reference_image": str(ref)})

    story = await _historia_escrita(tema_dinos, estilo, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path / "out")

    assert all(c["refs"] and c["refs"][0] == ref.read_bytes() for c in prov.llamadas)


async def test_un_estilo_sin_referencia_no_rompe_nada(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Que falte el ancla de estilo pierde el ancla, no la historia."""
    estilo = estilo_3d.model_copy(update={"reference_image": "/no/existe.png"})
    story = await _historia_escrita(tema_dinos, estilo, dino, tuca)
    await SceneIllustrator(FakeImageProvider()).illustrate(story, tmp_path)
    assert all(e.image_path for e in story.scenes)


async def test_el_negativo_viaja_en_el_prompt(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _historia_escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path)
    assert all("EVITAR:" in c["prompt"] for c in prov.llamadas)
    # lo propio del estilo y lo que nunca queremos, juntos
    assert all("realismo fotográfico" in c["prompt"] for c in prov.llamadas)
    assert all("marca de agua" in c["prompt"] for c in prov.llamadas)


async def test_el_formato_vertical_es_el_default(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El caso de uso principal son shorts: 9:16."""
    story = await _historia_escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path)
    assert all(c["size"] == (1024, 1536) for c in prov.llamadas)


async def test_ilustrar_sin_escenas_avisa_bien(historia) -> None:
    with pytest.raises(DomainError, match="no tiene escenas"):
        await SceneIllustrator(FakeImageProvider()).illustrate(historia, "/tmp/x")


async def test_una_escena_sin_prompt_no_se_ilustra_a_ciegas(
    tmp_path: Path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Ilustrar sin prompt compuesto daría una imagen que no corresponde a nada."""
    story = await _historia_escrita(tema_dinos, estilo_3d, dino, tuca)
    story.scenes[0].image_prompt = ""
    with pytest.raises(DomainError, match="no tiene prompt de imagen"):
        await SceneIllustrator(FakeImageProvider()).illustrate(story, tmp_path)
