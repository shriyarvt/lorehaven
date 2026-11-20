"""Intent names, phrase patterns, and synonym tables.

Add a synonym by appending one string. Longer or more specific intents are
listed first, and the first match wins.
"""

from __future__ import annotations

# First match wins. Help is the fallback when nothing else matches.
INTENT_PATTERNS = {
    "reset": (r"\breset\b", r"start over"),
    "profit_question": (r"\bprofit\b", r"\bmargin\b", r"\bcost\b"),
    "explain_confidence": (
        r"how sure",
        r"\bconfidence\b",
        r"\breliable\b",
        r"can i trust",
    ),
    "explain_assumptions": (
        r"assumption",
        r"how does this work",
        r"what does this mean",
    ),
    "apply_preset": (
        r"current policy",
        r"revenue[- ]max",
        r"best this season",
    ),
    "compare": (r"compare to baseline", r"vs current", r"\bdifference\b"),
    "best_price": (
        r"best promo",
        r"best price",
        r"which price",
        r"maximizes revenue",
    ),
    "what_if": (r"what if", r"how about", r"\btry\b"),
    "set_scenario": (
        r"\bpromo\b",
        r"\blist\b",
        r"\bbase\b",
        r"\bdiscount\b",
        r"\boffer\b",
        r"season",
        r"\$",
    ),
    "help": (r"\bhelp\b", r"what can you do"),
}

# A number after one of these words is the list price.
LIST_WORDS = ("list", "base")

# A number after one of these words is the promo dollar.
PROMO_WORDS = ("promo", "discount", "offer")

# Longer phrases first so "current members" is not read as something else.
USER_TYPE_PATTERNS = (
    ("lapsed", (r"came back", r"returning", r"lapsed")),
    ("new", (r"first-time", r"first time", r"\bnew\b")),
    ("recurring", (r"current members", r"existing", r"renewing", r"recurring")),
    ("everyone", (r"everyone", r"\ball\b")),
)

PRESET_PATTERNS = (
    ("current_policy", (r"current policy",)),
    ("revenue_max", (r"revenue[- ]max", r"best this season")),
)

# Spec: a dollar is one or two digits, with an optional cents part.
DOLLAR_PATTERN = r"\$?\s?(\d{1,2}(?:\.\d{1,2})?)"

ROLE_ANSWERS = {
    "list": "list",
    "list price": "list",
    "the list": "list",
    "base": "list",
    "promo": "promo",
    "promo dollar": "promo",
    "the promo": "promo",
    "discount": "promo",
    "offer": "promo",
}
