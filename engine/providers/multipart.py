"""Armado de multipart/form-data, sin dependencias.

Hace falta solo para mandar imágenes de referencia a `/v1/images/edits`, que no
acepta JSON. Son treinta líneas; traer `requests` por esto sería sumar un árbol de
dependencias para un caso.
"""

from __future__ import annotations

import secrets

_CRLF = b"\r\n"


def build(
    fields: dict[str, str],
    files: list[tuple[str, str, bytes]],
    *,
    content_type: str = "image/png",
) -> tuple[str, bytes]:
    """(content_type, cuerpo) listos para el POST.

    `files` es [(nombre_campo, nombre_archivo, bytes)]. Para varias referencias, OpenAI
    exige el campo `image[]` — repetir `image` da 400 "Duplicate parameter".

    `content_type` es el de los archivos que se mandan, no el del pedido: el mismo
    armador sirve para subir imágenes a `/images/edits` y audio a `/transcriptions`.
    """
    frontera = "----storyengine" + secrets.token_hex(16)
    sep = f"--{frontera}".encode()
    partes: list[bytes] = []

    for clave, valor in fields.items():
        partes += [
            sep,
            f'Content-Disposition: form-data; name="{clave}"'.encode(),
            b"",
            str(valor).encode(),
        ]

    for campo, nombre, crudo in files:
        partes += [
            sep,
            f'Content-Disposition: form-data; name="{campo}"; filename="{nombre}"'.encode(),
            f"Content-Type: {content_type}".encode(),
            b"",
            crudo,
        ]

    partes += [f"--{frontera}--".encode(), b""]
    return f"multipart/form-data; boundary={frontera}", _CRLF.join(partes)
