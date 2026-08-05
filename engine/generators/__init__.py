"""Generadores: la parte del motor que produce contenido.

El planificador (`planner`) decide la estructura sin IA. El escritor (`writer`, en
camino) le pone las palabras a cada escena usando un `TextProvider`.
"""

from engine.generators.planner import StoryPlanner
from engine.generators.values import PROFILES, ValueProfile, profile_for

__all__ = ["PROFILES", "StoryPlanner", "ValueProfile", "profile_for"]
