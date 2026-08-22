"""«Pablito y Alvin y el desierto donde no llueve nunca» — Atacama, Chile.

EL PRIMER CUENTO DISEÑADO PARA ANIMARSE
───────────────────────────────────────
21-ago-2026. Pablo, después de que fallaran dos intentos de animar cuentos ya hechos:
*"si para hacer que funcione tenés que crear 10 imágenes me decís y lo hacés, pero seguir
queriendo hacer algo que no se puede no va a salir nunca. NO SE PUEDE MÁS DE 5 s Y ES ASÍ"*.

Ese es el diseño entero. Wan 2.2 genera **5,0 segundos** y no hay forma de estirarlos:
encadenar degrada en cascada y partir una escena larga en varios clips repite la misma
lámina —Pablo lo vio enseguida: *"la misma imagen se repite varias veces"*—.

Entonces el cuento se escribe al revés de como se venía escribiendo: **diez escenas de cinco
segundos, una lámina cada una, un clip cada una**. Nada partido, nada estirado, nada
encadenado. Es lo que hizo la otra IA en Ushuaia y por eso salió bien en cinco minutos.

Es la primera parada fuera de la Argentina —las 29 argentinas ya están producidas— y el
desierto es lo más lejos que se puede estar del glaciar del cuento anterior, que es la regla
de la serie: dos paisajes parecidos seguidos se leen como el mismo video repetido.

CÓMO SE ESCRIBIÓ CADA COSA
──────────────────────────
**El texto: 9 a 11 palabras y casi sin comas.** Lizy va a ~1,9 palabras por segundo, así que
5,0 s son unas 9,5 palabras. Y **cada coma cuesta casi una palabra** —medido: dos textos de
13 palabras dieron 5,20 s y 7,55 s, y la diferencia eran las comas—.

**La primera palabra de cada tramo es sacrificable** («Un día», «Del otro lado», «Y ahí»):
`eleven_multilingual_v2` deforma la primera palabra y el motor narra tramo por tramo.

**Van encadenados.** Cada texto empieza donde terminó el anterior. Es lo que hace que se oiga
como un cuento y no como diez frases sueltas.

**Cada escena tiene algo que se mueve solo**: vapor, nubes, arena, agua, vicuñas, estrellas.
Es la lección del cuento de Dino, donde el claro estaba quieto y el modelo, sin nada que
animar, **terminaba moviendo la cámara**. En Atacama el paisaje hace la mitad del trabajo.

**Ninguna acción sin dueño.** El prompt del Calafate decía "un flamenco abre las alas" y el
modelo se las puso al perro: a Alvin le crecieron alas rosas. Acá cada movimiento dice quién
lo hace, y lo que pasa en el fondo dice que pasa en el fondo.

**El abuelo no corre.** Nunca. Es regla del canal, no de este cuento.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/opt/ct3d/backend")

LUGAR = "el desierto de Atacama, Chile"
TITULO = "Pablito y Alvin y el desierto donde no llueve nunca"
DESCRIPCION = ("Pablito, su abuelo y Alvin cruzan la cordillera y llegan al desierto de "
               "Atacama, el lugar más seco del mundo: piedras rojas, géiseres, vicuñas, "
               "un campo de sal y el cielo más estrellado que vieron nunca.")

DESTINO = Path("/root/.claude/jobs/8e6ab4db/tmp/atacama")
SPACE = "linoyts/wan2-2-i2v-rCM"
CLIP_S = 5.0
FPS = 30
EN_PARALELO = 3

NEGATIVO = (
    "overexposed, blurry, low quality, deformed faces, extra limbs, extra fingers, "
    "new characters, duplicate people, extra people, extra dogs, extra animals, "
    "unreadable changing text, camera spin, walking backward, morphing bodies, "
    "zoom in, zoom out, camera zoom, dolly in, camera push in, characters growing larger, "
    "changing scale, running, winged dog, wings on the dog, animal hybrid, "
    "necktie, tie, changing clothes, new clothing, different outfit, "
    "talking dog, dog talking, animal talking, dog mouth moving, lip sync, speaking animal"
)
SIN_ZOOM = (" The camera never moves and never zooms: the framing stays exactly as it is and "
            "everyone keeps the same size on screen from the first frame to the last. "
            "Stable camera.")

#: Las diez escenas. `texto` es lo que se escucha, `imagen` la lámina y `movimiento` lo que
#: se anima. Las tres tienen que contar LO MISMO: si el texto nombra una acción, la lámina la
#: dibuja y el movimiento la ejecuta. Es el error que más caro salió en las dos series.
ESCENAS = [
    {
        "texto": "Un día cruzaron la cordillera y llegaron a Chile.",
        "imagen": ("Pablito, his grandpa and Alvin at a mountain pass high in the Andes, "
                   "snowy peaks all around, a simple road marker beside them, cold clear "
                   "sky with clouds moving over the summits."),
        # Las nubes y el viento hacen el movimiento: nadie camina, así que no hay forma de
        # que el modelo se lleve a los personajes fuera del cuadro.
        "movimiento": ("Clouds drift slowly over the snowy peaks and a cold wind moves their "
                       "clothes and Alvin's fur. Pablito looks up at the mountains and his "
                       "grandfather rests a hand on his shoulder. All three stay in place."),
    },
    {
        "texto": "Del otro lado estaba el desierto más seco del mundo.",
        "imagen": ("Pablito, his grandpa and Alvin standing at the edge of a vast dry desert "
                   "in Atacama, orange sand and stones reaching the horizon, no plants, "
                   "distant volcano, bright empty sky."),
        "movimiento": ("Loose sand blows across the ground in thin ribbons and heat shimmers "
                       "near the horizon. Pablito shades his eyes with one hand and looks "
                       "out. The grandfather stands beside him and Alvin sniffs the air."),
    },
    {
        "texto": "Acá casi nunca llueve dijo el abuelo tomando agua.",
        "imagen": ("The grandpa holding an old metal canteen and pouring a little water into "
                   "a cup for Alvin, Pablito watching closely, dry cracked desert ground "
                   "around them, warm afternoon light."),
        # El agua cayendo es el movimiento. Alvin toma: la boca se le mueve por una razón que
        # el cuento nombra, no porque el modelo lo haya decidido.
        "movimiento": ("A thin stream of water pours from the canteen into the cup and Alvin "
                       "laps at it. Pablito leans in to watch and the grandfather smiles. "
                       "The dry ground and the light stay exactly the same."),
    },
    {
        "texto": "Después Pablito vio unas piedras rojas como estatuas gigantes.",
        "imagen": ("Pablito, his grandpa and Alvin small in the foreground looking up at tall "
                   "red rock formations in the Valle de la Luna, sharp shadows, fine dust in "
                   "the air, deep blue sky."),
        "movimiento": ("Fine dust drifts slowly across the base of the red rocks and the "
                       "shadows stay still. Pablito tips his head back to see the top and "
                       "points upward. The grandfather follows his gesture. Alvin sits."),
    },
    {
        "texto": "Y Alvin olfateó la arena y encontró unas huellas.",
        "imagen": ("Alvin with his nose down close to the sand, sniffing a line of small "
                   "animal tracks; Pablito crouching beside him pointing at the tracks; the "
                   "grandpa standing behind them; warm sand, low sun."),
        # Alvin es el sujeto del movimiento y está nombrado: no hay ambigüedad sobre quién
        # olfatea. Y la cola le da algo que hacer sin que se levante ni se vaya del cuadro.
        "movimiento": ("Alvin keeps his nose down and sniffs along the tracks while his tail "
                       "wags. Pablito crouches and points at the little prints. The "
                       "grandfather watches from behind. Nobody stands up or walks away."),
    },
    {
        "texto": "Bien temprano el suelo largaba vapor blanco calentito.",
        "imagen": ("Pablito, his grandpa and Alvin at a safe distance watching white steam "
                   "rising from holes in the ground at the El Tatio geysers, dawn light, "
                   "cold blue morning air, distant mountains."),
        # La escena con más movimiento propio de todas. El vapor le da al modelo tanto que
        # animar que no necesita tocar ni la cámara ni a los personajes.
        "movimiento": ("Thick white steam rises and curls from the holes in the ground and "
                       "drifts sideways in the cold morning air. Pablito watches with wide "
                       "eyes, the grandfather holds his hand, and Alvin's ears twitch."),
    },
    {
        "texto": "Y ahí aparecieron unas vicuñas caminando despacio.",
        "imagen": ("A small group of vicuñas walking slowly among stones on a high plateau, "
                   "seen from a distance; Pablito, his grandpa and Alvin standing quietly in "
                   "the foreground watching them; pale dry grass, mountains behind."),
        # LAS VICUÑAS CAMINAN Y ELLOS NO. Va dicho de las dos maneras —quién se mueve y quién
        # no— porque en el Calafate una acción del fondo se la quedó el personaje del frente.
        "movimiento": ("The vicuñas in the background walk slowly among the stones, one "
                       "lowering its head to the grass. Pablito, his grandfather and Alvin "
                       "stay completely still in the foreground and watch them. Dry grass "
                       "sways in the wind."),
    },
    {
        "texto": "Más allá brillaba un campo de sal como nieve.",
        "imagen": ("Pablito, his grandpa and Alvin at the edge of a huge white salt flat in "
                   "the Salar de Atacama, cracked hexagon patterns on the crust, bright "
                   "midday sun, mountains far away."),
        "movimiento": ("Heat shimmers over the white salt crust and the light glints on it. "
                       "Pablito crouches and touches the salt with one finger, then looks up "
                       "at his grandfather, who nods. Alvin stays beside them."),
    },
    {
        "texto": "Cuando cayó la noche aparecieron miles de estrellas.",
        "imagen": ("Night in the Atacama desert: an enormous starry sky with the Milky Way "
                   "over the dark desert; Pablito, his grandpa and Alvin sitting on a "
                   "blanket on the sand, small under the sky, seen from behind."),
        "movimiento": ("The stars twinkle slowly across the Milky Way and a faint glow moves "
                       "along the horizon. The three of them sit still on the blanket looking "
                       "up. Alvin's fur moves slightly in the night air."),
    },
    {
        "texto": "Los tres se abrazaron mirando el cielo más limpio.",
        "imagen": ("Pablito hugging Alvin while his grandpa puts an arm around them both, all "
                   "three sitting on the blanket under the huge starry Atacama sky, warm "
                   "lantern light on their faces, peaceful."),
        "movimiento": ("The grandfather draws his arm gently around Pablito and Alvin and the "
                       "three settle closer together. Alvin wags his tail. The stars keep "
                       "twinkling above them and the lantern light flickers warmly."),
    },
]


def guion() -> dict:
    """El guion en el formato de `cuentos_ar.py`, para que `recomponer()` lo entienda."""
    return {"titulo": TITULO, "descripcion": DESCRIPCION,
            "escenas": [{"texto": e["texto"], "imagen": e["imagen"]} for e in ESCENAS]}


def _dur(p) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def mostrar():
    """El cuento entero, sin gastar un peso. Es el paso que Pablo pidió que fuera primero."""
    print("«%s»\n" % TITULO)
    palabras = 0
    for i, e in enumerate(ESCENAS, 1):
        n = len(e["texto"].split())
        palabras += n
        print("%2d. %s" % (i, e["texto"]))
        print("    %d palabras · ~%.1fs a 1,9 palabras/s" % (n, n / 1.9))
        print("    lámina    : %s" % e["imagen"][:96])
        print("    movimiento: %s" % e["movimiento"][:96])
        print()
    print("%d escenas · %d palabras · ~%.0fs de cuento"
          % (len(ESCENAS), palabras, palabras / 1.9))


def laminas():
    """Las diez imágenes. ES EL PASO CARO: se corre una sola vez y quedan en disco."""
    from cuentos_ar import escena

    DESTINO.mkdir(parents=True, exist_ok=True)
    for i, e in enumerate(ESCENAS):
        crudo = DESTINO / ("img%02d.png" % i)
        if crudo.is_file() and crudo.stat().st_size > 10_000:
            print("  ya estaba: %s" % crudo.name)
            continue
        print("  generando lámina %d/%d…" % (i + 1, len(ESCENAS)), flush=True)
        try:
            img = escena(e["imagen"])
        except RuntimeError as ex:
            # El filtro de seguridad de OpenAI es errático: una escena rechazada no se lleva
            # el cuento entero ni las láminas ya pagadas.
            print("  ⚠  escena %d: %s" % (i, str(ex)[:160]))
            continue
        with open(crudo, "wb") as f:
            f.write(img)
    with open(DESTINO / "guion.json", "w", encoding="utf-8") as f:
        json.dump(guion(), f, ensure_ascii=False, indent=1)


def voces():
    """Los diez tramos de voz, Y LA MEDICIÓN.

    Es el control que va ANTES de la GPU: si un tramo se pasa de 5,0 s, el clip no lo cubre
    y hay que acortar el texto. Descubrirlo después de animar es pagar los clips dos veces.
    """
    from cuentos_ar import voz

    DESTINO.mkdir(parents=True, exist_ok=True)
    largos = []
    for i, e in enumerate(ESCENAS):
        mp3 = DESTINO / ("a%02d.mp3" % i)
        if not mp3.is_file():
            voz(e["texto"], str(mp3))
        d = _dur(mp3)
        largos.append(d)
        marca = "  " if d <= CLIP_S + 0.15 else "⚠ "
        print("%s%2d. %.2fs  %s" % (marca, i + 1, d, e["texto"][:58]))
    largos_malos = [i + 1 for i, d in enumerate(largos) if d > CLIP_S + 0.15]
    print("\ntotal: %.1fs" % sum(largos))
    if largos_malos:
        print("⚠  se pasan de %.1fs las escenas %s: hay que acortarles el texto ANTES"
              % (CLIP_S, largos_malos))
        print("   de animar, o el clip no llega a cubrirlas.")
    return largos


def clips():
    from concurrent.futures import ThreadPoolExecutor

    from gradio_client import Client, handle_file

    token = json.load(open("/opt/ct3d/backend/config.json"))["hf_token"]
    pedidos = []
    for i, e in enumerate(ESCENAS):
        clip = DESTINO / ("clip%02d.mp4" % i)
        if clip.is_file() and clip.stat().st_size > 10_000:
            print("  ya estaba: %s" % clip.name)
            continue
        crudo = DESTINO / ("img%02d.png" % i)
        if not crudo.is_file():
            print("  ⚠  falta %s" % crudo.name)
            continue
        # La lámina se recorta al 9:16 del canal ANTES de animar: si se recorta después, el
        # modelo gastó movimiento en píxeles que se tiran.
        lamina = DESTINO / ("lam%02d.png" % i)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(crudo), "-vf",
                        "scale=864:1536:force_original_aspect_ratio=increase,crop=864:1536",
                        str(lamina)], check=True)
        pedidos.append((i, lamina, clip))
    if not pedidos:
        print("no falta ningún clip")
        return

    def uno(pedido):
        i, lamina, clip = pedido
        cliente = Client(SPACE, token=token, verbose=False)   # uno por hilo
        t0 = time.time()
        try:
            r = cliente.predict(handle_file(str(lamina)),
                                prompt=ESCENAS[i]["movimiento"] + SIN_ZOOM, steps=6,
                                negative_prompt=NEGATIVO, duration_seconds=CLIP_S,
                                guidance_scale=1, guidance_scale_2=1,
                                seed=300 + i, randomize_seed=False,
                                api_name="/generate_video")
        except Exception as ex:
            return "  ⚠  escena %d · %s: %s" % (i + 1, type(ex).__name__, str(ex)[:220])
        o = r[0] if isinstance(r, (tuple, list)) else r
        if isinstance(o, dict):
            o = o["path"]
        shutil.copy(o, clip)
        return "  ✔ %s (%.0fs)" % (clip.name, time.time() - t0)

    print("%d clips, de a %d" % (len(pedidos), EN_PARALELO))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=EN_PARALELO) as ex:
        for linea in ex.map(uno, pedidos):
            print(linea, flush=True)
    print("\n%.1f min (en fila habrían sido ~%.1f)"
          % ((time.time() - t0) / 60, len(pedidos) * 70 / 60))


def _titular(entrada: Path, salida: Path) -> Path:
    """El título del canal sobre el primer plano, con `componer()` de `cuentos_ar.py`.

    Se reutiliza el código del canal y no se reescribe con drawtext: el tamaño, la posición
    y el contorno del título se midieron sobre los cuentos publicados, y uno "parecido"
    haría que este video se vea distinto de todos los demás.
    """
    from cuentos_ar import componer

    tmp = Path(tempfile.mkdtemp(prefix="tit_"))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(entrada), str(tmp / "f%05d.png")],
                   check=True)
    for c in sorted(tmp.glob("f*.png")):
        with open(c, "rb") as f:
            componer(f.read(), "", str(c), titulo=TITULO)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS),
                    "-i", str(tmp / "f%05d.png"), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "19", "-pix_fmt", "yuv420p", str(salida)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return salida


def montar() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="atacama_"))
    partes = []
    for i, e in enumerate(ESCENAS):
        mp3 = DESTINO / ("a%02d.mp3" % i)
        if not mp3.is_file():
            raise SystemExit("falta la voz de la escena %d" % (i + 1))
        largo = _dur(mp3)
        clip = DESTINO / ("clip%02d.mp4" % i)
        if clip.is_file():
            entrada = ["-i", str(clip)]
        else:
            # Sin clip, esa escena sale quieta. Un cuento a medio animar es preferible a uno
            # que no se puede armar.
            entrada = ["-loop", "1", "-t", "%.3f" % largo, "-i", str(DESTINO / ("img%02d.png" % i))]
        mudo = tmp / ("v%02d.mp4" % i)
        # El clip dura 5,0 s y la voz un poco menos: se CORTA a la voz. Si la voz fuera más
        # larga, `tpad` congela el último cuadro — nunca se estira, que sería cámara lenta.
        vf = ("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=%d,"
              "tpad=stop_mode=clone:stop_duration=%.3f,trim=duration=%.3f,setpts=PTS-STARTPTS"
              % (FPS, largo, largo))
        subprocess.run(["ffmpeg", "-y", "-v", "error", *entrada, "-vf", vf, "-an",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                        "-pix_fmt", "yuv420p", str(mudo)], check=True)
        if i == 0:
            mudo = _titular(mudo, tmp / "v00t.mp4")
        # El audio de la escena se pega acá, tramo por tramo: así cada imagen dura
        # exactamente lo que dura su voz y no hay nada que sincronizar después.
        conaudio = tmp / ("s%02d.mp4" % i)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mudo), "-i", str(mp3),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                        str(conaudio)], check=True)
        partes.append(conaudio)

    lista = tmp / "l.txt"
    lista.write_text("".join("file '%s'\n" % p for p in partes))
    final = DESTINO / "cuento_pya_31_atacama.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c", "copy", "-movflags", "+faststart", str(final)],
                   check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("✔ %s  (%.1fs)" % (final, _dur(final)))
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description="Atacama: el primer cuento diseñado animable.")
    for paso in ("laminas", "voces", "clips", "montar"):
        ap.add_argument("--" + paso, action="store_true")
    a = ap.parse_args()
    if not any((a.laminas, a.voces, a.clips, a.montar)):
        mostrar()
        return 0
    if a.laminas:
        laminas()
    if a.voces:
        voces()
    if a.clips:
        clips()
    if a.montar:
        montar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
