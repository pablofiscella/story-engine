"""El prompt de imagen se COMPONE, no se escribe.

Decisión deliberada: el modelo de texto no redacta los prompts de imagen. Los arma
el motor, ensamblando piezas fijas — el estilo, la descripción canónica de cada
personaje, el lugar y la emoción.

Por qué. Si el prompt de cada escena lo escribe una IA, cada escena describe al
protagonista con sus propias palabras: "un dinosaurio verde", "un dino simpático",
"el pequeño reptil". El generador recibe tres descripciones distintas y dibuja tres
personajes distintos.

REGLAS DURAS (las tres salieron de mirar un cuento ilustrado real que salió mal):

1. **Elenco cerrado.** Se nombra a TODOS los que aparecen y se prohíbe cualquier
   otro. Sin esto, la escena final decía "los dos juegan juntos" describiendo a uno
   solo, y el modelo completó el elenco con un dinosaurio del fondo de la referencia.
2. **Continuidad de escenario.** El lugar, la hora y el clima son los mismos en toda
   la historia. La emoción se muestra en la CARA y la POSTURA, nunca cambiando el
   clima: una escena triste no nubla el cielo si el cuento no dice que se nubló.
3. **La imagen ilustra lo que se narra.** Manda el texto de la escena, no la orden
   interna del motor. "Rexo quiere jugar y Dino se niega" se dibujó como Rexo
   sacándole la pelota, cuando la narración decía que solo la miraba.
4. **Nombrado es descrito.** Un personaje que se menciona sin describir lo inventa el
   modelo: el Rexo de la burbuja de pensamiento salió violeta en vez de azul.
5. **Cada uno con su cara.** La emoción se pide por PERSONAJE, no por escena. Con una
   sola emoción por escena, el que no comparte y el que se queda afuera salían con la
   misma cara de enojo y los mismos brazos cruzados.
6. **Ninguna instrucción puede contradecir a otra.** Cuando dos partes del prompt se
   pelean, el modelo elige una y no siempre la que importa: el plano corto del
   aprendizaje salía tan abierto como el resto porque otro bloque pedía "escena
   completa con los personajes apoyados en el suelo".
7. **Lo que decidió el motor no puede depender de que el texto lo nombre.** El objeto
   del conflicto lo elige el motor, pero el prompt se arma con la NARRACIÓN — y el
   escritor, apretado por el presupuesto de palabras, es el primero que deja de
   nombrarlo. "Dino se fue a un rincón y jugó solo" no dice "pelota", así que el
   modelo lo dibujó jugando con piedras. Va como bloque propio, siempre.
"""

from __future__ import annotations

from engine.core.enums import Emotion, ShotType
from engine.core.models.character import Character
from engine.core.models.scene import Scene
from engine.core.models.style import Style
from engine.core.models.theme import Theme

#: Cómo se traduce cada encuadre al vocabulario del generador de imágenes.
_ENCUADRE: dict[str, str] = {
    "plano_general": "plano general, se ve todo el escenario",
    "plano_medio": "plano medio",
    # No "primer plano del rostro" a secas: el beat del aprendizaje es un gesto
    # (ofrecer el juguete) y un encuadre solo de cara lo dejaría fuera de cuadro.
    "primer_plano": "plano corto: las caras y las manos llenan el cuadro",
    "sobre_hombro": "plano por encima del hombro",
}

#: Cómo se pide el fondo, según cuán cerca esté la cámara.
#:
#: Existe porque si la referencia de estilo es una hoja de personajes sobre fondo
#: blanco, el modelo copia ese vacío y los personajes quedan flotando. Pero pedir
#: "escena completa con los personajes apoyados en el suelo" en un plano corto es
#: contradictorio: el aprendizaje salía tan abierto como el resto porque el prompt
#: pedía las dos cosas a la vez y el modelo elegía una.
_FONDO: dict[ShotType, str] = {
    ShotType.WIDE: (
        "escena COMPLETA: se ve todo el lugar, con piso y horizonte, los personajes "
        "apoyados en el suelo, nunca flotando sobre fondo liso"
    ),
    ShotType.MEDIUM: (
        "escena COMPLETA: con piso y fondo del lugar, los personajes apoyados en el "
        "suelo, nunca flotando sobre fondo liso"
    ),
    ShotType.OVER_SHOULDER: (
        "escena COMPLETA: con piso y fondo del lugar, los personajes apoyados en el "
        "suelo, nunca flotando sobre fondo liso"
    ),
    ShotType.CLOSE_UP: (
        "CÁMARA CERCA: los personajes ocupan casi todo el alto del cuadro y se los ve "
        "de la cintura para arriba. Detrás se sigue viendo el lugar, aunque quede "
        "desenfocado — nunca fondo liso ni blanco"
    ),
}

#: Lo que nunca queremos, pase lo que pase. Se suma al negativo del estilo.
_NEGATIVO_BASE = (
    "texto, letras, palabras, marca de agua, logo, firma, "
    "manos deformes, dedos de más, rostros deformes, "
    "personajes de más, animales de fondo con cara o actitud de personaje, "
    "objetos o juguetes que la historia no nombró, "
    "contenido perturbador, violencia, personajes de marcas registradas"
)


def compose(
    scene: Scene,
    *,
    style: Style,
    theme: Theme,
    characters: dict[str, Character],
) -> str:
    """El prompt positivo de una escena.

    Determinista: mismos datos, mismo texto. Esa estabilidad ES la consistencia
    visual entre escenas.
    """
    bloques: list[str] = [style.prompt_fragment()]

    # --- Regla 1: elenco cerrado ---------------------------------------------
    presentes = [characters[c] for c in scene.character_ids if c in characters]
    nombres = " y ".join(p.name for p in presentes)
    bloques.append(
        f"EN LA ESCENA HAY EXACTAMENTE {len(presentes)} "
        f"personaje{'s' if len(presentes) != 1 else ''}: {nombres}. "
        "No agregues ningún otro personaje ni criatura con protagonismo"
    )
    # Cada uno con SU emoción: en el problema de "compartir" el protagonista está
    # enojado y el compañero solo quiere jugar. Cuando la emoción era una sola por
    # escena, salían los dos con la misma cara de enojo y los mismos brazos cruzados.
    for p in presentes:
        emo = scene.emotion_for(p.id)
        bloques.append(
            f"{p.name}: {p.appearance.prompt_fragment()} "
            f"{p.expression_for(emo, _traductor(style)(emo))}"
        )
    # El prompt NEGATIVO del estilo devocional ya decía "faces, close-up hands,
    # fingers" y no alcanzó: la escena del aprendizaje salió igual como un primer plano
    # de una cara. **El positivo le gana al negativo**, así que la regla que sostiene al
    # nicho entero tiene que estar dicha en positivo y acá arriba, junto al personaje.
    if style.emotion_in_light and presentes:
        bloques.append(
            "LA FIGURA SE VE SIEMPRE DE ESPALDAS, LEJOS Y CHICA DENTRO DEL CUADRO: no "
            "se le ve la cara, ni los ojos, ni la boca, ni las manos, y nunca hace un "
            "gesto de celebración ni salta. Es una silueta, no un retrato"
        )

    # Los imaginados (burbuja de pensamiento, recuerdo) NO cuentan como presentes,
    # pero SÍ hay que describirlos: nombrarlos sin describirlos es lo que hizo que el
    # Rexo de la burbuja saliera violeta en vez de azul.
    imaginados = [characters[c] for c in scene.imagined_character_ids if c in characters]
    for p in imaginados:
        bloques.append(
            f"{p.name} (solo dentro de la burbuja de pensamiento, no en la escena real): "
            f"{p.appearance.prompt_fragment()} "
            f"{p.expression_for(emo := scene.emotion_for(p.id), _actitud(emo))}"
        )

    # --- Regla 3: manda lo que se narra --------------------------------------
    bloques.append(f"Qué está pasando: {scene.narration or scene.purpose}")
    # Y CÓMO se ve, que es otra cosa: la narración está escrita para oírse. "Se fue a
    # un rincón y jugó solo" no dice dónde queda el rincón ni qué hace el otro
    # mientras tanto, así que cada imagen lo resolvía distinto y la secuencia saltaba.
    # Esto lo escribe el storyboard habiendo leído el cuento entero — es lo único del
    # prompt que sabe qué pasó en la escena anterior.
    if scene.shot_description:
        bloques.append(f"Puesta en escena: {scene.shot_description}")
    if scene.visual_note:
        bloques.append(scene.visual_note)

    # --- Regla 7: lo que decidió el motor no depende de que el texto lo nombre ---
    if scene.prop:
        bloques.append(
            f"EL OBJETO DE LA HISTORIA ES {scene.prop.upper()} y tiene que verse en "
            "esta escena. No lo reemplaces por otra cosa ni agregues otros juguetes"
        )

    # --- Regla 2: continuidad de escenario -----------------------------------
    bloques.append(f"Lugar: {scene.location}, ambientado en {theme.name.lower()}")
    bloques.append(style.continuity or _CONTINUIDAD_DEL_CUENTO)
    bloques.append(_ENCUADRE.get(scene.camera.shot.value, scene.camera.shot.value))
    bloques.append(
        f"paleta del tema: {theme.palette.primary}, {theme.palette.secondary}, "
        f"{theme.palette.accent}"
    )
    bloques.append(_FONDO[scene.camera.shot])
    return ". ".join(b.rstrip(". ") for b in bloques if b) + "."


def negative(style: Style) -> str:
    """El prompt negativo: lo que no queremos ver.

    Vale tanto como el positivo. El del estilo se suma al base, porque cada estilo
    tiene su propio enemigo: en palitos molesta el color, en 3D molesta el realismo
    fotográfico.
    """
    partes = [_NEGATIVO_BASE]
    if style.negative_prompt:
        partes.append(style.negative_prompt)
    return ", ".join(partes)


#: La continuidad de un cuento: el escenario y el clima no se mueven, y la emoción vive
#: en la cara. Se escribió porque el cuento se nublaba solo en la mitad.
_CONTINUIDAD_DEL_CUENTO = (
    "MISMO escenario, MISMA hora del día y MISMO clima que el resto de la historia: "
    "día soleado y despejado. La emoción se muestra SOLO en la cara y la postura del "
    "personaje, nunca en el clima ni en la luz del cielo"
)


def _traductor(style: Style):
    """Cómo se dibuja una emoción en ESTE estilo.

    Es un parámetro del estilo y no un `if` acá adentro porque el compositor no tiene
    por qué saber cuántos géneros existe — la misma razón por la que `StoryWriter.write`
    recibe el prompt de sistema en vez de elegirlo.
    """
    return _atmosfera if style.emotion_in_light else _actitud


def _atmosfera(emotion: Emotion) -> str:
    """La emoción, traducida a LUZ y ENCUADRE — nunca a cara.

    Es la regla de `_actitud` DADA VUELTA, y está bien que lo sea: son dos géneros
    distintos. En un cuento la emoción en el clima es un error (el cuento se nublaba
    solo); en un devocional la cara es el error, porque la figura es una silueta a
    contraluz y no tiene rasgos que mover. Pedirle una expresión a algo sin rostro no
    da una silueta expresiva: da una cara, que es lo que salió el 7-ago-2026.

    Acá el paisaje ES el personaje. Lo único que puede cambiar entre una escena y la
    siguiente es cuánta luz hay y qué tan chica se ve la figura.
    """
    return {
        Emotion.CURIOSITY: (
            "una franja de luz entrando desde un costado del cuadro, el resto en penumbra"
        ),
        Emotion.JOY: (
            "el paisaje entero encendido por un contraluz dorado, aire limpio y "
            "horizonte abierto, la figura quieta y de espaldas"
        ),
        Emotion.SADNESS: (
            "luz baja y fría, casi sin color, la figura muy chica contra un espacio "
            "vacío enorme"
        ),
        Emotion.FEAR: (
            "contraluz duro y cielo ocupando casi todo el cuadro, la figura diminuta y "
            "corrida del centro"
        ),
        Emotion.SURPRISE: (
            "un haz de luz abriéndose entre las nubes sobre el suelo, todo lo demás en "
            "sombra"
        ),
        Emotion.FRUSTRATION: "luz plana y gris, sin brillos, el horizonte cortado",
        Emotion.CALM: (
            "luz suave y pareja, horizonte amplio y despejado, la figura pequeña y "
            "quieta dentro del cuadro"
        ),
        Emotion.PRIDE: "luz alta y clara sobre un terreno abierto, sin nada que estorbe",
    }[emotion]


def _actitud(emotion: Emotion) -> str:
    """La emoción, traducida a CARA y CUERPO — nunca a clima.

    Antes esto devolvía luz y atmósfera ("cielo algo gris" para la frustración) y el
    cuento se nublaba en el medio sin que la historia lo dijera. La emoción de un
    personaje no cambia el tiempo.

    **Ojo:** para un estilo sin rostro esta función es exactamente el problema. Ver
    `_atmosfera` y `Style.emotion_in_light`.
    """
    return {
        Emotion.CURIOSITY: (
            "expresión de curiosidad, cejas levantadas, cuerpo inclinado hacia adelante"
        ),
        Emotion.JOY: "sonrisa grande, ojos brillantes, postura saltarina",
        Emotion.SADNESS: "cejas caídas, mirada baja, hombros hundidos",
        Emotion.FEAR: "ojos muy abiertos, cuerpo encogido, un paso hacia atrás",
        Emotion.SURPRISE: "boca abierta, ojos redondos, cuerpo erguido de golpe",
        Emotion.FRUSTRATION: "ceño fruncido, brazos cruzados, boca torcida",
        Emotion.CALM: "párpados relajados, sonrisa suave, postura tranquila",
        Emotion.PRIDE: "pecho inflado, mentón alto, sonrisa amplia",
    }[emotion]
