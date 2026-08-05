"""Base común de todos los modelos del motor.

Dos decisiones que se aplican a TODO el dominio:

1. `extra="forbid"` — si un proveedor de IA devuelve un campo que no esperábamos,
   queremos enterarnos ahí y no que viaje silencioso hasta el render.
2. `validate_assignment=True` — las reglas también corren al MUTAR, no solo al crear.
   Sin esto, `scene.duration_s = 999` pasaba sin chistar.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

#: Identificador estable, legible y seguro para nombres de archivo y URLs.
#: Se usa para personajes, temas y assets: `dino-rex`, `bosque-encantado`.
Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=64)]


class EngineModel(BaseModel):
    """Modelo base: estricto por defecto."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,  # queremos los enums, no sus strings sueltos
        str_strip_whitespace=True,
    )
