# 0002 — Las reglas duras del prompt de imagen

**Fecha:** 2026-08-05 · **Estado:** aceptado · **Sprint:** 3

Este documento no salió de una discusión de arquitectura. Salió de mirar el primer
cuento ilustrado de verdad que produjo el motor —6 escenas, dinosaurios, valor
compartir— y anotar todo lo que estaba mal.

Los cuatro errores tienen la **misma causa de fondo**, y por eso vale la pena
escribirlos juntos: el texto y la imagen se generan por caminos separados, y cada uno
sabe cosas que el otro no. Cada vez que uno de los dos decide algo que el otro no se
entera, la ilustración contradice al cuento.

La regla general, entonces:

> **Todo lo que aparece en la imagen tiene que estar dicho en el prompt, y el prompt
> tiene que estar hecho de lo que el cuento realmente dice.**

Lo que sigue son los cuatro casos concretos. Cada uno tiene su test en
`tests/test_reglas_de_imagen.py`, con el bug que lo originó escrito en el docstring.

---

## 1. Elenco cerrado

**Qué pasó:** la última escena decía *"los dos juegan juntos"*, pero el plan tenía un
solo personaje en `character_ids`. El prompt describía a Dino nada más. El modelo, que
necesitaba dos dinosaurios para ilustrar la frase, agarró uno del fondo de la imagen
de referencia y lo ascendió a personaje. Salió un dinosaurio que no era Rexo.

**La causa:** la plantilla del propósito decía *"Los dos juegan"* en texto plano. El
planificador arma el elenco buscando `{companero}` en la plantilla — sin esa marca, no
tenía cómo saber que hacían falta dos.

**La regla:** el prompt declara el número exacto y nombra a cada uno.

```
EN LA ESCENA HAY EXACTAMENTE 2 personajes: Dino y Rexo.
No agregues ningún otro personaje ni criatura con protagonismo
```

Y el negativo prohíbe explícitamente `animales de fondo con cara o actitud de
personaje` — un dinosaurio pastando lejos está bien, uno mirando a cámara no.

Un test recorre los 8 perfiles de valor y falla si alguna plantilla habla de dos
personajes sin nombrar al compañero. La regla se hace cumplir en los datos, no en la
buena memoria del que agregue el noveno valor.

---

## 2. La emoción va en la cara, no en el clima

**Qué pasó:** la escena del error salió nublada. El cuento nunca dijo que se nublara.

**La causa:** había una función `_clima()` que traducía cada emoción a una atmósfera.
Para la frustración devolvía literalmente *"cielo algo gris, luz apagada"*. Estaba
haciendo exactamente lo que se le pidió; el problema era lo que se le pidió.

**La regla:** el escenario, la hora del día y el clima son los mismos en toda la
historia salvo que el cuento diga otra cosa. La emoción se muestra en la cara y la
postura. `_clima()` pasó a llamarse `_actitud()` y devuelve solo cuerpo y gesto
(*"cejas caídas, mirada baja, hombros hundidos"*).

Un test recorre las 8 emociones y falla si alguna menciona cielo, nublado, gris,
atardecer, lluvia o tonos fríos.

---

## 3. La imagen ilustra lo que se narra, no lo que el motor ordenó

**Qué pasó:** la narración decía *"Rexo miraba la pelota, pero Dino no quería
compartirla"*. La imagen mostró a Rexo sacándole la pelota de las manos.

**La causa:** el prompt se componía con `scene.purpose` —la orden interna del motor,
*"Rexo quiere jugar y Dino se niega"*— en lugar de con `scene.narration`. El propósito
es una instrucción para el escritor, no una descripción de lo que se ve. "Se niega"
admite muchas imágenes; solo una coincide con el texto.

**La regla:** el prompt usa `scene.narration`. El `purpose` queda de respaldo para
cuando todavía no hay texto (por ejemplo, previsualizar un plan sin gastar en escritura).

---

## 4. Nombrado es descrito

**Qué pasó:** en la escena del error, Dino se imagina jugando con Rexo en una burbuja
de pensamiento. El Rexo de la burbuja salió violeta. El Rexo real es azul.

**La causa:** la nota visual mencionaba a Rexo, pero Rexo no estaba en
`character_ids` —correctamente, porque no está ahí, se lo está imaginando—, así que el
prompt no lo describía y el ilustrador no le pasaba su imagen de referencia. Un nombre
sin descripción es una invitación a inventar.

**La regla:** existe `imagined_character_ids`, separado de `character_ids`. Los
imaginados no cuentan para el conteo de la regla 1, pero sí se describen, con la misma
descripción canónica de siempre, y el ilustrador les pasa su ancla visual:

```
Rexo (solo dentro de la burbuja de pensamiento, no en la escena real):
un dinosaurio bebé azul de cresta redondeada…
```

`Story._validar_elenco` valida los imaginados igual que a los presentes: un personaje
que la historia no conoce no puede aparecer ni siquiera en un pensamiento.

---

## Por qué esto es arquitectura y no una lista de parches

Los cuatro bugs son el mismo bug con distinta ropa: **una decisión que se tomó de un
lado del motor y no cruzó al otro**. El propósito no llegó al prompt. La emoción llegó
transformada. El compañero no llegó nunca. El imaginado llegó como nombre sin cuerpo.

De ahí sale el criterio para lo que viene —la voz, el video, la publicación—: cada vez
que un módulo nuevo consuma la historia, la pregunta no es *"¿funciona?"* sino
**"¿qué está decidiendo este módulo que el resto no se entera?"**.

Y la forma de sostenerlo: cada error real que se vea en una salida se convierte en un
test con el caso escrito en el docstring. No se arregla la imagen, se arregla la regla.
