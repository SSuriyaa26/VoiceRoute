"""
Evaluation script: runs test utterances through NLU + Router and reports metrics.

Usage:
  python tests/eval.py             # Runs all 36 utterances (with pacing for free tier API)
  python tests/eval.py --quick     # Fast 6-sample sanity check across all decision paths
  python tests/eval.py --limit 10  # Run first 10 utterances
  python tests/eval.py --delay 0   # No delay between calls (for paid tiers or offline fallback)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import config, nlu, session
from backend.router import route as route_fn


def load_utterances() -> list[dict]:
    path = Path(__file__).parent / "utterances.json"
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(limit: int | None = None, delay_s: float = 0.0, quick: bool = False) -> None:
    utterances = load_utterances()
    
    if quick:
        # Pick 6 diverse cases: route billing, route hindi, route tech, clarify, escalate angry, reprompt empty
        quick_indices = [0, 2, 10, 21, 26, 28]
        utterances = [utterances[idx] for idx in quick_indices if idx < len(utterances)]
    elif limit:
        utterances = utterances[:limit]

    total = len(utterances)

    intent_correct = 0
    decision_correct = 0
    clarify_count = 0
    escalate_count = 0
    fallback_count = 0
    latencies: list[int] = []

    print(f"\n{'='*75}")
    print(f"  VoiceRoute Evaluation — {total} utterances")
    print(f"  Model: {config.get_llm_model()} | Delay: {delay_s}s per request")
    print(f"{'='*75}\n")

    for i, utt in enumerate(utterances):
        text = utt["text"]
        lang = utt.get("language", "en-IN")
        expected_intent = utt.get("expected_intent")
        expected_decision = utt.get("expected_decision")

        sid = f"eval-{i}-{int(time.time())}"

        # Run NLU
        nlu_result, nlu_source, nlu_ms = nlu.analyze(text, lang)
        latencies.append(nlu_ms)

        if nlu_source == "keyword_fallback":
            fallback_count += 1

        # Run router
        decision = route_fn(
            intents=nlu_result["intents"],
            sentiment=nlu_result["sentiment"],
            transcript=text,
            entities=nlu_result["entities"],
            turn=1,
            can_clarify=session.can_clarify(sid),
            can_reprompt=session.can_reprompt(sid),
        )

        actual_intent = decision.get("primary_intent")
        actual_decision = decision["decision"]

        # Score intent (skip if expected is null = ambiguous)
        intent_match = "—"
        if expected_intent is not None:
            if actual_intent == expected_intent:
                intent_correct += 1
                intent_match = "✓"
            else:
                intent_match = "✗"

        # Score decision
        dec_match = "✓" if actual_decision == expected_decision else "✗"
        if actual_decision == expected_decision:
            decision_correct += 1

        if actual_decision == "clarify":
            clarify_count += 1
        elif actual_decision == "escalate":
            escalate_count += 1

        # Print row
        text_short = (text[:36] + "…") if len(text) > 36 else text.ljust(37)
        if not text_short.strip():
            text_short = "(silent / empty audio)".ljust(37)

        print(
            f"  [{i+1:2d}] {text_short} "
            f"intent={actual_intent or '—':22s} {intent_match} "
            f"dec={actual_decision:9s} {dec_match} "
            f"src={nlu_source:15s} {nlu_ms:4d}ms"
        )

        # Rate limit pacing if specified and more items remain
        if delay_s > 0 and i < total - 1 and nlu_source != "keyword_fallback":
            time.sleep(delay_s)

    # Summary
    intent_scoreable = sum(1 for u in utterances if u.get("expected_intent") is not None)
    mean_latency = sum(latencies) / len(latencies) if latencies else 0
    sorted_lat = sorted(latencies)
    p95_idx = int(len(sorted_lat) * 0.95)
    p95_latency = sorted_lat[p95_idx] if sorted_lat else 0

    print(f"\n{'='*75}")
    print(f"  BENCHMARK SUMMARY")
    print(f"{'='*75}")
    print(f"  Intent accuracy:    {intent_correct}/{intent_scoreable} "
          f"({intent_correct/intent_scoreable*100:.1f}%)" if intent_scoreable else "  Intent accuracy:    N/A")
    print(f"  Decision accuracy:  {decision_correct}/{total} "
          f"({decision_correct/total*100:.1f}%)")
    print(f"  Clarification rate: {clarify_count}/{total} "
          f"({clarify_count/total*100:.1f}%)")
    print(f"  Escalation rate:    {escalate_count}/{total} "
          f"({escalate_count/total*100:.1f}%)")
    print(f"  Fallback rate:      {fallback_count}/{total} "
          f"({fallback_count/total*100:.1f}%)")
    print(f"  NLU latency mean:   {mean_latency:.0f} ms")
    print(f"  NLU latency p95:    {p95_latency} ms")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate VoiceRoute on benchmark dataset")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of utterances to evaluate")
    parser.add_argument("--quick", action="store_true", help="Run quick 6-utterance sanity check")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between requests (default: 2.0s for free-tier rate limits)")
    args = parser.parse_args()

    evaluate(limit=args.limit, delay_s=args.delay, quick=args.quick)
