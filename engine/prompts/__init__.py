"""Prompts: lo que se le pide a los modelos.

Separados del código que los usa porque son CONTENIDO — se ajustan seguido, y hay
que poder leer de un vistazo qué se le está pidiendo realmente al modelo.

`narration` arma los pedidos de texto. `image` COMPONE el prompt de imagen a partir
de piezas fijas (estilo + descripción canónica del personaje): ese prompt no lo
escribe ninguna IA, y por eso el personaje se ve igual en todas las escenas.
"""
