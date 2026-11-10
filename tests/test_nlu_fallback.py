"""Tests for the keyword-based NLU fallback classifier."""
import pytest
from backend.nlu import _keyword_classify


class TestKeywordClassifier:
    def test_billing_keywords(self):
        result = _keyword_classify("my bill is too high")
        top = result[0]
        assert top["name"] == "billing_issue"
        assert top["confidence"] >= 0.30

    def test_recharge_keywords(self):
        result = _keyword_classify("I want to recharge my prepaid plan")
        top = result[0]
        assert top["name"] == "recharge_plan"
        assert top["confidence"] >= 0.30

    def test_network_keywords(self):
        result = _keyword_classify("there is no signal in my area")
        top = result[0]
        assert top["name"] == "network_problem"

    def test_sim_keywords(self):
        result = _keyword_classify("I need to activate my new sim card")
        top = result[0]
        assert top["name"] == "sim_activation"

    def test_cancel_keywords(self):
        result = _keyword_classify("I want to cancel my service")
        top = result[0]
        assert top["name"] == "cancel_service"

    def test_agent_keywords(self):
        result = _keyword_classify("let me talk to a human agent")
        top = result[0]
        assert top["name"] == "talk_to_agent"

    def test_hindi_transliteration(self):
        result = _keyword_classify("mera bill zyada aaya hai")
        top = result[0]
        assert top["name"] == "billing_issue"

    def test_hindi_network(self):
        result = _keyword_classify("network nahi aa raha")
        top = result[0]
        assert top["name"] == "network_problem"

    def test_unknown_falls_back(self):
        """Unrecognized input should return talk_to_agent at low confidence."""
        result = _keyword_classify("blah blah random words")
        top = result[0]
        assert top["name"] == "talk_to_agent"
        assert top["confidence"] < 0.30

    def test_multiple_intents_ranked(self):
        """Input mentioning both billing and recharge should return both."""
        result = _keyword_classify("my bill for the recharge plan is wrong")
        names = [r["name"] for r in result]
        assert "billing_issue" in names
        assert "recharge_plan" in names
        # billing should score higher (more keyword hits)
        assert result[0]["name"] == "billing_issue"

    def test_confidence_capped(self):
        """Even many keyword hits should not exceed 0.75."""
        result = _keyword_classify(
            "bill billing charge payment invoice overcharge paisa paise rupee"
        )
        assert result[0]["confidence"] <= 0.75

    def test_complaint_keywords(self):
        result = _keyword_classify("I want to file a complaint and escalate")
        top = result[0]
        assert top["name"] == "complaint_escalation"

