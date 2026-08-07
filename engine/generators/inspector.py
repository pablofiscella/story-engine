"""El verificador: el motor MIRA lo que dibujó, antes de que lo mire Pablo.

Corre después del ilustrador. Le pasa cada imagen a un modelo de visión con las
preguntas cuya respuesta **el plan ya sabe** —cuántos personajes hay, si se ve el
objeto, si es de día— y rehace sólo la imagen que no coincide.

Por qué existe, con el número que lo justifica: de los 8 shorts del lote del
7-ago-2026, **3 salieron con anatomía rota** —una mano de más y dos casos de patas de
más— y los encontró Pablo mirando los videos terminados. El motor no detectó ninguno.
Mientras siga así no hay diez shorts por día sin que alguien los mire uno por uno, que
es exactamente lo que el motor viene a evitar. Con el caché puesto, rehacer una sola
imagen cuesta US$0,005.

**Lo que este paso puede y lo que no**, medido contra esos tres casos reales y cinco
imágenes sanas del mismo lote (ver `providers/openai.MODELO_DE_VISION`):

- De los tres defectos de anatomía, el modelo de visión encuentra **uno**: la mano de
  más del abrazo, que describe igual que Pablo (*"tres manos/brazos en el abrazo"*).
  Los dos casos de patas de más se le escapan.
- **Nunca se equivocó al revés**: sobre las cinco imágenes sanas dijo siempre que
  estaban bien. Eso es lo que permite rehacer sin pensarlo — un falso positivo cuesta
  medio centavo y una imagen distinta, pero rehacer una imagen buena una y otra vez
  sería una fábrica de ruido.

O sea que **esto no es el guardián completo de anatomía: es un cedazo**. Se escribe
igual porque un tercio de los errores atajados sin intervención humana es la
diferencia entre revisar 8 videos y revisar 6, y porque las otras preguntas —elenco,
objeto, clima, texto— sí las contesta bien y cubren errores que ya costaron vueltas
enteras: el claro vacío, Dino jugando con piedras, la escena que se nublaba sola.

Dos decisiones de forma, heredadas del storyboard:

1. **Un fallo del proveedor no frena la producción.** Si la visión no contesta o
   contesta algo que no se entiende, la imagen se da por buena y sigue. Un cuento sin
   verificar es peor que uno verificado; un cuento que no existe es mucho peor que los
   dos.
2. **Los guardianes son deterministas.** El modelo describe; quién decide si eso es un
   error es código que compara contra el plan. Lo que no se entiende, no se usa.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from engine.core.interfaces import VisionProvider
from engine.core.models.scene import Scene
from engine.core.models.story import Story
from engine.core.retry import con_reintentos

logger = logging.getLogger(__name__)

#: Cuántas veces se rehace una imagen que no pasó antes de darse por vencido.
#:
#: Dos y no más: cada vuelta cuesta plata y tiempo, y si el modelo de imagen insiste
#: con el mismo error dos veces seguidas la tercera no lo va a arreglar. Cuando se
#: agotan, se deja la ÚLTIMA imagen que menos reparos tuvo y se avisa — nunca se frena
#: el cuento por una escena.
INTENTOS_DE_IMAGEN = 2

SYSTEM = (
    "Sos el control de calidad de un estudio que ilustra cuentos infantiles con IA. "
    "El generador de imágenes falla seguido dibujando miembros de más, manos "
    "duplicadas o patas fusionadas, y esos errores llegan al video publicado. Tu "
    "trabajo es encontrarlos. Describí lo que ves REALMENTE dibujado, no lo que el "
    "personaje debería tener: si el dibujo tiene seis patas hay que reportarlo con "
    "seis, no corregirlo mentalmente a cuatro."
)

#: Un renglón "clave: valor" de la respuesta. Estricto a propósito: lo que no entra en
#: este formato no se usa para decidir nada.
_RENGLON = re.compile(r"^\s*[-*`]*\s*([a-z_]+)\s*:\s*(.+?)\s*[`]*\s*$", re.IGNORECASE)

#: Qué cuenta como "sí" y como "no" en las respuestas de una palabra.
_SI = frozenset({"si", "sí", "yes", "true"})
_NO = frozenset({"no", "not", "false", "ninguno", "ninguna"})


@dataclass(frozen=True)
class Reparo:
    """Algo que la imagen tiene mal, con el nombre de la regla que rompe."""

    escena: int
    regla: str
    detalle: str

    def __str__(self) -> str:
        return f"escena {self.escena}: {self.detalle}"


@dataclass
class Veredicto:
    """Cómo le fue a la imagen de una escena."""

    escena: int
    reparos: list[Reparo] = field(default_factory=list)
    intentos: int = 1
    resuelta: bool = True

    @property
    def paso(self) -> bool:
        return not self.reparos


class ImageInspector:
    """Mira las imágenes de una historia y rehace las que no coinciden con el plan."""

    def __init__(self, vision: VisionProvider, illustrator: object | None = None) -> None:
        #: Quien MIRA. Conviene que no sea el mismo modelo que dibujó: el que produjo
        #: el error es el que menos chance tiene de verlo.
        self._vision = vision
        #: Quien REHACE, si se le pasó uno. Sin ilustrador el verificador sigue
        #: sirviendo: reporta y no toca nada, que es como se audita un lote ya hecho.
        self._illustrator = illustrator

    async def inspect(self, story: Story) -> list[Veredicto]:
        """Revisa cada escena ilustrada. Devuelve un veredicto por escena.

        No lanza: un cuento con una imagen dudosa se entrega igual, con el aviso en el
        log y en el veredicto. Quien orquesta decide qué hacer con eso.
        """
        personajes = story.characters_by_id
        veredictos: list[Veredicto] = []

        for escena in story.scenes:
            if not escena.image_path or not Path(escena.image_path).is_file():
                continue
            veredictos.append(await self._revisar(escena, story, personajes))

        malas = [v for v in veredictos if not v.paso]
        logger.info(
            "Verificación: %s de %s escenas sin reparos%s",
            len(veredictos) - len(malas),
            len(veredictos),
            f" · quedaron con reparo: {[v.escena for v in malas]}" if malas else "",
        )
        return veredictos

    # ------------------------------------------------------------------------
    async def _revisar(self, escena: Scene, story: Story, personajes: dict) -> Veredicto:
        """Mira una escena y, si hace falta y se puede, la rehace.

        Se queda con la primera imagen que pasa. Si ninguna pasa, deja la que MENOS
        reparos tuvo: rehacer no puede empeorar el resultado, que es lo que pasaría si
        se quedara con la última porque sí.
        """
        mejores = await self._mirar(escena, story, personajes)
        if not mejores or not self._puede_rehacer():
            return Veredicto(escena.index, mejores, intentos=1, resuelta=not mejores)

        original = Path(escena.image_path).read_bytes()
        mejor_imagen, mejor_reparos = original, mejores

        for intento in range(1, INTENTOS_DE_IMAGEN + 1):
            logger.warning(
                "Escena %s: %s. Se rehace la imagen (%s de %s).",
                escena.index,
                "; ".join(r.detalle for r in mejor_reparos),
                intento,
                INTENTOS_DE_IMAGEN,
            )
            try:
                nueva = await self._illustrator.rehacer(  # type: ignore[union-attr]
                    escena, story, correccion=_correccion(mejor_reparos)
                )
            except Exception as e:  # noqa: BLE001 — rehacer es una mejora, no un requisito
                logger.warning(
                    "Escena %s: no se pudo rehacer (%s). Queda la que había.", escena.index, e
                )
                break

            reparos = await self._mirar(escena, story, personajes)
            if not reparos:
                return Veredicto(escena.index, [], intentos=intento + 1, resuelta=True)
            if len(reparos) < len(mejor_reparos):
                mejor_imagen, mejor_reparos = nueva, reparos

        # Ninguna pasó: se deja la mejor de todas, que puede ser la original.
        Path(escena.image_path).write_bytes(mejor_imagen)
        return Veredicto(
            escena.index, mejor_reparos, intentos=INTENTOS_DE_IMAGEN + 1, resuelta=False
        )

    def _puede_rehacer(self) -> bool:
        return self._illustrator is not None and hasattr(self._illustrator, "rehacer")

    async def _mirar(self, escena: Scene, story: Story, personajes: dict) -> list[Reparo]:
        """Los reparos de la imagen que hay HOY en disco. Lista vacía es aprobada."""
        try:
            crudo = await con_reintentos(
                lambda: self._vision.inspect_image(
                    _pregunta(escena, personajes), _vistas(Path(escena.image_path)), system=SYSTEM
                ),
                al_reintentar=lambda n, e: logger.warning(
                    "Escena %s: el proveedor de visión falló (%s). Reintento %s.",
                    escena.index, e, n,
                ),
            )
        except Exception as e:  # noqa: BLE001 — sin verificación se sigue igual
            logger.warning(
                "Escena %s: no se pudo verificar la imagen (%s). Se da por buena.",
                escena.index, e,
            )
            return []

        return _reparos(_campos(crudo), escena, personajes)


# --------------------------------------------------------------------------- pedido
def _pregunta(escena: Scene, personajes: dict) -> str:
    """Las preguntas cuya respuesta el plan YA SABE.

    Es la idea entera del módulo: no se le pide al modelo que opine si la imagen está
    linda —eso no se puede verificar— sino que cuente cosas que el motor decidió antes
    de dibujar. Un conteo se compara; una opinión, no.
    """
    presentes = [personajes[c].name for c in escena.character_ids if c in personajes]
    imaginados = [personajes[c].name for c in escena.imagined_character_ids if c in personajes]

    lineas = [
        "Te paso dos vistas de la MISMA ilustración de un cuento infantil: la escena "
        "completa y un recorte ampliado de la mitad de abajo, donde se ven las patas.",
        "",
        "Contestá SOLO con estas líneas, sin agregar nada más:",
        "",
        "que_veo: <describí el cuerpo de cada personaje: de dónde sale cada miembro y "
        "dónde termina>",
        "anatomia: <ok|rota — 'rota' si algún personaje tiene miembros de más, "
        "duplicados, fusionados o que nacen de un lugar imposible>",
        "cual: <si dijiste 'rota', qué error concreto viste>",
        "personajes: <cuántos personajes con cara y actitud de personaje hay>",
        "dia: <si|no — si la escena transcurre de día, con cielo claro>",
        "texto: <si|no — si hay letras, palabras o números escritos en la imagen>",
    ]
    if escena.prop:
        lineas.append(f"objeto: <si|no — si se ve {escena.prop} en la escena>")

    lineas += [
        "",
        f"Para tu referencia, en la escena tendría que haber {len(presentes)} "
        f"personaje(s): {', '.join(presentes) or '—'}.",
    ]
    if imaginados:
        lineas.append(
            f"Además puede verse {', '.join(imaginados)} dentro de una burbuja de "
            "pensamiento: ése no cuenta como personaje presente."
        )
    return "\n".join(lineas)


def _vistas(png: Path) -> list[bytes]:
    """La escena entera y su mitad de abajo, ampliada.

    Las dos y no una: **sobre la imagen entera el modelo no ve las patas de más**.
    Medido contra los tres casos reales — a 1024×1536 escalada por la API, una pata
    extra ocupa poquísimos píxeles; ampliada la zona baja, el mismo modelo la describe.

    Si ffmpeg no está o falla, va sola la imagen entera: se pierde sensibilidad, no la
    verificación.
    """
    entera = png.read_bytes()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp) / "bajo.png"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(png),
                 "-vf", "crop=iw:ih*0.45:0:ih*0.5,scale=1024:-1", str(salida)],
                check=True, capture_output=True, timeout=60,
            )
            return [entera, salida.read_bytes()]
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(
            "No se pudo recortar %s (%s): se verifica sólo la vista entera.", png.name, e
        )
        return [entera]


# ------------------------------------------------------------------------ guardianes
def _campos(crudo: str) -> dict[str, str]:
    """Los renglones "clave: valor" que devolvió el modelo.

    Tolerante con lo de alrededor y estricto con cada línea, igual que el storyboard:
    un "Claro, acá va:" adelante no rompe nada, y lo que no se entiende no se usa.
    """
    salida: dict[str, str] = {}
    for linea in crudo.splitlines():
        if m := _RENGLON.match(linea):
            salida[m.group(1).lower()] = m.group(2).strip()
    return salida


def _reparos(campos: dict[str, str], escena: Scene, personajes: dict) -> list[Reparo]:
    """Qué NO coincide con lo que el plan decidió.

    Cada regla de acá se ganó mirando una salida real y ninguna se dispara con una
    respuesta ambigua: ante la duda la imagen pasa. El costo de dejar pasar una mala
    es que la vea Pablo —que es exactamente lo que pasa hoy—; el de rehacer una buena
    es un cuento que empeora solo, sin que nadie se entere.
    """
    reparos: list[Reparo] = []

    # --- anatomía: el caso que justifica el módulo ---------------------------
    if _es(campos.get("anatomia"), {"rota", "mal", "error"}):
        detalle = campos.get("cual") or "anatomía rota"
        reparos.append(Reparo(escena.index, "anatomia", f"anatomía rota — {detalle}"))

    # --- regla 1: elenco cerrado --------------------------------------------
    # Sólo si hay personajes DE MÁS. Que se vea uno menos es legítimo: en un plano
    # sobre el hombro o en un plano corto, el compañero puede quedar fuera de cuadro
    # o cortado por el borde, y el modelo lo cuenta o no según cuánto asome.
    esperados = len([c for c in escena.character_ids if c in personajes])
    if (vistos := _entero(campos.get("personajes"))) is not None and vistos > esperados:
        reparos.append(
            Reparo(
                escena.index,
                "elenco",
                f"se ven {vistos} personajes y la escena tiene {esperados}",
            )
        )

    # --- regla 2: el clima no cambia con la emoción --------------------------
    if _es(campos.get("dia"), _NO):
        reparos.append(Reparo(escena.index, "clima", "la escena no se ve de día"))

    # --- el negativo prohíbe texto en la imagen ------------------------------
    if _es(campos.get("texto"), _SI):
        reparos.append(Reparo(escena.index, "texto", "hay letras o palabras escritas"))

    # --- regla 7: el objeto que eligió el motor tiene que verse ---------------
    if escena.prop and _es(campos.get("objeto"), _NO):
        reparos.append(Reparo(escena.index, "objeto", f"no se ve {escena.prop}"))

    return reparos


def _es(valor: str | None, cuales: set[str] | frozenset[str]) -> bool:
    """Si la respuesta de una palabra dice que sí a alguna de `cuales`.

    Mira sólo la primera palabra: el modelo contesta "no" tanto como "no, la escena es
    de día", y las dos quieren decir lo mismo. Ausente o incomprensible es **falso**,
    porque un guardián que no entendió no puede acusar.
    """
    if not valor:
        return False
    primera = re.split(r"[^\wáéíóúñ]+", valor.strip().lower(), maxsplit=1)[0]
    return primera in cuales


def _entero(valor: str | None) -> int | None:
    """El número que trae la respuesta, o None si no hay uno claro."""
    if not valor:
        return None
    m = re.search(r"\d+", valor)
    return int(m.group()) if m else None


def _correccion(reparos: list[Reparo]) -> str:
    """El bloque que se le agrega al prompt para volver a pedir la imagen.

    **No se pide lo mismo otra vez**: eso ya se aprendió con las tomas de voz que
    nacían cortadas —el guardián las rechazaba, las pedía igual tres veces y frenaba
    la producción—. Al modelo hay que darle una orden realmente distinta, y acá la
    orden distinta es el error concreto que se vio en el intento anterior.
    """
    if not reparos:
        return ""
    partes = [f"- {r.detalle}" for r in reparos]
    return (
        "CORRECCIÓN — el intento anterior de esta misma imagen salió con estos "
        "errores:\n" + "\n".join(partes) + "\n"
        "Dibujá la escena de nuevo sin ellos. Prestá especial atención a la anatomía: "
        "cada personaje tiene exactamente cuatro extremidades (dos delanteras y dos "
        "traseras) y una sola cola, todas naciendo del cuerpo en su lugar, sin "
        "miembros sueltos, duplicados ni fusionados."
    )
