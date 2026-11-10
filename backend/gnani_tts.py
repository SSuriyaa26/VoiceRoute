"""Gnani TTS wrapper with text formatting for natural pronunciation."""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import time
import wave

import httpx

from backend import config
from backend.config import (
    GNANI_TTS_SSE_ENDPOINT,
    GNANI_AUTH_HEADER,
    GNANI_TTS_TIMEOUT_S,
)

logger = logging.getLogger(__name__)

# Map supported languages to Gnani Timbre voices
_LANGUAGE_VOICE_MAP = {
    "en-IN": "Nalini",
    "hi-IN": "Bhavna",
    "ta-IN": "Ambuja",
}


def format_for_tts(text: str) -> str:
    """
    Pre-process text so TTS reads numbers, IDs, and amounts naturally.
    Gnani mispronounces raw numbers and ticket IDs.
    """
    # Ticket IDs like T-1042 → "T dash 1 0 4 2"
    def _spell_ticket(m: re.Match) -> str:
        prefix = m.group(1)
        digits = " ".join(m.group(2))
        return f"{prefix} dash {digits}"
    text = re.sub(r"(T)-(\d+)", _spell_ticket, text)

    # Rupee symbols: ₹599 → "599 rupees"
    text = re.sub(r"₹(\d+)", r"\1 rupees", text)

    # Long digit strings (6+) that might be phone/account numbers → spell out
    def _spell_long(m: re.Match) -> str:
        return " ".join(m.group(0))
    text = re.sub(r"\b\d{6,}\b", _spell_long, text)

    return text


async def synthesize(text: str, language: str = "hi-IN") -> bytes | None:
    """
    Send text to Gnani TTS SSE endpoint and return assembled WAV audio bytes.
    Returns None on failure so the frontend can fall back to speechSynthesis.
    """
    api_key = config.get_gnani_api_key()
    if not api_key:
        return None

    formatted = format_for_tts(text)
    voice = _LANGUAGE_VOICE_MAP.get(language, "Nalini")
    target_sample_rate = 24000

    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=GNANI_TTS_TIMEOUT_S) as client:
            resp = await client.post(
                GNANI_TTS_SSE_ENDPOINT,
                headers={
                    GNANI_AUTH_HEADER: api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": formatted,
                    "language": language,
                    "model": "timbre-v2.5",
                    "voice": voice,
                    "speed": 1.0,
                    "audio_config": {
                        "sample_rate": target_sample_rate,
                        "num_channels": 1,
                        "encoding": "linear_pcm",
                    },
                },
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            if resp.status_code == 200:
                chunks: list[tuple[int, bytes]] = []
                for line in resp.text.splitlines():
                    if line.startswith("data: ") and "audio" in line:
                        try:
                            payload = json.loads(line[6:])
                            if "audio" in payload:
                                idx = payload.get("chunk_index", len(chunks))
                                chunks.append((idx, base64.b64decode(payload["audio"])))
                        except Exception:
                            continue

                if chunks:
                    # Sort chunks by chunk_index to ensure flawless audio continuity
                    chunks.sort(key=lambda c: c[0])
                    raw_pcm = b"".join(c[1] for c in chunks)

                    wav_buf = io.BytesIO()
                    with wave.open(wav_buf, "wb") as wf:
                        wf.setnchannels(1)                # Mono
                        wf.setsampwidth(2)                # 16-bit PCM
                        wf.setframerate(target_sample_rate)  # 24 kHz matching audio_config
                        wf.writeframes(raw_pcm)

                    wav_bytes = wav_buf.getvalue()
                    logger.info(
                        "Gnani TTS: %d WAV bytes generated in %d ms (%s voice @ %d Hz)",
                        len(wav_bytes), latency_ms, voice, target_sample_rate
                    )
                    return wav_bytes

            logger.warning(
                "Gnani TTS HTTP %d: %s",
                resp.status_code, resp.text[:200]
            )
            return None

    except Exception as e:
        logger.warning("Gnani TTS call failed: %s", e)
        return None
