# Lorehaven Pricing Simulator

A one-page tool for a pricing or business lead. It shows how a promo dollar or the $15 to $12 list-price cut would change membership 
and revenue this season. Revenue is not profit. Cost to serve is assumed to be zero.

## Setup

From `lorehaven_sim/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows, activate with `.venv\Scripts\activate`. Then open the local URL Streamlit prints. Dependencies are pinned in `requirements.txt`.

## Usage

Choose Promo price or List price.

Promo price sets the offer dollar for Everyone, Recurring, Lapsed, or New.  Tested promos exist only at a $12 list ($7–$11) and a $15 list ($10–$14). 
Current policy is list $12 and promo $11. Revenue-max this season picks the promo with the highest this-season revenue at list $12. 
Compare to current policy shows the change against that policy.

List price shows the $15 to $12 cut for Total pooled, Recurring, Lapsed, New, and the two lapsed-plus-new groups. $12 and $15 are marked Observed. 
A price between them is read off a straight line.

The basic assistant answers a fixed set of questions from the simulator. The AI assistant is optional. It needs a passcode and an API key, 
entered locally in `lorehaven_sim/.streamlit/secrets.toml` or in the host's secret settings. Do not commit those values. 
`.streamlit/secrets.toml.example` has placeholders only.

## Key assumptions

Numbers come from the saved estimates. The page does not fit a new model.

A promo inside a tested grid was randomized, so confidence is High. A promo outside that grid is not a tested result, and confidence is Low.

The list-price comparison uses Panem as the only holdout. Pre-period trends do not line up, so the result is directional, not a clean causal estimate. Confidence is Low. The slider between $12 and $15 was not tested.

When two prices are too close to separate, the page shows the one with higher this-season revenue. Later seasons are not estimated.
