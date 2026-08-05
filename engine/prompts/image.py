"""El prompt de imagen se COMPONE, no se escribe.

Decisión deliberada: el modelo de texto no redacta los prompts de imagen. Los arma
el motor, ensamblando piezas fijas — el estilo, la descripción canónica de cada
personaje, el lugar, la emoción.

Por qué. Si el prompt de cada escena lo escribe una IA, cada escena describe al
protagonista con sus propias palabras: "un dinosaurio verde", "un dino simpático",
"el pequeño reptil". El generador de imágenes recibe tres descripciones distintas y
dibuja tres personajes distintos. Es el bug clásico de los cuentos ilustrados por
IA — el pijama que cambia de color entre la página 2 y la 3.

Componiéndolo, la descripción del personaje es byte por byte la misma en las diez
escenas. La consistencia deja de depender de la suerte.
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
    "primer_plano": "primer plano del rostro",
    "sobre_hombro": "plano por encima del hombro",
}

#: Lo que nunca queremos, pase lo que pase. Se suma al negativo del estilo.
_NEGATIVO_BASE = (
    "texto, letras, palabras, marca de agua, logo, firma, "
    "manos deformes, dedos de más, rostros deformes, "
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

    # Personajes: descripción canónica + cómo se les ve la cara en esta emoción.
    for cid in scene.character_ids:
        p = characters.get(cid)
        if p is None:
            continue
        bloques.append(
            f"{p.name}: {p.appearance.prompt_fragment()} {p.expression_for(scene.emotion)}"
        )

    bloques.append(f"Escena: {scene.purpose}")
    bloques.append(f"Lugar: {scene.location}, ambientado en {theme.name.lower()}")
    bloques.append(_ENCUADRE.get(scene.camera.shot.value, scene.camera.shot.value))
    bloques.append(_clima(scene.emotion))
    bloques.append(
        f"paleta del tema: {theme.palette.primary}, {theme.palette.secondary}, "
        f"{theme.palette.accent}"
    )
    # Aprendido de ilustrar cuentos con IA: si la referencia de estilo es una hoja de
    # personajes sobre fondo blanco, el modelo copia ese vacío y los personajes quedan
    # flotando. Hay que pedir el escenario de forma explícita, siempre.
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


def _clima(emotion: Emotion) -> str:
    """La emoción, traducida a luz y atmósfera.

    El generador de imágenes no entiende "frustración" como dirección de arte; sí
    entiende "luz apagada, cielo gris".
    """
    return {
        Emotion.CURIOSITY: "luz clara, atmósfera de descubrimiento",
        Emotion.JOY: "luz cálida y brillante, colores vivos",
        Emotion.SADNESS: "luz suave y apagada, tonos fríos",
        Emotion.FEAR: "sombras largas, luz baja, sin llegar a dar miedo",
        Emotion.SURPRISE: "luz que entra de golpe, contraste alto",
        Emotion.FRUSTRATION: "luz plana, cielo algo gris",
        Emotion.CALM: "luz difusa de atardecer, todo en calma",
        Emotion.PRIDE: "contraluz dorado, el personaje destacado",
    }[emotion]
