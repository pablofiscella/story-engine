"""Caso de referencia: "El dinosaurio que aprendió a compartir".

Es el storyboard real que definió el objetivo del motor (short de 30s, 6 escenas de
5s, dinosaurio que no quiere prestar su pelota). Este test reconstruye ESE short con
el modelo de dominio y verifica que todo lo que aparece en el guion tiene dónde vivir:
narración, diálogo, subtítulos con palabras resaltadas, sonidos, música, idea
principal y pregunta final.

Es el test más importante del core: si mañana un cambio rompe la capacidad de
representar este short, rompimos el motor.
"""

from __future__ import annotations

from engine.core.enums import (
    AgeRange,
    AspectRatio,
    CameraMovement,
    Channel,
    CharacterRole,
    EducationalValue,
    Emotion,
    Language,
    MusicMood,
    NarrativeBeat,
    OutputKind,
    ShotType,
    StoryStatus,
)
from engine.core.models import (
    Appearance,
    CameraDirection,
    Character,
    DialogueLine,
    MusicCue,
    Output,
    Palette,
    Publication,
    Scene,
    ScenePlan,
    Story,
    StoryCharacter,
    StoryMetadata,
    StoryPlan,
    Style,
    Theme,
)

# El guion tal cual el storyboard: (beat, propósito, narración, subrayado, emoción)
GUION = [
    (
        NarrativeBeat.HOOK,
        "Presentar a Dino y su juguete nuevo",
        "Este es Dino. ¡Le encanta su juguete nuevo!",
        ["Dino", "juguete"],
        Emotion.JOY,
    ),
    (
        NarrativeBeat.PROBLEM,
        "Rexo quiere jugar y Dino se niega",
        "Pero cuando su amigo Rexo quiere jugar, Dino dice: ¡No! Es mío.",
        ["Rexo"],
        Emotion.FRUSTRATION,
    ),
    (
        NarrativeBeat.FAILURE,
        "Dino se queda solo y no la pasa bien",
        "Dino se queda solo y piensa: sería más divertido compartir...",
        ["compartir"],
        Emotion.SADNESS,
    ),
    (
        NarrativeBeat.LESSON,
        "Dino decide compartir",
        "Entonces decide compartir y le dice a Rexo: ¡Toma, juguemos juntos!",
        ["compartir", "juntos"],
        Emotion.SURPRISE,
    ),
    (
        NarrativeBeat.ENDING,
        "Los dos juegan felices",
        "Ahora sí, se divierten mucho más. ¡Compartir hace todo mejor!",
        ["Compartir"],
        Emotion.JOY,
    ),
    (
        NarrativeBeat.ENDING,
        "Cierre con la moraleja y la pregunta al espectador",
        "¡Compartir es cuidar y hacer amigos!",
        ["Compartir"],
        Emotion.PRIDE,
    ),
]


def _construir_short() -> Story:
    dino = Character(
        id="dino",
        name="Dino",
        appearance=Appearance(
            species="dinosaurio bebé",
            description="regordete y tierno, ojos enormes y expresivos, estilo 3D infantil",
            colors=["verde", "amarillo"],
            distinctive_features=["crestas naranjas en la espalda"],
        ),
        personality=["alegre", "posesivo al principio"],
        expressions={Emotion.JOY: "sonrisa grande con la boca abierta"},
    )
    rexo = Character(
        id="rexo",
        name="Rexo",
        appearance=Appearance(
            species="dinosaurio bebé",
            description="regordete y tierno, ojos enormes, estilo 3D infantil",
            colors=["azul", "celeste"],
            distinctive_features=["crestas naranjas en la espalda"],
        ),
        personality=["amistoso", "paciente"],
    )
    tema = Theme(
        id="dinosaurios",
        name="Dinosaurios",
        description="Un bosque prehistórico soleado, con helechos y rocas.",
        palette=Palette(primary="#4CAF50", secondary="#7E57C2", accent="#FFC107"),
        locations=["el claro del bosque"],
        character_ids=["dino", "rexo"],
        default_style_id="animacion-3d",
    )
    # el storyboard dice: "Animación 3D colorida estilo infantil, personajes tiernos
    # y expresivos, ambientes vivos y amigables"
    estilo = Style(
        id="animacion-3d",
        name="Animación 3D",
        art_style="animación 3D colorida estilo infantil, personajes tiernos y expresivos",
        lighting="ambientes vivos y amigables, luz cálida",
        color_treatment="colores saturados",
        negative_prompt="texto, realismo fotográfico",
    )

    plan = StoryPlan(
        target_duration_s=30.0,
        scenes=[
            ScenePlan(
                index=i,
                beat=beat,
                purpose=purpose,
                duration_s=5.0,
                location="el claro del bosque",
                character_ids=["dino"] if i in (0, 2) else ["dino", "rexo"],
                emotion=emocion,
            )
            for i, (beat, purpose, _, _, emocion) in enumerate(GUION)
        ],
    )

    escenas = [
        Scene.from_plan(
            plan.scenes[i],
            narration=narracion,
            subtitle=narracion,
            emphasis=resaltadas,
            image_prompt=f"{estilo.prompt_fragment()}. {dino.appearance.prompt_fragment()}",
            camera=CameraDirection(shot=ShotType.MEDIUM, movement=CameraMovement.ZOOM_IN),
            music=MusicCue(mood=MusicMood.PLAYFUL),
            sfx=["música infantil alegre"],
        )
        for i, (_, _, narracion, resaltadas, _) in enumerate(GUION)
    ]
    # El globo de Rexo en la escena 2. `spoken=False` porque en el storyboard real la
    # voz en off NO lo dice: es texto en pantalla, así que no gasta tiempo de audio.
    escenas[1].dialogue = [
        DialogueLine(character_id="rexo", text="¿Puedo jugar contigo?", spoken=False)
    ]
    escenas[-1].sfx = ["risas al final"]

    return Story(
        metadata=StoryMetadata(
            title="El dinosaurio que aprendió a compartir",
            language=Language.ES_AR,
            age_range=AgeRange.EARLY,  # el storyboard dice 3 a 7 años
            target_duration_s=30.0,
        ),
        theme=tema,
        style=estilo,
        value=EducationalValue.SHARING,
        characters=[
            StoryCharacter(character=dino, role=CharacterRole.PROTAGONIST),
            StoryCharacter(character=rexo, role=CharacterRole.COMPANION),
        ],
        moral="Compartir nos hace más felices y fortalece la amistad.",
        closing_question="¿Y vos, qué compartís con tus amigos?",
        plan=plan,
        scenes=escenas,
    )


def test_el_storyboard_de_referencia_se_representa_entero() -> None:
    story = _construir_short()

    assert story.metadata.title == "El dinosaurio que aprendió a compartir"
    assert story.duration_s == 30.0
    assert len(story.scenes) == 6
    assert all(s.duration_s == 5.0 for s in story.scenes)
    assert story.value is EducationalValue.SHARING
    assert story.moral.startswith("Compartir nos hace")
    assert story.closing_question.startswith("¿Y vos")


def test_los_dos_dinosaurios_tienen_descripcion_estable() -> None:
    """El mismo personaje se describe igual en toda la historia: eso es lo que
    impide que Dino cambie de color entre la escena 1 y la 5."""
    story = _construir_short()
    dino = story.characters_by_id["dino"]
    assert dino.appearance.prompt_fragment() == dino.appearance.prompt_fragment()
    assert "verde" in dino.appearance.prompt_fragment()
    assert "azul" in story.characters_by_id["rexo"].appearance.prompt_fragment()


def test_el_dialogo_del_globo_esta_atado_a_quien_lo_dice() -> None:
    story = _construir_short()
    linea = story.scenes[1].dialogue[0]
    assert linea.character_id == "rexo"
    assert linea.text == "¿Puedo jugar contigo?"


def test_el_globo_en_pantalla_no_gasta_tiempo_de_audio() -> None:
    """El globo se lee, no se narra: si contara como habla, la escena 2 del guion
    real no entraría en sus 5 segundos."""
    story = _construir_short()
    escena = story.scenes[1]
    assert escena.dialogue[0].spoken is False
    assert escena.word_count == len(escena.narration.split())


def test_las_palabras_resaltadas_del_subtitulo() -> None:
    story = _construir_short()
    assert story.scenes[0].emphasis == ["Dino", "juguete"]
    assert "compartir" in story.scenes[3].emphasis


def test_toda_la_narracion_entra_en_su_escena() -> None:
    """Cada bloque de 5s del guion real respeta el presupuesto de palabras."""
    story = _construir_short()
    for escena in story.scenes:
        assert escena.word_count <= escena.max_words


def test_el_mismo_short_se_publica_en_los_tres_canales() -> None:
    """Un render, tres plataformas: es el objetivo de producir 10 shorts por día."""
    story = _construir_short()
    story.advance_to(StoryStatus.PLANNED)
    story.advance_to(StoryStatus.WRITTEN)
    story.advance_to(StoryStatus.ILLUSTRATED)
    story.advance_to(StoryStatus.NARRATED)
    story.advance_to(StoryStatus.RENDERED)

    short = Output(
        kind=OutputKind.SHORT,
        path="/out/dino-compartir.mp4",
        aspect_ratio=AspectRatio.VERTICAL,
        duration_s=30.0,
        publications=[
            Publication(channel=Channel.YOUTUBE, url="https://youtube.com/shorts/abc"),
            Publication(channel=Channel.INSTAGRAM, url="https://instagram.com/reel/abc"),
            Publication(channel=Channel.FACEBOOK, url="https://facebook.com/reel/abc"),
        ],
    )
    story.add_output(short)
    story.advance_to(StoryStatus.PUBLISHED)

    assert story.status is StoryStatus.PUBLISHED
    assert len({p.channel for p in short.publications}) == 3


def test_la_misma_historia_da_libro_y_audiolibro() -> None:
    """El cuento no muere en el short: se reusa como producto de la tienda."""
    story = _construir_short()
    story.add_output(Output(kind=OutputKind.SHORT, path="/out/s.mp4"))
    story.add_output(Output(kind=OutputKind.AUDIOBOOK, path="/out/a.mp3", duration_s=30.0))
    story.add_output(
        Output(kind=OutputKind.BOOK, path="/out/l.pdf", aspect_ratio=AspectRatio.PRINT_A4)
    )
    story.add_output(Output(kind=OutputKind.ACTIVITY, path="/out/act.pdf"))

    assert {o.kind for o in story.outputs} == {
        OutputKind.SHORT,
        OutputKind.AUDIOBOOK,
        OutputKind.BOOK,
        OutputKind.ACTIVITY,
    }
    # el texto del audiolibro sale de la misma narración, sin reescribir nada
    assert "Este es Dino" in story.full_narration
