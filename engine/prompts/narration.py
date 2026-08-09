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

from collections.abc import Sequence

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
        "- ESCRIBÍ PARA QUE SE LEA EN VOZ ALTA, no para que se lea en silencio:\n"
        "  · Puntos suspensivos antes de una sorpresa o un cambio: hacen que el "
        "narrador tome aire y generan expectativa. \"Abrió la puerta y... ¡sorpresa!\"\n"
        "  · Signos de exclamación y de pregunta de verdad, no de adorno: son los que "
        "levantan el tono.\n"
        "  · Diminutivos rioplatenses cuando queden naturales (chiquitito, un ratito, "
        "el osito): suavizan la lectura.\n"
        "- Nada de emojis ni de asteriscos."
    )


def scene_prompt(
    plan: ScenePlan,
    *,
    characters: dict[str, Character],
    max_words: int,
    previous: str | None = None,
    is_last: bool = False,
    aperturas: Sequence[str] = (),
    muletillas: Sequence[str] = (),
    narra_el_lugar: bool = True,
) -> str:
    """El pedido de UNA escena.

    Incluye lo que pasó antes para que el texto encadene, pero solo la escena
    anterior: alcanza para dar continuidad y mantiene el pedido corto y barato.

    `aperturas` son los arranques que ya se usaron en esta pieza, y existen porque
    **una regla que sólo mira la escena anterior no alcanza cuando hay veinte**.
    Medido sobre el primer devocional de 20 minutos (8-ago-2026): el sistema ya decía
    *"NEVER open a scene with the same words as the scene before it"* y **diez de las
    veinte escenas abrieron con "As…"** — *"As dawn breaks"*, *"As you breathe in"*,
    *"As the day unfolds"*, *"As the dawn breaks gently"*. Ninguna repetía a su vecina
    exacta, así que ninguna violaba la regla, y el conjunto es igual el *"generic or
    unoriginal template"* que la política de YouTube del 16-jul-2026 castiga con el
    canal entero. Con seis escenas el problema no existía; con veinte, sí.

    `narra_el_lugar=False` **le saca la ubicación al pedido**, y es la corrección más
    cara de las dos. El sistema devocional dice, textual: *"NEVER describe the location
    or what the person is doing or seeing. The location you are given is there so the
    ILLUSTRATOR knows what to draw"*. Y el pedido, dos líneas después, le mostraba
    `- Dónde: a country road between fields at sunrise`. El escritor hizo lo esperable:
    *"As you walk along a quiet country road"*, *"As you stand at the shoreline"*.

    **Pedirle algo en la regla y darle lo contrario en el dato no es una regla débil,
    es una regla imposible.** Es el mismo patrón que ya mordió dos veces a este motor:
    el ejemplo del prompt que el escritor repitió, y la respuesta puesta adentro de la
    pregunta del verificador de anatomía. Si el género no narra el lugar, el lugar no
    va en el pedido — la escena lo sigue teniendo para el ilustrador.
    """
    en_escena = ", ".join(
        f"{characters[cid].name} ({characters[cid].appearance.species})"
        for cid in plan.character_ids
        if cid in characters
    )

    partes = []
    if previous:
        partes.append(f"La escena anterior terminó así:\n«{previous}»\n")
    if aperturas:
        usadas = "\n".join(f"- «{a}…»" for a in aperturas)
        partes.append(
            "ARRANQUES YA USADOS EN ESTA PIEZA. Tu primera frase no puede empezar "
            "como ninguno de éstos, ni con las mismas primeras palabras:\n"
            f"{usadas}\n"
        )
    if muletillas:
        repes = "\n".join(f"- «{m}»" for m in muletillas)
        partes.append(
            "FRASES QUE ESTA PIEZA YA REPITIÓ. No uses ninguna, ni una variante que "
            "cambie una palabra. Decí lo mismo de otra manera:\n"
            f"{repes}\n"
        )

    lugar = f"- Dónde: {plan.location}\n" if narra_el_lugar else ""
    partes.append(
        "Escribí la narración de esta escena:\n"
        f"- Qué tiene que pasar: {plan.purpose}\n"
        f"{lugar}"
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
