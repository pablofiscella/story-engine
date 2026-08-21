# story-engine

Motor de historias infantiles. Planifica, escribe, ilustra, narra y publica.

Una historia se crea **una vez** y sale en todos los formatos: short vertical, video
largo, audiolibro, libro ilustrado, imprimible de actividades, placa para feed. Y en
todos los canales: YouTube, Instagram, Facebook, TikTok, tienda propia.

```python
story = engine.generate(theme="dinosaurios", value="compartir", age=4, duration=30)

story.render.short()       # 9:16 para Shorts/Reels
story.render.audiobook()   # mp3 narrado
story.render.pdf()         # libro imprimible
story.publish.youtube()
```

## La idea que sostiene todo

**La IA no decide. La IA escribe.**

El motor decide primero la estructura completa — cuántas escenas, qué hace cada una,
cuánto dura, quién aparece, qué se siente — y recién después le pide a un modelo que
redacte la narración de cada escena, de a una y con contexto acotado.

```
        EL MOTOR DECIDE                      LA IA ESCRIBE
    ┌────────────────────┐              ┌────────────────────┐
    │ Escena 3           │              │                    │
    │ beat: intento      │   ──────►    │ "Dino estiró el    │
    │ duración: 5s       │              │  cuello, pero la   │
    │ lugar: el claro    │              │  fruta estaba muy  │
    │ personajes: Dino   │              │  alto..."          │
    │ emoción: frustración│             │                    │
    └────────────────────┘              └────────────────────┘
```

Pedirle a un modelo *"escribí un cuento de 30 segundos sobre compartir"* da resultados
que van de excelentes a irreproducibles. Pedirle *"escribí 5 segundos de narración para
esta escena, cuyo objetivo es que Dino intente alcanzar la fruta y se frustre"* da un
resultado consistente, historia tras historia. Esa diferencia es todo el proyecto.

## El arco narrativo

Toda historia sigue el mismo esqueleto. El planificador puede repetir un beat (dos
intentos fallidos) pero nunca alterar el orden:

```
gancho → problema → intento → error → aprendizaje → final
```

Un plan que no respeta el arco no llega a existir: `StoryPlan` se valida a sí mismo.
Un arco roto se detecta ahí, antes de gastar un peso en imágenes o audio.

## Estado

**Sprint 1 — Core.** El dominio: qué es una historia y qué la hace válida.

Sin IA, sin base de datos, sin framework web. La única dependencia es Pydantic.

```
engine/core/
├── enums.py          vocabulario cerrado (beats, emociones, canales, formatos)
├── constants.py      límites del dominio y el arco canónico
├── exceptions.py     errores de dominio vs. errores de proveedor
├── interfaces.py     contratos con el exterior (texto, imagen, voz, persistencia)
└── models/
    ├── story.py      ← la raíz: todo cuelga de acá
    ├── plan.py       ← el esqueleto narrativo (la pieza central)
    ├── scene.py      la escena escrita
    ├── character.py  personajes con descripción visual canónica
    ├── theme.py      temáticas (mundo, paleta, estilo)
    ├── metadata.py   identidad, estado y versión
    └── output.py     artefactos generados y dónde se publicaron
```

## Cómo se prueba

```bash
pip install -e ".[dev]"
pytest
```

El test más importante es `tests/test_referencia_storyboard.py`: reconstruye un short
real completo ("El dinosaurio que aprendió a compartir") con el modelo de dominio. Si
un cambio rompe la capacidad de representar ese short, rompimos el motor.

## Roadmap

| Fase | Módulo | Estado |
|---|---|---|
| 1 | Core — modelos y reglas | ✅ |
| 2 | Motor narrativo — planificador + escritor | ⬜ |
| 3 | Generación de imágenes | ⬜ |
| 4 | Narración y subtítulos | ⬜ |
| 5 | Render (FFmpeg) | ⬜ |
| 6 | Publicación y panel | ⬜ |

Las decisiones de arquitectura y su porqué están en [`docs/decisions/`](docs/decisions/).
