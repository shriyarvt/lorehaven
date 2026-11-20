"""Further checks on the spring 2019 list-price cut.

Step 0 rebuilds the published at-risk, no-promo sample and stops if the
headline does not match. Later steps add recurring members, leave-one-region-out,
a Poisson rate ratio, and a comparison
with the randomized promo elasticities.

    .venv/bin/python list_price_extensions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "submission"))
import list_price as lp

OUT = ROOT / "output" / "list_price" / "extensions"
PARQUET = ROOT / "output" / "flow" / "customer_season.parquet"
AGGREGATE = ROOT / "data" / "aggregate.csv"
PROPENSITY = ROOT / "data" / "customer_propensities.csv"

REF = lp.REF
PRE_SEASONS = list(range(2017 * 4 + 1, REF + 1))


def _row(step, spec, outcome, term, fit, note, estimate=np.nan, se=np.nan, stat=np.nan, df=np.nan, pvalue=np.nan, n=np.nan, customers=np.nan):
    if fit is not None and term in fit["names"]:
        i = fit["names"].index(term)
        estimate = float(fit["beta"][i])
        se = float(fit["se"][i])
        n = fit["n"]
        customers = fit["customers"]
    return {
        "step": step,
        "spec": spec,
        "outcome": outcome,
        "term": term,
        "estimate": estimate,
        "se": se,
        "ci_low": estimate - 1.96 * se if np.isfinite(se) else np.nan,
        "ci_high": estimate + 1.96 * se if np.isfinite(se) else np.nan,
        "stat": stat,
        "df": df,
        "pvalue": pvalue,
        "n": n,
        "customers": customers,
        "note": note,
    }


def coef(fit, term):
    i = fit["names"].index(term)
    return float(fit["beta"][i]), float(fit["se"][i])


def load_acquisition() -> pd.DataFrame:
    con = duckdb.connect()
    frame = con.execute(
        f"""
        WITH base AS (
          SELECT
            customer_id,
            lower(region_name) AS region_name,
            season_index,
            year,
            lower(season) AS season,
            CASE WHEN treated_region THEN 1 ELSE 0 END AS treated,
            CASE WHEN era = 'post' THEN 1 ELSE 0 END AS post,
            CAST(new_signup AS INTEGER) AS signup,
            CAST(new_signup AS INTEGER) * membership_price AS revenue,
            membership_price AS price,
            MAX(sign_up_flag) OVER (
              PARTITION BY customer_id ORDER BY season_index
              ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS ever_member,
            SUM(sign_up_flag) OVER (
              PARTITION BY customer_id ORDER BY season_index
              ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS prior_member_seasons
          FROM read_parquet('{PARQUET}')
          WHERE at_risk = TRUE AND discount_flag = 0 AND season_index > {2017 * 4}
        )
        SELECT
          b.*,
          CASE WHEN b.ever_member = 1 THEN 'lapsed' ELSE 'new' END AS user_type,
          p.customer_tv_score, p.customer_radio_score, p.customer_social_score,
          p.customer_podcast_score, p.customer_display_score,
          a.tv_ratings, a.radio_ratings, a.search_impressions, a.social_impressions,
          a.podcast_ad_listens, a.display_impressions
        FROM base b
        LEFT JOIN read_csv_auto('{PROPENSITY}') p
          ON b.customer_id = p.customer_id AND b.year = p.year + 1
        LEFT JOIN read_csv_auto('{AGGREGATE}') a
          ON b.region_name = lower(a.region_name)
         AND b.year = a.year AND b.season = lower(a.season)
        ORDER BY b.customer_id
        """
    ).fetchdf()
    frame["region_name"] = frame["region_name"].astype("string")
    frame["user_type"] = frame["user_type"].astype("string")
    return frame


def load_everyone() -> pd.DataFrame:
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
          CAST(p.sign_up_flag AS INTEGER) AS member,
          CAST(p.sign_up_flag AS INTEGER) * p.membership_price AS revenue,
          p.membership_price AS price,
          a.tv_ratings, a.radio_ratings, a.search_impressions, a.social_impressions,
          a.podcast_ad_listens, a.display_impressions
        FROM read_parquet('{PARQUET}') p
        LEFT JOIN read_csv_auto('{AGGREGATE}') a
          ON lower(p.region_name) = lower(a.region_name)
         AND p.year = a.year AND lower(p.season) = lower(a.season)
        WHERE p.season_index > {2017 * 4}
        ORDER BY p.customer_id
        """
    ).fetchdf()
    frame["region_name"] = frame["region_name"].astype("string")
    return frame


def did_fit(frame: pd.DataFrame, outcome: str, exposure: list[str] | None = None):
    y = frame[outcome].to_numpy(dtype=np.float64)
    customer = frame["customer_id"].to_numpy()
    x, names = lp.did_design(frame, exposure)
    return lp._fit(y, x, customer, names)


def soy_design(frame: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Region-by-season-of-year effects, year effects, and one treated-by-post term.

    Panem in winter and the year 2017 are the omitted cells.
    """
    region = frame["region_name"].to_numpy()
    soy = (frame["season_index"].to_numpy() % 4).astype(int)
    year = frame["year"].to_numpy()
    columns = [np.ones(len(frame))]
    names = ["intercept"]
    for name in sorted(pd.unique(region)):
        for season_of_year in range(4):
            if name == "panem" and season_of_year == 0:
                continue
            columns.append(((region == name) & (soy == season_of_year)).astype(np.float64))
            names.append(f"soy_{name}_{season_of_year}")
    for value in sorted(pd.unique(year)):
        if int(value) == 2017:
            continue
        columns.append((year == value).astype(np.float64))
        names.append(f"year_{int(value)}")
    did = ((frame["treated"].to_numpy() == 1) & (frame["post"].to_numpy() == 1)).astype(np.float64)
    columns.append(did)
    names.append("treated_post")
    kept = [i for i, column in enumerate(columns) if i == 0 or float(np.max(np.abs(column))) > 0]
    return np.column_stack([columns[i] for i in kept]), [names[i] for i in kept]


def soy_did(frame: pd.DataFrame, outcome: str):
    """Treated-by-post with region-specific season-of-year effects and year effects."""
    y = frame[outcome].to_numpy(dtype=np.float64)
    customer = frame["customer_id"].to_numpy()
    x, names = soy_design(frame)
    return lp._fit(y, x, customer, names)


def ppml(y, x, customer, names, max_iter=30):
    """Poisson pseudo-likelihood with customer-clustered standard errors."""
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    mu = None
    for _ in range(max_iter):
        eta = np.clip(x @ beta, -20, 20)
        mu = np.exp(eta)
        z = eta + (y - mu) / np.maximum(mu, 1e-12)
        weighted = x * mu[:, None]
        beta_new = np.linalg.solve(x.T @ weighted, x.T @ (mu * z))
        if np.max(np.abs(beta_new - beta)) < 1e-8:
            beta = beta_new
            break
        beta = beta_new
    eta = np.clip(x @ beta, -20, 20)
    mu = np.exp(eta)
    weighted = x * mu[:, None]
    bread = np.linalg.inv(x.T @ weighted)
    starts = np.r_[0, np.flatnonzero(np.diff(customer)) + 1]
    scores = np.add.reduceat(x * (y - mu)[:, None], starts, axis=0)
    meat = scores.T @ scores
    n_obs, k = x.shape
    n_groups = int(starts.size)
    scale = (n_groups / (n_groups - 1)) * ((n_obs - 1) / (n_obs - k))
    cov = bread @ (scale * meat) @ bread
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    return {"names": names, "beta": beta, "se": se, "cov": cov, "n": n_obs, "customers": n_groups}


def member_count_gap() -> float:
    con = duckdb.connect()
    gap = con.execute(
        f"""
        WITH panel AS (
          SELECT lower(region_name) AS region_name, year, lower(season) AS season,
                 SUM(sign_up_flag) AS panel_members
          FROM read_parquet('{PARQUET}')
          GROUP BY 1, 2, 3
        )
        SELECT MAX(ABS(panel_members - member_count)) AS gap
        FROM panel p
        JOIN read_csv_auto('{AGGREGATE}') a
          ON p.region_name = lower(a.region_name)
         AND p.year = a.year AND p.season = lower(a.season)
        """
    ).fetchone()[0]
    return float(gap)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    print("STEP 0 reproduce")
    acquisition = load_acquisition()
    n = len(acquisition)
    customers = int(acquisition["customer_id"].nunique())
    if n != 4_032_066 or customers != 504_622:
        sys.exit(f"STOP sample mismatch: N={n:,} customers={customers:,}, expected 4,032,066 and 504,622")
    signup_fit = did_fit(acquisition, "signup")
    revenue_fit = did_fit(acquisition, "revenue")
    signup_b, signup_se = coef(signup_fit, "treated_post")
    revenue_b, revenue_se = coef(revenue_fit, "treated_post")
    if abs(signup_b * 100 - 3.54) > 0.01 or abs(revenue_b - 0.348) > 0.001:
        sys.exit(
            "STOP headline mismatch: "
            f"signup {signup_b * 100:.4f} pp (se {signup_se:.6f}), "
            f"revenue {revenue_b:.4f} (se {revenue_se:.6f})"
        )
    print(f"reproduced N={n:,} customers={customers:,} signup={signup_b*100:.2f} pp revenue=${revenue_b:.3f}")
    rows.append(_row("0", "reproduce", "signup", "treated_post", signup_fit, "Matches the published headline."))
    rows.append(_row("0", "reproduce", "revenue", "treated_post", revenue_fit, "Matches the published headline."))

    print("STEP 1 all customers")
    everyone = load_everyone()
    gap = member_count_gap()
    rows.append(_row("1", "reconcile", "member_count", "max_abs_gap", None, "Panel stock versus aggregate.csv member_count.", estimate=gap, n=int(everyone.shape[0])))
    if abs(gap) > 1e-6:
        sys.exit(f"STOP member_count does not match the panel. Max gap {gap}.")
    for outcome in ("revenue", "member"):
        fit = did_fit(everyone, outcome)
        rows.append(_row("1", "all_customers_did", outcome, "treated_post", fit, "Every customer, spring 2017–fall 2019. Includes recurring members."))
        post_treated = (everyone["treated"] == 1) & (everyone["post"] == 1)
        total = float(fit["beta"][fit["names"].index("treated_post")]) * int(post_treated.sum())
        rows.append(_row(
            "1", "all_customers_total", outcome, "treated_post_times_post_treated_rows", None,
            "Per-person effect times post-cut customer-seasons in the five regions. Not a new regression.",
            estimate=total, n=int(post_treated.sum()),
        ))
    print("all-customer revenue", coef(did_fit(everyone, "revenue"), "treated_post"))

    print("STEP 2 inference")
    targets = [
        ("acquisition", acquisition, "signup"),
        ("all_customers", everyone, "revenue"),
        ("all_customers", everyone, "member"),
    ]
    pre_only = {name: frame[frame["season_index"] <= REF].copy() for name, frame, _ in [
        ("acquisition", acquisition, "signup"),
        ("all_customers", everyone, "revenue"),
    ]}
    pre_only["all_customers_member"] = everyone[everyone["season_index"] <= REF].copy()
    sample_frames = {
        ("acquisition", "signup"): acquisition,
        ("all_customers", "revenue"): everyone,
        ("all_customers", "member"): everyone,
    }
    for sample_name, outcome in [("acquisition", "signup"), ("all_customers", "revenue"), ("all_customers", "member")]:
        real = signup_b if outcome == "signup" else coef(did_fit(sample_frames[(sample_name, outcome)], outcome), "treated_post")[0]
        # real was just refit for revenue/member above; reuse stored fits when possible
    # Use the fits we already have
    real_fits = {
        ("acquisition", "signup"): signup_fit,
        ("all_customers", "revenue"): did_fit(everyone, "revenue"),
        ("all_customers", "member"): did_fit(everyone, "member"),
    }
    pre_frames = {
        ("acquisition", "signup"): acquisition[acquisition["season_index"] <= REF],
        ("all_customers", "revenue"): everyone[everyone["season_index"] <= REF],
        ("all_customers", "member"): everyone[everyone["season_index"] <= REF],
    }
    for key, real_fit in real_fits.items():
        sample_name, outcome = key
        real_est = coef(real_fit, "treated_post")[0]
        placebo_ests = []
        pre = pre_frames[key]
        for cut in range(PRE_SEASONS[1], REF + 1):
            sample = pre.copy()
            sample["post"] = (sample["season_index"] >= cut).astype(int)
            fit = did_fit(sample, outcome)
            estimate, se = coef(fit, "treated_post")
            placebo_ests.append(estimate)
            rows.append(_row(
                "2", "placebo_in_time", outcome, f"cut_{cut}", None,
                f"{sample_name}. Fake cut at {lp.season_label(cut)}, using only seasons through winter 2019.",
                estimate=estimate, se=se, n=fit["n"], customers=fit["customers"],
            ))
        beats = int(np.sum(np.abs(np.array(placebo_ests)) >= abs(real_est)))
        rows.append(_row(
            "2", "placebo_summary", outcome, "placebos_at_least_as_large", None,
            f"{sample_name}. Count of pre-period placebos with absolute effect at least the real estimate {real_est:.4f}.",
            estimate=beats, stat=len(placebo_ests), n=real_fit["n"], customers=real_fit["customers"],
        ))
        base = sample_frames[key]
        regions = sorted(base["region_name"].unique())
        treated_regions = [name for name in regions if name != "panem"]
        for dropped in treated_regions:
            sample = base[base["region_name"] != dropped]
            fit = did_fit(sample, outcome)
            estimate, se = coef(fit, "treated_post")
            rows.append(_row(
                "2", "leave_one_region_out", outcome, f"drop_{dropped}", None,
                f"{sample_name}. Panem stays the control.",
                estimate=estimate, se=se, n=fit["n"], customers=fit["customers"],
            ))

    print("STEP 3 poisson")
    y_signup = acquisition["signup"].to_numpy(dtype=np.float64)
    customer = acquisition["customer_id"].to_numpy()
    x_did, names_did = lp.did_design(acquisition)
    poisson_did = ppml(y_signup, x_did, customer, names_did)
    b, se = coef(poisson_did, "treated_post")
    rows.append(_row("3", "ppml_did", "signup", "treated_post", poisson_did, "Log coefficient. Rate ratio is exp(estimate)."))
    rows.append(_row(
        "3", "ppml_did", "signup", "rate_ratio", None,
        "exp(treated x post). Break-even versus $15 is a rate ratio of 1.25.",
        estimate=float(np.exp(b)),
        se=float(np.exp(b) * se),
        n=poisson_did["n"], customers=poisson_did["customers"],
    ))

    print("STEP 5 exposure and selection")
    con = duckdb.connect()
    channel_change = con.execute(
        f"""
        SELECT channel, treated_post - treated_pre AS treated_change,
               panem_post - panem_pre AS panem_change,
               (treated_post - treated_pre) - (panem_post - panem_pre) AS differential
        FROM (
          SELECT channel,
                 AVG(CASE WHEN grp = 'treated' AND era = 'pre' THEN value END) AS treated_pre,
                 AVG(CASE WHEN grp = 'treated' AND era = 'post' THEN value END) AS treated_post,
                 AVG(CASE WHEN grp = 'panem' AND era = 'pre' THEN value END) AS panem_pre,
                 AVG(CASE WHEN grp = 'panem' AND era = 'post' THEN value END) AS panem_post
          FROM (
            SELECT CASE WHEN lower(region_name) = 'panem' THEN 'panem' ELSE 'treated' END AS grp,
                   CASE WHEN year < 2019 OR (year = 2019 AND lower(season) = 'winter') THEN 'pre' ELSE 'post' END AS era,
                   channel, value
            FROM (
              SELECT region_name, year, season, 'tv_ratings' AS channel, tv_ratings AS value
              FROM read_csv_auto('{AGGREGATE}')
              WHERE NOT (year = 2017 AND lower(season) = 'winter')
              UNION ALL
              SELECT region_name, year, season, 'radio_ratings', radio_ratings
              FROM read_csv_auto('{AGGREGATE}')
              WHERE NOT (year = 2017 AND lower(season) = 'winter')
              UNION ALL
              SELECT region_name, year, season, 'search_impressions', search_impressions
              FROM read_csv_auto('{AGGREGATE}')
              WHERE NOT (year = 2017 AND lower(season) = 'winter')
              UNION ALL
              SELECT region_name, year, season, 'social_impressions', social_impressions
              FROM read_csv_auto('{AGGREGATE}')
              WHERE NOT (year = 2017 AND lower(season) = 'winter')
              UNION ALL
              SELECT region_name, year, season, 'podcast_ad_listens', podcast_ad_listens
              FROM read_csv_auto('{AGGREGATE}')
              WHERE NOT (year = 2017 AND lower(season) = 'winter')
              UNION ALL
              SELECT region_name, year, season, 'display_impressions', display_impressions
              FROM read_csv_auto('{AGGREGATE}')
              WHERE NOT (year = 2017 AND lower(season) = 'winter')
            )
          )
          GROUP BY channel
        )
        """
    ).fetchdf()
    channel_change.to_csv(OUT / "channel_changes.csv", index=False)
    con.execute(f"CREATE VIEW f AS SELECT * FROM read_parquet('{PARQUET}')")
    share = con.execute(
        f"""
        SELECT lower(region_name) AS region_name, season_index,
               AVG(CASE WHEN discount_flag = 0 THEN 1.0 ELSE 0.0 END) AS nopromo_share,
               COUNT(*) AS at_risk_n
        FROM f
        WHERE at_risk = TRUE AND season_index > {2017 * 4}
        GROUP BY 1, 2
        ORDER BY 2, 1
        """
    ).fetchdf()
    share.to_csv(OUT / "nopromo_share.csv", index=False)
    composition = acquisition.groupby(["user_type", "post", "treated"], as_index=False).agg(
        n=("signup", "size"),
        signup=("signup", "mean"),
        prior_member_seasons=("prior_member_seasons", "mean"),
        propensity=("customer_tv_score", "mean"),
        propensity_n=("customer_tv_score", "count"),
    )
    composition.to_csv(OUT / "composition.csv", index=False)
    for user_type, part in acquisition.groupby("user_type"):
        fit = did_fit(part, "signup")
        rows.append(_row("5", f"did_{user_type}", "signup", "treated_post", fit, "At-risk customers paying list price, this type only."))
        fit_r = did_fit(part, "revenue")
        rows.append(_row("5", f"did_{user_type}", "revenue", "treated_post", fit_r, "At-risk customers paying list price, this type only."))

    print("STEP 6 elasticity, churn, anticipation")
    promo = pd.read_csv(ROOT / "output" / "discount" / "estimates.csv")
    signup_promo = promo[promo["outcome"] == "signup"]
    for era, low, high, label in (("pre", 10, 14, "pre_$10_vs_$14"), ("post", 7, 11, "post_$7_vs_$11")):
        part = signup_promo[signup_promo["era"] == era]
        r_low = float(part.loc[part["price"] == low, "adj_rate"].iloc[0])
        r_high = float(part.loc[part["price"] == high, "adj_rate"].iloc[0])
        elasticity = float(np.log(r_low / r_high) / np.log(low / high))
        rows.append(_row(
            "6", "promo_elasticity", "signup", label, None,
            f"log({low} rate / {high} rate) / log({low}/{high}), adjusted promo sign-up rates.",
            estimate=elasticity,
        ))
    rate_with = signup_b + 0.024335728101463908
    rate_without = 0.024335728101463908
    did_elasticity = float(np.log(rate_with / rate_without) / np.log(12 / 15))
    rows.append(_row(
        "6", "did_elasticity", "signup", "$12_vs_$15", None,
        "log(counterfactual rate plus effect, over counterfactual) / log(12/15). Acquisition sample.",
        estimate=did_elasticity, se=signup_se,
    ))
    churn = con.execute(
        f"""
        WITH ordered AS (
          SELECT customer_id, season_index, lower(region_name) AS region_name,
                 treated_region, era, discount_flag, at_risk, new_signup, sign_up_flag,
                 LEAD(sign_up_flag) OVER (PARTITION BY customer_id ORDER BY season_index) AS next_member,
                 LEAD(season_index) OVER (PARTITION BY customer_id ORDER BY season_index) AS next_index
          FROM f
        )
        SELECT CASE WHEN treated_region THEN 1 ELSE 0 END AS treated,
               CASE WHEN era = 'post' THEN 1 ELSE 0 END AS post,
               AVG(next_member) AS still_member,
               COUNT(*) AS n
        FROM ordered
        WHERE at_risk = TRUE AND discount_flag = 0 AND new_signup = TRUE
          AND next_index = season_index + 1
          AND season_index > {2017 * 4} AND season_index < {2019 * 4 + 3}
        GROUP BY 1, 2
        """
    ).fetchdf()
    churn.to_csv(OUT / "list_price_joiner_retention.csv", index=False)
    winters = con.execute(
        f"""
        SELECT year,
               CASE WHEN treated_region THEN 'treated' ELSE 'panem' END AS grp,
               AVG(CAST(new_signup AS DOUBLE)) AS signup
        FROM f
        WHERE at_risk = TRUE AND discount_flag = 0 AND lower(season) = 'winter' AND year >= 2018
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchdf()
    winters.to_csv(OUT / "winter_signup.csv", index=False)

    print("region of season year")
    rows.append(_row(
        "4", "region_season_of_year", "signup", "treated_post", soy_did(acquisition, "signup"),
        "List-price sign-up. Each region keeps its own season-of-year level, plus a year shift.",
    ))
    rows.append(_row(
        "4", "region_season_of_year", "member", "treated_post", soy_did(everyone, "member"),
        "All customers. Each region keeps its own season-of-year level, plus a year shift.",
    ))
    rows.append(_row(
        "4", "region_season_of_year", "revenue", "treated_post", soy_did(everyone, "revenue"),
        "All customers. Each region keeps its own season-of-year level, plus a year shift.",
    ))

    results = pd.DataFrame(rows)
    results.to_csv(OUT / "results.csv", index=False)
    print(results[["step", "spec", "outcome", "term", "estimate", "se"]].to_string(index=False))
    print(f"wrote {OUT / 'results.csv'}")
    print("member_count gap", gap)
    print("churn\n", churn.to_string(index=False))
    print("winters\n", winters.to_string(index=False))


if __name__ == "__main__":
    main()
