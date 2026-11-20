"""Reply wording. No calculations live here."""

from __future__ import annotations

UNDERSTOOD = "I understood: {scenario}."
ASSUMED_ORDER = "I read {list_price} as the list price and {promo} as the promo."
PROMO_LEVELS = (
    "{rate_label}: {rate}%. "
    "Revenue per person offered is {revenue}."
)
COMPARE_MORE = "That is {delta} more than the current policy."
COMPARE_FEWER = "That is {delta} fewer than the current policy."
COMPARE_SAME = "That matches the current policy."
CONFIDENCE = "Confidence is {level}. {detail}"
BEST = "The best promo this season is {dollars}."
LIST_LEVELS = (
    "{signup}% of at-risk people join, {lift} percentage points versus the counterfactual. "
    "The curve passes through the two observed prices, ${observed} and ${comparison}. "
    "The join rate has to rise by {needed} percentage points "
    "to match revenue per joiner at the comparison price."
)
OBSERVED = (
    "Confidence in the size of that lift is {signup_confidence}. "
    "Revenue from that comparison has confidence {revenue_confidence}."
)
LIST_SIGNUP = (
    "{label}: sign-up changes by {signup} percentage points ({signup_low} to {signup_high}). "
    "Revenue per customer-season changes by {revenue} ({revenue_low} to {revenue_high})."
)
LIST_MEMBERSHIP = (
    "{label}: membership changes by {membership} percentage points "
    "({membership_low} to {membership_high}). "
    "Revenue per customer-season changes by {revenue} ({revenue_low} to {revenue_high})."
)
LIST_SIGNUP_LINE = (
    "{label}: sign-up changes by {signup} percentage points along the line. "
    "Revenue per customer-season changes by {revenue}."
)
LIST_MEMBERSHIP_LINE = (
    "{label}: membership changes by {membership} percentage points along the line. "
    "Revenue per customer-season changes by {revenue}."
)
OFFER = (
    "{label}: {signup}% of at-risk people join at the baseline, and the cut "
    "adds {lift} percentage points ({signup_low} to {signup_high}). "
    "Revenue per person at risk is {revenue_baseline} at the baseline and "
    "{revenue_lift} higher ({revenue_low} to {revenue_high}). "
    "Sign-up confidence is {signup_confidence}. Revenue confidence is {revenue_confidence}."
)
PROFIT = (
    "This is revenue, not profit. Cost to serve is assumed zero, so nothing is subtracted."
)
ASSUMPTIONS = (
    "A promo inside the tested grid was randomized. The list-price curve is the "
    "linear-probability elasticity through the two observed prices, $12 and $15. "
    "No other list price can be selected. Revenue is this season only. "
    "Revenue is not profit, and cost to serve is assumed zero."
)
ERROR = "I can't use that. {message}"
CLARIFY_ROLE = "Is {amount} the list price or the promo dollar?"
CLARIFY_PROMO = "What promo dollar should I use?"
CLARIFY_LIST = "What list price should I use?"
CLARIFY_DETAIL = "What should I change: the promo, the list price, or the group?"
HELP = (
    "I can set a promo or a list price, apply a preset, and read the simulator. "
    "Try one of these: {examples}."
)
TRY_NEXT = "Try next: {suggestions}."
CAPTION = (
    "Scripted assistant. It understands a fixed set of questions and always "
    "uses the simulator's numbers."
)

HELP_EXAMPLES = (
    "What is the best promo?",
    "What if the promo is lower?",
    "Compare to baseline",
    "Is this profit?",
)

ROLE_BUTTONS = ("List price", "Promo dollar")
FOLLOW_UPS = ("Compare to baseline", "Show best price")
