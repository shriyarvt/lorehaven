"""Table of messages and the request the parser should return."""

from __future__ import annotations

import pytest

from chat.assistant import handle
from chat.parser import parse
from sim.model import baseline_scenario

CASES = [
    ("promo $8", {"intent": "set_scenario", "promo_dollar": 8}),
    ("PROMO $8", {"intent": "set_scenario", "promo_dollar": 8}),
    ("list price 13", {"intent": "set_scenario", "list_price": 13}),
    ("set promo to 9 for lapsed", {"intent": "set_scenario", "promo_dollar": 9, "user_type": "lapsed"}),
    ("4 seasons", {"intent": "set_scenario", "clarify": "price_role", "ambiguous_number": 4, "horizon": None}),
    ("for new customers", {"intent": "set_scenario", "user_type": "new"}),
    ("what if promo is $8 for lapsed users", {"intent": "what_if", "promo_dollar": 8, "user_type": "lapsed"}),
    ("list price 13 promo 9 4 seasons", {"intent": "set_scenario", "list_price": 13, "promo_dollar": 9, "horizon": None}),
    ("best price?", {"intent": "best_price"}),
    ("is this profit?", {"intent": "profit_question"}),
    ("asdf", {"intent": "help"}),
    ("promo $20", {"intent": "set_scenario", "promo_dollar": 20}),
    ("promo 12 list 12", {"intent": "set_scenario", "promo_dollar": 12, "list_price": 12}),
    ("how about $10", {"intent": "what_if", "clarify": "price_role", "ambiguous_number": 10}),
    ("try promo $7", {"intent": "what_if", "promo_dollar": 7}),
    ("current policy", {"intent": "apply_preset", "preset": "current_policy"}),
    ("revenue max", {"intent": "apply_preset", "preset": "revenue_max"}),
    ("best this season", {"intent": "apply_preset", "preset": "revenue_max"}),
    ("long horizon", {"intent": "help", "preset": None}),
    ("compare to baseline", {"intent": "compare"}),
    ("vs current", {"intent": "compare"}),
    ("how sure are you", {"intent": "explain_confidence"}),
    ("what are the assumptions", {"intent": "explain_assumptions"}),
    ("reset", {"intent": "reset"}),
    ("this season only", {"intent": "set_scenario", "horizon": None}),
    ("13 and 9", {"intent": "set_scenario", "list_price": 13, "promo_dollar": 9, "assumed_order": True}),
    ("help", {"intent": "help"}),
    ("what can you do", {"intent": "help"}),
    ("for recurring members", {"intent": "set_scenario", "user_type": "recurring"}),
    ("discount $8", {"intent": "set_scenario", "promo_dollar": 8}),
    ("base price 15", {"intent": "set_scenario", "list_price": 15}),
    ("", {"intent": "help"}),
    ("1 more season", {"intent": "set_scenario", "clarify": "price_role", "ambiguous_number": 1, "horizon": None}),
    ("came back customers promo 10", {"intent": "set_scenario", "user_type": "lapsed", "promo_dollar": 10}),
    ("first-time buyers", {"intent": "set_scenario", "user_type": "new"}),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_parse_table(text, expected):
    parsed = parse(text)
    for field, value in expected.items():
        assert getattr(parsed, field) == value, f"{text!r} field {field}"


def test_a_custom_list_price_is_refused():
    turn = handle("list price 13", baseline_scenario(), None)
    assert turn.result is None
    assert "$12" in turn.text and "$15" in turn.text
    assert turn.scenario.list_price == 12


def test_promo_20_is_an_out_of_range_reply():
    turn = handle("promo $20", baseline_scenario(), None)
    assert turn.result is None
    assert "below the list price" in turn.text
    assert "$7" in turn.text and "$11" in turn.text


def test_promo_equal_to_list_is_invalid():
    turn = handle("promo 12 list 12", baseline_scenario(), None)
    assert turn.result is None
    assert "below the list price" in turn.text


def test_a_bare_number_asks_instead_of_guessing():
    turn = handle("9", baseline_scenario(), None)
    assert turn.result is None
    assert turn.pending is not None
    assert "list price or the promo" in turn.text
    follow = handle("promo", baseline_scenario(), turn.pending)
    assert follow.result is not None
    assert follow.scenario.promo_dollar == 9
