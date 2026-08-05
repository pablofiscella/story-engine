"""El plan narrativo es el guardián de la estructura: si acá pasa algo roto, se
propaga a imágenes, audio y video. Estos tests son la red principal del motor."""

from __future__ import annotations

import pytest

from engine.core.enums import Emotion, NarrativeBeat
from engine.core.exceptions import InvalidArcError, InvalidDurationError
from engine.core.models import ScenePlan, StoryPlan


def _escena(index: int, beat: NarrativeBeat, dur: float = 5.0) -> ScenePlan:
    return ScenePlan(
        index=index,
        beat=beat,
        purpose=f"objetivo de la escena {index}",
        duration_s=dur,
        location="el claro",
        character_ids=["dino-rex"],
        emotion=Emotion.CURIOSITY,
    )


def test_plan_valido_se_construye(plan_valido: StoryPlan) -> None:
    assert len(plan_valido.scenes) == 6
    assert plan_valido.total_duration_s == 30.0
    assert plan_valido.beats[0] is NarrativeBeat.HOOK
    assert plan_valido.beats[-1] is NarrativeBeat.ENDING


def test_el_arco_no_puede_retroceder() -> None:
    """Un problema no puede aparecer DESPUÉS del aprendizaje."""
    with pytest.raises(InvalidArcError, match="retrocede"):
        StoryPlan(
            target_duration_s=15.0,
            scenes=[
                _escena(0, NarrativeBeat.HOOK),
                _escena(1, NarrativeBeat.LESSON),
                _escena(2, NarrativeBeat.PROBLEM),  # ← retrocede
            ],
        )


def test_repetir_un_beat_es_valido() -> None:
    """Dos intentos fallidos seguidos son narrativamente correctos."""
    plan = StoryPlan(
        target_duration_s=25.0,
        scenes=[
            _escena(0, NarrativeBeat.HOOK),
            _escena(1, NarrativeBeat.ATTEMPT),
            _escena(2, NarrativeBeat.ATTEMPT),
            _escena(3, NarrativeBeat.LESSON),
            _escena(4, NarrativeBeat.ENDING),
        ],
    )
    assert plan.beats.count(NarrativeBeat.ATTEMPT) == 2


def test_debe_abrir_con_gancho() -> None:
    with pytest.raises(InvalidArcError, match="gancho"):
        StoryPlan(
            target_duration_s=15.0,
            scenes=[
                _escena(0, NarrativeBeat.PROBLEM),
                _escena(1, NarrativeBeat.LESSON),
                _escena(2, NarrativeBeat.ENDING),
            ],
        )


def test_debe_cerrar_con_final() -> None:
    with pytest.raises(InvalidArcError, match="final"):
        StoryPlan(
            target_duration_s=15.0,
            scenes=[
                _escena(0, NarrativeBeat.HOOK),
                _escena(1, NarrativeBeat.PROBLEM),
                _escena(2, NarrativeBeat.LESSON),
            ],
        )


def test_indices_deben_ser_correlativos() -> None:
    with pytest.raises(InvalidArcError, match="correlativos"):
        StoryPlan(
            target_duration_s=15.0,
            scenes=[
                _escena(0, NarrativeBeat.HOOK),
                _escena(5, NarrativeBeat.PROBLEM),  # ← salteado
                _escena(2, NarrativeBeat.ENDING),
            ],
        )


def test_la_duracion_debe_cerrar_contra_el_objetivo() -> None:
    with pytest.raises(InvalidDurationError, match="suman"):
        StoryPlan(
            target_duration_s=60.0,  # pide 60s
            scenes=[
                _escena(0, NarrativeBeat.HOOK),
                _escena(1, NarrativeBeat.PROBLEM),
                _escena(2, NarrativeBeat.ENDING),
            ],  # pero suma 15s
        )


def test_tolerancia_de_redondeo() -> None:
    """El planificador reparte segundos; el redondeo no puede tirar abajo el plan."""
    plan = StoryPlan(
        target_duration_s=15.0,
        scenes=[
            _escena(0, NarrativeBeat.HOOK, 5.3),
            _escena(1, NarrativeBeat.PROBLEM, 5.3),
            _escena(2, NarrativeBeat.ENDING, 5.3),
        ],
    )
    assert plan.total_duration_s == pytest.approx(15.9)


def test_una_escena_necesita_al_menos_un_personaje() -> None:
    with pytest.raises(ValueError):
        _ = ScenePlan(
            index=0,
            beat=NarrativeBeat.HOOK,
            purpose="una escena vacía",
            duration_s=5.0,
            location="el claro",
            character_ids=[],  # ← nadie
            emotion=Emotion.CURIOSITY,
        )


def test_character_ids_junta_todo_el_elenco(plan_valido: StoryPlan) -> None:
    assert plan_valido.character_ids == {"dino-rex", "tuca-tucan"}


def test_scenes_with_beat(plan_valido: StoryPlan) -> None:
    assert len(plan_valido.scenes_with_beat(NarrativeBeat.HOOK)) == 1
    assert plan_valido.scenes_with_beat(NarrativeBeat.HOOK)[0].index == 0
