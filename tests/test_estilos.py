"""Estilo como eje independiente.

El mismo cuento, dibujado distinto, sin reescribir una palabra: 3D estilo Pixar para
YouTube, palitos 2D para un imprimible, acuarela para un libro. Es lo que permite que
el panel ofrezca "elegí tema, valor, edad Y estilo" y salga un video adaptado.
"""

from __future__ import annotations

from engine.core.enums import EducationalValue
from engine.core.models import Story, StoryPlan, Style, Theme

PRESETS = [
    Style(
        id="pixar-3d",
        name="Animación 3D",
        description="Tierno y expresivo, como una película de estudio.",
        art_style="animación 3D colorida estilo Pixar, personajes tiernos y expresivos",
        lighting="luz cálida cinematográfica",
        color_treatment="colores saturados",
        negative_prompt="texto, realismo fotográfico, terror",
    ),
    Style(
        id="plano-2d",
        name="Plano 2D",
        description="Vectorial y limpio, ideal para imprimibles.",
        art_style="ilustración plana 2D vectorial, formas simples",
        color_treatment="colores planos sin degradé",
        detail_level="formas simples y limpias",
        negative_prompt="sombras realistas, texturas, 3D",
    ),
    Style(
        id="palitos",
        name="Personajes palito",
        description="Dibujo de trazo mínimo, como el de un chico.",
        art_style="dibujo de palitos infantil, trazo negro simple sobre fondo blanco",
        detail_level="trazo mínimo",
        negative_prompt="color, sombreado, detalle, 3D",
    ),
    Style(
        id="acuarela",
        name="Acuarela",
        description="Suave y artesanal, para libros ilustrados.",
        art_style="ilustración infantil en acuarela, trazo suave",
        color_treatment="pastel suave",
        lighting="luz difusa",
        negative_prompt="líneas duras, vectorial, 3D",
    ),
]


def test_cada_preset_produce_un_prompt_distinto() -> None:
    fragmentos = [s.prompt_fragment() for s in PRESETS]
    assert len(set(fragmentos)) == len(PRESETS)
    assert "Pixar" in fragmentos[0]
    assert "palitos" in fragmentos[2]


def test_el_prompt_de_estilo_es_determinista() -> None:
    """El mismo estilo da siempre exactamente el mismo texto: sin eso, dos escenas
    del mismo cuento salen con look distinto."""
    estilo = PRESETS[0]
    assert estilo.prompt_fragment() == estilo.prompt_fragment()


def test_la_misma_historia_en_cuatro_estilos(
    historia: Story, tema_dinos: Theme, plan_valido: StoryPlan
) -> None:
    """El contenido no cambia: cambia solo cómo se dibuja."""
    versiones = [historia.model_copy(update={"style": preset}) for preset in PRESETS]

    # el cuento es el mismo en las cuatro
    assert all(v.value is EducationalValue.SHARING for v in versiones)
    assert all(v.duration_s == historia.duration_s for v in versiones)
    assert all(v.plan == historia.plan for v in versiones)

    # lo único distinto es el prompt de imagen
    assert len({v.style.prompt_fragment() for v in versiones}) == 4


def test_el_negative_prompt_viaja_con_el_estilo() -> None:
    """Lo que NO queremos ver es parte del estilo, no del tema: en palitos molesta
    el color, en 3D molesta el realismo fotográfico."""
    palitos = next(s for s in PRESETS if s.id == "palitos")
    pixar = next(s for s in PRESETS if s.id == "pixar-3d")
    assert "color" in palitos.negative_prompt
    assert "realismo fotográfico" in pixar.negative_prompt


def test_el_tema_sugiere_pero_la_historia_decide(historia: Story) -> None:
    """El tema trae un estilo por default; la historia puede pisarlo."""
    assert historia.theme.default_style_id == "pixar-3d"
    otra = historia.model_copy(update={"style": PRESETS[2]})  # palitos
    assert otra.theme.default_style_id == "pixar-3d"  # el tema no cambió
    assert otra.style.id == "palitos"  # la historia sí
