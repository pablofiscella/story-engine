"""El escritor y la fachada.

Todo corre contra un proveedor falso: el pipeline entero se prueba sin red, sin
API key y sin gastar. Los casos que con un modelo real son carísimos de reproducir
—que se pase de largo, que devuelva vacío, que se caiga— acá son un test más.
"""

from __future__ import annotations

import pytest

from engine.core.enums import EducationalValue, StoryStatus
from engine.core.exceptions import ProviderError, ProviderRefusedError, ProviderUnavailableError
from engine.core.models import Character, Style, Theme
from engine.engine import StoryEngine
from engine.generators.writer import (
    PALABRAS_DE_APERTURA,
    StoryWriter,
    _limpiar,
    _recortar,
    _subtitulo,
    apertura_de,
)
from engine.providers.fake import FakeTextProvider, ProviderQueCae, ProviderVacio

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def motor(dino: Character) -> StoryEngine:
    return StoryEngine(text_provider=FakeTextProvider())


def _kwargs(tema: Theme, estilo: Style, dino: Character, tuca: Character, **extra):
    base = dict(
        theme=tema, style=estilo, value=EducationalValue.SHARING,
        age=4, duration_s=30.0, characters=[dino, tuca],
    )
    base.update(extra)
    return base


# --- el camino feliz -------------------------------------------------------------


async def test_genera_una_historia_completa(
    motor: StoryEngine, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))

    assert story.status is StoryStatus.WRITTEN
    assert len(story.scenes) == len(story.plan.scenes)
    assert all(e.narration for e in story.scenes)
    assert story.word_count > 0


async def test_cada_escena_respeta_su_plan(
    motor: StoryEngine, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El escritor pone palabras; no puede cambiar lo que decidió el motor."""
    story = await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    for escena, plan in zip(story.scenes, story.plan.scenes, strict=True):
        assert escena.beat is plan.beat
        assert escena.duration_s == plan.duration_s
        assert escena.character_ids == plan.character_ids
        assert escena.location == plan.location


async def test_la_narracion_entra_en_cada_escena(
    motor: StoryEngine, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    assert all(e.word_count <= e.max_words for e in story.scenes)


async def test_el_prompt_de_imagen_se_compone_solo(
    motor: StoryEngine, tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Lo arma el motor, no la IA — por eso el personaje se describe igual siempre."""
    story = await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    prompts = [e.image_prompt for e in story.scenes]
    assert all(p for p in prompts)
    # la descripción canónica del protagonista aparece idéntica en todas
    fragmento = dino.appearance.prompt_fragment()
    assert all(fragmento in p for p in prompts)
    # y el estilo también
    assert all(estilo_3d.art_style in p for p in prompts)


async def test_las_escenas_encadenan(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """A partir de la segunda, el pedido incluye lo que pasó antes."""
    provider = FakeTextProvider()
    motor = StoryEngine(text_provider=provider)
    # Sin storyboard: éste es un test del ESCRITOR, y el storyboard suma un pedido más
    # al final —el del cuento entero— que no encadena porque las ve todas juntas.
    await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca), con_storyboard=False)
    assert "La escena anterior terminó" not in provider.llamadas[0]
    assert all("La escena anterior terminó" in p for p in provider.llamadas[1:])


async def test_a_la_ultima_escena_se_le_pide_que_cierre(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    provider = FakeTextProvider()
    motor = StoryEngine(text_provider=provider)
    await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca), con_storyboard=False)
    assert "última escena" in provider.llamadas[-1]
    assert not any("última escena" in p for p in provider.llamadas[:-1])


# --- cuando el modelo se porta mal -----------------------------------------------


async def test_si_se_pasa_de_largo_se_le_pide_de_nuevo_y_se_recorta(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """El vicio clásico: escribir un párrafo hermoso que no entra en 5 segundos."""
    provider = FakeTextProvider(obedece_limite=False)
    motor = StoryEngine(text_provider=provider)
    story = await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))

    # reintentó antes de rendirse...
    assert any("palabras de más" in p for p in provider.llamadas)
    # ...y aun así ninguna escena quedó fuera de presupuesto
    assert all(e.word_count <= e.max_words for e in story.scenes)


async def test_texto_vacio_falla_claro(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    motor = StoryEngine(text_provider=ProviderVacio())
    with pytest.raises(ProviderError, match="vacío"):
        await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))


async def test_falla_transitoria_se_reintenta_y_recien_ahi_sube(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Un 5xx es transitorio: se insiste. Si igual no se recupera, sube como tal
    para que el que llama sepa que puede volver a intentar más tarde."""
    from engine.core.retry import INTENTOS

    provider = ProviderQueCae()
    motor = StoryEngine(text_provider=provider)
    with pytest.raises(ProviderUnavailableError):
        await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    assert len(provider.llamadas) == INTENTOS


async def test_rechazo_de_contenido_no_se_confunde_con_caida(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Reintentar contra un filtro de contenido quema cuota sin ninguna chance."""
    provider = ProviderQueCae(refused=True)
    motor = StoryEngine(text_provider=provider)
    with pytest.raises(ProviderRefusedError):
        await motor.generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    assert len(provider.llamadas) == 1  # ni un intento de más


async def test_escribir_sin_plan_no_se_puede(historia) -> None:
    historia.plan = None
    with pytest.raises(ValueError, match="no tiene plan"):
        await StoryWriter(FakeTextProvider()).write(historia)


# --- la fachada ------------------------------------------------------------------


def test_se_puede_planificar_sin_proveedor(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """Planificar no cuesta nada: el plan se revisa antes de gastar en texto."""
    story = StoryEngine().plan(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    assert story.status is StoryStatus.PLANNED
    assert story.plan is not None
    assert story.scenes == []


async def test_generar_sin_proveedor_avisa_bien(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    with pytest.raises(RuntimeError, match="no tiene proveedor de texto"):
        await StoryEngine().generate(**_kwargs(tema_dinos, estilo_3d, dino, tuca))


def test_la_edad_puede_venir_como_numero(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    """`age=4` es lo natural para quien usa la API; adentro se razona por franja."""
    from engine.core.enums import AgeRange

    story = StoryEngine().plan(**_kwargs(tema_dinos, estilo_3d, dino, tuca, age=4))
    assert story.metadata.age_range is AgeRange.PRESCHOOL


def test_el_valor_puede_venir_como_texto(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = StoryEngine().plan(**_kwargs(tema_dinos, estilo_3d, dino, tuca, value="paciencia"))
    assert story.value is EducationalValue.PATIENCE


def test_la_moraleja_y_la_pregunta_salen_del_valor(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = StoryEngine().plan(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    assert "Compartir" in story.moral
    assert story.closing_question.startswith("¿Y vos")


def test_el_primer_personaje_es_el_protagonista(
    tema_dinos: Theme, estilo_3d: Style, dino: Character, tuca: Character
) -> None:
    story = StoryEngine().plan(**_kwargs(tema_dinos, estilo_3d, dino, tuca))
    assert story.protagonist is not None
    assert story.protagonist.id == dino.id


def test_una_historia_necesita_personajes(tema_dinos: Theme, estilo_3d: Style) -> None:
    with pytest.raises(ValueError, match="al menos un personaje"):
        StoryEngine().plan(
            theme=tema_dinos, style=estilo_3d, value=EducationalValue.SHARING,
            age=4, duration_s=30.0, characters=[],
        )


# --- limpieza del texto que devuelve el modelo -----------------------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ('"Dino miró el cielo."', "Dino miró el cielo."),
        ("«Dino miró el cielo.»", "Dino miró el cielo."),
        ("Escena 3: Dino miró el cielo.", "Dino miró el cielo."),
        ("Narración: Dino miró el cielo.", "Dino miró el cielo."),
        ("**Dino** miró   el cielo.", "Dino miró el cielo."),
        ("  Dino miró el cielo.  ", "Dino miró el cielo."),
    ],
)
def test_limpia_lo_que_el_modelo_agrega_de_mas(crudo: str, esperado: str) -> None:
    """Es más confiable limpiarlo que confiar en que esta vez sí obedeció."""
    assert _limpiar(crudo) == esperado


def test_recorta_en_el_punto_mas_cercano() -> None:
    texto = "Primera frase corta. Segunda frase que se pasa bastante de largo."
    assert _recortar(texto, 6) == "Primera frase corta."


def test_recortar_no_toca_lo_que_ya_entra() -> None:
    assert _recortar("Tres palabras justas", 5) == "Tres palabras justas"


def test_el_subtitulo_corta_en_la_primera_frase_si_es_largo() -> None:
    largo = "Frase uno bien cortita. " + "palabra " * 30
    assert _subtitulo(largo) == "Frase uno bien cortita."


def test_el_recorte_no_deja_la_frase_colgada() -> None:
    """El bug: una narración salió "...juegan con la pelota de colores en el." —
    cortada justo en una preposición, que no cierra nada."""
    texto = "Dino y Rexo juegan felices con la pelota de colores en el claro del bosque"
    assert _recortar(texto, 12) == "Dino y Rexo juegan felices con la pelota de colores."


# --- Lo que el escritor VE, que es lo que decide lo que escribe -------------------
def test_al_escritor_no_se_le_muestra_el_lugar_si_el_genero_no_lo_narra() -> None:
    """**Pedirle algo en la regla y darle lo contrario en el dato es una regla
    imposible.**

    El sistema devocional dice, textual: *"NEVER describe the location or what the
    person is doing or seeing. The location you are given is there so the ILLUSTRATOR
    knows what to draw"*. Y el pedido, dos líneas después, le mostraba
    `- Dónde: a country road between fields at sunrise`.

    Resultado medido sobre el primer devocional de 20 minutos (8-ago-2026): **6 de 20
    escenas** narraron el paisaje —*"You stand at the shoreline"*, *"you walk along a
    quiet country road"*— en un formato donde quien escucha está en su cama.

    Es el mismo patrón que ya mordió dos veces a este motor: el ejemplo del prompt que
    el escritor repitió, y la respuesta puesta adentro de la pregunta del verificador de
    anatomía. La escena SIGUE teniendo su lugar: lo que cambia es a quién se lo cuenta.
    """
    from engine.core.enums import Emotion, NarrativeBeat, ShotType
    from engine.core.models.plan import ScenePlan
    from engine.prompts.narration import scene_prompt

    plan = ScenePlan(
        index=0,
        beat=NarrativeBeat.HOOK,
        purpose="Saludar a quien mira",
        duration_s=60.0,
        location="a country road between fields at sunrise",
        character_ids=["orante"],
        emotion=Emotion.CALM,
        shot=ShotType.WIDE,
    )
    con = scene_prompt(plan, characters={}, max_words=100)
    sin = scene_prompt(plan, characters={}, max_words=100, narra_el_lugar=False)

    assert "country road" in con  # los cuentos sí narran dónde pasan
    assert "country road" not in sin
    assert "Dónde" not in sin
    assert "Saludar a quien mira" in sin  # y lo demás sigue igual


def test_el_escritor_ve_TODAS_las_aperturas_ya_usadas_y_no_solo_la_anterior() -> None:
    """Una regla que sólo mira la escena anterior no alcanza cuando hay veinte.

    El sistema ya decía *"NEVER open a scene with the same words as the scene before
    it"*, y el primer devocional de 20 minutos salió con **11 de 20 escenas empezando
    con "As…"**: *"As dawn breaks"*, *"As you breathe in"*, *"As the day unfolds"*.
    Ninguna repetía a su vecina inmediata, así que ninguna violaba la regla — y el
    conjunto es igual el *"generic or unoriginal template"* que la política de YouTube
    del 16-jul-2026 castiga con el canal entero.
    """
    from engine.core.enums import Emotion, NarrativeBeat, ShotType
    from engine.core.models.plan import ScenePlan
    from engine.prompts.narration import scene_prompt

    plan = ScenePlan(
        index=3,
        beat=NarrativeBeat.PROBLEM,
        purpose="Nombrar la carga",
        duration_s=60.0,
        location="a hilltop",
        character_ids=["orante"],
        emotion=Emotion.SADNESS,
        shot=ShotType.MEDIUM,
    )
    pedido = scene_prompt(
        plan, characters={}, max_words=100,
        aperturas=["As the dawn breaks", "As you breathe in"],
    )
    assert "As the dawn breaks" in pedido
    assert "As you breathe in" in pedido
    assert "no puede empezar" in pedido


def test_la_apertura_son_CUATRO_palabras() -> None:
    """Con dos, *"As dawn"* y *"As you"* cuentan como arranques distintos y el escritor
    sigue empezando todo igual. Con ocho, la lista deja de ser una prohibición y
    empieza a funcionar como EJEMPLO — la trampa que este motor ya documentó dos veces.
    """
    assert PALABRAS_DE_APERTURA == 4
    assert apertura_de("As the dawn breaks gently, I pause") == "As the dawn breaks"
    assert apertura_de("As the dawn breaks softly, take a moment") == "As the dawn breaks"
    assert apertura_de("Hola") == "Hola"
