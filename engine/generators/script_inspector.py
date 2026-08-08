"""El verificador de GUION: el motor LEE lo que escribió, antes de pagar la voz.

Es el hermano de `inspector.py`. Aquél mira las imágenes; éste lee el texto. La idea
es la misma y es la que da todo el valor: **un modelo distinto del que escribe** lo
revisa, contesta preguntas concretas, y **quién decide si eso es un error es código
determinista** que compara contra lo que el guion realmente dice.

POR QUÉ EXISTE, con la frase que lo pidió. Pablo, 8-ago-2026, mirando los canales del
nicho devocional: *"el problema es cómo sabemos si el texto está bien"*. Él no juzga
inglés, y el guion sale en inglés. Sin esto, la única verificación del texto son los
guardianes de forma que ya había —que entre en los segundos, que no repita la primera
frase— y ninguno de los dos sabe si el inglés suena a inglés.

**El revisor NO es el escritor.** El escritor corre en `gpt-4o-mini` (barato, una
escena por vez); el revisor corre en `MODELO_DE_REVISION`. Es la misma regla que en
las imágenes: *quien produjo el error es el que menos chance tiene de verlo*. Y es
más fuerte todavía en texto — pedirle al mismo modelo que juzgue su propia prosa da
"suena natural" prácticamente siempre.

LA DIFERENCIA DE FORMA CON EL VERIFICADOR DE IMÁGENES, y es de fondo: las imágenes se
revisan **de a una** porque cada una se compara contra su propia escena. El guion se
revisa **ENTERO Y DE UNA VEZ**, porque las tres cosas que más lo arruinan sólo existen
mirando el conjunto:

- la **muletilla** es una frase que se repite entre escenas distintas: dentro de una
  sola escena no hay nada que ver;
- la **apertura** es una propiedad de la primera escena *en tanto* primera;
- el **cierre** es una propiedad de la última.

EL CASO REAL QUE LO CALIBRA, y está entero en `tests/test_script_inspector.py`: el
devocional de ansiedad generado el 7-ago-2026 (`out/devocional/ansiedad/`), 10 escenas
en inglés, revisado a mano el 8-ago-2026. Lo que tenía, medido:

1. **«Your eyes open… no worries, yet rest still eludes you»** (escena 1). En inglés
   *"no worries"* quiere decir *"tranquilo, no pasa nada"* — es lo que se contesta
   cuando alguien pide perdón. El propósito de la escena decía *"eyes open, nothing
   wrong, and still no rest"*: el modelo tradujo el sentido y eligió la locución que
   significa otra cosa. Es exactamente el error que Pablo no puede ver y el que
   justifica el módulo entero.
2. **«Take a moment»** (escenas 0 y 4) y **«when your heart»** (escenas 2 y 3).
   `aperturas_repetidas()` devuelve **cero** sobre este guion, y tiene razón: compara
   las TRES primeras palabras de cada escena, y la escena 0 abre con "If this
   message". La muletilla está en el medio de la frase, que es donde se esconde.
3. La escena 9 cierra con **«Can you feel it?»**, una pregunta retórica. El pedido de
   un acto concreto —*"type AMEN"*— vive en `closing_question` y llega igual al video,
   así que el guion pasa; pero el guardián tiene que mirar el cierre COMPLETO
   (narración final + moraleja + invitación) y no sólo la última escena, o acusa a un
   devocional bien armado.

**LO QUE ESTE PASO ENCUENTRA Y LO QUE NO**, corrido contra ese guion el 8-ago-2026 con
`gpt-5.2` de revisor y `temperature=0` — **8 reparos y 1 descarte**:

| de dónde salió | cuántos | qué |
|---|---:|---|
| guardián determinista | 2 | `take a moment` (0 y 4), `when your heart` (2 y 3) |
| el revisor, verificado | 6 | `no worries`, `Your eyes open`, `message found you`, `breaks gently`, `wraps around you` repetido, y el juicio de traducción |
| el revisor, descartado | 1 | una muletilla que el código fue a contar y no se repetía |

Tres cosas que sólo se supieron corriéndolo, y que valen más que el módulo:

1. **Pedir "los errores, uno por línea" devuelve UNO.** Con esa redacción, gpt-5.2
   contestó un solo error y se detuvo — y el que se saltó era `no worries`. Pidiendo
   *"TODOS los que encuentres, hasta CINCO"* y nombrando las locuciones hechas, la
   misma llamada al mismo modelo con la misma temperatura devuelve cinco. **Un modelo
   contesta la forma de la pregunta antes que su contenido.**
2. **El filtro anti-invento tiraba hallazgos buenos.** El guion se le muestra numerado
   (`[0] narración`) y el modelo cita numerado: `[1] It's 3 a.m…`. Esa cita no está
   literal en ninguna escena, así que se descartaban 4 de 5 errores reales. Un filtro
   que tira las citas buenas deja de ser un filtro y pasa a ser una venda.
3. **`errores:` viene solo en su renglón, con la lista debajo.** Con el parser que
   exigía valor en la misma línea, la clave quedaba en la anterior y **los cinco
   errores se perdían en silencio**: el verificador decía "todo bien" sobre un guion
   con cinco reparos, que es la peor falla posible en un guardián.

LOS TRES GUARDIANES DETERMINISTAS, que no necesitan modelo y por eso no fallan nunca
por falta de crédito ni de red:

    frases_repetidas()   la muletilla, contada y no opinada
    abre_saludando()     "hola / bienvenidos / buenos días a todos" al arranque
    pide_un_acto()       el cierre tiene un verbo de acción dirigido a quien mira

Y LA REGLA QUE ORDENA TODO LO DEMÁS: **toda frase que el revisor cite tiene que
existir, literal, en el guion.** Si cita algo que no está, se descarta y se anota en el
log. Un modelo que juzga prosa inventa citas con una facilidad que uno que cuenta patas
no tiene: sin este filtro, el verificador reescribiría escenas por errores imaginarios,
que es un producto que empeora solo y sin que nadie se entere.

Dos decisiones heredadas tal cual del verificador de imágenes:

1. **Un fallo del proveedor no frena la producción.** Si el revisor no contesta o
   contesta algo que no se entiende, el guion se da por bueno y sigue. Los guardianes
   deterministas corren igual — son código, no una llamada.
2. **El modelo describe; el código decide.** Lo que no se entiende, no se usa.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from engine.core.interfaces import TextProvider
from engine.core.models.story import Story
from engine.core.retry import con_reintentos

logger = logging.getLogger(__name__)

#: Cuántas veces se reescribe una escena con reparos antes de darse por vencido.
#:
#: DOS, igual que las imágenes y por la misma razón medida: si con el reparo dicho
#: explícito el modelo insiste dos veces, la tercera no lo arregla. Cuando se agotan,
#: queda la versión con MENOS reparos —que puede ser la original— y se avisa. Nunca se
#: frena el devocional por una escena.
INTENTOS_DE_ESCENA = 2

#: Cuántas palabras seguidas iguales, en dos escenas distintas, cuentan como muletilla.
#:
#: **TRES, y salió de medir, no de elegir.** Corrido sobre el devocional real del
#: 7-ago-2026 (10 escenas, `out/devocional/ansiedad/historia.json`):
#:
#: | n | repeticiones | qué son |
#: |---|---|---|
#: | 2 | 10 | armazón del idioma: "a moment", "your heart", "you feel", "god i" |
#: | 3 | **2** | "take a moment" (escenas 0 y 4) y "when your heart" (2 y 3) |
#: | 4 | 0 | nada |
#:
#: Con 3 salen exactamente las dos que un humano marcaría leyendo, y ninguna de más.
PALABRAS_DE_MULETILLA = 3

#: Cuántas palabras "con contenido" tiene que tener la frase repetida para que cuente.
#:
#: Es un piso, no la palanca principal, y conviene decirlo con el número medido: sobre
#: el guion del 7-ago-2026 **a n=3 no cambia nada** (2 repeticiones con filtro y sin
#: él), y a n=2 corta la mitad del ruido (20 → 10). O sea que lo que hace el trabajo es
#: `PALABRAS_DE_MULETILLA`, y esto está para que un guion largo —40 escenas en vez de
#: 10— no empiece a acusar trigramas de armazón sólo porque hay cuatro veces más texto
#: donde puedan chocar.
CONTENIDO_MINIMO = 1

#: Palabras de función que no alcanzan para que una repetición sea una muletilla.
#: Inglés y español juntos: el motor narra en los dos y un guardián determinista no
#: puede depender de que alguien se acuerde de decirle el idioma.
_FUNCION = frozenset({
    # inglés
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "at", "to", "for",
    "with", "from", "by", "as", "is", "are", "was", "were", "be", "been", "am", "do",
    "does", "did", "not", "no", "you", "your", "yours", "i", "me", "my", "mine", "we",
    "us", "our", "he", "she", "it", "its", "they", "them", "their", "this", "that",
    "these", "those", "there", "here", "have", "has", "had", "will", "would", "can",
    "could", "may", "might", "shall", "should", "must", "so", "than", "then", "when",
    "what", "who", "how", "all", "any", "each", "more", "very", "just", "yet", "still",
    "into", "out", "up", "down", "over", "about", "like", "let", "even", "only",
    # español
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "con",
    "por", "para", "sin", "sobre", "y", "e", "o", "u", "que", "su", "sus", "mi", "tu",
    "lo", "se", "más", "pero", "al", "es", "son", "está", "están", "ser", "estar",
    # "me" y "no" ya están arriba: se escriben igual en los dos idiomas.
    "te", "nos", "vos", "yo", "él", "ella", "ellos", "sí", "si", "ya",
    "cuando", "como", "porque", "esto", "esta", "este", "eso", "esa", "ese",
})

#: Con qué se abre un devocional del nicho: mandando parar, no saludando.
#:
#: Medido sobre los subtítulos automáticos de los seis mejores canales del nicho
#: (8-ago-2026): cuatro de seis arrancan con *"Before…"* — *"Before you rush into this
#: day, stop for just one moment"*—, **ninguno dice "hola" y ninguno dice el nombre del
#: canal**. Se entra en el estado, no en el video. Es lo contrario de un tutorial de
#: YouTube, y es lo que hace que alguien que venía scrolleando frene.
_SALUDOS = (
    "hello", "hi ", "hey", "welcome", "good morning everyone", "good evening everyone",
    "what's up", "whats up", "greetings",
    "hola", "buenos días a todos", "buenas noches a todos", "bienvenidos",
    "bienvenidas", "qué tal", "que tal",
)

#: Verbos con los que el cierre le pide un acto a quien mira.
#:
#: El nicho se eligió por su 1,718 % de comentarios contra el 0,000 % del infantil, y
#: eso sale de una línea: GOD REVEALED cierra con *"Type it in the comments.
#: Declare…"*. Un cierre que sólo bendice tiene likes altos y menos comentarios
#: (Morning Grace Daily, medido el 8-ago-2026). O sea que esto no es una preferencia
#: de estilo: es la métrica por la que se eligió el nicho.
_VERBOS_DE_ACTO = (
    "comment", "type", "write", "share", "say", "declare", "repeat", "reply", "post",
    "tell me", "send",
    "comentá", "comenta", "escribí", "escribe", "compartí", "comparte", "decí", "dime",
    "repetí", "repite", "respondé", "responde",
)

SYSTEM = (
    "Sos el control de calidad de un estudio que produce devocionales en inglés para "
    "adultos, narrados por una voz sola sobre una imagen fija. Quien los publica NO "
    "habla inglés: si vos no marcás un error de idioma, ese error sale publicado.\n\n"
    "Leé el guion como lo leería un hablante nativo que lo va a ESCUCHAR, no como un "
    "corrector de estilo. Lo que buscás es lo que delata a una máquina: locuciones "
    "usadas con el sentido equivocado, calcos de otro idioma, frases que ningún nativo "
    "diría en voz alta, y frases que el propio guion repite.\n\n"
    "Citá SIEMPRE copiando el texto EXACTO del guion, caracter por caracter. No "
    "parafrasees ni corrijas al citar: si citás algo que no está literal en el guion, "
    "esa observación se descarta entera."
)

#: Un renglón "clave: valor". Estricto a propósito: lo que no entra en este formato no
#: se usa para decidir nada. Copiado del verificador de imágenes, que ya probó que
#: tolerar el "Claro, acá va:" de adelante y nada más es el punto justo.
#:
#: **El valor puede venir VACÍO, y esa es la única diferencia con el de las imágenes.**
#: Cuando se le pide una lista, gpt-5.2 contesta a veces `errores:` solo en su renglón
#: y los errores en los renglones de abajo. Con `(.+?)` ese renglón no matcheaba, la
#: clave quedaba en la anterior y **los cinco errores se perdían enteros**: el
#: verificador reportaba "todo bien" sobre un guion con cinco reparos, que es la peor
#: falla posible en un guardián. Sigue exigiendo UNA palabra pegada a los dos puntos,
#: así que una frase con dos puntos en el medio no se confunde con una clave.
_RENGLON = re.compile(r"^\s*[-*`]*\s*([a-z_]+)\s*:\s*(.*?)\s*[`]*\s*$", re.IGNORECASE)

#: Qué cuenta como "no hay nada que reportar". El modelo contesta de las dos formas.
_NADA = frozenset({"ninguna", "ninguno", "none", "no", "n/a", "-", "—", ""})

#: Los registros que un devocional puede tener sin que sea un reparo.
#:
#: `intimo` es el que se busca; `neutro` pasa porque un guardián que exige entusiasmo
#: en la respuesta de una palabra termina reescribiendo escenas que están bien. Lo que
#: se rechaza es lo que el nicho NO es: un tutorial que explica, un sermón que reta y
#: una publicidad que vende.
_REGISTROS_OK = frozenset({"intimo", "íntimo", "intimate", "neutro", "neutral", "calmo"})


@dataclass(frozen=True)
class ReparoDeGuion:
    """Algo que el guion tiene mal, con la regla que rompe y dónde está.

    `escena` es `None` cuando el reparo es del guion entero y no de una escena: el
    registro equivocado o un cierre que no pide nada no se arreglan reescribiendo una
    escena suelta.
    """

    regla: str
    detalle: str
    escena: int | None = None

    def __str__(self) -> str:
        donde = f"escena {self.escena}" if self.escena is not None else "el guion"
        return f"{donde}: {self.detalle}"


@dataclass
class VeredictoDeGuion:
    """Cómo le fue al guion, con lo que se reescribió."""

    reparos: list[ReparoDeGuion] = field(default_factory=list)
    reescritas: list[int] = field(default_factory=list)
    intentos: int = 1
    #: Lo que el revisor dijo y el código NO pudo verificar contra el guion. No es
    #: ruido: es la medida de cuánto inventa el modelo, y sin anotarla no se puede
    #: saber si el revisor sirve.
    descartados: list[str] = field(default_factory=list)

    @property
    def paso(self) -> bool:
        return not self.reparos


class ScriptInspector:
    """Lee el guion de una historia y reescribe las escenas que no pasan."""

    def __init__(self, reviewer: TextProvider, writer: object | None = None) -> None:
        #: Quien LEE. Conviene —y para esto está el parámetro— que no sea el mismo
        #: modelo que escribió.
        self._reviewer = reviewer
        #: Quien REESCRIBE, si se le pasó uno. Sin escritor el verificador sigue
        #: sirviendo: reporta y no toca nada, que es como se audita un guion ya hecho.
        self._writer = writer

    async def inspect(
        self, story: Story, *, sistema_de_escritura: str | None = None
    ) -> VeredictoDeGuion:
        """Revisa el guion entero. Devuelve un veredicto, y no lanza.

        `sistema_de_escritura` es el prompt de narrador con el que se escribió: hay que
        pasárselo para reescribir con el mismo, o el devocional se reescribe con voz de
        cuentacuentos.
        """
        veredicto = VeredictoDeGuion()
        mejores = self._separar(await self._revisar(story), veredicto)
        veredicto.reparos = mejores

        if not mejores or not self._puede_reescribir():
            _avisar(veredicto)
            return veredicto

        #: El guion tal como llegó, y la mejor versión conocida. Reescribir MUTA el
        #: texto de la escena, así que sin esta copia una vuelta que empeora deja el
        #: producto peor de lo que estaba y nadie se entera. Es exactamente lo que el
        #: verificador de imágenes hace con los bytes de la imagen original.
        original = _texto_de(story)
        mejor_texto = list(original)

        for intento in range(1, INTENTOS_DE_ESCENA + 1):
            porescena = _por_escena(mejores, len(story.scenes))
            if not porescena:
                break  # sólo quedan reparos del guion entero: no hay qué reescribir

            _restaurar(story, mejor_texto)
            for i, suyos in sorted(porescena.items()):
                logger.warning(
                    "Escena %s: %s. Se reescribe (%s de %s).",
                    i, "; ".join(r.detalle for r in suyos), intento, INTENTOS_DE_ESCENA,
                )
                try:
                    await self._writer.reescribir(  # type: ignore[union-attr]
                        story.scenes[i],
                        story,
                        correccion=_correccion(suyos),
                        sistema=sistema_de_escritura,
                        anterior=story.scenes[i - 1].narration if i > 0 else None,
                    )
                except Exception as e:  # noqa: BLE001 — reescribir es una mejora, no un requisito
                    logger.warning(
                        "Escena %s: no se pudo reescribir (%s). Queda la que había.", i, e
                    )

            nuevos = self._separar(await self._revisar(story), veredicto)
            veredicto.intentos = intento + 1
            # Se acepta la vuelta SÓLO si mejoró. Una reescritura puede traer un reparo
            # nuevo —tres escenas corregidas con la misma idea son una muletilla nueva—
            # y quedarse con la última porque sí sería una fábrica de ruido.
            if len(nuevos) < len(mejores):
                mejores, mejor_texto = nuevos, _texto_de(story)
            if not mejores:
                break

        _restaurar(story, mejor_texto)
        veredicto.reparos = mejores
        veredicto.reescritas = [
            i for i, (antes, ahora) in enumerate(zip(original, mejor_texto, strict=True))
            if antes != ahora
        ]
        _avisar(veredicto)
        return veredicto

    async def _revisar(self, story: Story) -> list[ReparoDeGuion]:
        """Una pasada completa: los guardianes deterministas y el revisor."""
        return self._deterministas(story) + await self._del_revisor(story)

    def _separar(
        self, reparos: list[ReparoDeGuion], veredicto: VeredictoDeGuion
    ) -> list[ReparoDeGuion]:
        """Aparta lo que el revisor citó mal. Se cuenta, pero no acusa a nadie."""
        veredicto.descartados += [r.detalle for r in reparos if r.regla == "descartado"]
        return [r for r in reparos if r.regla != "descartado"]

    def _puede_reescribir(self) -> bool:
        return self._writer is not None and hasattr(self._writer, "reescribir")

    # ------------------------------------------------------------------ deterministas
    def _deterministas(self, story: Story) -> list[ReparoDeGuion]:
        """Los guardianes que no preguntan: miden. Corren siempre, aun sin revisor."""
        narraciones = [e.narration for e in story.scenes]
        reparos: list[ReparoDeGuion] = []

        for frase, escenas in frases_repetidas(narraciones):
            reparos.append(
                ReparoDeGuion(
                    "muletilla",
                    f"«{frase}» se repite en las escenas {escenas}",
                    escena=escenas[-1],
                )
            )

        if narraciones and abre_saludando(narraciones[0]):
            reparos.append(
                ReparoDeGuion(
                    "apertura",
                    "el guion abre saludando; el nicho abre mandando parar",
                    escena=0,
                )
            )

        if not pide_un_acto(_cierre_completo(story)):
            reparos.append(
                ReparoDeGuion("cierre", "el cierre no le pide ningún acto a quien mira")
            )
        return reparos

    # ---------------------------------------------------------------------- revisor
    async def _del_revisor(self, story: Story) -> list[ReparoDeGuion]:
        """Lo que dijo el modelo, ya filtrado contra lo que el guion dice de verdad."""
        narraciones = [e.narration for e in story.scenes]
        try:
            crudo = await con_reintentos(
                lambda: self._reviewer.generate_text(
                    _pregunta(story), system=SYSTEM, temperature=0.0
                ),
                al_reintentar=lambda n, e: logger.warning(
                    "El revisor de guion falló (%s). Reintento %s.", e, n
                ),
            )
        except Exception as e:  # noqa: BLE001 — sin revisión se sigue igual
            logger.warning("No se pudo revisar el guion (%s). Se da por bueno.", e)
            return []
        return _reparos(_campos(crudo), narraciones)


# --------------------------------------------------------------------------- pedido
def _pregunta(story: Story) -> str:
    """Las preguntas que Pablo haría si leyera inglés.

    Todas piden una CITA además del juicio, y ahí está la mitad del diseño: "¿suena
    natural?" sola devuelve una opinión que no se puede verificar ni corregir. Con la
    frase exacta al lado, el código puede comprobar que exista y el escritor puede
    recibir el error concreto en vez de un "mejoralo".
    """
    guion = "\n".join(f"[{e.index}] {e.narration}" for e in story.scenes)
    cierre = _cierre_completo(story)

    return (
        f"Guion de un devocional, una escena por línea con su número:\n\n{guion}\n\n"
        f"El video termina diciendo, después de la última escena:\n«{cierre}»\n\n"
        "Contestá SOLO con estas líneas, sin agregar nada más:\n\n"
        "natural: <nativo|traducido — 'traducido' si alguna frase se lee como "
        "traducida de otro idioma o como escrita por alguien que no habla inglés>\n"
        "cual_traducida: <la frase EXACTA del guion que suena traducida, copiada tal "
        "cual, o 'ninguna'>\n"
        "registro: <intimo|tutorial|sermon|publicidad — íntimo y pausado es lo "
        "buscado: alguien hablándole bajo a UNA persona. 'tutorial' si explica o "
        "enseña, 'sermon' si reta o exige, 'publicidad' si vende o promete>\n"
        # **"TODOS, hasta cinco" no es una formalidad: es la diferencia medida entre
        # encontrar un error y encontrar cinco.** Con el pedido en singular ("uno por
        # línea"), gpt-5.2 devolvió sobre el guion real del 7-ago-2026 UN solo error y
        # se detuvo — y el que se le escapó era justo `no worries`, la locución usada
        # con el sentido de otro idioma, que es el error que este módulo existe para
        # encontrar. Con este párrafo, la misma llamada al mismo modelo con
        # temperatura 0 devuelve cinco, `no worries` incluido. Un modelo contesta la
        # forma de la pregunta antes que su contenido.
        "errores: <los errores de gramática, concordancia, tiempo verbal o uso de una "
        "locución con el sentido equivocado. Uno por línea, con el formato "
        "«frase exacta del guion || qué está mal». Listá TODOS los que encuentres, "
        "hasta CINCO. Mirá especialmente las LOCUCIONES HECHAS: una locución usada con "
        "el sentido que tiene en otro idioma es el error más caro de todos, porque deja "
        "el texto gramaticalmente perfecto. Si no hay ninguno, escribí 'ninguno'>\n"
        "muletilla: <la frase de tres o más palabras que el guion repite en escenas "
        "distintas, copiada exacta del guion, o 'ninguna'>\n"
        "apertura: <parar|saludo|otro — 'parar' si la escena 0 le pide a quien "
        "escucha que frene lo que está haciendo; 'saludo' si lo saluda o se presenta>\n"
        "cierre_pide: <si|no — si el final le pide a quien mira un acto concreto y "
        "verificable, como escribir una palabra en los comentarios>\n"
    )


def _cierre_completo(story: Story) -> str:
    """Todo lo que se dice después de la última escena, junto.

    La última narración, la promesa y la invitación. Van juntas porque **así se
    escuchan**: el guardián del cierre tiene que juzgar lo que oye quien mira, no un
    campo del modelo. Mirando sólo la última escena, el devocional del 7-ago-2026
    —que cierra con "Can you feel it?" y pide "type AMEN" un renglón después— salía
    reprobado por un error que no existe.
    """
    partes = [story.scenes[-1].narration] if story.scenes else []
    partes += [t for t in (story.moral, story.closing_question) if t]
    return " ".join(partes)


# ------------------------------------------------------------------------ guardianes
def _campos(crudo: str) -> dict[str, str]:
    """Los renglones "clave: valor" que devolvió el revisor.

    `errores` puede traer VARIAS líneas y por eso se acumulan con `\\n` en vez de
    pisarse: es el único campo donde el modelo tiene permiso de contestar más de una
    cosa, porque un guion con tres errores tiene tres errores.

    Y las trae de las DOS formas, según el día: repitiendo `errores:` en cada renglón,
    o poniendo `errores:` una vez y la lista debajo. Las dos se aceptan; lo que decide
    que un renglón suelto pertenece a la lista es que traiga el separador `||`, que es
    el formato que se pidió.
    """
    salida: dict[str, str] = {}
    clave = ""
    for linea in crudo.splitlines():
        if m := _RENGLON.match(linea):
            clave = m.group(1).lower()
            salida[clave] = (
                f"{salida[clave]}\n{m.group(2).strip()}"
                if clave == "errores" and clave in salida
                else m.group(2).strip()
            )
        elif clave == "errores" and "||" in linea:
            salida["errores"] = f"{salida.get('errores', '')}\n{linea.strip()}"
    return salida


def _reparos(campos: dict[str, str], narraciones: list[str]) -> list[ReparoDeGuion]:
    """Qué de lo que dijo el revisor sobrevive al contraste con el guion.

    La regla que ordena todo: **una cita que no está en el guion no vale**. Se devuelve
    como un reparo de regla `descartado` para poder contarlos —cuánto inventa el
    revisor es un dato que hay que tener— y quien llama los separa.
    """
    reparos: list[ReparoDeGuion] = []

    # --- suena a traducción: el caso que justifica el módulo -------------------
    if _es(campos.get("natural"), {"traducido", "translated", "no"}):
        cita = campos.get("cual_traducida", "")
        i = _ubicar(cita, narraciones)
        if i is None:
            reparos.append(ReparoDeGuion("descartado", f"traducción sin cita real: {cita!r}"))
        else:
            reparos.append(
                ReparoDeGuion("traduccion", f"suena a traducción: «{cita.strip()}»", escena=i)
            )

    # --- registro: es del guion entero, no de una escena -----------------------
    registro = (campos.get("registro") or "").strip().lower().split()[0] if campos.get(
        "registro"
    ) else ""
    if registro and registro not in _REGISTROS_OK:
        reparos.append(
            ReparoDeGuion("registro", f"el registro es «{registro}» y tiene que ser íntimo")
        )

    # --- errores de idioma: cada uno con su frase, y cada frase verificada ------
    for linea in (campos.get("errores") or "").splitlines():
        if not linea.strip() or _vacio(linea):
            continue
        frase, _, motivo = linea.partition("||")
        i = _ubicar(frase, narraciones)
        if i is None:
            reparos.append(ReparoDeGuion("descartado", f"error sin cita real: {linea.strip()!r}"))
            continue
        reparos.append(
            ReparoDeGuion(
                "idioma",
                f"«{frase.strip()}» — {motivo.strip() or 'error de idioma'}",
                escena=i,
            )
        )

    # --- muletilla: el revisor la nombra, el código la CUENTA -------------------
    # No alcanza con que exista: tiene que aparecer en DOS escenas distintas. Si el
    # revisor marca como repetida una frase que está una sola vez, se descarta.
    cita = campos.get("muletilla", "")
    if not _vacio(cita):
        escenas = _escenas_con(cita, narraciones)
        if len(escenas) < 2:
            reparos.append(
                ReparoDeGuion("descartado", f"muletilla que no se repite: {cita.strip()!r}")
            )
        else:
            reparos.append(
                ReparoDeGuion(
                    "muletilla",
                    f"«{cita.strip()}» se repite en las escenas {escenas}",
                    escena=escenas[-1],
                )
            )

    # --- apertura y cierre: el revisor confirma lo que ya miran los deterministas.
    # Sólo se le hace caso cuando ACUSA: si dice que está bien y el guardián
    # determinista dice que está mal, manda el determinista — es el que mide.
    if _es(campos.get("apertura"), {"saludo", "greeting", "hola"}):
        reparos.append(
            ReparoDeGuion("apertura", "la primera escena saluda en vez de mandar parar", escena=0)
        )
    return reparos


def frases_repetidas(
    narraciones: list[str], n: int = PALABRAS_DE_MULETILLA
) -> list[tuple[str, list[int]]]:
    """Las frases de `n` palabras que aparecen en más de una escena.

    Es `aperturas_repetidas()` llevado adentro de la frase. Aquélla compara sólo las
    TRES PRIMERAS palabras de cada escena, y sobre el devocional real del 7-ago-2026
    devuelve **cero** — que es lo que se anotó en el diario como "ninguna escena abre
    como otra". Es cierto y no alcanza: el mismo guion repite

        escena 0: "…it wasn't by chance. Take a moment… just sixty seconds."
        escena 4: "Take a moment to breathe. God, I bring this thought to You…"

    —que `aperturas_repetidas` no ve porque en la escena 0 la frase está en el MEDIO— y

        escena 2: "…pretending everything is fine when your heart carries a weight."
        escena 3: "It's hard to find peace when your heart is restless."

    que no está cerca de ningún principio. Las dos las devuelve esta función.

    **Lo que NO caza, dicho para que nadie se confíe:** la repetición que cambia una
    letra. El mismo guion dice *"let the stillness wrap around you"* (escena 0) y *"The
    stillness wraps around you"* (escena 3), y para este guardián son frases distintas.
    Eso queda del lado del revisor, que sí lee; acá no se stemiza a propósito, porque
    un guardián determinista que empieza a normalizar morfología deja de ser
    verificable de un vistazo.

    Determinista y pura, como los guardianes del storyboard: no pregunta, cuenta.
    Devuelve `(frase, [escenas])` ordenado por dónde aparece primero.
    """
    vistas: dict[str, list[int]] = {}
    for i, narracion in enumerate(narraciones):
        palabras = _palabras(narracion)
        for j in range(len(palabras) - n + 1):
            grupo = palabras[j : j + n]
            if sum(1 for p in grupo if p not in _FUNCION) < CONTENIDO_MINIMO:
                continue
            frase = " ".join(grupo)
            if i not in vistas.setdefault(frase, []):
                vistas[frase].append(i)

    repetidas = [(f, e) for f, e in vistas.items() if len(e) > 1]
    return sorted(repetidas, key=lambda x: (x[1][0], x[0]))


def abre_saludando(primera: str) -> bool:
    """Si la primera frase saluda en vez de mandar parar.

    Mira sólo el ARRANQUE (las primeras palabras): "hi" adentro de la escena puede ser
    parte de una frase legítima, y un guardián que acusa por eso obliga a apagarlo.
    """
    inicio = " ".join(_palabras(primera)[:6])
    return any(inicio.startswith(s.strip()) or f" {s.strip()} " in f" {inicio} " for s in _SALUDOS)


def pide_un_acto(cierre: str) -> bool:
    """Si el cierre le pide a quien mira algo que se pueda hacer.

    Se busca un verbo de acción dirigido a la audiencia. Es tosco a propósito: un
    guardián determinista que intente entender la intención de una frase se equivoca
    más de lo que acierta, y acá el costo de un falso positivo es reescribir un cierre
    que estaba bien.
    """
    texto = f" {' '.join(_palabras(cierre))} "
    return any(f" {v.strip()} " in texto for v in _VERBOS_DE_ACTO)


# --------------------------------------------------------------------------- utils
def _palabras(texto: str) -> list[str]:
    """Las palabras, en minúscula y sin puntuación.

    Los apóstrofos tipográficos (’) y los rectos (') se borran los dos: el modelo mezcla
    las dos formas en el mismo guion —"wasn't" y "wasn’t"— y sin normalizarlos "doesn't
    stop" y "doesn’t stop" son dos frases distintas para el guardián de muletillas.
    """
    limpio = "".join(
        c.lower() if (c.isalnum() or c.isspace()) else (" " if c not in "'’" else "")
        for c in texto
    )
    return limpio.split()


def _normalizar(texto: str) -> str:
    return " ".join(_palabras(texto))


def _ubicar(cita: str, narraciones: list[str]) -> int | None:
    """En qué escena está `cita`, comparando sin puntuación ni mayúsculas.

    Sin normalizar, el filtro anti-invento rechazaría citas correctas: el revisor
    escribe *"no worries, yet rest still eludes you"* donde el guion tiene los mismos
    caracteres con otra comilla o sin la coma final. Lo que se exige es que las
    PALABRAS estén, en ese orden — que es lo que hace falta para poder corregirlas.
    """
    escenas = _escenas_con(cita, narraciones)
    return escenas[0] if escenas else None


#: El "[3]" con el que se numeran las escenas al mostrarle el guion al revisor.
#:
#: **Hay que sacarlo de las citas, y esto costó cuatro hallazgos buenos.** El guion se
#: le muestra al modelo como `[0] narración`, y en algunas corridas devuelve la cita
#: con el número adelante: *"[1] It's 3 a.m. Your eyes open… no worries…"*. Esa cita no
#: está literal en ninguna narración —la narración no empieza con "1"— así que el
#: filtro anti-invento la descartaba. Medido sobre el guion real del 7-ago-2026: **4 de
#: 5 errores de idioma se perdían así, incluido `no worries`**, que es el que justifica
#: el módulo.
#:
#: Es la misma lección que ya dejó la muletilla del prompt de narración, del otro lado:
#: **el modelo copia la FORMA de lo que se le muestra**. Si se le enseña el guion
#: numerado, cita numerado.
_MARCA_DE_ESCENA = re.compile(r"^\s*[\[(]?\s*(\d{1,2})\s*[\])]?\s*[:.\-]?\s*")


def _escenas_con(cita: str, narraciones: list[str]) -> list[int]:
    """Todas las escenas donde aparece `cita`, normalizada y sin su número de escena."""
    aguja = _normalizar(_MARCA_DE_ESCENA.sub("", cita.strip()))
    if not aguja:
        return []
    return [i for i, n in enumerate(narraciones) if aguja in _normalizar(n)]


def _es(valor: str | None, cuales: set[str] | frozenset[str]) -> bool:
    """Si la respuesta de una palabra dice que sí a alguna de `cuales`.

    Mira sólo la primera palabra, igual que en el verificador de imágenes: ausente o
    incomprensible es **falso**, porque un guardián que no entendió no puede acusar.
    """
    if not valor:
        return False
    primera = re.split(r"[^\wáéíóúñ]+", valor.strip().lower(), maxsplit=1)[0]
    return primera in cuales


def _vacio(valor: str | None) -> bool:
    """Si la respuesta es alguna de las formas de decir "no hay nada"."""
    return (valor or "").strip().strip(".").lower() in _NADA


def _texto_de(story: Story) -> list[str]:
    """Las narraciones de todas las escenas, para poder volver atrás."""
    return [e.narration for e in story.scenes]


def _restaurar(story: Story, textos: list[str]) -> None:
    """Deja el guion como estaba en `textos`.

    El subtítulo se recalcula desde la narración y no se guarda aparte: tenerlo en dos
    lados sería una segunda fuente de verdad del mismo texto, que es como se llegó a
    que un video dijera una cosa y mostrara otra.
    """
    from engine.generators.writer import _subtitulo

    for escena, texto in zip(story.scenes, textos, strict=True):
        if escena.narration != texto:
            escena.narration = texto
            escena.subtitle = _subtitulo(texto)


def _por_escena(
    reparos: list[ReparoDeGuion], cuantas: int
) -> dict[int, list[ReparoDeGuion]]:
    """Los reparos agrupados por escena. Los del guion entero quedan afuera."""
    porescena: dict[int, list[ReparoDeGuion]] = {}
    for r in reparos:
        if r.escena is not None and 0 <= r.escena < cuantas:
            porescena.setdefault(r.escena, []).append(r)
    return porescena


def _correccion(reparos: list[ReparoDeGuion]) -> str:
    """El bloque que se le agrega al pedido para volver a escribir la escena.

    Lleva el error CONCRETO y, sobre todo, **la frase que no puede volver a usar**. Es
    la misma lección que dejó la muletilla del 7-ago-2026 al revés: si el ejemplo pesa
    más que el contexto, entonces nombrar la frase prohibida es lo único que la saca.
    """
    partes = [f"- {r.detalle}" for r in reparos]
    return (
        "CORRECCIÓN — la versión anterior de esta misma escena salió con estos "
        "problemas:\n" + "\n".join(partes) + "\n"
        "Escribila de nuevo sin ellos, con el mismo propósito y el mismo límite de "
        "palabras. NO reuses ninguna de las frases citadas arriba: cambiá la idea de "
        "lugar, no le cambies una palabra."
    )


def _avisar(veredicto: VeredictoDeGuion) -> None:
    logger.info(
        "Verificación del guion: %s reparo(s)%s%s",
        len(veredicto.reparos),
        f" · reescritas: {veredicto.reescritas}" if veredicto.reescritas else "",
        f" · descartados por cita inventada: {len(veredicto.descartados)}"
        if veredicto.descartados
        else "",
    )
