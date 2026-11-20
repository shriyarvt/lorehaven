"""Promo and list-price calculations.

Every number the app or the assistant shows comes from a Result built here.
Rates inside a tested promo grid are straight lines between the saved dollars.
Outside that grid the line continues from the two nearest dollars and is flagged.
A list price other than the two observed prices uses a constant elasticity.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, is_dataclass

from sim.constants import (
    LIST_OFFER_LABELS,
    MEMBERS_LABELS,
    RATE_LABELS,
    PRESET_CURRENT,
    PRESET_LABELS,
    PRESET_REVENUE_MAX,
    PRICE_STEP,
    Z_95,
)
from sim.estimates import Estimates, OfferGroup, PricePoint, PromoEra, RevenueGap, load
from sim.validate import (
    check_scenario,
    list_curve_confidence,
    observed_revenue_confidence,
    observed_signup_confidence,
    promo_confidence,
    range_warnings,
)

_CACHE: Estimates | None = None


def get_estimates() -> Estimates:
    """Load the estimates file once per process."""
    global _CACHE
    if _CACHE is None:
        _CACHE = load()
    return _CACHE


@dataclass(frozen=True)
class Scenario:
    """One question the simulator can answer."""

    list_price: float
    promo_dollar: float | None
    user_type: str
    horizon_extra_seasons: int
    mode: str


@dataclass(frozen=True)
class Result:
    """Numbers for one scenario. Display code should not recompute these."""

    scenario: Scenario
    confidence: str
    warnings: tuple[str, ...]
    extrapolated: bool
    members_rate: float | None = None
    members_per_100: float | None = None
    members: float | None = None
    members_label: str = "People who stay members"
    join_rate: float | None = None
    revenue_per_person: float | None = None
    total_revenue: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    vs_baseline: float | None = None
    break_even_value: float | None = None
    net_gain_per_100: float | None = None
    reference_dollar: float | None = None
    best_dollars: tuple[float, ...] = ()
    tie: bool = False
    quick_prices: tuple[float, ...] = ()
    signup_per_100: float | None = None
    signup_lift: float | None = None
    signup_lift_pp: float | None = None
    signup_ci_low_pp: float | None = None
    signup_ci_high_pp: float | None = None
    needed_gain: float | None = None
    needed_gain_pp: float | None = None
    join_delta_label: str | None = None
    observed_price: float | None = None
    comparison_price: float | None = None
    list_revenue_per_person: float | None = None
    list_total_revenue: float | None = None
    observed_signup_lift: float | None = None
    observed_signup_lift_pp: float | None = None
    observed_acquisition_revenue_lift: float | None = None
    observed_all_revenue_lift: float | None = None
    observed_signup_confidence: str | None = None
    observed_revenue_confidence: str | None = None
    revenue_per_member_before: float | None = None
    revenue_per_member_after: float | None = None
    pretrend_chi2: float | None = None
    pretrend_df: int | None = None
    list_confidence: str | None = None
    interval_unavailable: bool = False
    offer_label: str | None = None
    offer_signup_per_100: float | None = None
    offer_signup_lift_pp: float | None = None
    offer_signup_ci_low_pp: float | None = None
    offer_signup_ci_high_pp: float | None = None
    offer_revenue_baseline: float | None = None
    offer_revenue_lift: float | None = None
    offer_revenue_ci_low: float | None = None
    offer_revenue_ci_high: float | None = None
    offer_n: int | None = None
    list_n: int | None = None
    list_n_fit: int | None = None
    list_share: float | None = None
    membership_lift_pp: float | None = None
    membership_ci_low_pp: float | None = None
    membership_ci_high_pp: float | None = None
    revenue_lift: float | None = None
    revenue_ci_low: float | None = None
    revenue_ci_high: float | None = None

    def numeric_values(self) -> list[float]:
        """Every number stored on this result, including the scenario."""
        return _walk_numbers(self)


@dataclass(frozen=True)
class CurvePoint:
    price: float
    y: float
    ci_low: float | None
    ci_high: float | None
    is_best: bool


@dataclass(frozen=True)
class Curve:
    """A line the chart can draw without further calculation."""

    points: tuple[CurvePoint, ...]
    y_label: str
    observed_price: float | None = None
    observed_y: float | None = None
    observed_label: str = ""
    selected_price: float | None = None
    selected_y: float | None = None


@dataclass(frozen=True)
class SignupLiftView:
    """Sign-up curve at one list price. Rates are proportions, not percents.

    The curve is the constant elasticity through the counterfactual at the
    comparison price and the observed total at the tested price. ``lift_pp``
    and ``hurdle_pp`` are rate differences. Multiply by 100 to read percentage
    points. The interval is the saved lift interval, and only at the tested price.
    """

    list_price: float
    counterfactual: float
    rate_at_list: float
    lift_pp: float
    hurdle_pp: float
    breakeven_rate: float
    is_observed: bool
    lift_ci_low: float | None
    lift_ci_high: float | None
    extrapolated: bool


@dataclass(frozen=True)
class ListPriceChart:
    """Series and labels for the list-price charts. The page does not recompute them.

    Join rates are already in percent. Revenue values are dollars per person at risk.
    """

    x_min: float
    x_max: float
    observed_price: float
    comparison_price: float
    join_prices: tuple[float, ...]
    join_percents: tuple[float, ...]
    counterfactual_percent: float
    counterfactual_label: str
    observed_percent: float
    observed_label: str
    observed_ci_low: float | None
    observed_ci_high: float | None
    observed_error_plus: float | None
    observed_error_minus: float | None
    breakeven_percent: float
    breakeven_label: str
    arrow_price: float
    arrow_x: float
    arrow_low: float
    arrow_high: float
    arrow_label_y: float
    lift_label: str
    assumption_price: float | None
    assumption_percent: float | None
    assumption_label: str
    caption: str
    show_bars: bool
    bar_labels: tuple[str, str, str]
    bar_values: tuple[float, float, float]
    bar_hover: tuple[str, str, str]
    revenue_prices: tuple[float, ...]
    revenue_values: tuple[float, ...]
    revenue_counterfactual: float
    revenue_observed: float
    revenue_gap_label: str
    curve_label: str


def baseline_scenario() -> Scenario:
    """Current policy: list $12, promo $11, this season, everyone."""
    return Scenario(12.0, 11.0, "everyone", 0, "promo")


def preset_scenario(name: str, estimates: Estimates | None = None) -> Scenario:
    """Build one of the named starting points."""
    data = estimates or get_estimates()
    if name == PRESET_CURRENT:
        return Scenario(12.0, 11.0, "everyone", 0, "promo")
    if name == PRESET_REVENUE_MAX:
        dollar = best_dollars(12.0, 0, data)[0]
        return Scenario(12.0, dollar, "everyone", 0, "promo")
    known = ", ".join(PRESET_LABELS)
    raise ValueError(f"Unknown preset. Choose one of: {known}.")


def promo_bounds(list_price: float, estimates: Estimates | None = None) -> tuple[float, float] | None:
    """Tested promo range at this list price, or None when no promo test exists."""
    era = (estimates or get_estimates()).era_for_list_price(list_price)
    if era is None:
        return None
    return era.membership[0].price, era.membership[-1].price


def type_best_table(
    list_price: float, estimates: Estimates | None = None
) -> dict[str, tuple[float, ...]] | None:
    """Saved best dollars by group. None when this list price has no promo test."""
    data = estimates or get_estimates()
    for era_name, era in data.promo.items():
        if era.list_price == float(list_price):
            table = data.type_best.get(era_name)
            if table is None:
                raise ValueError(f"Estimates file is missing table types.{era_name}")
            return table
    return None


def simulate(scenario: Scenario, estimates: Estimates | None = None) -> Result:
    """Score one scenario. Raise ValueError on a price that cannot be used."""
    data = estimates or get_estimates()
    check_scenario(
        scenario.list_price,
        scenario.promo_dollar,
        scenario.user_type,
        scenario.horizon_extra_seasons,
        scenario.mode,
    )
    warnings = list(
        range_warnings(
            scenario.list_price,
            scenario.promo_dollar,
            scenario.mode,
            data,
            scenario.user_type,
        )
    )
    if scenario.mode == "promo":
        scored = _score_promo(scenario, data, warnings)
        vs_baseline = _versus_baseline(scenario, data, scored)
    else:
        scored = _score_list(scenario, data)
        vs_baseline = None
    confidence = scored["confidence"] or list_curve_confidence()
    skip = {"confidence", "extrapolated"}
    fields = {key: value for key, value in scored.items() if key not in skip}
    return Result(
        scenario=scenario,
        confidence=confidence,
        warnings=tuple(warnings),
        extrapolated=bool(scored["extrapolated"]),
        vs_baseline=vs_baseline,
        **fields,
    )


def revenue_curve(scenario: Scenario, estimates: Estimates | None = None) -> Curve:
    """This-season revenue at each tenth of a dollar on the tested grid."""
    data = estimates or get_estimates()
    era = data.era_for_list_price(scenario.list_price)
    if era is None or scenario.user_type not in MEMBERS_LABELS:
        return Curve((), "Revenue per person offered")
    best = best_dollars(scenario.list_price, 0, data, scenario.user_type)
    points = []
    for price in _grid(era):
        scored = _score_at(era, price, 0, scenario.user_type, data)
        points.append(
            CurvePoint(
                price=price,
                y=scored["revenue"],
                ci_low=scored["ci_low"],
                ci_high=scored["ci_high"],
                is_best=price in best,
            )
        )
    return Curve(tuple(points), "Revenue per person offered")


def members_curve(scenario: Scenario, estimates: Estimates | None = None) -> Curve:
    """Share who stay members, as a percent, across the tested grid."""
    data = estimates or get_estimates()
    era = data.era_for_list_price(scenario.list_price)
    if era is None or scenario.user_type not in MEMBERS_LABELS:
        return Curve((), RATE_LABELS["everyone"])
    best = best_dollars(scenario.list_price, 0, data, scenario.user_type)
    points = []
    for price in _grid(era):
        scored = _score_at(era, price, 0, scenario.user_type, data)
        per_100 = scored["members_rate"] * 100
        points.append(
            CurvePoint(
                price=price,
                y=per_100,
                ci_low=None,
                ci_high=None,
                is_best=price in best,
            )
        )
    return Curve(tuple(points), _members_axis(scenario.user_type))


# Drawn window. Outside it the elasticity runs to extreme rates.
LIST_CHART_MIN = 10.0
LIST_CHART_MAX = 18.0
_LIST_CHART_STEP = 0.5
_CURVE_LABEL = "Curve through the two observed points"
_ASSUMPTION_LABEL = "Assumption, not observed"


def _same_price(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) < 1e-9


def _lpm_elasticity(listing) -> float:
    """Elasticity through the counterfactual and the observed test-market rate."""
    observed_total = listing.counterfactual_signup + listing.observed_signup_lift
    ratio = observed_total / listing.counterfactual_signup
    return constant_elasticity(ratio, listing.observed_price, listing.comparison_price)


def _percent_points(rate: float) -> str:
    return f"{rate * 100:.2f}"


def _signed_points(rate: float) -> str:
    return f"{rate * 100:+.2f}"


def signup_lift_view(list_price: float, estimates: Estimates | None = None) -> SignupLiftView:
    """Sign-up rate, lift, and break-even hurdle at one list price.

    Only the tested price and the comparison price were observed. Every other
    price, including a price between them, is an assumption. The confidence
    interval is the saved interval for the lift, and it is attached only at the
    tested price.
    """
    listing = (estimates or get_estimates()).list_price
    counterfactual = listing.counterfactual_signup
    elasticity = _lpm_elasticity(listing)
    rate = signup_rate_at(list_price, counterfactual, elasticity, listing.comparison_price)
    hurdle = needed_signup_gain(list_price, listing.comparison_price, counterfactual)
    at_test = _same_price(list_price, listing.observed_price)
    at_reference = _same_price(list_price, listing.comparison_price)
    low, high = interval(listing.observed_signup_lift, listing.observed_signup_se) if at_test else (None, None)
    return SignupLiftView(
        list_price=float(list_price),
        counterfactual=counterfactual,
        rate_at_list=rate,
        lift_pp=rate - counterfactual,
        hurdle_pp=hurdle,
        breakeven_rate=counterfactual + hurdle,
        is_observed=at_test or at_reference,
        lift_ci_low=low,
        lift_ci_high=high,
        extrapolated=not (at_test or at_reference),
    )


def list_price_chart(list_price: float, estimates: Estimates | None = None) -> ListPriceChart:
    """Join and revenue charts for one list price.

    At the tested price and the comparison price, the arrow and the break-even
    line describe the test. At any other price they move to that price, and an
    assumption marker is added. The revenue label is the saved regression gap,
    not the gap between the two curve points.
    """
    data = estimates or get_estimates()
    listing = data.list_price
    selected = signup_lift_view(list_price, data)
    story_price = listing.observed_price if selected.is_observed else float(list_price)
    story = signup_lift_view(story_price, data)
    elasticity = _lpm_elasticity(listing)
    prices = _chart_prices()
    join_percents = tuple(
        signup_rate_at(price, listing.counterfactual_signup, elasticity, listing.comparison_price) * 100
        for price in prices
    )
    revenue_values = tuple(
        signup_rate_at(price, listing.counterfactual_signup, elasticity, listing.comparison_price) * price
        for price in prices
    )
    observed_total = listing.counterfactual_signup + listing.observed_signup_lift
    counterfactual_percent = listing.counterfactual_signup * 100
    observed_percent = observed_total * 100
    tested = signup_lift_view(listing.observed_price, data)
    ci_low = None if tested.lift_ci_low is None else (listing.counterfactual_signup + tested.lift_ci_low) * 100
    ci_high = None if tested.lift_ci_high is None else (listing.counterfactual_signup + tested.lift_ci_high) * 100
    error_plus = None if ci_high is None else ci_high - observed_percent
    error_minus = None if ci_low is None else observed_percent - ci_low
    arrow_low = min(counterfactual_percent, story.rate_at_list * 100)
    arrow_high = max(counterfactual_percent, story.rate_at_list * 100)
    lift_label = _lift_label(story)
    show_bars = _same_price(list_price, listing.observed_price)
    assumption_price = None if selected.is_observed else float(list_price)
    assumption_percent = None if selected.is_observed else selected.rate_at_list * 100
    return ListPriceChart(
        x_min=LIST_CHART_MIN,
        x_max=LIST_CHART_MAX,
        observed_price=listing.observed_price,
        comparison_price=listing.comparison_price,
        join_prices=prices,
        join_percents=join_percents,
        counterfactual_percent=counterfactual_percent,
        counterfactual_label=f"Counterfactual: {_percent_points(listing.counterfactual_signup)}% (without the cut)",
        observed_percent=observed_percent,
        observed_label=f"Observed in test: {_percent_points(observed_total)}%",
        observed_ci_low=ci_low,
        observed_ci_high=ci_high,
        observed_error_plus=error_plus,
        observed_error_minus=error_minus,
        breakeven_percent=story.breakeven_rate * 100,
        breakeven_label=(
            f"Break-even: {_signed_points(story.hurdle_pp)} pp needed to match "
            f"${listing.comparison_price:g} revenue per joiner"
        ),
        arrow_price=story_price,
        arrow_x=min(LIST_CHART_MAX - 0.35, story_price + 0.4),
        arrow_low=arrow_low,
        arrow_high=arrow_high,
        arrow_label_y=(arrow_low + arrow_high) / 2,
        lift_label=lift_label,
        assumption_price=assumption_price,
        assumption_percent=assumption_percent,
        assumption_label=_ASSUMPTION_LABEL,
        caption=_chart_caption(listing, elasticity),
        show_bars=show_bars,
        bar_labels=("Counterfactual", "Lift", "Observed total"),
        bar_values=(counterfactual_percent, listing.observed_signup_lift * 100, observed_percent),
        bar_hover=(
            f"Counterfactual, {_percent_points(listing.counterfactual_signup)}%",
            f"Lift, {_signed_points(listing.observed_signup_lift)} pp",
            f"Observed total, {_percent_points(observed_total)}%",
        ),
        revenue_prices=prices,
        revenue_values=revenue_values,
        revenue_counterfactual=listing.counterfactual_signup * listing.comparison_price,
        revenue_observed=observed_total * listing.observed_price,
        revenue_gap_label=_revenue_gap_label(listing),
        curve_label=_CURVE_LABEL,
    )


def _chart_prices() -> tuple[float, ...]:
    prices = []
    price = LIST_CHART_MIN
    while price <= LIST_CHART_MAX + 1e-9:
        prices.append(round(price, 2))
        price = round(price + _LIST_CHART_STEP, 2)
    return tuple(prices)


def _lift_label(story: SignupLiftView) -> str:
    lift = f"{_signed_points(story.lift_pp)} pp lift"
    if story.lift_ci_low is None or story.lift_ci_high is None:
        return lift
    return (
        f"{lift} (95% CI {_percent_points(story.lift_ci_low)} to {_percent_points(story.lift_ci_high)})"
    )


def _chart_caption(listing, elasticity: float) -> str:
    return (
        f"Curve is the linear-probability elasticity (about {elasticity:.1f}) through "
        f"the two observed rates, ${listing.comparison_price:g} and ${listing.observed_price:g}. "
        "Any other price was not observed. "
        "Pre-trends fail and Panem is the only control, and the interval shows sampling error only."
    )


def _revenue_gap_label(listing) -> str:
    low, high = interval(
        listing.observed_acquisition_revenue_lift,
        listing.observed_acquisition_revenue_se,
    )
    if low is None or high is None:
        raise ValueError("The acquisition revenue interval was not saved.")
    return (
        f"+${listing.observed_acquisition_revenue_lift:.3f} per person at risk "
        f"(95% CI ${low:.3f} to ${high:.3f})"
    )


def best_dollars(
    list_price: float,
    horizon_extra_seasons: int,
    estimates: Estimates | None = None,
    user_type: str = "everyone",
) -> tuple[float, ...]:
    """The tested dollar with the highest this-season revenue.

    Everyone uses the membership curve. Recurring uses the churn curve.
    Lapsed and New use their own saved curves. The search uses tenth-of-a-dollar
    steps inside the tested grid and does not recommend a price outside that
    grid. When the peak sits inside a pair whose 95% gap includes zero, the
    dollar in that pair with the higher revenue is returned.
    """
    if horizon_extra_seasons != 0:
        raise ValueError("Later seasons are not estimated.")
    if user_type not in MEMBERS_LABELS:
        raise ValueError("Choose Everyone, Recurring, Lapsed, or New.")
    data = estimates or get_estimates()
    era = data.era_for_list_price(list_price)
    if era is None:
        raise ValueError(
            f"No promo curve was estimated at list ${list_price:g}. "
            "Promo results are available at list $12 and list $15."
        )
    scored = [
        (_score_at(era, price, 0, user_type, data)["metric"], price)
        for price in _grid(era)
    ]
    peak = max(value for value, _price in scored)
    winners = tuple(price for value, price in scored if abs(value - peak) <= 1e-9)
    pair = (
        _tie_pair(era.revenue_gap)
        if user_type == "everyone"
        else _published_tie(data, list_price, user_type)
    )
    if pair is not None and winners and all(pair[0] <= price <= pair[1] for price in winners):
        candidates = pair
    else:
        candidates = winners
    return (_higher_revenue_dollar(era, candidates, user_type, data),)


def _higher_revenue_dollar(
    era: PromoEra,
    prices: tuple[float, ...],
    user_type: str,
    data: Estimates,
) -> float:
    """One dollar. Higher this-season revenue wins, then the higher dollar."""
    return max(
        prices,
        key=lambda price: (_score_at(era, price, 0, user_type, data)["revenue"], price),
    )


def needed_signup_gain(list_price: float, comparison_price: float, counterfactual: float) -> float:
    """Extra sign-up rate required so a joiner at `list_price` matches comparison revenue.

    A $12 joiner pays 20% less than a $15 joiner, so the rate has to be 25% higher.
    At a 2.43% counterfactual that is 0.61 percentage points.
    """
    if list_price <= 0:
        raise ValueError("Enter a list price above zero.")
    return (comparison_price / list_price - 1.0) * counterfactual


def constant_elasticity(rate_ratio: float, low_price: float, high_price: float) -> float:
    """Elasticity implied by a rate ratio between two prices. Negative when demand slopes down."""
    if rate_ratio <= 0 or low_price <= 0 or high_price <= 0 or low_price == high_price:
        raise ValueError("Elasticity needs a positive rate ratio and two different positive prices.")
    return math.log(rate_ratio) / math.log(low_price / high_price)


def signup_rate_at(
    list_price: float,
    counterfactual: float,
    elasticity: float,
    comparison_price: float,
) -> float:
    """Constant-elasticity sign-up rate. Equals the counterfactual at the comparison price."""
    if list_price <= 0 or comparison_price <= 0:
        raise ValueError("Enter a list price above zero.")
    return counterfactual * (list_price / comparison_price) ** elasticity


def se_gap(
    price_a: float,
    var_rate_a: float,
    price_b: float,
    var_rate_b: float,
    cov: float | None,
) -> float | None:
    """Standard error of a revenue gap. None when the covariance was not saved.

    SE = sqrt(p_a^2 Var(rate_a) + p_b^2 Var(rate_b) - 2 p_a p_b Cov).
    Rates are not treated as independent. A missing covariance is not a zero.
    """
    if cov is None:
        return None
    inside = (
        price_a**2 * var_rate_a
        + price_b**2 * var_rate_b
        - 2.0 * price_a * price_b * cov
    )
    if inside < 0:
        raise ValueError("The variance of the gap is negative. Check the covariance.")
    return math.sqrt(inside)


def interval(estimate: float, se: float | None) -> tuple[float | None, float | None]:
    """95% interval, estimate plus or minus 1.96 standard errors."""
    if se is None:
        return None, None
    return estimate - Z_95 * se, estimate + Z_95 * se


def _score_promo(scenario: Scenario, data: Estimates, warnings: list[str]) -> dict:
    era = data.era_for_list_price(scenario.list_price)
    assert era is not None
    if scenario.promo_dollar is None:
        raise ValueError("Enter a promo dollar.")
    scored = _score_at(
        era,
        scenario.promo_dollar,
        0,
        scenario.user_type,
        data,
    )
    if not 0.0 <= scored["members_rate"] <= 1.0 or not 0.0 <= scored["churn"] <= 1.0:
        warnings.append(
            "The extended line is outside 0 to 100 percent. Treat it as a sketch."
        )
    low, high = promo_bounds(scenario.list_price, data)
    assert low is not None and high is not None
    best = best_dollars(
        scenario.list_price,
        0,
        data,
        scenario.user_type,
    )
    level_ci = (scored["ci_low"], scored["ci_high"])
    offered = _offered_count(era, scenario.user_type, data)
    return {
        "confidence": promo_confidence(scored["extrapolated"]),
        "extrapolated": scored["extrapolated"],
        "members_rate": scored["members_rate"],
        "members_per_100": scored["members_rate"] * 100,
        "members": scored["members_rate"] * offered,
        "members_label": MEMBERS_LABELS[scenario.user_type],
        "join_rate": scored["join_rate"],
        "revenue_per_person": scored["revenue"],
        "total_revenue": scored["revenue"] * offered,
        "ci_low": level_ci[0],
        "ci_high": level_ci[1],
        "reference_dollar": era.reference_dollar,
        "best_dollars": best,
        "tie": False,
        "quick_prices": _quick_prices(scenario.promo_dollar, low, high, best),
        "interval_unavailable": level_ci[0] is None,
    }


def _score_list(scenario: Scenario, data: Estimates) -> dict:
    listing = data.list_price
    group = listing.groups.get(scenario.user_type)
    if group is None:
        raise ValueError("Choose a group from the list-price table.")
    view = signup_lift_view(listing.observed_price, data)
    has_signup = group.signup_lift is not None
    weight = _line_weight(scenario.list_price, listing.observed_price, listing.comparison_price)
    at_cut = abs(weight - 1.0) < 1e-9
    confidence = observed_signup_confidence()
    signup_low, signup_high = interval(group.signup_lift, group.signup_se)
    member_low, member_high = interval(group.membership_lift, group.membership_se)
    revenue_low, revenue_high = interval(group.revenue_lift, group.revenue_se)
    scored = {
        "confidence": confidence,
        "extrapolated": False,
        "observed_price": listing.observed_price,
        "comparison_price": listing.comparison_price,
        "observed_signup_confidence": observed_signup_confidence(),
        "observed_revenue_confidence": observed_revenue_confidence(),
        "revenue_per_member_before": listing.revenue_per_member_before,
        "revenue_per_member_after": listing.revenue_per_member_after,
        "pretrend_chi2": listing.pretrend_chi2,
        "pretrend_df": listing.pretrend_df,
        "list_confidence": confidence,
        "list_n": group.n,
        "list_n_fit": group.n_fit,
        "list_share": group.n / listing.n_all,
        "membership_lift_pp": None if group.membership_lift is None else group.membership_lift * weight * 100,
        "membership_ci_low_pp": None if member_low is None or not at_cut else member_low * 100,
        "membership_ci_high_pp": None if member_high is None or not at_cut else member_high * 100,
        "revenue_lift": group.revenue_lift * weight,
        "revenue_ci_low": revenue_low if at_cut else None,
        "revenue_ci_high": revenue_high if at_cut else None,
    }
    if has_signup:
        scored.update(
            {
                "signup_lift": group.signup_lift * weight,
                "signup_lift_pp": group.signup_lift * weight * 100,
                "signup_ci_low_pp": None if signup_low is None or not at_cut else signup_low * 100,
                "signup_ci_high_pp": None if signup_high is None or not at_cut else signup_high * 100,
            }
        )
    if scenario.user_type == "acquisition":
        scored.update(
            {
                "signup_per_100": (listing.counterfactual_signup + listing.observed_signup_lift) * 100,
                "needed_gain": view.hurdle_pp,
                "needed_gain_pp": view.hurdle_pp * 100,
                "join_delta_label": f"{_signed_points(listing.observed_signup_lift)} pp vs counterfactual",
                "observed_signup_lift": listing.observed_signup_lift,
                "observed_signup_lift_pp": listing.observed_signup_lift * 100,
                "observed_acquisition_revenue_lift": listing.observed_acquisition_revenue_lift,
            }
        )
    offer = listing.offer_groups.get(scenario.user_type)
    if offer is not None:
        scored.update(_offer_fields(offer, LIST_OFFER_LABELS[scenario.user_type]))
    return scored


def list_group_curves(
    user_type: str,
    price: float = 12.0,
    estimates: Estimates | None = None,
) -> tuple[Curve, Curve]:
    """Two-point charts for one list-price group, $12 and $15.

    The line connects the comparison price to the cut. A 95% interval is drawn
    on $12, around the level when a $15 level was saved and around the lift
    when it was not.
    """
    data = estimates or get_estimates()
    group = data.list_price.groups.get(user_type)
    if group is None:
        raise ValueError("Choose a group from the list-price table.")
    if group.signup_lift is not None:
        rate_name = "Sign-up"
        rate_lift = group.signup_lift
        rate_se = group.signup_se
    else:
        rate_name = "Membership"
        rate_lift = group.membership_lift or 0.0
        rate_se = group.membership_se
    if group.rate_base is None:
        rate = _lift_curve(rate_lift, rate_se, f"{rate_name} lift (pp)", percent_points=True)
    else:
        rate = _level_curve(
            group.rate_base,
            rate_lift,
            rate_se,
            f"% who join" if group.signup_lift is not None else "% who stay members",
            scale=100.0,
        )
    if group.revenue_base is None:
        revenue = _lift_curve(group.revenue_lift, group.revenue_se, "Revenue change ($)", percent_points=False)
    else:
        revenue = _level_curve(
            group.revenue_base,
            group.revenue_lift,
            group.revenue_se,
            "Revenue per person",
            scale=1.0,
        )
    return _mark_selected(rate, price), _mark_selected(revenue, price)


def _level_curve(base: float, lift: float, se: float | None, label: str, scale: float) -> Curve:
    low, high = interval(base + lift, se)
    return Curve(
        _span_points(
            (base + lift) * scale,
            base * scale,
            None if low is None else low * scale,
            None if high is None else high * scale,
        ),
        label,
    )


def _lift_curve(lift: float, se: float | None, label: str, percent_points: bool) -> Curve:
    scale = 100.0 if percent_points else 1.0
    low, high = interval(lift, se)
    return Curve(
        _span_points(
            lift * scale,
            0.0,
            None if low is None else low * scale,
            None if high is None else high * scale,
        ),
        label,
    )


def _line_weight(price: float, observed: float, comparison: float) -> float:
    """1 at the cut, 0 at the comparison price."""
    span = comparison - observed
    if span == 0:
        return 1.0
    return (comparison - float(price)) / span


def _mark_selected(curve: Curve, price: float) -> Curve:
    if not curve.points:
        return curve
    y_at_12 = curve.points[0].y
    y_at_15 = curve.points[-1].y
    share = (float(price) - 12.0) / 3.0
    return Curve(
        curve.points,
        curve.y_label,
        selected_price=float(price),
        selected_y=y_at_12 + (y_at_15 - y_at_12) * share,
    )


def _span_points(
    y_at_12: float,
    y_at_15: float,
    ci_low: float | None,
    ci_high: float | None,
) -> tuple[CurvePoint, ...]:
    """Straight line from $12 to $15, with a point at every tenth so hover can read it."""
    start = int(round(12.0 / PRICE_STEP))
    end = int(round(15.0 / PRICE_STEP))
    points: list[CurvePoint] = []
    for index in range(start, end + 1):
        price = round(index * PRICE_STEP, 2)
        share = (price - 12.0) / 3.0
        y = y_at_12 + (y_at_15 - y_at_12) * share
        if price == 12.0:
            points.append(CurvePoint(price, y_at_12, ci_low, ci_high, False))
        else:
            points.append(CurvePoint(price, y, None, None, False))
    return tuple(points)


def _offer_fields(group: OfferGroup, label: str) -> dict:
    """Baseline and lift for one lapsed-plus-new comparison."""
    signup_low, signup_high = interval(group.signup_lift, group.signup_se)
    revenue_low, revenue_high = interval(group.revenue_lift, group.revenue_se)
    return {
        "offer_label": label,
        "offer_signup_per_100": group.signup_baseline * 100,
        "offer_signup_lift_pp": group.signup_lift * 100,
        "offer_signup_ci_low_pp": None if signup_low is None else signup_low * 100,
        "offer_signup_ci_high_pp": None if signup_high is None else signup_high * 100,
        "offer_revenue_baseline": group.revenue_baseline,
        "offer_revenue_lift": group.revenue_lift,
        "offer_revenue_ci_low": revenue_low,
        "offer_revenue_ci_high": revenue_high,
        "offer_n": group.n,
    }


def _versus_baseline(scenario: Scenario, data: Estimates, promo: dict) -> float | None:
    """Difference in this-season revenue per person from list $12, promo $11."""
    current = promo.get("revenue_per_person")
    if current is None:
        return None
    base = _score_at(_require_era(data, 12.0), 11.0, 0, scenario.user_type, data)
    return current - base["revenue"]


def _require_era(data: Estimates, list_price: float) -> PromoEra:
    era = data.era_for_list_price(list_price)
    if era is None:
        raise ValueError(f"Estimates file has no promo curve at list ${list_price:g}")
    return era


def _score_at(
    era: PromoEra,
    price: float,
    horizon_extra_seasons: int,
    user_type: str,
    data: Estimates,
) -> dict:
    """Everyone uses membership. Recurring uses churn. Lapsed and New use their curves."""
    if user_type == "recurring":
        return _at_stay(era, price, horizon_extra_seasons)
    if user_type in {"lapsed", "new"}:
        curve = _require_type_curve(data, era.list_price, user_type)
        return _at_rate_curve(curve.points, price, horizon_extra_seasons, era)
    return _at_price(era, price, horizon_extra_seasons)


def _at_rate_curve(
    points: tuple[PricePoint, ...],
    price: float,
    horizon_extra_seasons: int,
    era: PromoEra,
) -> dict:
    """Group revenue is the saved membership rate times the offer."""
    del horizon_extra_seasons
    rate = _interpolate(points, price)
    churn = _interpolate(era.churn, price)
    revenue = rate["value"] * price
    metric = revenue
    ci_low, ci_high = (None, None)
    if rate["revenue_se"] is not None and not rate["extrapolated"]:
        ci_low, ci_high = interval(revenue, rate["revenue_se"])
    return {
        "members_rate": rate["value"],
        "join_rate": None,
        "churn": churn["value"],
        "revenue": revenue,
        "metric": metric,
        "extrapolated": rate["extrapolated"],
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def _require_type_curve(data: Estimates, list_price: float, user_type: str):
    """The saved lapsed or new curve at this list price."""
    for era_name, era in data.promo.items():
        if era.list_price != float(list_price):
            continue
        curve = data.type_curves.get(era_name, {}).get(user_type)
        if curve is None:
            raise ValueError(
                f"Estimates file is missing the {user_type} curve at list ${list_price:g}."
            )
        return curve
    raise ValueError(f"Estimates file has no promo curve at list ${list_price:g}.")


def _members_axis(user_type: str) -> str:
    return RATE_LABELS.get(user_type, RATE_LABELS["everyone"])


def _at_stay(era: PromoEra, price: float, horizon_extra_seasons: int) -> dict:
    """Recurring revenue is the stay rate, one minus churn, times the offer.

    The stored churn revenue is churn times price, so it is not reused. The
    standard error of stay revenue equals the stored churn revenue error,
    because the stay rate is the complement of churn.
    """
    churn = _interpolate(era.churn, price)
    del horizon_extra_seasons
    stay = 1.0 - churn["value"]
    revenue = stay * price
    metric = revenue
    ci_low, ci_high = (None, None)
    if churn["revenue_se"] is not None and not churn["extrapolated"]:
        ci_low, ci_high = interval(revenue, churn["revenue_se"])
    return {
        "members_rate": stay,
        "join_rate": None,
        "churn": churn["value"],
        "revenue": revenue,
        "metric": metric,
        "extrapolated": churn["extrapolated"],
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def _offered_count(era: PromoEra, user_type: str, data: Estimates) -> int:
    """Customer-seasons the rate applies to."""
    if user_type == "recurring":
        return sum(point.n for point in era.churn)
    if user_type in {"lapsed", "new"}:
        return sum(point.n for point in _require_type_curve(data, era.list_price, user_type).points)
    return era.n_customer_seasons


def _published_tie(
    data: Estimates, list_price: float, user_type: str
) -> tuple[float, float] | None:
    """Published this-season tie. Two saved dollars means the gap includes zero."""
    table = type_best_table(list_price, data)
    if table is None:
        return None
    dollars = table[user_type]
    if len(dollars) != 2:
        return None
    return tuple(sorted(dollars))


def _at_price(era: PromoEra, price: float, horizon_extra_seasons: int) -> dict:
    """Membership, sign-up, churn, revenue, and the horizon metric at one promo dollar."""
    members = _interpolate(era.membership, price)
    signup = _interpolate(era.signup, price)
    churn = _interpolate(era.churn, price)
    del horizon_extra_seasons
    revenue = members["value"] * price
    metric = revenue
    ci_low, ci_high = (None, None)
    if members["revenue_se"] is not None and not members["extrapolated"]:
        ci_low, ci_high = interval(revenue, members["revenue_se"])
    return {
        "members_rate": members["value"],
        "join_rate": signup["value"],
        "churn": churn["value"],
        "revenue": revenue,
        "metric": metric,
        "extrapolated": members["extrapolated"],
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def _interpolate(points: tuple[PricePoint, ...], price: float) -> dict:
    """Linear rate. Outside the knots, continue the nearest segment and flag it."""
    for point in points:
        if point.price == price:
            return {
                "value": point.rate,
                "se": point.rate_se,
                "revenue_se": point.revenue_se,
                "extrapolated": False,
            }
    if price < points[0].price:
        left, right, extrapolated = points[0], points[1], True
    elif price > points[-1].price:
        left, right, extrapolated = points[-2], points[-1], True
    else:
        left, right, extrapolated = points[0], points[1], False
        for candidate, nxt in zip(points, points[1:]):
            if candidate.price <= price <= nxt.price:
                left, right = candidate, nxt
                break
    span = right.price - left.price
    weight = 0.0 if span == 0 else (price - left.price) / span
    rate = left.rate + weight * (right.rate - left.rate)
    return {"value": rate, "se": None, "revenue_se": None, "extrapolated": extrapolated}


def _grid(era: PromoEra) -> tuple[float, ...]:
    low = era.membership[0].price
    high = era.membership[-1].price
    start = int(round(low / PRICE_STEP))
    end = int(round(high / PRICE_STEP))
    return tuple(round(index * PRICE_STEP, 2) for index in range(start, end + 1))


def _tie_pair(gap: RevenueGap) -> tuple[float, float] | None:
    """The two dollars in a saved comparison, when the 95% interval includes zero."""
    low, high = interval(gap.estimate, gap.se)
    if low is None or high is None or low > 0 or high < 0:
        return None
    return tuple(sorted((gap.price_a, gap.price_b)))


def _quick_prices(
    current: float,
    low: float,
    high: float,
    best: tuple[float, ...],
) -> tuple[float, ...]:
    picks: list[float] = []
    for price in list(best) + [round(current - 1, 2), round(current + 1, 2)]:
        if low <= price <= high and abs(price - current) > 1e-9 and price not in picks:
            picks.append(price)
    return tuple(picks[:3])


def _walk_numbers(value: object) -> list[float]:
    found: list[float] = []
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_walk_numbers(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_walk_numbers(item))
    elif isinstance(value, bool):
        return found
    elif isinstance(value, (int, float)):
        found.append(float(value))
    return found
