"""Reintentos ante fallas transitorias.

El caso real: un 500 de OpenAI en la escena 3 tiró abajo la historia entera, con
las dos ilustraciones anteriores ya pagadas. El dominio SABÍA que era transitorio
—lo clasifica como `ProviderUnavailableError`— pero nadie reintentaba.
"""

from __future__ import annotations

import pytest

from engine.core.exceptions import (
    ProviderRefusedError,
    ProviderUnavailableError,
)
from engine.core.models import Character, Style, Theme
from engine.core.retry import con_reintentos
from engine.generators.illustrator import SceneIllustrator

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_insiste_hasta_que_sale() -> None:
    intentos = []

    async def falla_dos_veces():
        intentos.append(1)
        if len(intentos) < 3:
            raise ProviderUnavailableError("OpenAI 500")
        return "listo"

    assert await con_reintentos(falla_dos_veces, espera_base_s=0) == "listo"
    assert len(intentos) == 3


async def test_se_rinde_y_sube_el_ultimo_error() -> None:
    async def siempre_falla():
        raise ProviderUnavailableError("OpenAI 500")

    with pytest.raises(ProviderUnavailableError, match="500"):
        await con_reintentos(siempre_falla, intentos=2, espera_base_s=0)


async def test_un_rechazo_de_contenido_no_se_reintenta() -> None:
    """Insistir contra un filtro de moderación quema cuota sin ninguna chance."""
    intentos = []

    async def rechazado():
        intentos.append(1)
        raise ProviderRefusedError("moderación")

    with pytest.raises(ProviderRefusedError):
        await con_reintentos(rechazado, espera_base_s=0)
    assert len(intentos) == 1


async def test_un_error_de_dominio_tampoco_se_reintenta() -> None:
    intentos = []

    async def rota():
        intentos.append(1)
        raise ValueError("bug nuestro")

    with pytest.raises(ValueError):
        await con_reintentos(rota, espera_base_s=0)
    assert len(intentos) == 1


async def test_avisa_que_tuvo_que_insistir() -> None:
    """Si no, una historia que costó el triple parece haber salido a la primera."""
    avisos = []
    llamadas = []

    async def falla_una_vez():
        llamadas.append(1)
        if len(llamadas) == 1:
            raise ProviderUnavailableError("rate limit")
        return "ok"

    await con_reintentos(
        falla_una_vez, espera_base_s=0, al_reintentar=lambda n, e: avisos.append((n, str(e)))
    )
    assert avisos == [(1, "rate limit")]


async def test_la_historia_sobrevive_a_un_500_en_el_medio(
    tmp_path, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El caso real, de punta a punta: se cae una escena y la historia igual sale."""
    from engine.core.enums import EducationalValue
    from engine.engine import StoryEngine
    from engine.providers.fake import FakeImageProvider, FakeTextProvider

    historia = await StoryEngine(text_provider=FakeTextProvider()).generate(
        theme=tema_dinos, style=estilo_3d, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )

    class CaeUnaVez(FakeImageProvider):
        def __init__(self):
            super().__init__()
            self.caidas = 0

        async def generate_image(self, prompt, **kw):
            if self.caidas == 0 and "burbuja" in prompt:
                self.caidas += 1
                raise ProviderUnavailableError("OpenAI 500")
            return await super().generate_image(prompt, **kw)

    prov = CaeUnaVez()
    story = await SceneIllustrator(prov).illustrate(historia, tmp_path)
    assert prov.caidas == 1
    assert all(e.image_path for e in story.scenes)
