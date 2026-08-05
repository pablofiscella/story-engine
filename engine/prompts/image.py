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
"""

from __future__ import annotations

from engine.core.enums import Emotion
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

#: Lo que nunca queremos, pase lo que pase. Se suma al negativo del estilo.
_NEGATIVO_BASE = (
    "texto, letras, palabras, marca de agua, logo, firma, "
    "manos deformes, dedos de más, rostros deformes, "
    "personajes de más, animales de fondo con cara o actitud de personaje, "
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
            f"{p.expression_for(emo, _actitud(emo))}"
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
    if scene.visual_note:
        bloques.append(scene.visual_note)

    # --- Regla 2: continuidad de escenario -----------------------------------
    bloques.append(f"Lugar: {scene.location}, ambientado en {theme.name.lower()}")
    bloques.append(
        "MISMO escenario, MISMA hora del día y MISMO clima que el resto de la "
        "historia: día soleado y despejado. La emoción se muestra SOLO en la cara y "
        "la postura del personaje, nunca en el clima ni en la luz del cielo"
    )
    bloques.append(_ENCUADRE.get(scene.camera.shot.value, scene.camera.shot.value))
    bloques.append(
        f"paleta del tema: {theme.palette.primary}, {theme.palette.secondary}, "
        f"{theme.palette.accent}"
    )
    # Si la referencia de estilo es una hoja de personajes sobre fondo blanco, el
    # modelo copia ese vacío y los personajes quedan flotando. Hay que pedir el
    # escenario de forma explícita, siempre.
    bloques.append(
        "escena COMPLETA: con piso y fondo del lugar, los personajes apoyados en el "
        "suelo, nunca flotando sobre fondo liso"
    )
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


def _actitud(emotion: Emotion) -> str:
    """La emoción, traducida a CARA y CUERPO — nunca a clima.

    Antes esto devolvía luz y atmósfera ("cielo algo gris" para la frustración) y el
    cuento se nublaba en el medio sin que la historia lo dijera. La emoción de un
    personaje no cambia el tiempo.
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
