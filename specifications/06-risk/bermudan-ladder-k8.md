# Bermudan sensitivity ladder at the default grid (stage K item K-8, R6-27)

Spec version 0.1.0. Status: **PROPOSED** (stage K wave 1). Rulings: `stage-k-rulings-w1.md` KR-8, KR-9. Depends on `04-pricing/short-rate-models.md` (G-18 scheme, unchanged) and `aad-core.md`.

**Plain idea.** The ladder of the pinned G-18 scheme is the exact derivative of a first-order scheme, and at the default grid that derivative is far from the model's: the price is within 0.2% but single ladder entries are off by up to 11%. Plan K-8 asks for every entry within 1% of the converged model derivative at the default grid. This spec says how, and why Richardson extrapolation alone is not the answer.

## What the R6 grid file already shows (`oracle/R6_LADDER_GRIDS.json`, read 2026-11-18)

Gap of the discount-factor entries (indices 0..5) at a grid against the 801/400 grid, percent:

| Case | 201/100 (default) | 101/50 (golden) |
|---|---|---|
| aadladder_g-0001 | 0.0, -6.4, +10.9, -4.0, -1.2, -0.1 | +0.1, -15.0, +9.9, +11.9, -0.4, -1.2 |
| aadladder_g-0002 | +0.1, +2.1, -3.3, +0.4, -1.6, +0.2 | +0.3, -9.6, +9.0, +3.5, +5.8, -0.2 |
| aadladder_g-0003 | +0.2, +7.8, +2.4, -2.1, +3.8, +1.1 | +0.5, -4.5, +15.2, -7.5, +0.4, +2.1 |

Two facts matter. (1) Several entries do not converge monotonically: aadladder_g-0002 entry 1 reads 87,159, 98,464, 102,352, 93,700, 96,435 on the five grids. (2) Even 801/400 is not converged for those entries (401/200 and 801/400 differ by 2.8%), so 801/400 cannot serve as the reference for a 1% test. The likely cause is the exercise boundary crossing grid nodes: the derivative of a pointwise `max` jumps when the boundary moves to the next node. A second-order time scheme alone does not remove that.

## Proposed method `CN_RANNACHER_SMOOTHED` (KR-8)

1. Same state, grid and exercise value as G-18 steps 1 to 4.
2. Time stepping: Crank-Nicolson (theta = 1/2) with Rannacher start-up: after the maturity payoff and after each exercise date, two fully implicit steps of half size replace the first full step [Rannacher, "Finite element solution of diffusion problems with irregular data", *Numer. Math.* 43 (1984) 309-327 (not free; idea restated in Giles and Carter, "Convergence analysis of Crank-Nicolson and Rannacher time-marching", *J. Comput. Finance* 9(4) 2006, free preprint, UNVERIFIED)].
3. Exercise smoothing: at each exercise date, node `i` takes the average of `max(V, E)` over its cell `[x_i - dx/2, x_i + dx/2]`, with `V` and `E` linear between nodes, computed in closed form (split the cell at the crossing of `V - E` if inside it). This makes the price a smooth function of the inputs, so its derivative converges [Pooley, Vetzal, Forsyth, "Convergence remedies for non-smooth payoffs in option pricing", *J. Comput. Finance* 6(4) 2003, free preprint (UNVERIFIED)].
4. Ladder by reverse-mode AAD of this scheme, as `aad-core.md`.
5. Richardson only through `num.richardson.check` (KR-9), never unguarded.

## `num.richardson.check` (guard helper, four languages)

Inputs: `values` `[f(h), f(h/r), f(h/r^2)]`, `ratio` r > 1, `assumed_order` p > 0. Outputs: `status` (`OK`, `ORDER_MISMATCH`, `NON_MONOTONE`), `observed_order` `log((f1 - f2)/(f2 - f3)) / log r` (null if the differences have opposite signs or one is zero), `extrapolated` `(r^p f3 - f2)/(r^p - 1)` when `OK`, else null. `OK` iff same-sign differences and `|observed - assumed| <= 0.5`.

Output fields compared: `status` (string), `observed_order` (binary64 or `null`), `extrapolated` (binary64 or `null`). Error cases compare `error.code` (string) only.

| Case | values | ratio | assumed_order | Expected status | Expected observed_order | Expected extrapolated |
|---|---|---|---|---|---|---|
| rich_k-0001 | [10.5, 10.125, 10.03125] | 2 | 2 | OK | 2 (exact) | 10.0 (exact) |
| rich_k-0002 | [11, 10.5, 10.25] | 2 | 2 | ORDER_MISMATCH | 1 (exact) | null |
| rich_k-0003 | [11, 10.5, 10.25] | 2 | 1 | OK | 1 | 10.0 (exact) |
| rich_k-0004 | [98464, 93700, 96435] (aadladder_g-0002 entry 1 at 201, 401, 801, rounded) | 2 | 2 | NON_MONOTONE | null | null |
| rich_k-0005 | [211255, 220895, 225712] (aadladder_g-0001 entry 1, rounded) | 2 | 2 | ORDER_MISMATCH | 1.0008982225303467 | null |
| rich_k-0006 | [211255, 220895, 225712] | 2 | 1 | OK | 1.0008982225303467 | 230,529 |

<!-- blind:strip -->
rich_k-0005/0006 show the G-18 ladder entry converging at first order (as G-18 says of the price), so a first-order extrapolation from the three finest grids gives 230,529, a further 2.1% above 801/400: the scale of what K-8 has to fix.
<!-- /blind:strip -->

| Case | values | ratio | assumed_order | Expected error.code |
|---|---|---|---|---|
| rich_k-0007 | [10.5, 10.125, 10.03125] | 1 | 2 | E_DOMAIN |
| rich_k-0008 | [10.5, 10.125] | 2 | 2 | E_INPUT |

## Acceptance (fixed before any run; plan 14.8 K-8)

1. Reference ("converged model derivative"): central bump-and-revalue with QuantLib `FdHullWhiteSwaptionEngine` at a fine grid (proposed tGrid 2,000, xGrid 801), relative bump 1e-4 on each discount factor, repeated at 5e-5; the two must agree within 0.1% or the entry is reported as unresolved. Cross-check: `CN_RANNACHER_SMOOTHED` at 801/400 and 1601/800 agree with each other within 0.2%. Both are required (owner decision K-QA, 2026-11-18); QuantLib is the counted outside check.
2. At the default grid 201/100, every ladder entry of aadladder_g-0001..0003 with `|reference| >= 1e-3 max |reference|` is within 1% of the reference; `d_price_d_mean_reversion` and `d_price_d_sigma` too.
3. Observed order of the new method's price and ladder, by `num.richardson.check` on 201/401/801, between 1.5 and 2.5 with status `OK` on every entry. If any entry is `NON_MONOTONE`, step 3 of the method is not working and the test fails, whatever step 2 says.
4. The R6 use restriction is removed from docs and the model inventory only for `CN_RANNACHER_SMOOTHED`, only after 1 to 3 pass; G-18 goldens unchanged.
5. AAD of the new scheme equals its own Richardson bump reference to 1e-8 relative (the aad-core rule).

If 2 fails after the method is built, K-8 moves to a point release under the plan 15 gate rule and the restriction stays; the default grid is not redefined to pass (owner decision K-QB, 2026-11-18).
