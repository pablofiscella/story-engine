"""Proveedores falsos, para testear el motor entero sin gastar un peso.

No son "mocks de mentira": producen texto plausible y respetan el contrato real
(incluido el límite de palabras). Con esto se puede correr el pipeline completo mil
veces en CI, y probar los casos que con un modelo real son carísimos de reproducir:
que se pase de largo, que devuelva vacío, que falle.
"""

from __future__ import annotations

import io
import re
import wave

from engine.core.exceptions import ProviderRefusedError, ProviderUnavailableError

_FRASES = [
    "El sol se colaba entre las hojas y todo parecía a punto de empezar",
    "Nadie se lo esperaba, pero así fue como pasó",
    "Se quedó quieto un momento, pensando qué hacer",
    "Y entonces algo cambió, despacito",
    "No hizo falta decir nada más",
    "Fue como si el día entero se pusiera contento",
]


class FakeTextProvider:
    """Devuelve texto que respeta el presupuesto de palabras del pedido.

    Lee el "MÁXIMO N palabras" del prompt y se ajusta — así el escritor se prueba de
    verdad, en vez de contra un provider que siempre devuelve lo mismo.
    """

    def __init__(self, *, obedece_limite: bool = True) -> None:
        self.obedece_limite = obedece_limite
        self.llamadas: list[str] = []

    async def generate_text(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        self.llamadas.append(prompt)
        tope = _tope_del_prompt(prompt)
        semilla = len(self.llamadas) - 1
        frase = _FRASES[semilla % len(_FRASES)]
        if not self.obedece_limite:
            # simula el vicio real del modelo: escribir de más
            return (frase + ", ") * 6
        palabras = frase.split()[:tope]
        return " ".join(palabras) + "."


class ProviderQueCae:
    """Falla siempre. Para probar que el motor no se rompe feo cuando el mundo falla."""

    def __init__(self, *, refused: bool = False) -> None:
        self.refused = refused
        #: Cuántas veces se le pidió. Sirve para verificar que se reintentó —o que
        #: NO se reintentó, cuando el rechazo es de contenido.
        self.llamadas: list[str] = []

    async def generate_text(self, prompt: str, **kwargs: object) -> str:
        self.llamadas.append(prompt)
        if self.refused:
            raise ProviderRefusedError("El contenido fue rechazado por el filtro del proveedor.")
        raise ProviderUnavailableError("503 del proveedor.")


class ProviderVacio:
    """Devuelve cadena vacía: pasa de verdad y hay que manejarlo."""

    async def generate_text(self, prompt: str, **kwargs: object) -> str:
        return "   "


def _tope_del_prompt(prompt: str) -> int:
    m = re.search(r"M[ÁA]XIMO\s+(\d+)\s+palabras", prompt, re.IGNORECASE)
    return int(m.group(1)) if m else 12


class FakeImageProvider:
    """Devuelve un PNG mínimo válido y ANOTA con qué referencias se lo llamó.

    Lo que importa testear del ilustrador no es la imagen (no la podemos evaluar en
    un test) sino que cada escena reciba las referencias correctas. Por eso este
    provider guarda las llamadas.
    """

    #: PNG de 1×1 transparente. Suficiente para que Pillow y el disco lo acepten.
    PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
        b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def __init__(self) -> None:
        self.llamadas: list[dict] = []

    async def generate_image(
        self,
        prompt: str,
        *,
        reference_images: list[bytes] | None = None,
        width: int = 1024,
        height: int = 1024,
    ) -> bytes:
        self.llamadas.append(
            {"prompt": prompt, "refs": list(reference_images or []), "size": (width, height)}
        )
        # imagen distinta por llamada, para poder seguirle el rastro a las anclas
        return self.PNG + str(len(self.llamadas)).encode()


#: Igual que en el proveedor real: lo que va entre corchetes se actúa, no se lee.
_ETIQUETA = re.compile(r"\[[^\]]{1,300}\]")


class FakeVoiceProvider:
    """Devuelve un WAV real, con la duración que le correspondería a ese texto.

    No es un archivo cualquiera: dura lo que tardaría en decirse a `palabras_por_s`.
    Eso permite probar de verdad el guardián de duración —que una escena se pase, que
    la suma no cierre— sin gastar un peso en TTS y sin depender de la velocidad real
    de un proveedor, que cambia según la voz.

    `palabras_por_s` es el parámetro que importa: bajándolo se simula una voz lenta,
    que es el caso que rompe el timing del video.
    """

    def __init__(self, *, palabras_por_s: float = 2.5) -> None:
        self.palabras_por_s = palabras_por_s
        self.llamadas: list[dict] = []

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        speed: float = 1.0,
        audio_format: str = "wav",
    ) -> bytes:
        self.llamadas.append({"text": text, "voice_id": voice_id, "speed": speed})
        # Las etiquetas de entonación no se DICEN: son instrucciones de actuación.
        # Contarlas como palabras haría que el fake mintiera sobre la duración, que es
        # justo lo que este provider existe para simular bien.
        dicho = _ETIQUETA.sub("", text)
        segundos = max(0.1, len(dicho.split()) / (self.palabras_por_s * speed))
        return _wav_silencioso(segundos)


def _wav_silencioso(segundos: float, *, fps: int = 22050) -> bytes:
    """Un WAV mono válido de `segundos` de silencio.

    Se arma con `wave` de la stdlib para que sea un archivo de verdad: si el motor
    lo mide mal, el test falla acá y no en producción.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fps)
        w.writeframes(b"\x00\x00" * int(fps * segundos))
    return buf.getvalue()
