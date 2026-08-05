"""El ilustrador: dibuja cada escena, manteniendo al personaje igual.

El problema que resuelve es EL problema de los cuentos ilustrados con IA. Si cada
escena se genera sola, el modelo dibuja un protagonista distinto cada vez: cambia el
color del pijama entre la página 2 y la 3, la nena de colitas aparece con otro peinado,
el elenco se multiplica. Pasa siempre, y no se arregla pidiéndole mejor al modelo.

Se arregla con **anclas encadenadas**: la primera imagen donde aparece un personaje se
guarda como su referencia, y todas las escenas siguientes donde vuelve a aparecer se
generan pasándole esa imagen. El modelo ya no tiene que imaginarse cómo era — lo está
viendo.

Dos anclas, no una:

- **protagonista** — la primera escena donde está. Es quien más aparece y quien más
  se nota si cambia.
- **elenco** — la primera escena con los secundarios, para que tampoco muten.

Más el ancla de ESTILO del tema, que va siempre y en primer lugar.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from engine.core.enums import CharacterRole, StoryStatus
from engine.core.exceptions import DomainError, ProviderError
from engine.core.interfaces import ImageProvider
from engine.core.models.story import Story
from engine.prompts import image as image_prompts

#: Cuántas escenas se ilustran a la vez. Bajo a propósito: las anclas se construyen
#: con las primeras imágenes, así que hay un orden que respetar. Solo se paraleliza
#: DESPUÉS de tener las referencias.
CONCURRENCIA = 3


class SceneIllustrator:
    """Ilustra las escenas de una historia con consistencia entre ellas."""

    def __init__(self, provider: ImageProvider, *, width: int = 1024, height: int = 1536) -> None:
        self._provider = provider
        self._width = width
        self._height = height

    async def illustrate(self, story: Story, dest_dir: str | Path) -> Story:
        """Genera la ilustración de cada escena y deja la historia en ILLUSTRATED.

        El orden importa: primero se generan, en serie, las escenas que fijan las
        anclas; el resto puede ir en paralelo porque ya tiene de dónde copiar.
        """
        if not story.scenes:
            raise DomainError(
                "La historia no tiene escenas: hay que escribirla antes de ilustrarla."
            )

        destino = Path(dest_dir)
        destino.mkdir(parents=True, exist_ok=True)

        estilo_ref = _leer(story.style.reference_image)
        anclas: dict[str, bytes] = {}
        negativo = image_prompts.negative(story.style)

        fijan_ancla, resto = self._separar(story)

        # --- 1) en serie: las escenas que construyen las anclas --------------------
        for escena in fijan_ancla:
            img = await self._generar(escena, estilo_ref, anclas, negativo)
            _guardar(img, destino, escena, story)
            for cid in escena.character_ids:
                anclas.setdefault(cid, img)

        # --- 2) en paralelo: el resto ya tiene a quién parecerse -------------------
        limite = asyncio.Semaphore(CONCURRENCIA)

        async def _una(escena):
            async with limite:
                img = await self._generar(escena, estilo_ref, anclas, negativo)
                _guardar(img, destino, escena, story)

        if resto:
            await asyncio.gather(*(_una(e) for e in resto))

        if story.status is StoryStatus.WRITTEN:
            story.advance_to(StoryStatus.ILLUSTRATED)
        story.metadata.touch()
        return story

    # ------------------------------------------------------------------------
    def _separar(self, story: Story):
        """Qué escenas hay que generar primero para tener las anclas.

        Son la primera aparición de cada personaje. Con protagonista + compañero
        suelen ser dos; el resto de las escenas ya puede ir en paralelo.
        """
        vistos: set[str] = set()
        fijan, resto = [], []
        for escena in story.scenes:
            nuevos = [c for c in escena.character_ids if c not in vistos]
            if nuevos:
                vistos.update(nuevos)
                fijan.append(escena)
            else:
                resto.append(escena)
        return fijan, resto

    async def _generar(
        self, escena, estilo_ref: bytes | None, anclas: dict[str, bytes], negativo: str
    ) -> bytes:
        """Una ilustración, con las referencias que correspondan.

        El orden de las referencias no es casual: primero el estilo (marca el "cómo se
        dibuja"), después los personajes (marcan el "quién es").
        """
        refs: list[bytes] = []
        if estilo_ref:
            refs.append(estilo_ref)
        # también los imaginados: si Rexo aparece en una burbuja, necesita su ancla
        # igual que si estuviera parado en la escena.
        for cid in list(escena.character_ids) + list(escena.imagined_character_ids):
            if cid in anclas and anclas[cid] not in refs:
                refs.append(anclas[cid])

        prompt = escena.image_prompt or ""
        if not prompt:
            raise DomainError(
                f"La escena {escena.index} no tiene prompt de imagen: la compone el escritor."
            )
        if negativo:
            prompt = f"{prompt} EVITAR: {negativo}"

        img = await self._provider.generate_image(
            prompt,
            reference_images=refs or None,
            width=self._width,
            height=self._height,
        )
        if not img:
            raise ProviderError(
                f"El ilustrador devolvió una imagen vacía en la escena {escena.index}."
            )
        return img


# --------------------------------------------------------------------------- utils
def _leer(ruta: str | None) -> bytes | None:
    """La imagen de referencia del estilo, si el tema tiene una.

    Que falte no puede frenar la generación: se pierde el ancla de estilo, no la
    historia.
    """
    if not ruta:
        return None
    p = Path(ruta)
    return p.read_bytes() if p.is_file() else None


def _guardar(img: bytes, destino: Path, escena, story: Story) -> None:
    archivo = destino / f"escena_{escena.index:02d}.png"
    archivo.write_bytes(img)
    escena.image_path = str(archivo)


def anchor_of(story: Story) -> str | None:
    """El id del personaje cuya consistencia más importa.

    Lo usa el QA: si hay que revisar UNA cosa en las ilustraciones, es que el
    protagonista se vea igual en todas.
    """
    prota = next(
        (sc.character.id for sc in story.characters if sc.role is CharacterRole.PROTAGONIST),
        None,
    )
    return prota
