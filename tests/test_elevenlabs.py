"""El proveedor de ElevenLabs.

Sin red: se prueba lo que el proveedor DECIDE antes de salir a la API. Cada test acá
corresponde a algo que ya salió mal en los audiolibros de Casatridimensional, que
usan el mismo proveedor.
"""

from __future__ import annotations

import pytest

from engine.providers.elevenlabs import VOZ_POR_DEFECTO, ElevenLabsProvider, _envolver_wav


def test_sin_key_no_arranca() -> None:
    with pytest.raises(ValueError, match="API key"):
        ElevenLabsProvider("")


def test_la_voz_por_defecto_es_la_que_pablo_eligio_escuchando() -> None:
    """Lizy, elegida el 5-ago-2026 comparando cuatro configuraciones del MISMO cuento.
    Difiere de Valeria —la de los audiolibros— a propósito: son productos distintos y
    se eligió por separado, escuchando."""
    assert VOZ_POR_DEFECTO == "rrErIO88ehxTnspOjKvf"
    assert ElevenLabsProvider("k")._voz == VOZ_POR_DEFECTO


def test_la_estabilidad_es_la_de_cuento_no_la_de_lectura() -> None:
    """Baja de fábrica: le da permiso al modelo para emocionarse. Alta suena
    consistente pero plana, que es lo que Pablo escuchó y rechazó."""
    from engine.providers.elevenlabs import ESTABILIDAD_CUENTO

    assert ESTABILIDAD_CUENTO == 0.3
    assert ElevenLabsProvider("k")._stability == ESTABILIDAD_CUENTO


def test_v3_actua_las_etiquetas_y_v2_las_lee_en_voz_alta() -> None:
    """El bug: `[warmly]` es de v3. En multilingual_v2 el narrador dice "corchete
    warmly" en voz alta. El proveedor sabe qué modelo tiene y limpia solo."""
    assert ElevenLabsProvider("k", model="eleven_v3").soporta_etiquetas
    assert not ElevenLabsProvider("k", model="eleven_multilingual_v2").soporta_etiquetas


@pytest.mark.anyio
async def test_el_modelo_que_no_entiende_etiquetas_no_las_recibe(monkeypatch) -> None:
    enviado = {}

    def fake_post(self, url, cuerpo):
        enviado.update(cuerpo)
        enviado["url"] = url
        return b"\x00" * 1000

    monkeypatch.setattr(ElevenLabsProvider, "_post_sync", fake_post)
    prov = ElevenLabsProvider("k", model="eleven_multilingual_v2")
    await prov.synthesize("[warmly] Dino saltó feliz.")

    assert "[warmly]" not in enviado["text"]
    assert enviado["text"] == "Dino saltó feliz."


@pytest.mark.anyio
async def test_el_modelo_que_si_las_entiende_las_conserva(monkeypatch) -> None:
    enviado = {}
    monkeypatch.setattr(
        ElevenLabsProvider, "_post_sync",
        lambda self, url, cuerpo: (enviado.update(cuerpo), b"\x00" * 1000)[1],
    )
    await ElevenLabsProvider("k", model="eleven_v3").synthesize("[warmly] Dino saltó.")
    assert "[warmly]" in enviado["text"]


@pytest.mark.anyio
async def test_v3_no_manda_speed_porque_lo_ignora(monkeypatch) -> None:
    """Pedir speed a un modelo que lo ignora no rompe, pero CREER que se aplicó sí:
    una escena que "se aceleró un 10%" y en realidad no, desincroniza el video."""
    enviado = {}
    monkeypatch.setattr(
        ElevenLabsProvider, "_post_sync",
        lambda self, url, cuerpo: (enviado.update(cuerpo), b"\x00" * 1000)[1],
    )
    await ElevenLabsProvider("k", model="eleven_v3").synthesize("hola", speed=0.9)
    assert "speed" not in enviado["voice_settings"]

    enviado.clear()
    await ElevenLabsProvider("k", model="eleven_multilingual_v2").synthesize("hola", speed=0.9)
    assert enviado["voice_settings"]["speed"] == 0.9


@pytest.mark.anyio
async def test_pide_pcm_cuando_le_piden_wav(monkeypatch) -> None:
    """El motor necesita medir la duración, y para eso necesita un WAV.

    24 kHz y no 44.1: `pcm_44100` es sólo del tier Pro, verificado contra la cuenta
    real. Si alguien lo sube sin plan, TODAS las tomas fallan con 403."""
    enviado = {}
    monkeypatch.setattr(
        ElevenLabsProvider, "_post_sync",
        lambda self, url, cuerpo: (enviado.update({"url": url}), b"\x00" * 1000)[1],
    )
    await ElevenLabsProvider("k").synthesize("hola", audio_format="wav")
    assert "output_format=pcm_24000" in enviado["url"]


@pytest.mark.anyio
async def test_un_formato_desconocido_falla_claro() -> None:
    with pytest.raises(ValueError, match="ogg"):
        await ElevenLabsProvider("k").synthesize("hola", audio_format="ogg")


@pytest.mark.anyio
async def test_el_pcm_sale_como_wav_medible(monkeypatch) -> None:
    """ElevenLabs devuelve PCM pelado, sin cabecera. Si el motor lo guarda así, no lo
    puede abrir nadie ni se puede medir."""
    from engine.generators.narrator import duracion_de_wav

    monkeypatch.setattr(
        ElevenLabsProvider, "_post_sync",
        lambda self, url, cuerpo: b"\x00\x00" * 24000,  # 1 segundo a 24kHz mono 16bit
    )
    audio = await ElevenLabsProvider("k").synthesize("hola")
    assert audio[:4] == b"RIFF"
    assert duracion_de_wav(audio) == pytest.approx(1.0, abs=0.01)


def test_la_cabecera_wav_declara_bien_el_tamano() -> None:
    import struct

    wav = _envolver_wav(b"\x00\x00" * 100, fps=24000)
    assert struct.unpack("<I", wav[4:8])[0] == 36 + 200
    assert struct.unpack("<I", wav[40:44])[0] == 200


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
