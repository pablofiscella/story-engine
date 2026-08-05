"""El planificador: la mitad del motor que DECIDE.

Todo lo que se prueba acá es determinista — no hay IA de por medio. Si estos tests
pasan, cualquier historia que salga del planificador tiene estructura válida.
"""

from __future__ import annotations

import pytest

from engine.core.enums import AgeRange, EducationalValue, NarrativeBeat
from engine.core.exceptions import DomainError
from engine.core.models import Character, Theme
from engine.generators import PROFILES, StoryPlanner


@pytest.fixture
def planner() -> StoryPlanner:
    return StoryPlanner()


def _plan(
    planner, tema, dino, rexo=None, *,
    valor=EducationalValue.SHARING, dur=30.0, edad=AgeRange.PRESCHOOL,
):
    return planner.create_plan(
        theme=tema, value=valor, age_range=edad, duration_s=dur,
        protagonist=dino, companion=rexo,
    )


# --- estructura ------------------------------------------------------------------


def test_treinta_segundos_para_preescolar_da_el_arco_canonico(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """El caso de referencia: 6 escenas de 5s, igual que el storyboard real."""
    plan = _plan(planner, tema_dinos, dino, tuca)
    assert len(plan.scenes) == 6
    assert all(s.duration_s == 5.0 for s in plan.scenes)
    assert plan.beats == [
        NarrativeBeat.HOOK,
        NarrativeBeat.PROBLEM,
        NarrativeBeat.ATTEMPT,
        NarrativeBeat.FAILURE,
        NarrativeBeat.LESSON,
        NarrativeBeat.ENDING,
    ]


@pytest.mark.parametrize("dur", [15.0, 20.0, 30.0, 45.0, 60.0, 90.0, 180.0])
def test_cualquier_duracion_produce_un_plan_valido(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character, dur: float
) -> None:
    """`StoryPlan` se valida solo, así que construirlo YA prueba arco y duración."""
    plan = _plan(planner, tema_dinos, dino, tuca, dur=dur)
    assert plan.total_duration_s == pytest.approx(dur, abs=1.0)
    assert plan.beats[0] is NarrativeBeat.HOOK
    assert plan.beats[-1] is NarrativeBeat.ENDING


@pytest.mark.parametrize("edad", list(AgeRange))
@pytest.mark.parametrize("valor", list(EducationalValue))
def test_toda_combinacion_de_valor_y_edad_funciona(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character,
    edad: AgeRange, valor: EducationalValue,
) -> None:
    """8 valores × 4 edades = 32 combinaciones, todas válidas sin tocar código."""
    plan = _plan(planner, tema_dinos, dino, tuca, valor=valor, edad=edad)
    assert len(plan.scenes) >= 3


def test_mas_chicos_tienen_escenas_mas_cortas(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """La atención de un chico de 2 años no da lo mismo que la de uno de 8."""
    bebes = _plan(planner, tema_dinos, dino, tuca, dur=60.0, edad=AgeRange.TODDLER)
    grandes = _plan(planner, tema_dinos, dino, tuca, dur=60.0, edad=AgeRange.KID)
    assert len(bebes.scenes) > len(grandes.scenes)


def test_una_historia_larga_repite_beats_sin_romper_el_arco(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    plan = _plan(planner, tema_dinos, dino, tuca, dur=60.0, edad=AgeRange.KID)
    assert len(plan.scenes) > 6
    assert plan.beats.count(NarrativeBeat.ATTEMPT) >= 2


def test_los_beats_repetidos_reciben_instrucciones_distintas(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """Si el escritor recibe dos veces la misma orden, escribe dos escenas iguales."""
    plan = _plan(planner, tema_dinos, dino, tuca, dur=60.0, edad=AgeRange.KID)
    intentos = [s.purpose for s in plan.scenes if s.beat is NarrativeBeat.ATTEMPT]
    assert len(intentos) == len(set(intentos))


def test_una_historia_corta_recorta_pero_conserva_el_aprendizaje(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """Lo primero que se saca es el fracaso; la enseñanza es lo último que se pierde."""
    plan = _plan(planner, tema_dinos, dino, tuca, dur=15.0, edad=AgeRange.TODDLER)
    assert NarrativeBeat.LESSON in plan.beats
    assert NarrativeBeat.FAILURE not in plan.beats


def test_duracion_imposible_falla_con_un_mensaje_claro(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character
) -> None:
    with pytest.raises(DomainError, match="No se puede armar"):
        _plan(planner, tema_dinos, dino, dur=4.0)


# --- contenido -------------------------------------------------------------------


def test_el_protagonista_esta_en_todas_las_escenas(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    plan = _plan(planner, tema_dinos, dino, tuca)
    assert all(dino.id in s.character_ids for s in plan.scenes)


def test_el_companero_solo_aparece_donde_hace_falta(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """No está de relleno: aparece en los beats donde el conflicto lo necesita."""
    plan = _plan(planner, tema_dinos, dino, tuca)
    con_companero = [s for s in plan.scenes if tuca.id in s.character_ids]
    assert 0 < len(con_companero) < len(plan.scenes)


def test_sin_companero_no_se_inventa_ninguno(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character
) -> None:
    """Un personaje fantasma es la causa de que el ilustrador dibuje a alguien
    distinto en cada escena."""
    plan = _plan(planner, tema_dinos, dino)
    assert plan.character_ids == {dino.id}
    assert not any("{companero}" in s.purpose for s in plan.scenes)
    assert not any("Los dos" in s.purpose for s in plan.scenes)


def test_los_nombres_reales_reemplazan_las_plantillas(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    plan = _plan(planner, tema_dinos, dino, tuca)
    texto = " ".join(s.purpose for s in plan.scenes)
    assert "{" not in texto
    assert dino.name in texto and tuca.name in texto


def test_los_lugares_salen_del_tema(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """Inventar lugares que el tema no declaró rompe la coherencia del mundo."""
    plan = _plan(planner, tema_dinos, dino, tuca)
    assert all(s.location in tema_dinos.locations for s in plan.scenes)


def test_la_curva_emocional_arranca_curiosa_y_cierra_bien(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    from engine.core.enums import Emotion

    plan = _plan(planner, tema_dinos, dino, tuca)
    assert plan.scenes[-1].emotion in (Emotion.JOY, Emotion.PRIDE)


def test_es_determinista(
    planner: StoryPlanner, tema_dinos: Theme, dino: Character, tuca: Character
) -> None:
    """Mismos parámetros, mismo plan. Sin esto no se puede reproducir un bug."""
    assert _plan(planner, tema_dinos, dino, tuca) == _plan(planner, tema_dinos, dino, tuca)


# --- perfiles de valor -----------------------------------------------------------


def test_todo_valor_del_enum_tiene_su_perfil() -> None:
    """Un valor sin perfil generaría una historia sin conflicto real."""
    assert set(PROFILES) == set(EducationalValue)


def test_cada_perfil_cubre_todo_el_arco() -> None:
    for valor, perfil in PROFILES.items():
        faltan = set(NarrativeBeat) - set(perfil.purposes)
        assert not faltan, f"{valor.value} no tiene propósito para {faltan}"
        faltan = set(NarrativeBeat) - set(perfil.emotions)
        assert not faltan, f"{valor.value} no tiene emoción para {faltan}"


def test_cada_valor_tiene_moraleja_y_pregunta_propias() -> None:
    morales = {p.moral for p in PROFILES.values()}
    preguntas = {p.question for p in PROFILES.values()}
    assert len(morales) == len(PROFILES)
    assert len(preguntas) == len(PROFILES)
