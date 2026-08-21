"""Produce un cuento de Dino y Rexo entero: texto, voz, imágenes y MP4.

    python3 producir_cuento.py incluir
    python3 producir_cuento.py incluir esperar-turno cuidar cumplir --solo-texto

POR QUÉ EXISTE
──────────────
21-ago-2026. Los diez cuentos anteriores se armaron **a mano cada vez**: no había script,
así que cada tanda había que reconstruir el pipeline —motor, ilustrador, render— desde
cero. Ese es exactamente el trabajo que se paga dos veces.

El tema, el estilo y los personajes salen de `out/dino/historia.json`, el primer cuento
publicado: no se reinventan acá para que Dino y Rexo sigan siendo los mismos. **La
consistencia de los personajes es lo único que sostiene una serie.**

LO QUE CUESTA
─────────────
Un cuento son ~6 imágenes y ~7 tramos de voz. `--solo-texto` escribe el guion y no gasta
ni en imágenes ni en voz: sirve para leer el cuento antes de pagarlo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

from engine.core.enums import EducationalValue  # noqa: E402
from engine.core.models.character import Character, Voice  # noqa: E402
from engine.core.models.style import Style  # noqa: E402
from engine.core.models.theme import Theme  # noqa: E402
from engine.engine import StoryEngine  # noqa: E402
from engine.generators.values import PROFILES  # noqa: E402

#: El cuento del que se copian tema, estilo y personajes. Es el primero publicado.
MOLDE = RAIZ / "out" / "dino" / "historia.json"
SALIDA = RAIZ / "out"
CONFIG_CT3D = "/opt/ct3d/backend/config.json"

#: La voz de Cuentitos: Lizy, con `eleven_multilingual_v2` y NUNCA v3. v3 deforma la
#: primera palabra de cada tramo y el motor narra escena por escena — medido con Whisper
#: sobre cuentos ya renderizados: "Rexo"→"Prexo", "Dino"→"Pino", "Pedir"→"seguir".
VOZ_ID = "rrErIO88ehxTnspOjKvf"
MODELO_VOZ = "eleven_multilingual_v2"


def _claves() -> dict:
    with open(CONFIG_CT3D) as f:
        return json.load(f)


def _molde():
    """Tema, estilo y personajes del primer cuento publicado."""
    if not MOLDE.is_file():
        raise SystemExit("no está %s: sin molde no se puede mantener a Dino igual" % MOLDE)
    with open(MOLDE, encoding="utf-8") as f:
        d = json.load(f)
    theme = Theme(**d["theme"])
    style = Style(**d["style"])
    personajes = [Character(**sc["character"]) for sc in d["characters"]]
    return theme, style, personajes


async def _producir(valor: str, *, solo_texto: bool, destino: Path):
    cfg = _claves()
    theme, style, personajes = _molde()

    from engine.providers.openai import OpenAIProvider

    text_provider = OpenAIProvider(cfg["openai_api_key"])
    voice_provider = None
    narrator_voice = None
    if not solo_texto:
        from engine.providers.elevenlabs import ElevenLabsProvider

        voice_provider = ElevenLabsProvider(cfg["elevenlabs_api_key"])
        narrator_voice = Voice(provider_voice_id=VOZ_ID)

    motor = StoryEngine(text_provider=text_provider, voice_provider=voice_provider,
                        narrator_voice=narrator_voice)
    story = await motor.generate(theme=theme, style=style, value=EducationalValue(valor),
                                 age=4, duration_s=40.0, characters=personajes)

    print("  título: «%s»" % story.metadata.title)
    for i, esc in enumerate(story.scenes, 1):
        print("    %d. %s" % (i, (esc.narration or "")[:96]))
    if solo_texto:
        return None

    destino.mkdir(parents=True, exist_ok=True)
    with open(destino / "historia.json", "w", encoding="utf-8") as f:
        json.dump(json.loads(story.model_dump_json()), f, ensure_ascii=False, indent=1)

    from engine.generators.illustrator import SceneIllustrator
    from engine.render.video import VideoRenderer

    story = await SceneIllustrator(text_provider).illustrate(story, destino / "imagenes")
    return Path(VideoRenderer().render(story, destino / ("%s.mp4" % valor)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Produce cuentos de Dino y Rexo.")
    ap.add_argument("valores", nargs="+", help="p.ej. incluir esperar-turno")
    ap.add_argument("--solo-texto", action="store_true",
                    help="escribe el guion y NO gasta en imágenes ni voz")
    a = ap.parse_args()

    conocidos = {v.value for v in EducationalValue}
    for v in a.valores:
        if v not in conocidos:
            print("  ⚠  %r no está en el catálogo. Son: %s"
                  % (v, ", ".join(sorted(conocidos))))
            return 2

    for v in a.valores:
        perfil = PROFILES[EducationalValue(v)]
        print("\n── %s ─ «%s»" % (v, perfil.title.replace("{protagonista}", "Dino")))
        try:
            mp4 = asyncio.run(_producir(v, solo_texto=a.solo_texto,
                                        destino=SALIDA / ("dino_%s" % v.replace("-", "_"))))
        except Exception as e:
            # Se sigue con el resto: que falle uno no puede tirar la tanda entera, y lo que
            # ya se pagó de los anteriores quedó en disco.
            print("  ⚠  %s: %s" % (type(e).__name__, str(e)[:220]))
            continue
        if mp4:
            print("  ✔ %s" % mp4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
