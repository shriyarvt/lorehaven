"""Input checks: nonsense prices stop, and out-of-grid prices warn."""

from __future__ import annotations

import pytest

from sim.model import Scenario, simulate
from sim.validate import check_scenario, range_warnings
from sim.estimates import load


def test_promo_at_or_above_list_is_rejected():
    with pytest.raises(ValueError, match="below the list price"):
        simulate(Scenario(12, 12, "everyone", 0, "promo"))
    with pytest.raises(ValueError, match="below the list price"):
        check_scenario(12, 20, "everyone", 0, "promo")


def test_a_list_price_other_than_12_or_15_is_rejected():
    with pytest.raises(ValueError, match="from \\$12 to \\$15"):
        simulate(Scenario(10, None, "everyone", 0, "list"))
    with pytest.raises(ValueError, match="\\$12 or \\$15"):
        check_scenario(14, 11, "everyone", 0, "promo")


def test_negative_and_zero_prices_are_rejected():
    with pytest.raises(ValueError, match="above zero"):
        simulate(Scenario(12, -1, "everyone", 0, "promo"))
    with pytest.raises(ValueError, match="above zero"):
        simulate(Scenario(0, 7, "everyone", 0, "promo"))
    with pytest.raises(ValueError, match="above zero"):
        simulate(Scenario(-5, None, "everyone", 0, "list"))


def test_out_of_grid_warns_and_does_not_raise():
    result = simulate(Scenario(12, 6, "everyone", 0, "promo"))
    assert result.extrapolated is True
    assert result.warnings
    warnings = range_warnings(12, 6, "promo", load())
    assert warnings
    assert any("outside" in warning.lower() for warning in warnings)


def test_missing_estimates_file_fails_loudly(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load(tmp_path / "missing.json")
