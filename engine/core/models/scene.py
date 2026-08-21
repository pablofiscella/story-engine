"""La escena escrita: el plan, ya con palabras.

Una `Scene` es un `ScenePlan` al que el escritor le agregó narración, diálogo y
dirección. Conserva `beat` y `purpose` del plan a propósito: cuando dentro de un año
alguien mire una escena suelta, tiene que poder saber QUÉ venía a hacer, no solo qué
dice.

El guardián de duración vive acá: una narración que no entra en los segundos de la
escena rompe el video (el audio se corta o la imagen se congela). Mejor rechazarla
al construirla que descubrirlo en el render.
"""

from __future__ import annotations

import math

from pydantic import Field, model_validator

from engine.core.constants import (
    MAX_SCENE_DURATION_S,
    MAX_SUBTITLE_LENGTH,
    MIN_SCENE_DURATION_S,
    NARRATION_OVERFLOW_TOLERANCE,
    WORDS_PER_SECOND,
)
from engine.core.enums import CameraMovement, Emotion, MusicMood, NarrativeBeat, ShotType
from engine.core.exceptions import InvalidDurationError
from engine.core.models.audio import AudioTrack
from engine.core.models.base import EngineModel, Slug
from engine.core.models.plan import ScenePlan


class DialogueLine(EngineModel):
    """Una línea de diálogo, atada a QUIÉN la dice.

    `character_id` y no un nombre suelto: así el narrador sabe con qué voz leerla y
    el validador puede chequear que ese personaje exista de verdad.
    """

    character_id: Slug
    text: str = Field(min_length=1)
    emotion: Emotion | None = Field(
        default=None, description="Si difiere de la emoción general de la escena."
    )
    spoken: bool = Field(
        default=True,
        description=(
            "Si se narra en voz alta o es solo un globo en pantalla. En los shorts, "
            "un globo de diálogo se LEE pero no se dice: no ocupa tiempo de audio y "
            "por eso no gasta presupuesto de palabras."
        ),
    )


class CameraDirection(EngineModel):
    """Dirección de cámara. En imagen fija, el render la traduce a Ken Burns."""

    shot: ShotType = ShotType.MEDIUM
    movement: CameraMovement = CameraMovement.STATIC


class MusicCue(EngineModel):
    """Qué suena de fondo."""

    mood: MusicMood = MusicMood.PLAYFUL
    track: str | None = Field(
        default=None, description="Pista concreta; si no, la elige el render."
    )
    volume: float = Field(default=0.3, ge=0.0, le=1.0)


class Scene(EngineModel):
    """Una escena completa, lista para ilustrar y narrar."""

    # --- viene del plan (lo decidió el motor) ---
    index: int = Field(ge=0)
    beat: NarrativeBeat
    purpose: str = Field(min_length=5)
    duration_s: float = Field(ge=MIN_SCENE_DURATION_S, le=MAX_SCENE_DURATION_S)
    location: str = Field(min_length=2)
    character_ids: list[Slug] = Field(min_length=1)
    emotion: Emotion = Field(description="El tono de la escena: música y default de cara.")
    character_emotions: dict[Slug, Emotion] = Field(
        default_factory=dict,
        description="Lo que siente cada uno, cuando no es el tono general. Viene del plan.",
    )

    # --- lo escribió la IA ---
    narration: str = Field(min_length=1, description="Lo que dice el narrador.")
    dialogue: list[DialogueLine] = Field(default_factory=list)
    subtitle: str = Field(default="", max_length=MAX_SUBTITLE_LENGTH)
    emphasis: list[str] = Field(
        default_factory=list,
        description=(
            "Palabras del subtítulo a resaltar en pantalla "
            "('compartir', 'juntos'). "
            "Las elige el escritor porque dependen del sentido de la frase; el render "
            "solo las pinta."
        ),
    )
    imagined_character_ids: list[Slug] = Field(
        default_factory=list,
        description="Personajes en burbuja de pensamiento o recuerdo: no están presentes.",
    )
    prop: str = Field(
        default="",
        description=(
            "El objeto del conflicto, si esta escena lo tiene. Lo elige el motor y va "
            "al prompt de imagen sí o sí, aunque la narración no lo nombre."
        ),
    )
    visual_note: str = Field(
        default="",
        description=(
            "Recurso visual concreto para esta escena: 'burbuja de pensamiento donde "
            "se imagina jugando con su amigo'. Lo decide el MOTOR (viene del plan), "
            "no la IA — es dirección de arte, no redacción."
        ),
    )
    audio: list[AudioTrack] = Field(
        default_factory=list,
        description=(
            "Las pistas de audio de la escena, en el orden en que suenan. Vacía hasta "
            "que corre el narrador."
        ),
    )
    image_prompt: str = Field(default="", description="Prompt final para ilustrar la escena.")
    image_path: str = Field(
        default="",
        description="Ruta de la ilustración ya generada. Vacía hasta que corre el ilustrador.",
    )

    # --- dirección (motor + defaults) ---
    camera: CameraDirection = Field(default_factory=CameraDirection)
    music: MusicCue | None = None
    sfx: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validar_narracion_entra(self) -> Scene:
        """La narración tiene que caber en los segundos de la escena."""
        if self.word_count > self.max_words:
            raise InvalidDurationError(
                f"Escena {self.index}: la narración tiene {self.word_count} palabras y no entra "
                f"en {self.duration_s:.1f}s (máximo {self.max_words}). Hay que acortarla."
            )
        return self

    def emotion_for(self, character_id: str) -> Emotion:
        """Qué siente este personaje acá. Si no se dijo, el tono de la escena.

        Lo usa el prompt de imagen para darle a cada uno SU cara: el que no comparte
        y el que se queda afuera no ponen la misma.
        """
        return self.character_emotions.get(character_id, self.emotion)

    @property
    def word_count(self) -> int:
        """Palabras que se DICEN: narración + diálogo hablado.

        Los globos que solo se leen en pantalla (`spoken=False`) no cuentan: no
        consumen tiempo de audio.
        """
        total = len(self.narration.split())
        return total + sum(len(d.text.split()) for d in self.dialogue if d.spoken)

    @property
    def max_words(self) -> int:
        """Presupuesto de palabras para esta escena, con la tolerancia ya aplicada."""
        return math.floor(self.duration_s * WORDS_PER_SECOND * NARRATION_OVERFLOW_TOLERANCE)

    @property
    def estimated_speech_duration_s(self) -> float:
        """Cuánto tardaría en decirse, ESTIMADO. Sirve antes de que exista el audio."""
        return round(self.word_count / WORDS_PER_SECOND, 2)

    @property
    def audio_duration_s(self) -> float:
        """Cuánto dura la escena de verdad, medido del audio ya generado.

        Cero mientras no se narró. El render tiene que usar ésta y no `duration_s`:
        la del plan es una intención, ésta es un hecho.
        """
        return round(sum(t.duration_s for t in self.audio), 3)

    @property
    def real_duration_s(self) -> float:
        """La duración que vale para el render: la del audio si existe, si no la del plan."""
        return self.audio_duration_s or self.duration_s

    @classmethod
    def from_plan(cls, plan: ScenePlan, *, narration: str, **extra: object) -> Scene:
        """Construye la escena a partir de su plan.

        Es el único camino previsto: garantiza que la escena escrita no se desvíe de
        lo que el motor decidió (mismo beat, misma duración, mismos personajes).

        Lo que venga en `extra` pisa al plan: sirve para afinar una escena suelta a
        mano sin tener que rearmar el plan entero.
        """
        campos: dict[str, object] = {
            "index": plan.index,
            "beat": plan.beat,
            "purpose": plan.purpose,
            "duration_s": plan.duration_s,
            "location": plan.location,
            "character_ids": list(plan.character_ids),
            "emotion": plan.emotion,
            "character_emotions": dict(plan.character_emotions),
            "camera": CameraDirection(shot=plan.shot),
            "prop": plan.prop,
            "visual_note": plan.visual_note,
            "imagined_character_ids": list(plan.imagined_character_ids),
            "narration": narration,
        }
        campos.update(extra)
        return cls(**campos)  # type: ignore[arg-type]
