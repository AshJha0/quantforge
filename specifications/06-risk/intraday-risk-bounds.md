# Intraday risk with error bounds (stage K)

Spec version 0.1.0. Status: **PROPOSED** (stage K wave 1, plan 14.8 K-5). Rulings: `stage-k-rulings-w1.md` KR-7, KR-10.

**Plain idea.** Full revaluation of a book on every market move is slow. Delta and gamma, computed once, give a fast estimate. The estimate is only worth showing with a statement of how wrong it can be, and for smooth instruments Taylor's theorem gives that statement exactly.

**Formal statement.** For `V` three times differentiable on the segment between `x` and `x + h`, `|V(x + h) - V(x) - V'(x) h - V''(x) h^2 / 2| <= M3 |h|^3 / 6` with `M3 = max |V'''|` on the segment (Lagrange remainder) [any calculus text; e.g. Apostol, *Calculus* vol. 1, 2nd ed., Wiley 1967, section 7.7 (not free, definition only)]. For a zero-coupon position `V(y) = N exp(-y T)` (continuous yield): `V' = -T V`, `V'' = T^2 V`, `|V'''| = T^3 V`, decreasing in `y`, so `M3 = T^3 N exp(-T min(y, y + h))`.

## `risk.intraday.delta_gamma_bound`

Inputs: `positions` (list of `{notional N, maturity T > 0, yield y}`; empty `E_INPUT`; more than 100,000 `E_LIMIT`), `shift` `h` (parallel, decimal). Outputs: `estimate_pnl` (delta-gamma), `bound` (sum of position bounds), `label` (KR-10). The exact revaluation is not an output; it is what the acceptance test compares with.

## Golden value cases (hand-derived; 30-digit mpmath check)

One position, N = 1,000,000, T = 5, y = 0.04; `V(y) = 818,730.753077981859`.

| Case | h | Exact V(y+h) | Delta-gamma estimate of V(y+h) | Error (est - exact) | Bound | Error / bound |
|---|---|---|---|---|---|---|
| idr_k-0001 | +0.01 | 778,800.783071404868 | 778,817.628865430243 | 16.845794 | 17.056891 | 0.988 |
| idr_k-0002 | -0.01 | 860,707.976425057807 | 860,690.704173228429 | -17.272252 | 17.931416 | 0.963 |
| idr_k-0003 | +0.0025 | 808,560.316321452466 | 808,560.582004591303 | 0.265683 | 0.266514 | 0.997 |
| idr_k-0004 | +0.05 | 637,628.151621773293 | 639,633.400842173327 | 2,005.249220 | 2,132.111336 | 0.940 |

Outputs as P&L: `estimate_pnl = estimate - V(y)`; e.g. idr_k-0001 `estimate_pnl = -39,913.124212551616`, `bound = 17.056891` (to 1e-9 relative). Derivation of idr_k-0001: `V (1 - T h + T^2 h^2 / 2) = 818,730.753078 x 0.95125`; bound `= 0.01^3 x 125 / 6 x 818,730.753078`.

The bounds are tight (ratio near 1) because a zero bond's third derivative barely moves over the shift: a good test that the bound is not loosened by a factor nobody checks. Two positions: idr_k-0005 = the idr_k-0001 position plus N = -500,000, T = 2, y = 0.03, h = +0.01; the bound is the sum of the two position bounds (no netting of remainders, since their signs are unknown in general). Expected values are left for the oracle lane and the blind lane to compute from the formulas; this lane did not compute them.

Error cases: idr_k-0006 `T = 0` → `E_DOMAIN`; idr_k-0007 empty positions → `E_INPUT`.

## Acceptance (fixed before any run; plan K-5)

- idr_k-0001..0007 in four languages, 1e-9 relative.
- 1,000 random parallel moves (seeded, h uniform in [-0.02, 0.02]) on a seeded 50-position book: `|estimate - full revaluation| <= bound` on every move, and the 1,000 results logged.
- Instruments without a supplied `M3` are reported as "no bound" and excluded from the "with error bounds" claim. Described as latency-aware analytics on simulated data.
