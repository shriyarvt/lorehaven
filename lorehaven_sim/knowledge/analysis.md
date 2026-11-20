# Lorehaven Pricing: Promo and List Price Findings

## Summary

| Question                                                            | Answer                                                                                                                           | Confidence                            | Data tested                                                                                                                                                                                                 |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Best promo dollar through winter 2019 overall pooled (grid $10–$14) | $11, tied with $10 at $3.88; $11 is slightly higher                                                                              | High, randomized                      | Five promo regions; Panem excluded. All eligible customers, pooled                                                                                                                                          |
| Best promo dollar, spring 2019 overall pooled (grid $7–$11)         | $11: $5.95 per person offered, $0.25 ± $0.02 above $10                                                                           | High, randomized                      | Five promo regions; Panem excluded. All eligible customers, pooled                                                                                                                                          |
| Best dollar by user type, pre-cut (grid $10–$14)                    | New $10; lapsed $10; recurring $13 (ties $14)                                                                                    | High for one season                   | Five promo regions; Panem excluded. New, lapsed, and recurring, each fit separately. Winter 2017 excluded                                                                                                   |
| Best dollar by user type, post-cut (grid $7–$11)                    | New $7; lapsed $8 (ties $7); recurring $11                                                                                       | High for one season                   | Five promo regions; Panem excluded. New, lapsed, and recurring, each fit separately                                                                                                                         |
| Did the $15 to $12 list cut pay off?                                | Yes, sign-ups +3.54 pp (95% CI 3.45 to 3.63); revenue per person at risk +$0.35; all-customer revenue +$0.35 per customer-season | Low to moderate; parallel trends fail | Five regions versus Panem as counterfactual. Sign-up and revenue per person at risk (people not members last season who pay list price). All-customer revenue: every customer, including recurring members |

## Recommendations

**List price**

Keep the five promo regions at $12 and leave Panem at $15, and run a randomized list-price test before changing either. The $15 to $12 cut lifted sign-ups for at risk customers by 3.54 pp (95% CI 3.45 to 3.63), well above the 0.61 pp a $12 joiner needs to match $15 revenue, and revenue per person at risk rose $0.35. Even under the most conservative specification (region × season-of-year effects), the sign-up gain is still +1.03 pp, but all-customer revenue per customer-season turns slightly negative (−$0.06), so the evidence supports keeping $12 without supporting a confident revenue claim. There is not enough confidence to move Panem to $12. Confidence is moderate on memberships, low to moderate on the size of the sign-up gain, and low on revenue. Panem is also the only holdout, so moving it would remove the only comparison group for future work.

The list-price result is directional only. Pre-cut gaps were already moving (χ² = 2,335, 7 df, p < 0.001), Panem is the single comparison region, and its 10.9 pp sign-up drop in summer 2019 cannot be separated from the effect of the cut. The estimates also bundle the list cut with the promo grid moving from $10–$14 to $7–$11. The follow-up test should randomize list price across several regions and compare $12 against prices between $12 and $15 (for example $13 and $14), since only $12 and $15 have been observed. It should hold the promo grid fixed, confirm parallel pre-period trends before launch, and track sign-up, churn, and revenue per person at risk over more than one season.

**Promo pricing**

After the cut, in the five promo regions, offer $11 to recurring users, $8 to lapsed users, and $7 to new users. Recurring customers earn $9.66 per person offered at $11, $0.623 ± $0.020 above the next dollar, with 87.9% staying. This is the clearest result, and they are 57% of post-cut customer-seasons. Lapsed customers earn $3.73 at $8, but the $0.102 ± $0.069 lead over $7 is a tie, chosen for higher revenue. This is the noisiest group, at about 5,900 customer-seasons per dollar, so $7 and $8 are effectively interchangeable. New customers earn $1.44 at $7, $0.164 ± $0.022 above the next dollar. If the firm cannot price by type, offer $11 to all eligible customers. That earns $5.95 per person offered, $0.249 ± $0.024 above $10, or $117,000 ± $11,000 more in total ($2.80 million). That price is driven by the recurring group, so it depends on the 57% recurring mix. The result is causal for eligible customers within the tested $7–$11 grid, and it does not say who should receive a promo. Panem never has promos, so no promo recommendation applies to it.

**Caveats.** Everything above assumes a member stays one season. A retention model by dollar at sign-up should settle the best dollar for closer revenue gaps. Post-cut revenue is still rising at $11, promos above $11 were not randomized, and $7 is the bottom of the grid, so nothing here speaks to deeper discounts, which may also attract members who churn faster. Finally, revenue is treated as profit (cost to serve assumed zero), and the break-evens shift once that changes.

## Promo price study

The promo dollar was randomized among eligible customers in five regions each season: $10 to $14 off a $15 list through winter 2019, and $7 to $11 off a $12 list from spring 2019. Panem never has promos and is excluded. Each period is a linear probability model with a dummy per dollar, region and year-season effects, and standard errors clustered by customer.

Eight linear probability models were fit: three user types times two periods, plus one stacked model per period. Each has the same right-hand side: a dummy for every dollar, with the lowest dollar as the baseline, region effects, and year-season effects. Standard errors are clustered by customer. Each regression covers all five regions. 

These results are predicated on the following assumptions: promo dollar amount is random among eligible customers, revenue is the objective (over membership), a member is counted for this season only, the two periods are estimated separately (split at spring 2019).

`P(y=1) = a + Σ b_d · 1[price = d] + region effect + year-season effect + error`

LPM Assumptions: promo dollar randomized among eligible customers (causal price coefficients, balanced on prior-season membership), flexible price effect via a dummy per dollar (no equal-step assumption) with additive region and year-season effects, rates far from 0 and 1 (about 5% to 65%), heteroskedastic errors handled with robust standard errors, independence across customers but not across seasons (standard errors clustered by customer), no spillovers between customers, estimates valid only for eligible customers within the tested prices.

Results: The best dollar is the one with the highest revenue per person per season. 

Revenue = estimated membership rate x the offer price

| User type        | Period   | N (% of customer-seasons per period) | Best dollar | Revenue per person per season | Lead over next      | Membership rate (95% CI) |
| ---------------- | -------- | ------------------------------------- | ----------- | ----------------------------- | ------------------- | ------------------------ |
| **All eligible** | **Pre**  | **1.04M (100%)**                      | **$11**     | **$3.884**                    | **$0.003 ± $0.015** | **35.3% ± 0.24**         |
| Recurring        | Pre      | 318k (30.4%)                          | $13         | $9.965                        | $0.028 ± $0.033     | 76.7% ± 0.32             |
| Lapsed           | Pre      | 39k (3.7%)                            | $10         | $4.044                        | $0.327 ± $0.081     | 40.4% ± 1.09             |
| New              | Pre      | 598k (57.2%)                          | $10         | $1.582                        | $0.245 ± $0.015     | 15.8% ± 0.21             |
| **All eligible** | **Post** | **471k (100%)**                       | **$11**     | **$5.946**                    | **$0.249 ± $0.024** | **54.1% ± 0.34**         |
| Recurring        | Post     | 270k (57.3%)                          | $11         | $9.664                        | $0.623 ± $0.020     | 87.9% ± 0.28             |
| Lapsed           | Post     | 29k (6.3%)                            | $8          | $3.727                        | $0.102 ± $0.069     | 46.6% ± 1.27             |
| New              | Post     | 171k (36.4%)                          | $7          | $1.443                        | $0.164 ± $0.022     | 20.6% ± 0.43             |

*Pre is through winter 2019, on the $10–$14 grid. Post is spring 2019 on, on the $7–$11 grid. Membership is the share of that row who are members this season. For recurring customers that is the share who stay. The ± on the membership rate is a 95% confidence interval, the estimate ± 1.96 clustered standard errors. The ± on the lead is one clustered standard error. Where that lead's 95% interval includes 0, the table reports the higher-revenue dollar.*

A higher offer price also cuts sign-ups (17.3% at $10 to 5.3% at $14 before the cut; 25.2% at $7 to 8.4% at $11 after) and raises churn (11.6% to 29.0%; 5.1% to 12.1%). The higher price paid by members who stay outweighs that within one season, however, for the purposes of this analysis members are assumed to be staying only one season. After the cut, $11 collects $2.80 million from 470,674 eligible customer-seasons, $117,000 ± $11,000 more than $10. Before the cut, $10 and $11 each collect about $4.05 million.

Does a cheaper dollar pay back through longer membership? After the cut, a cheaper dollar gives up revenue now and keeps more members. This is what an extra member must be worth in later revenue for it to beat $11.

Against $11, $10 gives up $0.25 per offer and keeps 2.9 extra members per 100 offers, so an extra member must be worth $8.53. $9 gives up $0.59 and keeps 5.4, a break-even of $10.89. $8 gives up $0.96 and keeps 8.2, a break-even of $11.69. $7 gives up $1.37 and keeps 11.3, a break-even of $12.11.

One more season at $11 is worth 87.9% × $11 = $9.66, which clears only $10. Two or more seasons clears $7. So the post-cut answer is $11 for this season only, $10 with one more season, and $7 with two or more. These horizons are assumptions, and they value every extra member at the $11 price, which flatters the cheaper dollars. Counting later seasons at each dollar's own price and churn, $10 breaks even after one future season and $9, $8 and $7 after two.

## List price cut: $15 to $12

In spring 2019 five regions cut list price from $15 to $12 while Panem stayed at $15. Every estimate is a difference-in-differences against Panem, measured relative to winter 2019, with standard errors clustered by customer. Two samples are tested: people who were not members last season and pay list price (4,032,066 customer-seasons), and all customers (5,610,979).

**DiD Assumptions:**

- **Parallel trends** between the five cut regions and Panem without the cut: *fails*. A joint test rejects flat pre-cut gaps (χ² = 2,335, 7 df, p < 0.001), with gaps of −0.18 to +2.35 pp before versus +3.41 to +6.11 pp after.
- **Valid counterfactual (Panem):** tested through the parallel-trends check, which failed. Separately, with one control region, a Panem-specific shock such as its 10.9 pp sign-up drop in summer 2019 cannot be separated from the effect of the cut.
- **Exogenous allocation of the cut:** *unclear*. The regions were chosen, not randomized.
- **No anticipation** of the cut before spring 2019: *holds on an informal check*. In winter 2019 sign-up rose in both groups, and the gap versus Panem moved from −1.74 to −2.44 pp, small next to the +3.54 pp effect.
- **No spillovers** between treated regions and Panem (SUTVA): *not tested*.
- **Stable customer mix** across periods: *mostly holds*. The no-promo share of at-risk customers stayed between 74.3% and 75.4%. Caveat: Panem’s lapsed share went from 12.1% to 19.4% in summer 2019, and the cut changes who counts as a member.
- **Constant treatment effects** across regions and time: *holds*. All five regions were cut in the same season.
- **No other concurrent changes:** *violated for all-customer results*. Membership and total revenue include the promo grid moving from $10–$14 to $7–$11, so they are package effects. The +3.54 pp sign-up result covers people paying list price who were not offered a promo, so it is not the promo-grid package.
- **Additive region and season effects:** *sensitive*. The baseline model assumes each region has a fixed level and each season shifts all regions by the same amount, so region and season effects simply add up. Allowing each region its own seasonal pattern (region × season-of-year effects) cuts the sign-up gain from +3.54 to +1.03 pp, membership gain from +11.23 to +8.07 pp, and turns revenue per customer-season slightly negative (from +$0.35 to −$0.06). The headline result depends on that shared seasonal pattern. This region × season-of-year model is a separate specification from the pre-trend test above: the pre-trend test rejects flat pre-cut gaps, and this specification shrinks the estimated gain.
- **Independence across customers, not across seasons:** standard errors clustered by customer.
- **Marketing exposure comparable across regions:** *assumed true*. Ad spend is identical per region.

**Results** **are descriptive upper-end estimates, not clean causal effects.**

Each lift is the five regions after the cut, relative to Panem (+2.43% counterfactual sign-up rate). Lapsed, new, and lapsed plus new are people in that group paying list price. On those rows, membership and sign-up are the same fit. Lapsed + new (acquisition revenue including promos) is lapsed and new customers, including promo offers. On that row, membership and sign-up are the same fit. Recurring and total pooled include every customer in the group. The ± on each lift is the 95% margin, customer clustered standard errors to account for customer bias.

| User group                          | N (% of customer-seasons) | Sign-up lift     | Membership lift   | Revenue lift         |
| ----------------------------------- | ------------------------- | ---------------- | ----------------- | -------------------- |
| Recurring (including promos)       | 741k (13.2%)              |                  | +2.56 ± 0.48      | −$2.64 ± $0.08       |
| Lapsed (excluding promos)          | 424k (7.6%)               | +14.61 ± 0.60    | +14.61 ± 0.60     | +$1.51 ± $0.08       |
| New (excluding promos)             | 4.45M (79.2%)             | +3.77 ± 0.09     | +3.77 ± 0.09      | +$0.415 ± $0.012     |
| **Lapsed + new (excluding promos)** | **4.87M (86.8%)**         | **+3.54 ± 0.09** | **+3.54 ± 0.09**  | **+$0.348 ± $0.013** |
| Lapsed + new (including promos)     | 4.87M (86.8%)             | +4.32 ± 0.10     | +4.32 ± 0.10      | +$0.337 ± $0.012     |
| **Total pooled (including promos)** | **5.61M (100%)**          |                  | **+11.23 ± 0.16** | **+$0.353 ± $0.021** |

Recurring users do not have a sign-up model as this would be measuring retention and mix the objective of list price cut feasibility with churn. Total pooled does not have a sign-up model as this would mix people who can join with people who are already members which blends join rate (objective) with how large the recurring group is. Churn is already modeled in the membership equation for these groups.

A $12 joiner pays 20% less than a $15 joiner, so sign-ups must rise 0.61 pp (25% of the 2.43% counterfactual rate) to match $15 revenue. The +3.54 pp gain clears that. Membership and total revenue rise because the member base grows, even though members who stay pay $8.96 after the cut against $11.89 before, about $2.93 less. The cut also moved the promo grid down, so these are package effects.

The gain is **not a clean causal effect**. A joint test rejects flat pre-cut gaps (χ² = 2,335, 7 degrees of freedom, p < 0.001), and the pre-cut gaps range from −0.18 to +2.35 pp against +3.41 to +6.11 pp after the cut.

The direction holds on sign-ups and memberships, but the revenue gain turns slightly negative under region-by-season controls. Summer 2019 is the main worry: Panem's own sign-up fell 10.9 pp, and with one control region a Panem-specific shock cannot be separated from the effect of the cut. Confidence is moderate on memberships, low to moderate on the size of the sign-up gain, and low on revenue.

Under the baseline, sign-up is +3.54 pp, membership is +11.23 pp, and revenue per customer-season is +$0.35. Allowing each region its own seasonal pattern cuts those to +1.03 pp, +8.07 pp, and −$0.06. 

## Limitations and Next Steps

Post-cut revenue is still rising at $11, and promos above $11 were not randomized, so $11 versus the $12 list price is untested. $7 is the bottom of the grid, so nothing here speaks to deeper discounts. Deep-discount members may churn faster, which would overstate $7. The all-eligible dollar depends on the type mix (57% recurring post-cut). It is not known that the firm can price by type. Only $12 was observed, so $13 and $14 are untested. Totals count customer-seasons, not unique customers, and the $4.05 million pre-cut and $2.80 million post-cut totals are not comparable.

Next: (1) randomized list-price test, $12 against $13 or $14, across several regions; (2) a retention model by dollar at sign-up to settle $7 versus $11; (3) a price-by-region test within each user type; (4) an event-study and leave-one-region-out check on the cut; (5) adding controls for spend level per channel; (6) a Poisson specification.
