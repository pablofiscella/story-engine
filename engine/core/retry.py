"""Reintentos ante fallas transitorias del proveedor.

El dominio ya distingue una caída pasajera (`ProviderUnavailableError`: un 500, un
rate limit, un timeout) de un rechazo de contenido (`ProviderRefusedError`, que
reintentar solo quema cuota). Faltaba usar esa distinción: un 500 de OpenAI en la
escena 3 tiraba abajo la historia entera y las dos imágenes ya pagadas.

Para publicar 10 shorts por día sin nadie mirando, eso no alcanza. La política vive
acá y no adentro del proveedor a propósito: quien llama es el que sabe cuánto vale
la pena esperar. Ilustrar una escena cuesta plata y vale la pena insistir; un ping
de healthcheck, no.

Espera exponencial y no fija: si el proveedor está saturado, insistir cada un segundo
es parte del problema.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from engine.core.exceptions import ProviderUnavailableError

#: Cuántas veces se vuelve a intentar antes de rendirse. Tres alcanzan: los 5xx de
#: OpenAI duran segundos, y si dura más que eso no es un pico sino una caída.
INTENTOS = 3

#: Segundos de la primera espera. Las siguientes duplican: 2, 4, 8.
ESPERA_BASE_S = 2.0


async def con_reintentos[T](
    accion: Callable[[], Awaitable[T]],
    *,
    intentos: int = INTENTOS,
    espera_base_s: float = ESPERA_BASE_S,
    al_reintentar: Callable[[int, Exception], None] | None = None,
) -> T:
    """Ejecuta `accion`, reintentando solo las fallas transitorias.

    `ProviderRefusedError` y cualquier otro error suben en el acto: reintentar contra
    un filtro de contenido no lo va a convencer.

    `al_reintentar(intento, error)` sirve para dejar rastro de que hubo que insistir
    — si no, una historia que costó el triple parece haber salido a la primera.
    """
    ultimo: ProviderUnavailableError | None = None
    for intento in range(1, intentos + 1):
        try:
            return await accion()
        except ProviderUnavailableError as e:
            ultimo = e
            if intento == intentos:
                break
            if al_reintentar is not None:
                al_reintentar(intento, e)
            await asyncio.sleep(espera_base_s * 2 ** (intento - 1))
    assert ultimo is not None
    raise ultimo
