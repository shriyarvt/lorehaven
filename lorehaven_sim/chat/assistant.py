"""Orchestrate one turn: parse, merge, validate, simulate, respond.

Nothing in this module computes a rate, a revenue, or a best dollar.
Those come back from sim.model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from chat.intents import ROLE_ANSWERS
from chat.parser import ParsedRequest, parse
from chat.responder import clarify_text, error_text, help_text, respond
from chat.templates import HELP_EXAMPLES
from sim.constants import LIST_OFFER_TYPES
from sim.model import Result, Scenario, best_dollars, preset_scenario, simulate


@dataclass(frozen=True)
class Pending:
    """A question waiting for the next message."""

    kind: str
    value: float | None = None


@dataclass(frozen=True)
class Turn:
    """What the page should show and store after one message."""

    text: str
    buttons: tuple[str, ...]
    scenario: Scenario
    result: Result | None
    pending: Pending | None
    show_comparison: bool = False


def handle(text: str, scenario: Scenario, pending: Pending | None = None) -> Turn:
    """Answer one message from the current scenario. Same input, same output."""
    cleaned = "" if text is None else str(text).strip()
    if not cleaned:
        return Turn(help_text(), HELP_EXAMPLES, scenario, None, None)

    if pending is not None and _answers_pending(cleaned, pending):
        parsed = _apply_pending(cleaned, pending)
    else:
        parsed = parse(cleaned)

    if parsed.intent == "help":
        return Turn(help_text(), HELP_EXAMPLES, scenario, None, None)
    if parsed.intent == "reset":
        fresh = preset_scenario("current_policy")
        result = simulate(fresh)
        text_out, buttons = respond(parsed, result)
        return Turn(text_out, buttons, fresh, result, None)
    if parsed.clarify:
        question, buttons = clarify_text(parsed.clarify, parsed.ambiguous_number)
        return Turn(
            question,
            buttons,
            scenario,
            None,
            Pending(parsed.clarify, parsed.ambiguous_number),
        )

    try:
        proposed = _propose(scenario, parsed)
        result = simulate(proposed)
    except ValueError as exc:
        message, buttons = error_text(str(exc))
        return Turn(message, buttons, scenario, None, None)

    text_out, buttons = respond(parsed, result)
    return Turn(
        text_out,
        buttons,
        proposed,
        result,
        None,
        show_comparison=parsed.intent in {"compare", "what_if"},
    )


def _propose(scenario: Scenario, parsed: ParsedRequest) -> Scenario:
    if parsed.intent == "apply_preset" and parsed.preset:
        return preset_scenario(parsed.preset)
    if parsed.intent == "best_price":
        dollars = _best_for(scenario)
        promo = scenario.promo_dollar if scenario.promo_dollar in dollars else dollars[0]
        mode = _mode_for(scenario.mode, scenario.list_price, promo)
        return Scenario(
            scenario.list_price,
            promo,
            _promo_group(scenario.user_type, mode),
            0,
            mode,
        )
    list_price = parsed.list_price if parsed.list_price is not None else scenario.list_price
    promo = parsed.promo_dollar if parsed.promo_dollar is not None else scenario.promo_dollar
    mode = _mode_for(scenario.mode, list_price, promo)
    user_type = _promo_group(parsed.user_type or scenario.user_type, mode)
    if mode == "list":
        promo = None
    return Scenario(list_price, promo, user_type, 0, mode)


def _best_for(scenario: Scenario) -> tuple[float, ...]:
    user_type = scenario.user_type if scenario.user_type not in LIST_OFFER_TYPES else "everyone"
    return best_dollars(scenario.list_price, 0, user_type=user_type)


def _promo_group(user_type: str, mode: str) -> str:
    """The two acquisition comparisons exist only on the list-price page."""
    if mode != "list" and user_type in LIST_OFFER_TYPES:
        return "everyone"
    return user_type


def _mode_for(current: str, list_price: float, promo: float | None) -> str:
    """Keep the current page unless the message names the other price."""
    del list_price
    if current == "list" and promo is not None:
        return "promo"
    if current == "promo" and promo is None:
        return "list"
    return current


def _answers_pending(text: str, pending: Pending) -> bool:
    lowered = text.strip().lower()
    if pending.kind == "price_role":
        return lowered in ROLE_ANSWERS
    if pending.kind in {"need_promo", "need_list"} and re.fullmatch(
        r"\$?\s?\d{1,2}(?:\.\d{1,2})?", lowered
    ):
        return True
    return False


def _apply_pending(text: str, pending: Pending) -> ParsedRequest:
    lowered = text.strip().lower()
    if pending.kind == "price_role":
        role = ROLE_ANSWERS[lowered]
        amount = pending.value
        return ParsedRequest(
            intent="set_scenario",
            list_price=amount if role == "list" else None,
            promo_dollar=amount if role == "promo" else None,
            raw_text=text,
        )
    amount = float(re.findall(r"\d{1,2}(?:\.\d{1,2})?", lowered)[0])
    if pending.kind == "need_list":
        return ParsedRequest(intent="set_scenario", list_price=amount, raw_text=text)
    return ParsedRequest(intent="set_scenario", promo_dollar=amount, raw_text=text)
