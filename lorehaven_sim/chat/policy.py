"""Which prices the assistant may treat as tested. No rate or revenue math."""

from __future__ import annotations


def promo_grid_sentence(list_price: float) -> str:
    """The promo grid is known only at the two observed list prices."""
    if abs(float(list_price) - 12.0) < 1e-9:
        return "At a list price of $12 the tested promo grid is $7 to $11."
    if abs(float(list_price) - 15.0) < 1e-9:
        return "At a list price of $15 the tested promo grid is $10 to $14."
    return (
        "Only $12 and $15 have promo data. "
        "A list price between them is an untested straight-line assumption."
    )


PROMO_GRID_RULE = (
    "Only list prices of $12 and $15 have promo data. "
    "At $12 the tested promo grid is $7 to $11. "
    "At $15 the tested promo grid is $10 to $14. "
    "A list price strictly between $12 and $15 has no promo grid. "
    "Treat that list price as an untested straight-line assumption, not a finding. "
    "Refuse a promo outside $10 to $14 before the cut and outside $7 to $11 after the cut."
)
