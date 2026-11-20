"""Choose the AI assistant or the scripted fallback. This module does not score a price."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from chat.gate import PasscodeGate
from chat.limits import (
    BASIC_CAPTION,
    DAILY_CAP_CAPTION,
    OVERSIZE_MESSAGE,
    SESSION_LIMIT_CAPTION,
    AiSettings,
    DailyCap,
    SessionQuota,
    reject_oversize,
)
from chat.prompt import request_payload
from chat.status import REASON_UNAVAILABLE, log_api_error


@dataclass(frozen=True)
class Route:
    mode: str
    caption: str
    reply: str
    called_client: bool
    reason: str = ""


def submit(
    message: str,
    *,
    secrets_ok: bool,
    gate: PasscodeGate,
    session: SessionQuota,
    daily: DailyCap,
    day: date,
    history: list[dict],
    analysis: str,
    client,
    settings: AiSettings,
) -> Route:
    """Call the client only when the gate, session, and daily cap all allow it.

    A client error does not use a session question. It does use one daily attempt.
    """
    if not secrets_ok or gate.locked_out() or not gate.unlocked:
        return Route("basic", BASIC_CAPTION, "", False)
    if not session.allow():
        return Route("basic", SESSION_LIMIT_CAPTION, "", False)
    if not daily.allow(day):
        return Route("basic", DAILY_CAP_CAPTION, "", False)
    too_long = reject_oversize(message, settings.max_input_chars)
    if too_long:
        return Route("basic", too_long, "", False)

    payload = request_payload(analysis, history, message, settings)
    daily.record_attempt(day)
    try:
        reply = client.complete(payload)
    except Exception as exc:
        log_api_error(exc)
        return Route("basic", BASIC_CAPTION, "", True, reason=REASON_UNAVAILABLE)
    session.record_success()
    return Route("ai", "", str(reply), True)
