"""Numeric checks for interpolation, the best dollar, and the list-price hurdle."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from sim.constants import CONFIDENCE_HIGH, CONFIDENCE_LOW
from sim.estimates import DEFAULT_PATH, load
from sim.model import (
    Scenario,
    best_dollars,
    constant_elasticity,
    get_estimates,
    list_group_curves,
    list_price_chart,
    needed_signup_gain,
    signup_lift_view,
    preset_scenario,
    se_gap,
    simulate,
)

def _post(price: float) -> object:
    return simulate(Scenario(12, price, "everyone", 0, "promo"))


def test_interpolation_is_the_midpoint_rate():
    era = get_estimates().era_for_list_price(15)
    left = next(point for point in era.membership if point.price == 10)
    right = next(point for point in era.membership if point.price == 11)
    result = simulate(Scenario(15, 10.5, "everyone", 0, "promo"))
    assert result.members_rate == pytest.approx((left.rate + right.rate) / 2)
    assert result.extrapolated is False
    assert result.confidence == CONFIDENCE_HIGH


def test_exact_knot_uses_the_saved_rate():
    era = get_estimates().era_for_list_price(12)
    saved = next(point for point in era.membership if point.price == 11)
    result = _post(11)
    assert result.members_rate == pytest.approx(saved.rate)
    assert result.revenue_per_person == pytest.approx(saved.revenue)
    assert result.ci_low is not None and result.ci_high is not None
    assert result.ci_low < result.revenue_per_person < result.ci_high


def test_extrapolation_is_flagged_and_low_confidence():
    era = get_estimates().era_for_list_price(12)
    left, right = era.membership[0], era.membership[1]
    expected = left.rate + (6 - left.price) / (right.price - left.price) * (right.rate - left.rate)
    result = _post(6)
    assert result.extrapolated is True
    assert result.confidence == CONFIDENCE_LOW
    assert result.members_rate == pytest.approx(expected)
    assert result.interval_unavailable is True
    assert any("outside" in warning.lower() or "extended" in warning.lower() for warning in result.warnings)


def test_later_seasons_are_rejected():
    with pytest.raises(ValueError, match="Later seasons are not estimated"):
        best_dollars(12, 4)
    with pytest.raises(ValueError, match="Later seasons are not estimated"):
        simulate(Scenario(12, 11, "everyone", 1, "promo"))


def test_needed_gain_at_12_is_0_61_percentage_points():
    listing = get_estimates().list_price
    gain = needed_signup_gain(12, listing.comparison_price, listing.counterfactual_signup)
    assert round(gain * 100, 2) == 0.61
    result = simulate(Scenario(12, None, "acquisition", 0, "list"))
    assert round(result.needed_gain * 100, 2) == 0.61


def test_lpm_curve_passes_through_the_two_observed_prices():
    listing = get_estimates().list_price
    observed = listing.counterfactual_signup + listing.observed_signup_lift
    at_12 = signup_lift_view(listing.observed_price)
    at_15 = signup_lift_view(listing.comparison_price)
    assert at_15.rate_at_list == pytest.approx(listing.counterfactual_signup, abs=1e-9)
    assert at_12.rate_at_list == pytest.approx(observed, abs=1e-9)
    ratio = observed / listing.counterfactual_signup
    elasticity = constant_elasticity(ratio, listing.observed_price, listing.comparison_price)
    assert elasticity == pytest.approx(-4.03, abs=0.005)
    assert ratio == pytest.approx(2.456, abs=0.0005)
    assert at_12.hurdle_pp == pytest.approx(0.0061, abs=0.0001)
    assert at_12.breakeven_rate == pytest.approx(0.0304, abs=0.0001)
    assert round(at_12.lift_ci_low * 100, 2) == 3.45
    assert round(at_12.lift_ci_high * 100, 2) == 3.63
    assert at_15.lift_ci_low is None
    assert at_12.is_observed and not at_12.extrapolated
    assert at_15.is_observed and not at_15.extrapolated
    result = simulate(Scenario(12, None, "acquisition", 0, "list"))
    assert round(result.signup_lift * 100, 2) == 3.54
    assert round(result.signup_per_100, 2) == 5.98
    assert result.join_delta_label == "+3.54 pp vs counterfactual"
    assert result.list_confidence == "Low"
    chart = list_price_chart(12)
    assert chart.show_bars is True
    assert "+3.54 pp lift (95% CI 3.45 to 3.63)" == chart.lift_label
    assert "+$0.348 per person at risk (95% CI $0.335 to $0.360)" == chart.revenue_gap_label


def test_prices_between_the_anchors_are_an_assumption():
    low = signup_lift_view(13)
    high = signup_lift_view(14)
    assert low.is_observed is False and low.extrapolated is True
    assert high.is_observed is False and high.extrapolated is True
    assert low.lift_ci_low is None
    assert low.rate_at_list > high.rate_at_list > 0
    chart = list_price_chart(13)
    assert chart.show_bars is False
    assert chart.assumption_price == 13
    assert chart.arrow_price == 13
    assert "95% CI" not in chart.lift_label
    reference = list_price_chart(15)
    assert reference.assumption_price is None
    assert reference.arrow_price == 12
    assert reference.show_bars is False
    with pytest.raises(ValueError, match="from \\$12 to \\$15"):
        simulate(Scenario(10, None, "everyone", 0, "list"))


def test_chart_window_rates_stay_inside_zero_and_one():
    chart = list_price_chart(12)
    assert chart.join_prices[0] == chart.x_min == 10
    assert chart.join_prices[-1] == chart.x_max == 18
    for price in (10, 18):
        view = signup_lift_view(price)
        assert chart.x_min <= price <= chart.x_max
        assert 0 < view.rate_at_list < 1
    earlier = chart.join_percents[0]
    for value in chart.join_percents[1:]:
        assert 0 < value < earlier
        earlier = value


def test_caption_uses_the_linear_probability_curve():
    chart = list_price_chart(12)
    assert "poisson" not in chart.caption.lower()
    assert "linear-probability" in chart.caption.lower()
    assert round(signup_lift_view(12).lift_pp * 100, 2) == 3.54


def test_the_page_does_not_calculate_the_list_curve():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    for token in ("poisson", "elasticity", "math.log", "counterfactual_signup", "observed_signup_se"):
        assert token not in source


def test_best_dollar_is_the_higher_revenue_dollar():
    assert best_dollars(15, 0) == (11.0,)
    assert best_dollars(12, 0) == (11.0,)
    chosen = simulate(Scenario(15, 10, "everyone", 0, "promo"))
    assert chosen.tie is False
    assert chosen.best_dollars == (11.0,)


def test_se_gap_hand_example():
    # 10^2 * 0.01 + 11^2 * 0.02 - 2 * 10 * 11 * 0.001 = 3.2
    assert se_gap(10, 0.01, 11, 0.02, 0.001) == pytest.approx(math.sqrt(3.2))
    assert se_gap(10, 0.01, 11, 0.02, None) is None


def test_missing_covariance_does_not_invent_an_interval():
    between = simulate(Scenario(12, 10.5, "everyone", 0, "promo"))
    assert between.ci_low is None
    assert between.ci_high is None
    assert between.interval_unavailable is True


def test_recurring_revenue_is_the_stay_rate_times_the_offer():
    result = simulate(Scenario(12, 11, "recurring", 0, "promo"))
    point = next(item for item in load().promo["post"].churn if item.price == 11)
    offered = sum(item.n for item in load().promo["post"].churn)
    stay = 1.0 - point.rate
    revenue = stay * 11
    assert result.revenue_per_person == pytest.approx(revenue)
    assert result.members == pytest.approx(stay * offered)
    assert result.ci_low == pytest.approx(revenue - 1.96 * point.revenue_se)
    assert result.ci_high == pytest.approx(revenue + 1.96 * point.revenue_se)
    assert result.join_rate is None
    assert result.confidence == CONFIDENCE_HIGH
    assert result.vs_baseline == pytest.approx(0.0)
    assert result.best_dollars == (11.0,)
    assert not any("not saved" in warning.lower() for warning in result.warnings)
    assert best_dollars(15, 0, user_type="recurring") == (13.0,)
    between = simulate(Scenario(12, 10.5, "recurring", 0, "promo"))
    assert between.revenue_per_person is not None
    assert between.ci_low is None


def test_lapsed_and_new_use_saved_curves():
    curves = load().type_curves
    lapsed_point = next(point for point in curves["post"]["lapsed"].points if point.price == 8)
    lapsed_n = sum(point.n for point in curves["post"]["lapsed"].points)
    lapsed = simulate(Scenario(12, 8, "lapsed", 0, "promo"))
    assert lapsed.revenue_per_person == pytest.approx(lapsed_point.revenue)
    assert lapsed.members == pytest.approx(lapsed_point.rate * lapsed_n)
    assert lapsed.ci_low == pytest.approx(lapsed_point.revenue - 1.96 * lapsed_point.revenue_se)
    assert lapsed.best_dollars == (8.0,)
    assert lapsed.tie is False
    assert lapsed.members_label == "People who rejoin"
    assert not any("not saved" in warning.lower() for warning in lapsed.warnings)

    new_point = next(point for point in curves["post"]["new"].points if point.price == 7)
    new = simulate(Scenario(12, 7, "new", 0, "promo"))
    assert new.revenue_per_person == pytest.approx(new_point.revenue)
    assert new.best_dollars == (7.0,)
    assert new.members_label == "People who join"
    assert best_dollars(15, 0, user_type="lapsed") == (10.0,)
    assert best_dollars(15, 0, user_type="new") == (10.0,)


def test_load_rejects_a_missing_type_table(tmp_path):
    import json

    source = load()
    raw = json.loads(DEFAULT_PATH.read_text())
    del raw["types"]["post"]["lapsed"]
    path = tmp_path / "estimates.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="types.post.lapsed"):
        load(path)
    assert source.type_best["post"]["lapsed"] == (7.0, 8.0)
    raw = json.loads(DEFAULT_PATH.read_text())
    del raw["types"]["post"]["new"]["points"]
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="types.post.new.points"):
        load(path)


def test_acquisition_offers_match_the_published_table():
    listing = get_estimates().list_price
    no_promo = simulate(Scenario(12, None, "acquisition", 0, "list"))
    assert no_promo.offer_label == "*Lapsed + new, excluding promos"
    assert round(no_promo.offer_signup_per_100, 2) == 8.62
    assert round(no_promo.offer_signup_lift_pp, 2) == 3.54
    assert round(no_promo.offer_signup_ci_low_pp, 2) == 3.45
    assert round(no_promo.offer_signup_ci_high_pp, 2) == 3.63
    assert round(no_promo.offer_revenue_baseline, 2) == 1.29
    assert round(no_promo.offer_revenue_lift, 3) == 0.348
    assert round(no_promo.offer_revenue_ci_low, 3) == 0.335
    assert round(no_promo.offer_revenue_ci_high, 3) == 0.360
    assert no_promo.offer_n == listing.n_acquisition
    assert no_promo.offer_revenue_lift == pytest.approx(listing.observed_acquisition_revenue_lift)
    assert round(no_promo.signup_lift * 100, 2) == 3.54

    with_promo = simulate(Scenario(12, None, "acquisition_promo", 0, "list"))
    assert with_promo.offer_label == "Lapsed + new, including promos"
    assert round(with_promo.offer_signup_per_100, 2) == 8.52
    assert round(with_promo.offer_signup_lift_pp, 2) == 4.32
    assert round(with_promo.offer_signup_ci_low_pp, 2) == 4.23
    assert round(with_promo.offer_signup_ci_high_pp, 2) == 4.42
    assert round(with_promo.offer_revenue_baseline, 2) == 1.26
    assert round(with_promo.offer_revenue_lift, 3) == 0.337
    assert round(with_promo.offer_revenue_ci_low, 3) == 0.325
    assert round(with_promo.offer_revenue_ci_high, 3) == 0.349
    assert with_promo.signup_per_100 is None
    assert with_promo.warnings == ()

    with pytest.raises(ValueError, match="from \\$12 to \\$15"):
        simulate(Scenario(16, None, "acquisition_promo", 0, "list"))
    with pytest.raises(ValueError, match="Choose a group"):
        simulate(Scenario(12, 11, "acquisition_promo", 0, "promo"))


def test_list_groups_use_separate_writeup_rows():
    everyone = simulate(Scenario(12, None, "everyone", 0, "list"))
    recurring = simulate(Scenario(12, None, "recurring", 0, "list"))
    lapsed = simulate(Scenario(12, None, "lapsed", 0, "list"))
    new = simulate(Scenario(12, None, "new", 0, "list"))
    assert everyone.signup_lift_pp is None
    assert round(everyone.membership_lift_pp, 2) == 11.23
    assert round(everyone.revenue_lift, 3) == 0.353
    assert recurring.signup_lift_pp is None
    assert round(recurring.membership_lift_pp, 2) == 2.56
    assert round(recurring.revenue_lift, 2) == -2.64
    assert round(lapsed.signup_lift_pp, 2) == 14.61
    assert round(lapsed.revenue_lift, 2) == 1.51
    assert round(new.signup_lift_pp, 2) == 3.77
    assert round(new.revenue_lift, 3) == 0.415
    assert {round(row.signup_lift_pp or row.membership_lift_pp, 2) for row in (everyone, recurring, lapsed, new)} == {
        11.23,
        2.56,
        14.61,
        3.77,
    }

    rate, revenue = list_group_curves("lapsed")
    assert rate.points[0].price == 12.0 and rate.points[-1].price == 15.0
    assert [point.price for point in rate.points if point.price in (12.0, 13.5, 15.0)] == [12.0, 13.5, 15.0]
    assert rate.points[-1].y == 0
    assert rate.y_label == "Sign-up lift (pp)"
    assert rate.points[0].ci_low is not None
    assert all(point.ci_low is None for point in rate.points if point.price != 12.0)
    middle = next(point for point in rate.points if point.price == 13.5)
    assert middle.y == pytest.approx(rate.points[0].y / 2)
    assert revenue.y_label == "Revenue change ($)"
    assert revenue.points[-1].y == 0

    stay, pay = list_group_curves("recurring")
    assert stay.points[-1].y == pytest.approx(89.276, abs=0.01)
    assert pay.points[0].y < pay.points[-1].y
    assert "(pp)" not in stay.y_label
    halfway = simulate(Scenario(13.5, None, "everyone", 0, "list"))
    assert halfway.confidence == "Low"
    assert halfway.membership_lift_pp == pytest.approx(everyone.membership_lift_pp / 2)
    assert halfway.revenue_lift == pytest.approx(everyone.revenue_lift / 2)
    assert halfway.membership_ci_low_pp is None
    at_comparison = simulate(Scenario(15, None, "everyone", 0, "list"))
    assert at_comparison.membership_lift_pp == pytest.approx(0)
    assert at_comparison.revenue_lift == pytest.approx(0)


def test_load_rejects_a_missing_offer_group(tmp_path):
    import json

    raw = json.loads(DEFAULT_PATH.read_text())
    del raw["list_price"]["offer_groups"]
    path = tmp_path / "estimates.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="list_price.offer_groups"):
        load(path)


def test_presets_use_the_post_cut_curve():
    current = preset_scenario("current_policy")
    assert (current.list_price, current.promo_dollar, current.horizon_extra_seasons, current.mode) == (12, 11, 0, "promo")
    assert preset_scenario("revenue_max").promo_dollar == 11
    with pytest.raises(ValueError, match="Unknown preset"):
        preset_scenario("long_horizon")
