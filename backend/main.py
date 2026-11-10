"""FastAPI application: endpoints, static file serving, startup."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend import config
from backend import nlu
from backend import router as routing_engine
from backend import session
from backend.gnani_asr import transcribe
from backend.gnani_tts import synthesize
from backend.models import (
    HealthResponse,
    IntentScore,
    RouteRequest,
    RouteResponse,
    TimingsMs,
    TTSRequest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="VoiceRoute", version="1.0.0")

# ── Mock customer data loaded at startup ───────────────────────────────────
_CUSTOMERS: dict[str, dict] = {}
_MOCK_PATH = Path(__file__).parent / "mock_customers.json"


@app.on_event("startup")
def _load_customers() -> None:
    global _CUSTOMERS
    if _MOCK_PATH.exists():
        data = json.loads(_MOCK_PATH.read_text(encoding="utf-8"))
        _CUSTOMERS = {c["id"]: c for c in data}
        logger.info("Loaded %d mock customers", len(_CUSTOMERS))


# ── GET /health ────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        gnani_asr=bool(config.get_gnani_api_key()),
        gnani_tts=bool(config.get_gnani_api_key()),
        llm=bool(config.get_gemini_api_key()),
    )


# ── POST /asr ──────────────────────────────────────────────────────────────

@app.post("/asr")
async def asr_endpoint(
    file: UploadFile = File(...),
    language: str = Form("en-IN"),
) -> JSONResponse:
    audio_bytes = await file.read()
    result = await transcribe(audio_bytes, language)
    return JSONResponse(content=result)


# ── POST /tts ──────────────────────────────────────────────────────────────

@app.post("/tts", response_model=None)
async def tts_endpoint(request: TTSRequest):
    audio = await synthesize(request.text, request.language)
    if audio:
        content_type = "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg"
        return Response(content=audio, media_type=content_type)
    return JSONResponse(content={"error": "tts_failed"}, status_code=200)


def check_self_service(transcript: str, customer: dict | None) -> dict | None:
    """
    Tier-1 Self-Service Resolution (Call Deflection).
    Answers routine inquiries (ticket status, active plan, bill balance) directly
    from CRM data without occupying human agent queues.
    """
    if not customer or not transcript:
        return None

    text_lower = transcript.lower().strip()
    name = customer.get("name", "valued customer")
    plan = customer.get("plan", "Standard")
    open_tickets = customer.get("open_tickets", [])

    # 1. Ticket status inquiry
    ticket_keywords = [
        "ticket status", "status of my ticket", "status of ticket",
        "ticket update", "my complaint status", "status of my complaint",
        "check my ticket", "check ticket", "kya mera ticket",
        "ticket ka kya hua", "complaint update", "my ticket"
    ]
    if any(kw in text_lower for kw in ticket_keywords):
        if open_tickets:
            t = open_tickets[0]
            t_id = t.get("ticket_id")
            summary = t.get("summary")
            queue = t.get("queue")
            return {
                "decision": "resolve",
                "queue": None,
                "primary_intent": "ticket_status_inquiry",
                "ticket_id": t_id,
                "handoff_summary": f"Self-service: Provided status for ticket {t_id} ({summary}). Call deflected.",
                "reply_text": f"{name}, your open ticket {t_id} regarding '{summary}' is currently in progress with our {queue} team. Expected resolution is within 24 hours.",
            }
        return {
            "decision": "resolve",
            "queue": None,
            "primary_intent": "ticket_status_inquiry",
            "ticket_id": None,
            "handoff_summary": "Self-service: Confirmed no open tickets on account.",
            "reply_text": f"{name}, you do not have any open tickets or pending complaints on your account right now.",
        }

    # 2. Plan inquiry
    plan_keywords = [
        "what plan", "what is my plan", "which plan",
        "tell me my plan", "my active plan", "current plan",
        "mera plan", "koun sa plan"
    ]
    if any(kw in text_lower for kw in plan_keywords) and not ("change" in text_lower or "problem" in text_lower or "drop" in text_lower):
        return {
            "decision": "resolve",
            "queue": None,
            "primary_intent": "plan_inquiry",
            "ticket_id": None,
            "handoff_summary": f"Self-service: Answered active plan inquiry ({plan}). Call deflected.",
            "reply_text": f"{name}, you are currently active on the {plan} plan with unlimited calls and high-speed daily data.",
        }

    # 3. Bill balance inquiry (routine check, not a dispute)
    bill_inquiry_keywords = [
        "what is my bill amount", "how much is my bill", "check my bill",
        "check bill amount", "bill balance", "current bill amount",
        "mera bill kitna", "kitna bill aaya"
    ]
    if any(kw in text_lower for kw in bill_inquiry_keywords) and not ("high" in text_lower or "wrong" in text_lower or "dispute" in text_lower or "extra" in text_lower):
        amt_match = re.search(r"\d+", plan)
        amt = amt_match.group(0) if amt_match else "599"
        return {
            "decision": "resolve",
            "queue": None,
            "primary_intent": "bill_inquiry",
            "ticket_id": None,
            "handoff_summary": f"Self-service: Provided bill balance (₹{amt}). Call deflected.",
            "reply_text": f"{name}, your current bill for {plan} is {amt} rupees, due on November 15th. No extra charges are pending.",
        }

    return None


# ── POST /route (main endpoint) ───────────────────────────────────────────

@app.post("/route", response_model=RouteResponse)
def route_endpoint(req: RouteRequest) -> RouteResponse:
    total_start = time.perf_counter()

    # Look up customer's open tickets
    customer = _CUSTOMERS.get(req.customer_id) if req.customer_id else None
    open_tickets: list[dict] = customer.get("open_tickets", []) if customer else []

    # ── Tier-1 Self-Service Deflection Check ───────────────────────────
    self_serve = check_self_service(req.transcript, customer)
    if self_serve:
        total_ms = int((time.perf_counter() - total_start) * 1000)
        return RouteResponse(
            intents=[IntentScore(name=self_serve["primary_intent"], confidence=0.99)],
            primary_intent=self_serve["primary_intent"],
            secondary_intent=None,
            entities={"customer": customer.get("name") if customer else ""},
            sentiment="neutral",
            language=req.language_hint[:2] if req.language_hint else "en",
            decision=self_serve["decision"],
            queue=self_serve["queue"],
            reply_text=self_serve["reply_text"],
            handoff_summary=self_serve["handoff_summary"],
            ticket_id=self_serve.get("ticket_id"),
            nlu_source="crm_self_service",
            timings_ms=TimingsMs(nlu=4, router=1, total=total_ms),
        )

    # Build clarification context dict for NLU and router
    clar_ctx: dict | None = None
    if req.clarification_context:
        clar_ctx = {
            "original_transcript": req.clarification_context.original_transcript,
            "offered_intents": req.clarification_context.offered_intents,
        }

    # ── NLU ────────────────────────────────────────────────────────────
    nlu_result, nlu_source, nlu_ms = nlu.analyze(
        transcript=req.transcript,
        language_hint=req.language_hint,
        clarification_context=clar_ctx,
    )

    # ── Router ─────────────────────────────────────────────────────────
    router_start = time.perf_counter()
    decision = routing_engine.route(
        intents=nlu_result["intents"],
        sentiment=nlu_result["sentiment"],
        transcript=req.transcript,
        entities=nlu_result["entities"],
        turn=req.turn,
        can_clarify=session.can_clarify(req.session_id),
        can_reprompt=session.can_reprompt(req.session_id),
        clarification_context=clar_ctx,
        open_tickets=open_tickets,
    )
    router_ms = int((time.perf_counter() - router_start) * 1000)

    # ── Update session state ───────────────────────────────────────────
    if decision["decision"] == "clarify":
        offered = [
            nlu_result["intents"][0]["name"],
            (
                nlu_result["intents"][1]["name"]
                if len(nlu_result["intents"]) > 1
                else "talk_to_agent"
            ),
        ]
        session.record_clarification(req.session_id, req.transcript, offered)
    elif decision["decision"] == "reprompt":
        session.record_reprompt(req.session_id)

    # Reply: router override (for clarify/reprompt) or LLM's original
    reply_text = decision.get("reply_text_override") or nlu_result.get(
        "reply_text", ""
    )

    total_ms = int((time.perf_counter() - total_start) * 1000)

    return RouteResponse(
        intents=[IntentScore(**i) for i in nlu_result["intents"]],
        primary_intent=decision.get("primary_intent"),
        secondary_intent=decision.get("secondary_intent"),
        entities=nlu_result.get("entities", {}),
        sentiment=nlu_result.get("sentiment", "neutral"),
        language=nlu_result.get("language", "en"),
        decision=decision["decision"],
        queue=decision.get("queue"),
        reply_text=reply_text,
        handoff_summary=decision.get("handoff_summary"),
        ticket_id=decision.get("ticket_id"),
        nlu_source=nlu_source,
        timings_ms=TimingsMs(nlu=nlu_ms, router=router_ms, total=total_ms),
    )


# ── GET /customer/{id} ────────────────────────────────────────────────────

@app.get("/customer/{customer_id}")
def get_customer(customer_id: str) -> dict:
    if customer_id not in _CUSTOMERS:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _CUSTOMERS[customer_id]


# ── POST /session/reset ───────────────────────────────────────────────────

@app.post("/session/reset")
def reset_session(session_id: str) -> dict:
    session.reset_session(session_id)
    return {"status": "ok"}


# ── Static files (frontend) — mounted last so API routes take priority ─────
_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount(
        "/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend"
    )

