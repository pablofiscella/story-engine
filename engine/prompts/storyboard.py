"""El storyboard: pensar las imágenes del cuento juntas, no una por una.

Hasta acá cada imagen se componía sola, con la narración de SU escena como única
descripción de lo que se ve. El problema es que la narración está escrita para
**oírse**: *"Dino se fue a un rincón y jugó solo"* no dice dónde queda el rincón, ni
qué hace el otro mientras tanto, ni si el objeto quedó en el piso. Cada imagen
resolvía esos huecos por su cuenta, y como los resolvía distinto cada vez, la
secuencia daba saltos.

Pablo, mirando el primer lote de ocho: *"hay que leer el fragmento de texto y pensar
bien la imagen y que tenga coherencia con las que siguen"*.

Por eso este paso lee **todas las escenas de una vez** y escribe qué se ve en cada
una. Es la única forma de que la imagen 3 sepa cómo terminó la 2 — un modelo que ve
una escena por vez no puede dar continuidad, por buenas que sean sus respuestas.

**Lo que este paso NO decide**, porque ya lo decidió el motor y no se discute: quién
aparece, qué emoción tiene cada uno, el encuadre, el objeto, el lugar, el clima. Eso
sigue entrando al prompt de imagen como bloque aparte y le gana a lo que diga acá.
Este paso describe la puesta en escena; no reescribe la historia.
"""

from __future__ import annotations

SYSTEM = (
    "Sos director de fotografía de una serie de cuentos infantiles ilustrados. "
    "Tu trabajo es convertir el texto de cada escena en una descripción de LO QUE SE "
    "VE, pensando las escenas como una secuencia continua y no como imágenes sueltas.\n\n"
    "Reglas:\n"
    "1. Describí posiciones concretas: dónde está cada personaje en el cuadro, qué "
    "hace con las manos, hacia dónde mira. Nada de estados de ánimo abstractos.\n"
    "2. CONTINUIDAD: cada escena arranca donde terminó la anterior. Si un objeto quedó "
    "en el piso, sigue en el piso. Si un personaje estaba sentado, no aparece de pie "
    "sin motivo. Si algo cambió, que se note por qué.\n"
    "3. No inventes personajes, animales ni criaturas: sólo los que te nombran.\n"
    "4. No cambies la hora del día ni el clima: es siempre el mismo día soleado. La "
    "emoción va en la cara y el cuerpo, nunca en el cielo.\n"
    "5. Escenas distintas tienen que verse distintas: cambiá la distancia, el ángulo o "
    "la posición de los personajes entre una y otra.\n"
    "6. Una o dos oraciones por escena, concretas y visuales. Sin adjetivos de "
    "sentimiento ('conmovedor', 'mágico'): eso no se dibuja."
)


def user_prompt(
    *,
    titulo: str,
    lugar: str,
    elenco: str,
    objeto: str,
    escenas: list[dict],
) -> str:
    """El pedido: el cuento entero, escena por escena, y qué devolver.

    Se le da el cuento COMPLETO aunque después describa una escena por línea: sin ver
    el final no puede sembrar lo que el final necesita, y sin ver el principio repite
    lo que ya se mostró.
    """
    lineas = [
        f"CUENTO: {titulo}",
        f"LUGAR (el mismo en todas): {lugar}",
        f"PERSONAJES (no hay ningún otro): {elenco}",
    ]
    if objeto:
        lineas.append(f"OBJETO de la historia, tiene que verse: {objeto}")
    lineas.append("")
    lineas.append("LAS ESCENAS, en orden:")
    for e in escenas:
        quienes = e["quienes"] or "nadie más que el protagonista"
        lineas.append(
            f"[{e['indice']}] ({e['beat']}, encuadre {e['encuadre']}, en escena: {quienes})\n"
            f"    texto: {e['texto']}"
        )
    lineas += [
        "",
        f"Devolvé EXACTAMENTE {len(escenas)} líneas, una por escena, con este formato "
        "y nada más:",
        "0| lo que se ve en la escena 0",
        "1| lo que se ve en la escena 1",
        "…",
    ]
    return "\n".join(lineas)
