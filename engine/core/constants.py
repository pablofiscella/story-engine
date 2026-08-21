"""Límites y valores canónicos del dominio.

Todo número mágico del motor vive acá. Si mañana los Shorts pasan a durar 90s,
se cambia en un lugar y no hay que salir a cazar `60` por todo el código.
"""

from __future__ import annotations

from types import MappingProxyType

from engine.core.enums import AgeRange, NarrativeBeat, ShotType, StoryStatus

#: Orden canónico del arco. El planificador puede REPETIR beats (varios intentos)
#: o saltear alguno en historias muy cortas, pero nunca alterar este orden relativo.
CANONICAL_ARC: tuple[NarrativeBeat, ...] = (
    NarrativeBeat.HOOK,
    NarrativeBeat.PROBLEM,
    NarrativeBeat.ATTEMPT,
    NarrativeBeat.FAILURE,
    NarrativeBeat.LESSON,
    NarrativeBeat.ENDING,
)

#: Posición de cada beat, para validar orden sin recorrer la tupla.
BEAT_ORDER: MappingProxyType[NarrativeBeat, int] = MappingProxyType(
    {beat: i for i, beat in enumerate(CANONICAL_ARC)}
)

#: Con qué encuadre se cuenta cada beat.
#:
#: Antes todas las escenas salían en plano medio y el cuento se veía plano: el
#: gancho y el intento daban literalmente la misma imagen —el protagonista solo con
#: el objeto— porque tenían el mismo elenco y el mismo encuadre.
#:
#: El criterio es de cine, no de variedad por variedad: el gancho ABRE (hay que ver
#: dónde estamos), el conflicto se cuenta a media distancia (hay que ver a los dos y
#: el objeto), el aprendizaje es un momento de cara, y el final vuelve a abrir para
#: mostrar el mundo ya arreglado.
SHOT_BY_BEAT: MappingProxyType[NarrativeBeat, ShotType] = MappingProxyType(
    {
        NarrativeBeat.HOOK: ShotType.WIDE,
        NarrativeBeat.PROBLEM: ShotType.MEDIUM,
        NarrativeBeat.ATTEMPT: ShotType.OVER_SHOULDER,
        NarrativeBeat.FAILURE: ShotType.MEDIUM,
        NarrativeBeat.LESSON: ShotType.CLOSE_UP,
        NarrativeBeat.ENDING: ShotType.WIDE,
    }
)

# --- Duración -------------------------------------------------------------------
MIN_STORY_DURATION_S = 15
MAX_STORY_DURATION_S = 600
DEFAULT_STORY_DURATION_S = 30

MIN_SCENE_DURATION_S = 2.0
MAX_SCENE_DURATION_S = 20.0

#: Tolerancia al comparar la suma de escenas contra la duración objetivo. El
#: planificador reparte segundos y el redondeo no puede hacer fallar la validación.
DURATION_TOLERANCE_S = 1.0

# --- Estructura -----------------------------------------------------------------
MIN_SCENES = 3
MAX_SCENES = 40

# --- Ritmo por edad -------------------------------------------------------------
#: Segundos "cómodos" por escena según la franja: cuanto más chico el chico, más
#: corta la escena (la atención no da para más) y más simple el vocabulario.
SCENE_PACING_S: MappingProxyType[AgeRange, float] = MappingProxyType(
    {
        AgeRange.TODDLER: 4.0,
        AgeRange.PRESCHOOL: 5.0,
        AgeRange.EARLY: 6.5,
        AgeRange.KID: 8.0,
    }
)

#: Palabras habladas por segundo. Es el guardián contra el vicio clásico del modelo:
#: escribir un párrafo hermoso que no entra en 5 segundos.
#:
#: CALIBRADO CONTRA UN GUION REAL (el storyboard "El dinosaurio que aprendió a
#: compartir", 6 escenas de 5s): promedio 2.13 pal/s, pico 2.6 pal/s = ~128 pal/min.
#: 2.5 cubre el pico sin dejar pasar párrafos imposibles. El valor teórico de 2.0
#: rechazaba narración profesional perfectamente decible.
WORDS_PER_SECOND = 2.5

#: Aire extra sobre el presupuesto antes de rechazar. Chico a propósito: con el ritmo
#: ya calibrado contra material real, una tolerancia grande solo dejaría pasar audio
#: que no entra en la escena.
NARRATION_OVERFLOW_TOLERANCE = 1.15

# --- Texto ----------------------------------------------------------------------
MAX_TITLE_LENGTH = 120
MAX_SUBTITLE_LENGTH = 90

# --- Pipeline -------------------------------------------------------------------
#: A qué estados puede pasar cada estado. El pipeline avanza en un solo sentido:
#: no se puede renderizar algo que no se narró. FAILED se alcanza desde cualquier
#: lado, y desde FAILED se puede volver a intentar la etapa que falló.
ALLOWED_TRANSITIONS: MappingProxyType[StoryStatus, frozenset[StoryStatus]] = MappingProxyType(
    {
        StoryStatus.DRAFT: frozenset({StoryStatus.PLANNED, StoryStatus.FAILED}),
        StoryStatus.PLANNED: frozenset({StoryStatus.WRITTEN, StoryStatus.FAILED}),
        StoryStatus.WRITTEN: frozenset(
            # el audiolibro no necesita imágenes: puede saltar directo a narrado
            {StoryStatus.ILLUSTRATED, StoryStatus.NARRATED, StoryStatus.FAILED}
        ),
        StoryStatus.ILLUSTRATED: frozenset({StoryStatus.NARRATED, StoryStatus.FAILED}),
        StoryStatus.NARRATED: frozenset({StoryStatus.RENDERED, StoryStatus.FAILED}),
        StoryStatus.RENDERED: frozenset({StoryStatus.PUBLISHED, StoryStatus.FAILED}),
        StoryStatus.PUBLISHED: frozenset({StoryStatus.FAILED}),
        StoryStatus.FAILED: frozenset(
            {
                StoryStatus.PLANNED,
                StoryStatus.WRITTEN,
                StoryStatus.ILLUSTRATED,
                StoryStatus.NARRATED,
                StoryStatus.RENDERED,
            }
        ),
    }
)


# --- Ritmo del video ------------------------------------------------------------
#: Silencio entre una escena y la siguiente.
#:
#: Sin esto las narraciones se pisan: la última palabra de una escena y la primera
#: de la siguiente quedan pegadas, y el cuento suena apurado. Lo escuchó Pablo en el
#: primer short: *"entre cada texto parece que se junta mucho el audio"*.
PAUSA_ENTRE_ESCENAS_S = 0.45

#: Aire después de la última palabra, antes de que termine el video.
#:
#: Un cuento que corta en seco en la última sílaba se siente roto aunque esté
#: completo. También le da lugar al fundido.
COLA_FINAL_S = 1.2

#: Cuánto dura la placa de título del principio.
#: Corta a propósito: en un short los primeros segundos deciden si se quedan.
# La placa del título, sobre la primera imagen. Bajó de 2 s a 0,8 s el 13-ago-2026: con la voz
# arrancando de una (ver render/video.py), dos segundos de placa dejaban el título colgado
# encima de una narración que ya iba por la mitad de la frase.
TITULO_S = 0.8

#: Cuánto se acerca (o se aleja) la cámara a lo largo de UNA escena, en tanto por uno.
#:
#: La imagen del cuento es un PNG fijo: sin esto, el video son ocho diapositivas de 5 s con
#: voz encima. El 15-ago-2026 Pablo miró la retención —27,9 % se quedaban a mirar, y de esos
#: la mitad se iba antes del segundo 13— y el diagnóstico fue el arranque, no el contenido:
#: en un feed donde todo se mueve, una imagen quieta se lee como "esto no va a pasar nada".
#:
#: 9 % es poco a propósito. Más que eso marea en vertical y se nota el recorte de los bordes.
ZOOM_POR_ESCENA = 0.09
