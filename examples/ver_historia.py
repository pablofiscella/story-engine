"""Demo: construye una historia con el core y la muestra como un guion legible.

El core todavía no genera nada con IA — esto arma la historia a mano para que se vea
QUÉ puede representar el modelo de dominio. Es el mismo short del storyboard de
referencia, pero además lo muestra en dos estilos distintos para dejar ver que el
contenido y el dibujo son ejes separados.

    python examples/ver_historia.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.core.enums import OutputKind, StoryStatus  # noqa: E402
from engine.core.models import Story, Style  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from test_referencia_storyboard import _construir_short  # noqa: E402

VERDE, AMARILLO, GRIS, CIAN, RESET, NEGRITA = (
    "\033[32m", "\033[33m", "\033[90m", "\033[36m", "\033[0m", "\033[1m",
)


def linea(char: str = "─", n: int = 78) -> str:
    return GRIS + char * n + RESET


def mostrar(story: Story) -> None:
    print()
    print(linea("═"))
    print(f"{NEGRITA}{story.metadata.title}{RESET}")
    print(
        f"{GRIS}{story.theme.name} · {story.value.value} · "
        f"{story.metadata.age_range.value} años · {story.duration_s:.0f}s · "
        f"estilo: {story.style.name}{RESET}"
    )
    print(linea("═"))

    for esc in story.scenes:
        inicio = sum(s.duration_s for s in story.scenes[: esc.index])
        fin = inicio + esc.duration_s
        print(
            f"\n{CIAN}{inicio:>5.0f}s – {fin:<4.0f}s{RESET}  "
            f"{AMARILLO}[{esc.beat.value}]{RESET}  "
            f"{GRIS}{esc.location} · {esc.emotion.value} · "
            f"{esc.camera.shot.value}/{esc.camera.movement.value}{RESET}"
        )
        print(f"   {GRIS}objetivo:{RESET} {esc.purpose}")
        print(f"   {VERDE}🎙️  {esc.narration}{RESET}")
        for d in esc.dialogue:
            marca = "💬" if not d.spoken else "🗣️"
            quien = story.characters_by_id[d.character_id].name
            nota = f" {GRIS}(solo en pantalla){RESET}" if not d.spoken else ""
            print(f"   {marca} {quien}: “{d.text}”{nota}")
        if esc.emphasis:
            print(f"   {GRIS}resaltado:{RESET} {', '.join(esc.emphasis)}")
        if esc.sfx:
            print(f"   {GRIS}sonido:{RESET} {', '.join(esc.sfx)}")
        print(
            f"   {GRIS}palabras: {esc.word_count}/{esc.max_words} · "
            f"habla ~{esc.estimated_speech_duration_s}s{RESET}"
        )

    print(f"\n{linea()}")
    print(f"{NEGRITA}Idea principal:{RESET} {story.moral}")
    print(f"{NEGRITA}Cierre:{RESET} {story.closing_question}")
    print(f"{GRIS}Total: {story.word_count} palabras en {story.duration_s:.0f}s{RESET}")


def mostrar_prompt_de_imagen(story: Story) -> None:
    """Lo que recibiría el generador de imágenes para la primera escena."""
    esc = story.scenes[0]
    prota = story.protagonist
    assert prota is not None
    print(f"\n{linea()}")
    print(f"{NEGRITA}Prompt de imagen — escena 1 (estilo: {story.style.name}){RESET}\n")
    print(f"{GRIS}estilo:{RESET}     {story.style.prompt_fragment()}")
    print(f"{GRIS}personaje:{RESET}  {prota.appearance.prompt_fragment()}")
    print(f"{GRIS}escena:{RESET}     {esc.purpose} — en {esc.location}")
    print(f"{GRIS}expresión:{RESET}  {prota.expression_for(esc.emotion)}")
    print(f"{GRIS}evitar:{RESET}     {story.style.negative_prompt}")


def main() -> None:
    story = _construir_short()
    mostrar(story)
    mostrar_prompt_de_imagen(story)

    # El mismo cuento, otro estilo: cambia el dibujo, no el texto.
    palitos = Style(
        id="palitos",
        name="Personajes palito",
        art_style="dibujo de palitos infantil, trazo negro simple sobre fondo blanco",
        detail_level="trazo mínimo",
        negative_prompt="color, sombreado, detalle, 3D",
    )
    mostrar_prompt_de_imagen(story.model_copy(update={"style": palitos}))

    # De una historia salen todos los formatos.
    print(f"\n{linea()}")
    print(f"{NEGRITA}Formatos que puede producir esta misma historia{RESET}\n")
    for kind in OutputKind:
        print(f"   {GRIS}·{RESET} {kind.value}")
    print(f"\n{GRIS}estado actual: {story.status.value}{RESET}")
    assert story.status is StoryStatus.DRAFT
    print()


if __name__ == "__main__":
    main()
