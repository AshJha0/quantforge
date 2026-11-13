# AAD core on the rates models (Q3b)

Spec version 1.0.0. Status: Specified (stage G, wave 3d). Rulings: `stage-g-rulings.md` G-9, G-35. Suite `stage_g/aadladder_g` (5 cases: 3 values, 2 errors), written by `oracle/python/gen_stage_g_q3b.py`.

**Plain idea.** A trader needs the price of a Bermudan swaption and also how it moves when each curve point, the mean reversion and the volatility move: the "ladder". Bumping each input and repricing costs one pricing per input. Reverse-mode automatic differentiation (AAD) records the pricing once and runs it backwards, so the whole ladder costs a small fixed multiple of one pricing, whatever the number of inputs [Giles and Glasserman, "Smoking adjoints", *Risk*, January 2006; Griewank and Walther, *Evaluating Derivatives*, 2nd ed., SIAM, 2008, chapter 3 (not opened)]. Q3b builds that core in all four languages on the Hull-White Bermudan of wave 2d and checks it against a bump reference.

Formal statement. Let `V(theta)` be the G-18 reference scheme price (`rates.shortrate.bermudan_swaption`), with `theta` the curve discount factors `P_1, ..., P_m`, `a` and `sigma`. The ladder is `dV/dtheta`, the derivative of the **discrete scheme** (not of the continuous model): AAD differentiates exactly what is computed, including the Thomas solve and the exercise `max`, taken as its active branch. **Convention, stated so it cannot be misread (R6, 2026-11-12):** `d_price_d_discount_factors[i]` is the derivative, per unit change of the input discount factor `P_i` (absolute, not relative, not per bp of a rate), of the scheme price at the case's own grid (`nx`, `steps_per_year`, `width`). It is not the derivative of the continuous Hull-White price, and the two differ by much more than the prices do: on `aadladder_g-0001` the 1-year entry is 191,964 at the golden grid (101 points, 50 steps a year), 220,895 at 401 and 200, 225,712 at 801 and 400, while the price moves only from 22,697.8 to 22,751.8 (0.24%). A converged library derivative (QuantLib `FdHullWhiteSwaptionEngine` on a fine grid) is therefore not an outside check of these entries; only the price, `d_price_d_mean_reversion` and `d_price_d_sigma` can be compared that way, with a tolerance measured for each derivative, not taken from the price.

## `rates.shortrate.bermudan_ladder`

Inputs: exactly those of `rates.shortrate.bermudan_swaption`, with its errors and limits (G-31).

Outputs (ruling R6-27; each is a derivative of the **discrete scheme at the case's grid**, not a model sensitivity):
- `price`: the G-18 scheme price at the case grid.
- `d_price_d_discount_factors` (one per curve pillar, in order): the scheme price's derivative per unit absolute change of each input discount factor.
- `d_price_d_mean_reversion`, `d_price_d_sigma`: the scheme price's derivative per unit change of `a` and of `sigma`.

**Use restriction: not for hedging at the default grid.** At 101 space points and 50 steps a year the discount-factor entries differ from the converged ones by up to about 18% while the price differs by 0.24% (`oracle/R6_LADDER_GRIDS.json`). Use a finer grid (the `r6/aadladder_r6` golden shows one within 2% of the 801/400 reference on every entry) or treat the ladder as a test of the AAD, not as a hedge ratio. The real fix, a second-order scheme or Richardson extrapolation so the default grid is within 1%, is stage K item K-8.

Reference (the golden). Richardson-extrapolated central differences of the binary64 scheme with relative bumps `h = 1e-4` and `5e-5`: `D(h) = (V(x(1+h)) - V(x(1-h)))/(2 h x)`, `ref = (4 D(h/2) - D(h))/3`, the Q3a rule (`book-sensitivities.md`). A second pair (`5e-5`, `2.5e-5`) must agree with the first within 1e-9 relative (of the larger of the value and 1e-6 x notional). If it does not, a bump has moved an exercise decision across a grid node, the derivative is not defined there, and the case is dropped. One of the four candidate cases (`bermudan_g-0001` at the coarser grid) was dropped this way (agreement 1.1e-9).

Tolerance (G-9): `abs(AAD - ref) <= 1e-10 + 1e-8 abs(ref)` per unit notional, class `aad_sensitivity`; the price at 1e-9 relative.

Worked example (`aadladder_g-0001`, from `bermudan_g-0002` on `nx = 101`, 50 steps a year). Price 22,697.81 per 1,000,000. `dV/dsigma = 2,269,595`: a 1 bp rise in `sigma` adds about 227. `dV/da = -52,528`: more mean reversion damps rate moves and cheapens the option. Per unit change of each discount factor: the 6-month pillar 127, the 1- to 3-year pillars +191,964, +173,816, +147,510, the 5- and 7-year pillars -233,482 and -343,473 (a higher long discount factor lowers the forward swap rate of a payer), and 0 beyond the last payment.

## Performance acceptance (G-9)

Median of 21 timed runs after 5 warm-ups of (a) one price and (b) price plus full ladder by reverse-mode AAD, same process and thread, on `aadladder_g-0001`'s inputs. Pass when `median(b)/median(a) <= 5`. Each language reports the ratio in its benchmark output; this spec session has no AAD build, so no ratio is recorded here.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Richardson central differences | `h^4` truncation; two pairs agree within 1e-9 relative | the three kept cases: agreement 2.9e-10, 6.8e-10, 9.0e-10 | a bump crossing an exercise node: the case is dropped, not judged | Q3a rule |
| AAD of the scheme | exact to rounding | language builds against `aadladder_g` | none | the bump reference |

Outside: none. No library differentiates this scheme (G-18).
