# AAD core on the rates models (Q3b)

Spec version 1.0.0. Status: Specified (stage G, wave 3d). Rulings: `stage-g-rulings.md` G-9, G-35. Suite `stage_g/aadladder_g` (5 cases: 3 values, 2 errors), written by `oracle/python/gen_stage_g_q3b.py`.

**Plain idea.** A trader needs the price of a Bermudan swaption and also how it moves when each curve point, the mean reversion and the volatility move: the "ladder". Bumping each input and repricing costs one pricing per input. Reverse-mode automatic differentiation (AAD) records the pricing once and runs it backwards, so the whole ladder costs a small fixed multiple of one pricing, whatever the number of inputs [Giles and Glasserman, "Smoking adjoints", *Risk*, January 2006; Griewank and Walther, *Evaluating Derivatives*, 2nd ed., SIAM, 2008, chapter 3 (not opened)]. Q3b builds that core in all four languages on the Hull-White Bermudan of wave 2d and checks it against a bump reference.

Formal statement. Let `V(theta)` be the G-18 reference scheme price (`rates.shortrate.bermudan_swaption`), with `theta` the curve discount factors `P_1, ..., P_m`, `a` and `sigma`. The ladder is `dV/dtheta`, the derivative of the **discrete scheme** (not of the continuous model): AAD differentiates exactly what is computed, including the Thomas solve and the exercise `max`, taken as its active branch.

## `rates.shortrate.bermudan_ladder`

Inputs: exactly those of `rates.shortrate.bermudan_swaption`, with its errors and limits (G-31).

Outputs: `price`; `d_price_d_discount_factors` (one per curve pillar, in order); `d_price_d_mean_reversion`; `d_price_d_sigma`.

Reference (the golden). Richardson-extrapolated central differences of the binary64 scheme with relative bumps `h = 1e-4` and `5e-5`: `D(h) = (V(x(1+h)) - V(x(1-h)))/(2 h x)`, `ref = (4 D(h/2) - D(h))/3`, the Q3a rule (`book-sensitivities.md`). A second pair (`5e-5`, `2.5e-5`) must agree with the first within 1e-9 relative (of the larger of the value and 1e-6 x notional). If it does not, a bump has moved an exercise decision across a grid node, the derivative is not defined there, and the case is dropped. One of the four candidate cases (`bermudan_g-0001` at the coarser grid) was dropped this way (agreement 1.1e-9).

Tolerance (G-9): `abs(AAD - ref) <= 1e-10 + 1e-8 abs(ref)` per unit notional, class `aad_sensitivity`; the price at 1e-9 relative.

Worked example (`aadladder_g-0001`, from `bermudan_g-0002` on `nx = 101`, 50 steps a year). Price 22,697.81 per 1,000,000. `dV/dsigma = 2,269,595`: a 1 bp rise in `sigma` adds about 227. `dV/da = -52,528`: more mean reversion damps rate moves and cheapens the option. The 6-month pillar has almost no effect (127 per unit change of its discount factor); the 1-year pillar has the largest (191,964), because the first exercise date is there.

## Performance acceptance (G-9)

Median of 21 timed runs after 5 warm-ups of (a) one price and (b) price plus full ladder by reverse-mode AAD, same process and thread, on `aadladder_g-0001`'s inputs. Pass when `median(b)/median(a) <= 5`. Each language reports the ratio in its benchmark output; this spec session has no AAD build, so no ratio is recorded here.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Richardson central differences | `h^4` truncation; two pairs agree within 1e-9 relative | the three kept cases: agreement 2.9e-10, 6.8e-10, 9.0e-10 | a bump crossing an exercise node: the case is dropped, not judged | Q3a rule |
| AAD of the scheme | exact to rounding | language builds against `aadladder_g` | none | the bump reference |

Outside: none. No library differentiates this scheme (G-18).
