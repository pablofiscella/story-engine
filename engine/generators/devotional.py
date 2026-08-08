"""Cómo cada necesidad espiritual se convierte en una oración guiada.

Es el `values.py` del nicho devocional: el conocimiento del género, escrito una vez,
para que el devocional 500 salga tan armado como el primero.

QUÉ CAMBIA RESPECTO DEL CUENTO, y por qué justifica un módulo aparte en vez de ocho
perfiles más en `values.py`:

1. **No hay conflicto, hay una carga.** El cuento necesita que al protagonista le
   PASE algo. Acá no pasa nada: alguien está despierto a las tres de la mañana y del
   otro lado una voz le nombra lo que está cargando. El motor del cuento es el
   conflicto; el motor de esto es el reconocimiento.
2. **El destinatario está en la pantalla, no en la escena.** El "protagonista" no
   aprende nada — es una silueta que representa a quien mira. Por eso no hay
   compañero, no hay objeto y no hay emociones cruzadas entre personajes.
3. **El cierre pide respuesta.** La moraleja de un cuento se entiende sola; acá el
   último beat existe para que quien mira ESCRIBA algo. Es la diferencia medida entre
   1,7 % de comentarios en este nicho y 0,000 % en el infantil (ver el sondeo del
   7-ago-2026 en el diario del vault): un canal "hecho para niños" no tiene
   comentarios ni como opción.

LO QUE SE APROVECHA TAL CUAL: los seis beats de `NarrativeBeat`. No se inventó un
arco nuevo porque el del género YA es ése, sólo que con otros nombres — y reusarlo
significa que `StoryPlan` valida esto con el mismo código que valida los cuentos, sin
tocar una línea de `constants.py`:

    HOOK    → la llamada      "si esto te apareció hoy, quedate un minuto"
    PROBLEM → la carga        el peso concreto, dicho con nombre y apellido
    ATTEMPT → la oración      el pedido dicho en voz alta, en primera persona
    FAILURE → la espera       el momento en que la respuesta no llega
    LESSON  → la promesa      la Escritura que contesta la carga del PROBLEM
    ENDING  → la bendición    la declaración sobre quien mira, y el pedido de respuesta

LOS DATOS VAN EN INGLÉS y el código en español, que es lo que parece una
inconsistencia y no lo es: el nicho primario es inglés (es donde está el RPM y donde
los canales nuevos crecen), y el `purpose` es la instrucción literal que recibe el
escritor. Pedirle en español que escriba en inglés agrega una traducción en el medio
que es exactamente donde se cuelan las frases en el idioma equivocado.

SOBRE LAS ESCRITURAS: cada perfil lleva la REFERENCIA, no el texto del versículo. Dos
razones, las dos prácticas: el texto cambia según la traducción y varias tienen
copyright vigente, y una cita textual mal transcripta en este nicho no es una errata
sino una falta. El escritor recibe la referencia y una paráfrasis nuestra.

Las doce referencias se verificaron una por una contra BibleGateway el 7-ago-2026,
cruzadas con una segunda fuente: las doce existen y dicen lo que el perfil dice que
dicen. **Si algún día se quiere citar el versículo TEXTUAL, la traducción no da lo
mismo:**

- **Inglés → WEBBE** (World English Bible, British Edition). Dominio público, sin
  atribución obligatoria, apta para uso comercial. La WEB americana traduce el nombre
  divino como "Yahweh", que en devocional suena raro; la británica dice "the LORD".
- **Español → Reina-Valera 1909.** Dominio público por ser anterior a 1930.
- **NO usar Reina-Valera 1960**: su copyright está vigente (Sociedades Bíblicas
  Unidas, renovado en 1988) y su licencia libre de 500 versículos **excluye
  explícitamente el uso comercial**. Un canal monetizado cae de ese lado.
- La KJV es dominio público en todo el mundo salvo el Reino Unido, donde tiene Crown
  copyright perpetuo. Para publicar desde acá el riesgo es teórico, pero WEBBE no
  tiene ni ese asterisco.

EL RIESGO QUE DECIDE SI ESTO VIVE O NO, y por qué está escrito en un módulo de código
y no en una nota aparte: el 16-jul-2026 YouTube partió su política de "contenido
inauténtico" en tres, y una de las tres prohíbe textualmente

    "AI-generated content made with generic or unoriginal templates giving the
     impression of mass production"

y

    "videos where characters are put in the same situation over and over again with
     the same outcome"

En enero de 2026 YouTube eliminó 16 canales de IA con 35 millones de suscriptores
sumados. **Los dos más grandes del mundo eran en español, y eran estos dos nichos:**
"Cuentos Fascinantes" (cuentos, 5,95 M de subs) e "Imperio de Jesus" (historias
bíblicas narradas con IA, 5,87 M). Los dos publicaban varios episodios por día.

O sea: el precedente más parecido a lo que hace este motor terminó cancelado. Lo que
la política **sí** bendice, también textual, es

    "using AI to visualize a unique character and narrative you invented"

y una serie donde "each video has a distinct storyline, focus, or concept". La línea
no pasa por usar IA: pasa por si cada video es una pieza propia o una plantilla con
los nombres cambiados. La política se aplica **al canal entero**, no video por video.

Por eso este módulo está armado para que cada devocional se distinga de los otros en
CUATRO ejes a la vez —la carga, la promesa, la Escritura y el mundo visual— y hay un
test que lo verifica como invariante (`test_devocional.py`). Es la traducción de esa
política a algo que falla en CI antes de publicar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.core.enums import Emotion, Language, NarrativeBeat, SpiritualNeed


@dataclass(frozen=True, slots=True)
class DevotionalProfile:
    """El molde de una oración guiada.

    Los `purposes` son INSTRUCCIONES para el escritor, con `{orante}` para completar
    con el nombre de la figura que se ve en pantalla. No son texto para el espectador.
    """

    need: SpiritualNeed
    #: La carga concreta. Es lo que reemplaza al conflicto del cuento, y tiene que ser
    #: ESPECÍFICA: "no llegar a fin de mes" funciona, "las dificultades" no. Lo que
    #: hace que alguien se quede es reconocerse, y nadie se reconoce en una categoría.
    burden: str
    #: La referencia bíblica que responde a la carga. Sólo la referencia: ver el
    #: encabezado del módulo.
    scripture: str
    #: La promesa en nuestras palabras, por idioma. VA AL PRODUCTO FINAL — se dibuja
    #: en la placa de cierre—, así que no puede quedar en un solo idioma como quedó
    #: `ValueProfile.moral`, que hoy sale en español aunque el cuento se narre en otro.
    promise: dict[Language, str]
    #: El cierre que pide respuesta, por idioma. Es la pieza que convierte a quien mira
    #: en quien comenta, y la que el nicho infantil no puede tener.
    invitation: dict[Language, str]
    #: Instrucción para el escritor en cada beat.
    purposes: dict[NarrativeBeat, str]
    #: El tono de cada beat. Acá es el tono de la ESCENA y de la voz, no lo que siente
    #: un personaje: no hay nadie sintiendo nada, hay una imagen y una narración.
    emotions: dict[NarrativeBeat, Emotion]
    #: Dirección de arte por beat, cuando el beat pide una imagen concreta.
    imagery: dict[NarrativeBeat, str] = field(default_factory=dict)
    #: Variantes para cuando un beat se repite (un devocional de 150 s nombra varias
    #: cargas seguidas: "si estás cargando X… si estás cargando Y"). Sin esto, dos
    #: escenas del mismo beat salen calcadas — el problema ya documentado en
    #: `values.py`, que acá aparece MÁS seguido porque el formato del nicho dura
    #: 145 s de mediana y no 40 s, o sea casi el doble de escenas.
    deepenings: dict[NarrativeBeat, tuple[str, ...]] = field(default_factory=dict)


def _tono_base() -> dict[NarrativeBeat, Emotion]:
    """La curva del género: entra en calma, baja al peso, y sale en paz.

    No es la curva del cuento. El cuento arranca en CURIOSITY porque tiene que
    enganchar con una pregunta; un devocional arranca en CALM porque su gancho es lo
    contrario — frenar a alguien que viene scrolleando rápido. La primera imagen no
    compite con el feed por energía, compite por quietud.
    """
    return {
        NarrativeBeat.HOOK: Emotion.CALM,
        NarrativeBeat.PROBLEM: Emotion.SADNESS,
        NarrativeBeat.ATTEMPT: Emotion.CALM,
        NarrativeBeat.FAILURE: Emotion.FEAR,
        NarrativeBeat.LESSON: Emotion.SURPRISE,
        NarrativeBeat.ENDING: Emotion.JOY,
    }


#: Imágenes que sirven para cualquier necesidad, cuando el perfil no pide una propia.
#: Todas evitan rostros y manos a propósito — ver `PROFILES` abajo.
#:
#: Tienen que cubrir LOS SEIS beats, no los que a uno se le ocurran: una escena sin
#: dirección de arte sale genérica, y diez escenas genéricas son exactamente la
#: "plantilla" que la política de contenido inauténtico castiga. El hueco lo encontró
#: `test_toda_escena_lleva_direccion_de_arte`, que dejaba mudas la oración y la
#: bendición — los dos beats que más se repiten en un devocional largo.
IMAGEN_COMUN: dict[NarrativeBeat, str] = {
    NarrativeBeat.HOOK: (
        "wide landscape at first light, no people, soft mist over the horizon"
    ),
    NarrativeBeat.PROBLEM: (
        "a single dim light in a wide dark landscape, everything else in shadow"
    ),
    NarrativeBeat.ATTEMPT: (
        "a distant silhouette standing still with head bowed, seen from behind "
        "against a wide bright sky"
    ),
    NarrativeBeat.FAILURE: (
        "a single distant silhouette seen from very far away, dwarfed by an enormous "
        "sky, back to the camera"
    ),
    NarrativeBeat.LESSON: (
        "a shaft of light breaking through clouds onto the ground, no figures"
    ),
    NarrativeBeat.ENDING: (
        "a wide horizon fully lit at golden hour, the whole landscape open and clear"
    ),
}


PROFILES: dict[SpiritualNeed, DevotionalProfile] = {
    SpiritualNeed.ANXIETY: DevotionalProfile(
        need=SpiritualNeed.ANXIETY,
        burden="a mind that will not stop running at night",
        scripture="Philippians 4:6-7",
        promise={
            Language.EN: "Peace is not the absence of the storm. It is God standing in it with you.",
            Language.ES: "La paz no es que se vaya la tormenta. Es que Dios se queda adentro de ella con vos.",
            Language.PT_BR: "A paz não é a tempestade ir embora. É Deus ficar dentro dela com você.",
        },
        invitation={
            Language.EN: "If your mind has been loud lately, type AMEN so I can pray for you by name.",
            Language.ES: "Si tu cabeza no para últimamente, escribí AMÉN y oro por vos por tu nombre.",
            Language.PT_BR: "Se sua mente não para ultimamente, escreva AMÉM e eu oro por você pelo nome.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Tell the viewer that if this reached them tonight it was not an accident, "
                "and ask them to stop scrolling for sixty seconds"
            ),
            NarrativeBeat.PROBLEM: (
                "Name the exact feeling of lying awake replaying a conversation, without "
                "explaining anxiety or giving advice"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray out loud in the first person, handing the racing thoughts over one by one"
            ),
            NarrativeBeat.FAILURE: (
                "Admit honestly that the noise does not always stop the moment we pray"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: peace that guards the heart even before "
                "the circumstance changes"
            ),
            NarrativeBeat.ENDING: (
                "Speak a short blessing of rest over the viewer and ask them to answer"
            ),
        },
        emotions=_tono_base(),
        imagery={
            NarrativeBeat.PROBLEM: (
                "a lit window seen from outside in the dark, the only one awake on the street"
            ),
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name the 3 a.m. wake-up: eyes open, nothing wrong, and still no rest",
                "Name the tiredness of pretending all day that nothing is heavy",
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray specifically for the thought that keeps coming back",
                "Pray for the body to unclench: the jaw, the shoulders, the breath",
            ),
        },
    ),
    SpiritualNeed.MORNING: DevotionalProfile(
        need=SpiritualNeed.MORNING,
        burden="waking up already behind, before the day has even started",
        scripture="Lamentations 3:22-23",
        promise={
            Language.EN: "Yesterday does not get a vote in today. The mercy is new this morning.",
            Language.ES: "Ayer no vota en el día de hoy. La misericordia es nueva esta mañana.",
            Language.PT_BR: "Ontem não vota no dia de hoje. A misericórdia é nova esta manhã.",
        },
        invitation={
            Language.EN: "Comment the word NEW if you are claiming a fresh start today.",
            Language.ES: "Escribí NUEVO si hoy estás empezando de nuevo.",
            Language.PT_BR: "Escreva NOVO se hoje você está começando de novo.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Greet the viewer at the very start of their day and tell them this minute "
                "is the first thing they are giving to God"
            ),
            NarrativeBeat.PROBLEM: (
                "Name waking up already carrying yesterday: what was left undone, what was said"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person, handing over the hours of this day one at a time"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that mornings often start before we feel ready for them"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: mercy that is renewed every single morning"
            ),
            NarrativeBeat.ENDING: (
                "Bless the viewer's day out loud and ask them to answer"
            ),
        },
        emotions={**_tono_base(), NarrativeBeat.HOOK: Emotion.CURIOSITY},
        imagery={
            NarrativeBeat.HOOK: (
                "the very first light hitting a quiet valley, dew on the grass, no people"
            ),
            NarrativeBeat.ENDING: "an open road heading toward a bright sunrise",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name opening your eyes already tired of a day that has not happened yet",
                "Name the weight of a list that was long before the alarm went off",
            ),
        },
    ),
    SpiritualNeed.NIGHT: DevotionalProfile(
        need=SpiritualNeed.NIGHT,
        burden="lying down with the day still unfinished",
        scripture="Psalm 4:8",
        promise={
            Language.EN: "You are allowed to stop. Nothing falls apart tonight because you slept.",
            Language.ES: "Tenés permiso de parar. Nada se rompe esta noche porque hayas dormido.",
            Language.PT_BR: "Você tem permissão de parar. Nada desmorona esta noite porque você dormiu.",
        },
        invitation={
            Language.EN: "Type REST and I will pray over your night before I sleep.",
            Language.ES: "Escribí DESCANSO y oro por tu noche antes de dormirme.",
            Language.PT_BR: "Escreva DESCANSO e eu oro pela sua noite antes de dormir.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Speak softly to someone who is already in bed and tell them this is the "
                "last thing they need to hear today"
            ),
            NarrativeBeat.PROBLEM: (
                "Name the habit of reviewing the whole day the moment the lights go out"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person, setting down what will still be there tomorrow"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that some nights the worry comes back the moment we close our eyes"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: lying down and sleeping in peace, kept safe"
            ),
            NarrativeBeat.ENDING: (
                "Speak a blessing of sleep over the viewer, quietly, and ask them to answer"
            ),
        },
        # El único perfil que NO cierra en alegría: un devocional de antes de dormir que
        # termina eufórico despierta a quien se estaba durmiendo. Cierra en calma.
        emotions={**_tono_base(), NarrativeBeat.ENDING: Emotion.CALM},
        imagery={
            NarrativeBeat.HOOK: "a still lake under a deep blue night sky, full moon, no people",
            NarrativeBeat.ENDING: "a calm horizon of stars, everything quiet",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name the replay of one conversation that will not let go",
                "Name the tiredness that sleep alone does not fix",
            ),
        },
    ),
    SpiritualNeed.STRENGTH: DevotionalProfile(
        need=SpiritualNeed.STRENGTH,
        burden="having nothing left and still having to show up tomorrow",
        scripture="Isaiah 40:31",
        promise={
            Language.EN: "You are not running out. You are being carried while you rest.",
            Language.ES: "No te estás quedando sin nada. Te están sosteniendo mientras descansás.",
            Language.PT_BR: "Você não está se esgotando. Você está sendo carregado enquanto descansa.",
        },
        invitation={
            Language.EN: "If you are tired in a way sleep does not fix, comment I NEED STRENGTH.",
            Language.ES: "Si estás cansado de un cansancio que no se arregla durmiendo, escribí FUERZA.",
            Language.PT_BR: "Se você está cansado de um cansaço que dormir não resolve, escreva FORÇA.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Speak to someone who kept going today on empty, and tell them you see it"
            ),
            NarrativeBeat.PROBLEM: (
                "Name the specific exhaustion of holding everything together for other people"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person, admitting out loud that there is nothing left"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that strength usually does not arrive as a sudden surge"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: renewed strength for those who wait, "
                "wings like eagles"
            ),
            NarrativeBeat.ENDING: (
                "Declare renewed strength over the viewer and ask them to answer"
            ),
        },
        emotions={**_tono_base(), NarrativeBeat.ENDING: Emotion.PRIDE},
        imagery={
            NarrativeBeat.LESSON: "an eagle rising on a thermal against a vast open sky",
            NarrativeBeat.ENDING: "a mountain ridge at golden hour, wide and clear",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name being the one everybody leans on, with nobody to lean on",
                "Name doing it all again tomorrow with the same empty tank",
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray for strength for the next single hour, not for the whole year",
                "Pray to be allowed to stop pretending it is fine",
            ),
        },
    ),
    SpiritualNeed.PROVISION: DevotionalProfile(
        need=SpiritualNeed.PROVISION,
        burden="a number in the account that does not reach the end of the month",
        scripture="Philippians 4:19",
        promise={
            Language.EN: "God has never once been late. Early is not how He usually does it.",
            Language.ES: "Dios nunca llegó tarde. Temprano tampoco es su costumbre.",
            Language.PT_BR: "Deus nunca chegou atrasado. Cedo também não é o costume dele.",
        },
        invitation={
            Language.EN: "Comment PROVISION and I will agree with you in prayer for it.",
            Language.ES: "Escribí PROVISIÓN y me pongo de acuerdo con vos en oración.",
            Language.PT_BR: "Escreva PROVISÃO e eu concordo com você em oração.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Speak to someone who has done the math tonight and it did not work out"
            ),
            NarrativeBeat.PROBLEM: (
                "Name the shame of the specific bill, without moralizing about money"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person for the concrete need, saying the amount is not "
                "too small to bring"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that the answer rarely comes as a sudden windfall"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: a God who supplies what is needed, "
                "out of His riches and not out of ours"
            ),
            NarrativeBeat.ENDING: (
                "Speak provision over the viewer's household and ask them to answer"
            ),
        },
        emotions=_tono_base(),
        imagery={
            NarrativeBeat.PROBLEM: "an empty wooden table in a plain kitchen at dusk",
            NarrativeBeat.LESSON: "a field of wheat at harvest, heavy and gold",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name choosing which bill gets paid this month",
                "Name saying no to your kids for something small",
            ),
        },
    ),
    SpiritualNeed.HEALING: DevotionalProfile(
        need=SpiritualNeed.HEALING,
        burden="a body that will not cooperate, and a waiting room that never ends",
        scripture="Psalm 103:2-3",
        promise={
            Language.EN: "You are not your diagnosis. You are the one God is still holding.",
            Language.ES: "No sos tu diagnóstico. Sos a quien Dios sigue sosteniendo.",
            Language.PT_BR: "Você não é o seu diagnóstico. Você é quem Deus continua sustentando.",
        },
        invitation={
            Language.EN: "Type the name of who you are praying for and I will pray it too.",
            Language.ES: "Escribí el nombre de por quién estás orando y yo también oro.",
            Language.PT_BR: "Escreva o nome de quem você está orando e eu oro também.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Speak to someone waiting on a result, or sitting beside someone who is"
            ),
            NarrativeBeat.PROBLEM: (
                "Name the fear of the appointment without promising any medical outcome"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person for the body, for the doctors, and for the fear itself"
            ),
            NarrativeBeat.FAILURE: (
                "Admit honestly that healing does not always come the way or the day we ask"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: the God who forgives and heals, "
                "without turning it into a guarantee"
            ),
            NarrativeBeat.ENDING: (
                "Speak comfort and courage over the viewer and ask them to answer"
            ),
        },
        emotions=_tono_base(),
        imagery={
            NarrativeBeat.PROBLEM: "a long empty hospital corridor at night, no people",
            NarrativeBeat.LESSON: "morning light falling across a made bed by an open window",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name the silence of waiting for a phone call",
                "Name being the one who has to stay strong in the room",
            ),
        },
    ),
    SpiritualNeed.FAMILY: DevotionalProfile(
        need=SpiritualNeed.FAMILY,
        burden="a child who stopped answering, and a parent who keeps praying anyway",
        scripture="Isaiah 54:13",
        promise={
            Language.EN: "The prayers you pray over them outlive the silence between you.",
            Language.ES: "Las oraciones que hacés por ellos duran más que el silencio entre ustedes.",
            Language.PT_BR: "As orações que você faz por eles duram mais que o silêncio entre vocês.",
        },
        invitation={
            Language.EN: "Comment their first name. I will pray for them tonight.",
            Language.ES: "Escribí su nombre. Oro por esa persona esta noche.",
            Language.PT_BR: "Escreva o primeiro nome. Eu oro por essa pessoa hoje à noite.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Speak to a parent who has been carrying one particular person in prayer "
                "for a long time"
            ),
            NarrativeBeat.PROBLEM: (
                "Name the ache of loving someone who is far away, without blaming anyone"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person for that person by name, and for the relationship"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that years can pass with no visible change"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: children taught by God Himself, "
                "and great peace among them"
            ),
            NarrativeBeat.ENDING: (
                "Bless the viewer's household out loud and ask them to answer"
            ),
        },
        emotions=_tono_base(),
        imagery={
            NarrativeBeat.PROBLEM: "an empty chair at a set dinner table, warm lamp light",
            NarrativeBeat.ENDING: "a doorway open onto a lit path at dusk",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name the message that was typed and never sent",
                "Name the holidays where one seat stays empty",
            ),
        },
    ),
    SpiritualNeed.GUIDANCE: DevotionalProfile(
        need=SpiritualNeed.GUIDANCE,
        burden="a decision with no obviously right answer",
        scripture="Proverbs 3:5-6",
        promise={
            Language.EN: "You do not need the whole map. You need the next step, and that one is lit.",
            Language.ES: "No necesitás el mapa entero. Necesitás el próximo paso, y ése está iluminado.",
            Language.PT_BR: "Você não precisa do mapa inteiro. Precisa do próximo passo, e ele está iluminado.",
        },
        invitation={
            Language.EN: "If you have a decision to make this week, comment GUIDE ME.",
            Language.ES: "Si tenés una decisión para tomar esta semana, escribí GUIAME.",
            Language.PT_BR: "Se você tem uma decisão para tomar esta semana, escreva ME GUIE.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Speak to someone standing in front of a choice they have been avoiding"
            ),
            NarrativeBeat.PROBLEM: (
                "Name the exhaustion of going back and forth without deciding"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person, admitting they do not know and asking to be led"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that clarity rarely arrives all at once"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: trusting rather than leaning on our own "
                "understanding, and paths made straight"
            ),
            NarrativeBeat.ENDING: (
                "Declare clear direction over the viewer and ask them to answer"
            ),
        },
        emotions=_tono_base(),
        imagery={
            NarrativeBeat.PROBLEM: "a path splitting into two through a heavy forest fog",
            NarrativeBeat.LESSON: "a single lantern lighting the next few steps of a dark trail",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name lying awake making the same list of pros and cons",
                "Name the fear of choosing wrong and living with it",
            ),
        },
    ),
    SpiritualNeed.FORGIVENESS: DevotionalProfile(
        need=SpiritualNeed.FORGIVENESS,
        burden="something done years ago that still comes back at night",
        scripture="1 John 1:9",
        promise={
            Language.EN: "God is not holding it. You are. And you are allowed to put it down.",
            Language.ES: "Dios no lo está sosteniendo. Vos sí. Y tenés permiso de soltarlo.",
            Language.PT_BR: "Deus não está segurando isso. Você está. E você pode soltar.",
        },
        invitation={
            Language.EN: "You do not have to say what it was. Just comment FREE.",
            Language.ES: "No hace falta que digas qué fue. Escribí LIBRE y ya está.",
            Language.PT_BR: "Você não precisa dizer o que foi. Só escreva LIVRE.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Speak to someone who has already been forgiven but cannot feel it"
            ),
            NarrativeBeat.PROBLEM: (
                "Name carrying an old thing in private, without asking what it was"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person, saying it out loud to God without detailing it aloud"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that the feeling of guilt often outlasts the forgiveness itself"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: confession met with faithful forgiveness "
                "and cleansing"
            ),
            NarrativeBeat.ENDING: (
                "Declare the viewer free of it and ask them to answer"
            ),
        },
        emotions=_tono_base(),
        imagery={
            NarrativeBeat.PROBLEM: "a heavy stone half buried in wet sand at low tide",
            NarrativeBeat.LESSON: "a tide washing a beach completely smooth and clean",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name the memory that arrives uninvited in the middle of a good day",
                "Name believing God forgave it while still refusing to",
            ),
        },
    ),
    SpiritualNeed.GRATITUDE: DevotionalProfile(
        need=SpiritualNeed.GRATITUDE,
        burden="a life that is actually fine, and a heart that forgot to notice",
        scripture="1 Thessalonians 5:18",
        promise={
            Language.EN: "Gratitude does not wait for the season to improve. It changes the season.",
            Language.ES: "La gratitud no espera a que mejore la época. Cambia la época.",
            Language.PT_BR: "A gratidão não espera a fase melhorar. Ela muda a fase.",
        },
        invitation={
            Language.EN: "Comment one thing you are grateful for today. Just one.",
            Language.ES: "Escribí una sola cosa por la que estés agradecido hoy. Una.",
            Language.PT_BR: "Escreva uma coisa pela qual você é grato hoje. Uma só.",
        },
        purposes={
            NarrativeBeat.HOOK: (
                "Ask the viewer to notice one ordinary thing that went right today"
            ),
            NarrativeBeat.PROBLEM: (
                "Name how easily a good day disappears under the one thing that went wrong"
            ),
            NarrativeBeat.ATTEMPT: (
                "Pray in the first person, thanking God for something small and specific"
            ),
            NarrativeBeat.FAILURE: (
                "Admit that gratitude is hard to feel on command"
            ),
            NarrativeBeat.LESSON: (
                "Bring the promise of {escritura}: giving thanks in all circumstances, "
                "not for all circumstances"
            ),
            NarrativeBeat.ENDING: (
                "Bless the viewer's ordinary day out loud and ask them to answer"
            ),
        },
        emotions={**_tono_base(), NarrativeBeat.PROBLEM: Emotion.FRUSTRATION},
        imagery={
            NarrativeBeat.HOOK: "steam rising from a cup on a windowsill in morning light",
            NarrativeBeat.ENDING: "a warmly lit ordinary street at golden hour",
        },
        deepenings={
            NarrativeBeat.PROBLEM: (
                "Name remembering the one criticism and forgetting the ten kind words",
                "Name waiting to be happy until something specific finally changes",
            ),
        },
    ),
}


def profile_for(need: SpiritualNeed) -> DevotionalProfile:
    """El molde de `need`.

    Lanza `KeyError` si falta, igual que `values.profile_for`: una necesidad sin perfil
    es un bug de configuración, y preferimos romper fuerte a publicar un devocional que
    nombra una carga y no trae ninguna promesa.
    """
    return PROFILES[need]


#: Cuántas palabras del arranque se comparan. Tres alcanza para cazar una muletilla
#: ("I bring you this…") y es poco como para no acusar a dos escenas que apenas
#: empiezan con el mismo artículo.
PALABRAS_DE_APERTURA = 3


def _apertura(narracion: str) -> str:
    limpio = "".join(
        c.lower() if (c.isalnum() or c.isspace() or c == "'") else " " for c in narracion
    )
    return " ".join(limpio.split()[:PALABRAS_DE_APERTURA])


def aperturas_repetidas(narraciones: list[str]) -> list[tuple[int, int]]:
    """Los pares de escenas que arrancan con las MISMAS palabras.

    Los cuatro tests de política que ya existen comparan un devocional contra otro:
    que dos piezas distintas no repitan carga, promesa, Escritura ni imagen. Este
    guardián mira hacia adentro de UNA pieza, que es donde apareció el problema de
    verdad el 7-ago-2026: las tres escenas de oración del primer devocional abrieron
    las tres con la misma frase, copiada de un ejemplo del prompt.

    Un devocional de 150 s tiene diez escenas y repite beats a propósito —esa es la
    forma del género—, así que la repetición no se puede evitar prohibiendo el beat:
    hay que mirar el texto. Es determinista y puro, como los guardianes del
    storyboard: no pregunta, mide.

    Devuelve los pares `(i, j)` con `i < j`. Vacío es que está bien.
    """
    aperturas = [_apertura(n) for n in narraciones]
    return [
        (i, j)
        for i in range(len(aperturas))
        for j in range(i + 1, len(aperturas))
        if aperturas[i] and aperturas[i] == aperturas[j]
    ]
