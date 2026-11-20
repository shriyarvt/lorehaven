"""Save the two lapsed-plus-new list-price comparisons.

One sample is people paying list price. The other is the same people,
including those who were offered a promo. Both use the headline
difference-in-differences. The script stops if a result does not round
to the published table.

    python analysis/fit_offer_groups.py

Run from the repo root. Writes output/list_price/offer_groups.json and
adds that table to lorehaven_sim/data/estimates.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np

SIM_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from submission.list_price import _fit, did_design, load  # noqa: E402

PARQUET = REPO_ROOT / "output" / "flow" / "customer_season.parquet"
OUT = REPO_ROOT / "output" / "list_price" / "offer_groups.json"
ESTIMATES = SIM_ROOT / "data" / "estimates.json"

# Published rounding from the list-price results table.
EXPECTED = {
    "acquisition": {
        "signup_baseline": 8.62,
        "signup_lift": 3.54,
        "signup_ci": (3.45, 3.63),
        "revenue_baseline": 1.29,
        "revenue_lift": 0.348,
        "revenue_ci": (0.335, 0.360),
        "n": 4_032_066,
    },
    "acquisition_promo": {
        "signup_baseline": 8.52,
        "signup_lift": 4.32,
        "signup_ci": (4.23, 4.42),
        "revenue_baseline": 1.26,
        "revenue_lift": 0.337,
        "revenue_ci": (0.325, 0.349),
    },
}


def _with_promo():
    """At-risk customers, including promo offers, spring 2017 through fall 2019."""
    frame = duckdb.connect().execute(
        f"""
        SELECT
          p.customer_id,
          lower(p.region_name) AS region_name,
          p.season_index,
          CASE WHEN p.treated_region THEN 1 ELSE 0 END AS treated,
          CASE WHEN p.era = 'post' THEN 1 ELSE 0 END AS post,
          CAST(p.new_signup AS INTEGER) AS signup,
          CAST(p.new_signup AS INTEGER) * p.membership_price AS revenue
        FROM read_parquet('{PARQUET}') p
        WHERE p.at_risk = TRUE
          AND p.season_index > {2017 * 4}
        ORDER BY p.customer_id
        """
    ).fetchdf()
    frame["region_name"] = frame["region_name"].astype("string")
    return frame


def _fit_group(frame) -> dict:
    customer = frame["customer_id"].to_numpy()
    design, names = did_design(frame)
    intercept = names.index("intercept")
    treated_post = names.index("treated_post")
    row = {"n": int(len(frame))}
    for outcome, prefix in (("signup", "signup"), ("revenue", "revenue")):
        y = frame[outcome].to_numpy(dtype=np.float64)
        fit = _fit(y, design, customer, names)
        row[f"{prefix}_baseline"] = float(fit["beta"][intercept])
        row[f"{prefix}_lift"] = float(fit["beta"][treated_post])
        row[f"{prefix}_se"] = float(fit["se"][treated_post])
    return row


def _matches(name: str, row: dict) -> None:
    expected = EXPECTED[name]
    signup_low = (row["signup_lift"] - 1.96 * row["signup_se"]) * 100
    signup_high = (row["signup_lift"] + 1.96 * row["signup_se"]) * 100
    revenue_low = row["revenue_lift"] - 1.96 * row["revenue_se"]
    revenue_high = row["revenue_lift"] + 1.96 * row["revenue_se"]
    got = {
        "signup_baseline": round(row["signup_baseline"] * 100, 2),
        "signup_lift": round(row["signup_lift"] * 100, 2),
        "signup_ci": (round(signup_low, 2), round(signup_high, 2)),
        "revenue_baseline": round(row["revenue_baseline"], 2),
        "revenue_lift": round(row["revenue_lift"], 3),
        "revenue_ci": (round(revenue_low, 3), round(revenue_high, 3)),
    }
    if "n" in expected:
        got["n"] = row["n"]
    for field, value in got.items():
        if value != expected[field]:
            raise SystemExit(f"{name} {field} is {value}, not {expected[field]}")


def main() -> None:
    groups = {
        "acquisition": _fit_group(load()),
        "acquisition_promo": _fit_group(_with_promo()),
    }
    for name, row in groups.items():
        _matches(name, row)
    stored = json.loads(ESTIMATES.read_text())
    listing = stored["list_price"]
    no_promo = groups["acquisition"]
    for field, key in (
        ("signup_lift", "observed_signup_lift"),
        ("signup_se", "observed_signup_se"),
        ("revenue_lift", "observed_acquisition_revenue_lift"),
        ("revenue_se", "observed_acquisition_revenue_se"),
    ):
        if abs(no_promo[field] - float(listing[key])) > 1e-12:
            raise SystemExit(f"No-promo {field} does not match the saved list-price lift")
    if no_promo["n"] != int(listing["n_acquisition"]):
        raise SystemExit("No-promo sample size does not match n_acquisition")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(groups, indent=2) + "\n")
    listing["offer_groups"] = groups
    ESTIMATES.write_text(json.dumps(stored, indent=2) + "\n")
    print(f"Wrote {OUT}")
    print(f"Updated {ESTIMATES}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise
