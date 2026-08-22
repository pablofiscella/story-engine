"""Rearma el MP4 de un cuento ya producido, reemplazando las imágenes fijas por los
clips animados que existan.

    python3 montar_animado.py out/dino_incluir
    python3 montar_animado.py out/dino_incluir --sin 3 5    # deja 3 y 5 como imagen fija

POR QUÉ NO SE VUELVE A GENERAR NADA
───────────────────────────────────
El texto, la voz y las imágenes del cuento ya están pagados y en disco. Animar no cambia
ninguna de las tres: sólo reemplaza el plano fijo de cada escena por su clip. Por eso este
script **no llama a ninguna API** — lee lo que hay en la carpeta y vuelve a montar.

Y por eso se puede animar A MEDIAS. Cada clip entra por su cuenta: si uno sale mal se
rehace ese solo (`animar_cuento.py <carpeta> --solo N`) o se lo deja como imagen fija con
`--sin N`, y las otras siete escenas quedan intactas.

EL `historia.json` NO ALCANZA SOLO
──────────────────────────────────
`producir_cuento.py` lo guarda ANTES de narrar e ilustrar —a propósito: así el texto se
puede leer sin haber gastado en voz ni en imágenes—, así que el archivo no tiene ni las
rutas de las imágenes ni las duraciones del audio. Acá se reconstruyen desde los archivos
que quedaron en `imagenes/` y `audio/`, midiendo cada wav con ffprobe.

**Y la duración medida es la que manda.** Es la regla del render: si se usara la del plan,
la imagen cambiaría mientras el narrador todavía está hablando.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from engine.core.enums import AudioKind, StoryStatus  # noqa: E402
from engine.core.models.audio import AudioTrack  # noqa: E402
from engine.core.models.story import Story  # noqa: E402
from engine.render.video import ShortRenderer  # noqa: E402


def _dur(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)],
                       check=True, capture_output=True, text=True)
    return float(r.stdout.strip())


def _reconstruir(carpeta: Path) -> Story:
    """El Story de la carpeta, con las rutas y las duraciones REALES de los archivos."""
    with open(carpeta / "historia.json", encoding="utf-8") as f:
        story = Story.model_validate(json.load(f))

    for i, escena in enumerate(story.scenes):
        imagen = carpeta / "imagenes" / ("escena_%02d.png" % i)
        if not imagen.is_file():
            raise SystemExit("falta %s" % imagen)
        escena.image_path = str(imagen)

        wav = carpeta / "audio" / ("escena_%02d_narracion.wav" % i)
        if not wav.is_file():
            raise SystemExit("falta %s" % wav)
        escena.audio = [AudioTrack(kind=AudioKind.NARRATION, text=escena.narration,
                                   path=str(wav), duration_s=_dur(wav))]

    # El cierre son dos tramos y en este orden: primero la moraleja, después la pregunta.
    # El render se apoya en eso para decidir cuándo entra el texto de la pregunta.
    cierres = [(story.moral, carpeta / "audio" / "cierre_0.wav"),
               (story.closing_question, carpeta / "audio" / "cierre_1.wav")]
    story.closing_audio = [
        AudioTrack(kind=AudioKind.NARRATION, text=texto, path=str(w), duration_s=_dur(w))
        for texto, w in cierres if w.is_file()
    ]
    if not story.closing_audio:
        raise SystemExit("no hay audio de cierre en %s/audio" % carpeta)

    # El estado se toca por la puerta de atrás a propósito. `advance_to()` sólo acepta
    # las transiciones legales, y este Story viene de un JSON guardado ANTES de narrar:
    # no hay camino legal desde ahí hasta NARRATED sin volver a llamar al motor —que es
    # exactamente lo que no queremos, porque la voz ya está pagada y en disco.
    story.metadata.status = StoryStatus.NARRATED
    return story


def main() -> int:
    ap = argparse.ArgumentParser(description="Rearma el MP4 con los clips animados.")
    ap.add_argument("carpeta")
    ap.add_argument("--sin", type=int, nargs="*", default=[],
                    help="escenas que quedan como imagen fija aunque tengan clip")
    ap.add_argument("--salida", default=None)
    a = ap.parse_args()

    carpeta = Path(a.carpeta)
    if not carpeta.is_dir():
        carpeta = RAIZ / a.carpeta
    story = _reconstruir(carpeta)

    clips = {}
    for i in range(len(story.scenes)):
        clip = carpeta / "animado" / ("clip_%02d.mp4" % i)
        if clip.is_file() and clip.stat().st_size > 10_000 and i not in a.sin:
            clips[i] = clip
    if not clips:
        raise SystemExit("no hay clips en %s/animado: primero animar_cuento.py" % carpeta)

    fijas = [i for i in range(len(story.scenes)) if i not in clips]
    print("«%s»" % story.metadata.title)
    print("  %d escenas animadas%s" % (len(clips),
          (" · quedan fijas: %s" % ", ".join(str(i + 1) for i in fijas)) if fijas else ""))

    salida = Path(a.salida) if a.salida else carpeta / ("%s_animado.mp4" % carpeta.name)
    mp4 = ShortRenderer(clips=clips).render(story, salida)
    print("  ✔ %s  (%.1fs)" % (mp4, _dur(mp4)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
