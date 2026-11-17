# Interpolation backtests B1 and B2: results (stage J wave 3)

Run once on 2026-11-15 by `research/interp_backtest/run_interp_backtest.py`; raw numbers in `results.json`. Pass rules: `specifications/11-research/interp-backtest.md` section "Pass rules", committed in `c41f629` before any run. Label: *method test; B1 on a synthetic SSVI surface, real option quotes not done; B2 on par yields, not tradable instruments.*

| Backtest | Rule | Result | Verdict |
|---|---|---|---|
| B1 (a) leave one strike out, `cubic_natural` on total variance, 28 errors | max at most 0.25 vol pts | **0.370** vol pts (ATM strike, T = 0.25) | **FAIL** |
| B1 (b) alternate strikes held out, 16 errors | max at most 0.50 vol pts | 0.355 vol pts | pass |
| **B1 overall** | both | | **FAIL** |
| B2 leave one tenor out, `monotone_pchip`, 3M to 10Y pooled, 9,992 errors (1,249 rows, 3 skipped for blanks) | median at most 3 bp and 95th pct at most 15 bp | median **2.62** bp, 95th pct **14.19** bp | **PASS** (narrow) |

For information (not judged): B1 `linear` 1.82 / 1.69 vol pts, `monotone_pchip` 1.64 / 1.64 vol pts for (a) / (b). B2 `linear` median 4.0 bp, 95th 24.0 bp; `cubic_natural` 3.12 / 15.81 bp. 20Y (not judged): `monotone_pchip` median 10.9 bp, 95th 39.4 bp, as the prior note expected. Per-tenor 95th percentiles for `monotone_pchip`: 3M 14.4, 6M 19.6, 1Y 10.7, 2Y 11.2, 3Y 9.1, 5Y 12.3, 7Y 7.6, 10Y 17.2 bp.

## Reading

- B1 fails on the shortest expiry: at T = 0.25 the SSVI smile is sharply curved at the money (`phi` near 10), and a natural spline through strikes 0.1 apart misses the hidden ATM point by 0.37 vol points. Longer expiries are well inside the rule. The rule stands; no threshold is changed after the run.
- B2 passes by a small margin on both parts; `linear` would have failed. Several single tenors (6M, 10Y) have 95th percentiles above 15 bp; the rule is pooled, as fixed.

## Disclosure

The golden generator `gen_stage_j_w3.py` (commit `02304df`, after the rule commit and before this run) computes two B1 surfaces (design b and the ATM strike alone) and one B2 row (2020-02-19) as conformance cases, so those numbers were on screen before this run. The rules were already committed. Self-assessment; no different-model audit yet (plan 14.10 rule 5).
