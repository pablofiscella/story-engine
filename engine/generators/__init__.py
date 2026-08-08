"""Generadores: la parte del motor que produce contenido.

Hay DOS planificadores, y ninguno de los dos sabe del otro:

- `planner.StoryPlanner` + `values` — cuentos con valores para chicos de 3 a 6.
- `devotional_planner.DevotionalPlanner` + `devotional` — oraciones guiadas para
  adultos, el nicho que se abrió el 7-ago-2026.

Los dos devuelven el mismo `StoryPlan`, así que el escritor, el ilustrador, el
narrador y el render los consumen sin enterarse de cuál los armó. Están separados
porque las tres decisiones que definen un planificador —cuántas escenas, qué beat va
en cada una y qué dice cada una— se toman distinto en cada género, y un planificador
con un `if genero == ...` adentro de cada método son dos planificadores mal escritos
en el mismo archivo.

Los nombres se re-exportan con prefijo donde chocan (`PROFILES` existe en los dos):
importar el equivocado sería generar un cuento de dinosaurios en un canal de oración,
que es la versión de contenido del accidente de credenciales que ya costó tres
vueltas en `ct3d`.
"""

from engine.generators.devotional import PROFILES as DEVOTIONAL_PROFILES
from engine.generators.devotional import DevotionalProfile
from engine.generators.devotional_planner import (
    DevotionalPlanner,
    invitation_for,
    promise_for,
)
from engine.generators.illustrator import SceneIllustrator
from engine.generators.planner import StoryPlanner
from engine.generators.values import PROFILES, ValueProfile, profile_for

__all__ = [
    "DEVOTIONAL_PROFILES",
    "PROFILES",
    "DevotionalPlanner",
    "DevotionalProfile",
    "SceneIllustrator",
    "StoryPlanner",
    "ValueProfile",
    "invitation_for",
    "profile_for",
    "promise_for",
]
