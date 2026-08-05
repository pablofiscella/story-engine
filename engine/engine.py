"""La fachada: `StoryEngine`.

Es la única clase que necesita conocer quien usa el motor. Adentro orquesta las
piezas —planificador, escritor, y más adelante ilustrador, narrador y render— pero
hacia afuera muestra una sola operación clara.

    engine = StoryEngine(text_provider=OpenAIProvider(key))
    story = await engine.generate(theme=tema, style=estilo, value="compartir",
                                  age=4, duration_s=30, characters=[dino, rexo])

Todo lo que devuelve es un `Story` válido: si algo no cerró, no llega a existir.
"""

from __future__ import annotations

from engine.core.enums import (
    AgeRange,
    CharacterRole,
    EducationalValue,
    Language,
    StoryStatus,
)
from engine.core.interfaces import TextProvider
from engine.core.models.character import Character
from engine.core.models.metadata import StoryMetadata
from engine.core.models.story import Story, StoryCharacter
from engine.core.models.style import Style
from engine.core.models.theme import Theme
from engine.generators.planner import StoryPlanner
from engine.generators.values import profile_for
from engine.generators.writer import StoryWriter


class StoryEngine:
    """Arma historias completas a partir de una intención."""

    def __init__(self, *, text_provider: TextProvider | None = None) -> None:
        self._planner = StoryPlanner()
        self._writer = StoryWriter(text_provider) if text_provider is not None else None

    def plan(
        self,
        *,
        theme: Theme,
        style: Style,
        value: EducationalValue | str,
        age: int | AgeRange,
        duration_s: float,
        characters: list[Character],
        language: Language = Language.ES_AR,
        title: str = "",
    ) -> Story:
        """La historia planificada, sin una palabra escrita todavía.

        Es un paso público a propósito: el plan se puede revisar (y corregir) antes de
        gastar en texto, imágenes o audio. Ahí es donde sale más barato encontrar que
        una historia no cierra.
        """
        valor = EducationalValue(value) if isinstance(value, str) else value
        franja = age if isinstance(age, AgeRange) else AgeRange.from_age(age)
        if not characters:
            raise ValueError("Una historia necesita al menos un personaje.")

        protagonista, *resto = characters
        companero = resto[0] if resto else None
        perfil = profile_for(valor)

        plan = self._planner.create_plan(
            theme=theme,
            value=valor,
            age_range=franja,
            duration_s=duration_s,
            protagonist=protagonista,
            companion=companero,
        )

        elenco = [StoryCharacter(character=protagonista, role=CharacterRole.PROTAGONIST)]
        elenco += [
            StoryCharacter(
                character=c,
                role=CharacterRole.COMPANION if i == 0 else CharacterRole.EXTRA,
            )
            for i, c in enumerate(resto)
        ]

        story = Story(
            metadata=StoryMetadata(
                title=title,
                language=language,
                age_range=franja,
                target_duration_s=duration_s,
            ),
            theme=theme,
            style=style,
            value=valor,
            characters=elenco,
            moral=perfil.moral,
            closing_question=perfil.question,
            plan=plan,
        )
        story.advance_to(StoryStatus.PLANNED)
        return story

    async def generate(
        self,
        *,
        theme: Theme,
        style: Style,
        value: EducationalValue | str,
        age: int | AgeRange,
        duration_s: float,
        characters: list[Character],
        language: Language = Language.ES_AR,
        title: str = "",
    ) -> Story:
        """Planifica y escribe. Devuelve la historia lista para ilustrar y narrar."""
        if self._writer is None:
            raise RuntimeError(
                "Este motor no tiene proveedor de texto: solo puede planificar. "
                "Pasale un `text_provider` para poder escribir."
            )
        story = self.plan(
            theme=theme,
            style=style,
            value=value,
            age=age,
            duration_s=duration_s,
            characters=characters,
            language=language,
            title=title,
        )
        return await self._writer.write(story)
