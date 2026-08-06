"""El storyboard: pensar las imágenes juntas, no una por una.

Pablo, mirando el primer lote de ocho shorts: *"hay que leer el fragmento de texto y
pensar bien la imagen y que tenga coherencia con las que siguen"*.

Lo que se prueba acá no es que el modelo escriba lindo —eso no se testea— sino que el
paso haga lo único que justifica su existencia: **ver todas las escenas de una vez**, y
que lo que devuelva no pueda romper las reglas de imagen que ya se ganaron mirando
salidas reales.
"""

from __future__ import annotations

import pytest

from engine.core.enums import EducationalValue
from engine.core.models import Character, Style, Theme
from engine.engine import StoryEngine
from engine.generators.storyboarder import Storyboarder
from engine.providers.fake import FakeTextProvider

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Dicta(FakeTextProvider):
    """Un proveedor que responde el storyboard que le digan, en el formato pedido."""

    def __init__(self, lineas: list[str]) -> None:
        super().__init__()
        self._respuesta = "\n".join(f"{i}| {t}" for i, t in enumerate(lineas))
        self.pedidos: list[str] = []

    async def generate_text(self, prompt, *, system=None, **kw):
        if "director de fotografía" in (system or ""):
            self.pedidos.append(prompt)
            return self._respuesta
        return await super().generate_text(prompt, system=system, **kw)


async def _escrita(tema, estilo, dino, tuca, provider=None):
    motor = StoryEngine(text_provider=provider or FakeTextProvider())
    return await motor.generate(
        theme=tema, style=estilo, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca], con_storyboard=False,
    )


# --- lo que justifica el paso ----------------------------------------------------


async def test_el_storyboard_ve_TODAS_las_escenas_de_una_vez(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Es lo único que este paso puede hacer y el resto del motor no. Un modelo que
    mira una escena por vez no puede dar continuidad, por buenas que sean sus
    respuestas: no sabe qué pasó antes ni qué viene después."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = Dicta([f"Dino en el claro, plano {i}, sostiene la pelota" for i in story.scenes])

    await Storyboarder(prov).draw(story)

    assert len(prov.pedidos) == 1, "un solo pedido con el cuento entero"
    pedido = prov.pedidos[0]
    for escena in story.scenes:
        assert escena.narration in pedido, "todas las escenas van en el mismo pedido"


async def test_la_puesta_en_escena_LLEGA_al_prompt_de_imagen(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El prompt de imagen se compone al escribir, cuando esto todavía no existe. Sin
    recomponerlo, la puesta en escena quedaría guardada en la escena y no llegaría
    nunca a la imagen: es "subir un asset al repo no es entregarlo", en prompt."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    prov = Dicta(["Dino agarra la pelota con las dos manos y mira al frente"] * len(story.scenes))

    await Storyboarder(prov).draw(story)

    for escena in story.scenes:
        assert escena.shot_description
        assert escena.shot_description in escena.image_prompt


# --- lo que NO puede hacer -------------------------------------------------------


async def test_no_puede_meter_un_personaje_que_no_esta_en_la_escena(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """La regla 1 —elenco cerrado— por la puerta de atrás. En el primer cuento apareció
    un dinosaurio que no era Rexo porque el prompt no decía cuántos había; no vamos a
    dejar que vuelva por una descripción."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    sola = next(e for e in story.scenes if len(e.character_ids) == 1)
    otro = next(
        c for cid, c in story.characters_by_id.items() if cid not in sola.character_ids
    )

    lineas = ["Dino sostiene la pelota contra el pecho"] * len(story.scenes)
    lineas[sola.index] = f"Dino juega mientras {otro.name} lo mira desde atrás del árbol"
    await Storyboarder(Dicta(lineas)).draw(story)

    assert sola.shot_description == "", "esa línea se descarta entera"
    assert otro.name not in sola.image_prompt.split("Puesta en escena")[-1]


@pytest.mark.parametrize(
    "descripcion",
    [
        "Dino mira la pelota bajo un cielo nublado",
        "Es de noche y Dino sostiene la pelota",
        "Empieza a llover mientras Dino se aleja",
        "La luz del atardecer cae sobre el claro",
    ],
)
async def test_no_puede_cambiar_el_clima_ni_la_hora(
    descripcion, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """La regla 2, que es la que más veces se rompió sola: el modelo traduce "triste" a
    "nublado" sin que nadie se lo pida. Pasó en la primera tirada del cuento de Dino y
    lo marcó Pablo."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    await Storyboarder(Dicta([descripcion] * len(story.scenes))).draw(story)

    assert all(e.shot_description == "" for e in story.scenes)


async def test_una_linea_ilegible_no_se_lleva_a_las_demas(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Lo que no se entiende, no se usa — y sólo esa escena se queda sin puesta."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)

    class MediaRota(FakeTextProvider):
        async def generate_text(self, prompt, *, system=None, **kw):
            if "director de fotografía" in (system or ""):
                return (
                    "Claro, acá va el storyboard:\n"
                    "0| Dino sostiene la pelota con las dos manos\n"
                    "esta línea no tiene formato\n"
                    "2| Dino deja la pelota en el pasto y se aleja\n"
                )
            return await super().generate_text(prompt, system=system, **kw)

    await Storyboarder(MediaRota()).draw(story)

    assert story.scenes[0].shot_description
    assert story.scenes[1].shot_description == ""
    assert story.scenes[2].shot_description


async def test_si_el_storyboard_falla_la_historia_sigue(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Una secuencia con saltos es peor que una con continuidad, pero es muchísimo
    mejor que no tener imágenes. Este paso no puede ser el que frene la producción."""
    story = await _escrita(tema_dinos, estilo_3d, dino, tuca)
    prompts_antes = [e.image_prompt for e in story.scenes]

    class SiempreFalla(FakeTextProvider):
        async def generate_text(self, prompt, *, system=None, **kw):
            if "director de fotografía" in (system or ""):
                raise RuntimeError("el proveedor se cayó")
            return await super().generate_text(prompt, system=system, **kw)

    await Storyboarder(SiempreFalla()).draw(story)

    assert all(e.shot_description == "" for e in story.scenes)
    assert [e.image_prompt for e in story.scenes] == prompts_antes
