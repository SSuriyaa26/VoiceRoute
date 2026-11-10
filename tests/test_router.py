"""Unit tests for the deterministic routing rules engine (router.py)."""
import pytest
from backend.router import route


# ── Helpers ──────────────────────────────────────────────────────────────────

def _intents(pairs: list[tuple[str, float]]) -> list[dict]:
    """Shorthand to build an intent list from (name, confidence) pairs."""
    return [{"name": n, "confidence": c} for n, c in pairs]


BILLING_HIGH = _intents([("billing_issue", 0.92), ("recharge_plan", 0.10)])
BILLING_MID  = _intents([("billing_issue", 0.65), ("recharge_plan", 0.55)])
BILLING_LOW  = _intents([("billing_issue", 0.30), ("recharge_plan", 0.20)])
AMBIGUOUS    = _intents([("billing_issue", 0.55), ("recharge_plan", 0.50)])
NETWORK_HIGH = _intents([("network_problem", 0.88), ("billing_issue", 0.05)])
COMPLAINT    = _intents([("complaint_escalation", 0.75), ("billing_issue", 0.40)])

OPEN_BILLING_TICKET = [
    {"ticket_id": "T-1042", "queue": "Billing", "intent": "billing_issue",
     "summary": "Disputed charge"}
]
OPEN_NETWORK_TICKET = [
    {"ticket_id": "T-2087", "queue": "Tech Support", "intent": "network_problem",
     "summary": "Call drops"}
]


# ── Rule 0: empty transcript ────────────────────────────────────────────────

class TestRule0EmptyTranscript:
    def test_empty_first_time_reprompts(self):
        result = route(
            intents=BILLING_HIGH, sentiment="neutral", transcript="",
            entities={}, turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "reprompt"
        assert result["queue"] is None

    def test_empty_second_time_escalates(self):
        result = route(
            intents=BILLING_HIGH, sentiment="neutral", transcript="",
            entities={}, turn=1, can_clarify=True, can_reprompt=False,
        )
        assert result["decision"] == "escalate"
        assert result["queue"] == "General Agent"

    def test_whitespace_only_reprompts(self):
        result = route(
            intents=BILLING_HIGH, sentiment="neutral", transcript="   ",
            entities={}, turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "reprompt"


# ── Rule 1: escalation ─────────────────────────────────────────────────────

class TestRule1Escalation:
    def test_angry_sentiment_escalates(self):
        result = route(
            intents=BILLING_HIGH, sentiment="angry",
            transcript="mera bill galat hai", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "escalate"
        assert result["queue"] == "Senior Escalation"

    def test_keyword_plus_frustrated_escalates(self):
        result = route(
            intents=BILLING_HIGH, sentiment="frustrated",
            transcript="I want to escalate this", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "escalate"
        assert result["queue"] == "Senior Escalation"

    def test_keyword_alone_without_frustration_does_not_escalate(self):
        """Calm caller saying 'complaint about wrong charge' → should NOT escalate."""
        result = route(
            intents=BILLING_HIGH, sentiment="neutral",
            transcript="I want to make a complaint about a wrong charge",
            entities={}, turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "route"
        assert result["queue"] == "Billing"

    def test_complaint_escalation_intent_high_conf(self):
        result = route(
            intents=COMPLAINT, sentiment="frustrated",
            transcript="get me your manager now", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "escalate"
        assert result["queue"] == "Senior Escalation"

    def test_complaint_escalation_intent_alone(self):
        """complaint_escalation ≥ 0.70 should escalate even without keywords."""
        result = route(
            intents=COMPLAINT, sentiment="neutral",
            transcript="let me talk to someone senior", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "escalate"


# ── Rule 2: turn 2 (clarification answer) ──────────────────────────────────

class TestRule2ClarificationAnswer:
    def test_matching_offered_intent_routes(self):
        ctx = {"original_transcript": "problem with plan",
               "offered_intents": ["recharge_plan", "billing_issue"]}
        intents = _intents([("recharge_plan", 0.72), ("billing_issue", 0.20)])
        result = route(
            intents=intents, sentiment="neutral",
            transcript="yes recharge plan", entities={},
            turn=2, can_clarify=False, can_reprompt=True,
            clarification_context=ctx,
        )
        assert result["decision"] == "route"
        assert result["queue"] == "Sales"

    def test_low_confidence_on_turn2_escalates(self):
        ctx = {"original_transcript": "problem with plan",
               "offered_intents": ["recharge_plan", "billing_issue"]}
        intents = _intents([("recharge_plan", 0.45), ("billing_issue", 0.40)])
        result = route(
            intents=intents, sentiment="neutral",
            transcript="I don't know", entities={},
            turn=2, can_clarify=False, can_reprompt=True,
            clarification_context=ctx,
        )
        assert result["decision"] == "escalate"
        assert result["queue"] == "General Agent"

    def test_unoffered_intent_on_turn2_escalates(self):
        ctx = {"original_transcript": "problem with plan",
               "offered_intents": ["recharge_plan", "billing_issue"]}
        intents = _intents([("network_problem", 0.80), ("recharge_plan", 0.10)])
        result = route(
            intents=intents, sentiment="neutral",
            transcript="actually my network is bad", entities={},
            turn=2, can_clarify=False, can_reprompt=True,
            clarification_context=ctx,
        )
        assert result["decision"] == "escalate"


# ── Rule 3: high confidence route ──────────────────────────────────────────

class TestRule3HighConfidence:
    def test_high_confidence_routes(self):
        result = route(
            intents=BILLING_HIGH, sentiment="neutral",
            transcript="my bill is wrong", entities={"issue": "wrong bill"},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "route"
        assert result["queue"] == "Billing"
        assert result["primary_intent"] == "billing_issue"

    def test_includes_handoff_summary(self):
        result = route(
            intents=BILLING_HIGH, sentiment="frustrated",
            transcript="my bill is too high", entities={"issue": "high bill"},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "route"  # frustrated but no keywords
        assert "billing issue" in result["handoff_summary"].lower()
        assert "frustrated" in result["handoff_summary"].lower()


# ── Rule 4: clarify ────────────────────────────────────────────────────────

class TestRule4Clarify:
    def test_ambiguous_triggers_clarify(self):
        result = route(
            intents=AMBIGUOUS, sentiment="neutral",
            transcript="I have a problem with my plan", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "clarify"
        assert result["queue"] is None
        assert "billing" in result["reply_text_override"].lower()
        assert "recharge" in result["reply_text_override"].lower()

    def test_mid_confidence_triggers_clarify(self):
        result = route(
            intents=BILLING_MID, sentiment="neutral",
            transcript="plan related issue", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "clarify"

    def test_no_clarify_if_already_used(self):
        result = route(
            intents=AMBIGUOUS, sentiment="neutral",
            transcript="I have a problem", entities={},
            turn=1, can_clarify=False, can_reprompt=True,
        )
        # Can't clarify → should escalate
        assert result["decision"] == "escalate"
        assert result["queue"] == "General Agent"


# ── Rule 5: fallback escalation ────────────────────────────────────────────

class TestRule5Fallback:
    def test_low_confidence_escalates(self):
        result = route(
            intents=BILLING_LOW, sentiment="neutral",
            transcript="something something", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["decision"] == "escalate"
        assert result["queue"] == "General Agent"


# ── Rule 6 & 7: secondary intent and ticket matching ──────────────────────

class TestSecondaryIntentAndTickets:
    def test_secondary_intent_included(self):
        intents = _intents([("billing_issue", 0.85), ("recharge_plan", 0.35)])
        result = route(
            intents=intents, sentiment="neutral",
            transcript="bill and plan issue", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["secondary_intent"] == "recharge_plan"
        assert "recharge" in result["handoff_summary"].lower()

    def test_no_secondary_when_low(self):
        result = route(
            intents=BILLING_HIGH, sentiment="neutral",
            transcript="my bill", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
        )
        assert result["secondary_intent"] is None

    def test_open_ticket_attached(self):
        result = route(
            intents=BILLING_HIGH, sentiment="neutral",
            transcript="my bill is wrong", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
            open_tickets=OPEN_BILLING_TICKET,
        )
        assert result["decision"] == "route"
        assert result["ticket_id"] == "T-1042"
        assert result["queue"] == "Billing"

    def test_ticket_queue_overrides(self):
        """If ticket exists for intent, use ticket's queue."""
        result = route(
            intents=NETWORK_HIGH, sentiment="neutral",
            transcript="my calls keep dropping", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
            open_tickets=OPEN_NETWORK_TICKET,
        )
        assert result["ticket_id"] == "T-2087"
        assert result["queue"] == "Tech Support"

    def test_no_ticket_when_intent_mismatch(self):
        result = route(
            intents=BILLING_HIGH, sentiment="neutral",
            transcript="my bill", entities={},
            turn=1, can_clarify=True, can_reprompt=True,
            open_tickets=OPEN_NETWORK_TICKET,  # network ticket, not billing
        )
        assert result["ticket_id"] is None

