"""El plan narrativo: la decisión estructural, tomada ANTES de escribir.

Esta es la pieza central del motor.

El planificador (código determinista, sin IA) arma la secuencia de beats: cuántas
escenas, qué hace cada una, cuánto dura, quién aparece, qué se siente. Recién con
ese plan en la mano el escritor de IA redacta la narración de cada escena, de a una
y con contexto acotado.

La diferencia práctica: pedirle a un modelo "escribí un cuento de 30 segundos sobre
compartir" da resultados que varían de excelentes a irreproducibles. Pedirle "escribí
5 segundos de narración para esta escena, cuyo objetivo es presentar a Dino en el
bosque con curiosidad" da un resultado consistente, historia tras historia.

El plan es también lo que se REVISA y se corrige barato: si el arco está mal, se
detecta acá, antes de gastar un peso en imágenes o audio.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from engine.core.constants import (
    BEAT_ORDER,
    DURATION_TOLERANCE_S,
    MAX_SCENE_DURATION_S,
    MAX_SCENES,
    MIN_SCENE_DURATION_S,
    MIN_SCENES,
)
from engine.core.enums import Emotion, NarrativeBeat
from engine.core.exceptions import InvalidArcError, InvalidDurationError
from engine.core.models.base import EngineModel, Slug


class ScenePlan(EngineModel):
    """Qué tiene que lograr UNA escena. Sin una palabra de narración todavía.

    `purpose` es la instrucción para el escritor: "presentar a Dino y su curiosidad".
    No es texto para el chico, es la orden de trabajo.
    """

    index: int = Field(ge=0)
    beat: NarrativeBeat
    purpose: str = Field(
        min_length=5,
        description="Qué debe conseguir esta escena. Instrucción para el escritor.",
    )
    duration_s: float = Field(ge=MIN_SCENE_DURATION_S, le=MAX_SCENE_DURATION_S)
    location: str = Field(min_length=2, description="Dónde transcurre.")
    character_ids: list[Slug] = Field(
        min_length=1, description="Quiénes aparecen. Al menos uno: nadie habla solo al vacío."
    )
    emotion: Emotion = Field(description="Emoción dominante. Guía tono, cara y música.")
    imagined_character_ids: list[Slug] = Field(
        default_factory=list,
        description=(
            "Personajes que aparecen en la escena SIN estar físicamente: en una "
            "burbuja de pensamiento, un recuerdo, un dibujo. Van aparte de "
            "`character_ids` porque el prompt tiene que describirlos igual —si no, el "
            "modelo los inventa— pero sin contarlos como presentes en la escena."
        ),
    )
    visual_note: str = Field(
        default="",
        description=(
            "Recurso visual para esta escena, si el beat lo pide: una burbuja de "
            "pensamiento, un objeto en primer plano. Dirección de arte decidida por "
            "el motor."
        ),
    )


class StoryPlan(EngineModel):
    """El esqueleto completo de la historia.

    Se valida a sí mismo: si el arco está roto o las duraciones no cierran, el plan
    no llega a existir. Un plan válido es la garantía de que lo que sigue tiene sentido.
    """

    target_duration_s: float = Field(gt=0)
    scenes: list[ScenePlan] = Field(min_length=MIN_SCENES, max_length=MAX_SCENES)

    @model_validator(mode="after")
    def _validar(self) -> StoryPlan:
        self._validar_indices()
        self._validar_arco()
        self._validar_duracion()
        return self

    def _validar_indices(self) -> None:
        esperados = list(range(len(self.scenes)))
        reales = [s.index for s in self.scenes]
        if reales != esperados:
            raise InvalidArcError(
                f"Los índices deben ser correlativos desde 0: esperaba {esperados}, vino {reales}."
            )

    def _validar_arco(self) -> None:
        """El arco puede repetir beats, pero nunca retroceder.

        Repetir es legítimo (dos intentos fallidos seguidos). Retroceder no: un
        problema no puede aparecer DESPUÉS del aprendizaje.
        """
        posiciones = [BEAT_ORDER[s.beat] for s in self.scenes]
        for anterior, actual in zip(posiciones, posiciones[1:], strict=False):
            if actual < anterior:
                raise InvalidArcError(
                    "El arco narrativo retrocede: "
                    f"{[s.beat.value for s in self.scenes]}. "
                    "El orden canónico no admite volver atrás."
                )
        if self.scenes[0].beat is not NarrativeBeat.HOOK:
            raise InvalidArcError(
                f"La historia debe abrir con un gancho, no con '{self.scenes[0].beat.value}'."
            )
        if self.scenes[-1].beat is not NarrativeBeat.ENDING:
            raise InvalidArcError(
                f"La historia debe cerrar con un final, no con '{self.scenes[-1].beat.value}'."
            )

    def _validar_duracion(self) -> None:
        total = self.total_duration_s
        if abs(total - self.target_duration_s) > DURATION_TOLERANCE_S:
            raise InvalidDurationError(
                f"Las escenas suman {total:.1f}s pero la historia apunta a "
                f"{self.target_duration_s:.1f}s (tolerancia {DURATION_TOLERANCE_S}s)."
            )

    @property
    def total_duration_s(self) -> float:
        return round(sum(s.duration_s for s in self.scenes), 3)

    @property
    def beats(self) -> list[NarrativeBeat]:
        return [s.beat for s in self.scenes]

    @property
    def character_ids(self) -> set[str]:
        """Todos los personajes que el plan pone en escena."""
        return {cid for s in self.scenes for cid in s.character_ids}

    def scenes_with_beat(self, beat: NarrativeBeat) -> list[ScenePlan]:
        return [s for s in self.scenes if s.beat is beat]
