"""Cómo cada valor educativo se convierte en conflicto narrativo.

Esto es el conocimiento pedagógico del motor, y es la razón por la que
`EducationalValue` es un enum curado y no texto libre: enseñar "compartir" no es
poner la palabra en el cuento, es construir una situación donde el protagonista
TENGA algo y le cueste darlo. Cada valor necesita su propio conflicto.

Sin esto, el planificador tendría que preguntarle a la IA "¿cómo armo una historia
sobre paciencia?" — y volveríamos a depender de que el modelo tenga un buen día.
Acá está decidido de antemano, una vez, y sale igual de bien las mil veces.

Sumar un valor nuevo = agregar su perfil acá y su entrada en el enum. Son las dos
únicas cosas que hay que pensar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.core.enums import EducationalValue, Emotion, NarrativeBeat


@dataclass(frozen=True, slots=True)
class ValueProfile:
    """El molde narrativo de un valor.

    Los `purposes` son las INSTRUCCIONES que recibe el escritor en cada beat, con
    `{protagonista}` y `{companero}` para completar. No son texto para el chico.
    """

    value: EducationalValue
    #: Qué situación crea el problema. Es el motor del conflicto.
    conflict: str
    #: La frase que resume la enseñanza. Va al cierre y a la descripción del post.
    moral: str
    #: Pregunta final al espectador. Lo que convierte a quien mira en quien comenta.
    question: str
    #: Instrucción para el escritor en cada beat.
    purposes: dict[NarrativeBeat, str]
    #: Emoción dominante en cada beat. La sobreescribe el planificador si hace falta.
    emotions: dict[NarrativeBeat, Emotion]
    #: Si el conflicto necesita un OBJETO concreto (compartir necesita algo que dar),
    #: qué tipo de objeto es. El motor elige uno del tema y lo mete en los propósitos,
    #: para que el texto Y el prompt de imagen hablen de la misma cosa.
    needs_prop: bool = False
    #: Variantes para cuando un beat se repite en historias largas. Sin esto, dos
    #: escenas del mismo beat salen casi idénticas — pasó de verdad ("el secreto la
    #: aplastaba" / "el secreto la envolvía" en dos escenas seguidas).
    escalations: dict[NarrativeBeat, tuple[str, ...]] = field(default_factory=dict)


def _emociones_base() -> dict[NarrativeBeat, Emotion]:
    """Curva emocional estándar: sube, cae, y se resuelve arriba.

    Vale para casi todos los valores; los que necesitan otra cosa la pisan.
    """
    return {
        NarrativeBeat.HOOK: Emotion.CURIOSITY,
        NarrativeBeat.PROBLEM: Emotion.FRUSTRATION,
        NarrativeBeat.ATTEMPT: Emotion.CURIOSITY,
        NarrativeBeat.FAILURE: Emotion.SADNESS,
        NarrativeBeat.LESSON: Emotion.SURPRISE,
        NarrativeBeat.ENDING: Emotion.JOY,
    }


PROFILES: dict[EducationalValue, ValueProfile] = {
    EducationalValue.SHARING: ValueProfile(
        value=EducationalValue.SHARING,
        conflict="{protagonista} tiene algo que quiere solo para sí",
        moral="Compartir nos hace más felices y fortalece la amistad.",
        question="¿Y vos, qué compartís con tus amigos?",
        needs_prop=True,
        escalations={
            NarrativeBeat.ATTEMPT: (
                "{protagonista} juega con {objeto} dándole la espalda a los demás",
                "{protagonista} se lleva {objeto} a un rincón para que nadie lo vea",
            ),
            NarrativeBeat.FAILURE: (
                "Jugar solo con {objeto} se vuelve aburrido enseguida",
                "{protagonista} mira a los demás jugar juntos y se siente afuera",
            ),
        },
        purposes={
            NarrativeBeat.HOOK: "Presentar a {protagonista} feliz porque consiguió {objeto}",
            NarrativeBeat.PROBLEM: (
                "{companero} quiere jugar con {objeto} y {protagonista} se niega"
            ),
            NarrativeBeat.ATTEMPT: "{protagonista} intenta disfrutar {objeto} solo",
            NarrativeBeat.FAILURE: (
                "Jugar solo con {objeto} resulta aburrido: {protagonista} se queda sin nadie"
            ),
            NarrativeBeat.LESSON: (
                "{protagonista} entiende que con {companero} sería más divertido "
                "y le ofrece {objeto}"
            ),
            NarrativeBeat.ENDING: "Los dos juegan juntos con {objeto}, mucho más felices",
        },
        emotions=_emociones_base(),
    ),
    EducationalValue.FRIENDSHIP: ValueProfile(
        value=EducationalValue.FRIENDSHIP,
        conflict="{protagonista} está solo y no sabe cómo acercarse a los demás",
        moral="Un amigo se gana acercándose, no esperando.",
        question="¿Y vos, cómo hiciste tu mejor amigo?",
        purposes={
            NarrativeBeat.HOOK: "Mostrar a {protagonista} mirando de lejos cómo juegan los demás",
            NarrativeBeat.PROBLEM: "{protagonista} quiere sumarse pero le da vergüenza",
            NarrativeBeat.ATTEMPT: "{protagonista} se acerca sin animarse a hablar",
            NarrativeBeat.FAILURE: "Se queda callado y el momento pasa",
            NarrativeBeat.LESSON: (
                "{companero} lo invita, y {protagonista} descubre que bastaba con animarse"
            ),
            NarrativeBeat.ENDING: "{protagonista} y {companero} juegan juntos como viejos amigos",
        },
        emotions={**_emociones_base(), NarrativeBeat.PROBLEM: Emotion.FEAR},
    ),
    EducationalValue.RESPECT: ValueProfile(
        value=EducationalValue.RESPECT,
        conflict="{protagonista} quiere imponer su forma de hacer las cosas",
        moral="Cada uno tiene su manera, y todas merecen respeto.",
        question="¿Y vos, en qué sos diferente a tus amigos?",
        purposes={
            NarrativeBeat.HOOK: "Presentar a {protagonista} muy seguro de cómo se hacen las cosas",
            NarrativeBeat.PROBLEM: "{companero} lo hace distinto y {protagonista} se burla",
            NarrativeBeat.ATTEMPT: "{protagonista} insiste en que su forma es la única buena",
            NarrativeBeat.FAILURE: "{companero} se aleja triste y {protagonista} se queda incómodo",
            NarrativeBeat.LESSON: (
                "{protagonista} prueba la forma de {companero} y descubre que "
                "también funciona"
            ),
            NarrativeBeat.ENDING: "Los dos hacen las cosas a su manera, juntos y contentos",
        },
        emotions=_emociones_base(),
    ),
    EducationalValue.HONESTY: ValueProfile(
        value=EducationalValue.HONESTY,
        conflict="{protagonista} rompe o pierde algo y no quiere admitirlo",
        moral="Decir la verdad cuesta un ratito; la mentira pesa mucho más.",
        question="¿Y vos, alguna vez dijiste la verdad aunque diera miedo?",
        needs_prop=True,
        escalations={
            NarrativeBeat.ATTEMPT: (
                "{protagonista} esconde los restos de {objeto} donde nadie los vea",
                "{protagonista} disimula y cambia de tema cuando alguien menciona {objeto}",
            ),
            NarrativeBeat.FAILURE: (
                "{protagonista} no puede dormir pensando en lo que hizo",
                "Alguien pregunta por {objeto} y {protagonista} siente que se le nota",
            ),
        },
        purposes={
            NarrativeBeat.HOOK: "Mostrar a {protagonista} jugando cerca de {objeto}",
            NarrativeBeat.PROBLEM: "Sin querer rompe {objeto}, y nadie lo vio",
            NarrativeBeat.ATTEMPT: "{protagonista} lo esconde y hace como si nada",
            NarrativeBeat.FAILURE: "No puede disfrutar de nada: el secreto le pesa",
            NarrativeBeat.LESSON: "{protagonista} cuenta la verdad y descubre que lo entienden",
            NarrativeBeat.ENDING: "{protagonista} y {companero} lo arreglan juntos, aliviados",
        },
        emotions={**_emociones_base(), NarrativeBeat.ATTEMPT: Emotion.FEAR},
    ),
    EducationalValue.EMPATHY: ValueProfile(
        value=EducationalValue.EMPATHY,
        conflict="{protagonista} no se da cuenta de que {companero} está mal",
        moral="Preguntar '¿estás bien?' puede cambiarle el día a alguien.",
        question="¿Y vos, cómo te das cuenta cuando un amigo está triste?",
        purposes={
            NarrativeBeat.HOOK: "Presentar a {protagonista} entusiasmado con su propio juego",
            NarrativeBeat.PROBLEM: (
                "{companero} está apartado y triste, pero {protagonista} no lo nota"
            ),
            NarrativeBeat.ATTEMPT: "{protagonista} lo invita a jugar sin preguntarle qué le pasa",
            NarrativeBeat.FAILURE: "{companero} se aleja más y {protagonista} no entiende por qué",
            NarrativeBeat.LESSON: "{protagonista} se sienta al lado y le pregunta cómo está",
            NarrativeBeat.ENDING: "{companero} se anima, y juegan juntos de verdad",
        },
        emotions=_emociones_base(),
    ),
    EducationalValue.PATIENCE: ValueProfile(
        value=EducationalValue.PATIENCE,
        conflict="{protagonista} quiere algo YA y no tolera esperar",
        moral="Las cosas más lindas necesitan su tiempo.",
        question="¿Y vos, qué estás esperando con muchas ganas?",
        purposes={
            NarrativeBeat.HOOK: "Presentar a {protagonista} esperando algo que le entusiasma mucho",
            NarrativeBeat.PROBLEM: "Falta demasiado y {protagonista} se desespera",
            NarrativeBeat.ATTEMPT: "{protagonista} intenta apurarlo de cualquier manera",
            NarrativeBeat.FAILURE: "Apurarlo lo arruina y hay que empezar de nuevo",
            NarrativeBeat.LESSON: "{companero} lo acompaña a esperar y el rato se hace corto",
            NarrativeBeat.ENDING: "Llega el momento y vale cada segundo de espera",
        },
        emotions={**_emociones_base(), NarrativeBeat.PROBLEM: Emotion.FRUSTRATION},
    ),
    EducationalValue.COURAGE: ValueProfile(
        value=EducationalValue.COURAGE,
        conflict="{protagonista} tiene miedo de algo que quiere hacer",
        moral="Ser valiente no es no tener miedo: es animarse igual.",
        question="¿Y vos, a qué te animaste aunque tuvieras miedo?",
        escalations={
            NarrativeBeat.ATTEMPT: (
                "{protagonista} se acerca unos pasos y se detiene",
                "{protagonista} estira la mano pero la retira enseguida",
            ),
            NarrativeBeat.FAILURE: (
                "{protagonista} se asusta y vuelve corriendo",
                "{protagonista} se esconde y mira desde lejos, apenado",
            ),
        },
        purposes={
            NarrativeBeat.HOOK: "Mostrar a {protagonista} frente a algo nuevo y grande",
            NarrativeBeat.PROBLEM: "Le da miedo y prefiere quedarse atrás",
            NarrativeBeat.ATTEMPT: "{protagonista} se acerca de a poco, temblando",
            NarrativeBeat.FAILURE: "Se asusta y vuelve corriendo",
            NarrativeBeat.LESSON: "{companero} lo acompaña y {protagonista} da el paso",
            NarrativeBeat.ENDING: "{protagonista} lo logra y se siente enorme",
        },
        emotions={
            **_emociones_base(),
            NarrativeBeat.PROBLEM: Emotion.FEAR,
            NarrativeBeat.ATTEMPT: Emotion.FEAR,
            NarrativeBeat.ENDING: Emotion.PRIDE,
        },
    ),
    EducationalValue.PERSEVERANCE: ValueProfile(
        value=EducationalValue.PERSEVERANCE,
        conflict="a {protagonista} no le sale algo y quiere abandonar",
        moral="No salió todavía no es lo mismo que no puedo.",
        question="¿Y vos, qué aprendiste después de intentarlo muchas veces?",
        escalations={
            NarrativeBeat.ATTEMPT: (
                "{protagonista} lo intenta otra vez, poniendo más fuerza",
                "{protagonista} prueba una manera completamente distinta",
            ),
            NarrativeBeat.FAILURE: (
                "Falla de nuevo, y esta vez le duele más",
                "{protagonista} se sienta en el piso, sin ganas de seguir",
            ),
        },
        purposes={
            NarrativeBeat.HOOK: "Presentar a {protagonista} con muchas ganas de lograr algo",
            NarrativeBeat.PROBLEM: "Lo intenta y no le sale para nada",
            NarrativeBeat.ATTEMPT: "{protagonista} prueba otra vez, de otra manera",
            NarrativeBeat.FAILURE: "Vuelve a fallar y se quiere rendir",
            NarrativeBeat.LESSON: (
                "{companero} lo anima y {protagonista} entiende que le falta "
                "práctica, no talento"
            ),
            NarrativeBeat.ENDING: "Lo consigue, y la alegría es enorme porque costó",
        },
        emotions={
            **_emociones_base(),
            NarrativeBeat.FAILURE: Emotion.FRUSTRATION,
            NarrativeBeat.ENDING: Emotion.PRIDE,
        },
    ),
}


def profile_for(value: EducationalValue) -> ValueProfile:
    """El molde narrativo de `value`.

    Lanza `KeyError` si falta: preferimos romper fuerte a generar una historia sin
    conflicto real. Un valor sin perfil es un bug de configuración, no un caso a
    manejar en silencio.
    """
    return PROFILES[value]
