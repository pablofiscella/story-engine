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
    #:
    #: NO EMPEZARLA CON "¿Y vos,". Las diez arrancaban así y la voz la leía mal de forma
    #: recurrente: salió "la voz" en un cuento y "¿Para quién" en otro. Aislada se pronuncia
    #: bien —se probó—, así que no es el texto sino esa arranque en el contexto del cierre.
    #: El "vos" va DESPUÉS del verbo: "¿Qué compartís vos…?".
    question: str
    #: Instrucción para el escritor en cada beat.
    purposes: dict[NarrativeBeat, str]
    #: Qué siente el PROTAGONISTA en cada beat. Es también el tono de la escena.
    emotions: dict[NarrativeBeat, Emotion]
    #: Qué siente el COMPAÑERO en cada beat, que casi nunca es lo mismo.
    #:
    #: Salió de mirar una ilustración donde Dino y Rexo tenían la misma cara de enojo
    #: y los mismos brazos cruzados, cuando el enojado era Dino y Rexo solo quería
    #: jugar. La emoción era una sola por escena y se le aplicaba igual a todos.
    #:
    #: El compañero es el otro lado del conflicto, así que su curva es distinta por
    #: valor: en `compartir` es el que se queda afuera, en `amistad` es el que ya está
    #: jugando contento, en `empatía` es el que está mal desde el principio.
    companion_emotions: dict[NarrativeBeat, Emotion]
    #: Si el conflicto necesita un OBJETO concreto (compartir necesita algo que dar),
    #: qué tipo de objeto es. El motor elige uno del tema y lo mete en los propósitos,
    #: para que el texto Y el prompt de imagen hablen de la misma cosa.
    needs_prop: bool = False
    #: Dirección de arte por beat, cuando el beat pide un recurso visual concreto.
    #: Idea de Pablo mirando el cuento ilustrado: en el ERROR de "compartir" no
    #: alcanza con que esté triste — se entiende mucho mejor si se lo ve imaginando,
    #: en una burbuja de pensamiento, lo que se está perdiendo.
    visual_notes: dict[NarrativeBeat, str] = field(default_factory=dict)
    #: Variantes para cuando un beat se repite en historias largas. Sin esto, dos
    #: escenas del mismo beat salen casi idénticas — pasó de verdad ("el secreto la
    #: aplastaba" / "el secreto la envolvía" en dos escenas seguidas).
    escalations: dict[NarrativeBeat, tuple[str, ...]] = field(default_factory=dict)
    #: EL OBJETO que pide este valor, cuando el del tema no sirve.
    #:
    #: El objeto sale de `theme.props[0]` — el primero del tema, sin mirar el conflicto. Para
    #: "compartir" una pelota es perfecta; para "pedir ayuda", cuyo conflicto es NO PODER SOLO,
    #: es absurda: un dinosaurio mueve una pelota sin ayuda de nadie. El guión lo notó y lo
    #: parcheó inventando que la empujaba con un palito hasta romperla, y después la movían
    #: entre los dos aunque estuviera rota. Pablo: *"el relato está mal y hace que la imagen
    #: muestre algo errado"*.
    #:
    #: Cuando el conflicto necesita un objeto con cierta propiedad —pesado, frágil, único— se
    #: declara acá y gana sobre el del tema.
    prop_override: str = ""

    #: CÓMO QUEDA EL OBJETO a partir de cierto beat, y para siempre.
    #:
    #: El ilustrador dibuja cada escena por separado y sin memoria: rompía la pelota en el
    #: problema y la volvía a dibujar entera dos escenas después. Pablo, 13-ago-2026: *"habia
    #: un tema de la pelota que se rompia y despues estaba sana o la buscaba y estaba rota al
    #: lado… un tema de recordar lo que pasaba en tomas anteriores"*.
    #:
    #: Lo que se declara acá viaja a TODAS las escenas siguientes. Va en inglés porque termina
    #: en el prompt de imagen.
    prop_state: dict[NarrativeBeat, str] = field(default_factory=dict)


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


def _emociones_companero() -> dict[NarrativeBeat, Emotion]:
    """Curva del que está del otro lado: pide, lo dejan afuera, y termina incluido.

    La clave está en el PROBLEMA: `CURIOSITY` es "cuerpo inclinado hacia adelante,
    cejas levantadas" — o sea, querer. Es lo que hace que el compañero mire el objeto
    en vez de compartir el enojo del protagonista.
    """
    return {
        NarrativeBeat.HOOK: Emotion.CURIOSITY,
        NarrativeBeat.PROBLEM: Emotion.CURIOSITY,
        NarrativeBeat.ATTEMPT: Emotion.SADNESS,
        NarrativeBeat.FAILURE: Emotion.SADNESS,
        NarrativeBeat.LESSON: Emotion.SURPRISE,
        NarrativeBeat.ENDING: Emotion.JOY,
    }


def _companero_que_acompana() -> dict[NarrativeBeat, Emotion]:
    """Cuando el compañero no sufre el conflicto sino que sostiene al protagonista.

    Vale para paciencia, coraje y perseverancia: el otro está tranquilo mientras el
    protagonista se pelea con algo que es suyo.
    """
    return {
        **_emociones_companero(),
        NarrativeBeat.PROBLEM: Emotion.CALM,
        NarrativeBeat.ATTEMPT: Emotion.CALM,
        NarrativeBeat.FAILURE: Emotion.CALM,
    }


PROFILES: dict[EducationalValue, ValueProfile] = {
    EducationalValue.SHARING: ValueProfile(
        value=EducationalValue.SHARING,
        conflict="{protagonista} tiene algo que quiere solo para sí",
        moral="Compartir nos hace más felices y fortalece la amistad.",
        question="¿Qué compartís vos con tus amigos?",
        needs_prop=True,
        visual_notes={
            NarrativeBeat.PROBLEM: (
                "{companero} mira {objeto} y estira una mano hacia él; {protagonista} "
                "lo aprieta contra el pecho y lo aleja"
            ),
            NarrativeBeat.FAILURE: (
                "burbuja de pensamiento sobre la cabeza de {protagonista}, donde se "
                "imagina jugando con {companero} y {objeto}, los dos contentos"
            ),
        },
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
            # Tiene que nombrar a {companero} y decir DÓNDE se pone: si el intento es
            # solo "disfrutar el objeto solo", sale la misma imagen que el gancho.
            NarrativeBeat.ATTEMPT: (
                "{protagonista} se lleva {objeto} a un rincón y juega de espaldas, "
                "mientras {companero} lo mira desde lejos"
            ),
            NarrativeBeat.FAILURE: (
                "Jugar solo con {objeto} resulta aburrido: {protagonista} se queda sin nadie"
            ),
            NarrativeBeat.LESSON: (
                "{protagonista} entiende que con {companero} sería más divertido "
                "y le ofrece {objeto}"
            ),
            NarrativeBeat.ENDING: (
                "{protagonista} y {companero} juegan juntos con {objeto}, mucho más felices"
            ),
        },
        emotions=_emociones_base(),
        companion_emotions=_emociones_companero(),
    ),
    EducationalValue.FRIENDSHIP: ValueProfile(
        value=EducationalValue.FRIENDSHIP,
        conflict="{protagonista} está solo y no sabe cómo acercarse a los demás",
        moral="Un amigo se gana acercándose, no esperando.",
        question="¿Cómo conociste vos a tu mejor amigo?",
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
        # Acá el compañero es el que YA está jugando contento: no sufre nada, y
        # esa es justamente la distancia que el protagonista tiene que cruzar.
        companion_emotions={
            **_emociones_companero(),
            NarrativeBeat.HOOK: Emotion.JOY,
            NarrativeBeat.PROBLEM: Emotion.JOY,
            NarrativeBeat.ATTEMPT: Emotion.JOY,
            NarrativeBeat.FAILURE: Emotion.CALM,
        },
    ),
    EducationalValue.RESPECT: ValueProfile(
        value=EducationalValue.RESPECT,
        conflict="{protagonista} quiere imponer su forma de hacer las cosas",
        moral="Cada uno tiene su manera, y todas merecen respeto.",
        question="¿En qué sos diferente a tus amigos?",
        purposes={
            NarrativeBeat.HOOK: "Presentar a {protagonista} muy seguro de cómo se hacen las cosas",
            NarrativeBeat.PROBLEM: "{companero} lo hace distinto y {protagonista} se burla",
            NarrativeBeat.ATTEMPT: "{protagonista} insiste en que su forma es la única buena",
            NarrativeBeat.FAILURE: "{companero} se aleja triste y {protagonista} se queda incómodo",
            NarrativeBeat.LESSON: (
                "{protagonista} prueba la forma de {companero} y descubre que "
                "también funciona"
            ),
            NarrativeBeat.ENDING: (
                "{protagonista} y {companero} hacen las cosas a su manera, juntos y contentos"
            ),
        },
        emotions=_emociones_base(),
        # El que sufre que le impongan: se frustra primero y se apaga después.
        companion_emotions={
            **_emociones_companero(),
            NarrativeBeat.PROBLEM: Emotion.FRUSTRATION,
        },
    ),
    EducationalValue.HONESTY: ValueProfile(
        value=EducationalValue.HONESTY,
        conflict="{protagonista} rompe o pierde algo y no quiere admitirlo",
        moral="Decir la verdad cuesta un ratito; la mentira pesa mucho más.",
        question="¿Alguna vez dijiste la verdad aunque diera miedo?",
        needs_prop=True,
        visual_notes={
            NarrativeBeat.FAILURE: (
                "burbuja de pensamiento sobre la cabeza de {protagonista} con {objeto} "
                "roto, que le vuelve a la cabeza y no la deja disfrutar de nada"
            ),
        },
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
        # El afectado por la mentira: no sabe nada al principio, se sorprende
        # cuando aparece la verdad.
        companion_emotions={
            **_emociones_companero(),
            NarrativeBeat.HOOK: Emotion.CALM,
            NarrativeBeat.PROBLEM: Emotion.SURPRISE,
        },
    ),
    EducationalValue.EMPATHY: ValueProfile(
        value=EducationalValue.EMPATHY,
        conflict="{protagonista} no se da cuenta de que {companero} está mal",
        moral="Preguntar '¿estás bien?' puede cambiarle el día a alguien.",
        question="¿Cómo te das cuenta cuando un amigo está triste?",
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
        # Acá el compañero está mal DESDE EL PRINCIPIO, y que se note en su cara
        # antes de que el protagonista lo registre es medio cuento contado.
        companion_emotions={
            **_emociones_companero(),
            NarrativeBeat.HOOK: Emotion.SADNESS,
            NarrativeBeat.PROBLEM: Emotion.SADNESS,
        },
    ),
    EducationalValue.PATIENCE: ValueProfile(
        value=EducationalValue.PATIENCE,
        conflict="{protagonista} quiere algo YA y no tolera esperar",
        moral="Las cosas más lindas necesitan su tiempo.",
        question="¿Qué estás esperando vos con muchas ganas?",
        purposes={
            NarrativeBeat.HOOK: "Presentar a {protagonista} esperando algo que le entusiasma mucho",
            NarrativeBeat.PROBLEM: "Falta demasiado y {protagonista} se desespera",
            NarrativeBeat.ATTEMPT: "{protagonista} intenta apurarlo de cualquier manera",
            NarrativeBeat.FAILURE: "Apurarlo lo arruina y hay que empezar de nuevo",
            NarrativeBeat.LESSON: "{companero} lo acompaña a esperar y el rato se hace corto",
            NarrativeBeat.ENDING: (
                "Llega el momento y {protagonista} lo disfruta con {companero}: "
                "valió cada segundo de espera"
            ),
        },
        emotions={**_emociones_base(), NarrativeBeat.PROBLEM: Emotion.FRUSTRATION},
        companion_emotions=_companero_que_acompana(),
    ),
    EducationalValue.COURAGE: ValueProfile(
        value=EducationalValue.COURAGE,
        conflict="{protagonista} tiene miedo de algo que quiere hacer",
        moral="Ser valiente no es no tener miedo: es animarse igual.",
        question="¿A qué te animaste vos aunque tuvieras miedo?",
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
            NarrativeBeat.ENDING: (
                "{protagonista} lo logra, con {companero} al lado, y se siente enorme"
            ),
        },
        emotions={
            **_emociones_base(),
            NarrativeBeat.PROBLEM: Emotion.FEAR,
            NarrativeBeat.ATTEMPT: Emotion.FEAR,
            NarrativeBeat.ENDING: Emotion.PRIDE,
        },
        # El que acompaña sin miedo: su calma es lo que contrasta con el susto.
        companion_emotions=_companero_que_acompana(),
    ),
    EducationalValue.PERSEVERANCE: ValueProfile(
        value=EducationalValue.PERSEVERANCE,
        conflict="a {protagonista} no le sale algo y quiere abandonar",
        moral="No salió todavía no es lo mismo que no puedo.",
        question="¿Qué aprendiste después de intentarlo muchas veces?",
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
            NarrativeBeat.ENDING: (
                "{protagonista} lo consigue y lo festeja con {companero}: "
                "la alegría es enorme porque costó"
            ),
        },
        emotions={
            **_emociones_base(),
            NarrativeBeat.FAILURE: Emotion.FRUSTRATION,
            NarrativeBeat.ENDING: Emotion.PRIDE,
        },
        # El que alienta desde afuera y festeja al final.
        companion_emotions=_companero_que_acompana(),
    ),
    # ── Los dos valores que abren la serie más allá del catálogo original ──────
    # Se agregaron el 12-ago-2026 porque los ocho primeros ya estaban publicados o agendados.
    # Cada uno tiene su conflicto propio, que es la razón de que este archivo exista: sin eso,
    # "pedir ayuda" y "no darse por vencido" saldrían el mismo cuento.

    EducationalValue.ASKING_FOR_HELP: ValueProfile(
        value=EducationalValue.ASKING_FOR_HELP,
        # El conflicto NO es que no pueda: es que no quiere que lo vean necesitando.
        # Por eso el fracaso no puede ser "se cansó", tiene que ser "se quedó solo con el
        # problema mientras el otro estaba ahí al lado".
        conflict="{protagonista} no puede solo con {objeto} pero le da vergüenza pedir ayuda",
        # Pesado a propósito: si se puede mover solo, no hay a quién pedirle ayuda.
        prop_override="una roca grande",
        # NO EMPIEZA CON "Pedir". La voz deforma la primera palabra del tramo: se oyó
        # "medir ayuda" primero y "seguir ayuda" después, con dos generaciones distintas.
        # La palabra que sostiene el sentido no puede ir en el arranque; adelante va algo
        # sacrificable.
        moral=("Cuando algo te cuesta, pedir ayuda no es rendirse: "
               "es animarse a decir que solo no puedo."),
        question="¿A quién le pedís ayuda vos cuando algo te cuesta?",
        needs_prop=True,
        visual_notes={
            NarrativeBeat.PROBLEM: (
                "{protagonista} forcejea con {objeto} y mira de reojo a {companero}, "
                "que está cerca; enseguida vuelve a intentarlo solo"
            ),
            # EL BEAT DEL INTENTO NO TENÍA NOTA, y por eso salió mal: el escritor inventó
            # un palito y escribió "empuja la roca y... ¡se rompe!" —sin sujeto—, así que
            # el ilustrador partió LA ROCA. Lo que se rompe es la herramienta, nunca el
            # obstáculo: si el obstáculo cede, el cuento ya no necesita a nadie más.
            # UNA NOTA POR REPETICIÓN. El beat aparece dos veces y con una sola nota las
            # dos escenas pedían la misma imagen: "Dino empuja la roca" y "Dino empuja la
            # roca con todas sus fuerzas", con el mismo dibujo.
            NarrativeBeat.ATTEMPT: (
                "{protagonista} de ESPALDAS contra {objeto}, empujando con las patas "
                "traseras clavadas en la tierra, que se levanta bajo sus pies; {objeto} no "
                "se mueve ni un poco",
                "{protagonista} hace palanca con un palito fino contra {objeto}; EL PALITO "
                "se parte en dos pedazos y {objeto} sigue ENTERA, sin moverse y sin una sola "
                "grieta",
            ),
            NarrativeBeat.FAILURE: (
                "{protagonista} DE PIE con los brazos caídos y la cabeza gacha frente a "
                "{objeto}, sin tocarla; {companero} pasa a lo lejos, de espaldas",
                "{protagonista} SENTADO en el suelo dándole la espalda a {objeto}, chiquito "
                "en el cuadro, con la cara apoyada en las manos; {companero} lejos",
            ),
            # EL FINAL ES DE A DOS, y hay que decirlo: sin esto el ilustrador dibujó a
            # {protagonista} jugando SOLO justo después de haber pedido ayuda, que es lo
            # contrario de lo que el cuento acaba de enseñar.
            NarrativeBeat.LESSON: (
                "{protagonista} se acerca a {companero} y le habla mirándolo a los ojos; "
                "los dos están cerca, en el mismo plano"
            ),
            NarrativeBeat.ENDING: (
                "LOS DOS JUNTOS empujando {objeto} al mismo tiempo, uno de cada lado, "
                "moviéndolo de verdad; ninguno está solo en el cuadro"
            ),
        },
        escalations={
            NarrativeBeat.ATTEMPT: (
                "{protagonista} empuja {objeto} con todas sus fuerzas y no se mueve",
                "{protagonista} prueba con un palito, y el palito se rompe",
            ),
            NarrativeBeat.FAILURE: (
                "{protagonista} se queda sin ideas y {objeto} sigue igual",
                "{protagonista} se sienta al lado de {objeto}, cansado y solo",
            ),
        },
        purposes={
            NarrativeBeat.HOOK: "{protagonista} descubre {objeto} y quiere moverlo él solo",
            NarrativeBeat.PROBLEM: (
                "{objeto} pesa demasiado; {companero} está cerca, pero {protagonista} "
                "no quiere que lo vea sin poder"
            ),
            NarrativeBeat.ATTEMPT: (
                "{protagonista} lo intenta de todas las formas mientras {companero} lo "
                "mira desde lejos sin acercarse"
            ),
            NarrativeBeat.FAILURE: (
                "{protagonista} se queda sin fuerzas y {objeto} no se movió ni un poquito"
            ),
            NarrativeBeat.LESSON: (
                "{protagonista} respira hondo y le dice a {companero}: ¿me ayudás?"
            ),
            # EL {companero} VA NOMBRADO CON EL MARCADOR, y no como "entre los dos": el
            # planificador arma el elenco de la escena preguntando si el purpose menciona
            # `{companero}`. Escrito en prosa, el compañero no entra al cuadro — y el final de
            # este cuento salió con el protagonista SOLO justo después de haber pedido ayuda,
            # que es lo contrario de lo que enseña. Pablo lo vio enseguida.
            NarrativeBeat.ENDING: (
                "{protagonista} y {companero} empujan {objeto} JUNTOS, uno de cada lado, y "
                "esta vez sí se mueve"
            ),
        },
        emotions=_emociones_base(),
        companion_emotions=_emociones_companero(),
    ),

    EducationalValue.APOLOGIZING: ValueProfile(
        value=EducationalValue.APOLOGIZING,
        # Acá el protagonista es el que rompe algo. El conflicto es la tentación de que no se
        # note — por eso el intento es esconder, no arreglar.
        #
        # EL OBJETO SE ROMPE Y SIGUE ROTO. Cada beat posterior lo nombra como "los pedazos",
        # nunca como el objeto entero: el ilustrador dibuja cada escena por separado y sin esto
        # vuelve a poner la pelota sana en las seis escenas siguientes. Pablo lo cazó mirando:
        # *"rompe la pelota pero en todas las escenas siguientes la pelota esta sana"*.
        conflict="{protagonista} rompió {objeto} de {companero} sin querer y nadie lo vio",
        prop_state={
            NarrativeBeat.PROBLEM: "{objeto} is SHATTERED into several separate loose fragments "
                                   "lying apart from each other; there is NO whole round "
                                   "{objeto} anywhere in the picture, and it stays like that "
                                   "for the rest of the story",
            NarrativeBeat.ATTEMPT: "the loose broken fragments of {objeto} are being pushed "
                                   "behind a rock; they are separate pieces, NOT a whole ball, "
                                   "and most of them are already out of sight",
            NarrativeBeat.LESSON: "{protagonista} is now HOLDING the broken pieces of {objeto} "
                                  "in his hands: they are no longer hidden",
            NarrativeBeat.ENDING: "the broken pieces of {objeto} lie together on the ground to "
                                  "one side: nobody is playing with it",
        },
        moral="Decir perdón arregla lo que ningún pegamento puede.",
        question="¿Cómo te sentís vos después de decir perdón?",
        needs_prop=True,
        visual_notes={
            NarrativeBeat.PROBLEM: (
                "{objeto} PARTIDO EN PEDAZOS en el suelo y {protagonista} con los ojos muy "
                "abiertos, mirando para los costados"
            ),
            NarrativeBeat.ATTEMPT: (
                "los PEDAZOS de {objeto} asomando detrás de una piedra; {objeto} NO está "
                "entero en ninguna parte del cuadro"
            ),
            NarrativeBeat.FAILURE: (
                "{companero} busca por el suelo con cara triste, y {protagonista} mira "
                "desde atrás hacia la piedra donde escondió los PEDAZOS"
            ),
            NarrativeBeat.LESSON: (
                "{protagonista} sostiene los PEDAZOS de {objeto} con las dos manos y se los "
                "muestra a {companero}, cabizbajo"
            ),
            NarrativeBeat.ENDING: (
                "los PEDAZOS de {objeto} quedan a un costado del suelo mientras los dos se "
                "abrazan; NADIE juega con {objeto}, que sigue roto"
            ),
        },
        escalations={
            NarrativeBeat.ATTEMPT: (
                "{protagonista} empuja los pedazos de {objeto} detrás de una piedra",
                "{protagonista} tapa los pedazos con una hoja grande",
            ),
            NarrativeBeat.FAILURE: (
                "{companero} busca {objeto} por todas partes y no lo encuentra",
                "{protagonista} tiene un nudo en la panza que no se le va",
            ),
        },
        purposes={
            NarrativeBeat.HOOK: (
                "{protagonista} juega con {objeto}, que está entero y es de {companero}"
            ),
            NarrativeBeat.PROBLEM: (
                "{objeto} se rompe en pedazos sin querer, y no hay nadie mirando"
            ),
            # SIN nombrar a {companero}: el motor arma el elenco buscando ese marcador, y
            # nombrarlo —aunque sea para decir que no se entere— lo mete en el cuadro. Salió
            # {protagonista} escondiendo la pelota CON el otro mirando, que destruye el
            # conflicto entero.
            NarrativeBeat.ATTEMPT: (
                "{protagonista} esconde los pedazos detrás de una piedra, solo, mirando "
                "para todos lados por si alguien viene"
            ),
            NarrativeBeat.FAILURE: (
                "{companero} busca su {objeto} y se pone triste; a {protagonista} le queda "
                "un nudo en la panza"
            ),
            NarrativeBeat.LESSON: (
                "{protagonista} junta los pedazos, se acerca a {companero} y le dice perdón"
            ),
            NarrativeBeat.ENDING: (
                "{companero} lo abraza. {objeto} sigue roto y lo dejan a un costado: "
                "se van a jugar juntos a otra cosa"
            ),
        },
        emotions=_emociones_base(),
        companion_emotions=_emociones_companero(),
    ),

}


def profile_for(value: EducationalValue) -> ValueProfile:
    """El molde narrativo de `value`.

    Lanza `KeyError` si falta: preferimos romper fuerte a generar una historia sin
    conflicto real. Un valor sin perfil es un bug de configuración, no un caso a
    manejar en silencio.
    """
    return PROFILES[value]
