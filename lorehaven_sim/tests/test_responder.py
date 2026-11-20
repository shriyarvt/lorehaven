"""The assistant reply is stable, and every number in it comes from the Result."""

from __future__ import annotations

import json
import re
from dataclasses import asdict

from chat.assistant import handle
from sim.model import Scenario, baseline_scenario

PROMPTS = (
    "promo $8",
    "what if promo is $8 for lapsed users",
    "best price?",
    "compare to baseline",
    "is this profit?",
    "list price 13",
)


def test_including_promos_reply_uses_that_comparison():
    scenario = Scenario(12, None, "acquisition_promo", 0, "list")
    turn = handle("list price 12", scenario, None)
    assert turn.result is not None
    assert turn.scenario.user_type == "acquisition_promo"
    assert "4.32" in turn.text
    assert "0.337" in turn.text
    assert "Lapsed + new, including promos" in turn.text
    assert "8.52" not in turn.text


def test_list_price_15_stays_one_comparison_on_the_list_page():
    scenario = Scenario(12, None, "everyone", 0, "list")
    turn = handle("list price 15", scenario, None)
    assert turn.scenario.list_price == 15
    assert turn.scenario.mode == "list"
    assert "membership changes by 0.00" in turn.text


def test_list_price_15_on_the_promo_page_switches_the_grid():
    scenario = Scenario(12, 11, "everyone", 0, "promo")
    turn = handle("list price 15", scenario, None)
    assert turn.scenario.mode == "promo"
    assert turn.scenario.list_price == 15


def test_same_input_twice_is_identical():
    scenario = baseline_scenario()
    for prompt in PROMPTS:
        first = handle(prompt, scenario, None)
        second = handle(prompt, scenario, None)
        assert first.text == second.text
        assert first.buttons == second.buttons
        assert first.scenario == second.scenario


def test_every_number_in_a_reply_appears_in_the_result():
    scenario = Scenario(12, 11, "everyone", 0, "promo")
    for prompt in ("promo $8", "what if promo is $10", "best price?"):
        turn = handle(prompt, scenario, None)
        assert turn.result is not None, prompt
        blob = json.dumps(asdict(turn.result))
        for token in re.findall(r"\d[\d,]*(?:\.\d+)?", turn.text):
            assert _appears(token, turn.result, blob), f"{prompt}: {token} not in the result"


def _appears(token: str, result, blob: str) -> bool:
    plain = token.replace(",", "")
    if plain in blob or token in blob:
        return True
    number = float(plain)
    for value in result.numeric_values():
        candidates = (
            value,
            abs(value),
            round(value, 1),
            round(value, 2),
            round(value, 3),
            round(value),
            round(abs(value), 1),
            round(abs(value), 2),
            round(abs(value), 3),
        )
        if any(abs(number - candidate) < 1e-9 for candidate in candidates):
            return True
    return False
