"""Los prompts de narración.

Viven separados del escritor a propósito. Un prompt es contenido que se ajusta
seguido (una palabra de más, un ejemplo nuevo, un tono distinto por edad); el
escritor es lógica que casi no cambia. Mezclarlos obliga a tocar código para
corregir una coma, y hace imposible ver de un vistazo qué se le está pidiendo
realmente al modelo.

Regla que atraviesa todo esto: al modelo se le pide **una escena por vez**, con el
objetivo ya decidido y el presupuesto de palabras explícito. Nunca "escribí un
cuento".
"""

from __future__ import annotations

from engine.core.enums import AgeRange, Language
from engine.core.models.character import Character
from engine.core.models.plan import ScenePlan

#: Cómo hablarle a cada edad. Es lo que evita que un cuento para un chico de 3
#: use subordinadas de dos renglones.
_TONO_POR_EDAD: dict[AgeRange, str] = {
    AgeRange.TODDLER: (
        "Frases MUY cortas (5 a 8 palabras). Palabras de todos los días. "
        "Repetición y sonidos (¡pum!, ¡uy!). Nada de metáforas."
    ),
    AgeRange.PRESCHOOL: (
        "Frases cortas y claras. Vocabulario simple y concreto. "
        "Puede haber una comparación fácil de imaginar."
    ),
    AgeRange.EARLY: (
        "Frases de largo normal. Se puede nombrar lo que siente el personaje. "
        "Alguna palabra nueva, siempre que el contexto la explique."
    ),
    AgeRange.KID: (
        "Frases con algo más de vuelo. Se admite ironía suave y juegos de palabras. "
        "El personaje puede razonar en voz alta."
    ),
}

_IDIOMA: dict[Language, str] = {
    Language.ES_AR: (
        "Español rioplatense de Argentina. Usá VOSEO siempre "
        "(mirá, vení, tenés, dale) y nunca tuteo (mira, ven, tienes)."
    ),
    Language.ES: "Español neutro latinoamericano.",
    Language.EN: "English, natural and warm.",
    Language.PT_BR: "Português do Brasil, natural e caloroso.",
}


def system_prompt(*, language: Language, age_range: AgeRange, value_moral: str) -> str:
    """Quién es el narrador y qué reglas no puede romper.

    Va una sola vez por historia: no cambia entre escenas, así que repetirlo en cada
    pedido sería gastar tokens en lo mismo.
    """
    edad_desde, edad_hasta = age_range.bounds
    return (
        "Sos un cuentacuentos que narra historias para chicos de "
        f"{edad_desde} a {edad_hasta} años.\n\n"
        f"IDIOMA: {_IDIOMA[language]}\n"
        f"TONO: {_TONO_POR_EDAD[age_range]}\n\n"
        f"La historia enseña, sin nunca decirlo de forma explícita: {value_moral}\n\n"
        "REGLAS:\n"
        "- Escribís SOLO la narración de la escena que te piden. Nada de títulos, "
        "acotaciones, números de escena ni comillas alrededor de todo.\n"
        "- No moralices ni expliques la enseñanza: que se entienda por lo que pasa.\n"
        "- Nunca inventes personajes: usá únicamente los que te nombran.\n"
        "- Respetá el límite de palabras. Es un límite de tiempo real: si te pasás, "
        "el audio no entra en la escena.\n"
        "- NO escribas diálogo entrecomillado. Contá lo que el personaje dice, no lo "
        "pongas entre comillas.\n"
        "- Nada de emojis ni de asteriscos."
    )


def scene_prompt(
    plan: ScenePlan,
    *,
    characters: dict[str, Character],
    max_words: int,
    previous: str | None = None,
    is_last: bool = False,
) -> str:
    """El pedido de UNA escena.

    Incluye lo que pasó antes para que el texto encadene, pero solo la escena
    anterior: alcanza para dar continuidad y mantiene el pedido corto y barato.
    """
    en_escena = ", ".join(
        f"{characters[cid].name} ({characters[cid].appearance.species})"
        for cid in plan.character_ids
        if cid in characters
    )

    partes = []
    if previous:
        partes.append(f"La escena anterior terminó así:\n«{previous}»\n")

    partes.append(
        "Escribí la narración de esta escena:\n"
        f"- Qué tiene que pasar: {plan.purpose}\n"
        f"- Dónde: {plan.location}\n"
        f"- Quiénes están: {en_escena}\n"
        f"- Clima emocional: {plan.emotion.value}\n"
        f"- MÁXIMO {max_words} palabras."
    )

    if is_last:
        partes.append(
            "Es la última escena: cerrá la historia con una sensación de final feliz, "
            "sin dejar nada abierto."
        )

    partes.append("Respondé únicamente con el texto de la narración.")
    return "\n".join(partes)


def retry_suffix(sobrante: int, max_words: int) -> str:
    """Qué agregar cuando el modelo se pasó de largo.

    Se le dice el número exacto: 'acortá' a secas devuelve textos que siguen sin
    entrar. Que sepa cuánto le sobra hace que el segundo intento funcione.
    """
    return (
        f"\n\nTu respuesta anterior tenía {sobrante} palabras de más. "
        f"Reescribila entera en {max_words} palabras o menos, sin perder lo esencial."
    )
