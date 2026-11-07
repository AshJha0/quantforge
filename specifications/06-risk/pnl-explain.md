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
- `threshold = max(0.05 |full_pnl|, 0.05 |par_dv01|)`, with `par_dv01` the sum of `par_buckets`;
- `explained`: `true` when `|unexplained| <= threshold`.

The threshold is 5% of the day's P&L, with a floor of 5% of one basis point of DV01, so quiet days are not failed on noise. A day fails when second-order terms (convexity, cross-gamma) exceed that, as they do on large moves for long-dated products. Plan 11.2.1 asks for a stated threshold; this is it, and it is fixed here, not tuned per product.

Checks: those of `risk.curve.par`, then the tenor match (`E_INPUT`).

## Real historical moves

`tools/workflows/pnl_explain.py` runs the control over real daily moves. Data: the US Treasury daily par yield curve, bootstrapped with SOFR OIS conventions. This is the same proxy curve as workflow (a), labelled the same way: Treasury par yields are not SOFR swap rates. For each pair of consecutive published days it uses the tenors present on both days, and sends one case per product of a fixed sample book through the CLI's `--batch` mode. The tool holds no financial logic.

Report, dated, per product:
- days run, days explained, and the explained share;
- percentiles (50, 95, 99) of `|unexplained| / max(|full_pnl|, |par_dv01|)`;
- the five worst days, with their largest quote move.

Acceptance (R2): at least 95% of days explained for every product in the book, over every year run. A product below that is reported, not hidden, with its worst days. Every report is labelled *real moves of a proxy curve; synthetic product terms*.

## Acceptance (goldens)

The goldens use synthetic moves: parallel, twist and shock, from 1 bp to 150 bp. `explained` is exact (`date_and_convention`). The generator stops if any case's `|unexplained|` lies within 10% of its `threshold`, so curve-solve noise cannot flip the flag. Numbers use the `risk.curve.par` limits. Values and buckets are re-priced in QuantLib, as in `par-and-key-rate.md`.
