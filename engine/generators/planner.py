"""El planificador: arma el esqueleto de la historia. Sin IA.

Es la mitad del motor que DECIDE. Recibe qué contar (tema, valor, edad, duración) y
devuelve un `StoryPlan` completo: cuántas escenas, qué hace cada una, cuánto dura,
quién aparece, qué se siente y dónde transcurre.

Todo esto es determinista y auditable: dos llamadas con los mismos parámetros dan
exactamente el mismo plan. Recién con ese plan en la mano el escritor de IA redacta
la narración de cada escena (`engine/generators/writer.py`, Sprint 2b).

Que sea código y no un prompt es lo que hace que la historia 500 salga tan bien
armada como la primera.
"""

from __future__ import annotations

import math

from engine.core.constants import (
    CANONICAL_ARC,
    MAX_SCENE_DURATION_S,
    MAX_SCENES,
    MIN_SCENE_DURATION_S,
    MIN_SCENES,
    SCENE_PACING_S,
)
from engine.core.enums import AgeRange, EducationalValue, NarrativeBeat
from engine.core.exceptions import DomainError
from engine.core.models.character import Character
from engine.core.models.plan import ScenePlan, StoryPlan
from engine.core.models.theme import Theme
from engine.generators.values import ValueProfile, profile_for

#: Si hay que recortar el arco (historias muy cortas), en qué orden se sacan beats.
#: FAILURE primero porque es el más prescindible: se puede contar un aprendizaje sin
#: mostrar el fracaso. LESSON es lo último que se saca — es la carga pedagógica.
_ORDEN_DE_RECORTE: tuple[NarrativeBeat, ...] = (
    NarrativeBeat.FAILURE,
    NarrativeBeat.ATTEMPT,
    NarrativeBeat.LESSON,
)

_LUGAR_POR_DEFECTO = "el lugar de siempre"

#: Cómo se numera un beat que se repite, para que el escritor no reciba dos veces la
#: misma orden y escriba dos escenas iguales.
_ORDINAL: dict[int, str] = {0: "Primero", 1: "Después", 2: "Una vez más", 3: "Otra vez"}


class StoryPlanner:
    """Convierte una intención en una estructura narrativa válida."""

    def create_plan(
        self,
        *,
        theme: Theme,
        value: EducationalValue,
        age_range: AgeRange,
        duration_s: float,
        protagonist: Character,
        companion: Character | None = None,
    ) -> StoryPlan:
        """Arma el plan completo.

        `companion` es opcional: si no hay, los beats que lo necesitan se reescriben
        para que el protagonista los resuelva solo. Nunca se inventa un personaje que
        la historia no declaró — esa es justamente la causa de que los ilustradores
        dibujen a alguien distinto en cada escena.
        """
        perfil = profile_for(value)
        cantidad = self._cantidad_de_escenas(duration_s, age_range)
        beats = self._distribuir_beats(cantidad)
        duraciones = self._repartir_duracion(duration_s, len(beats))
        lugares = self._elegir_lugares(theme, len(beats))
        objeto = self._elegir_objeto(perfil, theme)

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
                        protagonist,
                        companion,
                        objeto=objeto,
                        repeticion=repeticion,
                        total_del_beat=beats.count(beat),
                    ),
                    duration_s=dur,
                    location=lugar,
                    character_ids=self._elenco_de(perfil, beat, protagonist, companion),
                    emotion=perfil.emotions[beat],
                )
            )
        return StoryPlan(target_duration_s=duration_s, scenes=escenas)

    # ------------------------------------------------------------------ estructura
    def _cantidad_de_escenas(self, duration_s: float, age_range: AgeRange) -> int:
        """Cuántas escenas entran, según la duración y la atención de la edad.

        El ritmo por edad manda (un chico de 3 no aguanta una escena de 8s), pero la
        duración de escena tiene topes duros: si el ritmo pidiera escenas de 30s, se
        agregan escenas hasta que cada una entre en el máximo.
        """
        ritmo = SCENE_PACING_S[age_range]
        cantidad = round(duration_s / ritmo)

        # los topes de escena mandan sobre el ritmo ideal
        cantidad = max(cantidad, math.ceil(duration_s / MAX_SCENE_DURATION_S))
        cantidad = min(cantidad, math.floor(duration_s / MIN_SCENE_DURATION_S))

        cantidad = max(MIN_SCENES, min(cantidad, MAX_SCENES))
        if duration_s / cantidad < MIN_SCENE_DURATION_S:
            raise DomainError(
                f"No se puede armar una historia de {duration_s:.0f}s: ni con el mínimo "
                f"de {MIN_SCENES} escenas cada una llega a {MIN_SCENE_DURATION_S}s."
            )
        return cantidad

    def _distribuir_beats(self, cantidad: int) -> list[NarrativeBeat]:
        """El arco, estirado o recortado a `cantidad` escenas.

        Nunca altera el orden canónico: para estirar repite beats intermedios (dos
        intentos seguidos), para recortar saca los más prescindibles.
        """
        arco = list(CANONICAL_ARC)

        for beat in _ORDEN_DE_RECORTE:
            if len(arco) <= cantidad:
                break
            arco.remove(beat)

        # estirar: duplicar intento/error alternadamente, siempre a continuación del
        # original para no romper el orden (ATTEMPT, ATTEMPT, FAILURE es válido;
        # ATTEMPT, FAILURE, ATTEMPT no lo es).
        for repetible in _ciclo(NarrativeBeat.ATTEMPT, NarrativeBeat.FAILURE):
            if len(arco) >= cantidad:
                break
            pos = _ultimo_indice(arco, repetible)
            if pos is None:
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
        """Reparte los lugares del tema entre las escenas.

        Cicla si hay menos lugares que escenas: repetir escenario es normal en un
        cuento corto, e inventar lugares que el tema no declaró rompe la coherencia
        visual del mundo.
        """
        lugares = theme.locations or [_LUGAR_POR_DEFECTO]
        return [lugares[i % len(lugares)] for i in range(cantidad)]

    # -------------------------------------------------------------------- contenido
    def _elegir_objeto(self, perfil: ValueProfile, theme: Theme) -> str:
        """El objeto concreto alrededor del cual gira el conflicto.

        Lo elige el MOTOR y no el escritor. Si lo inventa la IA, el prompt de imagen
        —que se compone del plan— no se entera, y la ilustración muestra al personaje
        feliz con las manos vacías mientras el texto habla de una piedra brillante.
        Pasó de verdad al probar con la API real.
        """
        if not perfil.needs_prop:
            return ""
        return theme.props[0] if theme.props else "un juguete nuevo"

    def _elenco_de(
        self,
        perfil: ValueProfile,
        beat: NarrativeBeat,
        protagonist: Character,
        companion: Character | None,
    ) -> list[str]:
        """Quiénes aparecen en el beat.

        El protagonista siempre. El compañero solo donde el guion lo necesita — y eso
        se deduce del propio texto del propósito: si la plantilla lo menciona, está
        en escena. Así no hay dos fuentes de verdad que puedan desincronizarse.
        """
        ids = [protagonist.id]
        if companion is not None and "{companero}" in perfil.purposes[beat]:
            ids.append(companion.id)
        return ids

    def _redactar_proposito(
        self,
        perfil: ValueProfile,
        beat: NarrativeBeat,
        protagonist: Character,
        companion: Character | None,
        *,
        objeto: str = "",
        repeticion: int = 0,
        total_del_beat: int = 1,
    ) -> str:
        """La instrucción para el escritor, con los nombres ya puestos.

        Sin compañero, los beats que lo requieren se reescriben en solitario: el
        protagonista se da cuenta solo. Es peor narrativamente, pero es honesto — y
        mucho mejor que ilustrar a un personaje fantasma.

        Cuando un beat se repite (historias largas con dos intentos), cada repetición
        recibe una instrucción DISTINTA. Sin esto, el escritor recibía dos veces la
        misma orden y producía dos escenas idénticas.
        """
        # Si el beat se repite y el valor tiene variantes, cada repetición recibe una
        # instrucción REALMENTE distinta. La numeración sola no alcanzaba: con
        # "Primero:"/"Después:" el modelo devolvía dos escenas casi calcadas.
        variantes = perfil.escalations.get(beat, ())
        if total_del_beat > 1 and repeticion < len(variantes):
            plantilla = variantes[repeticion]
        else:
            plantilla = perfil.purposes[beat]

        if companion is None:
            plantilla = _sin_companero(plantilla)
            texto = plantilla.format(protagonista=protagonist.name, objeto=objeto)
        else:
            texto = plantilla.format(
                protagonista=protagonist.name, companero=companion.name, objeto=objeto
            )

        # Solo numerar si no hubo variante propia: ahí la repetición sigue siendo el
        # mismo texto y al menos hay que señalar que es otro momento.
        if total_del_beat > 1 and repeticion >= len(variantes):
            texto = f"{_ORDINAL.get(repeticion, f'{repeticion + 1}º')}: {texto}"
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


def _sin_companero(plantilla: str) -> str:
    """Reescribe una instrucción para que funcione sin segundo personaje."""
    reemplazos = {
        "{companero} quiere jugar con {objeto} y {protagonista} se niega": (
            "{protagonista} tiene que decidir si comparte {objeto} o lo guarda"
        ),
        "Los dos juegan juntos con {objeto}, mucho más felices": (
            "{protagonista} comparte {objeto} y descubre que así es mucho más divertido"
        ),
        "{protagonista} y {companero} juegan juntos como viejos amigos": (
            "{protagonista} ya no está solo y juega contento"
        ),
        "{protagonista} y {companero} lo arreglan juntos, aliviados": (
            "{protagonista} ayuda a arreglarlo, aliviado"
        ),
        "Los dos hacen las cosas a su manera, juntos y contentos": (
            "{protagonista} acepta que hay muchas maneras, y todas valen"
        ),
        "{companero} se anima, y juegan juntos de verdad": (
            "{protagonista} aprende a mirar cómo están los demás"
        ),
        "{companero} lo invita, y {protagonista} descubre que bastaba con animarse": (
            "{protagonista} se anima y descubre que bastaba con eso"
        ),
        "{companero} lo hace distinto y {protagonista} se burla": (
            "{protagonista} descubre que hay otra forma de hacerlo y la rechaza"
        ),
        "{companero} se aleja triste y {protagonista} se queda incómodo": (
            "{protagonista} se queda incómodo con su propia reacción"
        ),
        "{protagonista} prueba la forma de {companero} y descubre que también funciona": (
            "{protagonista} prueba la otra forma y descubre que también funciona"
        ),
    }
    if plantilla in reemplazos:
        return reemplazos[plantilla]
    # genérico: sacar al compañero de la frase sin romperla
    return plantilla.replace("{companero}", "alguien más")
