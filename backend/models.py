"""Pydantic request / response models for all endpoints."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ── /route ──────────────────────────────────────────────────────────────────

class ClarificationContext(BaseModel):
    original_transcript: str
    offered_intents: list[str]


class RouteRequest(BaseModel):
    session_id: str
    transcript: str
    language_hint: str = "en-IN"
    turn: int = 1
    clarification_context: Optional[ClarificationContext] = None
    customer_id: Optional[str] = None


class IntentScore(BaseModel):
    name: str
    confidence: float


class TimingsMs(BaseModel):
    nlu: int = 0
    router: int = 0
    total: int = 0


class RouteResponse(BaseModel):
    intents: list[IntentScore]
    primary_intent: Optional[str] = None
    secondary_intent: Optional[str] = None
    entities: dict = Field(default_factory=dict)
    sentiment: str = "neutral"
    language: str = "en"
    decision: str                       # route | clarify | escalate | reprompt
    queue: Optional[str] = None
    reply_text: str = ""
    handoff_summary: Optional[str] = None
    ticket_id: Optional[str] = None
    nlu_source: str = "llm"             # llm | keyword_fallback
    timings_ms: TimingsMs = Field(default_factory=TimingsMs)


# ── /asr ────────────────────────────────────────────────────────────────────

class ASRResponse(BaseModel):
    transcript: str = ""
    provider: str = ""
    latency_ms: int = 0
    error: Optional[str] = None


# ── /tts ────────────────────────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str
    language: str = "hi-IN"


# ── /health ─────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    gnani_asr: bool = False
    gnani_tts: bool = False
    llm: bool = False


# ── Mock customer data ──────────────────────────────────────────────────────

class CustomerTicket(BaseModel):
    ticket_id: str
    queue: str
    intent: str
    summary: str


class Customer(BaseModel):
    id: str
    name: str
    phone: str
    plan: str
    open_tickets: list[CustomerTicket] = Field(default_factory=list)

