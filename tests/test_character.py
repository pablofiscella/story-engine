"""Personajes y temas: la base de la consistencia visual."""

from __future__ import annotations

import pytest

from engine.core.enums import AgeRange, Emotion
from engine.core.models import Appearance, Character, Palette, Style, Theme

# --- personaje -------------------------------------------------------------------


def test_prompt_fragment_es_estable(dino: Character) -> None:
    """La MISMA descripción, siempre. Es lo que evita que el personaje mute entre
    escenas cuando cada imagen se genera por separado."""
    assert dino.appearance.prompt_fragment() == dino.appearance.prompt_fragment()


def test_prompt_fragment_incluye_todo_lo_identificatorio(dino: Character) -> None:
    frag = dino.appearance.prompt_fragment()
    assert "dinosaurio T-Rex bebé" in frag
    assert "verde menta" in frag
    assert "hoja siempre pegada en la cola" in frag


def test_expresion_conocida(dino: Character) -> None:
    assert dino.expression_for(Emotion.CURIOSITY) == "cabeza ladeada y ojos bien abiertos"


def test_expresion_faltante_no_rompe(dino: Character) -> None:
    """Una expresión sin definir no puede frenar una historia entera."""
    assert dino.expression_for(Emotion.PRIDE) == "expresión de orgullo"


def test_el_id_debe_ser_un_slug() -> None:
    with pytest.raises(ValueError):
        Character(
            id="Dino Rex!",  # espacios y símbolos no
            name="Dino",
            appearance=Appearance(species="dino", description="un dinosaurio verde"),
        )


def test_descripcion_muy_corta_es_rechazada() -> None:
    """Una descripción pobre produce imágenes inconsistentes."""
    with pytest.raises(ValueError):
        Appearance(species="dino", description="verde")


# --- tema ------------------------------------------------------------------------


def test_paleta_normaliza_a_mayusculas() -> None:
    p = Palette(primary="#2e7d32", secondary="#ffb300", accent="#d84315")
    assert p.primary == "#2E7D32"


def test_paleta_rechaza_color_invalido() -> None:
    with pytest.raises(ValueError):
        Palette(primary="verde", secondary="#FFB300", accent="#D84315")


def test_estilo_baja_al_prompt(estilo_3d: Style) -> None:
    frag = estilo_3d.prompt_fragment()
    assert "estilo Pixar" in frag
    assert "luz cálida" in frag


def test_el_tema_solo_sugiere_un_estilo(tema_dinos: Theme) -> None:
    """El tema propone, la historia dispone: el estilo no vive adentro del tema."""
    assert tema_dinos.default_style_id == "pixar-3d"
    assert not hasattr(tema_dinos, "style")


def test_locations_limpia_vacios() -> None:
    t = Theme(
        id="selva",
        name="Selva",
        palette=Palette(primary="#0B6", secondary="#FA0", accent="#D41"),
        locations=["el río", "   ", "", "la copa de los árboles"],
    )
    assert t.locations == ["el río", "la copa de los árboles"]


# --- franjas etarias -------------------------------------------------------------


@pytest.mark.parametrize(
    ("edad", "esperado"),
    [
        (1, AgeRange.TODDLER),
        (3, AgeRange.TODDLER),
        (4, AgeRange.PRESCHOOL),
        (5, AgeRange.PRESCHOOL),
        (7, AgeRange.EARLY),
        (9, AgeRange.KID),
        (12, AgeRange.KID),
    ],
)
def test_from_age(edad: int, esperado: AgeRange) -> None:
    """La API recibe `age=4`; el motor razona en franjas."""
    assert AgeRange.from_age(edad) is esperado


def test_bounds() -> None:
    assert AgeRange.PRESCHOOL.bounds == (3, 5)
