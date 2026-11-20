"""Labels, ranges, and confidence names. Estimate numbers live in data/estimates.json."""

from __future__ import annotations

# 95% normal interval. A gap ties when the estimate is within this many
# standard errors of zero.
Z_95 = 1.96

# Best-dollar search steps through the tested grid at this spacing.
PRICE_STEP = 0.1

# Promo curves exist only at these list prices. The key is the list price
# and the value is the tested promo grid.
PROMO_GRID = {
    12.0: (7.0, 11.0),
    15.0: (10.0, 14.0),
}

USER_TYPES = ("everyone", "recurring", "lapsed", "new")
USER_TYPE_LABELS = {
    "everyone": "Everyone",
    "recurring": "Recurring",
    "lapsed": "Lapsed",
    "new": "New",
}
# List-price rows. Everyone is all customers. The last two pool lapsed and new.
LIST_GROUP_TYPES = USER_TYPES + ("acquisition", "acquisition_promo")
LIST_OFFER_TYPES = ("acquisition", "acquisition_promo")
LIST_OFFER_LABELS = {
    "acquisition": "*Lapsed + new, excluding promos",
    "acquisition_promo": "Lapsed + new, including promos",
}
LIST_GROUP_LABELS = {
    **USER_TYPE_LABELS,
    "everyone": "Total pooled",
    **LIST_OFFER_LABELS,
}
MEMBERS_LABELS = {
    "everyone": "People who stay members",
    "recurring": "People who stay members",
    "lapsed": "People who rejoin",
    "new": "People who join",
}
# Same number as a rate per hundred. Display these as percents.
RATE_LABELS = {
    "everyone": "% who stay members",
    "recurring": "% who stay members",
    "lapsed": "% who rejoin",
    "new": "% who join for the first time",
}
AT_RISK_JOIN_LABEL = "% of at-risk people who join"

MODES = ("promo", "list")
MODE_LABELS = {
    "promo": "Promo price",
    "list": "List price",
}

PRESET_CURRENT = "current_policy"
PRESET_REVENUE_MAX = "revenue_max"
PRESET_LABELS = {
    PRESET_CURRENT: "Current policy",
    PRESET_REVENUE_MAX: "Revenue-max this season",
}

CONFIDENCE_HIGH = "High"
CONFIDENCE_LOW_MODERATE = "Low-Moderate"
CONFIDENCE_LOW = "Low"

# High: a randomized promo inside the tested grid.
# Low-Moderate: the observed list-price sign-up comparison, which was not randomized.
# Low: extrapolation, the elasticity assumption, or list-price revenue.
CONFIDENCE_HELP = {
    CONFIDENCE_HIGH: "This promo dollar is inside the randomized test.",
    CONFIDENCE_LOW_MODERATE: "List price was not randomized. Treat the sign-up comparison as suggestive.",
    CONFIDENCE_LOW: "This is outside the test, or it is a list-price revenue claim. Treat it as a sketch.",
}

COST_NOTE = "Revenue is not profit. Cost to serve is assumed zero."

HELP = {
    "mode": "Promo price uses the randomized offer. List price uses the $15 to $12 cut.",
    "list_price": (
        "On List price, the slider reads the straight line from $12 to $15. "
        "On Promo price, only $12 and $15 choose a promo grid."
    ),
    "promo": "The tested offer after the cut is $7 to $11 (list $12). Before the cut it is $10 to $14 (list $15).",
    "user_type": (
        "On Promo price, Everyone, Recurring, Lapsed, and New each use their own offer curve. "
        "On List price, each group uses its own $15 to $12 result. "
        "Two more rows pool lapsed and new: excluding promos, and including promos. "
        "Everyone on List price is Total pooled."
    ),
    "per_type": "Shows the best dollar for each group this season. It does not score a dollar you type for that group.",
    "preset": "Current policy is list $12 and promo $11. Revenue-max picks the promo with the highest this-season revenue at list $12.",
    "compare": "Shows the change against list $12, promo $11, this season only.",
}
