"""Fit the lapsed and new promo curves and save them.

The published type table is the clustered mean at each dollar, not the
region-and-season adjustment. Those means match Table 3 to the published
rounding, including the lead and its standard error. Revenue is the
membership rate times the offer. The script stops if the sample size or a
published peak does not match.

    python analysis/fit_type_curves.py

Run from lorehaven_sim. Writes output/discount/type_curves.csv.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

SIM_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SIM_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from submission.discount_price import _fit, linear_rates  # noqa: E402

PARQUET = REPO_ROOT / "output" / "flow" / "customer_season.parquet"
OUT = REPO_ROOT / "output" / "discount" / "type_curves.csv"

# Published sample sizes and this-season peaks. Revenue and the lead are
# rounded to three decimals in the promo write-up.
EXPECTED_N = {
    ("lapsed", "pre"): 39_060,
    ("lapsed", "post"): 29_496,
    ("new", "pre"): 597_585,
    ("new", "post"): 171_312,
}
EXPECTED_REVENUE = {
    ("lapsed", "pre", 10): 4.044,
    ("lapsed", "post", 7): 3.625,
    ("lapsed", "post", 8): 3.727,
    ("new", "pre", 10): 1.582,
    ("new", "post", 7): 1.443,
}
EXPECTED_GAP = {
    ("lapsed", "pre"): (0.327, 0.081),
    ("lapsed", "post"): (0.102, 0.069),
    ("new", "pre"): (0.245, 0.015),
    ("new", "post"): (0.164, 0.022),
}


def load_types() -> pd.DataFrame:
    """Promo offers with a known prior season, labeled lapsed or new.

    Earlier membership is read from the full panel. A full-price season still
    counts as having been a member. Recurring customers are the churn sample
    and are not refit here.
    """
    if not PARQUET.is_file():
        raise SystemExit(f"Missing input file: {PARQUET}")
    frame = duckdb.connect().execute(
        f"""
        WITH history AS (
          SELECT
            customer_id,
            region_name,
            season_index,
            era,
            CAST(membership_price AS INTEGER) AS price,
            CAST(sign_up_flag AS INTEGER) AS member,
            CAST(prev_member AS INTEGER) AS prev_member,
            discount_flag,
            MAX(CAST(sign_up_flag AS INTEGER)) OVER (
              PARTITION BY customer_id
              ORDER BY season_index
              ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS ever_before
          FROM read_parquet('{PARQUET.as_posix()}')
        )
        SELECT
          customer_id,
          region_name,
          season_index,
          era,
          price,
          member,
          CASE
            WHEN prev_member = 0 AND ever_before = 1 THEN 'lapsed'
            WHEN prev_member = 0 AND COALESCE(ever_before, 0) = 0 THEN 'new'
          END AS user_type
        FROM history
        WHERE discount_flag = 1
          AND prev_member = 0
          AND era IS NOT NULL
        """
    ).fetchdf()
    frame["region_name"] = frame["region_name"].astype("string")
    frame["era"] = frame["era"].astype("string")
    frame["user_type"] = frame["user_type"].astype("string")
    return frame


def _check(table: pd.DataFrame, user_type: str, era: str) -> None:
    label = f"{user_type} {era}"
    counted = int(table["n"].sum())
    expected_n = EXPECTED_N[(user_type, era)]
    if counted != expected_n:
        raise SystemExit(f"{label}: n is {counted:,}, expected {expected_n:,}")
    for (group, period, price), expected in EXPECTED_REVENUE.items():
        if group != user_type or period != era:
            continue
        row = table.loc[table["price"] == price].iloc[0]
        shown = round(float(row["adj_revenue"]), 3)
        if shown != expected:
            raise SystemExit(
                f"{label} ${price}: revenue rounds to {shown}, expected {expected}"
            )
    gap, gap_se = EXPECTED_GAP[(user_type, era)]
    shown_gap = round(abs(float(table["gap_vs_runner_up"].iloc[0])), 3)
    shown_se = round(float(table["gap_se"].iloc[0]), 3)
    if (shown_gap, shown_se) != (gap, gap_se):
        raise SystemExit(
            f"{label}: lead rounds to {shown_gap} ± {shown_se}, expected {gap} ± {gap_se}"
        )


def fit(frame: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for user_type in ("lapsed", "new"):
        for era in ("pre", "post"):
            sample = frame[(frame["user_type"] == user_type) & (frame["era"] == era)]
            sample = sample.reset_index(drop=True)
            prices = sorted(int(price) for price in sample["price"].unique())
            print(f"{user_type} {era}: {len(sample):,} rows, prices {prices}", flush=True)
            fitted = _fit("member ~ C(price)", sample)
            table = linear_rates(fitted, sample, prices).rename(
                columns={
                    "rate": "adj_rate",
                    "se": "adj_se",
                    "revenue": "adj_revenue",
                    "revenue_se": "adj_revenue_se",
                }
            )
            _check(table, user_type, era)
            table.insert(0, "user_type", user_type)
            table.insert(1, "era", era)
            pieces.append(table)
            best = int(table["best_price"].iloc[0])
            print(f"  peak ${best}, lead {table['gap_vs_runner_up'].iloc[0]:.4f}", flush=True)
    return pd.concat(pieces, ignore_index=True)


def main() -> None:
    estimates = fit(load_types())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    estimates.to_csv(OUT, index=False)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
