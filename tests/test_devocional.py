"""El planificador devocional: la mitad del nicho nuevo que DECIDE.

Todo lo de acá es determinista — no hay IA de por medio. Si estos tests pasan,
cualquier devocional que salga del planificador tiene estructura válida.

Hay un bloque que no es como los demás y conviene leerlo antes de tocarlo: el de
"distinción entre videos". No prueba que el código funcione, prueba que el CATÁLOGO no
se parezca a sí mismo — porque eso es lo que YouTube castiga con la terminación del
canal entero, y porque es la clase de cosa que se degrada sola cuando alguien agrega
la necesidad número once a las apuradas.
"""

from __future__ import annotations

import pytest

from engine.core.enums import Emotion, Language, NarrativeBeat, ShotType, SpiritualNeed
from engine.core.exceptions import DomainError
from engine.core.models import Character, Style, Theme
from engine.core.models.character import Appearance
from engine.core.models.theme import Palette
from engine.generators.devotional import PROFILES, profile_for
from engine.generators.devotional_planner import (
    RITMO_DEVOCIONAL_S,
    DevotionalPlanner,
    invitation_for,
    promise_for,
)


@pytest.fixture
def planner() -> DevotionalPlanner:
    return DevotionalPlanner()


@pytest.fixture
def orante() -> Character:
    """La figura en pantalla. No es un protagonista: es un lugar donde ponerse.

    La `description` es la que evita el problema más caro del motor: sin rasgos ni
    manos visibles no hay dedos que contar, así que el error de anatomía que el
    verificador sólo ataja una de cada tres veces acá directamente no puede ocurrir.
    """
    return Character(
        id="orante",
        name="the one who prays",
        appearance=Appearance(
            species="human figure",
            description=(
                "a distant featureless silhouette seen from behind against strong "
                "backlight, no discernible facial features and no visible hands"
            ),
            colors=["backlit black", "warm amber rim light"],
        ),
    )


@pytest.fixture
def tema_amanecer() -> Theme:
    return Theme(
        id="amanecer",
        name="Quiet dawn",
        palette=Palette(primary="#F5C77E", secondary="#2E4A6B", accent="#FFFFFF"),
        locations=[
            "a hilltop above a valley at first light",
            "a shoreline at dawn",
            "an empty country road at sunrise",
        ],
    )


def _plan(planner, tema, orante, *, need=SpiritualNeed.ANXIETY, dur=150.0,
          idioma=Language.EN):
    return planner.create_plan(
        theme=tema, need=need, duration_s=dur, speaker=orante, language=idioma
    )


# --- estructura ------------------------------------------------------------------


def test_el_formato_del_nicho_da_diez_escenas(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """150 s es la duración MEDIANA medida en el nicho, no un número elegido a dedo.

    Sobre 53 videos de los canales de oración en inglés que más crecieron, la mediana
    dio 145 s (API de YouTube, 7-ago-2026). A 15 s por escena eso da 10 escenas.
    """
    plan = _plan(planner, tema_amanecer, orante)
    assert len(plan.scenes) == 10
    assert plan.total_duration_s == pytest.approx(150.0, abs=1.0)


@pytest.mark.parametrize("dur", [30.0, 60.0, 90.0, 120.0, 150.0, 180.0])
def test_cualquier_duracion_produce_un_plan_valido(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character, dur: float
) -> None:
    """`StoryPlan` se valida solo: construirlo YA prueba arco, índices y duración."""
    plan = _plan(planner, tema_amanecer, orante, dur=dur)
    assert plan.total_duration_s == pytest.approx(dur, abs=1.0)
    assert plan.beats[0] is NarrativeBeat.HOOK
    assert plan.beats[-1] is NarrativeBeat.ENDING


@pytest.mark.parametrize("need", list(SpiritualNeed))
def test_toda_necesidad_produce_un_devocional(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character,
    need: SpiritualNeed,
) -> None:
    """Las 10 necesidades funcionan sin tocar código."""
    plan = _plan(planner, tema_amanecer, orante, need=need)
    assert len(plan.scenes) >= 3


def test_el_ritmo_es_mas_lento_que_el_de_un_cuento(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Apurar un devocional le saca lo único que el formato tiene para ofrecer.

    El planificador de cuentos usa entre 4 y 8 s por escena; acá son 15.
    """
    plan = _plan(planner, tema_amanecer, orante, dur=150.0)
    assert RITMO_DEVOCIONAL_S >= 15.0
    assert all(s.duration_s >= 10.0 for s in plan.scenes)


def test_un_devocional_largo_repite_la_carga_y_la_oracion(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    plan = _plan(planner, tema_amanecer, orante, dur=180.0)
    assert plan.beats.count(NarrativeBeat.PROBLEM) >= 2
    assert plan.beats.count(NarrativeBeat.ATTEMPT) >= 2


def test_la_espera_nunca_se_repite(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Decir una vez "la respuesta no siempre llega" es honestidad. Dos, desánimo.

    Es la decisión menos obvia del planificador y la más fácil de romper sin querer
    agregando FAILURE a `_ORDEN_DE_REPETICION`.
    """
    for dur in (60.0, 90.0, 120.0, 150.0, 180.0, 300.0):
        plan = _plan(planner, tema_amanecer, orante, dur=dur)
        assert plan.beats.count(NarrativeBeat.FAILURE) <= 1, f"con {dur}s"


def test_los_beats_repetidos_reciben_instrucciones_distintas(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Si el escritor recibe dos veces la misma orden, escribe dos escenas iguales."""
    plan = _plan(planner, tema_amanecer, orante, dur=180.0)
    for beat in (NarrativeBeat.PROBLEM, NarrativeBeat.ATTEMPT):
        textos = [s.purpose for s in plan.scenes if s.beat is beat]
        assert len(textos) == len(set(textos)), f"{beat.value} repite instrucción"


def test_un_devocional_corto_conserva_la_promesa(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Nombrar una carga y no traer nada que la conteste deja a quien mira peor."""
    plan = _plan(planner, tema_amanecer, orante, dur=30.0)
    assert NarrativeBeat.LESSON in plan.beats
    assert NarrativeBeat.FAILURE not in plan.beats


def test_duracion_imposible_falla_con_un_mensaje_claro(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    with pytest.raises(DomainError, match="No se puede armar"):
        _plan(planner, tema_amanecer, orante, dur=4.0)


def test_es_determinista(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Mismos parámetros, mismo plan. Sin esto no se puede reproducir un bug."""
    assert _plan(planner, tema_amanecer, orante) == _plan(planner, tema_amanecer, orante)


# --- contenido -------------------------------------------------------------------


def test_hay_una_sola_figura_y_esta_en_todas_las_escenas(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    plan = _plan(planner, tema_amanecer, orante)
    assert plan.character_ids == {orante.id}
    assert all(s.character_ids == [orante.id] for s in plan.scenes)


def test_no_hay_emociones_cruzadas_ni_objeto(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Con un solo personaje, anotar su emoción sería duplicar el tono de la escena.

    Y el objeto trae de vuelta el problema del lote de cuentos: el barrilete que el
    plan declaraba y nunca llegaba a la imagen.
    """
    plan = _plan(planner, tema_amanecer, orante)
    assert all(s.character_emotions == {} for s in plan.scenes)
    assert all(s.prop == "" for s in plan.scenes)
    assert all(s.imagined_character_ids == [] for s in plan.scenes)


def test_no_quedan_plantillas_sin_completar(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    for need in SpiritualNeed:
        plan = _plan(planner, tema_amanecer, orante, need=need, dur=180.0)
        texto = " ".join(s.purpose for s in plan.scenes)
        assert "{" not in texto, f"{need.value} dejó una marca sin completar"


def test_la_promesa_llega_con_su_referencia_biblica(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """El beat de la promesa tiene que nombrar la Escritura, no aludirla."""
    for need in SpiritualNeed:
        plan = _plan(planner, tema_amanecer, orante, need=need)
        promesas = [s.purpose for s in plan.scenes if s.beat is NarrativeBeat.LESSON]
        assert promesas, f"{need.value} se quedó sin promesa"
        assert any(profile_for(need).scripture in p for p in promesas), need.value


def test_los_lugares_salen_del_tema(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    plan = _plan(planner, tema_amanecer, orante)
    assert all(s.location in tema_amanecer.locations for s in plan.scenes)


def test_la_curva_arranca_en_calma_y_no_cierra_en_el_peso(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """El gancho de un devocional es frenar a alguien, no excitarlo."""
    for need in SpiritualNeed:
        plan = _plan(planner, tema_amanecer, orante, need=need)
        assert plan.scenes[0].emotion in (Emotion.CALM, Emotion.CURIOSITY), need.value
        assert plan.scenes[-1].emotion in (Emotion.JOY, Emotion.CALM, Emotion.PRIDE)


def test_el_devocional_de_la_noche_no_cierra_eufórico(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Un video de antes de dormir que termina en fiesta despierta a quien se dormía."""
    plan = _plan(planner, tema_amanecer, orante, need=SpiritualNeed.NIGHT)
    assert plan.scenes[-1].emotion is Emotion.CALM


def test_la_espera_se_cuenta_de_lejos(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """El plano acompaña al sentido: en la espera la figura tiene que verse chica."""
    plan = _plan(planner, tema_amanecer, orante)
    esperas = [s for s in plan.scenes if s.beat is NarrativeBeat.FAILURE]
    assert all(s.shot is ShotType.WIDE for s in esperas)


def test_toda_escena_lleva_direccion_de_arte(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Sin nota visual, diez escenas de paisaje salen siendo el mismo paisaje."""
    for need in SpiritualNeed:
        plan = _plan(planner, tema_amanecer, orante, need=need)
        vacias = [s.index for s in plan.scenes if not s.visual_note]
        assert not vacias, f"{need.value} dejó sin imagen las escenas {vacias}"


# --- idioma ----------------------------------------------------------------------


@pytest.mark.parametrize("idioma", [Language.EN, Language.ES, Language.PT_BR])
def test_la_promesa_y_la_invitacion_salen_en_el_idioma_pedido(
    idioma: Language,
) -> None:
    """Las dos cosas que se DIBUJAN en pantalla tienen que hablar el idioma del video.

    Es la deuda que hoy tiene el planificador de cuentos: `ValueProfile.moral` está
    sólo en español, así que un cuento narrado en inglés cierra con la moraleja en
    castellano.
    """
    for need in SpiritualNeed:
        assert promise_for(need, idioma), f"{need.value} sin promesa en {idioma}"
        assert invitation_for(need, idioma), f"{need.value} sin invitación en {idioma}"


def test_el_default_del_motor_no_revienta() -> None:
    """`Language.ES_AR` es el default de todo el motor y los perfiles están en ES."""
    assert promise_for(SpiritualNeed.ANXIETY, Language.ES_AR) == promise_for(
        SpiritualNeed.ANXIETY, Language.ES
    )


def test_un_idioma_que_no_esta_cae_al_ingles(
    planner: DevotionalPlanner, tema_amanecer: Theme, orante: Character
) -> None:
    """Preferimos un devocional en inglés a una excepción en medio de un lote."""
    plan = _plan(planner, tema_amanecer, orante, idioma=Language.PT_BR)
    assert len(plan.scenes) == 10


# --- perfiles ---------------------------------------------------------------------


def test_toda_necesidad_del_enum_tiene_su_perfil() -> None:
    assert set(PROFILES) == set(SpiritualNeed)


def test_cada_perfil_cubre_todo_el_arco() -> None:
    for need, perfil in PROFILES.items():
        faltan = set(NarrativeBeat) - set(perfil.purposes)
        assert not faltan, f"{need.value} no tiene propósito para {faltan}"
        faltan = set(NarrativeBeat) - set(perfil.emotions)
        assert not faltan, f"{need.value} no tiene tono para {faltan}"


def test_cada_perfil_habla_los_tres_idiomas() -> None:
    for need, perfil in PROFILES.items():
        for idioma in (Language.EN, Language.ES, Language.PT_BR):
            assert perfil.promise.get(idioma), f"{need.value} sin promesa en {idioma}"
            assert perfil.invitation.get(idioma), f"{need.value} sin invitación en {idioma}"


def test_la_invitacion_pide_una_respuesta_concreta() -> None:
    """Lo que produce el comentario es pedir UNA palabra, no "dejá tu opinión".

    Es el beat que sostiene el 1,7 % de comentarios sobre vistas que se midió en el
    nicho — contra 0,000 % en el infantil, donde los comentarios están apagados.
    """
    for need, perfil in PROFILES.items():
        texto = perfil.invitation[Language.EN].lower()
        assert any(v in texto for v in ("comment", "type", "name")), need.value


# --- distinción entre videos ------------------------------------------------------
#
# Esto no prueba el código: prueba que el CATÁLOGO no se parezca a sí mismo.
#
# YouTube prohíbe textualmente el "AI-generated content made with generic or
# unoriginal templates giving the impression of mass production", y la sanción se
# aplica al canal entero. En enero de 2026 eliminó 16 canales de IA con 35 millones de
# subs sumados; los dos más grandes eran de cuentos y de historias bíblicas.
#
# Lo permitido es una serie donde "each video has a distinct storyline, focus, or
# concept". Estos cuatro tests son esa frase, escrita como invariante.


def test_cada_necesidad_nombra_una_carga_distinta() -> None:
    cargas = {p.burden for p in PROFILES.values()}
    assert len(cargas) == len(PROFILES)


def test_cada_necesidad_trae_una_escritura_distinta() -> None:
    """Dos devocionales que citan el mismo versículo son el mismo devocional."""
    escrituras = {p.scripture for p in PROFILES.values()}
    assert len(escrituras) == len(PROFILES)


def test_cada_necesidad_promete_y_pregunta_distinto() -> None:
    for idioma in (Language.EN, Language.ES, Language.PT_BR):
        promesas = {p.promise[idioma] for p in PROFILES.values()}
        invitaciones = {p.invitation[idioma] for p in PROFILES.values()}
        assert len(promesas) == len(PROFILES), f"promesas repetidas en {idioma}"
        assert len(invitaciones) == len(PROFILES), f"invitaciones repetidas en {idioma}"


def test_cada_necesidad_tiene_su_propio_mundo_visual() -> None:
    """El eje que más se nota y el que más fácil se descuida.

    Diez devocionales con el mismo amanecer genérico SON una plantilla, por más que
    el texto cambie: lo primero que ve un revisor es la imagen.
    """
    for need, perfil in PROFILES.items():
        assert perfil.imagery, f"{need.value} no tiene ninguna imagen propia"

    propias = [img for p in PROFILES.values() for img in p.imagery.values()]
    assert len(propias) == len(set(propias)), "hay dos necesidades con la misma imagen"


def test_ninguna_imagen_pide_caras_ni_manos() -> None:
    """La razón por la que este nicho es más barato de producir que un cuento.

    El verificador de anatomía sólo ataja uno de cada tres errores (medido el
    7-ago-2026), así que hoy un humano tiene que mirar cada imagen antes de publicar.
    Una silueta a contraluz no tiene dedos que contar: el error que el verificador no
    ve, acá no puede ocurrir. Basta con que alguien escriba "hands folded in prayer"
    en una imagen para perder esa propiedad, y por eso está en un test.
    """
    from engine.generators.devotional import IMAGEN_COMUN

    prohibidas = ("hand", "finger", "face", "smile", "eyes", "palm")
    todas = [img for p in PROFILES.values() for img in p.imagery.values()]
    todas += list(IMAGEN_COMUN.values())
    for img in todas:
        bajo = img.lower()
        assert not any(p in bajo for p in prohibidas), f"pide anatomía: {img!r}"


def test_el_prompt_no_le_dicta_al_modelo_una_frase_de_oracion() -> None:
    """El ejemplo entre paréntesis que se convirtió en muletilla (7-ago-2026).

    El prompt decía *"pray in the first person ('I bring you this thought')"*, y el
    primer devocional narrado abrió sus TRES escenas de oración con esa frase exacta.
    El escritor recibe la escena anterior, así que la tenía a la vista y la repitió
    igual: el ejemplo pesa más que el contexto.

    Es la misma trampa que ya costó una vuelta con el verificador de anatomía —ponerle
    la respuesta en la pregunta a un modelo es garantizar que la repita—, sólo que acá
    el ejemplo era de FORMA. Por eso el test no prohíbe una frase: prohíbe **dar
    ejemplos de texto narrado** en las reglas de persona gramatical.
    """
    from engine.prompts.devocional import system_prompt

    prompt = system_prompt(
        language=Language.EN,
        promise="Peace is not the absence of the storm.",
        scripture="Philippians 4:6-7",
    )
    assert "I bring you this thought" not in prompt
    assert "same words as the scene before" in prompt


def test_el_guardian_caza_dos_escenas_que_abren_igual() -> None:
    """Los otros cuatro tests de política comparan un devocional contra OTRO.

    Éste mira hacia adentro de uno solo, que es donde apareció el problema real. Tres
    aperturas idénticas dentro del mismo video son el *"generic or unoriginal
    template"* de la política del 16-jul-2026 tanto como diez videos calcados.
    """
    from engine.generators.devotional import aperturas_repetidas

    assert aperturas_repetidas([]) == []
    assert (
        aperturas_repetidas(
            [
                "You wake up at three a.m., eyes wide open.",
                "I bring you this thought that keeps returning.",
                "May you find rest in this new day.",
            ]
        )
        == []
    )

    # El caso real: las tres escenas de oración del primer devocional.
    repetidas = aperturas_repetidas(
        [
            "If this message found you tonight, it's for a reason.",
            "I bring you this thought that keeps returning...",
            "I bring you this thought... I ask for your body to unclench.",
            "I bring you this thought... I hand over each racing thought.",
        ]
    )
    assert repetidas == [(1, 2), (1, 3), (2, 3)]


def test_la_puntuacion_no_alcanza_para_esquivar_al_guardian() -> None:
    """Cambiar una coma por puntos suspensivos no vuelve original a una muletilla.

    El modelo varía la puntuación mucho antes que las palabras: si el guardián
    comparara el texto crudo, la misma apertura con tres puntos en vez de coma pasaría
    y el guardián quedaría de adorno.
    """
    from engine.generators.devotional import aperturas_repetidas

    assert aperturas_repetidas(
        ["I bring you this thought.", "I bring you, this thought..."]
    ) == [(0, 1)]


def test_un_estilo_sin_rostro_nunca_pide_una_cara(orante: Character, tema_amanecer: Theme) -> None:
    """Las dos imágenes rotas del 7-ago-2026, convertidas en un test.

    El primer devocional narrado sacó una escena que era un primer plano de una cara con
    la boca abierta y otra con la figura saltando con los brazos en alto. Ninguna estaba
    mal dibujada — salieron **exactamente como se las pidió**, porque el prompt de
    imagen traduce la emoción a cara y postura:

        SURPRISE → "boca abierta, ojos redondos, cuerpo erguido de golpe"
        JOY      → "sonrisa grande, ojos brillantes, postura saltarina"

    Es la regla correcta para un cuento y la ruina de un nicho que se eligió PORQUE no
    tiene caras que verificar. El prompt negativo ya decía "faces, close-up hands" y no
    alcanzó: **el positivo le gana al negativo**, y por eso esto se prueba sobre el
    prompt positivo.
    """
    from engine.core.enums import Emotion
    from engine.core.models.scene import Scene
    from engine.prompts import image as image_prompts

    estilo = Style(
        id="luz-natural",
        name="Natural light",
        art_style="cinematic landscape photography",
        emotion_in_light=True,
        continuity="MISMA paleta y MISMA hora del día que el resto del devocional",
    )
    prohibidas = (
        "sonrisa", "boca abierta", "ojos redondos", "ojos brillantes", "saltarina",
        "cejas", "mirada baja", "mentón", "ceño",
    )
    for emocion in Emotion:
        escena = Scene(
            index=0,
            beat=NarrativeBeat.LESSON,
            purpose="Bring the promise",
            duration_s=15.0,
            narration="a peace that guards the heart",
            location="a still lake under an open sky",
            character_ids=[orante.id],
            emotion=emocion,
        )
        prompt = image_prompts.compose(
            escena, style=estilo, theme=tema_amanecer, characters={orante.id: orante}
        ).lower()
        for palabra in prohibidas:
            assert palabra not in prompt, f"{emocion.value} pide {palabra!r}: {prompt}"
        assert "no se le ve la cara" in prompt
        assert "día soleado y despejado" not in prompt


def test_el_estilo_del_cuento_no_cambio(orante: Character, tema_amanecer: Theme) -> None:
    """La otra mitad de la regla de arriba: los cuentos tienen que salir IGUALES.

    `emotion_in_light` y `continuity` son aditivos y con default de cuento justamente
    para que agregar un nicho no le cambie una coma al que ya está publicando.
    """
    from engine.core.enums import Emotion
    from engine.core.models.scene import Scene
    from engine.prompts import image as image_prompts

    estilo = Style(id="pixar", name="Pixar", art_style="animación 3D estilo Pixar")
    escena = Scene(
        index=0,
        beat=NarrativeBeat.LESSON,
        purpose="Dino ofrece la pelota",
        duration_s=15.0,
        narration="Dino le ofrece la pelota",
        location="el claro del bosque",
        character_ids=[orante.id],
        emotion=Emotion.JOY,
    )
    prompt = image_prompts.compose(
        escena, style=estilo, theme=tema_amanecer, characters={orante.id: orante}
    )
    assert "sonrisa grande, ojos brillantes, postura saltarina" in prompt
    assert "día soleado y despejado" in prompt


def test_la_promesa_no_se_cuenta_en_primer_plano() -> None:
    """`primer_plano` significa, textual, *"las caras y las manos llenan el cuadro"*.

    El planificador pedía `CLOSE_UP` para el beat de la promesa con la intención —
    escrita en un comentario, donde el prompt de imagen no puede leerla— de que fuera
    un primer plano DE LA LUZ. Un comentario no es una interfaz.
    """
    from engine.core.enums import ShotType
    from engine.generators.devotional_planner import PLANO_POR_BEAT

    assert ShotType.CLOSE_UP not in PLANO_POR_BEAT.values()
