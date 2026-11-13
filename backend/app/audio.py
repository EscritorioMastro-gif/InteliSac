"""Converte áudio gravado no navegador (webm/ogg/mp4...) para o formato de mensagem de voz do
WhatsApp: OGG com codec Opus, mono, 48 kHz. Usa o ffmpeg que vem no pacote imageio-ffmpeg.

Atenção (doc. da Baileys): sem `-avoid_negative_ts make_zero` a gravação do navegador sai com
início negativo (ex.: -0,007 s) e vários celulares mostram "há algo errado com o arquivo de áudio".
"""

import asyncio
import os
import subprocess
import tempfile

VOICE_MIMETYPE = "audio/ogg; codecs=opus"
WAVEFORM_POINTS = 64  # o WhatsApp desenha 64 barrinhas (valores 0–100)


class AudioError(Exception):
    pass


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as e:  # pragma: no cover
        raise AudioError("Conversor de áudio não instalado (pip install imageio-ffmpeg)") from e
    return imageio_ffmpeg.get_ffmpeg_exe()


def _converter(data: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="intelisac-audio-") as tmp:
        entrada = os.path.join(tmp, "entrada")
        saida = os.path.join(tmp, "voz.ogg")
        with open(entrada, "wb") as f:
            f.write(data)
        cmd = [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", entrada, "-vn", "-map_metadata", "-1",
            "-ac", "1", "-ar", "48000",
            "-c:a", "libopus", "-b:a", "32k", "-application", "voip",
            "-avoid_negative_ts", "make_zero",
            "-f", "ogg", saida,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(saida):
            raise AudioError("Não consegui converter o áudio: " + r.stderr.decode(errors="ignore")[-300:])
        with open(saida, "rb") as f:
            return f.read()


def _waveform(ogg: bytes) -> list[int] | None:
    """64 valores 0–100 com o volume ao longo do áudio (as barrinhas da mensagem de voz)."""
    with tempfile.TemporaryDirectory(prefix="intelisac-onda-") as tmp:
        entrada = os.path.join(tmp, "voz.ogg")
        with open(entrada, "wb") as f:
            f.write(ogg)
        r = subprocess.run(
            [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", entrada, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
            capture_output=True,
            timeout=60,
        )
    pcm = r.stdout
    n = len(pcm) // 2
    if r.returncode != 0 or n < WAVEFORM_POINTS:
        return None
    amostras = memoryview(pcm).cast("h")
    bloco = n // WAVEFORM_POINTS
    medias = []
    for i in range(WAVEFORM_POINTS):
        trecho = amostras[i * bloco:(i + 1) * bloco]
        medias.append(sum(abs(x) for x in trecho) / max(1, len(trecho)))
    maior = max(medias) or 1
    return [min(100, round(v / maior * 100)) for v in medias]


async def to_voice_note(data: bytes) -> bytes:
    """Bytes de qualquer áudio → OGG/Opus (mensagem de voz)."""
    if not data:
        raise AudioError("Áudio vazio")
    return await asyncio.to_thread(_converter, data)


async def waveform(ogg: bytes) -> list[int] | None:
    try:
        return await asyncio.to_thread(_waveform, ogg)
    except Exception:  # a forma de onda é só visual: sem ela o áudio funciona
        return None


def duration_seconds(ogg: bytes) -> float | None:
    """Duração lida do próprio OGG (granule position da última página / 48000)."""
    i = ogg.rfind(b"OggS")
    if i < 0 or len(ogg) < i + 14:
        return None
    granule = int.from_bytes(ogg[i + 6:i + 14], "little")
    return round(granule / 48000, 1) if granule > 0 else None
