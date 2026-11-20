"""Input checks, range warnings, and confidence labels. No revenue math."""

from __future__ import annotations

from sim.constants import (
    CONFIDENCE_HELP,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    LIST_GROUP_LABELS,
    LIST_OFFER_TYPES,
    MODES,
    PROMO_GRID,
    USER_TYPES,
    USER_TYPE_LABELS,
)
from sim.estimates import Estimates


def check_scenario(
    list_price: float,
    promo_dollar: float | None,
    user_type: str,
    horizon_extra_seasons: int,
    mode: str,
) -> None:
    """Raise ValueError with a short message when an input cannot be simulated."""
    if mode not in MODES:
        raise ValueError("Choose Promo price or List price.")
    allowed = USER_TYPES + LIST_OFFER_TYPES if mode == "list" else USER_TYPES
    if user_type not in allowed:
        labels = LIST_GROUP_LABELS if mode == "list" else USER_TYPE_LABELS
        names = ", ".join(labels[name] for name in allowed)
        raise ValueError(f"Choose a group: {names}.")
    if horizon_extra_seasons != 0:
        raise ValueError("Later seasons are not estimated.")
    if list_price is None or list_price != list_price or list_price <= 0:
        raise ValueError("Enter a list price above zero.")
    price = float(list_price)
    if mode == "list":
        if price < 12 or price > 15:
            raise ValueError("Choose a list price from $12 to $15.")
    elif price not in PROMO_GRID:
        raise ValueError("Choose a list price of $12 or $15. Other list prices were not offered.")
    promo_required = mode == "promo"
    if promo_required and promo_dollar is None:
        low, high = PROMO_GRID[float(list_price)]
        raise ValueError(
            f"Enter a promo dollar. At a list price of ${list_price:g} the tested "
            f"range is ${low:g} to ${high:g}."
        )
    if promo_dollar is None:
        return
    if promo_dollar != promo_dollar or promo_dollar <= 0:
        raise ValueError("Enter a promo dollar above zero.")
    if promo_dollar >= list_price:
        extra = _tested_range_sentence(list_price)
        raise ValueError(
            f"The promo dollar has to be below the list price. "
            f"Promo ${promo_dollar:g} is not below list ${list_price:g}.{extra}"
        )


def range_warnings(
    list_price: float,
    promo_dollar: float | None,
    mode: str,
    estimates: Estimates,
    user_type: str = "everyone",
) -> list[str]:
    """Warnings for prices the model will still score. An empty list means in range."""
    warnings: list[str] = []
    era = estimates.era_for_list_price(list_price)
    if promo_dollar is not None and era is not None and mode == "promo":
        low = era.membership[0].price
        high = era.membership[-1].price
        if promo_dollar < low or promo_dollar > high:
            warnings.append(
                f"Promo ${promo_dollar:g} is outside the tested range of "
                f"${low:g} to ${high:g}. The line is extended from the two nearest "
                "tested dollars, and confidence is Low."
            )
    return warnings


def promo_confidence(extrapolated: bool) -> str:
    """High inside the randomized grid. Low when the line is extended."""
    if extrapolated:
        return CONFIDENCE_LOW
    return CONFIDENCE_HIGH


def list_curve_confidence() -> str:
    """The constant-elasticity list-price curve is an assumption."""
    return CONFIDENCE_LOW


def observed_signup_confidence() -> str:
    """The $12 versus $15 comparison was not randomized."""
    return CONFIDENCE_LOW


def observed_revenue_confidence() -> str:
    """List-price revenue is not a clean causal estimate."""
    return CONFIDENCE_LOW


def confidence_text(level: str) -> str:
    """Plain-language sentence for a confidence badge."""
    return CONFIDENCE_HELP.get(level, level)


def _tested_range_sentence(list_price: float) -> str:
    grid = PROMO_GRID.get(float(list_price))
    if grid is None:
        return ""
    return f" At a list price of ${list_price:g} the tested promo dollars are ${grid[0]:g} to ${grid[1]:g}."
