"""Las reglas duras del prompt de imagen.

Las tres salieron de mirar un cuento ilustrado real que salió mal (Pablo, 05-ago-2026).
Cada test acá corresponde a un error concreto que se vio en una imagen, y existe para
que no vuelva.
"""

from __future__ import annotations

import pytest

from engine.core.enums import EducationalValue, NarrativeBeat
from engine.core.models import Character, Style, Theme
from engine.engine import StoryEngine
from engine.generators.values import PROFILES
from engine.prompts import image as image_prompts
from engine.providers.fake import FakeTextProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _historia(tema, estilo, dino, tuca, valor=EducationalValue.SHARING):
    motor = StoryEngine(text_provider=FakeTextProvider())
    return await motor.generate(
        theme=tema, style=estilo, value=valor, age=4, duration_s=30.0,
        characters=[dino, tuca],
    )


# --- Regla 1: elenco cerrado -----------------------------------------------------


def test_ningun_proposito_dice_los_dos_sin_nombrarlos() -> None:
    """El bug: la escena final decía "los dos juegan juntos" pero el plan tenía UN
    personaje, así que el prompt describía a uno solo y el modelo completó el elenco
    con un dinosaurio del fondo de la imagen de referencia."""
    for valor, perfil in PROFILES.items():
        for beat, texto in perfil.purposes.items():
            if "los dos" in texto.lower():
                assert "{companero}" in texto, (
                    f"{valor.value}/{beat.value} habla de dos personajes sin nombrar al "
                    f"compañero: el planificador no puede saber a quién sumar al elenco."
                )


async def test_el_final_siempre_incluye_al_companero(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    final = story.scenes[-1]
    assert final.beat is NarrativeBeat.ENDING
    assert tuca.id in final.character_ids


async def test_el_prompt_declara_cuantos_personajes_hay(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    for escena in story.scenes:
        n = len(escena.character_ids)
        assert f"EXACTAMENTE {n} personaje" in escena.image_prompt
        assert "No agregues ningún otro personaje" in escena.image_prompt


async def test_el_prompt_nombra_a_todos_los_presentes(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    nombres = story.characters_by_id
    for escena in story.scenes:
        for cid in escena.character_ids:
            assert nombres[cid].name in escena.image_prompt


def test_el_negativo_prohibe_los_personajes_de_mas(estilo_3d: Style) -> None:
    neg = image_prompts.negative(estilo_3d)
    assert "personajes de más" in neg
    assert "animales de fondo con cara o actitud de personaje" in neg


# --- Regla 2: continuidad de escenario -------------------------------------------


async def test_el_prompt_pide_el_mismo_clima_en_toda_la_historia(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El bug: la escena del error salió nublada porque la emoción era tristeza. La
    historia nunca dijo que se nublara."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    for escena in story.scenes:
        assert "MISMO clima" in escena.image_prompt
        assert "nunca en el clima" in escena.image_prompt


def test_ninguna_emocion_pide_cambios_de_clima() -> None:
    """La emoción se muestra en la cara y el cuerpo, no en el cielo."""
    from engine.core.enums import Emotion

    prohibidas = ("cielo", "nublado", "gris", "atardecer", "lluvia", "tonos fríos")
    for emocion in Emotion:
        actitud = image_prompts._actitud(emocion).lower()
        for palabra in prohibidas:
            assert palabra not in actitud, f"{emocion.value} toca el clima: '{actitud}'"


# --- Regla 3: la imagen ilustra lo que se narra ----------------------------------


async def test_el_prompt_usa_la_narracion_y_no_la_orden_interna(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El bug: el prompt decía "Rexo quiere jugar y Dino se niega" (la orden del
    motor) y el modelo dibujó a Rexo sacándole la pelota, cuando la narración decía
    que solo la miraba."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    for escena in story.scenes:
        assert escena.narration in escena.image_prompt


# --- Dirección de arte -----------------------------------------------------------


async def test_el_error_de_compartir_lleva_burbuja_de_pensamiento(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Idea de Pablo: en el error no alcanza con que esté triste — se entiende mucho
    mejor si se lo ve imaginando lo que se pierde."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    error = next(e for e in story.scenes if e.beat is NarrativeBeat.FAILURE)
    assert "burbuja de pensamiento" in error.visual_note
    assert tuca.name in error.visual_note
    assert "burbuja de pensamiento" in error.image_prompt


async def test_la_nota_visual_funciona_sin_companero(
    tema_dinos: Theme, estilo_3d: Style, dino: Character
) -> None:
    motor = StoryEngine(text_provider=FakeTextProvider())
    story = await motor.generate(
        theme=tema_dinos, style=estilo_3d, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino],
    )
    error = next(e for e in story.scenes if e.beat is NarrativeBeat.FAILURE)
    assert "{" not in error.visual_note


# --- Regla 4: nombrado es descrito -----------------------------------------------


async def test_el_personaje_de_la_burbuja_tambien_se_describe(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El bug: la nota visual decía "se imagina jugando con Rexo", pero Rexo no
    estaba descrito en el prompt (no está "en" la escena). El modelo lo dibujó
    violeta en vez de azul. Nombrado sin describir = inventado."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    error = next(e for e in story.scenes if e.beat is NarrativeBeat.FAILURE)

    assert tuca.id in error.imagined_character_ids
    assert tuca.id not in error.character_ids  # no está presente, se lo imagina
    # pero SÍ está descrito, con su descripción canónica
    assert tuca.appearance.prompt_fragment() in error.image_prompt
    assert "solo dentro de la burbuja" in error.image_prompt
    # y el conteo de presentes no lo incluye
    assert "EXACTAMENTE 1 personaje" in error.image_prompt


async def test_el_imaginado_no_puede_estar_fuera_del_elenco(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    from engine.core.exceptions import UnknownCharacterError

    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    story.scenes[0].imagined_character_ids = ["fantasma"]
    with pytest.raises(UnknownCharacterError, match="fantasma"):
        story.model_validate(story.model_dump())


async def test_el_ilustrador_pasa_el_ancla_del_imaginado(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Sin su ancla, el Rexo de la burbuja no se parece al Rexo real."""
    from engine.generators.illustrator import SceneIllustrator
    from engine.providers.fake import FakeImageProvider

    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    prov = FakeImageProvider()
    await SceneIllustrator(prov).illustrate(story, tmp_path)

    idx = next(e.index for e in story.scenes if e.beat is NarrativeBeat.FAILURE)
    # en esa escena hay 1 presente pero 2 anclas: la de Dino y la de Rexo imaginado
    assert len(prov.llamadas[idx]["refs"]) >= 2
