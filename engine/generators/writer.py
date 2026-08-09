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
from collections.abc import Sequence

from engine.core.enums import StoryStatus
from engine.core.exceptions import ProviderError
from engine.core.interfaces import TextProvider
from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.core.retry import con_reintentos
from engine.generators.script_inspector import frases_repetidas
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

    async def write(
        self,
        story: Story,
        *,
        sistema: str | None = None,
        narra_el_lugar: bool = True,
    ) -> Story:
        """Escribe todas las escenas de `story` y la deja en estado WRITTEN.

        Necesita que la historia ya tenga plan. Devuelve la MISMA historia mutada:
        el plan, el tema y el elenco no se tocan.

        `sistema` permite pasar OTRO prompt de narrador. Existe porque el motor dejó de
        contar una sola clase de cosa: el prompt por defecto dice "sos un cuentacuentos
        que narra para chicos de 3 a 5 años" y calibra el vocabulario por edad, que es
        exactamente lo que no hay que decirle a quien narra una oración para adultos.
        Es un parámetro y no un `if`: el escritor no tiene por qué saber cuántos
        géneros existen.
        """
        if story.plan is None:
            raise ValueError("La historia no tiene plan: hay que planificarla antes de escribirla.")

        sistema = sistema or prompts.system_prompt(
            language=story.metadata.language,
            age_range=story.metadata.age_range,
            value_moral=story.moral or "",
        )
        personajes = story.characters_by_id
        escenas: list[Scene] = []
        anterior: str | None = None
        # Los arranques ya usados, para que la escena 14 no abra como la 3. Sin esto,
        # diez de veinte escenas del primer devocional largo abrieron con "As…": la
        # regla del sistema sólo prohíbe repetir a la escena ANTERIOR, y con veinte
        # escenas eso no alcanza. Ver `scene_prompt`.
        aperturas: list[str] = []
        # Las frases que la pieza ya repitió, calculadas con el MISMO detector que usa
        # el verificador después. Ver `muletillas_ya_usadas`.
        muletillas: list[str] = []

        for plan in story.plan.scenes:
            escena = await self._escribir_escena(
                plan,
                sistema=sistema,
                personajes=personajes,
                anterior=anterior,
                es_ultima=plan.index == len(story.plan.scenes) - 1,
                aperturas=aperturas,
                muletillas=muletillas,
                narra_el_lugar=narra_el_lugar,
            )
            escena.image_prompt = image_prompts.compose(
                escena, style=story.style, theme=story.theme, characters=personajes
            )
            escenas.append(escena)
            anterior = escena.narration
            aperturas.append(apertura_de(escena.narration))
            muletillas = muletillas_ya_usadas([e.narration for e in escenas])

        story.scenes = escenas
        if story.status is StoryStatus.PLANNED:
            story.advance_to(StoryStatus.WRITTEN)
        story.metadata.touch()
        return story

    async def reescribir(
        self,
        escena: Scene,
        story: Story,
        *,
        correccion: str = "",
        sistema: str | None = None,
        anterior: str | None = None,
    ) -> Scene:
        """Vuelve a escribir UNA escena, con una corrección encima.

        Es la hermana de `SceneIllustrator.rehacer`, y existe por la misma razón: el
        verificador encuentra el problema en una escena y reescribir el guion entero
        sería tirar todo lo que estaba bien. Devuelve la MISMA escena mutada, con la
        narración y el subtítulo nuevos — el índice, el beat y la duración no se tocan,
        así que el plan sigue valiendo.

        `correccion` no es decorativo: **pedir lo mismo otra vez es lo que ya falló**
        con las tomas de voz que nacían cortadas y con las imágenes de anatomía rota.
        Al modelo hay que darle una orden realmente distinta, y la orden distinta es el
        reparo concreto que se leyó en el intento anterior.
        """
        sistema = sistema or prompts.system_prompt(
            language=story.metadata.language,
            age_range=story.metadata.age_range,
            value_moral=story.moral or "",
        )
        tope = _presupuesto(escena.duration_s)
        pedido = prompts.scene_prompt(
            escena,
            characters=story.characters_by_id,
            max_words=tope,
            previous=anterior,
            is_last=escena.index == len(story.scenes) - 1,
        )
        if correccion:
            pedido = f"{pedido}\n\n{correccion}"

        crudo = await con_reintentos(
            lambda: self._provider.generate_text(pedido, system=sistema, temperature=0.8),
            al_reintentar=lambda n, e: logger.warning(
                "Escena %s: el proveedor de texto falló al reescribir (%s). Reintento %s.",
                escena.index, e, n,
            ),
        )
        texto = _limpiar(crudo)
        if not texto:
            raise ProviderError(
                f"El escritor devolvió texto vacío al reescribir la escena {escena.index}."
            )
        if len(texto.split()) > tope:
            texto = _recortar(texto, tope)

        escena.narration = texto
        escena.subtitle = _subtitulo(texto)
        return escena

    # ------------------------------------------------------------------------
    async def _escribir_escena(
        self,
        plan,
        *,
        sistema: str,
        personajes,
        anterior: str | None,
        es_ultima: bool,
        aperturas: Sequence[str] = (),
        muletillas: Sequence[str] = (),
        narra_el_lugar: bool = True,
    ) -> Scene:
        """Una escena, con reintentos si el texto no entra en su duración."""
        tope = _presupuesto(plan.duration_s)
        pedido = prompts.scene_prompt(
            plan,
            characters=personajes,
            max_words=tope,
            previous=anterior,
            is_last=es_ultima,
            aperturas=aperturas,
            muletillas=muletillas,
            narra_el_lugar=narra_el_lugar,
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
                        aperturas=aperturas,
                        muletillas=muletillas,
                        narra_el_lugar=narra_el_lugar,
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


#: Cuántas palabras del arranque se le muestran al escritor como "ya usada".
#:
#: Cuatro. Con dos, *"As dawn"* y *"As you"* cuentan como arranques distintos y el
#: escritor sigue empezando todo igual; con ocho, la lista se vuelve una lista de
#: frases enteras y **empieza a funcionar como ejemplo en vez de como prohibición** —
#: la trampa que este motor ya documentó dos veces. Cuatro alcanza para que *"As the
#: dawn breaks gently"* y *"As the dawn breaks softly"* choquen entre sí.
PALABRAS_DE_APERTURA = 4


def apertura_de(narracion: str) -> str:
    """Las primeras palabras de una escena, para que ninguna otra empiece igual."""
    return " ".join(narracion.split()[:PALABRAS_DE_APERTURA])


#: Cuántas frases repetidas se le muestran al escritor por pedido.
#:
#: Ocho. La lista es una PROHIBICIÓN, y una prohibición de cuarenta renglones deja de
#: leerse: el modelo la trata como contexto de fondo. Se muestran las que más veces
#: aparecieron, que son las que están por convertirse en el estribillo del video.
MULETILLAS_EN_EL_PEDIDO = 8


def muletillas_ya_usadas(narraciones: list[str]) -> list[str]:
    """Las frases que esta pieza ya repitió, para que la próxima escena no las use.

    **Es el guardián de muletillas usado ANTES en vez de sólo después.** El verificador
    de guion las detecta cuando el guion ya está escrito y manda a reescribir; acá la
    misma función evita que la frase se propague. La diferencia se ve en el número:
    sobre el devocional de 20 minutos del 8-ago-2026, *"You are not alone"* llegó a
    **seis escenas** (0, 2, 4, 7, 15, 18) y el verificador la marcó una vez que ya
    estaba en las seis. Prohibirla a partir de la tercera corta la propagación.

    Se reusa `frases_repetidas` y no se escribe otra: dos detectores de lo mismo se
    desincronizan, y el que corrige tiene que estar de acuerdo con el que acusa.
    """
    repetidas = frases_repetidas(narraciones)
    # Las más repetidas primero: son las que están por volverse el estribillo.
    ordenadas = sorted(repetidas, key=lambda x: (-len(x[1]), x[1][0]))
    return [frase for frase, _ in ordenadas[:MULETILLAS_EN_EL_PEDIDO]]
