"""El verificador de imágenes, probado con los casos que llegaron a Pablo.

Los tres errores de anatomía del lote del 7-ago-2026 —una mano de más en el final de
"honestidad", seis patas en el gancho de "paciencia" y en la cuarta de "valentia"— no
los detectó ningún test: los encontró un humano mirando los videos terminados. Cada
uno de esos casos está acá abajo escrito como respuesta del modelo de visión, para que
si el verificador deja de reaccionar a ellos, falle la suite y no el producto.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.generators.illustrator import SceneIllustrator
from engine.generators.inspector import ImageInspector, _campos, _correccion, _es, _reparos
from engine.providers.fake import (
    VISION_OK,
    FakeImageProvider,
    FakeVisionProvider,
    VisionQueCae,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

# --- Las respuestas REALES que dio el modelo mirando las imágenes del lote --------

#: "honestidad", última escena. Es el único de los tres que el modelo de visión
#: encuentra, y lo describe igual que Pablo: *"una mano de más"*.
MANO_DE_MAS = (
    "que_veo: el dinosaurio azul abraza al verde; en el abrazo se ven tres manos\n"
    "anatomia: rota\n"
    "cual: el dinosaurio azul tiene una mano/brazo de más (se aprecian tres "
    "manos/brazos en el abrazo)\n"
    "personajes: 2\n"
    "dia: si\n"
    "texto: no\n"
    "objeto: si"
)

#: Un tercer personaje que la historia no declaró. Es la regla 1 —elenco cerrado—, el
#: error del 5-ago: el modelo ascendía a personaje a un dinosaurio del fondo.
PERSONAJE_DE_MAS = (
    "que_veo: tres dinosaurios en el claro\n"
    "anatomia: ok\n"
    "cual: \n"
    "personajes: 3\n"
    "dia: si\n"
    "texto: no\n"
    "objeto: si"
)

#: El compañero quedó fuera de cuadro. NO es un error: el plano sobre el hombro y el
#: plano corto lo dejan afuera a propósito.
PERSONAJE_DE_MENOS = VISION_OK.replace("personajes: 2", "personajes: 1")


def _png_de_verdad(destino: Path) -> None:
    """Un PNG del tamaño real de una ilustración, hecho con ffmpeg.

    El de 1×1 del `FakeImageProvider` no sirve acá: el verificador recorta la mitad de
    abajo para ampliarla, y de una imagen de un píxel no se puede recortar nada. Con
    ese PNG el test pasaría por el camino degradado —una sola vista— sin probar el que
    se usa de verdad.
    """
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=green:s=1024x1536", "-frames:v", "1", str(destino)],
        check=True, capture_output=True,
    )


@pytest.fixture
def historia_ilustrada(historia: Story, tmp_path) -> Story:
    """Una historia con dos escenas de DOS personajes y sus PNG de verdad en disco.

    Se usan las escenas 4 y 5 del plan porque son las que tienen a los dos: el
    verificador compara el conteo de personajes contra el elenco de la escena, así que
    probarlo sobre una escena de uno solo mediría otra cosa.
    """
    historia.scenes = [
        Scene.from_plan(
            historia.plan.scenes[i],
            narration="Dino miró la pelota entre los helechos.",
            prop="una pelota de colores",
            image_prompt="Dino en el claro, con la pelota",
        )
        for i in (4, 5)
    ]
    for escena in historia.scenes:
        ruta = tmp_path / f"escena_{escena.index:02d}.png"
        _png_de_verdad(ruta)
        escena.image_path = str(ruta)
    return historia


async def test_una_imagen_sin_reparos_no_se_rehace(historia_ilustrada: Story) -> None:
    """Lo normal: la imagen coincide con el plan y no se toca."""
    imagenes = FakeImageProvider()
    inspector = ImageInspector(FakeVisionProvider(), SceneIllustrator(imagenes))

    veredictos = await inspector.inspect(historia_ilustrada)

    assert [v.paso for v in veredictos] == [True, True]
    assert imagenes.llamadas == [], "no se pagó ninguna imagen nueva"


async def test_la_mano_de_mas_se_detecta_y_se_rehace(historia_ilustrada: Story) -> None:
    """El caso de "honestidad": tres manos en el abrazo.

    Llegó al video que miró Pablo. Ahora el verificador lo ve, pide la imagen de nuevo
    y la segunda sale bien.
    """
    vision = FakeVisionProvider([MANO_DE_MAS, VISION_OK])
    imagenes = FakeImageProvider()
    inspector = ImageInspector(vision, SceneIllustrator(imagenes))

    veredictos = await inspector.inspect(historia_ilustrada)

    assert veredictos[0].paso, "la segunda imagen ya no tenía el reparo"
    assert veredictos[0].intentos == 2
    assert len(imagenes.llamadas) == 1, "se rehizo UNA sola imagen, no el cuento"


async def test_el_reintento_le_dice_al_modelo_QUE_salio_mal(historia_ilustrada: Story) -> None:
    """Pedir lo mismo otra vez no es un reintento.

    Es la lección de las tomas de voz que nacían cortadas: el guardián las rechazaba,
    las pedía igual tres veces y frenaba la producción. Al modelo hay que darle una
    orden realmente distinta.
    """
    imagenes = FakeImageProvider()
    inspector = ImageInspector(
        FakeVisionProvider([MANO_DE_MAS, VISION_OK]), SceneIllustrator(imagenes)
    )

    await inspector.inspect(historia_ilustrada)

    pedido = imagenes.llamadas[0]["prompt"]
    assert "CORRECCIÓN" in pedido
    assert "mano/brazo de más" in pedido
    assert "cuatro extremidades" in pedido


async def test_un_personaje_de_mas_es_reparo_y_uno_de_menos_no(
    historia_ilustrada: Story,
) -> None:
    """Regla 1 en un solo sentido.

    Un personaje que sobra es el error real del 5-ago —el modelo asciende a alguien
    del fondo—. Uno que falta suele ser el encuadre: en un plano corto o sobre el
    hombro el compañero queda afuera a propósito, y rehacer por eso sería romper el
    plano que el motor eligió.
    """
    escena = historia_ilustrada.scenes[0]
    personajes = historia_ilustrada.characters_by_id

    de_mas = _reparos(_campos(PERSONAJE_DE_MAS), escena, personajes)
    de_menos = _reparos(_campos(PERSONAJE_DE_MENOS), escena, personajes)

    assert [r.regla for r in de_mas] == ["elenco"]
    assert de_menos == []


async def test_si_la_vision_falla_el_cuento_sigue(historia_ilustrada: Story) -> None:
    """Un proveedor caído no puede frenar la producción.

    Es la misma decisión que en el storyboard: un cuento sin verificar es peor que uno
    verificado, y muchísimo mejor que un cuento que no existe.
    """
    vision = VisionQueCae()
    imagenes = FakeImageProvider()

    veredictos = await ImageInspector(vision, SceneIllustrator(imagenes)).inspect(
        historia_ilustrada
    )

    assert all(v.paso for v in veredictos)
    assert imagenes.llamadas == []
    assert vision.llamadas > 0, "se intentó de verdad antes de rendirse"


async def test_una_respuesta_que_no_se_entiende_no_acusa(historia_ilustrada: Story) -> None:
    """Lo que no se entiende, no se usa.

    Un guardián que no entendió no puede acusar: rehacer una imagen buena la cambia
    por otra sin que nadie lo haya pedido.
    """
    inspector = ImageInspector(
        FakeVisionProvider(["Lo siento, no puedo ayudar con eso."]),
        SceneIllustrator(FakeImageProvider()),
    )

    veredictos = await inspector.inspect(historia_ilustrada)

    assert all(v.paso for v in veredictos)


async def test_se_mira_la_escena_entera_y_la_zona_de_las_patas(
    historia_ilustrada: Story,
) -> None:
    """Dos vistas, no una.

    Medido contra los casos reales: sobre la imagen entera el modelo no ve las patas
    de más — a 1024×1536 una pata extra son cuatro píxeles. Ampliada la mitad de
    abajo, el mismo modelo la describe.
    """
    vision = FakeVisionProvider()

    await ImageInspector(vision).inspect(historia_ilustrada)

    assert vision.llamadas[0]["imagenes"] == 2


async def test_sin_ilustrador_reporta_pero_no_toca_nada(historia_ilustrada: Story) -> None:
    """Sirve como auditoría de un lote ya hecho, sin gastar en imágenes."""
    veredictos = await ImageInspector(FakeVisionProvider([MANO_DE_MAS])).inspect(
        historia_ilustrada
    )

    assert not veredictos[0].paso
    assert veredictos[0].resuelta is False


async def test_si_nunca_sale_bien_se_queda_con_la_mejor(historia_ilustrada: Story) -> None:
    """Rehacer no puede empeorar el cuento.

    Si ninguna vuelta arregla el problema, la escena se queda con la imagen que MENOS
    reparos tuvo. Quedarse con la última porque sí es cómo un arreglo termina dejando
    el producto peor que antes de tocarlo.
    """
    dos_reparos = MANO_DE_MAS.replace("personajes: 2", "personajes: 3")
    vision = FakeVisionProvider([dos_reparos, MANO_DE_MAS, MANO_DE_MAS, MANO_DE_MAS])
    imagenes = FakeImageProvider()

    veredictos = await ImageInspector(vision, SceneIllustrator(imagenes)).inspect(
        historia_ilustrada
    )

    assert veredictos[0].resuelta is False
    assert len(veredictos[0].reparos) == 1, "quedó la vuelta con un solo reparo"


async def test_el_objeto_solo_se_pregunta_si_la_escena_lo_tiene(
    historia_ilustrada: Story,
) -> None:
    """Regla 7: el objeto que eligió el motor tiene que verse.

    Pero sólo se pregunta donde el plan lo puso: preguntar por la pelota en una escena
    que no la tiene sería fabricar un reparo por una ausencia correcta.
    """
    historia_ilustrada.scenes[1].prop = ""
    vision = FakeVisionProvider()

    await ImageInspector(vision).inspect(historia_ilustrada)

    assert "una pelota de colores" in vision.llamadas[0]["prompt"]
    assert "objeto:" not in vision.llamadas[1]["prompt"]


def test_el_si_o_no_mira_solo_la_primera_palabra() -> None:
    """El modelo contesta "no" y también "no, la escena es de día"."""
    assert _es("no, la escena es de noche", {"no"})
    assert _es("SÍ", {"si", "sí"})
    assert not _es("", {"no"})
    assert not _es(None, {"no"})


def test_sin_reparos_no_hay_bloque_de_correccion() -> None:
    assert _correccion([]) == ""
