"""El planificador del nicho devocional. Sin IA, como el de los cuentos.

Es el hermano de `planner.py`: recibe una intención y devuelve un `StoryPlan` válido,
determinista y auditable. Se escribió aparte en vez de meterle parámetros al de
cuentos porque las tres decisiones que definen un planificador —cuántas escenas, qué
beat va en cada una, qué dice cada una— se toman distinto acá, y un planificador con
un `if genero == ...` adentro de cada método son dos planificadores mal escritos en el
mismo archivo.

LO QUE NO CAMBIA, a propósito: el `StoryPlan` que devuelve es el mismo objeto, con el
mismo arco de `NarrativeBeat`. Eso significa que se valida con el mismo código, que el
escritor, el ilustrador, el narrador y el render lo consumen sin enterarse, y que no
se tocó una línea de `constants.py` ni de `planner.py` — los cuentos de dinosaurios
salen exactamente igual que antes.

TRES DIFERENCIAS DE FONDO con el planificador de cuentos:

1. **No hay `age_range`.** Un devocional no está dirigido a una edad sino a un estado:
   quien busca "prayer for anxiety" a las tres de la mañana puede tener 19 o 70. El
   ritmo lo fija el género, no la atención de un chico de tres años.
2. **No hay compañero ni objeto.** Hay una sola figura, y representa a quien mira.
3. **El ritmo es mucho más lento.** `SCENE_PACING_S` va de 4 a 8 segundos por escena
   porque un cuento infantil necesita que pase algo todo el tiempo. Acá una imagen
   quieta con una voz encima aguanta bastante más, y apurarla rompe lo único que el
   formato tiene para ofrecer.

EL RITMO SALIÓ DE MEDIR EL NICHO, no de una intuición: sobre 53 videos de los canales
de oración en inglés que más crecieron, la duración **mediana es de 145 s** — contra
los 39,6 s del primer cuento. Medido con la API de YouTube el 7-ago-2026; está en el
diario del vault con el método.
"""

from __future__ import annotations

import math

from engine.core.constants import (
    CANONICAL_ARC,
    MAX_SCENE_DURATION_S,
    MAX_SCENES,
    MIN_SCENE_DURATION_S,
    MIN_SCENES,
)
from engine.core.enums import Emotion, Language, NarrativeBeat, ShotType, SpiritualNeed
from engine.core.exceptions import DomainError
from engine.core.models.character import Character
from engine.core.models.plan import ScenePlan, StoryPlan
from engine.core.models.theme import Theme
from engine.generators.devotional import (
    IMAGEN_COMUN,
    DevotionalProfile,
    profile_for,
)

#: Segundos por escena. Una imagen serena con narración encima sostiene mucho más que
#: una escena de cuento: con 15 s, un devocional de 150 s da 10 escenas, que es lo que
#: hace falta para nombrar varias cargas sin que ninguna quede a las apuradas.
RITMO_DEVOCIONAL_S = 15.0

#: Si hay que recortar, en qué orden se sacan beats.
#:
#: LA ESPERA es lo primero que se va: es el beat más honesto pero el más prescindible,
#: y en 60 s no hay lugar para matices. LA PROMESA no está en la lista y por lo tanto
#: no se saca nunca — un devocional que nombra una carga y no trae nada que la conteste
#: deja a quien mira peor de lo que estaba.
_ORDEN_DE_RECORTE: tuple[NarrativeBeat, ...] = (
    NarrativeBeat.FAILURE,
    NarrativeBeat.ATTEMPT,
    NarrativeBeat.PROBLEM,
)

#: Qué beats se repiten para estirar, y en qué orden.
#:
#: LA ESPERA queda AFUERA a propósito, y es la decisión menos obvia del módulo: decir
#: una vez "la respuesta no siempre llega cuando la pedimos" es honestidad, y es lo que
#: separa este contenido del que promete milagros a cambio de un like. Decirlo dos
#: veces en el mismo video ya no es honestidad, es desánimo — y desanimar a alguien que
#: entró buscando consuelo es exactamente el daño que este formato puede hacer.
_ORDEN_DE_REPETICION: tuple[NarrativeBeat, ...] = (
    NarrativeBeat.PROBLEM,
    NarrativeBeat.ATTEMPT,
)

#: Encuadre por beat. Es otro criterio que el de los cuentos: acá el plano no sigue a
#: un personaje —no hay personaje— sino a la distancia emocional. LA ESPERA se cuenta
#: en plano general para que la figura se vea chica contra el cielo.
#:
#: **LA PROMESA NO PUEDE SER `CLOSE_UP`, y ésta es la corrección más cara del módulo.**
#: Decía `CLOSE_UP` con el comentario *"primer plano de la luz, que es lo más parecido
#: a una cara que tiene este nicho"*. La intención era buena y quedó donde nadie podía
#: leerla: para el prompt de imagen `primer_plano` significa, textual, *"plano corto:
#: las caras y las manos llenan el cuadro"*. Así que el 7-ago-2026 la escena del
#: aprendizaje del primer devocional salió como el primer plano de una cara humana con
#: la boca abierta — en el único nicho que se eligió PORQUE no tiene caras.
#:
#: Es el error de [[un-sistema-una-carpeta]] en chico, por tercera vez: una decisión
#: tomada de un lado del motor que no cruza al otro. El primer plano de la luz se pide
#: donde sí se puede pedir, que es la dirección de arte (`IMAGEN_COMUN[LESSON]` ya dice
#: "a shaft of light breaking through clouds onto the ground, no figures"), no con un
#: tipo de plano que significa otra cosa.
PLANO_POR_BEAT: dict[NarrativeBeat, ShotType] = {
    NarrativeBeat.HOOK: ShotType.WIDE,
    NarrativeBeat.PROBLEM: ShotType.MEDIUM,
    NarrativeBeat.ATTEMPT: ShotType.MEDIUM,
    NarrativeBeat.FAILURE: ShotType.WIDE,
    NarrativeBeat.LESSON: ShotType.WIDE,
    NarrativeBeat.ENDING: ShotType.WIDE,
}

_LUGAR_POR_DEFECTO = "a quiet open landscape"

#: Cómo se numera un beat repetido, para que el escritor no reciba dos veces la misma
#: orden. En inglés porque los `purposes` van en inglés (ver `devotional.py`).
_ORDINAL: dict[int, str] = {0: "First", 1: "Then", 2: "Again", 3: "Once more"}


class DevotionalPlanner:
    """Convierte una necesidad espiritual en una estructura de oración guiada."""

    def create_plan(
        self,
        *,
        theme: Theme,
        need: SpiritualNeed,
        duration_s: float,
        speaker: Character,
        language: Language = Language.EN,
    ) -> StoryPlan:
        """Arma el plan completo.

        `speaker` es la figura que se ve en pantalla, y NO es un protagonista: no le
        pasa nada, no aprende nada y no tiene nombre propio en la narración. Está por
        una razón de forma —`ScenePlan` exige al menos un personaje, porque nadie habla
        solo al vacío— y por una razón de fondo: quien mira necesita un lugar donde
        ponerse, y una silueta a contraluz es un lugar donde cualquiera entra.

        Que sea una SILUETA no es una decisión estética. Es la que resuelve el problema
        más caro que tiene el motor: el verificador de anatomía sólo ataja uno de cada
        tres errores (medido el 7-ago-2026), así que hoy un humano tiene que mirar cada
        imagen antes de publicar. Una figura a contraluz no tiene dedos que contar ni
        patas de más: el error que el verificador no ve, acá directamente no puede
        ocurrir.

        `language` decide en qué idioma salen la promesa y la invitación —las dos cosas
        que se dibujan en pantalla—. El planificador de cuentos no lo recibe, y por eso
        hoy un cuento narrado en inglés cierra con la moraleja en español.
        """
        perfil = profile_for(need)
        if language not in perfil.promise:
            language = _idioma_mas_cercano(language, perfil)

        cantidad = self._cantidad_de_escenas(duration_s)
        beats = self._distribuir_beats(cantidad)
        duraciones = self._repartir_duracion(duration_s, len(beats))
        lugares = self._elegir_lugares(theme, len(beats))

        vistos: dict[NarrativeBeat, int] = {}
        escenas = []
        for i, (beat, dur, lugar) in enumerate(zip(beats, duraciones, lugares, strict=True)):
            repeticion = vistos.get(beat, 0)
            vistos[beat] = repeticion + 1
            escenas.append(
                ScenePlan(
                    index=i,
                    beat=beat,
                    purpose=self._redactar_proposito(
                        perfil,
                        beat,
                        speaker,
                        repeticion=repeticion,
                        total_del_beat=beats.count(beat),
                    ),
                    duration_s=dur,
                    location=lugar,
                    character_ids=[speaker.id],
                    emotion=perfil.emotions[beat],
                    # Vacío siempre y a propósito: `character_emotions` existe para que
                    # dos personajes no compartan la misma cara. Acá hay uno solo, así
                    # que anotarlo sería crear una segunda fuente de verdad del tono.
                    character_emotions={},
                    shot=PLANO_POR_BEAT[beat],
                    visual_note=self._imagen_de(perfil, beat),
                    # Sin objeto: el conflicto de un devocional no gira alrededor de una
                    # cosa. Poner uno traería de vuelta el problema que ya tuvo el lote
                    # de cuentos —el barrilete que nunca llegaba a la imagen—.
                    prop="",
                )
            )
        return StoryPlan(target_duration_s=duration_s, scenes=escenas)

    # ------------------------------------------------------------------ estructura
    def _cantidad_de_escenas(self, duration_s: float) -> int:
        """Cuántas escenas entran. Sin edad: el ritmo lo fija el género."""
        cantidad = round(duration_s / RITMO_DEVOCIONAL_S)

        # Los topes de escena mandan sobre el ritmo ideal, igual que en los cuentos:
        # con 150 s y escenas de 20 s como máximo hacen falta 8 sí o sí.
        cantidad = max(cantidad, math.ceil(duration_s / MAX_SCENE_DURATION_S))
        cantidad = min(cantidad, math.floor(duration_s / MIN_SCENE_DURATION_S))
        cantidad = max(MIN_SCENES, min(cantidad, MAX_SCENES))

        if duration_s / cantidad < MIN_SCENE_DURATION_S:
            raise DomainError(
                f"No se puede armar un devocional de {duration_s:.0f}s: ni con el mínimo "
                f"de {MIN_SCENES} escenas cada una llega a {MIN_SCENE_DURATION_S}s."
            )
        return cantidad

    def _distribuir_beats(self, cantidad: int) -> list[NarrativeBeat]:
        """El arco, estirado o recortado. Nunca altera el orden canónico."""
        arco = list(CANONICAL_ARC)

        for beat in _ORDEN_DE_RECORTE:
            if len(arco) <= cantidad:
                break
            arco.remove(beat)

        for repetible in _ciclo(*_ORDEN_DE_REPETICION):
            if len(arco) >= cantidad:
                break
            pos = _ultimo_indice(arco, repetible)
            if pos is None:
                # El beat se recortó por ser un devocional corto; no se lo trae de
                # vuelta por la puerta de atrás.
                continue
            arco.insert(pos + 1, repetible)
        return arco

    def _repartir_duracion(self, total_s: float, cantidad: int) -> list[float]:
        """Reparte los segundos en partes iguales; la última absorbe el redondeo."""
        base = round(total_s / cantidad, 2)
        duraciones = [base] * cantidad
        duraciones[-1] = round(total_s - base * (cantidad - 1), 2)
        return duraciones

    def _elegir_lugares(self, theme: Theme, cantidad: int) -> list[str]:
        """Reparte los lugares del tema entre las escenas, ciclando si faltan."""
        lugares = theme.locations or [_LUGAR_POR_DEFECTO]
        return [lugares[i % len(lugares)] for i in range(cantidad)]

    # -------------------------------------------------------------------- contenido
    def _imagen_de(self, perfil: DevotionalProfile, beat: NarrativeBeat) -> str:
        """La dirección de arte del beat: la propia del perfil, o la común.

        El fallback no es pereza: los beats que no tienen imagen propia son justamente
        los que se ven igual en cualquier necesidad —un amanecer abre igual de bien una
        oración por provisión que una por sanidad—, y lo que distingue a un devocional
        de otro es la carga que nombra, no el paisaje.
        """
        return perfil.imagery.get(beat) or IMAGEN_COMUN.get(beat, "")

    def _redactar_proposito(
        self,
        perfil: DevotionalProfile,
        beat: NarrativeBeat,
        speaker: Character,
        *,
        repeticion: int = 0,
        total_del_beat: int = 1,
    ) -> str:
        """La instrucción para el escritor, con los datos ya puestos.

        Cuando un beat se repite, cada repetición recibe una instrucción REALMENTE
        distinta si el perfil tiene variantes. Numerar sin cambiar el texto no alcanza:
        ya se probó en los cuentos y el modelo devolvía dos escenas calcadas.
        """
        variantes = perfil.deepenings.get(beat, ())
        if total_del_beat > 1 and repeticion < len(variantes):
            plantilla = variantes[repeticion]
        else:
            plantilla = perfil.purposes[beat]

        texto = plantilla.format(orante=speaker.name, escritura=perfil.scripture)

        if total_del_beat > 1 and repeticion >= len(variantes):
            texto = f"{_ORDINAL.get(repeticion, f'#{repeticion + 1}')}: {texto}"
        return texto


# --------------------------------------------------------------------------- utils
def _ciclo(*items: NarrativeBeat):
    """Alterna entre `items` para siempre (para estirar el arco de a un beat)."""
    while True:
        yield from items


def _ultimo_indice(arco: list[NarrativeBeat], beat: NarrativeBeat) -> int | None:
    for i in range(len(arco) - 1, -1, -1):
        if arco[i] is beat:
            return i
    return None


def _idioma_mas_cercano(language: Language, perfil: DevotionalProfile) -> Language:
    """El idioma disponible más parecido al pedido.

    Existe por un caso concreto: `Language.ES_AR` es el default de todo el motor y los
    perfiles están escritos en `ES` neutro, porque un devocional con voseo rioplatense
    en un canal que apunta a toda Latinoamérica suena local de más. Sin este fallback,
    pedir el default del motor reventaría con `KeyError`.
    """
    if language is Language.ES_AR and Language.ES in perfil.promise:
        return Language.ES
    return Language.EN


def promise_for(need: SpiritualNeed, language: Language = Language.EN) -> str:
    """La promesa de `need` en `language`. Va a la placa de cierre del video."""
    perfil = profile_for(need)
    return perfil.promise.get(language) or perfil.promise[
        _idioma_mas_cercano(language, perfil)
    ]


def invitation_for(need: SpiritualNeed, language: Language = Language.EN) -> str:
    """El cierre que pide respuesta, en `language`.

    Es la línea que produce el comentario, y el comentario es lo que este nicho tiene
    y el infantil no puede tener.
    """
    perfil = profile_for(need)
    return perfil.invitation.get(language) or perfil.invitation[
        _idioma_mas_cercano(language, perfil)
    ]
