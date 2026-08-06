"""Contratos con el mundo exterior.

El core no importa `openai` ni `elevenlabs` ni `sqlalchemy` en ningún lado. Define
QUÉ necesita y deja que otro lo implemente. Cambiar de proveedor es escribir una
clase nueva, no tocar el motor.

Por qué tres interfaces y no una sola `AIProvider`: los proveedores reales no son
intercambiables. ElevenLabs hace voz y no texto; Gemini hace texto e imagen y no voz.
Con una interfaz única, cada implementación tendría que romperse con
`NotImplementedError` en la mitad de sus métodos — y el motor no podría saber, sin
probar, si el proveedor que le pasaron sirve. Separadas, el tipo lo dice todo:
si una función pide un `VoiceProvider`, cualquier cosa que reciba sabe narrar.

Son `Protocol` y no clases base: un proveedor no necesita heredar de nada ni conocer
este módulo. Alcanza con tener los métodos correctos (tipado estructural).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from engine.core.models.story import Story


@runtime_checkable
class TextProvider(Protocol):
    """Genera texto. Lo usa el escritor de narración y diálogo."""

    async def generate_text(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Devuelve el texto generado.

        Lanza `ProviderUnavailableError` si es una falla transitoria (reintentable) y
        `ProviderRefusedError` si el pedido fue rechazado (no reintentar igual).
        """
        ...


@runtime_checkable
class ImageProvider(Protocol):
    """Genera imágenes. Lo usa el ilustrador de escenas."""

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_images: list[bytes] | None = None,
        width: int = 1024,
        height: int = 1024,
    ) -> bytes:
        """Devuelve los bytes de la imagen.

        `reference_images` es clave para la consistencia: se le pasan las imágenes ya
        aprobadas del personaje y del estilo para que la escena nueva no reinvente
        cómo se ven.
        """
        ...


@runtime_checkable
class VoiceProvider(Protocol):
    """Convierte texto en audio narrado."""

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        speed: float = 1.0,
        audio_format: str = "wav",
    ) -> bytes:
        """Devuelve los bytes del audio.

        El formato por defecto es WAV y no mp3 a propósito: el motor necesita MEDIR
        cuánto dura cada pista para que la imagen no cambie antes de que termine la
        frase, y la stdlib de Python sabe leer la duración de un WAV pero no la de un
        mp3. Poder medir sin sumar una dependencia vale más que el tamaño del archivo,
        que además es temporal — el render comprime al final.

        Mismas excepciones que el resto: `ProviderUnavailableError` si es transitorio,
        `ProviderRefusedError` si el pedido fue rechazado.
        """
        ...


@runtime_checkable
class StoryRepository(Protocol):
    """Persistencia de historias.

    El core no sabe si atrás hay PostgreSQL, SQLite o un JSON en disco. Eso permite
    testear todo el motor con un repositorio en memoria, sin levantar una base.
    """

    async def save(self, story: Story) -> None: ...

    async def get(self, story_id: UUID) -> Story | None: ...

    async def delete(self, story_id: UUID) -> None: ...
