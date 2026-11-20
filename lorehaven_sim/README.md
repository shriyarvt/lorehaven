# Lorehaven Pricing Simulator

A one-page simulator for the promo-dollar test and the list-price cut. It shows revenue, not profit. Cost to serve is assumed to be zero.

The basic assistant is scripted. It has no model API, and the same question always gets the same answer. Every number comes from the simulator. An optional AI assistant runs only after a local passcode and API key are set. Those values belong in `.env` or `.streamlit/secrets.toml`. Git ignores both files. `.streamlit/secrets.toml.example` has placeholders only.

## Quickstart

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
pytest
```

On Windows, activate with `.venv\Scripts\activate` instead. Then open the local URL Streamlit prints. That address is this computer only.

## Usage

The mode switch picks the question:

- **Promo price.** Offer dollar for Everyone, Recurring, Lapsed, or New. Everyone uses the membership curve. Recurring uses the churn curve: revenue is the stay rate times the offer. Lapsed uses the rejoin curve and New uses the first-time join curve. Both are the clustered mean at each tested dollar. Promo curves exist only at list $12 ($7–$11) and list $15 ($10–$14).
- **List price.** One comparison, the $15 to $12 cut. Total pooled, Recurring, Lapsed, New, and the two lapsed-plus-new rows (excluding promos, and including promos) each use their own saved result. The page draws $12 and $15 as observed. A slider between them reads the straight line. That line was not tested.

Revenue is this season only. Presets:

- Current policy: list $12 and promo $11.
- Revenue-max this season: the promo that maximizes this-season revenue at list $12.

Turn on "Compare to current policy" to see the change against list $12 and promo $11. The page works with the assistant closed.

Confidence:

- **High.** A randomized promo inside the tested grid.
- **Low.** A price outside a promo test, the list-price comparison, or a list-price revenue claim. List price was not randomized.

## Key assumptions

- Promo dollars inside a tested grid are read on a straight line between the saved dollars. Outside the grid, the line continues from the two nearest dollars, a warning is shown, and confidence is Low.
- When two tested dollars have a gap whose 95% interval includes zero, the page shows the one with higher this-season revenue.
- The list-price page draws each group's $15 to $12 result as a line with a 95% interval. A slider from $12 to $15 reads that straight line. The linear-probability elasticity, about −4.0, is still the curve through the two observed sign-up rates. The page does not draw that curve. Promo price still accepts only $12 and $15.
- The $12 versus $15 comparison uses one control region, Panem, and the pre-trends fail. It is not a clean causal estimate.
- Revenue is not profit. Nothing is subtracted for the cost to serve.

## How to add or refresh estimates

Estimates live in `data/estimates.json`. The loader stops if a required table is missing. Per-type rate curves are not in that file. Everyone uses the membership curve. Other groups have a best dollar only.

To rebuild the file from the regression output at the repo root:

```bash
python analysis/export_estimates.py
```

That reads `output/discount/estimates.csv` and `output/list_price/`. It keeps full precision. If you add a per-type curve later, put it in the JSON and teach `sim/estimates.py` to read it. Do not type a curve in by hand.

## Screenshot

![Lorehaven Pricing Simulator](screenshot.png)

Save a screenshot of the running page as `lorehaven_sim/screenshot.png` when you want this image to resolve.

## Layout

`app.py` is the page. `sim/model.py` is the only place that calculates. `chat/` parses a fixed set of questions and fills reply templates from the model result. `tests/` covers the math, the input checks, the parser, and the replies.
