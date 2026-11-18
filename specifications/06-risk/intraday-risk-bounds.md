# Intraday risk with error bounds (stage K)

Spec version 0.1.0. Status: **PROPOSED** (stage K wave 1, plan 14.8 K-5). Rulings: `stage-k-rulings-w1.md` KR-7, KR-10.

**Plain idea.** Full revaluation of a book on every market move is slow. Delta and gamma, computed once, give a fast estimate. The estimate is only worth showing with a statement of how wrong it can be, and for smooth instruments Taylor's theorem gives that statement exactly.

**Formal statement.** For `V` three times differentiable on the segment between `x` and `x + h`, `|V(x + h) - V(x) - V'(x) h - V''(x) h^2 / 2| <= M3 |h|^3 / 6` with `M3 = max |V'''|` on the segment (Lagrange remainder) [any calculus text; e.g. Apostol, *Calculus* vol. 1, 2nd ed., Wiley 1967, section 7.7 (not free, definition only)]. For a zero-coupon position `V(y) = N exp(-y T)` (continuous yield): `V' = -T V`, `V'' = T^2 V`, `|V'''| = T^3 V`, decreasing in `y`, so `M3 = T^3 N exp(-T min(y, y + h))`.

## `risk.intraday.delta_gamma_bound`

Inputs: `positions` (list of `{notional N, maturity T > 0, yield y}`; empty `E_INPUT`; more than 100,000 `E_LIMIT`), `shift` `h` (parallel, decimal). Outputs: `estimate_pnl` (delta-gamma), `bound` (sum of position bounds), `label` (KR-10). The exact revaluation is not an output; it is what the acceptance test compares with.

## Golden value cases (hand-derived; 30-digit mpmath check)

Output fields compared: `estimate_pnl` (binary64, delta-gamma estimate of `V(y + h) - V(y)` summed over positions), `bound` (binary64, sum of position bounds), `label` (string, KR-10). Tolerance 1e-9 relative on `estimate_pnl` and `bound`. Error cases compare `error.code` (string) only.

Cases 0001 to 0004: one position, `notional` N = 1,000,000, `maturity` T = 5, `yield` y = 0.04; input `shift` h as below.

| Case | h | Expected estimate_pnl | Expected bound | Expected label | Check exact V(y+h) | Check estimate of V(y+h) | Check error / bound |
|---|---|---|---|---|---|---|---|
| idr_k-0001 | +0.01 | -39,913.124212551616 | 17.056891 | latency-aware analytics on simulated data | 778,800.783071404868 | 778,817.628865430243 | 0.988 |
| idr_k-0002 | -0.01 | 41,959.951095246570 | 17.931416 | latency-aware analytics on simulated data | 860,707.976425057807 | 860,690.704173228429 | 0.963 |
| idr_k-0003 | +0.0025 | -10,170.171073390556 | 0.266514 | latency-aware analytics on simulated data | 808,560.316321452466 | 808,560.582004591303 | 0.997 |
| idr_k-0004 | +0.05 | -179,097.352235808532 | 2,132.111336 | latency-aware analytics on simulated data | 637,628.151621773293 | 639,633.400842173327 | 0.940 |

<!-- blind:strip -->
Hand values: `V(y) = 818,730.753077981859`; `estimate_pnl` = the estimate column minus `V(y)`. Derivation of idr_k-0001: `V (1 - T h + T^2 h^2 / 2) = 818,730.753078 x 0.95125`; bound `= 0.01^3 x 125 / 6 x 818,730.753078`. The `bound` values above are stated to six decimals only, short of the 1e-9 relative tolerance: the oracle lane (mpmath, 30 digits) fills them to full precision before any language lane is scored against them. Error column `est - exact`: 16.845794, -17.272252, 0.265683, 2,005.249220.

The bounds are tight (ratio near 1) because a zero bond's third derivative barely moves over the shift: a good test that the bound is not loosened by a factor nobody checks.
<!-- /blind:strip -->

<!-- blind:strip -->
**idr_k-0005 (ORACLE-PENDING, not in the blind packet).** Positions: the idr_k-0001 position plus N = -500,000, T = 2, y = 0.03; h = +0.01. The bound is the sum of the two position bounds (no netting of remainders, since their signs are unknown in general). Output fields as above. Expected values are not hand-derivable exactly (exponentials of non-trivial arguments) and are left for the oracle lane (mpmath, 30 digits); this lane did not compute them. The case enters a blind packet only after the oracle fills it, in a later wave.
<!-- /blind:strip -->

| Case | Input | Expected error.code |
|---|---|---|
| idr_k-0006 | one position N = 1,000,000, T = 0, y = 0.04; h = +0.01 | E_DOMAIN |
| idr_k-0007 | `positions` = []; h = +0.01 | E_INPUT |

## Acceptance (fixed before any run; plan K-5)

- idr_k-0001..0004, 0006, 0007 in four languages, 1e-9 relative; idr_k-0005 once the oracle lane fills it.
- 1,000 random parallel moves (seeded, h uniform in [-0.02, 0.02]) on a seeded 50-position book: `|estimate - full revaluation| <= bound` on every move, and the 1,000 results logged.
- Instruments without a supplied `M3` are reported as "no bound" and excluded from the "with error bounds" claim. Described as latency-aware analytics on simulated data.
