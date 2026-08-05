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


# --- Regla 5: cada uno con su cara -----------------------------------------------


async def test_el_que_no_comparte_y_el_que_mira_no_ponen_la_misma_cara(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El bug: en la escena del problema, Dino y Rexo salieron con el MISMO ceño
    fruncido y los MISMOS brazos cruzados. El enojado era Dino; Rexo solo quería
    jugar. La emoción era una sola por escena y se aplicaba igual a todos."""
    from engine.core.enums import Emotion

    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    problema = next(e for e in story.scenes if e.beat is NarrativeBeat.PROBLEM)

    assert problema.emotion_for(dino.id) is Emotion.FRUSTRATION
    assert problema.emotion_for(tuca.id) is Emotion.CURIOSITY
    # y el prompt le da a cada uno SU gesto, no dos veces el mismo
    assert "brazos cruzados" in problema.image_prompt
    assert "cuerpo inclinado hacia adelante" in problema.image_prompt
    assert problema.image_prompt.count("brazos cruzados") == 1


async def test_el_protagonista_no_se_repite_en_el_diccionario(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Su emoción ES el tono de la escena. Anotarla otra vez sería una segunda
    fuente de verdad para lo mismo."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    for escena in story.scenes:
        assert dino.id not in escena.character_emotions
        assert escena.emotion_for(dino.id) is escena.emotion


async def test_el_rexo_de_la_burbuja_esta_contento(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Lo imaginado es lo que se está perdiendo: acá triste, allá adentro alegre.
    Si el imaginado heredara el tono de la escena, la burbuja saldría triste y la
    escena no se leería."""
    from engine.core.enums import Emotion

    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    error = next(e for e in story.scenes if e.beat is NarrativeBeat.FAILURE)

    assert error.emotion is Emotion.SADNESS
    assert error.emotion_for(tuca.id) is Emotion.JOY
    assert "hombros hundidos" in error.image_prompt  # Dino, presente
    assert "sonrisa grande" in error.image_prompt  # Rexo, imaginado


def test_todos_los_valores_saben_que_siente_el_companero() -> None:
    """Agregar un valor nuevo sin su curva del compañero deja a los dos personajes
    con la misma cara. Que rompa acá y no en la imagen 40."""
    from engine.core.enums import NarrativeBeat as NB

    for valor, perfil in PROFILES.items():
        faltan = [b.value for b in NB if b not in perfil.companion_emotions]
        assert not faltan, f"{valor.value} no dice qué siente el compañero en {faltan}"


def test_nadie_siente_algo_si_no_esta_en_la_escena() -> None:
    from engine.core.enums import Emotion
    from engine.core.exceptions import InvalidArcError
    from engine.core.models.plan import ScenePlan

    with pytest.raises(InvalidArcError, match="fantasma"):
        ScenePlan(
            index=0, beat=NarrativeBeat.HOOK, purpose="presentar a alguien",
            duration_s=5.0, location="el bosque", character_ids=["dino"],
            emotion=Emotion.JOY, character_emotions={"fantasma": Emotion.FEAR},
        )


def test_la_expresion_propia_del_personaje_le_gana_al_gesto_generico(dino: Character) -> None:
    """`expressions` es el override: un dino que cuando se frustra infla los cachetes."""
    from engine.core.enums import Emotion

    propio = dino.model_copy(update={"expressions": {Emotion.FRUSTRATION: "infla los cachetes"}})
    assert propio.expression_for(Emotion.FRUSTRATION, "ceño fruncido") == "infla los cachetes"
    assert propio.expression_for(Emotion.JOY, "sonrisa grande") == "sonrisa grande"


# --- Que no se repita la misma imagen --------------------------------------------


async def test_el_gancho_y_el_intento_no_dan_la_misma_imagen(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El bug: las dos escenas salieron casi idénticas —el protagonista solo con la
    pelota, mismo encuadre, mismo lugar— porque tenían el mismo elenco y el mismo
    plano medio. Se separan por elenco Y por encuadre."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    gancho = next(e for e in story.scenes if e.beat is NarrativeBeat.HOOK)
    intento = next(e for e in story.scenes if e.beat is NarrativeBeat.ATTEMPT)

    assert gancho.camera.shot is not intento.camera.shot
    assert tuca.id in intento.character_ids  # mira desde lejos
    assert tuca.id not in gancho.character_ids


async def test_el_motor_elige_el_encuadre_de_cada_beat(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Sin esto salen seis planos medios seguidos, que es un video plano."""
    from engine.core.constants import SHOT_BY_BEAT

    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    for escena in story.scenes:
        assert escena.camera.shot is SHOT_BY_BEAT[escena.beat]
        assert image_prompts._ENCUADRE[escena.camera.shot.value] in escena.image_prompt
    assert len({e.camera.shot for e in story.scenes}) > 1


def test_todos_los_beats_tienen_encuadre() -> None:
    from engine.core.constants import SHOT_BY_BEAT

    faltan = [b.value for b in NarrativeBeat if b not in SHOT_BY_BEAT]
    assert not faltan, f"sin encuadre definido: {faltan}"


async def test_en_el_problema_el_companero_mira_el_objeto(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """La narración decía que Rexo miraba la pelota y en la imagen miraba a Dino.
    El gesto genérico no alcanza: hay que decir hacia dónde va la atención."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    problema = next(e for e in story.scenes if e.beat is NarrativeBeat.PROBLEM)

    assert tuca.name in problema.visual_note
    assert "mira" in problema.visual_note
    assert problema.visual_note in problema.image_prompt


async def test_el_plano_corto_no_pide_tambien_la_escena_completa(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El bug: el aprendizaje salía tan abierto como el resto. El prompt pedía "las
    caras llenan el cuadro" Y "escena completa con los personajes apoyados en el
    suelo". Cuando dos instrucciones se pelean, el modelo elige una."""
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    corto = next(e for e in story.scenes if e.beat is NarrativeBeat.LESSON)

    assert "CÁMARA CERCA" in corto.image_prompt
    assert "apoyados en el suelo" not in corto.image_prompt
    # pero el fondo se sigue pidiendo: sin eso los personajes flotan en blanco
    assert "nunca fondo liso" in corto.image_prompt


def test_todos_los_encuadres_dicen_como_va_el_fondo() -> None:
    """Un encuadre sin entrada acá rompe con KeyError, que es lo que queremos: si se
    agrega un plano nuevo hay que pensar qué se ve detrás."""
    from engine.core.enums import ShotType

    faltan = [s.value for s in ShotType if s not in image_prompts._FONDO]
    assert not faltan, f"sin instrucción de fondo: {faltan}"


async def test_ninguna_escena_pide_dos_cosas_opuestas(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await _historia(tema_dinos, estilo_3d, dino, tuca)
    for escena in story.scenes:
        cerca = "CÁMARA CERCA" in escena.image_prompt
        lejos = "escena COMPLETA" in escena.image_prompt
        assert cerca != lejos, f"escena {escena.index} pide las dos cosas"
