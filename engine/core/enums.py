"""Vocabulario cerrado del dominio.

Todo lo que es un conjunto FIJO y curado vive acá como enum: si mañana alguien
escribe `value="compartir!"` o `age="4 años"`, el motor lo rechaza en el borde en
vez de arrastrar un string roto hasta el render.

Lo que NO va acá: temas y personajes. Esos son DATOS (viven en `assets/`) porque
crecen todo el tiempo y tienen estructura propia (paleta, voz, poses). Un enum los
volvería un cuello de botella: agregar "dinosaurios marinos" no puede requerir tocar
código. Ver `models/theme.py`.
"""

from __future__ import annotations

from enum import StrEnum


class Language(StrEnum):
    """Idioma de la narración. El motor es multi-idioma desde el día 1."""

    ES_AR = "es-AR"
    ES = "es"
    EN = "en"
    PT_BR = "pt-BR"


class AgeRange(StrEnum):
    """Franja etaria destino.

    Es una FRANJA y no un número suelto porque todo lo que depende de la edad
    (vocabulario, cantidad de escenas, ritmo) se define por tramo, no por año.
    `from_age()` acepta la edad puntual que suele venir del usuario.
    """

    TODDLER = "2-3"
    PRESCHOOL = "3-5"
    EARLY = "5-7"
    KID = "7-9"

    @classmethod
    def from_age(cls, age: int) -> AgeRange:
        """Franja que contiene a `age`. Fuera de rango → la más cercana.

        Permite que la API acepte `age=4` (lo natural para quien la usa) sin que el
        resto del motor tenga que razonar nunca con años sueltos.
        """
        if age <= 3:
            return cls.TODDLER
        if age <= 5:
            return cls.PRESCHOOL
        if age <= 7:
            return cls.EARLY
        return cls.KID

    @property
    def bounds(self) -> tuple[int, int]:
        """(edad_min, edad_max) de la franja."""
        low, high = self.value.split("-")
        return int(low), int(high)


class EducationalValue(StrEnum):
    """El valor que la historia enseña. Es el ancla pedagógica del arco.

    Lista curada a propósito: cada valor necesita que el planificador sepa cómo
    construir un conflicto que lo ponga en juego. Sumar uno implica decidir eso,
    no solo agregar una palabra.
    """

    SHARING = "compartir"
    FRIENDSHIP = "amistad"
    RESPECT = "respeto"
    HONESTY = "honestidad"
    EMPATHY = "empatia"
    PATIENCE = "paciencia"
    COURAGE = "valentia"
    PERSEVERANCE = "perseverancia"
    # 12-ago-2026: los ocho primeros ya se publicaron o están agendados en Cuentitos de
    # Colores. Estos dos abren la serie sin repetir tema, y siguen la misma regla que los
    # demás: cada uno trae su propio conflicto en `values.py`, porque un valor sin conflicto
    # pensado es una palabra suelta y no una historia.
    ASKING_FOR_HELP = "pedir-ayuda"
    APOLOGIZING = "pedir-perdon"


class CharacterRole(StrEnum):
    """Rol narrativo del personaje dentro de UNA historia.

    Es del vínculo historia↔personaje, no del personaje: el mismo dinosaurio puede
    ser protagonista en un cuento y secundario en otro. Por eso vive en `StoryCharacter`
    y no en `Character`.
    """

    PROTAGONIST = "protagonista"
    COMPANION = "companero"
    MENTOR = "mentor"
    RIVAL = "rival"
    EXTRA = "secundario"


class NarrativeBeat(StrEnum):
    """Los pasos del arco narrativo.

    ESTA ES LA DECISIÓN CENTRAL DEL MOTOR. El planificador arma una secuencia de
    beats ANTES de que ninguna IA escriba una palabra; recién después el escritor
    rellena la narración de cada uno. Por eso todas las historias salen con la misma
    estructura sólida, sin depender de que el modelo "tenga un buen día".

    Orden canónico en `constants.CANONICAL_ARC`.
    """

    HOOK = "gancho"
    PROBLEM = "problema"
    ATTEMPT = "intento"
    FAILURE = "error"
    LESSON = "aprendizaje"
    ENDING = "final"


class StoryStatus(StrEnum):
    """Dónde está la historia dentro del pipeline.

    Avanza en un solo sentido (salvo FAILED). Cada etapa agrega algo que la anterior
    no tenía: PLANNED tiene beats, WRITTEN tiene narración, ILLUSTRATED tiene imágenes.
    """

    DRAFT = "draft"
    PLANNED = "planned"
    WRITTEN = "written"
    ILLUSTRATED = "illustrated"
    NARRATED = "narrated"
    RENDERED = "rendered"
    PUBLISHED = "published"
    FAILED = "failed"


class Emotion(StrEnum):
    """Emoción dominante de una escena.

    La decide el planificador (no la IA) y baja a TRES consumidores: el prompt de
    imagen (expresión del personaje), la narración (tono) y la música.
    """

    CURIOSITY = "curiosidad"
    JOY = "alegria"
    SADNESS = "tristeza"
    FEAR = "miedo"
    SURPRISE = "sorpresa"
    FRUSTRATION = "frustracion"
    CALM = "calma"
    PRIDE = "orgullo"


class ShotType(StrEnum):
    """Encuadre. Vocabulario de cine, no de IA: se traduce a prompt de imagen."""

    WIDE = "plano_general"
    MEDIUM = "plano_medio"
    CLOSE_UP = "primer_plano"
    OVER_SHOULDER = "sobre_hombro"


class CameraMovement(StrEnum):
    """Movimiento de cámara. En imagen fija se resuelve como Ken Burns en el render."""

    STATIC = "fijo"
    PAN_LEFT = "paneo_izquierda"
    PAN_RIGHT = "paneo_derecha"
    ZOOM_IN = "acercamiento"
    ZOOM_OUT = "alejamiento"


class MusicMood(StrEnum):
    """Clima musical de la escena."""

    PLAYFUL = "juguetona"
    TENSE = "tension"
    TENDER = "tierna"
    TRIUMPHANT = "triunfal"
    CALM = "calma"


class OutputKind(StrEnum):
    """QUÉ artefacto se produce.

    Una historia se planifica y escribe UNA sola vez y se materializa en varios
    formatos: el mismo cuento es un short, un audiolibro, un PDF imprimible y una
    ficha de actividades. Por eso `Story` no es "un video": es el CONTENIDO, y esto
    es en qué se convierte.
    """

    SHORT = "short"  # video vertical corto (Shorts/Reels)
    VIDEO = "video"  # video largo horizontal (YouTube clásico)
    AUDIOBOOK = "audiobook"
    BOOK = "book"  # libro ilustrado (PDF imprimible o digital)
    ACTIVITY = "activity"  # imprimible de actividades
    IMAGE_POST = "image_post"  # placa/carrusel para feed


class Channel(StrEnum):
    """DÓNDE se publica. Eje independiente de `OutputKind`.

    El mismo short va a YouTube, Instagram y Facebook sin volver a generarse. Mezclar
    formato y canal en un solo enum obliga a duplicar todo ("short_yt", "short_ig")
    y a reescribir el motor cuando aparece una plataforma nueva.
    """

    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    STORE = "store"  # la tienda propia (descarga directa)


class AspectRatio(StrEnum):
    """Relación de aspecto del render.

    La define el formato + el canal: un short es 9:16, un video de YouTube 16:9, una
    placa de feed 1:1 o 4:5. Se decide al exportar, no al escribir la historia.
    """

    VERTICAL = "9:16"
    HORIZONTAL = "16:9"
    SQUARE = "1:1"
    PORTRAIT = "4:5"
    PRINT_A4 = "210:297"


class AudioKind(StrEnum):
    """Qué es cada pista de audio de una escena.

    Se separan porque no las dice la misma voz: la narración la lee el narrador de la
    historia y el diálogo lo dice el personaje, con SU voz. Mezclarlas obligaría al
    render a adivinar quién habla.
    """

    NARRATION = "narracion"
    DIALOGUE = "dialogo"
