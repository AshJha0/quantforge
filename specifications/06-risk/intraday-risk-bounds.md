# Intraday risk with error bounds (stage K)

Spec version 1.0.0. Status: **CONFIRMED** 2026-11-19, confirmed by the stage K coordinator lane (branch k-w1; was PROPOSED, version 0.1.0, stage K wave 1, plan 14.8 K-5). Rulings: `stage-k-rulings-w1.md` KR-7 (as corrected by KR-15 and completed by KR-17), KR-10.

**Plain idea.** Full revaluation of a book on every market move is slow. Delta and gamma, computed once, give a fast estimate. The estimate is only worth showing with a statement of how wrong it can be, and for smooth instruments Taylor's theorem gives that statement exactly.

**Formal statement.** For `V` three times differentiable on the segment between `x` and `x + h`, `|V(x + h) - V(x) - V'(x) h - V''(x) h^2 / 2| <= M3 |h|^3 / 6` with `M3 = max |V'''|` on the segment (Lagrange remainder) [any calculus text; e.g. Apostol, *Calculus* vol. 1, 2nd ed., Wiley 1967, section 7.7 (not free, definition only)]. For a zero-coupon position `V(y) = N exp(-y T)` (continuous yield): `V' = -T V`, `V'' = T^2 V`, `|V'''| = T^3 V`, decreasing in `y`, so `M3 = T^3 abs(N) exp(-T min(y, y + h))` (absolute value for a short position, KR-15). For a book the position bounds are summed without netting; the `bound` output is this exact-arithmetic bound evaluated in binary64, and the derivation and its rounding budget are in KR-17.

## `risk.intraday.delta_gamma_bound`

Inputs: `positions` (list of `{notional N, maturity T > 0, yield y}`; empty `E_INPUT`; more than 100,000 `E_LIMIT`), `shift` `h` (parallel, decimal). Outputs: `estimate_pnl` (delta-gamma), `bound` (sum of position bounds), `label` (KR-10). Arithmetic (added 2026-11-19 after the K-5a blind lane's notes; no value changes): per position `V = N exp(-y T)`, the estimate term `V (-T h) + V T^2 h^2 / 2` and the bound term `abs(h)^3 T^3 abs(N) exp(-T min(y, y + h)) / 6` are evaluated in binary64; the order of operations inside a term is not fixed. The `estimate_pnl` sum over positions may be exactly rounded or left to right; the `bound` sum is exactly rounded (KR-17). The order is left open on purpose: different orders change a result by a few ulp per position, and the 1e-9 relative tolerance of the goldens is far above that (the blind lane's values, computed in its own order with an exactly rounded estimate sum, differ from the goldens by at most 2.1e-16 relative). The exact revaluation is not an output; it is what the acceptance test compares with.

## Golden value cases (hand-derived; 30-digit mpmath check)

Output fields compared: `estimate_pnl` (binary64, delta-gamma estimate of `V(y + h) - V(y)` summed over positions), `bound` (binary64, sum of position bounds), `label` (string, KR-10). Tolerance 1e-9 relative on `estimate_pnl` and `bound`. Error cases compare `error.code` (string) only.

Cases 0001 to 0004: one position, `notional` N = 1,000,000, `maturity` T = 5, `yield` y = 0.04; input `shift` h as below.

| Case | h | Expected estimate_pnl | Expected bound | Expected label | Check exact V(y+h) | Check estimate of V(y+h) | Check error / bound |
|---|---|---|---|---|---|---|---|
| idr_k-0001 | +0.01 | -39,913.124212551616 | 17.05689068912462 | latency-aware analytics on simulated data | 778,800.783071404868 | 778,817.628865430243 | 0.988 |
| idr_k-0002 | -0.01 | 41,959.951095246570 | 17.93141617552204 | latency-aware analytics on simulated data | 860,707.976425057807 | 860,690.704173228429 | 0.963 |
| idr_k-0003 | +0.0025 | -10,170.171073390556 | 0.2665139170175722 | latency-aware analytics on simulated data | 808,560.316321452466 | 808,560.582004591303 | 0.997 |
| idr_k-0004 | +0.05 | -179,097.352235808532 | 2,132.1113361405783 | latency-aware analytics on simulated data | 637,628.151621773293 | 639,633.400842173327 | 0.940 |

<!-- blind:strip -->
Hand values: `V(y) = 818,730.753077981859`; `estimate_pnl` = the estimate column minus `V(y)`. Derivation of idr_k-0001: `V (1 - T h + T^2 h^2 / 2) = 818,730.753078 x 0.95125`; bound `= 0.01^3 x 125 / 6 x 818,730.753078`. The `bound` values above were first stated to six decimals; the oracle lane (`oracle/python/gen_stage_k_w1.py`, mpmath 50 digits, 2026-11-18) filled them to full binary64 precision. The wave-1 blind lane checked them only to six decimals (5e-7 absolute, `program/STAGE_K_BLIND_W1.md`), which `verified_by` in `idr_k.json` records. Error column `est - exact`: 16.845794, -17.272252, 0.265683, 2,005.249220.

The bounds are tight (ratio near 1) because a zero bond's third derivative barely moves over the shift: a good test that the bound is not loosened by a factor nobody checks.
<!-- /blind:strip -->

<!-- blind:strip -->
**idr_k-0005 (filled by the oracle lane 2026-11-18; not blind).** Positions: the idr_k-0001 position plus N = -500,000, T = 2, y = 0.03; h = +0.01. The bound is the sum of the two position bounds (no netting of remainders, since their signs are unknown in general), each with `|N|`. Expected (mpmath 50 digits, rounded once to binary64): `estimate_pnl` -30,589.655330067555, `bound` 17.684733711514124, label as above; check exact revaluation -30,605.876407770527, `est - exact` 16.221077702973727 (ratio to the bound 0.917). The case was not in the wave-1 blind packet, so it is not blind; it may enter a later packet. It entered the K-5a packet of 2026-11-19 and matched there (`program/STAGE_K_BLIND_K5A.md`).
<!-- /blind:strip -->

| Case | Input | Expected error.code |
|---|---|---|
| idr_k-0006 | one position N = 1,000,000, T = 0, y = 0.04; h = +0.01 | E_DOMAIN |
| idr_k-0007 | `positions` = []; h = +0.01 | E_INPUT |

## Acceptance (fixed before any run; plan K-5)

- idr_k-0001..0007 in four languages, 1e-9 relative (idr_k-0005 filled by the oracle lane, not blind).
- 1,000 random parallel moves (seeded, h uniform in [-0.02, 0.02]) on a seeded 50-position book: `|estimate - full revaluation| <= bound` on every move, and the 1,000 results logged.
- Instruments without a supplied `M3` are reported as "no bound" and excluded from the "with error bounds" claim. Described as latency-aware analytics on simulated data.

## Acceptance evidence (2026-11-19)

- idr_k-0001..0007 and the `e2_k` cases: pass in all four builds at 1e-9 relative. idr_k-0005 is filled from the oracle (mpmath, 50 digits) and is not blind.
- 1,000 moves on a seeded 50-position book (key `intraday_bound_1000_moves` in `program/stage_k_w1/acceptance_python.json` and `acceptance_java.jsonl`, each move logged as `[h, estimate_pnl, full_revaluation, bound]`): zero violations in Python (worst error over bound 0.0105) and Java (0.382; Java draws its own book from java.util.Random). Checked again at 50 digits by `oracle/python/check_stage_k_idr_moves.py` (`oracle/IDR_K_MOVES_CHECK_W1.json`): zero exact violations, binary64 rounding at most 2.3e-8 of the bound (KR-17). This is our own oracle, not an outside check.
- Outside share (2026-11-19, `program/STAGE_K_BLIND_K5A.md`): idr_k-0001..0005 re-derived blind by a different model (Claude Sonnet 5.5) from a packet with the golden tables, hand derivations and acceptance sections stripped; 5 of 5 MATCH at 1e-9 relative on full-precision values (largest relative difference 2.08e-16), `label` rules-stated and given no credit. K-5a outside share 5 of 5 (100%), blind re-derivation only. Limit: the deriver saw only our rules text, so this checks that the spec is unambiguous and its arithmetic right, not that the bound's derivation is right; the evidence for the inequality itself is the 50-digit recheck of the 1,000 moves above, which is our own oracle.

## Limits and open issues

- **Open audit finding (2026-11-19): KA-A6.** In binary64 the reported `bound` can be exceeded for very small moves: for one position with maturity 5 the error is 1.40 times the bound at a yield move of 1e-8 and 21.6 times at 1e-9 (absolute size about 1e-17 on a million). Register: `docs/known-issues.md`.
