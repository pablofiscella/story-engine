"""El escritor: le pone las palabras al plan.

Es la única parte del motor que le habla a un modelo de lenguaje, y lo hace de la
forma más acotada posible: **una escena por vez**, con el objetivo ya decidido, los
personajes ya elegidos y el presupuesto de palabras explícito.

Lo que el escritor NO decide: cuántas escenas hay, qué pasa en cada una, quién
aparece, cuánto dura, cómo se ve. Todo eso ya vino resuelto en el plan. Por eso una
IA distinta —o el mismo modelo en un mal día— cambia la prosa pero no puede arruinar
la historia.

Si la narración no entra en los segundos de la escena, se la manda a reescribir con
el número exacto de palabras que sobran. Si igual no entra, se recorta en el último
punto: mejor una escena un poco más corta que un audio que se corta a la mitad.
"""

from __future__ import annotations

import logging
import re

from engine.core.enums import StoryStatus
from engine.core.exceptions import ProviderError
from engine.core.interfaces import TextProvider
from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.core.retry import con_reintentos
from engine.prompts import image as image_prompts
from engine.prompts import narration as prompts

logger = logging.getLogger(__name__)

#: Cuántas veces se le pide que acorte antes de recortar nosotros. Dos alcanzan: si
#: con el número exacto de sobrante no entra, no va a entrar nunca.
MAX_REINTENTOS = 2


class StoryWriter:
    """Convierte un `StoryPlan` en escenas escritas."""

    def __init__(self, provider: TextProvider) -> None:
        self._provider = provider

    async def write(self, story: Story) -> Story:
        """Escribe todas las escenas de `story` y la deja en estado WRITTEN.

        Necesita que la historia ya tenga plan. Devuelve la MISMA historia mutada:
        el plan, el tema y el elenco no se tocan.
        """
        if story.plan is None:
            raise ValueError("La historia no tiene plan: hay que planificarla antes de escribirla.")

        sistema = prompts.system_prompt(
            language=story.metadata.language,
            age_range=story.metadata.age_range,
            value_moral=story.moral or "",
        )
        personajes = story.characters_by_id
        escenas: list[Scene] = []
        anterior: str | None = None

        for plan in story.plan.scenes:
            escena = await self._escribir_escena(
                plan,
                sistema=sistema,
                personajes=personajes,
                anterior=anterior,
                es_ultima=plan.index == len(story.plan.scenes) - 1,
            )
            escena.image_prompt = image_prompts.compose(
                escena, style=story.style, theme=story.theme, characters=personajes
            )
            escenas.append(escena)
            anterior = escena.narration

        story.scenes = escenas
        story.metadata.title = self._titular(story, escenas)
        if story.status is StoryStatus.PLANNED:
            story.advance_to(StoryStatus.WRITTEN)
        story.metadata.touch()
        return story

    # ------------------------------------------------------------------------
    @staticmethod
    def _titular(story, escenas) -> str:
        """El título que va en el cartel de apertura.

        POR QUÉ EXISTE: nadie lo escribía. `metadata.title` quedaba en "" y el render
        caía en su respaldo —"Un cuento"— así que los videos abrían con un cartel
        genérico. Pablo lo vio publicado: "los dos videos cuando comienzan dicen cuento
        y no el titulo".

        Se arma con lo que ya está decidido —el protagonista y el objeto del conflicto—
        en vez de pedírselo al modelo: un cuento de 40 segundos no necesita ingenio en
        el título, y un pedido más es un gasto más por cuento.
        """
        # `story.characters` son StoryCharacter (personaje + papel), no Character:
        # el nombre está un nivel más adentro. Se busca al protagonista, no al primero.
        from engine.core.enums import CharacterRole
        heroe = ""
        for sc in story.characters:
            if sc.role is CharacterRole.PROTAGONIST:
                heroe = (sc.character.name or "").strip()
                break
        if not heroe and story.characters:
            heroe = (story.characters[0].character.name or "").strip()
        objeto = ""
        if story.plan is not None:
            objeto = (getattr(story.plan, "object_name", "") or "").strip()
        if not objeto:
            # El objeto vive en el plan; si el plan no lo expone, sale de la primera escena.
            import re as _re
            primera = escenas[0].narration if escenas else ""
            m = _re.search(r"\b(?:un|una|el|la|los|las)\s+(\w+(?:\s+\w+)?)", primera)
            objeto = m.group(1).strip() if m else ""
        objeto = objeto.rstrip(".,!?")
        if heroe and objeto:
            return f"{heroe} y {objeto}"
        return heroe or objeto or ""

    async def _escribir_escena(
        self,
        plan,
        *,
        sistema: str,
        personajes,
        anterior: str | None,
        es_ultima: bool,
    ) -> Scene:
        """Una escena, con reintentos si el texto no entra en su duración."""
        tope = _presupuesto(plan.duration_s)
        pedido = prompts.scene_prompt(
            plan,
            characters=personajes,
            max_words=tope,
            previous=anterior,
            is_last=es_ultima,
        )

        texto = ""
        for intento in range(MAX_REINTENTOS + 1):
            # Dos reintentos distintos, que no hay que confundir: este es por si el
            # proveedor se cae (un 500, un rate limit); el del bucle de afuera es
            # porque el texto no entró en los segundos de la escena.
            crudo = await con_reintentos(
                lambda p=pedido: self._provider.generate_text(
                    p, system=sistema, temperature=0.8
                ),
                al_reintentar=lambda n, e: logger.warning(
                    "Escena %s: el proveedor de texto falló (%s). Reintento %s.",
                    plan.index, e, n,
                ),
            )
            texto = _limpiar(crudo)
            if not texto:
                raise ProviderError(f"El escritor devolvió texto vacío en la escena {plan.index}.")
            sobrante = len(texto.split()) - tope
            if sobrante <= 0:
                break
            if intento < MAX_REINTENTOS:
                pedido = (
                    prompts.scene_prompt(
                        plan,
                        characters=personajes,
                        max_words=tope,
                        previous=anterior,
                        is_last=es_ultima,
                    )
                    + prompts.retry_suffix(sobrante, tope)
                )
        else:
            texto = _recortar(texto, tope)

        return Scene.from_plan(
            plan,
            narration=texto,
            subtitle=_subtitulo(texto),
        )


# --------------------------------------------------------------------------- utils
def _presupuesto(duration_s: float) -> int:
    """Palabras que entran en `duration_s`.

    Se pide un poco MENOS de lo que `Scene` acepta: el modelo siempre roza el techo,
    y dejando aire el texto entra sin necesidad de reescribir. Es más barato pedir de
    menos que gastar un segundo pedido.
    """
    from engine.core.constants import WORDS_PER_SECOND

    return max(4, int(duration_s * WORDS_PER_SECOND))


_ETIQUETAS = re.compile(r"^\s*(escena\s*\d+\s*[:.\-]|narraci[oó]n\s*[:.\-])\s*", re.IGNORECASE)


def _limpiar(texto: str) -> str:
    """Saca lo que el modelo agrega aunque le pidas que no.

    Comillas envolviendo todo, un "Escena 3:" al principio, asteriscos de markdown.
    Es más confiable limpiarlo que confiar en que esta vez sí obedeció.
    """
    t = (texto or "").strip()
    t = _ETIQUETAS.sub("", t)
    t = t.replace("*", "").replace("_", "")
    if len(t) > 1 and t[0] in "«\"'" and t[-1] in "»\"'":
        t = t[1:-1].strip()
    return " ".join(t.split())


#: Palabras que no pueden quedar al final de una frase cortada: no cierran nada y
#: dejan el texto colgado ("...juegan con la pelota en el.").
_COLGANTES = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "con",
    "por", "para", "sin", "sobre", "a", "al", "y", "e", "o", "u", "que", "su", "sus",
    "mi", "tu", "lo", "se", "muy", "más", "pero",
})

#: Qué tan atrás puede estar el último punto para que valga la pena cortar ahí.
#: Terminar en una frase completa suena mucho mejor que truncar en el medio, así que
#: se acepta perder hasta un 60% del texto con tal de cerrar bien.
_CORTE_MINIMO = 0.4


def _recortar(texto: str, tope: int) -> str:
    """Último recurso: cortar en el punto más cercano que entre en el presupuesto."""
    palabras = texto.split()
    if len(palabras) <= tope:
        return texto
    corto = " ".join(palabras[:tope])
    corte = max(corto.rfind("."), corto.rfind("!"), corto.rfind("?"))
    if corte >= len(corto) * _CORTE_MINIMO:  # cerrar en frase, si no queda un pedacito
        return corto[: corte + 1]
    # Sin punto donde cortar: al menos que no termine colgado en "en el." — se sueltan
    # las palabras de función finales, que no cierran nada.
    palabras_cortas = corto.split()
    while palabras_cortas and palabras_cortas[-1].lower().strip(",;:") in _COLGANTES:
        palabras_cortas.pop()
    return " ".join(palabras_cortas).rstrip(",;: ") + "."


def _subtitulo(texto: str, largo: int = 90) -> str:
    """El subtítulo que va en pantalla.

    Suele ser la narración tal cual; si es muy larga para un short, se corta en la
    primera frase.
    """
    if len(texto) <= largo:
        return texto
    corte = texto.rfind(".", 0, largo)
    return texto[: corte + 1] if corte > 20 else texto[: largo - 1].rstrip() + "…"
