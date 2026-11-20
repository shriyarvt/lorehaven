"""Build a customer-season sign-up flow from the Lorehaven membership panel.

``sign_up_flag`` is a stock: it is 1 in the season a customer becomes a member
and stays 1 until they leave. This script turns that stock into a flow.

``prev_member`` is last season's stock, and only when that season is the
immediately previous one. A gap is not treated as a continuation.

``--first-season`` chooses the first observed season for each customer, which
has no prior row:

* ``drop`` (default): leave ``prev_member``, ``at_risk``, ``new_signup``, and
  ``churned`` missing. Those rows stay in the customer-season file and stay
  out of the rates.
* ``assume_nonmember``: treat that first season as if the customer was not a
  member before it, so a stock of 1 counts as a new sign-up. Gaps are never
  filled in.

Run from the repo root:

    .venv/bin/python build_signup_flow.py \\
        --panel data/customer_panel.csv \\
        --aggregate data/aggregate.csv \\
        --out-dir output/flow
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SEASON_ORDER = {"winter": 0, "spring": 1, "summer": 2, "fall": 3}
SEASON_RANK = {name: rank for name, rank in SEASON_ORDER.items()}

REQUIRED_COLUMNS = (
    "region_id",
    "region_name",
    "year",
    "season",
    "customer_id",
    "search_flag",
    "social_ad_impressions",
    "podcast_ad_listen",
    "membership_price",
    "discount_flag",
    "sign_up_flag",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Turn the Lorehaven membership stock into a customer-season "
            "sign-up and churn flow."
        )
    )
    parser.add_argument("--panel", type=Path, required=True, help="Path to customer_panel.csv")
    parser.add_argument(
        "--aggregate",
        type=Path,
        default=None,
        help="Optional aggregate.csv. If given, member_count is compared with the panel stock.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory for customer_season.parquet and region_season_summary.csv",
    )
    parser.add_argument(
        "--first-season",
        choices=("assume_nonmember", "drop"),
        default="drop",
        help=(
            "How to treat each customer's first observed season, which has no prior row. "
            "drop (default) leaves the flow flags missing. "
            "assume_nonmember sets prev_member to 0 so a sign-up in that season counts as new. "
            "Neither option fills a later gap."
        ),
    )
    return parser.parse_args(argv)


def _normalize_season(season: pd.Series) -> pd.Series:
    cleaned = season.astype("string").str.strip().str.lower()
    unknown = sorted(set(cleaned.dropna()) - set(SEASON_ORDER))
    if unknown:
        raise ValueError(
            "Unrecognized season labels: "
            + ", ".join(unknown)
            + ". Expected winter, spring, summer, fall."
        )
    return cleaned


def add_season_index(panel: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with ``season_index`` in winter-spring-summer-fall order.

    The index is ``year * 4 + season rank``. Fall of one year and winter of the
    next are one step apart. Alphabetical season order is not used.
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in panel.columns]
    if missing:
        raise ValueError("Panel is missing columns: " + ", ".join(missing))

    out = panel.copy()
    out["season_key"] = _normalize_season(out["season"])
    out["year"] = pd.to_numeric(out["year"], errors="raise").astype("int64")
    out["season_index"] = out["year"] * 4 + out["season_key"].map(SEASON_RANK).astype("int64")
    out["sign_up_flag"] = pd.to_numeric(out["sign_up_flag"], errors="raise").astype("int64")
    out["discount_flag"] = pd.to_numeric(out["discount_flag"], errors="raise").astype("int64")
    out["membership_price"] = pd.to_numeric(out["membership_price"], errors="raise")
    return out


def validate_panel(panel: pd.DataFrame) -> None:
    """Check duplicates, balance, region stability, and 1 -> 0 -> 1 re-entry.

    Duplicate ``(customer_id, season_index)`` rows raise ``ValueError``.
    Other problems are printed and do not stop the build.
    """
    if "season_index" not in panel.columns:
        raise ValueError("season_index is required before validation.")

    duplicate_count = int(panel.duplicated(["customer_id", "season_index"]).sum())
    if duplicate_count:
        raise ValueError(
            f"Found {duplicate_count} duplicate (customer_id, season_index) rows. "
            "Each customer must appear at most once per season."
        )

    n_seasons = int(panel["season_index"].nunique())
    by_customer = panel.groupby("customer_id", sort=False)["season_index"]
    observed = by_customer.nunique()
    not_in_every_season = int((observed != n_seasons).sum())
    span = by_customer.max() - by_customer.min() + 1
    internal_gaps = int((span != by_customer.count()).sum())
    balanced = not_in_every_season == 0 and internal_gaps == 0

    region_count = panel.groupby("customer_id", sort=False)["region_name"].nunique()
    multi_region = int((region_count > 1).sum())

    ordered = panel.sort_values(["customer_id", "season_index"], kind="mergesort")
    grouped_flag = ordered.groupby("customer_id", sort=False)["sign_up_flag"]
    prior_max = grouped_flag.cummax().groupby(ordered["customer_id"], sort=False).shift(1)
    churn_event = ordered["sign_up_flag"].eq(0) & prior_max.eq(1)
    churn_seen_before = (
        churn_event.groupby(ordered["customer_id"], sort=False)
        .cummax()
        .groupby(ordered["customer_id"], sort=False)
        .shift(1)
    )
    reentry_customers = int(
        ordered.loc[ordered["sign_up_flag"].eq(1) & churn_seen_before.eq(1), "customer_id"].nunique()
    )

    print(f"customers: {panel['customer_id'].nunique()}")
    print(f"seasons: {n_seasons}")
    print(f"duplicate customer-seasons: {duplicate_count}")
    if balanced:
        print("panel: balanced. Every customer appears in every season, with no internal gaps.")
    else:
        print(
            "WARNING: panel is not balanced. "
            f"{not_in_every_season} customers are missing at least one season. "
            f"{internal_gaps} customers have a gap between their first and last season."
        )
    if multi_region:
        print(f"WARNING: {multi_region} customers appear in more than one region.")
    else:
        print("region: each customer stays in one region.")
    if reentry_customers:
        print(
            "WARNING: "
            f"{reentry_customers} customers go from member to non-member and back to member (1 -> 0 -> 1)."
        )
    else:
        print("re-entry: no customer goes 1 -> 0 -> 1.")


def add_flow(panel: pd.DataFrame, first_season: str = "drop") -> pd.DataFrame:
    """Add previous membership, sign-up, churn, era, and treated region.

    Parameters
    ----------
    panel:
        Frame that already has ``season_index`` from :func:`add_season_index`.
    first_season:
        ``drop`` or ``assume_nonmember``. See the module docstring.
    """
    if first_season not in {"drop", "assume_nonmember"}:
        raise ValueError("first_season must be 'drop' or 'assume_nonmember'.")

    out = panel.sort_values(["customer_id", "season_index"], kind="mergesort").reset_index(drop=True)
    grouped = out.groupby("customer_id", sort=False)
    previous_flag = grouped["sign_up_flag"].shift(1)
    previous_index = grouped["season_index"].shift(1)
    consecutive = out["season_index"].eq(previous_index + 1)
    prev_member = previous_flag.where(consecutive)

    first_observed = previous_index.isna()
    if first_season == "assume_nonmember":
        prev_member = prev_member.mask(first_observed, 0)

    prev_member = prev_member.astype("Int64")
    sign_up = out["sign_up_flag"].astype("boolean")
    known_prior = prev_member.notna()
    # Boolean NA combined with & becomes False. Put the missing prior back afterward.
    at_risk = prev_member.eq(0).astype("boolean")
    new_signup = (at_risk.fillna(False) & sign_up.fillna(False)).astype("boolean")
    new_signup = new_signup.mask(~known_prior)
    churned = (prev_member.eq(1).fillna(False) & ~sign_up.fillna(False)).astype("boolean")
    churned = churned.mask(~known_prior)
    at_risk = at_risk.mask(~known_prior)

    out["prev_member"] = prev_member
    out["at_risk"] = at_risk
    out["new_signup"] = new_signup
    out["churned"] = churned

    season_key = out["season_key"]
    pre = out["year"].lt(2019) | (out["year"].eq(2019) & season_key.eq("winter"))
    out["era"] = pd.Series(pd.NA, index=out.index, dtype="string")
    out.loc[pre, "era"] = "pre"
    out.loc[~pre, "era"] = "post"
    out["treated_region"] = ~out["region_name"].astype("string").str.strip().str.lower().eq("panem")
    return out.drop(columns=["season_key"])


def region_season_summary(flow: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sign-up and churn rates by region and season.

    Rates use only rows with a defined previous membership. ``signup_rate`` is
    new sign-ups divided by customers at risk. ``churn_rate`` is churns divided
    by customers who were members last season.
    """
    work = flow.copy()
    at_risk = work["at_risk"].fillna(False).astype("int64")
    work["at_risk_i"] = at_risk
    work["new_i"] = work["new_signup"].fillna(False).astype("int64")
    work["churn_i"] = work["churned"].fillna(False).astype("int64")
    work["prev_i"] = work["prev_member"].eq(1).fillna(False).astype("int64")
    work["promo_at_risk"] = work["discount_flag"].astype("int64") * at_risk
    work["price_at_risk"] = work["membership_price"].astype("float64") * at_risk

    grouped = work.groupby(["region_name", "year", "season", "season_index"], sort=False)
    summary = grouped.agg(
        n_customers=("customer_id", "size"),
        n_at_risk=("at_risk_i", "sum"),
        n_new_signup=("new_i", "sum"),
        n_churned=("churn_i", "sum"),
        n_prior_members=("prev_i", "sum"),
        promo_at_risk=("promo_at_risk", "sum"),
        price_at_risk=("price_at_risk", "sum"),
    ).reset_index()

    summary["signup_rate"] = summary["n_new_signup"] / summary["n_at_risk"].where(summary["n_at_risk"].gt(0))
    summary["churn_rate"] = summary["n_churned"] / summary["n_prior_members"].where(
        summary["n_prior_members"].gt(0)
    )
    summary["share_offered_promo"] = summary["promo_at_risk"] / summary["n_at_risk"].where(
        summary["n_at_risk"].gt(0)
    )
    summary["mean_offered_price"] = summary["price_at_risk"] / summary["n_at_risk"].where(
        summary["n_at_risk"].gt(0)
    )
    summary = summary.sort_values(["season_index", "region_name"]).reset_index(drop=True)
    return summary[
        [
            "region_name",
            "year",
            "season",
            "n_customers",
            "n_at_risk",
            "n_new_signup",
            "signup_rate",
            "n_churned",
            "churn_rate",
            "share_offered_promo",
            "mean_offered_price",
        ]
    ]


def flow_identity_mismatches(flow: pd.DataFrame) -> pd.DataFrame:
    """Return region-seasons where the membership flow does not add up.

    Among rows with a known previous season:

        members now = prior members - churned + new sign-ups

    Members in a first season or after a gap have no previous season, so they
    are reported separately and are not a mismatch under ``drop``.
    """
    known = flow["prev_member"].notna()
    work = flow.loc[known].copy()
    work["member_now"] = work["sign_up_flag"].eq(1).astype("int64")
    work["prior"] = work["prev_member"].eq(1).astype("int64")
    work["churn_i"] = work["churned"].fillna(False).astype("int64")
    work["new_i"] = work["new_signup"].fillna(False).astype("int64")

    if work.empty:
        checked = pd.DataFrame(
            columns=["region_name", "year", "season", "members_now", "expected", "difference"]
        )
    else:
        grouped = work.groupby(["region_name", "year", "season"], sort=False)
        checked = grouped.agg(
            members_now=("member_now", "sum"),
            prior=("prior", "sum"),
            churned=("churn_i", "sum"),
            new_signup=("new_i", "sum"),
        ).reset_index()
        checked["expected"] = checked["prior"] - checked["churned"] + checked["new_signup"]
        checked["difference"] = checked["members_now"] - checked["expected"]
        checked = checked.loc[checked["difference"].ne(0), ["region_name", "year", "season", "members_now", "expected", "difference"]]

    undefined = flow.loc[~known & flow["sign_up_flag"].eq(1)]
    undefined_counts = (
        undefined.groupby(["region_name", "year", "season"], sort=False).size().rename("members_without_prior").reset_index()
        if not undefined.empty
        else pd.DataFrame(columns=["region_name", "year", "season", "members_without_prior"])
    )
    if undefined_counts.empty:
        print("Members with no previous season: 0")
    else:
        print("Members with no previous season (first season or a gap; excluded from the identity):")
        print(undefined_counts.to_string(index=False))

    if checked.empty:
        print("Membership flow identity holds for every region-season with a known previous season.")
    else:
        print("WARNING: membership flow identity mismatches:")
        print(checked.to_string(index=False))
    return checked.reset_index(drop=True)


def compare_to_aggregate(flow: pd.DataFrame, aggregate_path: Path) -> float:
    """Compare the panel membership stock with ``member_count`` in aggregate.csv.

    Returns the maximum absolute gap. A gap of zero means the two files count
    the same members.
    """
    aggregate = pd.read_csv(aggregate_path)
    required = {"region_name", "year", "season", "member_count"}
    missing = required - set(aggregate.columns)
    if missing:
        raise ValueError("aggregate.csv is missing columns: " + ", ".join(sorted(missing)))

    panel_members = (
        flow.assign(_season=_normalize_season(flow["season"]))
        .groupby(["region_name", "year", "_season"], sort=False)["sign_up_flag"]
        .sum()
        .rename("panel_members")
        .reset_index()
    )
    aggregate = aggregate.copy()
    aggregate["_season"] = _normalize_season(aggregate["season"])
    aggregate["year"] = pd.to_numeric(aggregate["year"], errors="raise").astype("int64")
    aggregate["member_count"] = pd.to_numeric(aggregate["member_count"], errors="raise")
    merged = panel_members.merge(
        aggregate[["region_name", "year", "_season", "member_count"]],
        on=["region_name", "year", "_season"],
        how="outer",
        indicator=True,
    )
    if (merged["_merge"] != "both").any():
        print("WARNING: some region-seasons are in only one of the panel and aggregate files.")
    gap = (merged["panel_members"].fillna(0) - merged["member_count"].fillna(0)).abs()
    max_gap = float(gap.max()) if len(gap) else 0.0
    print(f"Max absolute gap between panel membership stock and aggregate member_count: {max_gap:.0f}")
    return max_gap


def build(panel: pd.DataFrame, first_season: str = "drop") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate ``panel`` and return the flow frame and the region-season summary."""
    indexed = add_season_index(panel)
    validate_panel(indexed)
    flow = add_flow(indexed, first_season=first_season)
    summary = region_season_summary(flow)
    return flow, summary


def main(argv: list[str] | None = None) -> None:
    """Load the panel, write the flow outputs, and print the checks."""
    args = parse_args(argv)
    panel = pd.read_csv(args.panel)
    flow, summary = build(panel, first_season=args.first_season)
    mismatches = flow_identity_mismatches(flow)
    if args.aggregate is not None:
        compare_to_aggregate(flow, args.aggregate)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    flow_path = args.out_dir / "customer_season.parquet"
    summary_path = args.out_dir / "region_season_summary.csv"
    flow.to_parquet(flow_path, index=False)
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {flow_path}")
    print(f"Wrote {summary_path}")
    if not mismatches.empty:
        print(
            f"{len(mismatches)} region-seasons failed the membership flow identity. See the table above.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
