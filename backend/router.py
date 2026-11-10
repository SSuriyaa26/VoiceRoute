"""Deterministic routing rules engine. Pure functions — no I/O, fully unit-testable."""
from __future__ import annotations

from typing import Any, Optional

from backend.config import (
    INTENT_QUEUE_MAP,
    FALLBACK_QUEUE,
    ROUTE_CONFIDENCE_THRESHOLD,
    ROUTE_MARGIN_THRESHOLD,
    CLARIFY_CONFIDENCE_MIN,
    CLARIFY_TURN2_CONFIDENCE_MIN,
    ESCALATION_CONFIDENCE_MIN,
    ESCALATION_KEYWORDS,
    ESCALATION_SENTIMENTS,
    ANGRY_SENTIMENTS,
    SECONDARY_INTENT_MIN_CONFIDENCE,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_queue(intent: str) -> str:
    """Map an intent to its queue, defaulting to General Agent."""
    return INTENT_QUEUE_MAP.get(intent, FALLBACK_QUEUE)


def _has_escalation_keywords(transcript: str) -> bool:
    """True if any escalation keyword appears as a whole word in the transcript."""
    words = set(transcript.lower().split())
    return bool(words & ESCALATION_KEYWORDS)


def _match_ticket(
    intent: str, tickets: list[dict[str, Any]] | None
) -> Optional[str]:
    """Return the ticket_id of the first open ticket matching the intent, or None."""
    if not tickets:
        return None
    for ticket in tickets:
        if ticket.get("intent") == intent:
            return ticket["ticket_id"]
    return None


def _ticket_queue(ticket_id: str, tickets: list[dict[str, Any]]) -> str:
    """Look up the queue recorded on a ticket."""
    for ticket in tickets:
        if ticket["ticket_id"] == ticket_id:
            return ticket["queue"]
    return FALLBACK_QUEUE


def _build_handoff_summary(
    primary_intent: str,
    secondary_intent: Optional[str],
    sentiment: str,
    entities: dict,
) -> str:
    """Build a human-readable summary for the receiving agent."""
    parts = [f"Customer intent: {primary_intent.replace('_', ' ')}."]
    if entities:
        entity_str = ", ".join(f"{k}: {v}" for k, v in entities.items())
        parts.append(f"Details: {entity_str}.")
    if secondary_intent:
        parts.append(f"Secondary concern: {secondary_intent.replace('_', ' ')}.")
    parts.append(f"Sentiment: {sentiment}.")
    return " ".join(parts)


# ── Main routing function ──────────────────────────────────────────────────

def route(
    intents: list[dict[str, Any]],
    sentiment: str,
    transcript: str,
    entities: dict,
    turn: int,
    can_clarify: bool,
    can_reprompt: bool,
    clarification_context: dict | None = None,
    open_tickets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Evaluate routing rules in spec order.

    Returns dict with keys:
      decision, queue, primary_intent, secondary_intent,
      handoff_summary, ticket_id, reply_text_override
    """
    # Sort by confidence descending
    sorted_intents = sorted(
        intents, key=lambda x: x["confidence"], reverse=True
    )
    top = sorted_intents[0] if sorted_intents else {
        "name": "talk_to_agent", "confidence": 0.0,
    }
    second = sorted_intents[1] if len(sorted_intents) > 1 else {
        "name": "", "confidence": 0.0,
    }

    top_name: str = top["name"]
    top_conf: float = top["confidence"]
    second_name: str = second["name"]
    second_conf: float = second["confidence"]
    margin: float = top_conf - second_conf

    # Secondary intent — included in handoff when confidence is meaningful
    secondary: Optional[str] = (
        second_name if second_conf >= SECONDARY_INTENT_MIN_CONFIDENCE else None
    )

    # ── Rule 0: empty / unintelligible transcript ──────────────────────
    if not transcript or not transcript.strip():
        if can_reprompt:
            return {
                "decision": "reprompt",
                "queue": None,
                "primary_intent": None,
                "secondary_intent": None,
                "handoff_summary": None,
                "ticket_id": None,
                "reply_text_override": (
                    "Sorry, I couldn't hear that. Could you please say that again?"
                ),
            }
        # Already reprompted once → escalate to agent
        return {
            "decision": "escalate",
            "queue": FALLBACK_QUEUE,
            "primary_intent": "talk_to_agent",
            "secondary_intent": None,
            "handoff_summary": (
                "Customer could not be understood after reprompt. "
                "Routing to agent."
            ),
            "ticket_id": None,
            "reply_text_override": (
                "Let me connect you with an agent who can help."
            ),
        }

    # ── Rule 1: Escalation ─────────────────────────────────────────────
    # angry sentiment always escalates;
    # keywords + frustrated/angry escalate;
    # complaint_escalation as primary with ≥ 0.70 escalates.
    is_angry = sentiment in ANGRY_SENTIMENTS
    has_keywords = _has_escalation_keywords(transcript)
    is_frustrated_or_angry = sentiment in ESCALATION_SENTIMENTS
    is_complaint_primary = (
        top_name == "complaint_escalation"
        and top_conf >= ESCALATION_CONFIDENCE_MIN
    )

    if is_angry or (has_keywords and is_frustrated_or_angry) or is_complaint_primary:
        return {
            "decision": "escalate",
            "queue": "Senior Escalation",
            "primary_intent": top_name,
            "secondary_intent": secondary,
            "handoff_summary": _build_handoff_summary(
                top_name, secondary, sentiment, entities
            ),
            "ticket_id": None,
            "reply_text_override": None,  # keep LLM's empathetic reply
        }

    # ── Rule 2: Turn-2 clarification answer ────────────────────────────
    if turn == 2 and clarification_context:
        offered = clarification_context.get("offered_intents", [])
        if top_name in offered and top_conf >= CLARIFY_TURN2_CONFIDENCE_MIN:
            queue = _get_queue(top_name)
            ticket_id = _match_ticket(top_name, open_tickets)
            if ticket_id and open_tickets:
                queue = _ticket_queue(ticket_id, open_tickets)
            return {
                "decision": "route",
                "queue": queue,
                "primary_intent": top_name,
                "secondary_intent": secondary,
                "handoff_summary": _build_handoff_summary(
                    top_name, secondary, sentiment, entities
                ),
                "ticket_id": ticket_id,
                "reply_text_override": None,
            }
        # Could not resolve → General Agent
        return {
            "decision": "escalate",
            "queue": FALLBACK_QUEUE,
            "primary_intent": top_name,
            "secondary_intent": secondary,
            "handoff_summary": _build_handoff_summary(
                top_name, secondary, sentiment, entities
            ) + " Could not resolve after clarification.",
            "ticket_id": None,
            "reply_text_override": (
                "I want to make sure you get the right help. "
                "Let me connect you with an agent."
            ),
        }

    # ── Rule 3: High-confidence route ──────────────────────────────────
    if top_conf >= ROUTE_CONFIDENCE_THRESHOLD and margin >= ROUTE_MARGIN_THRESHOLD:
        queue = _get_queue(top_name)
        ticket_id = _match_ticket(top_name, open_tickets)
        if ticket_id and open_tickets:
            queue = _ticket_queue(ticket_id, open_tickets)
        return {
            "decision": "route",
            "queue": queue,
            "primary_intent": top_name,
            "secondary_intent": secondary,
            "handoff_summary": _build_handoff_summary(
                top_name, secondary, sentiment, entities
            ),
            "ticket_id": ticket_id,
            "reply_text_override": None,
        }

    # ── Rule 4: Ambiguous → clarify (turn 1, one-time) ─────────────────
    in_clarify_range = (
        CLARIFY_CONFIDENCE_MIN <= top_conf < ROUTE_CONFIDENCE_THRESHOLD
    )
    low_margin = (
        margin < ROUTE_MARGIN_THRESHOLD and top_conf >= CLARIFY_CONFIDENCE_MIN
    )

    if turn == 1 and can_clarify and (in_clarify_range or low_margin):
        top_label = top_name.replace("_", " ")
        second_label = second_name.replace("_", " ")
        return {
            "decision": "clarify",
            "queue": None,
            "primary_intent": top_name,
            "secondary_intent": secondary,
            "handoff_summary": None,
            "ticket_id": None,
            "reply_text_override": (
                f"I want to help you with the right team. "
                f"Is this about {top_label}, or {second_label}?"
            ),
        }

    # ── Rule 5: Anything else → General Agent ──────────────────────────
    return {
        "decision": "escalate",
        "queue": FALLBACK_QUEUE,
        "primary_intent": top_name,
        "secondary_intent": secondary,
        "handoff_summary": _build_handoff_summary(
            top_name, secondary, sentiment, entities
        ),
        "ticket_id": None,
        "reply_text_override": (
            "Let me connect you with an agent who can help you."
        ),
    }

