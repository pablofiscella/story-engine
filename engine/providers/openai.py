"""Proveedor de OpenAI.

Implementa `TextProvider` e `ImageProvider` sin que el core se entere de que existe.
El día que convenga cambiar de modelo o de empresa, se escribe otra clase con estos
mismos dos métodos y el motor no cambia una línea.

Sin SDK a propósito: solo `urllib`. Son dos endpoints HTTP y el SDK trae un árbol de
dependencias que después hay que mantener.
"""

from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
import urllib.request

from engine.core.exceptions import ProviderRefusedError, ProviderUnavailableError

_CHAT = "https://api.openai.com/v1/chat/completions"
_IMAGES = "https://api.openai.com/v1/images/generations"

#: Códigos que valen un reintento: el problema es del otro lado y es pasajero.
_TRANSITORIOS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class OpenAIProvider:
    """Texto e imagen contra la API de OpenAI."""

    def __init__(
        self,
        api_key: str,
        *,
        text_model: str = "gpt-4o-mini",
        image_model: str = "gpt-image-1",
        timeout: int = 90,
    ) -> None:
        if not api_key:
            raise ValueError("Falta la API key de OpenAI.")
        self._key = api_key
        self._text_model = text_model
        self._image_model = image_model
        self._timeout = timeout

    async def generate_text(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        mensajes = []
        if system:
            mensajes.append({"role": "system", "content": system})
        mensajes.append({"role": "user", "content": prompt})

        cuerpo: dict[str, object] = {
            "model": self._text_model,
            "messages": mensajes,
            "temperature": temperature,
        }
        if max_tokens:
            cuerpo["max_tokens"] = max_tokens

        data = await self._post(_CHAT, cuerpo)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise ProviderUnavailableError(f"Respuesta inesperada de OpenAI: {e}") from e

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_images: list[bytes] | None = None,
        width: int = 1024,
        height: int = 1024,
    ) -> bytes:
        # `reference_images` se ignora en este endpoint: la edición con referencias usa
        # /images/edits, que es multipart. Queda para cuando enganchemos el ilustrador
        # (Sprint 3), donde las referencias encadenadas son justamente el mecanismo que
        # mantiene al personaje igual entre escenas.
        cuerpo = {
            "model": self._image_model,
            "prompt": prompt,
            "size": f"{width}x{height}",
            "n": 1,
        }
        data = await self._post(_IMAGES, cuerpo)
        try:
            item = data["data"][0]
        except (KeyError, IndexError) as e:
            raise ProviderUnavailableError(f"Respuesta inesperada de OpenAI: {e}") from e
        if "b64_json" in item:
            return base64.b64decode(item["b64_json"])
        raise ProviderUnavailableError("OpenAI no devolvió la imagen en base64.")

    # ------------------------------------------------------------------------
    async def _post(self, url: str, cuerpo: dict[str, object]) -> dict:
        """POST en un hilo aparte: urllib es bloqueante y esto es una API async."""
        return await asyncio.to_thread(self._post_sync, url, cuerpo)

    def _post_sync(self, url: str, cuerpo: dict[str, object]) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(cuerpo).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detalle = _detalle(e)
            # La distinción importa de verdad: reintentar contra un filtro de
            # contenido quema cuota sin ninguna chance de que salga distinto.
            if e.code in _TRANSITORIOS:
                raise ProviderUnavailableError(f"OpenAI {e.code}: {detalle}") from e
            raise ProviderRefusedError(f"OpenAI {e.code}: {detalle}") from e
        except (TimeoutError, urllib.error.URLError) as e:
            raise ProviderUnavailableError(f"No se pudo llegar a OpenAI: {e}") from e


def _detalle(e: urllib.error.HTTPError) -> str:
    """El mensaje de error de OpenAI, sin que se filtre la API key al log."""
    try:
        d = json.loads(e.read())
        return str((d.get("error") or {}).get("message") or d)[:300]
    except Exception:
        return e.reason or "sin detalle"
