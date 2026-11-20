"""Load data/estimates.json into dataclasses. Missing tables raise ValueError."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sim.constants import LIST_GROUP_TYPES, LIST_OFFER_TYPES, PROMO_GRID, USER_TYPES

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "estimates.json"

REQUIRED_PROMO_KEYS = (
    "list_price",
    "n_customer_seasons",
    "reference_dollar",
    "membership",
    "signup",
    "churn",
    "revenue_gap",
)
REQUIRED_LIST_KEYS = (
    "counterfactual_signup",
    "poisson_rate_ratio",
    "comparison_price",
    "observed_price",
    "observed_signup_lift",
    "observed_signup_se",
    "observed_acquisition_revenue_lift",
    "observed_acquisition_revenue_se",
    "observed_all_revenue_lift",
    "observed_all_revenue_se",
    "observed_membership_lift",
    "observed_membership_se",
    "n_acquisition",
    "n_all",
    "revenue_per_member_before",
    "revenue_per_member_after",
    "pretrend_chi2",
    "pretrend_df",
)
REQUIRED_OFFER_KEYS = (
    "signup_baseline",
    "signup_lift",
    "signup_se",
    "revenue_baseline",
    "revenue_lift",
    "revenue_se",
    "n",
)


@dataclass(frozen=True)
class PricePoint:
    """One tested promo dollar."""

    price: float
    rate: float
    rate_se: float
    revenue: float
    revenue_se: float
    n: int


@dataclass(frozen=True)
class RevenueGap:
    """Saved revenue difference between two tested dollars. Not a full covariance."""

    price_a: float
    price_b: float
    estimate: float
    se: float


@dataclass(frozen=True)
class PromoEra:
    """One promo experiment: pre-cut (list $15) or post-cut (list $12).

    Sign-up is the estimated join rate among people offered a promo. Membership
    and churn are what the page scores. The sign-up series stays with them.
    """

    list_price: float
    n_customer_seasons: int
    reference_dollar: float
    membership: tuple[PricePoint, ...]
    signup: tuple[PricePoint, ...]
    churn: tuple[PricePoint, ...]
    revenue_gap: RevenueGap


@dataclass(frozen=True)
class ListPriceEstimates:
    """Observed $12 versus $15 comparison, plus the inputs of the elasticity curve.

    The membership lift, standard errors, and all-customer sample size are the
    saved estimates. The page does not display every one of them.
    """

    counterfactual_signup: float
    poisson_rate_ratio: float
    comparison_price: float
    observed_price: float
    observed_signup_lift: float
    observed_signup_se: float
    observed_acquisition_revenue_lift: float
    observed_acquisition_revenue_se: float
    observed_all_revenue_lift: float
    observed_all_revenue_se: float
    observed_membership_lift: float
    observed_membership_se: float
    n_acquisition: int
    n_all: int
    revenue_per_member_before: float
    revenue_per_member_after: float
    pretrend_chi2: float
    pretrend_df: int
    groups: dict[str, "ListGroup"]
    offer_groups: dict[str, "OfferGroup"]


@dataclass(frozen=True)
class ListGroup:
    """One row of the list-price results table.

    Lifts are the five regions after the cut, relative to Panem. ``n`` is the
    group's share of all customer-seasons. ``n_fit`` is the regression sample
    when that is a smaller list-price subset. A rate or revenue base is the
    level at $15 from the same fit, when one was saved.
    """

    n: int
    n_fit: int
    signup_lift: float | None
    signup_se: float | None
    membership_lift: float | None
    membership_se: float | None
    revenue_lift: float
    revenue_se: float
    rate_base: float | None
    revenue_base: float | None


@dataclass(frozen=True)
class OfferGroup:
    """One lapsed-plus-new comparison from the $15 to $12 cut.

    The baseline is the fitted Panem level in winter 2019. The lift is the
    five regions after the cut, relative to Panem.
    """

    signup_baseline: float
    signup_lift: float
    signup_se: float
    revenue_baseline: float
    revenue_lift: float
    revenue_se: float
    n: int


@dataclass(frozen=True)
class TypeCurve:
    """Price curve for one group in one era. Revenue is rate times the offer."""

    points: tuple[PricePoint, ...]
    revenue_gap: RevenueGap


@dataclass(frozen=True)
class Estimates:
    promo: dict[str, PromoEra]
    type_best: dict[str, dict[str, tuple[float, ...]]]
    type_curves: dict[str, dict[str, TypeCurve]]
    list_price: ListPriceEstimates

    def era_for_list_price(self, list_price: float) -> PromoEra | None:
        """Return the promo experiment run at this list price, if one exists."""
        for era in self.promo.values():
            if era.list_price == float(list_price):
                return era
        return None


def load(path: Path | None = None) -> Estimates:
    """Read and validate the estimates file. Raise ValueError if a table is missing."""
    source = DEFAULT_PATH if path is None else Path(path)
    try:
        payload = json.loads(source.read_text())
    except FileNotFoundError as exc:
        raise ValueError(f"Estimates file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Estimates file is not valid JSON: {source}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Estimates file must be a JSON object")
    return Estimates(
        promo=_promo(payload),
        type_best=_types(payload),
        type_curves=_type_curves(payload),
        list_price=_list_price(payload),
    )


def _need(mapping: dict, key: str, table: str) -> object:
    if key not in mapping:
        raise ValueError(f"Estimates file is missing {table}.{key}")
    return mapping[key]


def _points(rows: object, table: str) -> tuple[PricePoint, ...]:
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Estimates file is missing table {table}")
    points = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Estimates file has a bad row in {table}")
        for field in ("price", "rate", "rate_se", "revenue", "revenue_se", "n"):
            if field not in row:
                raise ValueError(f"Estimates file is missing {table}.{field}")
        points.append(
            PricePoint(
                price=float(row["price"]),
                rate=float(row["rate"]),
                rate_se=float(row["rate_se"]),
                revenue=float(row["revenue"]),
                revenue_se=float(row["revenue_se"]),
                n=int(row["n"]),
            )
        )
    points.sort(key=lambda point: point.price)
    return tuple(points)


def _promo(payload: dict) -> dict[str, PromoEra]:
    raw = payload.get("promo")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Estimates file is missing table promo")
    eras = {}
    for name, block in raw.items():
        if not isinstance(block, dict):
            raise ValueError(f"Estimates file is missing table promo.{name}")
        for key in REQUIRED_PROMO_KEYS:
            _need(block, key, f"promo.{name}")
        gap = block["revenue_gap"]
        if not isinstance(gap, dict):
            raise ValueError(f"Estimates file is missing table promo.{name}.revenue_gap")
        for field in ("price_a", "price_b", "estimate", "se"):
            if field not in gap:
                raise ValueError(
                    f"Estimates file is missing promo.{name}.revenue_gap.{field}"
                )
        era = PromoEra(
            list_price=float(block["list_price"]),
            n_customer_seasons=int(block["n_customer_seasons"]),
            reference_dollar=float(block["reference_dollar"]),
            membership=_points(block["membership"], f"promo.{name}.membership"),
            signup=_points(block["signup"], f"promo.{name}.signup"),
            churn=_points(block["churn"], f"promo.{name}.churn"),
            revenue_gap=RevenueGap(
                price_a=float(gap["price_a"]),
                price_b=float(gap["price_b"]),
                estimate=float(gap["estimate"]),
                se=float(gap["se"]),
            ),
        )
        expected = PROMO_GRID.get(era.list_price)
        if expected is not None:
            low = era.membership[0].price
            high = era.membership[-1].price
            if (low, high) != expected:
                raise ValueError(
                    f"Promo grid at list ${era.list_price:g} is ${low:g}–${high:g}, "
                    f"expected ${expected[0]:g}–${expected[1]:g}"
                )
        eras[name] = era
    return eras


def _types(payload: dict) -> dict[str, dict[str, tuple[float, ...]]]:
    raw = payload.get("types")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Estimates file is missing table types")
    parsed: dict[str, dict[str, tuple[float, ...]]] = {}
    for era, groups in raw.items():
        if not isinstance(groups, dict):
            raise ValueError(f"Estimates file is missing table types.{era}")
        parsed[era] = {}
        for user_type in USER_TYPES:
            entry = groups.get(user_type)
            if not isinstance(entry, dict) or "best_dollars" not in entry:
                raise ValueError(
                    f"Estimates file is missing table types.{era}.{user_type}"
                )
            dollars = entry["best_dollars"]
            if not isinstance(dollars, list) or not dollars:
                raise ValueError(
                    f"Estimates file is missing best dollars for types.{era}.{user_type}"
                )
            parsed[era][user_type] = tuple(float(dollar) for dollar in dollars)
    return parsed


def _type_curves(payload: dict) -> dict[str, dict[str, TypeCurve]]:
    """Lapsed and new curves. Everyone and recurring are stored on the promo era."""
    raw = payload.get("types")
    if not isinstance(raw, dict):
        raise ValueError("Estimates file is missing table types")
    parsed: dict[str, dict[str, TypeCurve]] = {}
    for era, groups in raw.items():
        if not isinstance(groups, dict):
            raise ValueError(f"Estimates file is missing table types.{era}")
        parsed[era] = {}
        for user_type in ("lapsed", "new"):
            entry = groups.get(user_type)
            if not isinstance(entry, dict):
                raise ValueError(f"Estimates file is missing table types.{era}.{user_type}")
            gap = entry.get("revenue_gap")
            if not isinstance(gap, dict):
                raise ValueError(
                    f"Estimates file is missing table types.{era}.{user_type}.revenue_gap"
                )
            for field in ("price_a", "price_b", "estimate", "se"):
                if field not in gap:
                    raise ValueError(
                        f"Estimates file is missing types.{era}.{user_type}.revenue_gap.{field}"
                    )
            parsed[era][user_type] = TypeCurve(
                points=_points(entry.get("points"), f"types.{era}.{user_type}.points"),
                revenue_gap=RevenueGap(
                    price_a=float(gap["price_a"]),
                    price_b=float(gap["price_b"]),
                    estimate=float(gap["estimate"]),
                    se=float(gap["se"]),
                ),
            )
    return parsed


def _list_price(payload: dict) -> ListPriceEstimates:
    raw = payload.get("list_price")
    if not isinstance(raw, dict):
        raise ValueError("Estimates file is missing table list_price")
    for key in REQUIRED_LIST_KEYS:
        _need(raw, key, "list_price")
    return ListPriceEstimates(
        counterfactual_signup=float(raw["counterfactual_signup"]),
        poisson_rate_ratio=float(raw["poisson_rate_ratio"]),
        comparison_price=float(raw["comparison_price"]),
        observed_price=float(raw["observed_price"]),
        observed_signup_lift=float(raw["observed_signup_lift"]),
        observed_signup_se=float(raw["observed_signup_se"]),
        observed_acquisition_revenue_lift=float(raw["observed_acquisition_revenue_lift"]),
        observed_acquisition_revenue_se=float(raw["observed_acquisition_revenue_se"]),
        observed_all_revenue_lift=float(raw["observed_all_revenue_lift"]),
        observed_all_revenue_se=float(raw["observed_all_revenue_se"]),
        observed_membership_lift=float(raw["observed_membership_lift"]),
        observed_membership_se=float(raw["observed_membership_se"]),
        n_acquisition=int(raw["n_acquisition"]),
        n_all=int(raw["n_all"]),
        revenue_per_member_before=float(raw["revenue_per_member_before"]),
        revenue_per_member_after=float(raw["revenue_per_member_after"]),
        pretrend_chi2=float(raw["pretrend_chi2"]),
        pretrend_df=int(raw["pretrend_df"]),
        groups=_list_groups(raw),
        offer_groups=_offer_groups(raw),
    )


def _optional_float(entry: dict, field: str, table: str) -> float | None:
    if field not in entry:
        raise ValueError(f"Estimates file is missing {table}.{field}")
    value = entry[field]
    if value is None:
        return None
    return float(value)


def _list_groups(raw: dict) -> dict[str, ListGroup]:
    groups = raw.get("groups")
    if not isinstance(groups, dict):
        raise ValueError("Estimates file is missing table list_price.groups")
    parsed: dict[str, ListGroup] = {}
    fields = (
        "n",
        "n_fit",
        "signup_lift",
        "signup_se",
        "membership_lift",
        "membership_se",
        "revenue_lift",
        "revenue_se",
        "rate_base",
        "revenue_base",
    )
    for name in LIST_GROUP_TYPES:
        entry = groups.get(name)
        table = f"list_price.groups.{name}"
        if not isinstance(entry, dict):
            raise ValueError(f"Estimates file is missing table {table}")
        for field in fields:
            _need(entry, field, table)
        parsed[name] = ListGroup(
            n=int(entry["n"]),
            n_fit=int(entry["n_fit"]),
            signup_lift=_optional_float(entry, "signup_lift", table),
            signup_se=_optional_float(entry, "signup_se", table),
            membership_lift=_optional_float(entry, "membership_lift", table),
            membership_se=_optional_float(entry, "membership_se", table),
            revenue_lift=float(entry["revenue_lift"]),
            revenue_se=float(entry["revenue_se"]),
            rate_base=_optional_float(entry, "rate_base", table),
            revenue_base=_optional_float(entry, "revenue_base", table),
        )
    return parsed


def _offer_groups(raw: dict) -> dict[str, OfferGroup]:
    groups = raw.get("offer_groups")
    if not isinstance(groups, dict):
        raise ValueError("Estimates file is missing table list_price.offer_groups")
    parsed: dict[str, OfferGroup] = {}
    for name in LIST_OFFER_TYPES:
        entry = groups.get(name)
        table = f"list_price.offer_groups.{name}"
        if not isinstance(entry, dict):
            raise ValueError(f"Estimates file is missing table {table}")
        for field in REQUIRED_OFFER_KEYS:
            _need(entry, field, table)
        parsed[name] = OfferGroup(
            signup_baseline=float(entry["signup_baseline"]),
            signup_lift=float(entry["signup_lift"]),
            signup_se=float(entry["signup_se"]),
            revenue_baseline=float(entry["revenue_baseline"]),
            revenue_lift=float(entry["revenue_lift"]),
            revenue_se=float(entry["revenue_se"]),
            n=int(entry["n"]),
        )
    return parsed
