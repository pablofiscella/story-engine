"""Anima «Pablito y Alvin en El Calafate» — VARIOS CLIPS POR ESCENA.

    python3 animar_calafate.py --clips        # genera los 14 clips (GPU)
    python3 animar_calafate.py --montar       # arma el MP4 con lo que haya

POR QUÉ VARIOS CLIPS POR ESCENA
───────────────────────────────
21-ago-2026. Las escenas de este cuento duran de 6,7 a 10,9 s y Wan 2.2 genera 5,0 s. Las
dos salidas conocidas fallaron: estirar un clip de 5 s a 10,9 es cámara lenta al 46 %, y
encadenar desde el último cuadro degrada en cascada —los personajes se deforman y aparecen
otros—. Eso ya se probó dos veces y las dos salieron mal.

Acá se hace lo tercero: **N clips independientes por escena, todos desde la MISMA lámina
original**, cada uno con un movimiento distinto que avanza. Como ninguno arranca del cuadro
final del anterior, no hay cascada; y como son movimientos distintos de la misma escena, el
corte entre uno y otro se lee como un cambio de plano, no como un bucle.

**Nunca se estira: se corta.** N = ceil(duración / 5,0), y cada clip se recorta a
duración/N —siempre ≤ 5,0 s—. Una escena de 10,9 s pasa a ser tres planos de 3,6 s en vez
de uno quieto de casi once segundos, que además es mejor para la retención.

POR QUÉ ESTE CUENTO Y NO EL DE DINO
───────────────────────────────────
Pablo, 21-ago-2026: *"no me gusta mucho cómo queda, no es consistente, cambian de tamaño y
a veces no coincide con lo que hace. Fijate si podés hacer la próxima de Pablito para saber
si es algo que estás haciendo mal"*.

Es la comparación justa: Ushuaia salió bien con este mismo Space. Y de paso corrige un
malentendido — **Ushuaia no fue "el cuento animado"**: la otra IA armó siete escenas nuevas
de 5,7 s a la medida del modelo, y por eso hubo que grabarle voz nueva. Acá, en cambio, el
cuento ya está hecho y pagado, y lo que se prueba es si se puede animar SIN rehacerlo.

EL ABUELO NO CORRE. Nunca. Ninguno de estos prompts lo mueve más rápido que caminando.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/opt/ct3d/backend")

BASE = Path("/opt/ct3d/backend/campanias_out")
FUENTE = BASE / "cuento_pablito_y_alvin_en_el_calafate_fuente"
ORIGINAL = BASE / "cuento_pablito_y_alvin_en_el_calafate.mp4"
DESTINO = Path("/root/.claude/jobs/8e6ab4db/tmp/calafate")
CONFIG = "/opt/ct3d/backend/config.json"

SPACE = "linoyts/wan2-2-i2v-rCM"
CLIP_S = 5.0
FPS = 30

NEGATIVO = (
    "overexposed, blurry, low quality, deformed faces, extra limbs, extra fingers, "
    "new characters, duplicate people, extra people, extra dogs, extra animals, "
    "unreadable changing text, camera spin, walking backward, morphing bodies, "
    "zoom in, zoom out, camera zoom, dolly in, camera push in, characters growing larger, "
    "changing scale, running, winged dog, wings on the dog, feathered dog, "
    "pink wings, dog with wings, animal hybrid, necktie, tie, scarf, "
    "changing clothes, new clothing, different outfit, "
    # EL PERRO NO HABLA. Pablo, 21-ago-2026: *"el perro parece hablar en lugar de
    # ladrar, es preferible que no lo haga"*. Ningún prompt le pidió ladrar: el modelo
    # le anima la boca por su cuenta y queda como si conversara, que en un cuento con
    # personajes que NO hablan rompe la regla del canal.
    "talking dog, dog talking, animal talking, dog mouth moving, lip sync, "
    "open mouth talking, speaking animal"
)
SIN_ZOOM = (" The camera never moves and never zooms: the framing stays exactly as it is and "
            "everyone keeps the same size on screen from the first frame to the last. "
            "Stable camera.")

#: Los movimientos, por escena. Cada lista es UN plano por elemento y tienen que AVANZAR:
#: si los dos planos de una escena piden lo mismo, se ven como el mismo clip repetido.
#:
#: El paisaje hace la mitad del trabajo. En el claro de Dino no había nada que se moviera
#: solo y el modelo terminaba moviendo la cámara para cumplir; acá hay hielo que cae, agua
#: que ondula, pastos con viento y flamencos. Cada prompt le da al modelo algo del FONDO
#: para animar, además de lo que hacen los personajes.
MOVIMIENTOS = [
    [  # 0 · «El hielo cruje fuerte. Miran desde las pasarelas, con la pared azul atrás.»
        "Small fragments of ice trickle down the face of the huge blue glacier wall. Pablito "
        "looks up in awe, Alvin's tail wags on the wooden walkway, and the grandfather rests "
        "his hand on the railing. Sunlight glints on the ice.",
        "Pablito turns his head toward his grandfather and smiles. The grandfather nods "
        "slowly and lifts a calm hand toward the glacier. Alvin looks up at them. The water "
        "ripples softly at the base of the ice.",
        "Alvin steps forward once on the walkway and looks at the ice. Pablito leans on the "
        "wooden railing to see better. The grandfather stands quietly beside him. Clouds "
        "drift slowly above the glacier.",
    ],
    [  # 1 · «¡Crac! Un pedazo de hielo cae al lago. Alvin se esconde detrás del abuelo.»
        "A large chunk of ice breaks off the glacier and drops into the lake, throwing up a "
        "tall white splash of water. Pablito grips the railing and watches with wide eyes.",
        "The splash falls back and spreads into wide ripples across the turquoise water. "
        "Alvin peeks out from behind the grandfather's legs. The grandfather looks down at "
        "him and smiles reassuringly.",
    ],
    [  # 2 · «El viento patagónico silba. Caminan entre pastos altos.»
        "Pablito and his grandfather walk slowly along the gravel path while Alvin trots "
        "beside them. Tall golden grasses bend in the Patagonian wind on both sides.",
        "They keep walking at the same calm pace toward the turquoise lake ahead. Alvin's "
        "ears flutter in the wind and Pablito's striped shirt ruffles. The grasses keep "
        "swaying.",
    ],
    [  # 3 · «Hay flamencos rosados en la orilla. Detrás brilla el Lago Argentino.»
        "The pink flamingos wade slowly through the shallow water; one lifts a leg and dips "
        "its beak. Pablito stops and stares at them. Alvin sits and watches quietly.",
        # NO SE LE PIDE AL FLAMENCO QUE ABRA LAS ALAS. La primera versión decía "one
        # flamingo opens its wings once" y el modelo se las puso a ALVIN: al perro le
        # crecieron alas rosas durante todo el plano. Es el mismo error que "y se rompe"
        # sin sujeto —una acción sin dueño la resuelve el modelo, y la resuelve mal—, y
        # acá se agrava porque el perro estaba más cerca del centro que el flamenco.
        # LA REGLA: si en el cuadro hay un personaje que PODRÍA hacer la acción, esa
        # acción no se le pide a un elemento del fondo.
        "The flamingos in the background wade slowly through the shallow water and one "
        "dips its beak. Pablito raises his arm to point at them and the grandfather leans "
        "in to look. Alvin stays sitting still beside them. The turquoise water ripples.",
    ],
    [  # 4 · «Pablito se agacha y le muestra a Alvin. El abuelo susurra: quedate quietito.»
        "Pablito crouches a little lower and points slowly with his finger. Alvin sits "
        "perfectly still and tilts his head. The grandfather leans close and whispers behind "
        "his hand.",
        "Alvin's ears perk up while he stays seated. Pablito turns his head and grins at his "
        "grandfather, who smiles back at him. The reeds sway and the shallow water ripples.",
    ],
    [  # 5 · «El cielo se pone rosado. Pablito abraza a Alvin y el abuelo los cubre.»
        "The grandfather draws his coat around Pablito and Alvin and the three of them settle "
        "together. The pink sunset light shifts slowly across the lake behind them.",
        "Pablito hugs Alvin a little closer and Alvin wags his tail. The grandfather smiles "
        "and looks out over the water. Small waves catch the orange light.",
        # El primer intento le puso al abuelo una CORBATA ROJA que no tiene en ninguna
        # otra escena. La ropa se nombra explícitamente para anclarla: donde el prompt
        # no dice nada, el modelo rellena, y en el último plano del cuento se nota.
        # NOMBRAR LA ROPA PARA PROHIBIRLA NO FUNCIONA: el segundo intento decía "with no
        # tie" y la corbata volvió igual, más finita. El modelo no lee la negación —lee
        # "tie"—. La prohibición va SÓLO en el negativo, y el positivo no la menciona.
        "The three of them stay close together watching the sunset. Alvin wags his tail "
        "and Pablito smiles. The clouds glow warmer and the sun sinks a little lower "
        "over the lake.",
    ],
]


#: Semillas cambiadas a mano. Cuando un plano sale con una invención (una corbata que
#: nadie pidió, alas en el perro), corregir el prompt no siempre alcanza: hay que
#: moverlo de lugar en el espacio del modelo.
SEMILLAS = {(5, 2): 777}


def _dur(p) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _plan() -> list[tuple[int, int, float]]:
    """(escena, cuántos planos, cuánto dura cada plano). El audio manda: la escena dura
    exactamente lo que dura su mp3, que es como la arma `cuentos_ar.py`."""
    plan = []
    for i in range(len(MOVIMIENTOS)):
        d = _dur(FUENTE / ("a%02d.mp3" % i))
        n = max(1, math.ceil(d / CLIP_S))
        if n > len(MOVIMIENTOS[i]):
            raise SystemExit("escena %d necesita %d planos y hay %d prompts escritos"
                             % (i, n, len(MOVIMIENTOS[i])))
        plan.append((i, n, d / n))
    return plan


def _token() -> str:
    with open(CONFIG) as f:
        return json.load(f)["hf_token"]


def _recortar(origen: Path, destino: Path) -> Path:
    """La lámina en el encuadre 9:16 final, ANTES de animar: si se recorta después, el
    modelo gastó movimiento en píxeles que se tiran."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(origen), "-vf",
                    "scale=864:1536:force_original_aspect_ratio=increase,crop=864:1536",
                    str(destino)], check=True)
    return destino


#: Cuántos clips se piden a la vez.
#:
#: Pablo, 21-ago-2026: *"la ia que usé demoró 5 minutos en hacer todo, ¿qué pasa que tarda
#: tanto?"*. Los ~70 s por clip los pone Wan y no se pueden bajar. Lo que sí era nuestro es
#: haberlos pedido EN FILA: 14 clips × 70 s = 16 minutos de espera.
#:
#: MEDIDO el 21-ago-2026: tres pedidos simultáneos tardaron **85 s** contra los ~210 s que
#: tardan en fila. El Space los atiende a la vez. La CUOTA de GPU se consume igual —son
#: segundos de GPU, no de reloj—: lo que se ahorra es la espera, no el gasto.
EN_PARALELO = int(os.environ.get("HF_VIDEO_PARALELO", "3"))


def generar():
    from concurrent.futures import ThreadPoolExecutor

    from gradio_client import Client, handle_file

    DESTINO.mkdir(parents=True, exist_ok=True)
    pedidos = []
    for escena, n, largo in _plan():
        lamina = _recortar(FUENTE / ("img%02d.png" % escena),
                           DESTINO / ("lamina_%02d.png" % escena))
        for k in range(n):
            clip = DESTINO / ("e%02d_p%d.mp4" % (escena, k))
            if clip.exists() and clip.stat().st_size > 10_000:
                print("  ya estaba: %s" % clip.name)
                continue
            pedidos.append((escena, k, lamina, clip))
    if not pedidos:
        print("no falta ningún clip")
        return

    def uno(pedido):
        escena, k, lamina, clip = pedido
        # UN Client POR HILO: `gradio_client` guarda estado de la sesión y compartirlo entre
        # hilos mezcla las respuestas.
        cliente = Client(SPACE, token=_token(), verbose=False)
        t0 = time.time()
        try:
            r = cliente.predict(
                handle_file(str(lamina)), prompt=MOVIMIENTOS[escena][k] + SIN_ZOOM, steps=6,
                negative_prompt=NEGATIVO, duration_seconds=CLIP_S,
                guidance_scale=1, guidance_scale_2=1,
                # Semilla distinta por plano: con la misma, dos planos de la misma lámina
                # salen casi idénticos y se ve como un bucle.
                seed=SEMILLAS.get((escena, k), 200 + escena * 10 + k), randomize_seed=False,
                api_name="/generate_video")
        except Exception as e:
            return "  ⚠  escena %d plano %d · %s: %s" % (escena, k, type(e).__name__,
                                                         str(e)[:220])
        o = r[0] if isinstance(r, (tuple, list)) else r
        if isinstance(o, dict):
            o = o["path"]
        shutil.copy(o, clip)
        return "  ✔ %s  (%.0fs)" % (clip.name, time.time() - t0)

    print("%d clips, de a %d" % (len(pedidos), EN_PARALELO))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=EN_PARALELO) as ex:
        for linea in ex.map(uno, pedidos):
            print(linea, flush=True)
    print("\n%.1f min de reloj (en fila habrían sido ~%.1f)"
          % ((time.time() - t0) / 60, len(pedidos) * 70 / 60))


def _titular(entrada: Path, salida: Path, titulo: str) -> Path:
    """El título del canal, cuadro por cuadro, con el MISMO código que compone los cuentos.

    Se reutiliza `componer()` de `cuentos_ar.py` y no se reescribe el texto con ffmpeg: el
    tamaño, la posición y el contorno del título son los de los cuentos de Dino publicados
    —se midieron sobre sus frames— y un drawtext "parecido" haría que este video se vea
    distinto de todos los demás del canal.
    """
    from cuentos_ar import componer

    tmp = Path(tempfile.mkdtemp(prefix="titular_"))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(entrada),
                    str(tmp / "f%05d.png")], check=True)
    cuadros = sorted(tmp.glob("f*.png"))
    for c in cuadros:
        with open(c, "rb") as f:
            componer(f.read(), "", str(c), titulo=titulo)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
                    "-i", str(tmp / "f%05d.png"), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "19", "-pix_fmt", "yuv420p", str(salida)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return salida


def montar() -> Path:
    with open(FUENTE / "guion.json", encoding="utf-8") as f:
        guion = json.load(f)
    tmp = Path(tempfile.mkdtemp(prefix="calafate_"))
    partes = []
    for escena, n, largo in _plan():
        for k in range(n):
            clip = DESTINO / ("e%02d_p%d.mp4" % (escena, k))
            if not clip.is_file():
                # Sin clip, ese plano vuelve a ser la lámina fija. Un cuento a medio animar
                # es preferible a uno que no se puede armar.
                origen = FUENTE / ("img%02d.png" % escena)
                entrada = ["-loop", "1", "-t", "%.3f" % largo, "-i", str(origen)]
            else:
                # CADA PLANO ARRANCA EN UN PUNTO DISTINTO DE SU CLIP.
                #
                # Pablo, 21-ago-2026: *"no quedó bien, la misma imagen se repite varias veces
                # en algunas escenas"*. Tenía razón y la culpa era del montaje: los N planos
                # de una escena salen de la MISMA lámina, así que si los tres se cortan desde
                # el segundo cero, los tres empiezan en el mismo cuadro exacto. Se ve
                # imagen → movimiento → vuelve la imagen → movimiento → vuelve otra vez.
                # Un rebobinado, no un cambio de plano.
                #
                # El primer plano sí arranca en la lámina —es el comienzo de la escena y
                # tiene que enganchar con el corte anterior—; los demás entran cada vez más
                # adelante, donde su clip ya divergió (semilla y prompt distintos).
                desfase = (CLIP_S - largo) * k / (n - 1) if n > 1 else 0.0
                entrada = (["-ss", "%.3f" % desfase] if desfase > 0.01 else []) + \
                          ["-i", str(clip)]
            salida = tmp / ("p_%02d_%d.mp4" % (escena, k))
            # Se CORTA a la duración del plano, nunca se estira: `trim` no distorsiona el
            # movimiento y `setpts` lo pondría en cámara lenta.
            vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                  "fps=%d,tpad=stop_mode=clone:stop_duration=%.3f,trim=duration=%.3f,"
                  "setpts=PTS-STARTPTS" % (FPS, largo, largo))
            subprocess.run(["ffmpeg", "-y", "-v", "error", *entrada, "-vf", vf, "-an",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                            "-pix_fmt", "yuv420p", str(salida)], check=True)
            if escena == 0 and k == 0:
                salida = _titular(salida, tmp / "p_titulada.mp4", guion["titulo"])
            partes.append(salida)

    lista = tmp / "l.txt"
    lista.write_text("".join("file '%s'\n" % p for p in partes))
    mudo = tmp / "mudo.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                    "-pix_fmt", "yuv420p", str(mudo)], check=True)

    # EL AUDIO SALE DEL MP4 ORIGINAL, tal cual y sin recodificar. Ya está mezclado y
    # normalizado; rearmarlo desde los mp3 sueltos sería otra oportunidad de desincronizar.
    final = DESTINO / "cuento_pya_calafate_animado.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mudo), "-i", str(ORIGINAL),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
                    "-shortest", "-movflags", "+faststart", str(final)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("✔ %s  (%.1fs · el original dura %.1fs)" % (final, _dur(final), _dur(ORIGINAL)))
    return final


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", action="store_true")
    ap.add_argument("--montar", action="store_true")
    a = ap.parse_args()
    if not a.clips and not a.montar:
        for escena, n, largo in _plan():
            print("escena %d · %d planos de %.2fs" % (escena, n, largo))
        return 0
    if a.clips:
        generar()
    if a.montar:
        montar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
