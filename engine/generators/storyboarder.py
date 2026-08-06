"""El storyboard: escribe qué se ve en cada escena, mirando el cuento entero.

Corre entre el escritor y el ilustrador. Es el único paso del motor que ve todas las
escenas juntas, y existe exactamente por eso: la continuidad entre imágenes no se
puede resolver mirando una imagen por vez.

Es opcional a propósito. Si el proveedor falla o devuelve algo que no se puede usar,
el motor sigue con la narración cruda como venía haciendo: una secuencia con saltos
es peor que una con continuidad, pero es muchísimo mejor que no tener imágenes.
"""

from __future__ import annotations

import logging
import re

from engine.core.interfaces import TextProvider
from engine.core.models.story import Story
from engine.core.retry import con_reintentos
from engine.prompts import image as image_prompts
from engine.prompts import storyboard as prompts

logger = logging.getLogger(__name__)

#: Palabras que delatan que el storyboard cambió el clima o la hora, que es la regla
#: que más veces se rompió sola: el modelo traduce "triste" a "nublado" sin que nadie
#: se lo pida. Si aparecen, esa línea se descarta y la escena usa su narración.
_CLIMA = re.compile(
    r"\b(noche|nocturn\w+|atardecer|amanecer|anochec\w+|lluvi\w+|llov\w+|nubl\w+|"
    r"tormenta|niebla|neblina|oscur\w+|penumbra|grisác\w+|sombrí\w+)\b",
    re.IGNORECASE,
)

#: Un renglón del formato pedido: "2| Dino sostiene la pelota contra el pecho".
_RENGLON = re.compile(r"^\s*(\d+)\s*\|\s*(.+?)\s*$")


class Storyboarder:
    """Le pone la puesta en escena a una historia ya escrita."""

    def __init__(self, provider: TextProvider) -> None:
        self._provider = provider

    async def draw(self, story: Story) -> Story:
        """Completa `shot_description` en cada escena. Devuelve la MISMA historia.

        No cambia el texto, ni el elenco, ni el plan: sólo agrega qué se ve.
        """
        if not story.scenes:
            return story

        personajes = story.characters_by_id
        pedido = prompts.user_prompt(
            titulo=story.metadata.title or "Un cuento",
            lugar=story.scenes[0].location,
            elenco=", ".join(
                f"{p.name} ({p.appearance.species}, {', '.join(p.appearance.colors)})"
                for p in personajes.values()
            ),
            objeto=next((e.prop for e in story.scenes if e.prop), ""),
            escenas=[
                {
                    "indice": e.index,
                    "beat": e.beat.value,
                    "encuadre": e.camera.shot.value,
                    "quienes": " y ".join(
                        personajes[c].name for c in e.character_ids if c in personajes
                    ),
                    "texto": e.narration or e.purpose,
                }
                for e in story.scenes
            ],
        )

        try:
            crudo = await con_reintentos(
                lambda: self._provider.generate_text(pedido, system=prompts.SYSTEM),
                al_reintentar=lambda n, e: logger.warning(
                    "El storyboard falló (%s). Reintento %s.", e, n
                ),
            )
        except Exception as e:  # noqa: BLE001 — un storyboard perdido no frena el cuento
            logger.warning("Sin storyboard (%s): las imágenes usan la narración cruda.", e)
            return story

        nombres = {p.name for p in personajes.values()}
        for indice, descripcion in _renglones(crudo).items():
            escena = next((e for e in story.scenes if e.index == indice), None)
            if escena is None:
                continue
            if problema := _por_que_no_sirve(descripcion, escena, nombres, personajes):
                logger.warning("Escena %s: se descarta el storyboard — %s.", indice, problema)
                continue
            escena.shot_description = descripcion
            # El prompt de imagen se compuso al escribir, cuando esto todavía no
            # existía. Sin recomponerlo, la puesta en escena quedaría guardada en la
            # escena y no llegaría nunca a la imagen — que es el error de "subir un
            # asset al repo no es entregarlo", en versión prompt.
            escena.image_prompt = image_prompts.compose(
                escena, style=story.style, theme=story.theme, characters=personajes
            )

        puestas = sum(1 for e in story.scenes if e.shot_description)
        logger.info("Storyboard: %s de %s escenas con puesta en escena.", puestas, len(story.scenes))
        story.metadata.touch()
        return story


def _renglones(crudo: str) -> dict[int, str]:
    """Las líneas "N| descripción" que devolvió el modelo.

    Tolerante con lo de alrededor —un "Claro, acá va:" adelante no rompe nada— y
    estricto con el formato de cada línea: lo que no se entiende, no se usa.
    """
    salida: dict[int, str] = {}
    for linea in crudo.splitlines():
        if m := _RENGLON.match(linea):
            salida[int(m.group(1))] = m.group(2)
    return salida


def _por_que_no_sirve(
    descripcion: str, escena, nombres_del_elenco: set[str], personajes: dict
) -> str:
    """Por qué esta línea NO se puede usar, o cadena vacía si sirve.

    El storyboard puede escribir cualquier cosa; estas reglas son las que ya se
    ganaron mirando salidas reales y no se vuelven a discutir. Cuando una línea las
    rompe se descarta ENTERA y la escena vuelve a su narración: mejor una imagen sin
    puesta en escena que una con un personaje inventado adentro.
    """
    if len(descripcion) < 15:
        return "quedó demasiado corta para describir nada"

    if _CLIMA.search(descripcion):
        return "cambia el clima o la hora del día, y eso arruina la continuidad"

    # Un personaje del elenco que NO está en esta escena no puede aparecer en su
    # puesta en escena: es la regla 1 —elenco cerrado— por la puerta de atrás.
    presentes = {personajes[c].name for c in escena.character_ids if c in personajes}
    imaginados = {personajes[c].name for c in escena.imagined_character_ids if c in personajes}
    for nombre in nombres_del_elenco - presentes - imaginados:
        if re.search(rf"\b{re.escape(nombre)}\b", descripcion):
            return f"mete a {nombre}, que no está en esta escena"

    return ""
