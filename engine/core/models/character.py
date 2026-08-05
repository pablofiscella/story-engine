"""Personajes.

Un personaje NO es un string. Es un objeto con una descripción visual canónica que
se inyecta, textual e idéntica, en TODOS los prompts de imagen donde aparece.

Por qué importa tanto: cuando cada escena se genera sola y solo se le pasa "un
dinosaurio", el modelo dibuja un dinosaurio distinto cada vez — cambia el color, la
ropa, la cara. El arreglo no es pedirle mejor al modelo: es que el motor tenga UNA
sola descripción del personaje y la repita siempre igual. De eso se trata
`Appearance.prompt_fragment()`.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from engine.core.enums import Emotion
from engine.core.models.base import EngineModel, Slug


class Appearance(EngineModel):
    """El aspecto físico del personaje. Fuente única de verdad visual."""

    species: str = Field(description="Qué es: 'dinosaurio T-Rex', 'niña', 'robot'.")
    description: str = Field(
        min_length=10,
        description="Descripción canónica y CONCRETA. Va literal a todos los prompts.",
    )
    colors: list[str] = Field(default_factory=list, description="Colores dominantes.")
    outfit: str | None = Field(default=None, description="Ropa/accesorios fijos.")
    distinctive_features: list[str] = Field(
        default_factory=list,
        description="Lo que lo hace reconocible: 'cicatriz en la cola', 'gorro rojo'.",
    )

    def prompt_fragment(self) -> str:
        """Descripción compacta para inyectar en un prompt de imagen.

        Siempre devuelve lo mismo para el mismo personaje: esa estabilidad ES la
        consistencia visual entre escenas.
        """
        partes = [self.species, self.description]
        if self.colors:
            partes.append("colores: " + ", ".join(self.colors))
        if self.outfit:
            partes.append(f"viste {self.outfit}")
        if self.distinctive_features:
            partes.append("rasgos: " + ", ".join(self.distinctive_features))
        return ". ".join(p.rstrip(".") for p in partes if p) + "."


class Voice(EngineModel):
    """Cómo suena el personaje.

    `provider_voice_id` es opcional a propósito: el core no sabe si atrás hay
    ElevenLabs, OpenAI o Azure. Lo resuelve el proveedor de voz.
    """

    provider_voice_id: str | None = Field(default=None, description="ID en el proveedor de TTS.")
    description: str = Field(
        default="",
        description="Cómo suena en palabras: 'aguda y curiosa', 'grave y calma'.",
    )
    speed: float = Field(default=1.0, ge=0.5, le=1.5)
    pitch: float = Field(default=1.0, ge=0.5, le=1.5)


class Character(EngineModel):
    """Un personaje reutilizable entre historias.

    Vive en `assets/characters/` y se referencia por `id`. Definirlo una vez y
    reusarlo es lo que permite construir un universo coherente en vez de inventar
    protagonistas nuevos en cada cuento.
    """

    id: Slug
    name: str = Field(min_length=1, max_length=60)
    appearance: Appearance
    voice: Voice = Field(default_factory=Voice)
    personality: list[str] = Field(
        default_factory=list,
        description="Rasgos de carácter: 'curioso', 'impaciente'. Guían el diálogo.",
    )
    expressions: dict[Emotion, str] = Field(
        default_factory=dict,
        description="Cómo se le ve la cara en cada emoción. Alimenta el prompt de imagen.",
    )
    poses: list[str] = Field(
        default_factory=list,
        description="Poses típicas: 'saludando', 'corriendo'. Vocabulario para el ilustrador.",
    )

    @field_validator("personality", "poses")
    @classmethod
    def _sin_vacios(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]

    def expression_for(self, emotion: Emotion) -> str:
        """Cómo se ve este personaje sintiendo `emotion`.

        Si no está definida, cae a una descripción genérica en vez de romper: una
        expresión faltante no puede frenar la generación de una historia entera.
        """
        return self.expressions.get(emotion, f"expresión de {emotion.value}")
