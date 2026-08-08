"""El verificador de guion, probado con el devocional REAL que Pablo no puede juzgar.

Pablo, 8-ago-2026, después de mirar los canales del nicho: *"el problema es cómo
sabemos si el texto está bien"*. Él no juzga inglés. Este archivo es la respuesta
escrita como test: el guion completo del devocional de ansiedad generado el 7-ago-2026
—`out/devocional/ansiedad/historia.json`, 10 escenas, el que se iba a publicar— está
copiado abajo tal cual, con lo que tenía mal, para que si el verificador deja de
reaccionar falle la suite y no el producto.

**Lo que este guion tiene, revisado a mano el 8-ago-2026:**

1. `no worries` en la escena 1. El propósito pedía *"eyes open, nothing wrong, and
   still no rest"*; en inglés *"no worries"* no quiere decir "nada anda mal", quiere
   decir *"tranquilo, no pasa nada"* — es lo que se contesta cuando alguien pide
   perdón. Es el error exacto que Pablo no puede ver.
2. Dos muletillas: `take a moment` (escenas 0 y 4) y `when your heart` (2 y 3).
   **`aperturas_repetidas()`, el guardián que ya existía, devuelve cero sobre este
   mismo guion** — y tiene razón, porque compara sólo las tres primeras palabras.
3. El cierre de la última escena es una pregunta retórica (*"Can you feel it?"*), pero
   el pedido concreto —*"type AMEN"*— llega igual en la invitación. El guardián juzga
   el cierre COMPLETO, así que este guion pasa: es el falso positivo que había que
   evitar.
"""

from __future__ import annotations

import pytest

from engine.core.enums import Language, StoryStatus
from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.generators.devotional import aperturas_repetidas
from engine.generators.script_inspector import (
    ScriptInspector,
    _campos,
    _cierre_completo,
    _correccion,
    _reparos,
    abre_saludando,
    frases_repetidas,
    pide_un_acto,
)
from engine.providers.fake import (
    REVISION_OK,
    FakeRevisorDeGuion,
    RevisorQueCae,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- EL GUION REAL, tal como salió el 7-ago-2026 ---------------------------------

GUION_REAL: list[str] = [
    "If this message found you tonight, it wasn’t by chance. Take a moment… just sixty "
    "seconds. Pause everything around you. Breathe… and let the stillness wrap around "
    "you like a warm blanket.",
    "It’s 3 a.m. Your eyes open… no worries, yet rest still eludes you. The quiet is "
    "heavy. A sadness lingers, whispering of longing. You search for peace, hoping for "
    "something to hold onto in this stillness.",
    "You feel tired. Tired of pretending everything is fine when your heart carries a "
    "weight. It’s okay to acknowledge that. The dawn brings a gentle reminder: you "
    "don’t have to carry it alone.",
    "You lie awake, replaying that conversation in your mind. Each word echoes, heavy "
    "with regret. The stillness wraps around you, but the ache remains. It’s hard to "
    "find peace when your heart is restless.",
    "Take a moment to breathe. God, I bring this thought to You... the one that circles "
    "in my mind. Help me to release it to You. Let Your peace fill this space where my "
    "heart aches.",
    "Feel your body start to relax... Unclench your jaw... Let your shoulders drop. "
    "Breathe in deeply... and let it out slowly. God, I ask for relief in every tense "
    "place, filling it with Your gentle peace.",
    "God, I give You my racing thoughts... the worries about tomorrow... the burden of "
    "decisions... the fear of being alone... I hand them over to You, trusting in Your "
    "presence to calm my restless heart.",
    "Sometimes, the noise doesn’t quiet right away… The worries can swirl around like "
    "restless waves. You might still feel fear creeping in. But remember, even in the "
    "storm, God is there with you.",
    "The dawn breaks gently, surprising you with its softness. In this moment, you feel "
    "a whisper of peace. It wraps around your heart, guarding it. Even before things "
    "change, you are held in safety.",
    "May you find rest in this new day… May joy wash over you like gentle waves… "
    "Embrace the peace that holds you, knowing you are cherished. Can you feel it? Let "
    "it fill your heart.",
]

PROMESA_REAL = "Peace is not the absence of the storm. It is God standing in it with you."
INVITACION_REAL = (
    "If your mind has been loud lately, type AMEN so I can pray for you by name."
)

#: La respuesta del revisor sobre el guion real, con el hallazgo que importa.
#: Formato idéntico al que devuelve el modelo de verdad.
REVISION_DEL_GUION_REAL = (
    "natural: traducido\n"
    "cual_traducida: no worries, yet rest still eludes you\n"
    "registro: intimo\n"
    "errores: no worries || en inglés significa «tranquilo, no pasa nada», no «nada "
    "anda mal»: es lo que se contesta a una disculpa\n"
    "muletilla: take a moment\n"
    "apertura: parar\n"
    "cierre_pide: si"
)


@pytest.fixture
def devocional(historia: Story) -> Story:
    """El devocional real: 10 escenas con el texto que se iba a publicar.

    Se arma sobre la `historia` del conftest y se le pisan las escenas porque lo único
    que el verificador de guion mira es el TEXTO: el plan, el tema y el elenco no
    intervienen. Armar un `Story` devocional entero acá sería probar el planificador.

    Los 15 segundos por escena son los de verdad (`RITMO_DEVOCIONAL_S`), y no un
    detalle: con los 5 s del plan de cuentos del conftest, el guardián de duración de
    `Scene` rechaza el texto real antes de que el verificador lo llegue a mirar.
    """
    plan = historia.plan.scenes
    historia.scenes = [
        Scene.from_plan(
            plan[i % len(plan)].model_copy(update={"index": i, "duration_s": 15.0}),
            narration=texto,
        )
        for i, texto in enumerate(GUION_REAL)
    ]
    historia.moral = PROMESA_REAL
    historia.closing_question = INVITACION_REAL
    historia.metadata.language = Language.EN
    historia.advance_to(StoryStatus.PLANNED)
    historia.advance_to(StoryStatus.WRITTEN)
    return historia


#: Con qué reemplaza el escritor falso cada escena que le mandan reescribir.
#:
#: **Un texto DISTINTO por escena, y no es un adorno del test.** La primera versión
#: devolvía la misma frase para las tres, y el verificador —bien— la marcó como una
#: muletilla nueva: tres escenas corregidas con la misma idea son exactamente el
#: "generic or unoriginal template" que se está tratando de evitar. Que el fake tenga
#: que esforzarse para no repetirse es la señal de que el guardián funciona.
REESCRITURAS: dict[int, str] = {
    1: "Three in the morning, and the house sleeps without you.",
    3: "One sentence keeps returning. You cannot put it down.",
    4: "Father, I am handing over what circles above my bed.",
}


class EscritorFalso:
    """Reescribe una escena poniéndole un texto nuevo, y anota qué le pidieron.

    Lo que hay que probar del verificador no es la prosa nueva —eso no se puede
    evaluar en un test— sino QUÉ escenas manda reescribir y con qué corrección. Por eso
    este escritor guarda las llamadas, igual que el `FakeImageProvider` guarda las
    referencias con las que se lo llamó.
    """

    def __init__(self, nuevo: dict[int, str] | None = None) -> None:
        self.nuevo = REESCRITURAS if nuevo is None else nuevo
        self.llamadas: list[dict] = []

    async def reescribir(
        self,
        escena: Scene,
        story: Story,
        *,
        correccion: str = "",
        sistema: str | None = None,
        anterior: str | None = None,
    ) -> Scene:
        self.llamadas.append(
            {"escena": escena.index, "correccion": correccion, "sistema": sistema}
        )
        escena.narration = self.nuevo.get(
            escena.index, f"A different closing thought, number {escena.index}."
        )
        return escena


# --- Los guardianes deterministas, contra el guion real ---------------------------
def test_el_guardian_que_ya_existia_no_ve_nada_en_el_guion_real() -> None:
    """`aperturas_repetidas` devuelve cero, y por eso hizo falta otro guardián.

    No es un defecto suyo: compara las tres primeras palabras de cada escena, y las
    diez del guion real empiezan distinto. Este test fija el hueco, que es la razón de
    existir de `frases_repetidas`.
    """
    assert aperturas_repetidas(GUION_REAL) == []


def test_frases_repetidas_encuentra_las_dos_muletillas_reales() -> None:
    """Las dos que un humano marcaría leyendo, y ninguna de más."""
    assert frases_repetidas(GUION_REAL) == [
        ("take a moment", [0, 4]),
        ("when your heart", [2, 3]),
    ]


def test_con_dos_palabras_el_guardian_acusa_al_idioma_y_con_cuatro_no_ve_nada() -> None:
    """La calibración de `PALABRAS_DE_MULETILLA`, fijada con números.

    Es el test que impide que alguien "afine" la constante sin medir: con 2 salen diez
    repeticiones que son armazón del inglés ("your heart", "you feel"), y con 4 no sale
    ninguna porque la cuarta palabra ya difiere.
    """
    assert len(frases_repetidas(GUION_REAL, n=2)) == 10
    assert frases_repetidas(GUION_REAL, n=4) == []


def test_el_guion_real_no_abre_saludando() -> None:
    assert abre_saludando(GUION_REAL[0]) is False


def test_un_saludo_al_arranque_se_marca() -> None:
    """El anti-patrón del nicho: cuatro de los seis mejores canales abren con "Before…"
    y ninguno dice hola ni el nombre del canal (medido el 8-ago-2026)."""
    assert abre_saludando("Hello everyone and welcome back to the channel!") is True
    assert abre_saludando("Hola a todos, bienvenidos a un nuevo video.") is True


def test_el_cierre_se_juzga_completo_y_no_solo_la_ultima_escena(devocional: Story) -> None:
    """El falso positivo que había que evitar.

    La última escena termina en una pregunta retórica —"Can you feel it?"— y no pide
    nada. El pedido concreto está un renglón después, en la invitación, y **se escucha
    seguido**: quien mira oye una sola cosa. Juzgando sólo la escena, este devocional
    salía reprobado por un error que no existe.
    """
    assert pide_un_acto(GUION_REAL[-1]) is False
    assert pide_un_acto(_cierre_completo(devocional)) is True


def test_un_cierre_que_solo_bendice_se_marca() -> None:
    """Medido el 8-ago-2026: los canales que cierran con la bendición de Números 6 y
    sin CTA tienen likes altos y menos comentarios. El nicho se eligió por los
    comentarios."""
    assert pide_un_acto("May the Lord bless you and keep you. Amen.") is False


# --- El filtro anti-invento: la regla que ordena todo lo demás ---------------------
def test_una_cita_que_no_esta_en_el_guion_se_descarta() -> None:
    """Un revisor que inventa la frase no puede mandar a reescribir nada.

    Es el riesgo propio de este verificador y no del de imágenes: un modelo que juzga
    prosa cita de memoria con una facilidad que uno que cuenta patas no tiene. Sin este
    filtro, el motor reescribiría escenas buenas por errores imaginarios — un producto
    que empeora solo y sin que nadie se entere.
    """
    inventada = (
        "natural: traducido\n"
        "cual_traducida: the moon was crying over the empty village\n"
        "registro: intimo\n"
        "errores: ninguno\n"
        "muletilla: ninguna\n"
        "apertura: parar\n"
        "cierre_pide: si"
    )
    reparos = _reparos(_campos(inventada), GUION_REAL)
    assert [r.regla for r in reparos] == ["descartado"]


def test_la_muletilla_se_cuenta_no_se_cree() -> None:
    """El revisor dice que algo se repite; el código va y lo cuenta.

    "A sadness lingers" está en el guion una sola vez (escena 1). Que exista no alcanza:
    una muletilla es una repetición, y eso se verifica.
    """
    respuesta = REVISION_OK.replace("muletilla: ninguna", "muletilla: A sadness lingers")
    reparos = _reparos(_campos(respuesta), GUION_REAL)
    assert [r.regla for r in reparos] == ["descartado"]

    repetida = REVISION_OK.replace("muletilla: ninguna", "muletilla: take a moment")
    reparos = _reparos(_campos(repetida), GUION_REAL)
    assert [(r.regla, r.escena) for r in reparos] == [("muletilla", 4)]


def test_la_cita_se_ubica_aunque_cambie_la_puntuacion() -> None:
    """El revisor copia con comilla recta lo que el guion tiene con comilla tipográfica.

    Exigir los caracteres exactos convertiría el filtro anti-invento en un filtro
    anti-todo: se exige que estén las PALABRAS, en orden, que es lo que hace falta para
    poder corregirlas.
    """
    respuesta = REVISION_OK.replace(
        "errores: ninguno", "errores: It's 3 a.m. Your eyes open || suena raro"
    )
    reparos = _reparos(_campos(respuesta), GUION_REAL)
    assert [(r.regla, r.escena) for r in reparos] == [("idioma", 1)]


# --- El hallazgo real -------------------------------------------------------------
def test_el_no_worries_del_guion_real_sale_con_su_escena() -> None:
    """El error que justifica el módulo entero, ubicado en la escena 1."""
    reparos = _reparos(_campos(REVISION_DEL_GUION_REAL), GUION_REAL)
    reglas = {r.regla: r for r in reparos}

    assert reglas["traduccion"].escena == 1
    assert reglas["idioma"].escena == 1
    assert "tranquilo, no pasa nada" in reglas["idioma"].detalle
    assert reglas["muletilla"].escena == 4
    assert not [r for r in reparos if r.regla == "descartado"]


def test_el_registro_equivocado_es_del_guion_entero_no_de_una_escena() -> None:
    """Un sermón no se arregla reescribiendo la escena 3: cambia el prompt, no el texto.

    Por eso `escena` es `None` y el verificador no manda reescribir nada por esto.
    """
    respuesta = REVISION_OK.replace("registro: intimo", "registro: sermon")
    reparos = _reparos(_campos(respuesta), GUION_REAL)
    assert [(r.regla, r.escena) for r in reparos] == [("registro", None)]


def test_varios_errores_de_idioma_no_se_pisan() -> None:
    """`errores` es el único campo que puede traer más de una línea.

    Un guion con tres errores tiene tres errores; parsearlo con el "clave: valor" de
    siempre se quedaría con el último y los otros dos saldrían publicados.
    """
    respuesta = REVISION_OK.replace(
        "errores: ninguno",
        "errores: no worries || locución con el sentido equivocado\n"
        "A sadness lingers || calco, ningún nativo lo diría en voz alta",
    )
    reparos = [r for r in _reparos(_campos(respuesta), GUION_REAL) if r.regla == "idioma"]
    assert [r.escena for r in reparos] == [1, 1]


# --- Las dos formas en que gpt-5.2 contesta de verdad -----------------------------
#: Respuesta REAL de gpt-5.2 sobre el guion real, corrida el 8-ago-2026.
#:
#: Trae las dos trampas de formato juntas, y ninguna de las dos es un capricho del
#: modelo: **`errores:` va solo en su renglón** con la lista debajo, y **las citas
#: llevan el número de escena adelante** — el mismo `[N]` con el que el verificador le
#: numera el guion en el pedido. El modelo copia la forma de lo que se le muestra.
REVISION_REAL_CON_LISTA = """natural: traducido
cual_traducida: If this message found you tonight, it wasn’t by chance.
registro: intimo
errores:
[1] It’s 3 a.m. Your eyes open… no worries, yet rest still eludes you. || \
“no worries” significa «tranquilo, no pasa nada»: es lo que se contesta a una disculpa
[4] God, I bring this thought to You... the one that circles in my mind. || \
“circles in my mind” suena calcado; un nativo diría “keeps running through my mind”
muletilla: take a moment
apertura: parar
cierre_pide: si"""


def test_los_errores_no_se_pierden_cuando_la_clave_va_sola_en_su_renglon() -> None:
    """La falla más cara posible: reportar "todo bien" sobre un guion con cinco reparos.

    Pasó de verdad el 8-ago-2026 contra el modelo real. Con el renglón `errores:` vacío
    la clave quedaba en la anterior y la lista entera se descartaba en silencio.
    """
    campos = _campos(REVISION_REAL_CON_LISTA)
    assert campos["errores"].count("||") == 2


def test_la_cita_con_el_numero_de_escena_adelante_no_se_descarta() -> None:
    """Cuatro hallazgos buenos se perdían por el "[1]" que el propio pedido le enseñó.

    El filtro anti-invento está para tirar citas inventadas, no citas bien copiadas con
    un prefijo de más. Si tira las buenas, deja de ser un filtro y pasa a ser una venda.
    """
    reparos = _reparos(_campos(REVISION_REAL_CON_LISTA), GUION_REAL)
    idioma = [r for r in reparos if r.regla == "idioma"]

    assert [r.escena for r in idioma] == [1, 4]
    assert "no pasa nada" in idioma[0].detalle
    assert not [r for r in reparos if r.regla == "descartado"]


# --- El ciclo completo ------------------------------------------------------------
async def test_reescribe_solo_las_escenas_con_reparo(devocional: Story) -> None:
    """Las 10 escenas se revisan juntas y se tocan sólo las que fallaron.

    Sobre el guion real: los deterministas marcan las escenas 4 y 3 (las dos
    muletillas) y el revisor marca la 1. Las otras siete no se tocan — reescribir el
    guion entero sería tirar lo que estaba bien, que es lo mismo que el verificador de
    imágenes evita rehaciendo una sola escena.
    """
    escritor = EscritorFalso()
    veredicto = await ScriptInspector(
        FakeRevisorDeGuion([REVISION_DEL_GUION_REAL, REVISION_OK]), escritor
    ).inspect(devocional)

    assert sorted(veredicto.reescritas) == [1, 3, 4]
    assert len(escritor.llamadas) == 3
    assert veredicto.paso


async def test_la_correccion_le_dice_al_escritor_la_frase_prohibida(
    devocional: Story,
) -> None:
    """No se pide lo mismo otra vez: se nombra la frase que no puede volver a usar.

    Es la lección de la muletilla del 7-ago-2026 leída al revés — si el ejemplo pesa
    más que el contexto, nombrar la frase prohibida es lo único que la saca.
    """
    escritor = EscritorFalso()
    await ScriptInspector(
        FakeRevisorDeGuion([REVISION_DEL_GUION_REAL, REVISION_OK]), escritor
    ).inspect(devocional, sistema_de_escritura="EL PROMPT DEVOCIONAL")

    de_la_1 = next(x for x in escritor.llamadas if x["escena"] == 1)
    assert "no worries" in de_la_1["correccion"]
    assert "NO reuses" in de_la_1["correccion"]
    # El prompt de narrador viaja: sin esto la escena de un devocional se reescribe con
    # voz de cuentacuentos para chicos de 3 a 5 años, que es el default del escritor.
    assert de_la_1["sistema"] == "EL PROMPT DEVOCIONAL"


async def test_sin_escritor_reporta_y_no_toca_nada(devocional: Story) -> None:
    """Así se audita un guion ya hecho, que es como se usó sobre el del 7-ago."""
    original = list(GUION_REAL)
    veredicto = await ScriptInspector(FakeRevisorDeGuion([REVISION_DEL_GUION_REAL])).inspect(
        devocional
    )

    assert not veredicto.paso
    assert veredicto.reescritas == []
    assert [e.narration for e in devocional.scenes] == original


async def test_un_revisor_que_cae_no_frena_el_devocional(devocional: Story) -> None:
    """Un guion sin revisar es peor que uno revisado; uno que no existe es mucho peor.

    Y los guardianes deterministas corren igual: son código, no una llamada. Por eso
    las dos muletillas siguen apareciendo aunque el revisor esté caído.
    """
    revisor = RevisorQueCae()
    veredicto = await ScriptInspector(revisor).inspect(devocional)

    assert revisor.llamadas > 0
    assert [r.regla for r in veredicto.reparos] == ["muletilla", "muletilla"]


async def test_una_escena_que_no_se_puede_reescribir_deja_la_que_habia(
    devocional: Story,
) -> None:
    """Si el escritor se cae, queda el texto anterior y el devocional sale igual."""

    class EscritorQueCae:
        async def reescribir(self, *a, **k):
            raise RuntimeError("500 del proveedor de texto")

    original = list(GUION_REAL)
    veredicto = await ScriptInspector(
        FakeRevisorDeGuion([REVISION_DEL_GUION_REAL]), EscritorQueCae()
    ).inspect(devocional)

    assert veredicto.reescritas == []
    assert [e.narration for e in devocional.scenes] == original


async def test_un_guion_limpio_no_se_toca(historia: Story) -> None:
    """El caso que tiene que ser barato: sin reparos, ni una reescritura."""
    historia.scenes = [
        Scene.from_plan(p, narration=t)
        for p, t in zip(
            historia.plan.scenes,
            [
                "Before this day unfolds, stop for one moment.",
                "The weight you carry has a name tonight.",
                "Father, I hand over what I cannot fix.",
                "The quiet does not always answer on time.",
                "Mercy arrives before the circumstance changes.",
                "Rest now. Comment PEACE and I will pray for you.",
            ],
            strict=True,
        )
    ]
    historia.advance_to(StoryStatus.PLANNED)
    historia.advance_to(StoryStatus.WRITTEN)

    escritor = EscritorFalso()
    veredicto = await ScriptInspector(FakeRevisorDeGuion(), escritor).inspect(historia)

    assert veredicto.paso
    assert escritor.llamadas == []


def test_la_correccion_no_sale_vacia() -> None:
    """Una corrección vacía es pedir lo mismo otra vez, que es lo que ya falló."""
    reparos = _reparos(_campos(REVISION_DEL_GUION_REAL), GUION_REAL)
    texto = _correccion([r for r in reparos if r.escena == 1])
    assert "CORRECCIÓN" in texto and "no worries" in texto
