"""Proveedores: las implementaciones concretas de los contratos del core.

El core define QUÉ necesita (`TextProvider`, `ImageProvider`, `VoiceProvider`); acá
viven los que saben hacerlo de verdad. Cambiar de proveedor es escribir una clase
nueva — el motor no se entera.

`fake` permite correr el pipeline entero en tests, sin gastar ni depender de la red.
"""

from engine.providers.fake import FakeTextProvider

__all__ = ["FakeTextProvider"]
