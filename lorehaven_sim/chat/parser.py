"""Turn one message into a ParsedRequest. This file does not score a price."""

from __future__ import annotations

import re
from dataclasses import dataclass

from chat.intents import (
    DOLLAR_PATTERN,
    INTENT_PATTERNS,
    LIST_WORDS,
    PRESET_PATTERNS,
    PROMO_WORDS,
    USER_TYPE_PATTERNS,
)


@dataclass(frozen=True)
class ParsedRequest:
    """Slots pulled from one message. Unset slots stay None so the current scenario remains."""

    intent: str
    list_price: float | None = None
    promo_dollar: float | None = None
    user_type: str | None = None
    horizon: int | None = None
    preset: str | None = None
    raw_text: str = ""
    assumed_order: bool = False
    ambiguous_number: float | None = None
    clarify: str | None = None


def parse(text: str) -> ParsedRequest:
    """Read intent and slots. Never guess when a bare number could be either price."""
    raw = "" if text is None else str(text)
    lowered = raw.strip().lower()
    if not lowered:
        return ParsedRequest(intent="help", raw_text=raw)

    working = lowered
    working, list_price = _take_number(working, LIST_WORDS)
    working, promo_dollar = _take_number(working, PROMO_WORDS)
    user_type = _user_type(lowered)
    preset = _preset(lowered)
    assumed_order = False
    ambiguous = None
    leftover = _numbers(working)
    if list_price is None and promo_dollar is None and len(leftover) == 2:
        first, second = leftover
        if first == second:
            list_price = first
            promo_dollar = second
        else:
            list_price = max(first, second)
            promo_dollar = min(first, second)
            assumed_order = True
    elif list_price is None and promo_dollar is None and len(leftover) == 1:
        ambiguous = leftover[0]

    intent = _intent(lowered)
    if intent is None and any(
        value is not None for value in (list_price, promo_dollar, user_type, preset, ambiguous)
    ):
        intent = "set_scenario"
    if intent is None:
        intent = "help"
    if preset is not None:
        intent = "apply_preset"

    clarify = _clarify(lowered, intent, list_price, promo_dollar, ambiguous, user_type)
    return ParsedRequest(
        intent=intent,
        list_price=list_price,
        promo_dollar=promo_dollar,
        user_type=user_type,
        horizon=None,
        preset=preset,
        raw_text=raw,
        assumed_order=assumed_order,
        ambiguous_number=ambiguous,
        clarify=clarify,
    )


def _take_number(text: str, keywords: tuple[str, ...]) -> tuple[str, float | None]:
    pattern = re.compile(
        rf"(?:{'|'.join(keywords)})\D{{0,24}}?{DOLLAR_PATTERN}"
    )
    match = pattern.search(text)
    if match is None:
        return text, None
    start, end = match.span(1)
    blank = text[:start] + (" " * (end - start)) + text[end:]
    return blank, float(match.group(1))


def _numbers(text: str) -> list[float]:
    return [float(value) for value in re.findall(DOLLAR_PATTERN, text)]


def _user_type(text: str) -> str | None:
    for name, patterns in USER_TYPE_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return name
    return None


def _preset(text: str) -> str | None:
    for name, patterns in PRESET_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return name
    return None


def _intent(text: str) -> str | None:
    for name, patterns in INTENT_PATTERNS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            return name
    return None


def _clarify(
    text: str,
    intent: str,
    list_price: float | None,
    promo_dollar: float | None,
    ambiguous: float | None,
    user_type: str | None,
) -> str | None:
    if ambiguous is not None and list_price is None and promo_dollar is None:
        return "price_role"
    if intent not in {"set_scenario", "what_if"}:
        return None
    if any(value is not None for value in (list_price, promo_dollar, user_type)):
        return None
    if re.search(r"promo|discount|offer", text):
        return "need_promo"
    if re.search(r"list|base", text):
        return "need_list"
    if intent == "what_if":
        return "need_detail"
    return None
