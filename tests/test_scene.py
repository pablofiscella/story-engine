"""La escena escrita. El test central es el presupuesto de palabras: si la narración
no entra en los segundos de la escena, el video sale roto."""

from __future__ import annotations

import pytest

from engine.core.enums import Emotion, NarrativeBeat
from engine.core.exceptions import InvalidDurationError
from engine.core.models import DialogueLine, Scene, StoryPlan


def test_from_plan_conserva_lo_que_decidio_el_motor(plan_valido: StoryPlan) -> None:
    """La escena escrita no puede desviarse del plan."""
    plan = plan_valido.scenes[0]
    escena = Scene.from_plan(plan, narration="Dino asomó la cabeza.")
    assert escena.index == plan.index
    assert escena.beat is plan.beat
    assert escena.purpose == plan.purpose
    assert escena.duration_s == plan.duration_s
    assert escena.character_ids == plan.character_ids
    assert escena.emotion is plan.emotion


def test_narracion_que_no_entra_es_rechazada(plan_valido: StoryPlan) -> None:
    """5s dan para 14 palabras (2.5 p/s × 1.15). 40 no entran ni con buena voluntad."""
    with pytest.raises(InvalidDurationError, match="no entra"):
        Scene.from_plan(plan_valido.scenes[0], narration=" ".join(["palabra"] * 40))


def test_el_dialogo_hablado_tambien_cuenta(plan_valido: StoryPlan) -> None:
    """Todo lo que se DICE ocupa tiempo, sea narración o diálogo."""
    with pytest.raises(InvalidDurationError):
        Scene.from_plan(
            plan_valido.scenes[0],
            narration=" ".join(["palabra"] * 10),
            dialogue=[DialogueLine(character_id="dino-rex", text=" ".join(["hola"] * 10))],
        )


def test_el_globo_no_hablado_no_gasta_presupuesto(plan_valido: StoryPlan) -> None:
    """Un globo en pantalla se lee, no se narra: no consume tiempo de audio."""
    escena = Scene.from_plan(
        plan_valido.scenes[0],
        narration=" ".join(["palabra"] * 10),
        dialogue=[
            DialogueLine(character_id="dino-rex", text=" ".join(["hola"] * 10), spoken=False)
        ],
    )
    assert escena.word_count == 10


def test_word_count_suma_narracion_y_dialogo(escena: Scene) -> None:
    base = escena.word_count
    escena.dialogue = [DialogueLine(character_id="dino-rex", text="hola amigo")]
    assert escena.word_count == base + 2


def test_duracion_estimada_del_habla(plan_valido: StoryPlan) -> None:
    escena = Scene.from_plan(plan_valido.scenes[0], narration="una dos tres cuatro cinco")
    assert escena.estimated_speech_duration_s == 2.0  # 5 palabras / 2.5 p-s


def test_validate_assignment_protege_al_mutar(escena: Scene) -> None:
    """Cambiar un campo después de crear también valida (no solo al construir)."""
    with pytest.raises(ValueError):
        escena.duration_s = 999.0


def test_escena_completa_con_direccion(plan_valido: StoryPlan) -> None:
    from engine.core.enums import CameraMovement, MusicMood, ShotType
    from engine.core.models import CameraDirection, MusicCue

    escena = Scene.from_plan(
        plan_valido.scenes[0],
        narration="Dino asomó entre los helechos.",
        subtitle="Dino asomó entre los helechos.",
        image_prompt="dinosaurio verde asomando entre helechos gigantes",
        camera=CameraDirection(shot=ShotType.CLOSE_UP, movement=CameraMovement.ZOOM_IN),
        music=MusicCue(mood=MusicMood.PLAYFUL),
        sfx=["hojas moviéndose"],
    )
    assert escena.camera.shot is ShotType.CLOSE_UP
    assert escena.music is not None and escena.music.mood is MusicMood.PLAYFUL
    assert escena.sfx == ["hojas moviéndose"]


def test_campos_extra_son_rechazados() -> None:
    """Si un proveedor devuelve un campo que no esperamos, queremos enterarnos."""
    with pytest.raises(ValueError):
        Scene(
            index=0,
            beat=NarrativeBeat.HOOK,
            purpose="presentar",
            duration_s=5.0,
            location="el claro",
            character_ids=["dino-rex"],
            emotion=Emotion.JOY,
            narration="hola",
            campo_inventado="???",  # type: ignore[call-arg]
        )
