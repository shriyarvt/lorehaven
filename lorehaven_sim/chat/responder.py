"""Fill templates from a ParsedRequest and a Result. No pricing math."""

from __future__ import annotations

from chat.parser import ParsedRequest
from chat.templates import (
    ASSUMED_ORDER,
    ASSUMPTIONS,
    BEST,
    CLARIFY_DETAIL,
    CLARIFY_LIST,
    CLARIFY_PROMO,
    CLARIFY_ROLE,
    COMPARE_FEWER,
    COMPARE_MORE,
    COMPARE_SAME,
    CONFIDENCE,
    ERROR,
    FOLLOW_UPS,
    HELP,
    HELP_EXAMPLES,
    LIST_LEVELS,
    LIST_MEMBERSHIP,
    LIST_MEMBERSHIP_LINE,
    LIST_SIGNUP,
    LIST_SIGNUP_LINE,
    OBSERVED,
    OFFER,
    PROFIT,
    PROMO_LEVELS,
    ROLE_BUTTONS,
    TRY_NEXT,
    UNDERSTOOD,
)
from sim.constants import LIST_GROUP_LABELS, RATE_LABELS, USER_TYPE_LABELS
from sim.model import Result
from sim.validate import confidence_text


def scenario_words(result: Result) -> str:
    """Describe the scenario with the prices stored on the result."""
    scenario = result.scenario
    parts = [f"list price ${_plain(scenario.list_price)}"]
    if scenario.promo_dollar is not None:
        parts.append(f"promo ${_plain(scenario.promo_dollar)}")
    names = LIST_GROUP_LABELS if scenario.mode == "list" else USER_TYPE_LABELS
    parts.append(names.get(scenario.user_type, scenario.user_type))
    return ", ".join(parts)


def respond(parsed: ParsedRequest, result: Result) -> tuple[str, tuple[str, ...]]:
    """Build the reply and up to three quick replies. Numbers come from `result`."""
    if parsed.intent == "profit_question":
        return _join([PROFIT, CONFIDENCE.format(level=result.confidence, detail=confidence_text(result.confidence))]), _buttons(result)
    if parsed.intent == "explain_assumptions":
        return ASSUMPTIONS, _buttons(result)
    if parsed.intent == "explain_confidence":
        return _join(
            [
                UNDERSTOOD.format(scenario=scenario_words(result)),
                CONFIDENCE.format(level=result.confidence, detail=confidence_text(result.confidence)),
            ]
        ), _buttons(result)
    if parsed.intent == "help":
        return help_text(), HELP_EXAMPLES

    understood = UNDERSTOOD.format(scenario=scenario_words(result))
    if parsed.assumed_order and result.scenario.promo_dollar is not None:
        understood = (
            f"{understood} "
            + ASSUMED_ORDER.format(
                list_price=f"${_plain(result.scenario.list_price)}",
                promo=f"${_plain(result.scenario.promo_dollar)}",
            )
        )
    outcome = " ".join(_outcome(parsed, result))
    comparison = _comparison(result)
    warning = result.warnings[0] if result.warnings else ""
    detail = confidence_text(result.confidence)
    if warning:
        detail = f"{detail} {warning}"
    confidence = CONFIDENCE.format(level=result.confidence, detail=detail)
    buttons = _buttons(result)
    sentences = [understood, outcome, comparison, confidence, TRY_NEXT.format(suggestions=_english(buttons))]
    return _join(sentences), buttons


def help_text() -> str:
    return HELP.format(examples=_english(HELP_EXAMPLES))


def clarify_text(kind: str, amount: float | None) -> tuple[str, tuple[str, ...]]:
    """One short question. Buttons are the only suggested answers."""
    if kind == "price_role" and amount is not None:
        return CLARIFY_ROLE.format(amount=f"${_plain(amount)}"), ROLE_BUTTONS
    if kind == "need_promo":
        return CLARIFY_PROMO, ()
    if kind == "need_list":
        return CLARIFY_LIST, ()
    return CLARIFY_DETAIL, ("Promo", "List price")


def error_text(message: str) -> tuple[str, tuple[str, ...]]:
    return ERROR.format(message=message), HELP_EXAMPLES


def _outcome(parsed: ParsedRequest, result: Result) -> list[str]:
    if result.members_per_100 is not None and result.revenue_per_person is not None:
        lines = [
            PROMO_LEVELS.format(
                rate_label=RATE_LABELS.get(result.scenario.user_type, RATE_LABELS["everyone"]),
                rate=_num(result.members_per_100, 2),
                revenue=_money(result.revenue_per_person, 2),
            )
        ]
        if parsed.intent == "best_price":
            lines.append(_best_sentence(result))
        return lines
    if result.scenario.mode == "list" and result.list_n is not None:
        return [_list_sentence(result)]
    if result.scenario.mode == "list" and (
        result.signup_per_100 is not None or result.offer_signup_per_100 is not None
    ):
        lines = []
        if result.signup_per_100 is not None:
            lines.append(
                LIST_LEVELS.format(
                    signup=_num(result.signup_per_100, 2),
                    lift=_num(result.signup_lift_pp or 0, 2),
                    observed=_plain(result.observed_price or 0),
                    comparison=_plain(result.comparison_price or 0),
                    needed=_num(result.needed_gain_pp or 0, 2),
                )
            )
        if result.offer_signup_per_100 is not None:
            lines.append(
                OFFER.format(
                    label=result.offer_label or "",
                    signup=_num(result.offer_signup_per_100, 2),
                    lift=_num(result.offer_signup_lift_pp or 0, 2),
                    signup_low=_num(result.offer_signup_ci_low_pp or 0, 2),
                    signup_high=_num(result.offer_signup_ci_high_pp or 0, 2),
                    revenue_baseline=_money(result.offer_revenue_baseline or 0, 2),
                    revenue_lift=_money(result.offer_revenue_lift or 0, 2),
                    revenue_low=_money(result.offer_revenue_ci_low or 0, 2),
                    revenue_high=_money(result.offer_revenue_ci_high or 0, 2),
                    signup_confidence=result.observed_signup_confidence or "",
                    revenue_confidence=result.observed_revenue_confidence or "",
                )
            )
        elif (
            result.scenario.list_price == result.observed_price
            and result.observed_signup_lift_pp is not None
        ):
            lines.append(
                OBSERVED.format(
                    signup_confidence=result.observed_signup_confidence or "",
                    revenue_confidence=result.observed_revenue_confidence or "",
                )
            )
        return lines
    if result.warnings:
        return [result.warnings[0]]
    return []


def _list_sentence(result: Result) -> str:
    label = LIST_GROUP_LABELS.get(result.scenario.user_type, result.scenario.user_type)
    digits = 3 if abs(result.revenue_lift or 0) < 1 else 2
    low_digits = 3 if abs(result.revenue_ci_low or 0) < 1 else 2
    high_digits = 3 if abs(result.revenue_ci_high or 0) < 1 else 2
    revenue = _signed_money(result.revenue_lift or 0, digits)
    revenue_low = _signed_money(result.revenue_ci_low or 0, low_digits)
    revenue_high = _signed_money(result.revenue_ci_high or 0, high_digits)
    if result.signup_lift_pp is not None and result.signup_ci_low_pp is None:
        return LIST_SIGNUP_LINE.format(label=label, signup=_num(result.signup_lift_pp, 2), revenue=revenue)
    if result.signup_lift_pp is None and result.membership_ci_low_pp is None:
        return LIST_MEMBERSHIP_LINE.format(
            label=label,
            membership=_num(result.membership_lift_pp or 0, 2),
            revenue=revenue,
        )
    if result.signup_lift_pp is not None:
        return LIST_SIGNUP.format(
            label=label,
            signup=_num(result.signup_lift_pp, 2),
            signup_low=_num(result.signup_ci_low_pp or 0, 2),
            signup_high=_num(result.signup_ci_high_pp or 0, 2),
            revenue=revenue,
            revenue_low=revenue_low,
            revenue_high=revenue_high,
        )
    return LIST_MEMBERSHIP.format(
        label=label,
        membership=_num(result.membership_lift_pp or 0, 2),
        membership_low=_num(result.membership_ci_low_pp or 0, 2),
        membership_high=_num(result.membership_ci_high_pp or 0, 2),
        revenue=revenue,
        revenue_low=revenue_low,
        revenue_high=revenue_high,
    )


def _best_sentence(result: Result) -> str:
    return BEST.format(dollars=_dollar_list(result.best_dollars))


def _comparison(result: Result) -> str:
    if result.vs_baseline is None:
        return ""
    if abs(result.vs_baseline) < 0.0005:
        return COMPARE_SAME
    if result.vs_baseline > 0:
        return COMPARE_MORE.format(delta=_money(result.vs_baseline, 2))
    return COMPARE_FEWER.format(delta=_money(abs(result.vs_baseline), 2))


def _buttons(result: Result) -> tuple[str, ...]:
    picks: list[str] = []
    for price in result.quick_prices:
        label = f"Try promo ${_plain(price)}"
        if label not in picks:
            picks.append(label)
        if len(picks) == 1:
            break
    for label in FOLLOW_UPS:
        if label not in picks:
            picks.append(label)
    return tuple(picks[:3])


def _dollar_list(prices: tuple[float, ...]) -> str:
    labels = [f"${_plain(price)}" for price in prices]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return " and ".join(labels)


def _english(items: tuple[str, ...]) -> str:
    values = list(items)
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} or {values[1]}"
    return f"{', '.join(values[:-1])}, or {values[-1]}"


def _join(sentences: list[str]) -> str:
    return " ".join(sentence.strip() for sentence in sentences if sentence.strip())


def _plain(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _num(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def _money(value: float, digits: int) -> str:
    return f"${_num(value, digits)}"


def _signed_money(value: float, digits: int) -> str:
    text = _money(abs(value), digits)
    if value < 0:
        return f"-{text}"
    if value > 0:
        return f"+{text}"
    return text
