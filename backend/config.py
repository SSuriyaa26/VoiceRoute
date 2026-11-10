"""Central configuration: intents, queues, thresholds, environment."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ── API keys & dynamic reload ──────────────────────────────────────────────
def get_gemini_api_key() -> str:
    load_dotenv(override=True)
    return os.getenv("GEMINI_API_KEY", "")


def get_gnani_api_key() -> str:
    load_dotenv(override=True)
    return os.getenv("GNANI_API_KEY", "")


def get_llm_model() -> str:
    load_dotenv(override=True)
    return os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")


GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GNANI_API_KEY: str = os.getenv("GNANI_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")

# ── Gnani endpoints ────────────────────────────────────────────────────────
GNANI_BASE_URL: str = "https://api.vachana.ai"
GNANI_STT_ENDPOINT: str = f"{GNANI_BASE_URL}/stt/v3"
GNANI_TTS_SSE_ENDPOINT: str = f"{GNANI_BASE_URL}/api/v1/tts/sse"
GNANI_AUTH_HEADER: str = "X-API-Key-ID"

# ── Timeouts (seconds) ─────────────────────────────────────────────────────
LLM_TIMEOUT_S: int = 15
GNANI_ASR_TIMEOUT_S: int = 10
GNANI_TTS_TIMEOUT_S: int = 10

# ── Intent → Queue mapping ─────────────────────────────────────────────────
INTENT_QUEUE_MAP: dict[str, str] = {
    "billing_issue":         "Billing",
    "recharge_plan":         "Sales",
    "network_problem":       "Tech Support",
    "sim_activation":        "Sales",
    "cancel_service":        "Retention",
    "complaint_escalation":  "Senior Escalation",
    "talk_to_agent":         "General Agent",
}

VALID_INTENTS: list[str] = list(INTENT_QUEUE_MAP.keys())
FALLBACK_QUEUE: str = "General Agent"

# ── Routing thresholds ─────────────────────────────────────────────────────
ROUTE_CONFIDENCE_THRESHOLD: float = 0.80
ROUTE_MARGIN_THRESHOLD: float = 0.15
CLARIFY_CONFIDENCE_MIN: float = 0.50
CLARIFY_TURN2_CONFIDENCE_MIN: float = 0.60
ESCALATION_CONFIDENCE_MIN: float = 0.70
SECONDARY_INTENT_MIN_CONFIDENCE: float = 0.30

# ── Escalation ─────────────────────────────────────────────────────────────
ESCALATION_KEYWORDS: set[str] = {"complaint", "manager", "escalate", "supervisor"}
ESCALATION_SENTIMENTS: set[str] = {"angry", "frustrated"}
ANGRY_SENTIMENTS: set[str] = {"angry"}

# ── Sentiment ──────────────────────────────────────────────────────────────
VALID_SENTIMENTS: set[str] = {"neutral", "happy", "frustrated", "angry", "confused"}

# ── Language ───────────────────────────────────────────────────────────────
SUPPORTED_LANGUAGES: set[str] = {"en-IN", "hi-IN", "ta-IN"}

# ── Session limits ─────────────────────────────────────────────────────────
MAX_CLARIFICATIONS: int = 1
MAX_REPROMPTS: int = 1

