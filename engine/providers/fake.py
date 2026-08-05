"""Proveedores falsos, para testear el motor entero sin gastar un peso.

No son "mocks de mentira": producen texto plausible y respetan el contrato real
(incluido el límite de palabras). Con esto se puede correr el pipeline completo mil
veces en CI, y probar los casos que con un modelo real son carísimos de reproducir:
que se pase de largo, que devuelva vacío, que falle.
"""

from __future__ import annotations

import re

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

    async def generate_text(self, prompt: str, **kwargs: object) -> str:
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
