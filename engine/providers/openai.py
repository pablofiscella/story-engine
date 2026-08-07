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
_TRANSCRIPTIONS = "https://api.openai.com/v1/audio/transcriptions"

#: Códigos que valen un reintento: el problema es del otro lado y es pasajero.
_TRANSITORIOS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

#: Las calidades de imagen que acepta el modelo, de más barata a más cara.
CALIDADES = ("low", "medium", "high")

#: Con qué calidad se pide una imagen si nadie dice lo contrario.
#:
#: Es LA palanca del costo: un short son 6 imágenes, y a 3 shorts por día la cuenta del
#: mes cambia de orden de magnitud según esto. Pablo, 5-ago-2026: *"a 1 dólar el short
#: son 100 dólares al mes por 3 videos por día. Es inviable"*.
#:
#: Queda en `low` porque Pablo comparó los dos shorts enteros —el mismo cuento, el mismo
#: audio, sólo cambiando esto— y dijo *"se ve bien en la resolución baja"*. No es una
#: estimación: es el producto terminado mirado al lado del caro.
#:
#: Lo que se mira en un teléfono, en vertical, con fundidos de 0,4s y texto encima, no es
#: una lámina para imprimir. Subirlo es una decisión que hay que justificar mirando las
#: dos, no algo que se herede del default de la API.
CALIDAD_POR_DEFECTO = "low"

#: Con qué modelo se MIRA una imagen ya generada, para verificarla.
#:
#: No es el mismo que la genera ni el que escribe: revisar es otro trabajo. Se eligió
#: midiendo contra los tres errores de anatomía reales del lote del 7-ago-2026 (una
#: mano de más y dos casos de patas de más, sobre 48 imágenes):
#:
#: | modelo   | los 3 defectos | falsos positivos sobre 5 sanas |
#: |----------|----------------|--------------------------------|
#: | gpt-4o   | 0 de 3         | 0 |
#: | gpt-4.1  | 0 de 3         | 0 |
#: | gpt-5.2  | 1 de 3         | 0 |
#:
#: `gpt-4o` contesta *"4 extremidades, anatomía ok"* en las tres imágenes rotas: no
#: discrimina nada. `gpt-5.2` es el único que encuentra algo, y sin equivocarse nunca
#: sobre una imagen sana — que es lo que permite rehacer sin miedo.
MODELO_DE_VISION = "gpt-5.2"

#: Con qué modelo se ESCUCHA una toma ya grabada, para verificar la pronunciación.
MODELO_DE_TRANSCRIPCION = "gpt-4o-transcribe"


class OpenAIProvider:
    """Texto e imagen contra la API de OpenAI."""

    def __init__(
        self,
        api_key: str,
        *,
        text_model: str = "gpt-4o-mini",
        image_model: str = "gpt-image-2",
        vision_model: str = MODELO_DE_VISION,
        transcription_model: str = MODELO_DE_TRANSCRIPCION,
        image_quality: str = CALIDAD_POR_DEFECTO,
        timeout: int = 90,
    ) -> None:
        if not api_key:
            raise ValueError("Falta la API key de OpenAI.")
        if image_quality not in CALIDADES:
            raise ValueError(f"Calidad de imagen desconocida: {image_quality!r}. {CALIDADES}")
        self._key = api_key
        self._text_model = text_model
        self._image_model = image_model
        self._vision_model = vision_model
        self._transcription_model = transcription_model
        self._image_quality = image_quality
        self._timeout = timeout

    @property
    def cache_fingerprint(self) -> str:
        """Qué determina el resultado, además del pedido. Va en la clave del caché.

        Sin esto, cambiar de modelo devolvería lo generado con el anterior como si
        fuera nuevo — el bug del caché de TTS que no llevaba la voz en la clave.

        La calidad va acá por lo mismo: bajarla y recibir las imágenes caras de antes
        haría creer que se abarató algo que no se abarató.
        """
        return f"openai:{self._text_model}:{self._image_model}:{self._image_quality}"

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

    async def transcribe(self, audio: bytes, *, language: str = "es") -> str:
        """Lo que se ENTIENDE del audio.

        Lo usa el guardián de pronunciación del narrador: es la única forma de saber
        si la toma dijo "Dino" o dijo "Nino", porque el archivo suena igual de sano en
        los dos casos.

        Se declara `audio/wav` en el multipart: mandarlo como `image/png` funciona
        —OpenAI mira la extensión del nombre— pero es de las cosas que andan hasta que
        alguien del otro lado deja de ser amable.
        """
        from engine.providers.multipart import build

        campos = {"model": self._transcription_model, "language": language,
                  "response_format": "json"}
        ctype, cuerpo = build(
            campos, [("file", "toma.wav", audio)], content_type="audio/wav"
        )
        data = await asyncio.to_thread(self._post_raw, _TRANSCRIPTIONS, cuerpo, ctype)
        return str(data.get("text", ""))

    async def inspect_image(
        self,
        prompt: str,
        images: list[bytes],
        *,
        system: str | None = None,
    ) -> str:
        """Le pregunta a un modelo de VISIÓN qué ve en estas imágenes.

        Es el mismo endpoint de chat que el texto: la imagen viaja como `data:` URL
        adentro del mensaje. Se pide `detail: high` a propósito — con `low` la imagen
        se reduce a 85 tokens y contar patas se vuelve imposible.

        `temperature` no se manda: los modelos de razonamiento sólo aceptan el valor
        por defecto y este pedido es una medición, no una redacción.
        """
        contenido: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        for raw in images:
            contenido.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64.b64encode(raw).decode()}",
                        "detail": "high",
                    },
                }
            )
        mensajes: list[dict[str, object]] = []
        if system:
            mensajes.append({"role": "system", "content": system})
        mensajes.append({"role": "user", "content": contenido})

        data = await self._post(
            _CHAT, {"model": self._vision_model, "messages": mensajes}
        )
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
                    "quality": self._image_quality,
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
            "quality": self._image_quality,
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
