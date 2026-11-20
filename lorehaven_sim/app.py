"""Lorehaven Pricing Simulator.

Layout and wiring only. Every number on the page comes from sim.model.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import streamlit as st

from chat.gate import PasscodeGate, secrets_present
from chat.limits import DailyCap, SessionQuota, settings_from_env
from chat.dispatch import (
    AI_BUTTONS,
    MODE_AI,
    MODE_BASIC,
    ai_buttons_enabled,
    status_line,
    take_turn,
)
from chat.llm_assistant import AnthropicClient
from chat.templates import HELP_EXAMPLES
from sim.constants import (
    AT_RISK_JOIN_LABEL,
    COST_NOTE,
    HELP,
    LIST_GROUP_LABELS,
    MODE_LABELS,
    PRESET_LABELS,
    USER_TYPE_LABELS,
)
from sim.model import (
    Scenario,
    get_estimates,
    list_group_curves,
    members_curve,
    best_dollars,
    preset_scenario,
    promo_bounds,
    revenue_curve,
    simulate,
)
from sim.validate import confidence_text

st.set_page_config(page_title="Lorehaven Pricing Simulator", layout="wide")

_GROUP_NOTE = {
    "everyone": "Everyone uses the membership curve.",
    "recurring": "Recurring customers only. Revenue is the share who stay, one minus churn, times the offer.",
    "lapsed": "Lapsed customers only. Revenue is the share who rejoin times the offer.",
    "new": "New customers only. Revenue is the share who join for the first time times the offer.",
}
_LIST_NOTE = {
    "everyone": "Every customer, including recurring members and promo offers. No separate sign-up model.",
    "recurring": "Recurring customers, including promo offers. No sign-up model. Membership is the share who stay.",
    "lapsed": "Lapsed customers paying list price. Promo offers are left out. Sign-up and membership are the same fit.",
    "new": "New customers paying list price. Promo offers are left out. Sign-up and membership are the same fit.",
    "acquisition": "Lapsed and new customers. The count is their share of everyone. The lift is fit on people paying list price.",
    "acquisition_promo": "Lapsed and new customers, including people who were offered a promo. Sign-up and membership are the same fit.",
}


def main() -> None:
    try:
        get_estimates()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    _ensure_state()
    _apply_overrides()
    st.title("Lorehaven Pricing Simulator")
    st.caption(COST_NOTE)

    st.radio(
        "What do you want to set?",
        list(MODE_LABELS.values()),
        horizontal=True,
        key="mode_label",
        help=HELP["mode"],
    )
    show_chat = st.checkbox(
        "Show the assistant",
        key="show_chat",
        help="The page works the same with this closed. The assistant only repeats the simulator.",
    )

    if show_chat:
        scenario_col, result_col, chat_col = st.columns([1.15, 1.45, 1.15], gap="large")
    else:
        scenario_col, result_col = st.columns([1, 1.6], gap="large")
        chat_col = None

    with scenario_col:
        st.subheader("Scenario")
        scenario = _scenario_controls()
    with result_col:
        st.subheader("Results")
        result = _run(scenario)
        _results(scenario, result)
    if chat_col is not None:
        with chat_col:
            st.subheader("Ask")
            _chat(scenario)


def _ensure_state() -> None:
    """Fill any key the page reads before a widget creates it.

    A returning session can already have ``ready`` from an older script
    that did not set every key. Missing keys are filled; existing ones stay.
    """
    scenario = preset_scenario("current_policy")
    defaults = {
        "ready": True,
        "mode_label": MODE_LABELS[scenario.mode],
        "list_choice": "$12",
        "list_slider_value": 12.0,
        "list_generation": 0,
        "promo_value": float(scenario.promo_dollar),
        "promo_generation": 0,
        "outside": False,
        "user_type_label": USER_TYPE_LABELS[scenario.user_type],
        "per_type": False,
        "compare": False,
        "show_chat": True,
        "history": [],
        "pending": None,
        "buttons": HELP_EXAMPLES,
        "ai_notice": "",
        "assistant_radio": MODE_BASIC,
        "assistant_unlocked": False,
        "assistant_locked": False,
        "assistant_lock_reason": "",
        "session_quota": SessionQuota(settings_from_env().max_questions_per_session),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if st.session_state.get("list_choice") not in ("$12", "$15"):
        st.session_state.list_choice = "$12"
    if st.session_state.get("mode_label") not in MODE_LABELS.values():
        st.session_state.mode_label = MODE_LABELS["promo"]


def _apply_overrides() -> None:
    if st.session_state.pop("compare_next", False):
        st.session_state.compare = True
    overrides = st.session_state.pop("overrides", None)
    if not overrides:
        return
    for key, value in overrides.items():
        st.session_state[key] = value


def _scenario_controls() -> Scenario:
    mode = _mode_key()
    list_price = _list_price_slider() if mode == "list" else _list_price_control()
    promo = _promo_control(mode, list_price)
    user_type = _user_type_control(mode)
    if mode != "list":
        st.checkbox(
            "Show the best dollar for each group",
            key="per_type",
            help=HELP["per_type"],
        )
    st.caption("Starting points")
    for name, label in PRESET_LABELS.items():
        if st.button(label, help=HELP["preset"], width="stretch"):
            _queue(preset_scenario(name))
            st.rerun()
    return Scenario(list_price, promo, user_type, 0, mode)


def _list_price_slider() -> float:
    """Straight line from the comparison price to the cut, in tenths of a dollar."""
    low, high = 12.0, 15.0
    current = float(st.session_state.get("list_slider_value", low))
    if current < low or current > high:
        current = low
    generation = int(st.session_state.get("list_generation", 0))
    price = st.slider(
        "List price",
        min_value=low,
        max_value=high,
        value=current,
        step=0.1,
        key=f"list_slider_{generation}",
        help=HELP["list_price"],
    )
    st.session_state.list_slider_value = float(price)
    st.caption(
        "The line runs from $12 to $15. Those two prices were observed. "
        "Prices between them were not tested."
    )
    return float(price)


def _list_price_control() -> float:
    choice = st.radio(
        "List price",
        ["$12", "$15"],
        key="list_choice",
        help=HELP["list_price"],
        horizontal=True,
    )
    if choice == "$15":
        return 15.0
    return 12.0


def _promo_control(mode: str, list_price: float) -> float | None:
    if mode == "list":
        return None
    bounds = promo_bounds(list_price)
    if bounds is None:
        st.caption("No promo test was run at this list price.")
        return None
    low, high = float(bounds[0]), float(bounds[1])
    st.session_state.promo_low = low
    st.session_state.promo_high = high
    current = float(st.session_state.promo_value)
    if st.session_state.get("last_list_price") != list_price:
        st.session_state.last_list_price = list_price
        if not st.session_state.outside and not low <= current <= high:
            st.session_state.outside = True
    st.checkbox(
        "Use a dollar outside the tested range",
        key="outside",
        help="The cards score that dollar. The chart marks it Not tested, and confidence stays Low.",
        on_change=_keep_outside_if_needed,
    )
    # A new key each time the assistant or a preset changes the dollar.
    # Streamlit otherwise keeps the previous widget value and ignores value=.
    generation = int(st.session_state.promo_generation)
    if (not st.session_state.outside) and low <= current <= high:
        promo = st.slider(
            "Promo dollar",
            min_value=low,
            max_value=high,
            value=current,
            step=0.1,
            key=f"promo_slider_{generation}",
            help=HELP["promo"],
        )
    else:
        promo = st.number_input(
            "Promo dollar",
            value=current,
            step=0.1,
            key=f"promo_outside_{generation}",
            help=HELP["promo"],
        )
    st.session_state.promo_value = float(promo)
    st.caption(f"Tested at this list price: ${low:g} to ${high:g}.")
    return float(promo)


def _keep_outside_if_needed() -> None:
    """Stay on the typed box when the dollar is outside the tested range."""
    if st.session_state.outside:
        return
    current = float(st.session_state.promo_value)
    low = st.session_state.get("promo_low")
    high = st.session_state.get("promo_high")
    if low is not None and high is not None and not low <= current <= high:
        st.session_state.outside = True


def _results(scenario: Scenario, result) -> None:
    if scenario.mode == "promo":
        st.checkbox(
            "Compare to current policy",
            key="compare",
            help=HELP["compare"],
        )
    if result is None:
        return
    _badge(result.confidence, confidence_text(result.confidence))
    for warning in result.warnings:
        st.warning(warning)
    _cards(result)
    if st.session_state.get("per_type") and scenario.mode != "list":
        _type_table(scenario.list_price)
    _charts(scenario, result)


def _policy_delta(result) -> str:
    """Signed dollar change versus current policy, or Off when compare is closed."""
    if st.session_state.compare and result.vs_baseline is not None:
        return _signed_dollars(result.vs_baseline)
    return "Off"


def _cards(result) -> None:
    if result.scenario.mode == "list" and result.list_n is not None:
        _list_cards(result)
        return
    if result.offer_signup_per_100 is not None:
        top = st.columns(2)
        top[0].metric(AT_RISK_JOIN_LABEL, _percent(result.offer_signup_per_100))
        top[1].metric("More people join", f"{result.offer_signup_lift_pp:+.2f} pp")
        bottom = st.columns(2)
        bottom[0].metric("Revenue baseline", _dollars(result.offer_revenue_baseline))
        bottom[1].metric("Revenue change", _signed_dollars(result.offer_revenue_lift))
        st.caption(
            f"95% interval for the sign-up change: {result.offer_signup_ci_low_pp:.2f} to "
            f"{result.offer_signup_ci_high_pp:.2f} percentage points. "
            f"95% interval for the revenue change: {_dollars(result.offer_revenue_ci_low)} to "
            f"{_dollars(result.offer_revenue_ci_high)}."
        )
        st.caption(f"Sample: {_people(result.offer_n)} customer-seasons.")
        st.caption(
            f"Sign-up confidence is {result.observed_signup_confidence}. "
            f"Revenue confidence is {result.observed_revenue_confidence}."
        )
    elif result.members is not None:
        top = st.columns(2)
        top[0].metric(result.members_label, _people(result.members))
        top[1].metric("Revenue per person offered", _dollars(result.revenue_per_person))
        bottom = st.columns(2)
        bottom[0].metric("Revenue", _dollars(result.total_revenue))
        bottom[1].metric("Change vs current policy", _policy_delta(result))
    elif result.list_revenue_per_person is not None:
        top = st.columns(2)
        top[0].metric("People who join", _percent(result.signup_per_100), delta=result.join_delta_label)
        top[1].metric("Revenue per person at risk", _dollars(result.list_revenue_per_person))
        st.metric("Revenue", _dollars(result.list_total_revenue))
    else:
        cards = st.columns(2)
        dollars = _dollar_list(result.best_dollars)
        cards[0].metric("Saved best dollar", dollars or "—")
        cards[1].metric("Change vs current policy", _policy_delta(result))
    if st.session_state.compare and result.scenario.list_price != 12 and result.vs_baseline is not None:
        st.caption("Current policy is list $12. This change compares two different tests.")
    if result.scenario.mode == "list" and result.signup_per_100 is not None:
        st.caption(
            f"Members who stay pay about {_dollars(result.revenue_per_member_after)} after the cut "
            f"and {_dollars(result.revenue_per_member_before)} before it, in the five regions. "
            f"Pre-trends fail (chi-square {result.pretrend_chi2:,.0f} on {result.pretrend_df} df). "
            "Panem is the only control region."
        )
    note = _GROUP_NOTE.get(result.scenario.user_type)
    if note and (result.revenue_per_person is not None or result.offer_signup_per_100 is not None):
        st.caption(note)
    if result.ci_low is not None and result.ci_high is not None:
        st.caption(
            f"95% interval for revenue per person offered: "
            f"{_dollars(result.ci_low)} to {_dollars(result.ci_high)}."
        )
    elif result.interval_unavailable and result.revenue_per_person is not None:
        st.caption("The interval is unavailable at this dollar. It is saved only on the tested dollars.")


def _list_cards(result) -> None:
    """The write-up lifts for the selected list-price group."""
    top = st.columns(2)
    if result.signup_lift_pp is not None:
        top[0].metric("Sign-up lift", f"{result.signup_lift_pp:+.2f} pp")
    else:
        top[0].metric("Membership lift", f"{result.membership_lift_pp:+.2f} pp")
    top[1].metric("Revenue lift", _lift_dollars(result.revenue_lift))
    bottom = st.columns(2)
    bottom[0].metric("Customer-seasons", _people(result.list_n))
    bottom[1].metric("Share of everyone", f"{result.list_share * 100:.1f}%")
    if result.signup_ci_low_pp is not None:
        st.caption(
            f"95% interval for the sign-up lift: {result.signup_ci_low_pp:.2f} to "
            f"{result.signup_ci_high_pp:.2f} percentage points."
        )
    elif result.membership_ci_low_pp is not None:
        st.caption(
            f"95% interval for the membership lift: {result.membership_ci_low_pp:.2f} to "
            f"{result.membership_ci_high_pp:.2f} percentage points."
        )
    if result.revenue_ci_low is not None:
        st.caption(
            "95% interval for the revenue lift: "
            f"{_lift_dollars(result.revenue_ci_low)} to {_lift_dollars(result.revenue_ci_high)}."
        )
    st.caption(
        "Each lift is the five regions after the cut, relative to Panem. "
        f"Pre-trends fail (chi-square {result.pretrend_chi2:,.0f} on {result.pretrend_df} df). "
        "Panem is the only control region."
    )
    if result.list_n_fit is not None and result.list_n_fit != result.list_n:
        st.caption(
            f"The count is this group's share of all customer-seasons. "
            f"The lift is fit on {_people(result.list_n_fit)} customer-seasons."
        )
    if abs(result.scenario.list_price - 12) > 1e-9:
        st.caption("This price reads the straight line. The 95% interval is saved at $12.")
    note = _LIST_NOTE.get(result.scenario.user_type)
    if note:
        st.caption(note)
    st.caption(
        f"Confidence in the comparison is {result.observed_signup_confidence}. "
        f"Revenue confidence is {result.observed_revenue_confidence}."
    )


def _charts(scenario: Scenario, result) -> None:
    import plotly.graph_objects as go

    if scenario.mode == "promo" and result.revenue_per_person is not None:
        off_grid = _off_grid_point(scenario, result.revenue_per_person, result.extrapolated)
        _plot(go, revenue_curve(scenario), "Revenue", off_grid=off_grid)
        members_off = _off_grid_point(scenario, result.members_per_100, result.extrapolated)
        _plot(go, members_curve(scenario), result.members_label, off_grid=members_off)
        if result.extrapolated:
            st.caption("The selected dollar is off the tested grid. The chart marks it Not tested.")
    if scenario.mode == "list" and result.list_n is not None:
        rate, revenue = list_group_curves(scenario.user_type, scenario.list_price)
        _plot(go, rate, rate.y_label, "List price ($)", untested_line=True)
        _plot(go, revenue, revenue.y_label, "List price ($)", untested_line=True)
        st.caption(
            "The line between $12 and $15 was not tested. "
            "$12 and $15 are marked Observed. "
            "Hover anywhere between them to read the straight line. "
            "The interval is the 95% sampling error of the lift, drawn at $12."
        )


def _off_grid_point(scenario: Scenario, value: float | None, extrapolated: bool):
    """The scored off-grid dollar. The chart does not connect it to the tested grid."""
    if not extrapolated or value is None or scenario.promo_dollar is None:
        return None
    return (float(scenario.promo_dollar), float(value))


def _axis_kind(title: str, y_label: str) -> str:
    """Dollar, percentage points, or a percent. A lift in percentage points is not a percent."""
    text = f"{title} {y_label}".lower()
    if "(pp)" in text or "percentage point" in text:
        return "points"
    if "revenue" in text or "$" in text or "net gain" in text:
        return "dollar"
    return "percent"


def _hover_text(
    price: float,
    value: float,
    low: float | None,
    high: float | None,
    kind: str,
) -> str:
    """Offer dollar and point value, plus the half-width when an interval exists."""
    shown_x = f"${price:.2f}"
    shown_y = _axis_value(value, kind)
    if low is None or high is None:
        return f"{shown_x}, {shown_y}"
    margin = _axis_value((high - low) / 2, kind)
    return f"{shown_x}, {shown_y} ± {margin}"


def _axis_value(value: float, kind: str) -> str:
    if kind == "dollar":
        return _dollars(value)
    if kind == "points":
        return f"{value:.2f} pp"
    return _percent(value)


def _plot(
    go,
    curve,
    title: str,
    xaxis_title: str = "Dollar",
    *,
    untested_line: bool = False,
    off_grid: tuple[float, float] | None = None,
) -> None:
    if not curve.points and off_grid is None:
        return
    kind = _axis_kind(title, curve.y_label)

    def text_for(point) -> str:
        shown = _hover_text(point.price, point.y, point.ci_low, point.ci_high, kind)
        if untested_line and not _observed_end(point.price):
            return f"{shown} · not tested"
        return shown

    figure = go.Figure()
    if curve.points:
        figure.add_trace(
            go.Scatter(
                x=[point.price for point in curve.points],
                y=[point.y for point in curve.points],
                mode="lines",
                name="Not tested" if untested_line else curve.y_label,
                line={"color": "#1f4e79", "width": 3},
                hovertext=[text_for(point) for point in curve.points],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )
    if untested_line:
        ends = [point for point in curve.points if _observed_end(point.price)]
        if ends:
            figure.add_trace(
                go.Scatter(
                    x=[point.price for point in ends],
                    y=[point.y for point in ends],
                    mode="markers",
                    name="Observed",
                    marker={"size": 11, "symbol": "diamond", "color": "#548235"},
                    hovertext=[text_for(point) for point in ends],
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            )
    if off_grid is not None:
        price, value = off_grid
        figure.add_trace(
            go.Scatter(
                x=[price],
                y=[value],
                mode="markers",
                name="Not tested",
                marker={"size": 12, "symbol": "circle", "color": "#c45911"},
                hovertext=[f"{_hover_text(price, value, None, None, kind)} · not tested"],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )
    band = [point for point in curve.points if point.ci_low is not None]
    if band:
        figure.add_trace(
            go.Scatter(
                x=[point.price for point in band],
                y=[point.y for point in band],
                mode="markers",
                name="95% interval",
                marker={"size": 7, "color": "#1f4e79"},
                error_y={
                    "type": "data",
                    "array": [point.ci_high - point.y for point in band],
                    "arrayminus": [point.y - point.ci_low for point in band],
                    "color": "#9dc3e6",
                },
                hovertext=[text_for(point) for point in band],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )
    best = [point for point in curve.points if point.is_best]
    if best:
        figure.add_trace(
            go.Scatter(
                x=[point.price for point in best],
                y=[point.y for point in best],
                mode="markers",
                name="Best dollar",
                marker={"size": 16, "symbol": "star", "color": "#c45911"},
                hovertext=[text_for(point) for point in best],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )
    if curve.selected_y is not None and curve.selected_price is not None:
        interior = untested_line and not _observed_end(curve.selected_price)
        selected_hover = _hover_text(curve.selected_price, curve.selected_y, None, None, kind)
        if interior:
            selected_hover = f"{selected_hover} · not tested"
        figure.add_trace(
            go.Scatter(
                x=[curve.selected_price],
                y=[curve.selected_y],
                mode="markers",
                name="Not tested" if interior else "Selected",
                marker={"size": 12, "symbol": "circle", "color": "#c45911"},
                hovertext=[selected_hover],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )
    if curve.observed_y is not None:
        figure.add_trace(
            go.Scatter(
                x=[curve.observed_price],
                y=[curve.observed_y],
                mode="markers+text",
                name=curve.observed_label,
                text=[curve.observed_label],
                textposition="top center",
                marker={"size": 14, "symbol": "diamond", "color": "#548235"},
                hovertext=[_hover_text(curve.observed_price, curve.observed_y, None, None, kind)],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )
    yaxis = {"title": curve.y_label}
    if kind == "dollar":
        yaxis["tickformat"] = "$.2f"
    elif kind == "points":
        yaxis["tickformat"] = ".2f"
    else:
        yaxis["tickformat"] = ".2f"
        yaxis["ticksuffix"] = "%"
    figure.update_layout(
        title=title,
        hovermode="closest",
        xaxis_title=xaxis_title,
        yaxis=yaxis,
        height=400,
        margin={"l": 10, "r": 10, "t": 40, "b": 72},
        legend={
            "orientation": "h",
            "yanchor": "top",
            "y": -0.32,
            "xanchor": "left",
            "x": 0,
        },
    )
    st.plotly_chart(figure, width="stretch")


def _observed_end(price: float) -> bool:
    return abs(price - 12.0) < 1e-9 or abs(price - 15.0) < 1e-9


def _type_table(list_price: float) -> None:
    if promo_bounds(list_price) is None:
        st.info("Best dollars by group were saved only for list $12 and list $15.")
        return
    st.markdown("**Best dollar by group, this season**")
    for name, label in USER_TYPE_LABELS.items():
        dollars = best_dollars(list_price, 0, user_type=name)
        st.write(f"{label}: {_dollar_list(dollars)}")


def _secret_map() -> dict[str, str]:
    """Read the two secrets. Callers check that they exist and never display them."""
    found = {
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        "APP_PASSCODE": os.environ.get("APP_PASSCODE", "").strip(),
    }
    if all(found.values()):
        return found
    try:
        for name in found:
            if not found[name]:
                found[name] = str(st.secrets.get(name, "")).strip()
    except Exception:
        pass
    return found


@st.cache_resource
def _daily_cap() -> DailyCap:
    """One counter for every session on this server, keyed by UTC date inside the cap."""
    return DailyCap(settings_from_env().global_daily_questions)


def _utc_today():
    return datetime.now(timezone.utc).date()


def _chat(scenario: Scenario) -> None:
    values = _secret_map()
    if secrets_present(values) and "gate" not in st.session_state:
        st.session_state.gate = PasscodeGate(values["APP_PASSCODE"])
    gate = st.session_state.get("gate")
    if gate and gate.unlocked and not gate.locked_out():
        st.session_state.assistant_unlocked = True
    if "session_quota" not in st.session_state:
        st.session_state.session_quota = SessionQuota(settings_from_env().max_questions_per_session)
    if st.session_state.get("assistant_locked"):
        st.session_state.assistant_radio = MODE_BASIC
    pending_radio = st.session_state.pop("assistant_radio_next", None)
    if pending_radio is not None and not st.session_state.get("assistant_locked"):
        st.session_state.assistant_radio = pending_radio
    st.radio(
        "Assistant",
        [MODE_AI, MODE_BASIC],
        horizontal=True,
        key="assistant_radio",
        disabled=bool(st.session_state.get("assistant_locked")),
    )
    radio = st.session_state.assistant_radio
    unlocked = bool(st.session_state.get("assistant_unlocked")) and not (gate and gate.locked_out())
    reason = status_line(
        radio=radio,
        unlocked=unlocked,
        locked_basic=bool(st.session_state.get("assistant_locked")),
        lock_reason=str(st.session_state.get("assistant_lock_reason") or ""),
        notice=str(st.session_state.get("ai_notice") or ""),
        secrets_ok=secrets_present(values),
    )
    answering_ai = ai_buttons_enabled(
        radio=radio,
        unlocked=unlocked,
        locked_basic=bool(st.session_state.get("assistant_locked")),
        secrets_ok=secrets_present(values),
    )
    st.caption(MODE_AI if answering_ai else MODE_BASIC)
    if reason:
        st.caption(reason)
    if answering_ai:
        quota = st.session_state.session_quota
        st.caption(f"{quota.remaining()} of {quota.maximum} questions left")
        st.caption(
            "Answers are generated from the written analysis and may contain errors. "
            "Check figures against the report."
        )
    if radio == MODE_AI and not unlocked and not st.session_state.get("assistant_locked"):
        if secrets_present(values) and gate and not gate.locked_out():
            _passcode_form(gate)
        elif gate and gate.locked_out():
            st.caption("Too many tries. Basic mode is available for this session.")
    _message_box(scenario, ai_enabled=answering_ai, show_ai_buttons=radio == MODE_AI)


def _passcode_form(gate: PasscodeGate) -> None:
    """Ask for the passcode. The typed value is not stored in the chat."""
    st.caption("Enter the passcode to use the AI assistant.")
    st.text_input("Passcode", type="password", key="passcode_input")
    if gate.failures and not gate.locked_out():
        st.caption("That passcode did not match.")
    if st.button("Continue"):
        gate.try_passcode(str(st.session_state.get("passcode_input", "")))
        st.session_state.pop("passcode_input", None)
        if gate.unlocked:
            st.session_state.assistant_unlocked = True
            st.session_state.assistant_radio_next = MODE_AI
            st.session_state.ai_notice = ""
        st.rerun()


def _message_box(scenario: Scenario, *, ai_enabled: bool, show_ai_buttons: bool) -> None:
    with st.container(height=360):
        for message in st.session_state.history[-40:]:
            with st.chat_message(message["role"]):
                st.write(message["text"])
    if show_ai_buttons:
        labels = AI_BUTTONS
        disabled = not ai_enabled
    else:
        labels = st.session_state.buttons or HELP_EXAMPLES
        disabled = False
    for index, label in enumerate(labels):
        if st.button(label, key=f"suggest_{index}_{label}", disabled=disabled):
            _submit(scenario, label)
    prompt = st.chat_input("Ask about a price")
    if prompt:
        _submit(scenario, prompt)


def _submit(scenario: Scenario, text: str) -> None:
    settings = settings_from_env()
    box = st.empty()
    chunks: list[str] = []

    def on_text(piece: str) -> None:
        chunks.append(piece)
        box.write("".join(chunks))

    def client_factory():
        return AnthropicClient(_secret_map()["ANTHROPIC_API_KEY"], settings.request_timeout_s)

    gate = st.session_state.get("gate")
    unlocked = bool(st.session_state.get("assistant_unlocked")) and not (gate and gate.locked_out())
    taken = take_turn(
        text,
        radio=st.session_state.assistant_radio,
        unlocked=unlocked,
        locked_basic=bool(st.session_state.get("assistant_locked")),
        lock_reason=str(st.session_state.get("assistant_lock_reason") or ""),
        history=list(st.session_state.history),
        session=st.session_state.session_quota,
        daily=_daily_cap(),
        day=_utc_today(),
        scenario=scenario,
        pending=st.session_state.pending,
        secrets_ok=secrets_present(_secret_map()),
        client_factory=client_factory,
        settings=settings,
        on_text=on_text,
    )
    st.session_state.history.append({"role": "user", "text": text})
    st.session_state.history.append({"role": "assistant", "text": taken.reply})
    st.session_state.assistant_radio_next = taken.radio
    st.session_state.assistant_locked = taken.locked_basic
    st.session_state.assistant_lock_reason = taken.lock_reason
    st.session_state.ai_notice = taken.reason if taken.radio == MODE_BASIC and not taken.locked_basic else ""
    if taken.locked_basic:
        st.session_state.ai_notice = ""
    if taken.buttons is not None:
        st.session_state.buttons = taken.buttons
    st.session_state.pending = taken.pending
    if taken.show_comparison:
        st.session_state.compare_next = True
    if taken.queue is not None:
        _queue(taken.queue)
    st.rerun()


def _run(scenario: Scenario):
    try:
        return simulate(scenario)
    except ValueError as exc:
        st.error(str(exc))
        return None


def _queue(scenario: Scenario) -> None:
    price = float(scenario.list_price)
    choice = "$15" if price == 15 else "$12"
    promo = float(scenario.promo_dollar) if scenario.promo_dollar is not None else float(
        st.session_state.get("promo_value", 11)
    )
    bounds = promo_bounds(price)
    outside = bounds is not None and not bounds[0] <= promo <= bounds[1]
    st.session_state.overrides = {
        "mode_label": MODE_LABELS[scenario.mode],
        "list_choice": choice,
        "list_slider_value": price if scenario.mode == "list" else float(st.session_state.get("list_slider_value", 12.0)),
        "list_generation": int(st.session_state.get("list_generation", 0)) + (1 if scenario.mode == "list" else 0),
        "promo_value": promo,
        "promo_generation": int(st.session_state.get("promo_generation", 0)) + 1,
        "outside": outside,
        "user_type_label": (
            LIST_GROUP_LABELS if scenario.mode == "list" else USER_TYPE_LABELS
        )[scenario.user_type],
        "last_list_price": price,
    }


def _badge(level: str, detail: str) -> None:
    st.markdown(f"**Confidence: {level}.** {detail}")


def _mode_key() -> str:
    labels = {label: key for key, label in MODE_LABELS.items()}
    return labels[st.session_state.mode_label]


def _user_type_control(mode: str) -> str:
    """Promo groups, plus the two list-price acquisition comparisons."""
    labels = dict(LIST_GROUP_LABELS if mode == "list" else USER_TYPE_LABELS)
    if st.session_state.user_type_label not in labels.values():
        st.session_state.user_type_label = labels["everyone"]
    return str(
        _labeled_choice(
            "Who is offered this?",
            labels,
            "user_type_label",
            HELP["user_type"],
        )
    )


def _labeled_choice(label: str, mapping: dict, key: str, help_text: str) -> object:
    st.radio(label, list(mapping.values()), key=key, help=help_text)
    reverse = {text: value for value, text in mapping.items()}
    return reverse[st.session_state[key]]


def _percent(value: float) -> str:
    """A rate per hundred, shown as a percent. 5.23 per hundred is 5.23%."""
    return f"{value:.2f}%"


def _people(value: float) -> str:
    """254,414 people reads as 254K. A million or more reads as 1.20M."""
    absolute = abs(value)
    sign = "-" if value < 0 else ""
    if absolute >= 999_500:
        return f"{sign}{absolute / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{sign}{round(absolute / 1_000):.0f}K"
    return f"{sign}{absolute:.0f}"


def _dollars(value: float) -> str:
    """Two decimal places. Totals of about a million or more read as $2.80M."""
    absolute = abs(value)
    sign = "-" if value < 0 else ""
    if absolute >= 999_500:
        return f"{sign}${absolute / 1_000_000:.2f}M"
    return f"{sign}${absolute:,.2f}"


def _lift_dollars(value: float) -> str:
    """Three decimals under $1, so $0.348, $0.337, and $0.353 stay distinct."""
    digits = 3 if abs(value) < 1 else 2
    text = f"${abs(value):,.{digits}f}"
    if value > 0:
        return f"+{text}"
    if value < 0:
        return f"-{text}"
    return text


def _signed_dollars(value: float) -> str:
    text = _dollars(value)
    if value > 0:
        return f"+{text}"
    return text


def _dollar_list(prices: tuple[float, ...]) -> str:
    return " and ".join(f"${price:g}" for price in prices)


if __name__ == "__main__":
    main()
else:
    main()
