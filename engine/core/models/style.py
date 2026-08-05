"""Estilo visual: CÓMO se dibuja la historia.

Eje independiente del tema, igual que formato y canal.

- `Theme`  → QUÉ mundo (dinosaurios, espacio, princesas)
- `Style`  → CÓMO se ve (Pixar 3D, plano 2D, palitos, acuarela)

Separarlos es lo que permite que el MISMO cuento salga como corto 3D para YouTube y
como librito de palitos para imprimir, sin reescribir una palabra. Y que sumar un
estilo nuevo sea un archivo en `assets/styles/`, nunca un deploy.

Si estuvieran pegados (el estilo adentro del tema), cada combinación tema×estilo
obligaría a duplicar el tema entero: "dinosaurios-3d", "dinosaurios-palitos"...
"""

from __future__ import annotations

from pydantic import Field

from engine.core.models.base import EngineModel, Slug


class Style(EngineModel):
    """Un estilo gráfico reutilizable entre temas e historias.

    Vive en `assets/styles/<id>.json`. El panel lo ofrece como opción: elegís tema,
    valor, edad… y estilo.
    """

    id: Slug
    name: str = Field(min_length=1, max_length=60, description="Cómo se llama en el panel.")
    description: str = Field(default="", description="Para qué sirve, en una línea.")

    art_style: str = Field(
        min_length=3,
        description=(
            "El corazón del prompt de imagen: 'animación 3D estilo Pixar', "
            "'ilustración plana 2D vectorial', 'dibujo de palitos infantil'."
        ),
    )
    lighting: str = Field(
        default="", description="'luz cálida y difusa', 'iluminación cinematográfica'."
    )
    color_treatment: str = Field(
        default="", description="'colores saturados', 'pastel suave', 'blanco y negro'."
    )
    detail_level: str = Field(
        default="", description="'muy detallado', 'formas simples y limpias'."
    )

    negative_prompt: str = Field(
        default="",
        description=(
            "Qué NO queremos ver. Vale tanto como el prompt positivo: es lo que saca "
            "texto pegado, manos deformes y realismo cuando pedimos dibujo."
        ),
    )
    reference_image: str | None = Field(
        default=None,
        description=(
            "Imagen ancla del estilo. Se le pasa al generador junto con el prompt para "
            "que todas las escenas se vean de la misma familia."
        ),
    )

    def prompt_fragment(self) -> str:
        """Fragmento de estilo para inyectar en el prompt de imagen.

        Determinista: el mismo estilo produce siempre exactamente el mismo texto. Esa
        estabilidad es la mitad de la consistencia visual (la otra mitad es el
        personaje, ver `Appearance.prompt_fragment`).
        """
        partes = [self.art_style, self.lighting, self.color_treatment, self.detail_level]
        return ", ".join(p.strip() for p in partes if p and p.strip())
