"""Las etiquetas de entonación: cómo se DICE cada escena.

Mandarle texto crudo a ElevenLabs v3 suena, con palabras de Pablo escuchando la
primera muestra de los audiolibros, **"saturado y con falta de entonación"**. El
modelo sabe actuar, pero hay que pedírselo: `[warmly]`, `[excited]`, `[whispers]`.

Acá el motor tiene una ventaja sobre el audiolibro viejo. Allá `_etiqueta_pagina()`
tiene que ADIVINAR el tono leyendo el texto y buscando señales. Acá no hace falta
adivinar: el plan ya decidió el beat y la emoción de cada escena antes de que
existiera una sola palabra. La etiqueta sale de esa decisión, no de una heurística.

Es la misma regla que gobierna el prompt de imagen: lo que el motor decidió no puede
depender de que alguien lo deduzca del texto después.

**Una sola etiqueta por escena**, salvo la apertura. La combinación del gancho
—`[warmly] [slows down]`— está fija y el orden importa: salió de que Pablo escuchara
la versión con solo `[warmly]` y pidiera *"un poco más de entonación y un poco más
lento/pausado"*. Con las dos dijo *"Bien"*. No se cambia sin volver a escucharla.

Si el modelo de voz no entiende etiquetas —`eleven_multilingual_v2` las LEE en voz
alta— el proveedor las saca solo. Acá no hay que acordarse de nada.
"""

from __future__ import annotations

from engine.core.enums import Emotion, NarrativeBeat

#: La DIRECCIÓN de la toma: qué se le pide al modelo antes de una palabra de cuento.
#:
#: Es la receta que trajo Pablo (5-jul-2026) y que el motor viejo nunca llegó a usar.
#: Va en el primer renglón, entre corchetes, y le da al modelo el contexto de
#: actuación completo en vez de una etiqueta suelta.
DIRECCION = (
    "[Narración de cuento infantil, voz muy expresiva, dulce, animada, acento "
    "argentino natural, tono cálido de cuentacuentos, pausas marcadas para generar "
    "expectativa.]"
)

#: La apertura. Combinación fija y probada al oído; el orden importa.
APERTURA = "[warmly] [slows down]"

#: Cómo se dice cada emoción. Una por escena: dos etiquetas seguidas se pisan y el
#: resultado es peor que ninguna.
_POR_EMOCION: dict[Emotion, str] = {
    Emotion.JOY: "[excited]",
    Emotion.SURPRISE: "[excited]",
    Emotion.PRIDE: "[proudly]",
    Emotion.CURIOSITY: "[curious]",
    Emotion.SADNESS: "[sadly]",
    Emotion.FEAR: "[whispers]",
    Emotion.FRUSTRATION: "[frustrated]",
    Emotion.CALM: "[calmly]",
}


def direccion_de_escena(beat: NarrativeBeat, emotion: Emotion, *, es_primera: bool) -> str:
    """La dirección completa de la toma: contexto de actuación + tono de la escena.

    Las dos cosas juntas y no una u otra: la dirección le dice al modelo QUÉ está
    haciendo (contar un cuento a un chico, en argentino) y la etiqueta le dice cómo
    va ESTA escena. Sin la primera, el modelo lee como un noticiero.
    """
    return f"{DIRECCION} {etiqueta_de_escena(beat, emotion, es_primera=es_primera)}".strip()


def etiqueta_de_escena(beat: NarrativeBeat, emotion: Emotion, *, es_primera: bool) -> str:
    """Cómo hay que decir esta escena.

    La primera lleva la apertura sí o sí: es la que decide si el chico se queda o se
    va, y arrancar plano es perder el short en el primer segundo.
    """
    if es_primera:
        return APERTURA
    return _POR_EMOCION.get(emotion, "")


def con_entonacion(texto: str, etiqueta: str) -> str:
    """El texto listo para el modelo de voz.

    La etiqueta va adelante y separada: es una instrucción de actuación, no parte de
    lo que se dice. Por eso tampoco cuenta para el presupuesto de palabras ni para
    verificar que la toma llegó entera.
    """
    return f"{etiqueta} {texto}".strip() if etiqueta else texto
