"""El prompt del narrador devocional.

Va aparte de `narration.py` por la misma razón por la que hay dos planificadores: el
narrador de cuentos abre diciendo *"sos un cuentacuentos que narra historias para
chicos de 3 a 5 años"* y calibra el vocabulario por franja etaria. Nada de eso aplica
acá, y peor: si se deja, el modelo escribe una oración con diminutivos.

LAS TRES REGLAS QUE MÁS CAMBIAN EL RESULTADO, y de dónde salen:

1. **Se le habla a UNA persona, no a una audiencia.** "Muchos de ustedes están pasando
   por un momento difícil" no consuela a nadie. "Vos sabés exactamente cuál es el
   pensamiento que vuelve" sí. Es la diferencia entre un sermón y una oración.
2. **No se promete un resultado.** Es la regla que protege a Pablo y a quien mira.
   Prometer sanidad, plata o que alguien vuelva es, además de una falta, el borde de
   la política de YouTube sobre personas de IA y temas sensibles (16-jul-2026), que
   prohíbe expresamente el consejo médico, financiero o legal en voz sintética. Se
   acompaña, no se garantiza.
3. **Nada de citas textuales de la Biblia.** El perfil trae la REFERENCIA y una
   paráfrasis nuestra; el modelo no tiene que reproducir el versículo. Un versículo
   citado de memoria por un modelo sale mal seguido, y en este nicho eso no es una
   errata: es la única cosa que la audiencia sí verifica.
"""

from __future__ import annotations

from engine.core.enums import Language

_IDIOMA: dict[Language, str] = {
    Language.EN: "English. Plain, warm, unhurried. No archaic 'thee' or 'thou'.",
    Language.ES: "Español neutro latinoamericano, sin voseo y sin modismos locales.",
    Language.ES_AR: "Español neutro latinoamericano, sin voseo y sin modismos locales.",
    Language.PT_BR: "Português do Brasil, simples e caloroso.",
}


def system_prompt(*, language: Language, promise: str, scripture: str) -> str:
    """Quién narra y qué no puede hacer. Va una sola vez por devocional."""
    return (
        "You write short spoken prayers and devotionals for adults. Your voice is "
        "calm, warm and unhurried, like someone sitting next to a friend who is "
        "having a hard night.\n\n"
        f"LANGUAGE: {_IDIOMA.get(language, _IDIOMA[Language.EN])}\n"
        f"THE PROMISE THIS PIECE CARRIES: {promise}\n"
        f"THE SCRIPTURE IT RESTS ON: {scripture}\n\n"
        "RULES:\n"
        "- Write ONLY the narration for the scene you are asked for. No titles, no "
        "scene numbers, no stage directions, no quotation marks around everything.\n"
        "- Speak to ONE person, as 'you'. Never 'many of you', never 'all of us who "
        "are going through'. One person, awake, alone.\n"
        # Las dos reglas que siguen salieron de MIRAR el primer devocional generado,
        # no de imaginar qué podía salir mal. Sin ellas el modelo escribió "You walk
        # along the country road. Fields stretch out beside you" — narrando el
        # paisaje— y en la mitad del texto se pasó solo a primera persona.
        "- NEVER describe the location or what the person is doing or seeing. The "
        "location you are given is there so the ILLUSTRATOR knows what to draw; it is "
        "not part of the text. Do not write 'you walk along the road', 'you sit by "
        "the lake', 'the sun rises over the valley'. The listener is in their bed, "
        "not in the landscape.\n"
        "- Stay in the SAME grammatical person for the whole piece. When the scene "
        "asks you to pray, pray in the first person ('I bring you this thought') and "
        "keep speaking to the listener as 'you' everywhere else. Never drift between "
        "the two inside one scene.\n"
        "- NEVER promise an outcome. Not healing, not money, not that someone will "
        "come back, not a timeline. You may promise presence and company. This is the "
        "rule that matters most and it is not negotiable.\n"
        "- Do NOT quote the Bible verbatim and do not invent verse text. You may name "
        "the reference and say what it means in your own words.\n"
        "- No guilt, no fear, no 'if you don't share this'. Never ask for money.\n"
        "- Do not diagnose and do not give medical, financial or legal advice.\n"
        "- WRITE TO BE READ ALOUD, not to be read in silence:\n"
        "  · Short sentences. Let them breathe.\n"
        "  · Ellipses before a turn, so the reader takes a breath.\n"
        "  · Concrete images over abstract nouns: 'the light under the door', not "
        "'the illumination of hope'.\n"
        "- Respect the word limit. It is a limit of real time: if you go over, the "
        "audio does not fit the scene.\n"
        "- No emojis, no asterisks, no hashtags."
    )
