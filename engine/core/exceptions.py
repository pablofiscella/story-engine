"""Errores del motor.

Todos cuelgan de `StoryEngineError`, así quien consume el motor puede capturar
una sola cosa. La distinción que importa: un error de DOMINIO (la historia está
mal armada, culpa nuestra) no es lo mismo que un error de PROVEEDOR (OpenAI se
cayó, culpa de afuera y probablemente se reintenta).
"""

from __future__ import annotations


class StoryEngineError(Exception):
    """Base de todos los errores del motor."""


# --- Dominio: la historia está mal armada ---------------------------------------


class DomainError(StoryEngineError):
    """Algo del contenido no cierra. Reintentar no ayuda: hay que corregirlo."""


class InvalidArcError(DomainError):
    """El plan no respeta el arco narrativo canónico."""


class InvalidDurationError(DomainError):
    """Las duraciones no cierran contra el objetivo de la historia."""


class UnknownCharacterError(DomainError):
    """Una escena referencia un personaje que no está en el elenco de la historia.

    Es EL error que más rompe la consistencia visual: si la escena 4 nombra a un
    personaje que nadie definió, el generador de imágenes lo inventa distinto cada vez.
    """


class InvalidStateTransitionError(DomainError):
    """Se intentó saltar una etapa del pipeline (ej: renderizar sin narrar)."""


# --- Infra: el mundo de afuera falló --------------------------------------------


class ProviderError(StoryEngineError):
    """Un proveedor externo (texto, imagen, voz) falló."""


class ProviderUnavailableError(ProviderError):
    """Falla transitoria: rate limit, 5xx, timeout. Tiene sentido reintentar."""


class ProviderRefusedError(ProviderError):
    """El proveedor rechazó el pedido (moderación, prompt inválido).

    NO se reintenta con el mismo input: hay que cambiar el prompt. Separarlo de
    `ProviderUnavailableError` evita el bug clásico de reintentar 5 veces contra
    un filtro de contenido y quemar cuota al pedo.
    """
