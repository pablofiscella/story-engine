"""Proveedor de voz de ElevenLabs.

Implementa `VoiceProvider`. Todo lo que sigue salió de la experiencia con los
audiolibros de Casatridimensional, que es el mismo proveedor con las mismas trampas.

**Nunca cae a otro proveedor.** El motor viejo tenía un `tts_mp3()` que ante una falla
de ElevenLabs pasaba a OpenAI en silencio: no fallaba, cambiaba de voz. Se escucharon
audios "nuevos" con otra voz sin que nadie se enterara. Acá una falla es una falla; el
que llama decide si reintenta o si cambia de proveedor, y se entera de que lo hizo.

**El modelo decide si las etiquetas se dicen o se actúan.** `[warmly]`, `[whispers]`
son de `eleven_v3`; en `eleven_multilingual_v2` **se leen en voz alta** — el narrador
dice "corchete warmly". Por eso este proveedor sabe qué modelo tiene y limpia las
etiquetas cuando no las soporta, en vez de confiar en que quien llame se acuerde. Es
la misma regla que las del prompt de imagen: una decisión no puede depender de que
otra parte del sistema la recuerde.

**El acento rioplatense sale del TEXTO, no de la voz.** El voseo lo pone el escritor
(`prompts/narration.py`); no hay una voz "argentina" que arregle un texto en tuteo.

Sin SDK: son dos endpoints HTTP.
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request

from engine.core.exceptions import ProviderRefusedError, ProviderUnavailableError

_TTS = "https://api.elevenlabs.io/v1/text-to-speech"

#: Códigos que valen un reintento: el problema es del otro lado y es pasajero.
_TRANSITORIOS = frozenset({408, 429, 500, 502, 503, 504})

#: Voz por defecto: **Lizy**. La eligió Pablo el 5-ago-2026 escuchando el mismo
#: cuento narrado en cuatro configuraciones (Valeria con estabilidad 0.5 y 0.3,
#: Malena y Lizy), todas con la misma dirección de cuentacuentos.
#:
#: **Difiere a propósito de la línea de Casatridimensional**, que usa Valeria desde
#: el 25-jul-2026 para audiolibros y actividades. No es un descuido: son productos
#: distintos. Un audiolibro se escucha entero y de a ratos; un short tiene tres
#: segundos para enganchar. Se eligió por separado y escuchando.
VOZ_POR_DEFECTO = "rrErIO88ehxTnspOjKvf"

#: Estabilidad baja: le da permiso al modelo para emocionarse — sube el tono en las
#: partes divertidas y lo baja en las tristes. Es la perilla de la receta de cuento
#: infantil, y la que Pablo eligió al comparar. Más alta suena más consistente pero
#: más plana, que es exactamente lo que había que arreglar.
ESTABILIDAD_CUENTO = 0.3

#: Modelos y si entienden las etiquetas de emoción entre corchetes.
_ETIQUETAS_SOPORTADAS: dict[str, bool] = {
    "eleven_v3": True,
    "eleven_multilingual_v2": False,
    "eleven_turbo_v2_5": False,
}

#: `eleven_v3` ignora `speed`. Pedirlo igual no rompe, pero creer que se aplicó sí:
#: una escena que "se aceleró un 10%" y en realidad no, desincroniza el video.
_ACEPTAN_SPEED = frozenset({"eleven_multilingual_v2", "eleven_turbo_v2_5"})

#: `style` amplifica la expresividad y sólo existe en v2. Es la perilla que la receta
#: de cuento infantil manda subir (0.15–0.5) para el tono exagerado que se usa al
#: leerle a un chico.
_ACEPTAN_STYLE = frozenset({"eleven_multilingual_v2"})

#: Cualquier bloque entre corchetes es dirección de actuación, no texto a decir.
#: El tope es generoso porque la dirección de escena es una frase entera, no una
#: palabra: con un límite corto se colaba al audio y el narrador la leía.
_ETIQUETA = re.compile(r"\[[^\]]{1,300}\]")

#: Formatos de salida por extensión, con su frecuencia de muestreo.
#:
#: El motor pide WAV porque necesita MEDIR la duración con la stdlib; el mp3 queda
#: para cuando el render ya comprime.
#:
#: **24 kHz y no 44.1 kHz por un límite de plan**, verificado contra la cuenta real
#: (5-ago-2026): `pcm_44100` devuelve *"only available on the Pro tier and above"*.
#: Funcionan `pcm_24000`, `pcm_22050` y `pcm_16000`. 24 kHz es de sobra para voz —la
#: voz humana no pasa de ~8 kHz— así que el límite no cuesta calidad audible. Si algún
#: día hay plan Pro, se sube acá y nada más.
_FORMATOS: dict[str, tuple[str, int]] = {
    "wav": ("pcm_24000", 24000),
    "mp3": ("mp3_44100_128", 0),
}


class ElevenLabsProvider:
    """Voz contra la API de ElevenLabs."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "eleven_v3",
        default_voice_id: str = VOZ_POR_DEFECTO,
        stability: float = ESTABILIDAD_CUENTO,
        similarity: float = 0.8,
        style: float = 0.0,
        timeout: int = 120,
    ) -> None:
        if not api_key:
            raise ValueError("Falta la API key de ElevenLabs.")
        self._key = api_key
        self._model = model
        self._voz = default_voice_id
        self._stability = stability
        self._similarity = similarity
        self._style = style
        self._timeout = timeout

    @property
    def soporta_etiquetas(self) -> bool:
        """Si el modelo actúa las etiquetas `[warmly]` o las lee en voz alta."""
        return _ETIQUETAS_SOPORTADAS.get(self._model, False)

    @property
    def cache_fingerprint(self) -> str:
        """Modelo y ajustes: cambiarlos cambia cómo suena, así que cambia la clave."""
        return f"elevenlabs:{self._model}:{self._stability}:{self._similarity}:{self._style}"

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        speed: float = 1.0,
        audio_format: str = "wav",
    ) -> bytes:
        """Los bytes del audio. WAV por defecto para poder medir la duración."""
        if audio_format not in _FORMATOS:
            raise ValueError(
                f"Formato '{audio_format}' desconocido. Hay: {sorted(_FORMATOS)}."
            )
        if not self.soporta_etiquetas:
            text = _ETIQUETA.sub("", text).strip()

        cuerpo: dict[str, object] = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": self._stability,
                "similarity_boost": self._similarity,
            },
        }
        if self._style and self._model in _ACEPTAN_STYLE:
            cuerpo["voice_settings"] = {
                **cuerpo["voice_settings"],  # type: ignore[dict-item]
                "style": self._style,
                "use_speaker_boost": True,
            }
        if speed != 1.0 and self._model in _ACEPTAN_SPEED:
            cuerpo["voice_settings"] = {**cuerpo["voice_settings"], "speed": speed}  # type: ignore[dict-item]

        codigo, fps = _FORMATOS[audio_format]
        url = f"{_TTS}/{voice_id or self._voz}?output_format={codigo}"
        crudo = await asyncio.to_thread(self._post_sync, url, cuerpo)
        # El PCM viene sin cabecera, pelado. Se le pone la de WAV acá para que el resto
        # del motor reciba siempre un archivo que se puede medir y abrir.
        return _envolver_wav(crudo, fps=fps) if audio_format == "wav" else crudo

    # ------------------------------------------------------------------------
    def _post_sync(self, url: str, cuerpo: dict[str, object]) -> bytes:
        req = urllib.request.Request(
            url,
            data=json.dumps(cuerpo).encode(),
            method="POST",
            headers={"xi-api-key": self._key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            detalle = _detalle(e)
            if e.code in _TRANSITORIOS:
                raise ProviderUnavailableError(f"ElevenLabs {e.code}: {detalle}") from e
            raise ProviderRefusedError(f"ElevenLabs {e.code}: {detalle}") from e
        except (TimeoutError, urllib.error.URLError) as e:
            raise ProviderUnavailableError(f"No se pudo llegar a ElevenLabs: {e}") from e


def _envolver_wav(pcm: bytes, *, fps: int, canales: int = 1, ancho: int = 2) -> bytes:
    """La cabecera WAV que le falta al PCM crudo.

    Se escribe a mano y no con `wave` para no copiar el audio dos veces en memoria.
    """
    import struct

    bloque = canales * ancho
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(pcm))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, canales, fps, fps * bloque, bloque, ancho * 8)
        + b"data"
        + struct.pack("<I", len(pcm))
        + pcm
    )


def _detalle(e: urllib.error.HTTPError) -> str:
    """El mensaje de error, sin que se filtre la API key al log."""
    try:
        cuerpo = json.loads(e.read())
    except Exception:
        return e.reason or "sin detalle"
    detalle = cuerpo.get("detail", cuerpo)
    if isinstance(detalle, dict):
        return str(detalle.get("message") or detalle.get("status") or detalle)
    return str(detalle)
