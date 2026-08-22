"""Anima un cuento ya producido: un clip de video por escena, con Wan 2.2 en HF.

    python3 animar_cuento.py out/dino_incluir --solo 0     # una escena, para mirarla
    python3 animar_cuento.py out/dino_incluir              # las ocho

POR QUÉ ASÍ Y NO COMO LA PRIMERA VEZ
────────────────────────────────────
21-ago-2026. El primer motor de animación (`animar_hf.py`) encadenaba clips desde el
último cuadro del anterior para cubrir escenas de 8 a 11 s, y a partir del segundo clip
los personajes se deformaban, se iban del cuadro o aparecían dinosaurios que nadie pidió.
Pablo lo cortó: *"Esta es la 2da vez y en las dos salió cualquier cosa"*.

Lo que sí funcionó fue el video de Ushuaia, animado con otra IA. La diferencia no era el
modelo: era el largo. **Un clip de 5 s por escena, sin encadenar nada.** Wan genera 5 s de
una sola vez; todo lo que se pide más allá de eso hay que fabricarlo, y ahí es donde
deriva.

Este cuento se puede animar entero porque sus ocho escenas duran 5,0 s exactos —justo lo
que el modelo da de una—. Un cuento cuyas escenas duren 9 s NO es candidato: antes de
animar hay que mirar `duration_s`.

LAS TRES REGLAS DEL PROMPT, y las tres salieron de ver fallar la versión anterior:

1. **Un movimiento chico y concreto por escena.** "Da dos saltitos y sonríe", no "juega
   feliz". Un verbo vago lo resuelve el modelo inventando.
2. **Termina en "Stable camera".** Sin eso la cámara gira sola y el fondo se rehace.
3. **El negativo prohíbe personajes nuevos.** `new characters, duplicate people,
   extra dinosaurs`: es exactamente el error que arruinó los dos intentos anteriores.

EL RECORTE VA ANTES, NO DESPUÉS
───────────────────────────────
Las imágenes son 1024×1536 (2:3) y el short es 1080×1920 (9:16): sobran 160 px de ancho.
Si se anima la imagen entera y se recorta al final, el modelo gastó movimiento en píxeles
que se tiran, y Pablo lo vio en Ushuaia: *"están como muy cerca de la cámara"*. Acá la
imagen se recorta ANTES de mandarla, así el modelo compone sobre el encuadre real.

LO QUE CUESTA
─────────────
El Space declara ~86,5 s de GPU por clip. Con HF PRO son 40 min de cuota por día: entran
casi cuatro cuentos de ocho escenas sin pagar un peso. Pasada la cuota, US$1 cada 10 min.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CONFIG_CT3D = "/opt/ct3d/backend/config.json"

SPACE = os.environ.get("HF_VIDEO_SPACE", "linoyts/wan2-2-i2v-rCM")
PASOS = int(os.environ.get("HF_VIDEO_STEPS", "6"))
CLIP_S = float(os.environ.get("HF_VIDEO_CLIP_S", "5.0"))

#: Lo que NO tiene que aparecer. `new characters` y `extra dinosaurs` son la lección de los
#: dos intentos anteriores: el modelo llenaba el claro de bichos que el cuento no nombra.
NEGATIVO = (
    "overexposed, blurry, low quality, deformed faces, extra limbs, extra fingers, "
    "new characters, duplicate people, extra dinosaurs, extra animals, "
    "unreadable changing text, camera spin, walking backward, morphing bodies, "
    # LOS ANIMALES NO HABLAN. Pablo, 21-ago-2026: *"el perro parece hablar en lugar de
    # ladrar, es preferible que no lo haga"*. Ningún prompt se lo pidió: el modelo les
    # anima la boca por su cuenta y quedan como si conversaran.
    "talking animal, animal talking, mouth moving, lip sync, open mouth talking"
)

#: El zoom, aparte. Los ocho primeros clips salieron con "Stable camera" en el prompt y los
#: ocho hicieron zoom in igual: los personajes terminan bastante más grandes que en el
#: dibujo. Es el mismo defecto que Pablo marcó en Ushuaia —*"están como muy cerca de la
#: cámara"*— así que el pedido va en el NEGATIVO, que es donde el modelo sí lo escucha,
#: y no confiado a una frase del prompt.
SIN_ZOOM_NEG = (
    ", zoom in, zoom out, camera zoom, dolly in, dolly zoom, camera push in, "
    "characters growing larger, changing scale, cropping into the characters"
)
SIN_ZOOM_POS = (
    " The camera never moves and never zooms: the framing stays exactly as it is and the "
    "characters keep the same size on screen from the first frame to the last."
)

#: Un movimiento por escena de «Dino llama al que está solo». Van pegados al texto que se
#: escucha: si el relato dice que Rexo mira sin moverse, el prompt dice que se queda quieto.
MOVIMIENTOS = {
    "dino_incluir": [
        # 0 · «¡Mirá cómo brinca Dino en el claro! Rexo lo observa con curiosidad.»
        "The little green dinosaur hops happily in place, bouncing twice with a big smile. "
        "The blue dinosaur watches him and blinks, standing still. Grass and leaves sway "
        "gently in the warm breeze. Stable camera.",
        # 1 · «Rexo se queda parado, mirando a Dino brincar y brincar.»
        "The blue dinosaur stands completely still and watches, only his head turning a "
        "little. The green dinosaur bounces once and his smile fades as he glances aside. "
        "Leaves sway gently. Stable camera.",
        # 2 · «Dino salta y gira. Rexo lo observa, curioso, sin moverse.»
        "The green dinosaur jumps up and spins once with his mouth open in delight, landing "
        "softly. The blue dinosaur does not move, only his tail sways slowly. "
        "Grass moves in the breeze. Stable camera.",
        # 3 · «Dino juega más fuerte en el claro, mientras Rexo observa, curioso.»
        "The green dinosaur runs forward playing harder, arms swinging. The blue dinosaur "
        "stays planted in the foreground, tail swaying, quietly watching him. "
        "Distant palm leaves move in the wind. Stable camera.",
        # 4 · «Dino juega más fuerte, pero ya no se divierte. Rexo mira.»
        "The green dinosaur crouches low and his shoulders drop as he stops playing, his "
        "smile fading. The blue dinosaur stands quietly and keeps looking at him. "
        "Flowers sway gently. Stable camera.",
        # 5 · «Dino mira a Rexo, parado y triste. Se siente mal.»
        "The green dinosaur turns his head and looks straight at the blue dinosaur with a "
        "sad face. The blue dinosaur looks back and blinks slowly. Both stay in place. "
        "Leaves sway gently. Stable camera.",
        # 6 · «Dino lo mira y se da cuenta: ¡Rexo necesita un amigo!»
        "Close-up: the green dinosaur's eyes widen with a happy realization and he smiles "
        "wide. The blue dinosaur smiles back and tilts his head toward him. Warm light and "
        "gentle leaf movement behind them. Stable camera.",
        # 7 · «Dino llama a Rexo. Juegan juntos y se ríen. ¡Qué divertido!»
        "Both little dinosaurs hop and play together side by side, laughing, bouncing "
        "lightly in the clearing. Their tails wag and the flowers sway around them. "
        "Stable camera.",
    ],
}


def _token() -> str:
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    with open(CONFIG_CT3D) as f:
        return json.load(f)["hf_token"]


def _recortar(origen: Path, destino: Path, ancho: int = 864, alto: int = 1536) -> Path:
    """La imagen, ya en el encuadre 9:16 que se va a ver. Ver el docstring del módulo."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(origen), "-vf",
         f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto}",
         str(destino)], check=True)
    return destino


#: Cuántos clips se le piden al Space a la vez.
#:
#: Pablo, 21-ago-2026: *"la ia que usé demoró 5 minutos en hacer todo, ¿qué pasa que tarda
#: tanto?"*. Los ~70 s por clip los pone Wan y no bajan. Lo que sí era nuestro es haberlos
#: pedido EN FILA: ocho escenas × 70 s son nueve minutos de espera.
#:
#: MEDIDO el 21-ago-2026: tres pedidos simultáneos tardaron **85 s** contra los ~210 s que
#: tardan en fila. La CUOTA de GPU se consume igual —son segundos de GPU, no de reloj—: lo
#: que se ahorra es la espera, no el gasto.
EN_PARALELO = int(os.environ.get("HF_VIDEO_PARALELO", "3"))


def animar(carpeta: Path, indices: list[int], *, sin_zoom: bool = False,
           sufijo: str = "", rehacer: bool = False) -> list[Path]:
    from concurrent.futures import ThreadPoolExecutor

    from gradio_client import Client, handle_file

    movimientos = MOVIMIENTOS.get(carpeta.name)
    if not movimientos:
        raise SystemExit(
            "No hay prompts de movimiento para %r. Se escriben a mano, mirando las "
            "imágenes: un movimiento chico y concreto por escena." % carpeta.name)

    destino = carpeta / "animado"
    destino.mkdir(parents=True, exist_ok=True)

    pedidos = []
    hechos = []
    for i in indices:
        clip = destino / ("clip_%02d%s.mp4" % (i, sufijo))
        if not rehacer and clip.exists() and clip.stat().st_size > 10_000:
            print("  ya estaba: %s" % clip.name)
            hechos.append(clip)
            continue
        imagen = carpeta / "imagenes" / ("escena_%02d.png" % i)
        if not imagen.is_file():
            print("  ⚠  falta %s" % imagen)
            continue
        pedidos.append((i, _recortar(imagen, destino / ("fuente_%02d.png" % i)), clip))
    if not pedidos:
        return hechos

    def uno(pedido):
        i, fuente, clip = pedido
        # UN Client POR HILO: `gradio_client` guarda estado de sesión y compartirlo entre
        # hilos mezcla las respuestas.
        cliente = Client(SPACE, token=_token(), verbose=False)
        arranque = time.time()
        try:
            r = cliente.predict(
                handle_file(str(fuente)),
                prompt=movimientos[i] + (SIN_ZOOM_POS if sin_zoom else ""),
                steps=PASOS,
                negative_prompt=NEGATIVO + (SIN_ZOOM_NEG if sin_zoom else ""),
                duration_seconds=CLIP_S,
                guidance_scale=1,
                guidance_scale_2=1,
                # Semilla fija: si una escena sale mal se rehace SOLA y las otras siete
                # salen idénticas. Con `randomize_seed` no hay forma de repetir nada.
                seed=100 + i,
                randomize_seed=False,
                api_name="/generate_video",
            )
        except Exception as e:
            return None, "  ⚠  escena %d · %s: %s" % (i, type(e).__name__, str(e)[:260])
        origen = r[0] if isinstance(r, (tuple, list)) else r
        if isinstance(origen, dict):
            origen = origen["path"]
        shutil.copy(origen, clip)
        return clip, "  ✔ %s  (%.0fs)" % (clip.name, time.time() - arranque)

    print("%d clip(s)%s, de a %d" % (len(pedidos), " · sin zoom" if sin_zoom else "",
                                     EN_PARALELO))
    arranque = time.time()
    with ThreadPoolExecutor(max_workers=EN_PARALELO) as ex:
        for clip, linea in ex.map(uno, pedidos):
            print(linea, flush=True)
            if clip is not None:
                hechos.append(clip)
    print("  %.1f min de reloj (en fila habrían sido ~%.1f)"
          % ((time.time() - arranque) / 60, len(pedidos) * 70 / 60))
    return hechos


def main() -> int:
    ap = argparse.ArgumentParser(description="Anima escena por escena un cuento producido.")
    ap.add_argument("carpeta", help="p.ej. out/dino_incluir")
    ap.add_argument("--solo", type=int, action="append",
                    help="animar sólo esta escena (se puede repetir)")
    ap.add_argument("--sin-zoom", action="store_true",
                    help="prohíbe el zoom en el negativo (ver SIN_ZOOM_NEG)")
    ap.add_argument("--sufijo", default="",
                    help="p.ej. _v2: guarda al lado en vez de pisar el clip que ya está")
    ap.add_argument("--rehacer", action="store_true",
                    help="regenera aunque el clip ya exista")
    a = ap.parse_args()

    carpeta = Path(a.carpeta)
    if not carpeta.is_dir():
        carpeta = RAIZ / a.carpeta
    if not carpeta.is_dir():
        raise SystemExit("no existe %s" % a.carpeta)

    with open(carpeta / "historia.json", encoding="utf-8") as f:
        historia = json.load(f)
    largos = [e.get("duration_s") or 0 for e in historia["scenes"]]
    if max(largos) > CLIP_S + 0.6:
        print("  ⚠  hay escenas de hasta %.1fs y el modelo da %.1fs de una."
              % (max(largos), CLIP_S))
        print("     Estirarlas es exactamente lo que falló las dos veces anteriores.")
        return 2

    indices = sorted(set(a.solo)) if a.solo else list(range(len(largos)))
    print("«%s» · %d escena(s) de %.1fs" % (historia["metadata"]["title"], len(indices), CLIP_S))
    hechos = animar(carpeta, indices, sin_zoom=a.sin_zoom, sufijo=a.sufijo,
                    rehacer=a.rehacer)
    print("\n%d/%d clips en %s" % (len(hechos), len(indices), carpeta / "animado"))
    return 0 if len(hechos) == len(indices) else 1


if __name__ == "__main__":
    sys.exit(main())
