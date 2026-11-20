"""Rebuild data/estimates.json from the saved regression output.

Run from lorehaven_sim:

    python analysis/export_estimates.py

Promo rates come from output/discount/estimates.csv at full precision.
List-price lifts, the counterfactual sign-up rate, the Poisson rate
ratio, and the pre-trend test come from output/list_price/. The script
stops if a required table or row is missing.

Two figures are not in those files. They are copied from the list-price
note and named below: revenue per member before and after the cut, and
the best promo dollar by user type. Recurring revenue is not stored as
its own outcome. It is the churn curve, one minus the churn rate, times
the offer. Lapsed and New do not have separate rate curves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

SIM_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_ROOT.parent
PROMO_CSV = REPO_ROOT / "output" / "discount" / "estimates.csv"
LIST_ESTIMATES = REPO_ROOT / "output" / "list_price" / "estimates.csv"
LIST_EXTENSIONS = REPO_ROOT / "output" / "list_price" / "extensions" / "results.csv"
OFFER_GROUPS = REPO_ROOT / "output" / "list_price" / "offer_groups.json"
OUT_PATH = SIM_ROOT / "data" / "estimates.json"
TYPE_CURVES = REPO_ROOT / "output" / "discount" / "type_curves.csv"
CURVE_TYPES = ("lapsed", "new")

# Five regions, from the list-price note. Not a regression row.
REVENUE_PER_MEMBER_BEFORE = 11.89
REVENUE_PER_MEMBER_AFTER = 8.96

# Published this-season peaks. A list of two dollars is a tie.
# Lapsed and New have no separate rate curve. Recurring is the churn curve.
TYPE_BEST = {
    "pre": {
        "everyone": [10, 11],
        "new": [10],
        "lapsed": [10],
        "recurring": [13, 14],
    },
    "post": {
        "everyone": [11],
        "new": [7],
        "lapsed": [7, 8],
        "recurring": [11],
    },
}

REQUIRED_OUTCOMES = ("membership", "signup", "churn")
REQUIRED_ERAS = ("pre", "post")
LIST_BY_ERA = {"pre": 15, "post": 12}
REFERENCE_DOLLAR = 11
PUBLISHED_RATE_RATIO = 2.15


def _require(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Missing input file: {path}")


def _one(frame: pd.DataFrame, label: str) -> pd.Series:
    if frame.empty:
        raise SystemExit(f"Missing estimate row: {label}")
    if len(frame) > 1:
        raise SystemExit(f"Expected one row for {label}, found {len(frame)}")
    return frame.iloc[0]


def _promo_block(frame: pd.DataFrame, era: str) -> dict:
    block = frame[frame["era"] == era]
    if block.empty:
        raise SystemExit(f"Promo table has no '{era}' rows")
    outcomes = {}
    for outcome in REQUIRED_OUTCOMES:
        rows = block[block["outcome"] == outcome].sort_values("price")
        if rows.empty:
            raise SystemExit(f"Promo table is missing {outcome} for {era}")
        points = []
        for row in rows.itertuples(index=False):
            price = float(row.price)
            rate = float(row.adj_rate)
            revenue = float(row.adj_revenue)
            if abs(revenue - rate * price) > 1e-6:
                raise SystemExit(
                    f"{outcome} {era} ${price:g}: revenue is not rate times price"
                )
            points.append(
                {
                    "price": price,
                    "rate": rate,
                    "rate_se": float(row.adj_se),
                    "revenue": revenue,
                    "revenue_se": float(row.adj_revenue_se),
                    "n": int(row.n),
                }
            )
        outcomes[outcome] = points
    membership = block[block["outcome"] == "membership"]
    gap_row = membership.iloc[0]
    prices = {point["price"] for point in outcomes["membership"]}
    if REFERENCE_DOLLAR not in prices:
        raise SystemExit(f"{era} membership grid has no ${REFERENCE_DOLLAR}")
    return {
        "list_price": LIST_BY_ERA[era],
        "n_customer_seasons": int(membership["n"].sum()),
        "reference_dollar": REFERENCE_DOLLAR,
        "membership": outcomes["membership"],
        "signup": outcomes["signup"],
        "churn": outcomes["churn"],
        "revenue_gap": {
            "price_a": float(gap_row.best_price),
            "price_b": float(gap_row.runner_up),
            "estimate": float(gap_row.gap_vs_runner_up),
            "se": float(gap_row.gap_se),
        },
    }


def _list_block() -> dict:
    estimates = pd.read_csv(LIST_ESTIMATES)
    extensions = pd.read_csv(LIST_EXTENSIONS)

    counterfactual = _one(
        estimates[
            (estimates["spec"] == "breakeven")
            & (estimates["term"] == "counterfactual_rate")
        ],
        "counterfactual sign-up rate",
    )
    pretrend = _one(
        estimates[
            (estimates["spec"] == "pretrend")
            & (estimates["outcome"] == "signup")
            & (estimates["term"] == "pre_event_joint")
        ],
        "sign-up pre-trend test",
    )
    ratio = _one(
        extensions[
            (extensions["spec"] == "ppml_did")
            & (extensions["outcome"] == "signup")
            & (extensions["term"] == "rate_ratio")
        ],
        "Poisson sign-up rate ratio",
    )
    signup = _one(
        extensions[
            (extensions["spec"] == "reproduce")
            & (extensions["outcome"] == "signup")
            & (extensions["term"] == "treated_post")
        ],
        "observed sign-up lift",
    )
    acquisition = _one(
        extensions[
            (extensions["spec"] == "reproduce")
            & (extensions["outcome"] == "revenue")
            & (extensions["term"] == "treated_post")
        ],
        "observed acquisition revenue",
    )
    all_revenue = _one(
        extensions[
            (extensions["spec"] == "all_customers_did")
            & (extensions["outcome"] == "revenue")
        ],
        "observed all-customer revenue",
    )
    membership = _one(
        extensions[
            (extensions["spec"] == "all_customers_did")
            & (extensions["outcome"] == "member")
        ],
        "observed membership lift",
    )
    published_ratio = round(float(ratio.estimate), 2)
    if published_ratio != PUBLISHED_RATE_RATIO:
        raise SystemExit(
            f"Poisson rate ratio rounds to {published_ratio}, not {PUBLISHED_RATE_RATIO}"
        )
    return {
        "counterfactual_signup": float(counterfactual.estimate),
        "poisson_rate_ratio": PUBLISHED_RATE_RATIO,
        "poisson_rate_ratio_unrounded": float(ratio.estimate),
        "comparison_price": 15,
        "observed_price": 12,
        "observed_signup_lift": float(signup.estimate),
        "observed_signup_se": float(signup.se),
        "observed_acquisition_revenue_lift": float(acquisition.estimate),
        "observed_acquisition_revenue_se": float(acquisition.se),
        "observed_all_revenue_lift": float(all_revenue.estimate),
        "observed_all_revenue_se": float(all_revenue.se),
        "observed_membership_lift": float(membership.estimate),
        "observed_membership_se": float(membership.se),
        "n_acquisition": int(signup.n),
        "n_all": int(all_revenue.n),
        "revenue_per_member_before": REVENUE_PER_MEMBER_BEFORE,
        "revenue_per_member_after": REVENUE_PER_MEMBER_AFTER,
        "pretrend_chi2": float(pretrend.stat),
        "pretrend_df": int(pretrend.df),
        "offer_groups": _saved_offer_groups(),
    }


def _saved_offer_groups() -> dict:
    """Lapsed-plus-new comparisons, list price only and including promos."""
    _require(OFFER_GROUPS)
    payload = json.loads(OFFER_GROUPS.read_text())
    required = (
        "signup_baseline",
        "signup_lift",
        "signup_se",
        "revenue_baseline",
        "revenue_lift",
        "revenue_se",
        "n",
    )
    if not isinstance(payload, dict):
        raise SystemExit("offer_groups.json must be an object")
    for name in ("acquisition", "acquisition_promo"):
        entry = payload.get(name)
        if not isinstance(entry, dict) or any(field not in entry for field in required):
            raise SystemExit(f"offer_groups.json is missing {name}")
    return payload


def _type_block(frame: pd.DataFrame) -> dict:
    """Lapsed and new curves. A gap whose 95% interval includes zero is a tie."""
    types = {
        era: {name: {"best_dollars": dollars} for name, dollars in groups.items()}
        for era, groups in TYPE_BEST.items()
    }
    for user_type in CURVE_TYPES:
        for era in REQUIRED_ERAS:
            rows = frame[(frame["user_type"] == user_type) & (frame["era"] == era)]
            if rows.empty:
                raise SystemExit(f"Type curve is missing {user_type} {era}")
            rows = rows.sort_values("price")
            points = []
            for row in rows.itertuples(index=False):
                price = float(row.price)
                rate = float(row.adj_rate)
                revenue = float(row.adj_revenue)
                if abs(revenue - rate * price) > 1e-6:
                    raise SystemExit(
                        f"{user_type} {era} ${price:g}: revenue is not rate times price"
                    )
                points.append(
                    {
                        "price": price,
                        "rate": rate,
                        "rate_se": float(row.adj_se),
                        "revenue": revenue,
                        "revenue_se": float(row.adj_revenue_se),
                        "n": int(row.n),
                    }
                )
            gap = float(rows["gap_vs_runner_up"].iloc[0])
            gap_se = float(rows["gap_se"].iloc[0])
            best = float(rows["best_price"].iloc[0])
            runner = float(rows["runner_up"].iloc[0])
            low, high = gap - 1.96 * gap_se, gap + 1.96 * gap_se
            if low <= 0 <= high:
                dollars = sorted((best, runner))
            else:
                dollars = [best]
            published = types[era][user_type]["best_dollars"]
            if dollars != [float(price) for price in published]:
                raise SystemExit(
                    f"{user_type} {era}: curve peak {dollars} does not match "
                    f"published best dollars {published}"
                )
            types[era][user_type]["points"] = points
            types[era][user_type]["revenue_gap"] = {
                "price_a": best,
                "price_b": runner,
                "estimate": gap,
                "se": gap_se,
            }
    return types


def build() -> dict:
    for path in (PROMO_CSV, LIST_ESTIMATES, LIST_EXTENSIONS, TYPE_CURVES, OFFER_GROUPS):
        _require(path)
    promo = pd.read_csv(PROMO_CSV)
    missing = [era for era in REQUIRED_ERAS if era not in set(promo["era"])]
    if missing:
        raise SystemExit(f"Promo table is missing eras: {missing}")
    return {
        "promo": {era: _promo_block(promo, era) for era in REQUIRED_ERAS},
        "types": _type_block(pd.read_csv(TYPE_CURVES)),
        "list_price": _list_block(),
    }


def main() -> None:
    payload = build()
    if OUT_PATH.exists():
        previous = json.loads(OUT_PATH.read_text())
        groups = previous.get("list_price", {}).get("groups")
        if isinstance(groups, dict):
            payload["list_price"]["groups"] = groups
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise
