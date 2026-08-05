"""Temáticas.

El tema es DATO, no código: vive en `assets/themes/<id>.json` y se carga. Agregar
"dinosaurios marinos" tiene que ser un archivo nuevo, nunca un deploy.

Un tema define el MUNDO: dónde pasa, quiénes lo habitan, de qué color es. Lo que NO
define es cómo se DIBUJA (eso es `Style`) ni QUÉ enseña (eso es `EducationalValue`).

Los tres son ejes independientes a propósito:

    6 temas × 8 valores × N estilos

Cada eje que se suma multiplica el catálogo sin escribir una línea nueva. Si el
estilo viviera adentro del tema, cada combinación obligaría a duplicar el tema entero.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from engine.core.models.base import EngineModel, Slug

_HEX = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"


class Palette(EngineModel):
    """Paleta del tema. Baja al prompt de imagen y a los templates de PDF/video."""

    primary: str = Field(pattern=_HEX)
    secondary: str = Field(pattern=_HEX)
    accent: str = Field(pattern=_HEX)
    background: str = Field(pattern=_HEX, default="#FFFFFF")

    @field_validator("primary", "secondary", "accent", "background")
    @classmethod
    def _normalizar(cls, v: str) -> str:
        return v.upper()


class Theme(EngineModel):
    """Una temática completa: mundo, colores y elenco sugerido."""

    id: Slug
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", description="El mundo en una frase.")
    palette: Palette
    default_style_id: Slug | None = Field(
        default=None,
        description=(
            "Estilo sugerido para este tema. Es una SUGERENCIA, no una atadura: la "
            "historia puede pedir otro. Si no se elige ninguno, el motor usa este."
        ),
    )
    locations: list[str] = Field(
        default_factory=list,
        description="Lugares donde pueden pasar las escenas: 'el claro del bosque'.",
    )
    character_ids: list[Slug] = Field(
        default_factory=list,
        description="Elenco habitual del tema (ids de `assets/characters/`).",
    )
    music_tracks: list[str] = Field(default_factory=list, description="Pistas del tema.")

    @field_validator("locations")
    @classmethod
    def _sin_vacios(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]
