"""In-memory session state. Tracks clarifications and reprompts per session."""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.config import MAX_CLARIFICATIONS, MAX_REPROMPTS


@dataclass
class SessionState:
    clarifications_used: int = 0
    reprompts_used: int = 0
    last_transcript: str = ""
    last_offered_intents: list[str] = field(default_factory=list)


# Simple dict store — fine for a single-process hackathon demo
_sessions: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    """Return existing session or create a new one."""
    if session_id not in _sessions:
        _sessions[session_id] = SessionState()
    return _sessions[session_id]


def record_clarification(
    session_id: str, transcript: str, offered_intents: list[str]
) -> None:
    """Mark that we asked a clarification question this session."""
    s = get_session(session_id)
    s.clarifications_used += 1
    s.last_transcript = transcript
    s.last_offered_intents = offered_intents


def record_reprompt(session_id: str) -> None:
    """Mark that we asked the caller to repeat."""
    get_session(session_id).reprompts_used += 1


def can_clarify(session_id: str) -> bool:
    return get_session(session_id).clarifications_used < MAX_CLARIFICATIONS


def can_reprompt(session_id: str) -> bool:
    return get_session(session_id).reprompts_used < MAX_REPROMPTS


def reset_session(session_id: str) -> None:
    """Clear session state (e.g. when customer changes)."""
    _sessions.pop(session_id, None)

