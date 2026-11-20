"""Choose AI or basic mode for one turn. This module does not score a price."""

from __future__ import annotations

import re
from dataclasses import dataclass

from chat.assistant import Pending, Turn, handle
from chat.intents import INTENT_PATTERNS
from chat.limits import AiSettings, reject_oversize
from chat.llm_assistant import ask_ai
from chat.parser import parse
from chat.status import (
    REASON_DAILY,
    REASON_NO_SECRETS,
    REASON_PACKAGE,
    REASON_PASSCODE,
    REASON_SESSION,
    REASON_UNAVAILABLE,
    anthropic_importable,
)
from chat.templates import HELP_EXAMPLES
from sim.model import Scenario

MODE_AI = "AI assistant"
MODE_BASIC = "Basic (scripted)"
AI_BUTTONS = (
    "What does 'at risk' mean?",
    "Why is $11 best for recurring users?",
    "Why can't we trust the list-price result?",
    "What does 'parallel trends' mean?",
    "What happens if members stay longer than one season?",
)
UNAVAILABLE_NOTE = "AI is unavailable, here is the basic answer."
CANNOT_ANSWER = "The basic assistant can't answer that."


@dataclass(frozen=True)
class Taken:
    """What the page stores after one message."""

    reply: str
    radio: str
    locked_basic: bool
    lock_reason: str
    reason: str
    called_client: bool
    queue: Scenario | None
    buttons: tuple[str, ...] | None
    pending: Pending | None
    show_comparison: bool


def apply_radio(radio: str, *, locked_basic: bool) -> str:
    """A limit keeps the choice on Basic. Anything else follows the radio."""
    if locked_basic:
        return MODE_BASIC
    if radio == MODE_AI:
        return MODE_AI
    return MODE_BASIC


def ai_buttons_enabled(*, radio: str, unlocked: bool, locked_basic: bool, secrets_ok: bool) -> bool:
    """AI buttons stay off until the passcode is accepted and AI is allowed."""
    return radio == MODE_AI and unlocked and not locked_basic and secrets_ok


def status_line(
    *,
    radio: str,
    unlocked: bool,
    locked_basic: bool,
    lock_reason: str,
    notice: str,
    secrets_ok: bool,
) -> str:
    """A reason only when AI was requested and cannot run, or a limit is in force."""
    if locked_basic:
        return lock_reason
    if radio == MODE_AI and not secrets_ok:
        return REASON_NO_SECRETS
    if radio == MODE_AI and not unlocked:
        return REASON_PASSCODE
    return notice


def scripted_recognizes(text: str) -> bool:
    """True when the scripted assistant has an intent for this message."""
    parsed = parse(text)
    if parsed.intent != "help":
        return True
    lowered = "" if text is None else str(text).strip().lower()
    return any(re.search(pattern, lowered) for pattern in INTENT_PATTERNS["help"])


def take_turn(
    text: str,
    *,
    radio: str,
    unlocked: bool,
    locked_basic: bool,
    lock_reason: str,
    history: list[dict],
    session,
    daily,
    day,
    scenario: Scenario,
    pending: Pending | None,
    secrets_ok: bool,
    client_factory,
    settings: AiSettings,
    on_text,
) -> Taken:
    """Answer one message. A limit locks the radio on Basic. A failure does not use a question."""
    radio = apply_radio(radio, locked_basic=locked_basic)
    too_long = reject_oversize(text, settings.max_input_chars)
    if too_long:
        return Taken(
            reply=too_long,
            radio=radio,
            locked_basic=locked_basic,
            lock_reason=lock_reason,
            reason="",
            called_client=False,
            queue=None,
            buttons=None,
            pending=pending,
            show_comparison=False,
        )
    if _wants_ai(radio, unlocked, locked_basic, secrets_ok) and not session.allow():
        return _locked_scripted(
            text, scenario, pending, REASON_SESSION, history_unused=history
        )
    if _wants_ai(radio, unlocked, locked_basic, secrets_ok) and not daily.allow(day):
        return _locked_scripted(text, scenario, pending, REASON_DAILY, history_unused=history)
    if not _wants_ai(radio, unlocked, locked_basic, secrets_ok):
        reply, turn = _scripted(text, scenario, pending)
        reason = status_line(
            radio=radio,
            unlocked=unlocked,
            locked_basic=locked_basic,
            lock_reason=lock_reason,
            notice="",
            secrets_ok=secrets_ok,
        )
        return _from_scripted(
            reply,
            turn,
            radio=radio,
            locked_basic=locked_basic,
            lock_reason=lock_reason,
            reason=reason,
        )
    if not anthropic_importable():
        return _failed(text, scenario, pending, REASON_PACKAGE, called_client=False)
    outcome = ask_ai(
        message=text,
        history=[{"role": item["role"], "content": item["text"]} for item in history],
        analysis=_analysis_or_empty(),
        client=client_factory(),
        settings=settings,
        on_text=on_text,
        session=session,
        daily=daily,
        day=day,
    )
    if not outcome.ok:
        return _failed(text, scenario, pending, REASON_UNAVAILABLE, called_client=True)
    return Taken(
        reply=outcome.text,
        radio=MODE_AI,
        locked_basic=False,
        lock_reason="",
        reason="",
        called_client=True,
        queue=outcome.scenario,
        buttons=None,
        pending=None,
        show_comparison=False,
    )


def _wants_ai(radio: str, unlocked: bool, locked_basic: bool, secrets_ok: bool) -> bool:
    return ai_buttons_enabled(
        radio=radio,
        unlocked=unlocked,
        locked_basic=locked_basic,
        secrets_ok=secrets_ok,
    )


def _scripted(text: str, scenario: Scenario, pending: Pending | None) -> tuple[str, Turn | None]:
    if not scripted_recognizes(text):
        return CANNOT_ANSWER, None
    turn = handle(text, scenario, pending)
    return turn.text, turn


def _failed(
    text: str,
    scenario: Scenario,
    pending: Pending | None,
    reason: str,
    *,
    called_client: bool,
) -> Taken:
    """Same-turn scripted answer. The radio moves to Basic and the question is not used."""
    body, turn = _scripted(text, scenario, pending)
    if turn is None:
        reply = CANNOT_ANSWER
    else:
        reply = f"{UNAVAILABLE_NOTE} {body}"
    return _from_scripted(
        reply,
        turn,
        radio=MODE_BASIC,
        locked_basic=False,
        lock_reason="",
        reason=reason,
        called_client=called_client,
    )


def _locked_scripted(
    text: str,
    scenario: Scenario,
    pending: Pending | None,
    reason: str,
    *,
    history_unused: list[dict],
) -> Taken:
    del history_unused
    body, turn = _scripted(text, scenario, pending)
    return _from_scripted(
        body,
        turn,
        radio=MODE_BASIC,
        locked_basic=True,
        lock_reason=reason,
        reason=reason,
    )


def _from_scripted(
    reply: str,
    turn: Turn | None,
    *,
    radio: str,
    locked_basic: bool,
    lock_reason: str,
    reason: str,
    called_client: bool = False,
) -> Taken:
    if turn is None:
        return Taken(
            reply=reply,
            radio=radio,
            locked_basic=locked_basic,
            lock_reason=lock_reason,
            reason=reason,
            called_client=called_client,
            queue=None,
            buttons=HELP_EXAMPLES,
            pending=None,
            show_comparison=False,
        )
    return Taken(
        reply=reply,
        radio=radio,
        locked_basic=locked_basic,
        lock_reason=lock_reason,
        reason=reason,
        called_client=called_client,
        queue=turn.scenario if turn.result is not None else None,
        buttons=turn.buttons,
        pending=turn.pending,
        show_comparison=turn.show_comparison,
    )


def _analysis_or_empty() -> str:
    from chat.llm_assistant import load_analysis

    return load_analysis()
