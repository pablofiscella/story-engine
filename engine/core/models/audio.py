"""El audio de una escena, ya generado y MEDIDO.

La pieza central de este módulo es `duration_s`, y conviene entender por qué.

El plan le da a cada escena una duración (`Scene.duration_s`) y el escritor escribe
para esa duración usando una estimación: 2.5 palabras por segundo. Es una buena
estimación —está calibrada contra un storyboard real— pero sigue siendo una
estimación. El audio de verdad dura lo que dura.

Si el render usa la estimación en vez de la medición, pasa una de dos cosas, y las
dos son visibles: la imagen cambia antes de que el narrador termine la frase, o queda
un silencio raro al final de la escena. Es el mismo problema que ya tuvo el
audiolibro de Casatridimensional.

Por eso el narrador no solo genera el audio: lo **mide** y lo guarda acá. De ahí en
adelante manda esta duración y no la del plan.

Se pide WAV y no mp3 por una razón práctica: la stdlib de Python sabe leer la
duración de un WAV (módulo `wave`) y no la de un mp3. Poder medir sin sumar una
dependencia vale más que el tamaño del archivo, que además es temporal — el render
comprime al final.
"""

from __future__ import annotations

from pydantic import Field

from engine.core.enums import AudioKind
from engine.core.models.base import EngineModel, Slug


class AudioTrack(EngineModel):
    """Una pista de audio: una narración o una línea de diálogo, ya sintetizada."""

    kind: AudioKind
    character_id: Slug | None = Field(
        default=None,
        description="Quién la dice. `None` es el narrador, que no es un personaje.",
    )
    text: str = Field(min_length=1, description="Exactamente lo que se dijo.")
    path: str = Field(min_length=1, description="Ruta del archivo de audio.")
    duration_s: float = Field(
        gt=0,
        description="Duración REAL, medida del archivo. No es la estimada por el plan.",
    )
    voice_id: str = Field(
        default="",
        description="Voz concreta del proveedor. Se guarda para poder repetir la toma igual.",
    )
