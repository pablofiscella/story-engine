"""`Story` como raíz: consistencia del elenco, ciclo de vida y multi-formato."""

from __future__ import annotations

import pytest

from engine.core.enums import (
    AspectRatio,
    Channel,
    CharacterRole,
    EducationalValue,
    NarrativeBeat,
    OutputKind,
    StoryStatus,
)
from engine.core.exceptions import InvalidStateTransitionError, UnknownCharacterError
from engine.core.models import (
    Character,
    DialogueLine,
    Output,
    Publication,
    Scene,
    Story,
    StoryCharacter,
    StoryPlan,
    Style,
    Theme,
)

# --- consistencia del elenco (la validación que sostiene la calidad visual) ------


def test_una_escena_no_puede_usar_un_personaje_fuera_del_elenco(
    dino: Character, tema_dinos: Theme, estilo_3d: Style, plan_valido: StoryPlan
) -> None:
    escena_intrusa = Scene.from_plan(plan_valido.scenes[0], narration="Apareció alguien.")
    escena_intrusa.character_ids = ["fantasma-01"]

    with pytest.raises(UnknownCharacterError, match="fantasma-01"):
        Story(
            theme=tema_dinos,
            style=estilo_3d,
            value=EducationalValue.SHARING,
            characters=[StoryCharacter(character=dino, role=CharacterRole.PROTAGONIST)],
            scenes=[escena_intrusa],
        )


def test_el_dialogo_tambien_valida_el_elenco(
    dino: Character, tema_dinos: Theme, estilo_3d: Style, plan_valido: StoryPlan
) -> None:
    escena = Scene.from_plan(
        plan_valido.scenes[0],
        narration="Alguien habló.",
        dialogue=[DialogueLine(character_id="voz-misteriosa", text="hola")],
    )
    with pytest.raises(UnknownCharacterError, match="voz-misteriosa"):
        Story(
            theme=tema_dinos,
            style=estilo_3d,
            value=EducationalValue.SHARING,
            characters=[StoryCharacter(character=dino, role=CharacterRole.PROTAGONIST)],
            scenes=[escena],
        )


def test_el_plan_tambien_valida_el_elenco(
    dino: Character, tema_dinos: Theme, estilo_3d: Style, plan_valido: StoryPlan
) -> None:
    """El plan usa tuca-tucan, pero la historia solo declara a dino."""
    with pytest.raises(UnknownCharacterError, match="tuca-tucan"):
        Story(
            theme=tema_dinos,
            style=estilo_3d,
            value=EducationalValue.SHARING,
            characters=[StoryCharacter(character=dino, role=CharacterRole.PROTAGONIST)],
            plan=plan_valido,
        )


def test_historia_valida_se_construye(historia: Story) -> None:
    assert historia.status is StoryStatus.DRAFT
    assert historia.value is EducationalValue.SHARING
    assert historia.duration_s == 30.0
    assert set(historia.characters_by_id) == {"dino-rex", "tuca-tucan"}


def test_protagonista(historia: Story) -> None:
    prota = historia.protagonist
    assert prota is not None and prota.id == "dino-rex"


# --- ciclo de vida ---------------------------------------------------------------


def test_transicion_valida(historia: Story) -> None:
    historia.advance_to(StoryStatus.PLANNED)
    assert historia.status is StoryStatus.PLANNED


def test_no_se_puede_saltear_una_etapa(historia: Story) -> None:
    """No se renderiza algo que no se narró."""
    with pytest.raises(InvalidStateTransitionError, match="No se puede pasar"):
        historia.advance_to(StoryStatus.RENDERED)


def test_el_audiolibro_puede_saltear_las_imagenes(historia: Story) -> None:
    """Un audiolibro no necesita ilustraciones: WRITTEN → NARRATED es válido."""
    historia.advance_to(StoryStatus.PLANNED)
    historia.advance_to(StoryStatus.WRITTEN)
    historia.advance_to(StoryStatus.NARRATED)
    assert historia.status is StoryStatus.NARRATED


def test_se_puede_reintentar_desde_failed(historia: Story) -> None:
    historia.advance_to(StoryStatus.FAILED)
    historia.advance_to(StoryStatus.PLANNED)
    assert historia.status is StoryStatus.PLANNED


def test_avanzar_al_mismo_estado_no_hace_nada(historia: Story) -> None:
    historia.advance_to(StoryStatus.DRAFT)
    assert historia.status is StoryStatus.DRAFT


# --- multi-formato y multi-canal -------------------------------------------------


def test_una_historia_produce_varios_formatos(historia: Story) -> None:
    """El mismo cuento es short, audiolibro y libro. Eso es todo el punto del motor."""
    historia.add_output(
        Output(kind=OutputKind.SHORT, path="/out/s.mp4", aspect_ratio=AspectRatio.VERTICAL)
    )
    historia.add_output(Output(kind=OutputKind.AUDIOBOOK, path="/out/a.mp3", duration_s=30.0))
    historia.add_output(
        Output(kind=OutputKind.BOOK, path="/out/l.pdf", aspect_ratio=AspectRatio.PRINT_A4)
    )

    assert len(historia.outputs) == 3
    assert historia.has_output(OutputKind.SHORT)
    assert not historia.has_output(OutputKind.ACTIVITY)


def test_un_formato_va_a_varios_canales(historia: Story) -> None:
    """Un solo render de short se publica en YouTube, Instagram y Facebook."""
    short = Output(
        kind=OutputKind.SHORT,
        path="/out/s.mp4",
        aspect_ratio=AspectRatio.VERTICAL,
        publications=[
            Publication(channel=Channel.YOUTUBE, url="https://youtu.be/x"),
            Publication(channel=Channel.INSTAGRAM, url="https://instagram.com/p/y"),
        ],
    )
    historia.add_output(short)

    assert short.is_published
    assert short.published_on(Channel.YOUTUBE) is not None
    assert short.published_on(Channel.FACEBOOK) is None  # todavía no


def test_narracion_completa_para_audiolibro(
    historia: Story, plan_valido: StoryPlan
) -> None:
    historia.scenes = [
        Scene.from_plan(plan_valido.scenes[0], narration="Primera."),
        Scene.from_plan(plan_valido.scenes[1], narration="Segunda."),
    ]
    assert historia.full_narration == "Primera.\n\nSegunda."
    assert historia.word_count == 2


def test_escenas_por_beat(historia: Story, plan_valido: StoryPlan) -> None:
    historia.scenes = [Scene.from_plan(plan_valido.scenes[0], narration="Hola.")]
    assert len(historia.scene_by_beat(NarrativeBeat.HOOK)) == 1
    assert historia.scene_by_beat(NarrativeBeat.ENDING) == []
