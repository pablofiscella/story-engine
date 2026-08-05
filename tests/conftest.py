"""Fixtures compartidas: una historia mínima pero VÁLIDA sobre la que probar todo."""

from __future__ import annotations

import pytest

from engine.core.enums import (
    CharacterRole,
    EducationalValue,
    Emotion,
    NarrativeBeat,
)
from engine.core.models import (
    Appearance,
    Character,
    Palette,
    Scene,
    ScenePlan,
    Story,
    StoryCharacter,
    StoryPlan,
    Style,
    Theme,
)


@pytest.fixture
def dino() -> Character:
    return Character(
        id="dino-rex",
        name="Dino",
        appearance=Appearance(
            species="dinosaurio T-Rex bebé",
            description="pequeño, cabezón, ojos grandes y amistosos",
            colors=["verde menta", "amarillo"],
            distinctive_features=["una hoja siempre pegada en la cola"],
        ),
        personality=["curioso", "impaciente"],
        expressions={Emotion.CURIOSITY: "cabeza ladeada y ojos bien abiertos"},
    )


@pytest.fixture
def tuca() -> Character:
    return Character(
        id="tuca-tucan",
        name="Tuca",
        appearance=Appearance(
            species="tucán",
            description="pico enorme de colores, plumas negras brillantes",
            colors=["negro", "naranja"],
        ),
    )


@pytest.fixture
def estilo_3d() -> Style:
    return Style(
        id="pixar-3d",
        name="Animación 3D",
        art_style="animación 3D colorida estilo Pixar, personajes tiernos y expresivos",
        lighting="luz cálida, ambientes vivos",
        color_treatment="colores saturados",
        negative_prompt="texto, marcas de agua, realismo fotográfico, terror",
    )


@pytest.fixture
def tema_dinos() -> Theme:
    return Theme(
        id="dinosaurios",
        name="Dinosaurios",
        description="Un valle prehistórico lleno de helechos gigantes.",
        palette=Palette(primary="#2E7D32", secondary="#FFB300", accent="#D84315"),
        locations=["el claro de los helechos", "la laguna tibia"],
        character_ids=["dino-rex", "tuca-tucan"],
        default_style_id="pixar-3d",
    )


@pytest.fixture
def plan_valido() -> StoryPlan:
    """Arco completo de 6 escenas / 30s — el caso canónico."""
    beats = [
        (NarrativeBeat.HOOK, "Presentar a Dino y su curiosidad", Emotion.CURIOSITY),
        (
            NarrativeBeat.PROBLEM,
            "Dino encuentra una sola fruta y no quiere compartirla",
            Emotion.FRUSTRATION,
        ),
        (NarrativeBeat.ATTEMPT, "Dino intenta comerla solo y a escondidas", Emotion.FEAR),
        (NarrativeBeat.FAILURE, "La fruta se cae al agua y se pierde", Emotion.SADNESS),
        (NarrativeBeat.LESSON, "Tuca comparte la suya y Dino entiende", Emotion.SURPRISE),
        (NarrativeBeat.ENDING, "Los dos comen juntos y felices", Emotion.JOY),
    ]
    return StoryPlan(
        target_duration_s=30.0,
        scenes=[
            ScenePlan(
                index=i,
                beat=beat,
                purpose=purpose,
                duration_s=5.0,
                location="el claro de los helechos",
                character_ids=["dino-rex"] if i < 4 else ["dino-rex", "tuca-tucan"],
                emotion=emotion,
            )
            for i, (beat, purpose, emotion) in enumerate(beats)
        ],
    )


@pytest.fixture
def historia(
    dino: Character,
    tuca: Character,
    tema_dinos: Theme,
    estilo_3d: Style,
    plan_valido: StoryPlan,
) -> Story:
    return Story(
        theme=tema_dinos,
        style=estilo_3d,
        value=EducationalValue.SHARING,
        characters=[
            StoryCharacter(character=dino, role=CharacterRole.PROTAGONIST),
            StoryCharacter(character=tuca, role=CharacterRole.COMPANION),
        ],
        plan=plan_valido,
    )


@pytest.fixture
def escena(plan_valido: StoryPlan) -> Scene:
    return Scene.from_plan(
        plan_valido.scenes[0], narration="Dino asomó la cabeza entre los helechos."
    )
