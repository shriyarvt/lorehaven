"""List-price difference-in-differences: the spring 2019 cut from $15 to $12.

The sample is people who were not members last season and who were not offered
a promo. In the five discount regions that group pays list price. Panem stays
at $15 and never has a promo. Winter 2017 has no prior season, so it is out.
Winter 2019 is the last $15 season. The pre-trend test omits that season and
jointly tests the earlier five-region gaps.

    .venv/bin/python submission/list_price.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "list_price"
PARQUET = ROOT / "output" / "flow" / "customer_season.parquet"
AGGREGATE = ROOT / "data" / "aggregate.csv"

REF = 2019 * 4  # winter 2019, the last season before the cut
SEASON_NAME = {0: "winter", 1: "spring", 2: "summer", 3: "fall"}


# Turn a season index into a year and season name, such as "2019 spring".
def season_label(index: int) -> str:
    return f"{index // 4} {SEASON_NAME[index % 4]}"


def load() -> pd.DataFrame:
    """At-risk customers paying list price, spring 2017 through fall 2019."""
    con = duckdb.connect()
    frame = con.execute(
        f"""
        SELECT
          p.customer_id,
          lower(p.region_name) AS region_name,
          p.season_index,
          p.year,
          lower(p.season) AS season,
          CASE WHEN p.treated_region THEN 1 ELSE 0 END AS treated,
          CASE WHEN p.era = 'post' THEN 1 ELSE 0 END AS post,
          CAST(p.new_signup AS INTEGER) AS signup,
          CAST(p.new_signup AS INTEGER) * p.membership_price AS revenue,
          p.membership_price AS price,
          a.tv_ratings,
          a.search_impressions,
          a.podcast_ad_listens
        FROM read_parquet('{PARQUET}') p
        LEFT JOIN read_csv_auto('{AGGREGATE}') a
          ON lower(p.region_name) = lower(a.region_name)
         AND p.year = a.year
         AND lower(p.season) = lower(a.season)
        WHERE p.at_risk = TRUE
          AND p.discount_flag = 0
          AND p.season_index > {2017 * 4}
        ORDER BY p.customer_id
        """
    ).fetchdf()
    if frame[["tv_ratings", "search_impressions", "podcast_ad_listens"]].isna().any().any():
        raise ValueError("Aggregate exposure did not match every region-season.")
    frame["region_name"] = frame["region_name"].astype("string")
    return frame


def _fit(y: np.ndarray, x: np.ndarray, customer: np.ndarray, names: list[str]) -> dict:
    """OLS with standard errors clustered by customer.

    The scale factor matches statsmodels: G/(G-1) times (N-1)/(N-K).
    ``customer`` must be sorted so each customer's rows are contiguous.
    """
    if np.any(customer[1:] < customer[:-1]):
        raise ValueError("customer_id must be sorted before clustering.")
    xtx = x.T @ x
    xty = x.T @ y
    beta = np.linalg.solve(xtx, xty)
    resid = y - x @ beta
    starts = np.r_[0, np.flatnonzero(np.diff(customer)) + 1]
    grouped = np.add.reduceat(x * resid[:, None], starts, axis=0)
    meat = grouped.T @ grouped
    bread = np.linalg.inv(xtx)
    n_obs, k = x.shape
    n_groups = int(starts.size)
    scale = (n_groups / (n_groups - 1)) * ((n_obs - 1) / (n_obs - k))
    cov = bread @ (scale * meat) @ bread
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    return {
        "names": names,
        "beta": beta,
        "se": se,
        "cov": cov,
        "n": n_obs,
        "customers": n_groups,
    }


# Turn a true/false mask into a 0/1 regressor column.
def _column(mask: np.ndarray) -> np.ndarray:
    return mask.astype(np.float64)


# Intercept, region dummies, and season dummies. Panem and winter 2019 are omitted.
def _base_columns(frame: pd.DataFrame) -> tuple[list[np.ndarray], list[str], list[int]]:
    region = frame["region_name"].to_numpy()
    season = frame["season_index"].to_numpy()
    regions = [name for name in sorted(pd.unique(region)) if name != "panem"]
    seasons = [int(s) for s in sorted(pd.unique(season)) if int(s) != REF]
    columns = [np.ones(len(frame))]
    names = ["intercept"]
    for name in regions:
        columns.append(_column(region == name))
        names.append(f"region_{name}")
    for index in seasons:
        columns.append(_column(season == index))
        names.append(f"season_{index}")
    return columns, names, seasons


# Add a treated-by-season term for every season except winter 2019.
def event_design(frame: pd.DataFrame) -> tuple[np.ndarray, list[str], list[int]]:
    columns, names, seasons = _base_columns(frame)
    treated = frame["treated"].to_numpy() == 1
    season = frame["season_index"].to_numpy()
    for index in seasons:
        columns.append(_column(treated & (season == index)))
        names.append(f"event_{index}")
    return np.column_stack(columns), names, seasons


# Add one treated-by-post term, and optional region-season exposure controls.
def did_design(frame: pd.DataFrame, exposure: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    columns, names, _seasons = _base_columns(frame)
    did = (frame["treated"].to_numpy() == 1) & (frame["post"].to_numpy() == 1)
    columns.append(_column(did))
    names.append("treated_post")
    if exposure:
        for name in exposure:
            values = frame[name].to_numpy(dtype=np.float64)
            scale = float(values.std())
            if scale == 0:
                raise ValueError(f"{name} does not vary in this sample.")
            columns.append((values - values.mean()) / scale)
            names.append(name)
    return np.column_stack(columns), names


# Turn selected coefficients into estimate rows with 95% intervals.
def _term_rows(spec: str, outcome: str, fit: dict, terms: list[str], note: str) -> list[dict]:
    rows = []
    index = {name: i for i, name in enumerate(fit["names"])}
    for term in terms:
        i = index[term]
        estimate = float(fit["beta"][i])
        se = float(fit["se"][i])
        rows.append(
            {
                "spec": spec,
                "outcome": outcome,
                "term": term,
                "estimate": estimate,
                "se": se,
                "ci_low": estimate - 1.96 * se,
                "ci_high": estimate + 1.96 * se,
                "stat": np.nan,
                "df": np.nan,
                "pvalue": np.nan,
                "n": fit["n"],
                "customers": fit["customers"],
                "note": note,
            }
        )
    return rows


# Joint test that the named coefficients are all zero.
def wald_zero(fit: dict, terms: list[str]) -> tuple[float, int, float]:
    index = {name: i for i, name in enumerate(fit["names"])}
    picked = [index[term] for term in terms]
    r = np.zeros((len(picked), len(fit["beta"])))
    for row, col in enumerate(picked):
        r[row, col] = 1.0
    gap = r @ fit["beta"]
    middle = r @ fit["cov"] @ r.T
    stat = float(gap @ np.linalg.solve(middle, gap))
    df = len(picked)
    pvalue = float(stats.chi2.sf(stat, df))
    return stat, df, pvalue


def counterfactual_rate(frame: pd.DataFrame, fit: dict) -> float:
    """Mean sign-up rate on post-cut treated rows if the cut term is zero."""
    x, names = did_design(frame)
    if names != fit["names"]:
        raise ValueError("Counterfactual design does not match the fitted model.")
    post_treated = (frame["treated"].to_numpy() == 1) & (frame["post"].to_numpy() == 1)
    x = x.copy()
    x[:, names.index("treated_post")] = 0.0
    return float((x[post_treated] @ fit["beta"]).mean())


# Season-level sign-up and revenue means for the five regions and for Panem.
def raw_series(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        frame.groupby(["season_index", "year", "season", "treated"], sort=True)
        .agg(n=("signup", "size"), signup=("signup", "mean"), revenue=("revenue", "mean"), price=("price", "mean"))
        .reset_index()
    )
    grouped["group"] = np.where(grouped["treated"] == 1, "treated", "panem")
    return grouped


# Fit the headline difference-in-differences and the joint pre-trend test.
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame = load()
    customer = frame["customer_id"].to_numpy()
    exposure = ["search_impressions", "tv_ratings", "podcast_ad_listens"]
    rows: list[dict] = []

    series = raw_series(frame)
    for record in series.itertuples(index=False):
        for outcome, estimate in (("signup", record.signup), ("revenue", record.revenue)):
            rows.append(
                {
                    "spec": "raw_season",
                    "outcome": outcome,
                    "term": f"{record.group}_{int(record.season_index)}",
                    "estimate": float(estimate),
                    "se": np.nan,
                    "ci_low": np.nan,
                    "ci_high": np.nan,
                    "stat": np.nan,
                    "df": np.nan,
                    "pvalue": np.nan,
                    "n": int(record.n),
                    "customers": np.nan,
                    "note": f"{record.year} {record.season}, price ${record.price:.0f}",
                }
            )

    outcomes = {"signup": frame["signup"].to_numpy(dtype=np.float64), "revenue": frame["revenue"].to_numpy(dtype=np.float64)}
    event_x, event_names, event_seasons = event_design(frame)
    pre_terms = [f"event_{index}" for index in event_seasons if index < REF]
    for outcome, y in outcomes.items():
        fit = _fit(y, event_x, customer, event_names)
        stat, df, pvalue = wald_zero(fit, pre_terms)
        rows.append(
            {
                "spec": "pretrend",
                "outcome": outcome,
                "term": "pre_event_joint",
                "estimate": np.nan,
                "se": np.nan,
                "ci_low": np.nan,
                "ci_high": np.nan,
                "stat": stat,
                "df": df,
                "pvalue": pvalue,
                "n": fit["n"],
                "customers": fit["customers"],
                "note": "Joint test that every pre-cut treated-by-season gap is zero.",
            }
        )

    did_fits = {}
    did_x, did_names = did_design(frame)
    for outcome, y in outcomes.items():
        fit = _fit(y, did_x, customer, did_names)
        did_fits[outcome] = fit
        rows.extend(_term_rows("did", outcome, fit, ["treated_post"], "Treated regions from spring 2019 on, versus Panem."))

    rate_cf = counterfactual_rate(frame, did_fits["signup"])
    signup_gain = float(did_fits["signup"]["beta"][did_names.index("treated_post")])
    needed = 0.25 * rate_cf
    rows.append(
        {
            "spec": "breakeven",
            "outcome": "signup",
            "term": "counterfactual_rate",
            "estimate": rate_cf,
            "se": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
            "stat": np.nan,
            "df": np.nan,
            "pvalue": np.nan,
            "n": did_fits["signup"]["n"],
            "customers": did_fits["signup"]["customers"],
            "note": "Predicted post-cut sign-up rate in the five regions if the cut term is zero.",
        }
    )
    rows.append(
        {
            "spec": "breakeven",
            "outcome": "signup",
            "term": "gain_needed_for_15",
            "estimate": needed,
            "se": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
            "stat": signup_gain - needed,
            "df": np.nan,
            "pvalue": np.nan,
            "n": did_fits["signup"]["n"],
            "customers": did_fits["signup"]["customers"],
            "note": "Sign-up gain, in rate points, required so $12 matches $15 revenue. stat is estimated gain minus this hurdle.",
        }
    )

    exposure_x, exposure_names = did_design(frame, exposure)
    for outcome, y in outcomes.items():
        fit = _fit(y, exposure_x, customer, exposure_names)
        rows.extend(
            _term_rows(
                "did_exposure",
                outcome,
                fit,
                ["treated_post"],
                "Headline model plus search impressions, TV ratings, and podcast listens. Spend is not included.",
            )
        )

    no_westeros = frame[frame["region_name"] != "westeros"].reset_index(drop=True)
    no_westeros_customer = no_westeros["customer_id"].to_numpy()
    drop_x, drop_names = did_design(no_westeros)
    for outcome in outcomes:
        y = no_westeros[outcome].to_numpy(dtype=np.float64)
        fit = _fit(y, drop_x, no_westeros_customer, drop_names)
        rows.extend(
            _term_rows(
                "did_no_westeros",
                outcome,
                fit,
                ["treated_post"],
                "Headline model without Westeros. Its TV ratings are zero in three winters.",
            )
        )

    estimates = pd.DataFrame(rows)
    estimates.to_csv(OUT / "estimates.csv", index=False)

    def show(spec: str, outcome: str, term: str) -> None:
        hit = estimates[(estimates["spec"] == spec) & (estimates["outcome"] == outcome) & (estimates["term"] == term)].iloc[0]
        print(
            f"{spec} {outcome} {term}: estimate={hit['estimate']:.6f} se={hit['se']} "
            f"ci=[{hit['ci_low']}, {hit['ci_high']}] p={hit['pvalue']} stat={hit['stat']} df={hit['df']}"
        )

    for outcome in ("signup", "revenue"):
        show("pretrend", outcome, "pre_event_joint")
        show("did", outcome, "treated_post")
        show("did_exposure", outcome, "treated_post")
        show("did_no_westeros", outcome, "treated_post")
    show("breakeven", "signup", "counterfactual_rate")
    show("breakeven", "signup", "gain_needed_for_15")
    print(f"wrote {OUT / 'estimates.csv'}")


if __name__ == "__main__":
    main()
