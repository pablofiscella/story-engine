"""`Story`: la raíz del dominio.

Todo el motor gira alrededor de esta clase.

Una historia NO es un video. Es el CONTENIDO — el plan, el texto, los personajes —
y de ahí salen todos los formatos: short, video largo, audiolibro, libro ilustrado,
imprimible de actividades, placa para feed. Se planifica y se escribe una sola vez;
después se materializa tantas veces como haga falta, para tantos canales como haya.

Por eso `outputs` es una lista y no un campo `video_path`: el día que sumemos un
formato nuevo, `Story` no cambia.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from engine.core.constants import ALLOWED_TRANSITIONS
from engine.core.enums import (
    CharacterRole,
    EducationalValue,
    NarrativeBeat,
    OutputKind,
    StoryStatus,
)
from engine.core.exceptions import (
    InvalidStateTransitionError,
    UnknownCharacterError,
)
from engine.core.models.base import EngineModel
from engine.core.models.character import Character
from engine.core.models.metadata import StoryMetadata
from engine.core.models.output import Output
from engine.core.models.plan import StoryPlan
from engine.core.models.scene import Scene
from engine.core.models.style import Style
from engine.core.models.theme import Theme


class StoryCharacter(EngineModel):
    """Un personaje EN esta historia, con el rol que cumple acá.

    El rol vive en el vínculo y no en `Character` porque el mismo personaje puede ser
    protagonista de un cuento y secundario de otro.
    """

    character: Character
    role: CharacterRole = CharacterRole.EXTRA


class Story(EngineModel):
    """Una historia completa, en cualquier punto de su ciclo de vida."""

    metadata: StoryMetadata = Field(default_factory=StoryMetadata)
    theme: Theme
    style: Style = Field(
        description=(
            "Cómo se dibuja ESTA historia. Independiente del tema: el mismo cuento de "
            "dinosaurios puede salir en 3D estilo Pixar o en palitos 2D."
        )
    )
    value: EducationalValue
    characters: list[StoryCharacter] = Field(min_length=1)

    moral: str = Field(
        default="",
        max_length=200,
        description=(
            "La idea principal en una frase: 'Compartir nos hace más felices'. "
            "El `value` es la etiqueta ('compartir'); esto es cómo se DICE en ESTA "
            "historia. Va en el cierre del video, en la contratapa del libro y en la "
            "descripción del post."
        ),
    )
    closing_question: str = Field(
        default="",
        max_length=200,
        description=(
            "Pregunta final al espectador: '¿Y vos, qué compartís con tus amigos?'. "
            "Es lo que convierte a un espectador en comentario — el motor de alcance "
            "en YouTube e Instagram. Vacía en formatos donde no aplica."
        ),
    )

    plan: StoryPlan | None = Field(
        default=None, description="El esqueleto. Existe desde PLANNED en adelante."
    )
    scenes: list[Scene] = Field(
        default_factory=list, description="Las escenas escritas. Desde WRITTEN en adelante."
    )
    outputs: list[Output] = Field(
        default_factory=list, description="Todo lo generado a partir de esta historia."
    )

    # ------------------------------------------------------------------ validación
    @model_validator(mode="after")
    def _validar_elenco(self) -> Story:
        """Nadie puede aparecer en una escena sin estar en el elenco.

        Es LA validación que sostiene la consistencia visual: si una escena nombra un
        personaje que la historia no declaró, el generador de imágenes no tiene su
        descripción canónica y lo dibuja distinto cada vez. Falla acá, temprano y
        barato, en vez de en la imagen 40.
        """
        conocidos = {sc.character.id for sc in self.characters}

        for escena in self.scenes:
            # los imaginados cuentan igual: si no están declarados, el prompt no los
            # describe y el modelo los inventa (el Rexo violeta de la burbuja).
            desconocidos = (
                set(escena.character_ids)
                | set(escena.imagined_character_ids)
                | set(escena.character_emotions)
            ) - conocidos
            if desconocidos:
                raise UnknownCharacterError(
                    f"La escena {escena.index} usa personajes que no están en el elenco: "
                    f"{sorted(desconocidos)}. Elenco: {sorted(conocidos)}."
                )
            for linea in escena.dialogue:
                if linea.character_id not in conocidos:
                    raise UnknownCharacterError(
                        f"La escena {escena.index} tiene diálogo de '{linea.character_id}', "
                        f"que no está en el elenco: {sorted(conocidos)}."
                    )

        if self.plan is not None:
            desconocidos = self.plan.character_ids - conocidos
            if desconocidos:
                raise UnknownCharacterError(
                    f"El plan usa personajes fuera del elenco: {sorted(desconocidos)}."
                )
        return self

    # -------------------------------------------------------------------- consultas
    @property
    def id(self) -> object:
        return self.metadata.id

    @property
    def status(self) -> StoryStatus:
        return self.metadata.status

    @property
    def duration_s(self) -> float:
        """Duración real (suma de escenas). Antes de escribir, la del plan."""
        if self.scenes:
            return round(sum(s.duration_s for s in self.scenes), 3)
        if self.plan is not None:
            return self.plan.total_duration_s
        return 0.0

    @property
    def characters_by_id(self) -> dict[str, Character]:
        return {sc.character.id: sc.character for sc in self.characters}

    @property
    def protagonist(self) -> Character | None:
        """El protagonista, si está declarado.

        Lo necesita el generador de imágenes: es el personaje que tiene que verse
        idéntico en todas las escenas.
        """
        return next(
            (sc.character for sc in self.characters if sc.role is CharacterRole.PROTAGONIST),
            None,
        )

    @property
    def full_narration(self) -> str:
        """Toda la narración seguida. Es la base del audiolibro y del texto del libro."""
        return "\n\n".join(s.narration for s in self.scenes)

    @property
    def word_count(self) -> int:
        return sum(s.word_count for s in self.scenes)

    def scene_by_beat(self, beat: NarrativeBeat) -> list[Scene]:
        return [s for s in self.scenes if s.beat is beat]

    def outputs_of(self, kind: OutputKind) -> list[Output]:
        return [o for o in self.outputs if o.kind is kind]

    def has_output(self, kind: OutputKind) -> bool:
        return any(o.kind is kind for o in self.outputs)

    # ----------------------------------------------------------------- transiciones
    def advance_to(self, nuevo: StoryStatus) -> None:
        """Mueve la historia a la siguiente etapa, validando que sea posible.

        Sin esto es cuestión de tiempo que algo intente renderizar una historia que
        todavía no tiene audio, y el error aparezca tres capas más abajo.
        """
        actual = self.metadata.status
        if nuevo is actual:
            return
        if nuevo not in ALLOWED_TRANSITIONS[actual]:
            permitidos = sorted(s.value for s in ALLOWED_TRANSITIONS[actual])
            raise InvalidStateTransitionError(
                f"No se puede pasar de '{actual.value}' a '{nuevo.value}'. "
                f"Desde '{actual.value}' solo se puede ir a: {permitidos}."
            )
        self.metadata.status = nuevo
        self.metadata.touch()

    def add_output(self, output: Output) -> None:
        """Registra un artefacto generado."""
        self.outputs.append(output)
        self.metadata.touch()
