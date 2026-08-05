"""Lo que la historia produce, y a dónde va.

Dos ejes separados a propósito:

- `Output`  → QUÉ se generó (un short, un audiolibro, un PDF). Es un archivo.
- `Publication` → DÓNDE se publicó ese archivo (YouTube, Instagram, Facebook...).

Un mismo `Output` puede tener varias `Publication`: el short se sube a YouTube, a
Instagram y a Facebook sin volver a renderizarse. Y una misma historia tiene varios
`Output`: el cuento de dinosaurios es short, audiolibro, libro y actividad.

Mantenerlos separados es lo que permite sumar una plataforma nueva mañana sin tocar
el render, y un formato nuevo sin tocar la publicación.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from engine.core.enums import AspectRatio, Channel, OutputKind
from engine.core.models.base import EngineModel


def _ahora() -> datetime:
    return datetime.now(UTC)


class Publication(EngineModel):
    """Un `Output` publicado en un canal concreto."""

    channel: Channel
    url: str | None = Field(default=None, description="URL pública del post.")
    external_id: str | None = Field(
        default=None, description="ID en la plataforma (video_id, media_id)."
    )
    published_at: datetime = Field(default_factory=_ahora)
    title: str | None = Field(default=None, description="Título usado en ese canal.")
    description: str | None = Field(default=None, description="Copy/caption de ese canal.")
    tags: list[str] = Field(default_factory=list)


class Output(EngineModel):
    """Un artefacto concreto generado a partir de la historia."""

    kind: OutputKind
    path: str = Field(min_length=1, description="Ruta o URI del archivo generado.")
    aspect_ratio: AspectRatio | None = Field(
        default=None, description="Solo para formatos visuales."
    )
    duration_s: float | None = Field(
        default=None, ge=0, description="Solo para video y audio."
    )
    size_bytes: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=_ahora)
    publications: list[Publication] = Field(default_factory=list)

    @property
    def is_published(self) -> bool:
        return bool(self.publications)

    def published_on(self, channel: Channel) -> Publication | None:
        """La publicación de este artefacto en `channel`, si existe.

        Evita subir dos veces lo mismo al mismo lado.
        """
        return next((p for p in self.publications if p.channel is channel), None)
