"""Gnani STT wrapper with audio format conversion (webm → 16 kHz mono WAV)."""
from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

from backend import config
from backend.config import (
    GNANI_STT_ENDPOINT,
    GNANI_AUTH_HEADER,
    GNANI_ASR_TIMEOUT_S,
)

logger = logging.getLogger(__name__)


def convert_to_wav(audio_bytes: bytes, input_format: str = "webm") -> bytes:
    """
    Convert browser-recorded audio to 16 kHz mono WAV via ffmpeg.
    Returns original bytes if ffmpeg is unavailable or fails.
    """
    with tempfile.NamedTemporaryFile(
        suffix=f".{input_format}", delete=False
    ) as infile:
        infile.write(audio_bytes)
        infile.flush()
        in_path = Path(infile.name)

    out_path = in_path.with_suffix(".wav")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(in_path),
                "-ar", "16000", "-ac", "1", "-f", "wav", str(out_path),
            ],
            capture_output=True,
            timeout=10,
            check=True,
        )
        return out_path.read_bytes()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("ffmpeg conversion failed, sending raw bytes: %s", e)
        return audio_bytes
    finally:
        in_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)


async def transcribe(audio_bytes: bytes, language: str = "hi-IN") -> dict:
    """
    Send audio to Gnani STT.

    Returns {"transcript": ..., "provider": "gnani", "latency_ms": ...}
    On failure: {"transcript": "", "error": "asr_failed"}
    """
    api_key = config.get_gnani_api_key()
    if not api_key:
        return {
            "transcript": "", "error": "asr_failed",
            "provider": "gnani", "latency_ms": 0,
        }

    wav_bytes = convert_to_wav(audio_bytes)

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=GNANI_ASR_TIMEOUT_S) as client:
            resp = await client.post(
                GNANI_STT_ENDPOINT,
                headers={GNANI_AUTH_HEADER: api_key},
                files={"audio_file": ("audio.wav", wav_bytes, "audio/wav")},
                data={"language_code": language},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                transcript = data.get("transcript", data.get("text", ""))
                return {
                    "transcript": transcript,
                    "provider": "gnani",
                    "latency_ms": latency_ms,
                }

            logger.warning(
                "Gnani ASR HTTP %d: %s", resp.status_code, resp.text[:200]
            )
            return {
                "transcript": "", "error": "asr_failed",
                "provider": "gnani", "latency_ms": latency_ms,
            }

    except Exception as e:
        logger.warning("Gnani ASR call failed: %s", e)
        return {
            "transcript": "", "error": "asr_failed",
            "provider": "gnani", "latency_ms": 0,
        }

