"""Ficha técnica de la historia: quién es, para quién, en qué estado."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import Field

from engine.core.constants import (
    DEFAULT_STORY_DURATION_S,
    MAX_STORY_DURATION_S,
    MAX_TITLE_LENGTH,
    MIN_STORY_DURATION_S,
)
from engine.core.enums import AgeRange, Language, StoryStatus
from engine.core.models.base import EngineModel


def _ahora() -> datetime:
    return datetime.now(UTC)


class StoryMetadata(EngineModel):
    """Datos de identidad y estado.

    `version` existe porque una historia se REGENERA: se reescribe una escena, se
    cambia una imagen. Sin versión no hay forma de saber si el video publicado
    corresponde al texto actual.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str = Field(default="", max_length=MAX_TITLE_LENGTH)
    language: Language = Language.ES_AR
    age_range: AgeRange = AgeRange.PRESCHOOL
    target_duration_s: float = Field(
        default=DEFAULT_STORY_DURATION_S,
        ge=MIN_STORY_DURATION_S,
        le=MAX_STORY_DURATION_S,
        description="Duración objetivo de la NARRACIÓN, en segundos.",
    )
    status: StoryStatus = StoryStatus.DRAFT
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=_ahora)
    updated_at: datetime = Field(default_factory=_ahora)

    def touch(self) -> None:
        """Marca que la historia cambió."""
        self.updated_at = _ahora()

    def bump_version(self) -> None:
        """Nueva versión del contenido (se reescribió algo)."""
        self.version += 1
        self.touch()
