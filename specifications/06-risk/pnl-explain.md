# P&L explain

Spec version 1.0.0. Status: Specified (phase R2, plan 11.2.1). Goldens: `datasets/golden/r2/pnl_r2.json`, written by `oracle/python/gen_r2_pnl.py`. Real-data run: `tools/workflows/pnl_explain.py`.

The desk control: the P&L that risk predicts from a market move must match the P&L from full revaluation, within a stated unexplained-P&L threshold. It tests the curve, the pricer and the risk together.

## `risk.pnl.explain`

Inputs: `as_of`, `convention`, `interpolation`, `quotes_start`, `quotes_end`, `product` (as `par-and-key-rate.md`: `OIS` or `BOND`), `bump_bp` (as there; default 1).

`quotes_start` and `quotes_end` must have the same tenors in the same order, else `E_INPUT`. Both curves are built by `rates.ois.bootstrap` on the same `as_of`. This is a pure market-move P&L: no time passes, so there is no carry, roll-down or theta. Those terms come in stage F.

Outputs:
- `value_start`, `value_end`: the product on each curve;
- `full_pnl = value_end - value_start`;
- `par_buckets`: `risk.curve.par` buckets at the start curve, central, with `bump_bp`;
- `risk_pnl = sum_j par_buckets[j] (q_end[j] - q_start[j]) / 0.0001`: first order in par quotes;
- `unexplained = full_pnl - risk_pnl`;
- `gross_risk_pnl = sum_j |par_buckets[j]| |q_end[j] - q_start[j]| / 0.0001`: the first-order P&L with every term counted as a loss or gain in full, so offsetting buckets cannot hide a move;
- `threshold = 0.05 max(|full_pnl|, gross_risk_pnl) + 1e-8 N`, with `N` the product's notional. The last term is a numerical floor equal to the golden tolerance, not a risk allowance;
- `explained`: `true` when `|unexplained| <= threshold`.

The threshold scales with the size of the day's move (ruling R2-A3). A quiet day has a small threshold, so it cannot pass vacuously. A day with no move to which the product is exposed has only the numerical floor as its threshold, and counts as explained when risk and revaluation agree to rounding. A day fails when second-order terms (convexity, cross-gamma) exceed 5% of the larger of the realised P&L and the gross first-order P&L, as they do on large moves for long-dated products.

The 5% level is a **project choice**, fixed here and not tuned per product (ruling R2-A4). It is not the Basel FRTB P&L attribution test, which compares risk-theoretical and hypothetical P&L over a 250-day window with Spearman correlation and Kolmogorov-Smirnov statistics. The real-data run reports those two statistics alongside, unjudged.

Checks: those of `risk.curve.par`, then the tenor match (`E_INPUT`).

## Real historical moves

`tools/workflows/pnl_explain.py` runs the control over real daily moves. Data: the US Treasury daily par yield curve, bootstrapped with SOFR OIS conventions. This is the same proxy curve as workflow (a), labelled the same way: Treasury par yields are not SOFR swap rates. For each pair of consecutive published days it uses the tenors present on both days, and sends one case per product of a fixed sample book through the CLI's `--batch` mode. The tool holds no financial logic.

Report, dated, per product:
- days run, days explained, and the explained share;
- percentiles (50, 95, 99) of `|unexplained| / max(|full_pnl|, |par_dv01|)`;
- the five worst days, with their largest quote move;
- over the window, the Spearman rank correlation and the two-sample Kolmogorov-Smirnov statistic between daily `full_pnl` and `risk_pnl`. These are reported and not judged, in the style of the FRTB attribution test but without its thresholds.

Acceptance (R2): at least 95% of days explained for every product in the book, over every year run. A product below that is reported, not hidden, with its worst days. Every report is labelled *real moves of a proxy curve; synthetic product terms*.

## Acceptance (goldens)

The goldens use synthetic moves: parallel, twist and shock, from 1 bp to 150 bp. `explained` is exact (`date_and_convention`). The generator stops if any case's `|unexplained|` lies within 10% of its `threshold`, so curve-solve noise cannot flip the flag. Numbers use the `risk.curve.par` limits. Values and buckets are re-priced in QuantLib, as in `par-and-key-rate.md`.
