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
_IMAGE_EDITS = "https://api.openai.com/v1/images/edits"

#: Códigos que valen un reintento: el problema es del otro lado y es pasajero.
_TRANSITORIOS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class OpenAIProvider:
    """Texto e imagen contra la API de OpenAI."""

    def __init__(
        self,
        api_key: str,
        *,
        text_model: str = "gpt-4o-mini",
        image_model: str = "gpt-image-2",
        timeout: int = 90,
    ) -> None:
        if not api_key:
            raise ValueError("Falta la API key de OpenAI.")
        self._key = api_key
        self._text_model = text_model
        self._image_model = image_model
        self._timeout = timeout

    @property
    def cache_fingerprint(self) -> str:
        """Qué determina el resultado, además del pedido. Va en la clave del caché.

        Sin esto, cambiar de modelo devolvería lo generado con el anterior como si
        fuera nuevo — el bug del caché de TTS que no llevaba la voz en la clave.
        """
        return f"openai:{self._text_model}:{self._image_model}"

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
        """Con referencias usa /images/edits; sin ellas, /images/generations.

        Son dos endpoints distintos porque hacen dos cosas distintas: generar de cero
        acepta JSON, y editar a partir de imágenes exige multipart. Las referencias son
        el mecanismo que mantiene al personaje igual entre escenas, así que este camino
        es el normal, no el excepcional.
        """
        if reference_images:
            data = await self._post_multipart(prompt, reference_images, width, height)
        else:
            data = await self._post(
                _IMAGES,
                {
                    "model": self._image_model,
                    "prompt": prompt,
                    "size": f"{width}x{height}",
                    "n": 1,
                },
            )
        try:
            item = data["data"][0]
        except (KeyError, IndexError) as e:
            raise ProviderUnavailableError(f"Respuesta inesperada de OpenAI: {e}") from e
        if "b64_json" in item:
            return base64.b64decode(item["b64_json"])
        raise ProviderUnavailableError("OpenAI no devolvió la imagen en base64.")

    async def _post_multipart(
        self, prompt: str, refs: list[bytes], width: int, height: int
    ) -> dict:
        from engine.providers.multipart import build

        campos = {
            "model": self._image_model,
            "prompt": prompt,
            "size": f"{width}x{height}",
            "n": "1",
        }
        # `image[]` y no `image`: con varias referencias, repetir `image` devuelve
        # 400 "Duplicate parameter". Verificado contra la API real.
        archivos = [("image[]", f"ref{i}.png", raw) for i, raw in enumerate(refs)]
        ctype, cuerpo = build(campos, archivos)
        return await asyncio.to_thread(self._post_raw, _IMAGE_EDITS, cuerpo, ctype)

    def _post_raw(self, url: str, cuerpo: bytes, content_type: str) -> dict:
        req = urllib.request.Request(
            url,
            data=cuerpo,
            method="POST",
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detalle = _detalle(e)
            if e.code in _TRANSITORIOS:
                raise ProviderUnavailableError(f"OpenAI {e.code}: {detalle}") from e
            raise ProviderRefusedError(f"OpenAI {e.code}: {detalle}") from e
        except (TimeoutError, urllib.error.URLError) as e:
            raise ProviderUnavailableError(f"No se pudo llegar a OpenAI: {e}") from e

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
