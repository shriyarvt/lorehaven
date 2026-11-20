"""Discount-price estimates among customers offered a promo.

The offer dollar is randomized after eligibility. For each era, a linear
probability model puts a dummy on each dollar and holds region and year-season
fixed. Standard errors are clustered by customer. One-season revenue per
person offered is the membership rate at that dollar times the dollar.

    .venv/bin/python submission/discount_price.py
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "discount"
FIG = OUT / "figures"
PARQUET = ROOT / "output" / "flow" / "customer_season.parquet"

ERA_LABEL = {
    "pre": "Through winter 2019",
    "post": "Spring 2019 on",
}

plt.rcParams.update(
    {
        "figure.figsize": (9.2, 4.8),
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
        "axes.titlesize": 13,
        "legend.frameon": False,
    }
)


def load_eligible() -> pd.DataFrame:
    """Promo offers only. Panem has none."""
    con = duckdb.connect()
    frame = con.execute(
        f"""
        SELECT
          customer_id,
          region_name,
          season_index,
          era,
          CAST(membership_price AS INTEGER) AS price,
          CAST(sign_up_flag AS INTEGER) AS member,
          CAST(at_risk AS INTEGER) AS at_risk,
          CAST(new_signup AS INTEGER) AS signup,
          CAST(churned AS INTEGER) AS churn
        FROM read_parquet('{PARQUET}')
        WHERE discount_flag = 1
        """
    ).fetchdf()
    frame["region_name"] = frame["region_name"].astype("string")
    frame["era"] = frame["era"].astype("string")
    return frame


# Rebuild the fitted model's design matrix for a new set of rows.
def _design(result, data: pd.DataFrame) -> pd.DataFrame:
    info = result.model.data.orig_exog.design_info
    matrices = patsy.build_design_matrices([info], data, return_type="dataframe")
    return matrices[0]


# Fit OLS and cluster the standard errors by customer.
def _fit(formula: str, data: pd.DataFrame):
    return smf.ols(formula, data=data).fit(
        cov_type="cluster",
        cov_kwds={"groups": data["customer_id"].to_numpy()},
    )


def linear_rates(result, data: pd.DataFrame, prices: list[int]) -> pd.DataFrame:
    """Average predicted rate if every row in ``data`` were offered ``price``."""
    params = result.params
    cov = result.cov_params().to_numpy()
    rows = []
    xb = {}
    for price in prices:
        scenario = data.copy()
        scenario["price"] = price
        xbar = _design(result, scenario).mean(axis=0).reindex(params.index).to_numpy()
        rate = float(xbar @ params.to_numpy())
        se = float(np.sqrt(xbar @ cov @ xbar))
        xb[price] = xbar
        rows.append({"price": price, "rate": rate, "se": se, "n": int((data["price"] == price).sum())})
    table = pd.DataFrame(rows)
    table["revenue"] = table["rate"] * table["price"]
    table["revenue_se"] = table["se"] * table["price"]
    # Gap between the best dollar and the runner-up, on the revenue scale.
    order = table.sort_values("revenue", ascending=False)
    best, second = int(order.iloc[0]["price"]), int(order.iloc[1]["price"])
    gap_x = best * xb[best] - second * xb[second]
    gap = float(gap_x @ params.to_numpy())
    gap_se = float(np.sqrt(gap_x @ cov @ gap_x))
    table["best_price"] = best
    table["runner_up"] = second
    table["gap_vs_runner_up"] = gap
    table["gap_se"] = gap_se
    return table


# Price dummies only, with no region or season effects.
def raw_means(data: pd.DataFrame, y: str, prices: list[int]) -> pd.DataFrame:
    result = _fit(f"{y} ~ C(price)", data)
    table = linear_rates(result, data, prices)
    return table.rename(columns={"rate": "raw_rate", "se": "raw_se", "revenue": "raw_revenue", "revenue_se": "raw_revenue_se"})[
        ["price", "raw_rate", "raw_se", "raw_revenue", "raw_revenue_se", "n"]
    ]


def logit_rates(data: pd.DataFrame, y: str, prices: list[int]) -> pd.DataFrame:
    """Predicted rates from a logit with the same dummies and fixed effects."""
    result = smf.logit(f"{y} ~ C(price) + C(region_name) + C(season_index)", data=data).fit(
        method="lbfgs",
        disp=False,
        maxiter=100,
        cov_type="cluster",
        cov_kwds={"groups": data["customer_id"].to_numpy()},
    )
    params = result.params.to_numpy()
    cov = result.cov_params().to_numpy()
    rows = []
    for price in prices:
        scenario = data.copy()
        scenario["price"] = price
        exog = _design(result, scenario).reindex(columns=result.params.index).to_numpy()
        eta = exog @ params
        mu = 1.0 / (1.0 + np.exp(-eta))
        weight = (mu * (1.0 - mu))[:, None] * exog
        gradient = weight.mean(axis=0)
        rate = float(mu.mean())
        se = float(np.sqrt(gradient @ cov @ gradient))
        rows.append({"price": price, "logit_rate": rate, "logit_se": se})
    return pd.DataFrame(rows)


def within_effects(data: pd.DataFrame, y: str, prices: list[int]) -> pd.DataFrame:
    """Price differences versus the highest dollar, within customer.

    Region is constant for a customer, so it is absorbed. Year-season dummies
    are demeaned along with the price dummies.
    """
    base = max(prices)
    price_dummies = pd.get_dummies(data["price"].astype(int), prefix="p")
    price_dummies = price_dummies.drop(columns=[f"p_{base}"])
    season_dummies = pd.get_dummies(data["season_index"].astype(int), prefix="s", drop_first=True)
    exog = pd.concat([price_dummies, season_dummies], axis=1).astype(float)
    outcome = data[y].astype(float)
    customer = data["customer_id"]
    exog = exog - exog.groupby(customer).transform("mean")
    outcome = outcome - outcome.groupby(customer).transform("mean")
    keep = exog.std() > 1e-8
    exog = exog.loc[:, keep]
    result = sm.OLS(outcome, exog).fit(
        cov_type="cluster",
        cov_kwds={"groups": customer.to_numpy()},
    )
    rows = [{"price": base, "within_diff": 0.0, "within_se": 0.0}]
    for price in prices:
        if price == base:
            continue
        name = f"p_{price}"
        if name not in result.params.index:
            continue
        rows.append(
            {
                "price": price,
                "within_diff": float(result.params[name]),
                "within_se": float(result.bse[name]),
            }
        )
    varied = int(data.groupby("customer_id")["price"].nunique().gt(1).sum())
    table = pd.DataFrame(rows)
    table["customers_with_price_variation"] = varied
    return table


# Fit the adjusted, raw, logit, and within-customer estimates for one outcome, separately by era.
def estimate_outcome(data: pd.DataFrame, y: str, outcome: str) -> pd.DataFrame:
    pieces = []
    for era, era_data in data.groupby("era", sort=False):
        era_data = era_data.reset_index(drop=True)
        prices = sorted(int(p) for p in era_data["price"].unique())
        print(f"{outcome} {era}: {len(era_data):,} rows, prices {prices}", flush=True)
        adjusted = _fit(f"{y} ~ C(price) + C(region_name) + C(season_index)", era_data)
        adj = linear_rates(adjusted, era_data, prices).rename(
            columns={"rate": "adj_rate", "se": "adj_se", "revenue": "adj_revenue", "revenue_se": "adj_revenue_se"}
        )
        raw = raw_means(era_data, y, prices).drop(columns=["n"])
        print(f"  logit {outcome} {era}", flush=True)
        logit = logit_rates(era_data, y, prices)
        print(f"  within {outcome} {era}", flush=True)
        within = within_effects(era_data, y, prices)
        merged = adj.merge(raw, on="price").merge(logit, on="price").merge(within, on="price")
        merged.insert(0, "outcome", outcome)
        merged.insert(1, "era", era)
        pieces.append(merged)
    return pd.concat(pieces, ignore_index=True)


# Write one chart to the discount figures folder and close it.
def save_fig(fig: plt.Figure, name: str) -> Path:
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / f"{name}.png"
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


ERA_COLOR = {"pre": "#4C78A8", "post": "#F58518"}


# Rows for one outcome in one era, ordered by offer price.
def era_slice(estimates: pd.DataFrame, outcome: str, era: str) -> pd.DataFrame:
    return estimates[(estimates["outcome"] == outcome) & (estimates["era"] == era)].sort_values("price")


# Plot the raw average and the adjusted rate, with a 95% interval on the adjusted line.
def plot_series(rows: pd.DataFrame, y: str, se: str, raw: str, title: str, ylabel: str, name: str, color: str) -> Path:
    fig, ax = plt.subplots()
    ax.plot(
        rows["price"],
        rows[raw],
        color="#9a9a9a",
        lw=1.4,
        ls="--",
        marker="o",
        ms=7,
        mfc="none",
        label="Raw average",
    )
    ax.errorbar(
        rows["price"],
        rows[y],
        yerr=1.96 * rows[se],
        fmt="-o",
        color=color,
        lw=1.8,
        capsize=3,
        label="Region and season held constant",
        zorder=3,
    )
    prices = [int(p) for p in rows["price"]]
    ax.set_xticks(prices)
    ax.set_xlim(min(prices) - 0.35, max(prices) + 0.35)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Offer price ($)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.tight_layout()
    return save_fig(fig, name)


# Format a rate as a percent with one decimal.
def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


# Format a rate difference as percentage points.
def pp(x: float) -> str:
    points = 100 * x
    digits = 2 if abs(points) < 1 else 1
    return f"{points:.{digits}f} percentage points"


# Phrase a small rate gap as "less than 0.1 percentage points" when it rounds away.
def gap_phrase(x: float) -> str:
    if abs(100 * x) < 0.05:
        return "less than 0.1 percentage points"
    return pp(x)


# Format a dollar amount to the cent.
def money(x: float) -> str:
    return f"${x:.2f}"


# Say which dollar has the highest revenue, or that the top two are tied.
def ranking_sentence(rows: pd.DataFrame, what: str) -> str:
    best = int(rows["best_price"].iloc[0])
    second = int(rows["runner_up"].iloc[0])
    gap = float(rows["gap_vs_runner_up"].iloc[0])
    gap_se = float(rows["gap_se"].iloc[0])
    best_rev = float(rows.loc[rows["price"] == best, "adj_revenue"].iloc[0])
    second_rev = float(rows.loc[rows["price"] == second, "adj_revenue"].iloc[0])
    if abs(gap) < 1.96 * gap_se:
        return (
            f"${best} and ${second} are tied on {what}, at ${best_rev:.3f} and ${second_rev:.3f}. "
            f"The ${abs(gap):.3f} gap has a clustered standard error of ${gap_se:.3f}."
        )
    return (
        f"{what[:1].upper()}{what[1:]} is highest at ${best} ({money(best_rev)}). "
        f"${second} is next, ${gap:.2f} lower, and that gap is {gap / gap_se:.1f} clustered standard errors."
    )


# Describe how a rate changes from the lowest offer price to the highest.
def rate_path(rows: pd.DataFrame, noun: str, lead: bool = True) -> str:
    low, high = rows.iloc[0], rows.iloc[-1]
    verb = "falls" if low["adj_rate"] > high["adj_rate"] else "rises"
    sentence = (
        f"the {noun} {verb} from {pct(low['adj_rate'])} at ${int(low['price'])} "
        f"to {pct(high['adj_rate'])} at ${int(high['price'])}."
    )
    return sentence[:1].upper() + sentence[1:] if lead else sentence


# Write the membership, sign-up, churn, and robustness sentences for one era.
def era_paragraphs(estimates: pd.DataFrame, era: str) -> list[str]:
    mem = era_slice(estimates, "membership", era)
    signup = era_slice(estimates, "signup", era)
    churn = era_slice(estimates, "churn", era)
    low = mem.iloc[0]
    within_gap = float(low["within_diff"])
    within_word = "higher" if within_gap >= 0 else "lower"
    checks = pd.concat([mem, signup, churn])
    raw_gap = float((checks["adj_rate"] - checks["raw_rate"]).abs().max())
    logit_gap = float((checks["adj_rate"] - checks["logit_rate"]).abs().max())
    return [
        ranking_sentence(mem, "revenue per person offered")
        + f" Each dollar covers about {int(mem['n'].mean()):,} customer-seasons. "
        + rate_path(mem, "membership rate")
        + f" For the same customer, membership at ${int(low['price'])} is {pp(abs(within_gap))} "
        + f"{within_word} than at ${int(mem.iloc[-1]['price'])} (standard error {pp(low['within_se'])}).",
        "Among people who were not members last season, "
        + rate_path(signup, "sign-up rate", lead=False)
        + " "
        + ranking_sentence(signup, "sign-up revenue per person at risk"),
        "Among people who were members last season, " + rate_path(churn, "churn rate", lead=False),
        (
            f"Holding region and year-season constant changes every rate by {gap_phrase(raw_gap)}. "
            f"The logit differs from the linear probability model by {gap_phrase(logit_gap)}."
        ),
    ]


# Build the HTML table of membership and revenue by offer dollar.
def membership_table(rows: pd.DataFrame) -> list[str]:
    parts = ["<table><thead><tr>"]
    for column in [
        "Price",
        "N",
        "Raw rate",
        "Adjusted rate",
        "Raw revenue",
        "Adjusted revenue",
        "Logit rate",
        "Within-person gap vs highest price",
    ]:
        parts.append(f"<th>{column}</th>")
    parts.append("</tr></thead><tbody>")
    for _, row in rows.iterrows():
        parts.append(
            "<tr>"
            f"<td>${int(row['price'])}</td>"
            f"<td>{int(row['n']):,}</td>"
            f"<td>{pct(row['raw_rate'])}</td>"
            f"<td>{pct(row['adj_rate'])}</td>"
            f"<td>{money(row['raw_revenue'])}</td>"
            f"<td>{money(row['adj_revenue'])}</td>"
            f"<td>{pct(row['logit_rate'])}</td>"
            f"<td>{pct(row['within_diff'])}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    return parts


# Write the discount summary page with the charts embedded.
def build_html(estimates: pd.DataFrame) -> None:
    charts = [
        ("revenue", "membership", "adj_revenue", "adj_revenue_se", "raw_revenue", "One-season revenue per person offered", "Dollars per person offered", "Revenue per person offered", "Membership rate times the offer price."),
        ("membership_rate", "membership", "adj_rate", "adj_se", "raw_rate", "Membership rate by offer price", "Membership rate", "Membership rate", "Share of promo customers who are members this season."),
        ("signup_rate", "signup", "adj_rate", "adj_se", "raw_rate", "Sign-up rate by offer price", "Sign-up rate", "Sign-up rate", "Promo customers who were not members last season."),
        ("churn_rate", "churn", "adj_rate", "adj_se", "raw_rate", "Churn rate by offer price", "Churn rate", "Churn rate", "Promo customers who were members last season."),
    ]
    for stale in ("revenue", "membership_rate", "signup_rate", "churn_rate"):
        old = FIG / f"{stale}.png"
        if old.exists():
            old.unlink()

    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'><head><meta charset='utf-8'>",
        "<title>Discount price estimates</title>",
        "<style>",
        "body{font-family:Georgia,serif;max-width:880px;margin:2rem auto;padding:0 1.25rem;color:#1c1c1c;line-height:1.45}",
        "h1{font-weight:500;font-size:1.7rem} h2{font-weight:500;font-size:1.35rem;margin-top:2.4rem;border-top:1px solid #ddd;padding-top:1.4rem}",
        "h3{font-weight:500;font-size:1.1rem;margin-top:1.4rem}",
        "p{margin:0.4rem 0 0.8rem} img{width:100%;height:auto}",
        "table{border-collapse:collapse;width:100%;font-size:0.92rem;margin-top:0.6rem} td,th{border-bottom:1px solid #ddd;padding:0.3rem 0.4rem;text-align:right}",
        "td:first-child,th:first-child{text-align:left}",
        "</style></head><body>",
        "<h1>Discount price estimates</h1>",
        "<p>Sample is customers who were offered a promo. The dollar on that offer is the randomized price. "
        "The two periods are estimated and shown separately, because the grid is $10 to $14 through winter 2019 "
        "and $7 to $11 from spring 2019 on. "
        "Each period uses a linear probability model with a dummy for each dollar, region fixed effects, and year-season fixed effects. "
        "Standard errors are clustered by customer. The dashed line is the raw average. "
        "Filled circles hold region and year-season constant, with 95% intervals. "
        "One-season revenue per person offered is the membership rate times the price.</p>",
    ]
    for era in ("pre", "post"):
        parts.append(f"<h2>{html.escape(ERA_LABEL[era])}</h2>")
        for paragraph in era_paragraphs(estimates, era):
            parts.append(f"<p>{html.escape(paragraph)}</p>")
        for name, outcome, y, se, raw, title, ylabel, heading, blurb in charts:
            rows = era_slice(estimates, outcome, era)
            path = plot_series(
                rows,
                y,
                se,
                raw,
                f"{title}, {ERA_LABEL[era].lower()}",
                ylabel,
                f"{name}_{era}",
                ERA_COLOR[era],
            )
            uri = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
            parts.append(f"<h3>{html.escape(heading)}</h3>")
            parts.append(f"<p>{html.escape(blurb)}</p>")
            parts.append(f"<img alt='{html.escape(heading)}' src='{uri}'>")
        parts.append("<h3>Membership and revenue by dollar</h3>")
        parts.extend(membership_table(era_slice(estimates, "membership", era)))
        parts.append(
            "<p>The within-person column is the difference in the membership rate versus the highest dollar in this period, "
            "for the same customer in seasons when they were offered different dollars. "
            "The logit column uses the same dummies and fixed effects, then averages the predicted probability.</p>"
        )
    parts.append("</body></html>")
    (OUT / "summary.html").write_text("\n".join(parts))


# Estimate every promo outcome, save the table, and write the summary page.
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    eligible = load_eligible()
    print(f"eligible rows: {len(eligible):,}", flush=True)
    # Prior members have at_risk == 0. The opening season has a missing at_risk and is excluded.
    churn_sample = eligible[(eligible["at_risk"] == 0) & (eligible["churn"].notna())].reset_index(drop=True)
    signup_sample = eligible[eligible["at_risk"] == 1].reset_index(drop=True)

    pieces = [
        estimate_outcome(eligible.reset_index(drop=True), "member", "membership"),
        estimate_outcome(signup_sample, "signup", "signup"),
        estimate_outcome(churn_sample, "churn", "churn"),
    ]
    estimates = pd.concat(pieces, ignore_index=True)
    estimates.to_csv(OUT / "estimates.csv", index=False)

    build_html(estimates)
    for era in ("pre", "post"):
        print(ERA_LABEL[era])
        for paragraph in era_paragraphs(estimates, era):
            print(paragraph)
            print()
    print(f"wrote {OUT / 'summary.html'}")


if __name__ == "__main__":
    main()
