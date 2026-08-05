"""El render: de la historia narrada al MP4 vertical.

Junta lo que ya existe —las imágenes y las pistas de audio— y arma el short. Todo
lo que decide acá ya venía decidido: cuánto dura cada escena lo dijo el audio, qué
se ve lo dijo el ilustrador, qué se lee lo dijo el escritor.

**La duración de cada escena la manda el AUDIO, no el plan.** Es la regla que
sostiene todo el módulo: `Scene.real_duration_s` devuelve la duración medida del
audio si existe y la del plan si todavía no se narró. Usar la del plan haría que la
imagen cambie mientras el narrador sigue hablando.

Dos decisiones que salieron de errores del motor viejo:

1. **El audio se concatena re-codificando, nunca con `-c copy`.** Copiar los streams
   es más rápido pero corta el final de cada pista: en los reels viejos los diálogos
   se cortaban justo al pasar de una escena a la siguiente. El tiempo que se ahorra
   no vale un cuento con la voz mochada.
2. **La normalización de volumen va al final, sobre el audio ya armado.** Hacerla por
   tramo deja cada escena con un volumen distinto; y sin normalizar, el audio queda
   en −20 dB y en el feed se escucha flojo al lado de todo lo demás.

FFmpeg se invoca por línea de comandos a propósito: es la única dependencia externa
del motor y no queremos un binding que haya que compilar.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from engine.core.enums import AspectRatio, StoryStatus
from engine.core.exceptions import DomainError
from engine.core.models.story import Story

#: Medidas del short. 1080×1920 es lo que pide YouTube Shorts, Reels y TikTok.
TAMANO: dict[AspectRatio, tuple[int, int]] = {
    AspectRatio.VERTICAL: (1080, 1920),
    AspectRatio.HORIZONTAL: (1920, 1080),
    AspectRatio.SQUARE: (1080, 1080),
    AspectRatio.PORTRAIT: (1080, 1350),
}

#: Volumen de destino. −16 LUFS es el estándar de las plataformas: sin esto el audio
#: sale a −20 dB y en el feed se escucha flojo contra todo lo demás.
LOUDNESS = "loudnorm=I=-16:TP=-1.5:LRA=11"

FPS = 30


class ShortRenderer:
    """Arma el MP4 de una historia ya ilustrada y narrada."""

    def __init__(self, *, aspect: AspectRatio = AspectRatio.VERTICAL, fps: int = FPS) -> None:
        if shutil.which("ffmpeg") is None:
            raise DomainError("Falta ffmpeg: el render lo necesita para armar el video.")
        self._ancho, self._alto = TAMANO[aspect]
        self._fps = fps

    def render(self, story: Story, dest: str | Path) -> Path:
        """Devuelve la ruta del MP4."""
        self._verificar(story)
        salida = Path(dest)
        salida.parent.mkdir(parents=True, exist_ok=True)

        entradas: list[str] = []
        filtros: list[str] = []
        for i, escena in enumerate(story.scenes):
            # `-loop 1 -t dur` convierte una imagen fija en un tramo de video de esa
            # duración exacta. La duración sale del audio medido.
            entradas += ["-loop", "1", "-t", f"{escena.real_duration_s:.3f}",
                         "-i", escena.image_path]
            filtros.append(
                f"[{i}:v]scale={self._ancho}:{self._alto}:force_original_aspect_ratio=increase,"
                f"crop={self._ancho}:{self._alto},setsar=1,fps={self._fps}[v{i}]"
            )

        pistas = [t.path for e in story.scenes for t in e.audio]
        entradas += [x for p in pistas for x in ("-i", p)]

        n = len(story.scenes)
        cadena_v = "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[video]"
        cadena_a = (
            "".join(f"[{n + i}:a]" for i in range(len(pistas)))
            + f"concat=n={len(pistas)}:v=0:a=1[cruda];[cruda]{LOUDNESS}[audio]"
        )
        filtro = ";".join([*filtros, cadena_v, cadena_a])

        subprocess.run(
            ["ffmpeg", "-y", *entradas, "-filter_complex", filtro,
             "-map", "[video]", "-map", "[audio]",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(salida)],
            check=True, capture_output=True,
        )
        if story.status is StoryStatus.NARRATED:
            story.advance_to(StoryStatus.RENDERED)
        story.metadata.touch()
        return salida

    # ------------------------------------------------------------------------
    def _verificar(self, story: Story) -> None:
        """Falla antes de invocar a ffmpeg, con un mensaje que se entiende.

        Un error de ffmpeg son treinta líneas de jerga; esto dice qué falta.
        """
        if not story.scenes:
            raise DomainError("La historia no tiene escenas: no hay nada que renderizar.")
        sin_imagen = [e.index for e in story.scenes if not e.image_path]
        if sin_imagen:
            raise DomainError(f"Las escenas {sin_imagen} no tienen imagen: hay que ilustrarlas.")
        sin_audio = [e.index for e in story.scenes if not e.audio]
        if sin_audio:
            raise DomainError(f"Las escenas {sin_audio} no tienen audio: hay que narrarlas.")
        faltan = [e.image_path for e in story.scenes if not Path(e.image_path).exists()]
        if faltan:
            raise DomainError(f"Faltan archivos de imagen en el disco: {faltan}")
