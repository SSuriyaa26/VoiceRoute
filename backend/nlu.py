"""NLU module: Gemini LLM call with keyword-based fallback."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from google import genai
from google.genai import types

from backend import config
from backend.config import (
    VALID_INTENTS,
    VALID_SENTIMENTS,
)

logger = logging.getLogger(__name__)


# ── Keyword fallback classifier ────────────────────────────────────────────
# Covers English + common Hindi/Tamil transliterations so the demo works
# even when the LLM is unreachable.

_KEYWORD_MAP: dict[str, list[str]] = {
    "billing_issue": [
        "bill", "billing", "charge", "payment", "invoice", "overcharge",
        "paisa", "paise", "rupee", "rupay", "bill zyada", "extra charge",
        "wrong charge", "bill amount",
    ],
    "recharge_plan": [
        "recharge", "plan", "pack", "data pack", "validity", "offer",
        "topup", "top-up", "prepaid", "postpaid", "unlimited",
        "recharge karo", "plan change", "thittam",
    ],
    "network_problem": [
        "network", "signal", "call drop", "no signal", "slow internet",
        "coverage", "tower", "connection", "disconnect",
        "network nahi", "signal nahi", "internet slow",
    ],
    "sim_activation": [
        "sim", "activate", "new sim", "port", "mnp", "e-sim", "esim",
        "sim activate", "sim karo", "sim card",
    ],
    "cancel_service": [
        "cancel", "deactivate", "stop service", "unsubscribe", "close",
        "band karo", "cancel karo", "service hatao",
    ],
    "complaint_escalation": [
        "complaint", "escalate", "manager", "supervisor",
    ],
    "talk_to_agent": [
        "agent", "human", "person", "operator", "representative",
        "insaan se baat", "agent se baat",
    ],
}


def _keyword_classify(transcript: str) -> list[dict[str, Any]]:
    """Score intents by keyword hits. Max confidence capped at 0.75."""
    text = transcript.lower()
    scores: dict[str, float] = {}
    for intent, keywords in _KEYWORD_MAP.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scores[intent] = min(0.75, 0.30 + hits * 0.15)

    if not scores:
        return [{"name": "talk_to_agent", "confidence": 0.20}]

    sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [{"name": n, "confidence": round(c, 2)} for n, c in sorted_intents]


# ── Claude NLU ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an NLU engine for a telecom customer support router.
Analyze the customer's utterance and return a JSON object with these fields:

- intents: array of {name, confidence} for ALL relevant intents, sorted by confidence descending.
  Valid intent names: billing_issue, recharge_plan, network_problem, sim_activation, cancel_service, complaint_escalation, talk_to_agent
- entities: object with extracted key entities (e.g. {"issue": "high bill", "amount": "599"})
- sentiment: one of "neutral", "happy", "frustrated", "angry", "confused"
- language: detected language code (e.g. "en", "hi", "ta", "hi-en" for code-mixed)
- reply_text: a short, empathetic response in the SAME language the customer used.
  If they spoke Hindi, reply in Hindi. If code-mixed, reply in that mix. Keep it under 2 sentences.

Rules:
- Assign confidence scores that reflect genuine ambiguity. Do not inflate.
- "I want to make a complaint about a wrong charge" from a calm caller → billing_issue, NOT complaint_escalation.
  complaint_escalation is only for when the customer explicitly demands to escalate or reach management.
- Always return ALL 7 intents with scores. Put unlikely ones at 0.05 or below.
- Return ONLY the JSON object. No markdown fences, no commentary."""


def _build_user_message(
    transcript: str,
    language_hint: str,
    clarification_context: dict | None = None,
) -> str:
    """Construct the user message sent to Claude."""
    parts = [f"Language hint: {language_hint}"]
    if clarification_context:
        parts.append(
            f"Original utterance: {clarification_context['original_transcript']}"
        )
        parts.append(
            f"Offered intents: {clarification_context['offered_intents']}"
        )
        parts.append(f"Customer's clarification answer: {transcript}")
    else:
        parts.append(f"Customer utterance: {transcript}")
    return "\n".join(parts)


def _parse_llm_response(text: str) -> dict[str, Any]:
    """Parse Claude's JSON response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    return json.loads(cleaned)


_cached_client: genai.Client | None = None


_cached_key: str = ""


def _get_gemini_client(api_key: str) -> genai.Client:
    global _cached_client, _cached_key
    if _cached_client is None or _cached_key != api_key:
        _cached_client = genai.Client(api_key=api_key)
        _cached_key = api_key
    return _cached_client


def analyze(
    transcript: str,
    language_hint: str = "en-IN",
    clarification_context: dict | None = None,
) -> tuple[dict[str, Any], str, int]:
    """
    Run NLU on the transcript.

    Returns (result_dict, source, latency_ms).
      result_dict keys: intents, entities, sentiment, language, reply_text
      source: "llm" | "keyword_fallback"
    """
    api_key = config.get_gemini_api_key()
    llm_model = config.get_llm_model()

    # ── Try Gemini first ───────────────────────────────────────────────
    if api_key:
        try:
            client = _get_gemini_client(api_key)
            user_msg = _build_user_message(
                transcript, language_hint, clarification_context
            )

            start = time.perf_counter()
            response = client.models.generate_content(
                model=llm_model,
                contents=user_msg,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            parsed = _parse_llm_response(response.text)

            # Validate intents
            validated_intents: list[dict[str, Any]] = []
            for intent in parsed.get("intents", []):
                name = intent.get("name", "")
                conf = float(intent.get("confidence", 0))
                if name in VALID_INTENTS:
                    validated_intents.append(
                        {"name": name, "confidence": round(conf, 2)}
                    )

            if not validated_intents:
                validated_intents = [{"name": "talk_to_agent", "confidence": 0.20}]

            # Validate sentiment
            sentiment = parsed.get("sentiment", "neutral")
            if sentiment not in VALID_SENTIMENTS:
                sentiment = "neutral"

            result = {
                "intents": validated_intents,
                "entities": parsed.get("entities", {}),
                "sentiment": sentiment,
                "language": parsed.get("language", "en"),
                "reply_text": parsed.get("reply_text", ""),
            }
            return result, "llm", latency_ms

        except Exception as e:
            logger.warning("Gemini NLU failed, falling back to keywords: %s", e)

    # ── Keyword fallback ───────────────────────────────────────────────
    start = time.perf_counter()
    kw_intents = _keyword_classify(transcript)
    latency_ms = int((time.perf_counter() - start) * 1000)

    result = {
        "intents": kw_intents,
        "entities": {},
        "sentiment": "neutral",
        "language": language_hint.split("-")[0] if language_hint else "en",
        "reply_text": "I'll connect you to the right team.",
    }
    return result, "keyword_fallback", latency_ms

