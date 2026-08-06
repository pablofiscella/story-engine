"""No pagar dos veces por lo mismo.

El día que se ilustró el primer cuento se pagaron **27 imágenes para 6 que quedaron
en el producto**: 4,5 veces de más. No fue por el precio unitario — fue porque cada
corrección rehacía la historia entera. Se arreglaba la escena 4 y se volvían a pagar
las otras cinco, que no habían cambiado.

Estos envoltorios lo resuelven de la forma más aburrida posible: si el pedido es
idéntico a uno que ya se hizo, devuelven lo de antes. Envuelven a cualquier proveedor
sin que el motor se entere, porque cumplen el mismo Protocol.

    provider = CachedImageProvider(OpenAIProvider(key), "cache/imagenes")

**La clave incluye TODO lo que cambia el resultado.** Esto no es paranoia: el caché
de TTS de Casatridimensional no lleva la voz en la clave, y cuando se cambió la voz
por defecto los videos "nuevos" siguieron sonando con la vieja. Un caché que ignora un
parámetro no falla — **devuelve algo viejo con cara de nuevo**, que es peor.

Por eso los proveedores declaran `cache_fingerprint`: el modelo y los ajustes con los
que fueron construidos. Cambiar de modelo o de estabilidad cambia la clave y el caché
no miente.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from engine.core.interfaces import ImageProvider, VoiceProvider

#: Se puede mover el caché de disco sin tocar código.
VARIABLE_DE_ENTORNO = "STORY_ENGINE_CACHE"


def directorio_por_defecto() -> Path:
    """Dónde vive el caché cuando quien llama no dice otra cosa. **Nunca `/tmp`.**

    El 5-ago-2026 el caché de un día entero de trabajo vivía en `/tmp`. Se reinició la
    máquina y se lo llevó entero: las seis imágenes del cuento —ya pagadas— hubo que
    volver a comprarlas, que es exactamente lo que este módulo existe para evitar.

    Un caché en un directorio que el sistema borra solo no es un caché: es una demora.
    """
    return Path(os.environ.get(VARIABLE_DE_ENTORNO) or Path.home() / ".cache" / "story-engine")


class _Base:
    """Lo común: dónde guarda, cómo cuenta y cómo se olvida de algo."""

    def __init__(
        self,
        inner: object,
        cache_dir: str | Path | None = None,
        *,
        extension: str,
        carpeta: str,
    ) -> None:
        self._inner = inner
        self._dir = Path(cache_dir) if cache_dir is not None else directorio_por_defecto() / carpeta
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ext = extension
        #: Para poder decir cuánto se ahorró, que si no es una promesa sin número.
        self.hits = 0
        self.misses = 0

    @property
    def _firma(self) -> str:
        """Qué proveedor y con qué ajustes. Va en la clave sí o sí."""
        return str(getattr(self._inner, "cache_fingerprint", type(self._inner).__name__))

    def _ruta(self, *partes: object) -> Path:
        h = hashlib.sha256()
        h.update(self._firma.encode())
        for parte in partes:
            h.update(b"\x00")
            h.update(parte if isinstance(parte, bytes) else str(parte).encode())
        return self._dir / f"{h.hexdigest()[:32]}{self._ext}"

    @property
    def ahorro(self) -> str:
        """Una línea para el log: cuántos pedidos no se pagaron."""
        total = self.hits + self.misses
        pct = f"{self.hits / total:.0%}" if total else "—"
        return f"{self.hits} de {total} pedidos salieron del caché ({pct})"


class CachedImageProvider(_Base):
    """Un `ImageProvider` que no vuelve a pagar una imagen que ya generó."""

    def __init__(self, inner: ImageProvider, cache_dir: str | Path | None = None) -> None:
        super().__init__(inner, cache_dir, extension=".png", carpeta="imagenes")

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_images: list[bytes] | None = None,
        width: int = 1024,
        height: int = 1024,
    ) -> bytes:
        # Las referencias van en la clave por su contenido: la MISMA escena con otro
        # personaje de ancla da otra imagen, y devolver la vieja sería mentir.
        refs = [hashlib.sha256(r).hexdigest() for r in (reference_images or [])]
        ruta = self._ruta("img", prompt, width, height, *refs)

        if ruta.exists():
            self.hits += 1
            return ruta.read_bytes()

        self.misses += 1
        img = await self._inner.generate_image(
            prompt, reference_images=reference_images, width=width, height=height
        )
        ruta.write_bytes(img)
        return img


class CachedVoiceProvider(_Base):
    """Un `VoiceProvider` que no vuelve a pagar una toma que ya sintetizó.

    El TTS se paga por caracter, así que rehacer una historia por un error en la
    escena 4 pagaba de nuevo las seis narraciones.
    """

    def __init__(self, inner: VoiceProvider, cache_dir: str | Path | None = None) -> None:
        super().__init__(inner, cache_dir, extension=".wav", carpeta="voz")

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        speed: float = 1.0,
        audio_format: str = "wav",
    ) -> bytes:
        # `voice_id` en la clave. Es EL bug del caché viejo: sin esto, cambiar la voz
        # por defecto devolvía los audios de la voz anterior como si fueran nuevos.
        ruta = self._ruta("voz", text, voice_id, speed, audio_format)

        if ruta.exists():
            self.hits += 1
            return ruta.read_bytes()

        self.misses += 1
        audio = await self._inner.synthesize(
            text, voice_id=voice_id, speed=speed, audio_format=audio_format
        )
        ruta.write_bytes(audio)
        return audio
