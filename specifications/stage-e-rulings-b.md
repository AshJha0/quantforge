# Stage E rulings, spec B (E4, E6, E7, E8)

Spec version 1.0.0. Normative: this page is part of every stage E spec B page (`garch.md`, `variance-swaps.md`, `vix-index.md`, `rates-vol-cube.md` and the E6 and E8 pages as they land), and wins where it is more exact. Spec A's rulings are in `stage-e-rulings.md` with prefix E-A; the two sets do not overlap.

## E7 rulings

| # | Point | Ruling |
|---|---|---|
| E-B1 | GARCH mean and start | Returns are used as given: no mean is estimated. `"SAMPLE"` initial variance is `(1/n) sum r_t^2` over the whole series (divisor `n`, no demeaning). The log-likelihood keeps every term from `t = 1` and the `ln(2 pi)` constant, so values compare across languages and with published Gaussian likelihoods |
| E-B2 | GARCH constraints and fit | Likelihood: `omega > 0`, `alpha, beta >= 0`; `alpha + beta >= 1` allowed. Forecast: `alpha + beta >= 1` is `E_DOMAIN`. Fit: the initial variance is held fixed, at least 30 returns, judged on the log-likelihood within 1e-6 absolute; parameters are not compared (policy class `calibration`, judged on the objective). Golden optima are interior, checked by gradient and Hessian at 50 digits |
| E-B3 | Variance swap reference and drift | DDKZ discrete strip with reference `S* = spot` and QuantLib's weight walk (puts down, calls up, one extension strike each side, no option at the extension). The drift term is `(2/T)[(r - q)T - (F/S0 - 1)]`, the value of the log contract with dividends. QuantLib 1.44 writes `(2/T)(rT - (e^{rT} - 1))`, which equals this only at `q = 0`, so only `q = 0` cases are counted against QuantLib and QuantLib's form is a wrong-convention check |
| E-B4 | Realized variance | Log returns, no mean removed, divisor `m` (the number of returns), times `periods_per_year`. This is the standard variance swap term-sheet definition; the sample-variance form (`m - 1`, demeaned) is a wrong-convention check. Payoff at maturity, not discounted; discounting is the caller's |
| E-B5 | VIX strip details | Mids include zero-bid quotes for the forward step. The forward strike is the lowest strike among those with the smallest `|C - P|`. `dK` uses neighbours among the selected strikes, not the full strip. A zero bid is skipped; the second consecutive zero bid stops that side. `T = minutes / 525600`. `R` is the caller's continuous rate for the term (the white paper's Treasury interpolation is out of scope) |
| E-B6 | VIX interpolation | Two terms with `N1 < N2` and `N1 <= 43200 <= N2`; otherwise `E_INPUT`. No extrapolation and no single-term index |
| E-B7 | Error order | Each operation lists its checks in order; the first broken rule wins, as `cli-contract.md`. Schema errors (missing key, `null`, wrong type) come first, as everywhere |

## E4 rulings

| # | Point | Ruling |
|---|---|---|
| E-B8 | Cube interpolation | The four SABR parameters are each bilinear in (expiry time ACT/365F from `as_of` to the adjusted node date, tenor in years = months/12). Vols are never interpolated (a wrong-convention check). No extrapolation: outside the node grid is `E_INPUT`. The smile is read at the swaption's own forward (D7: exercise at swap start), unshifted Hagan |
| E-B9 | Caplet stripping shape | Piecewise-constant caplet vol on each segment between successive cap maturities, all caps starting at the same date and strike. Caplet-by-caplet stripping from an interpolated term-vol surface (QuantLib `OptionletStripper1`) is a different rule and not used |
| E-B10 | Stripping arbitrage | If a segment needs a caplet vol at or below zero (the longer cap is cheaper than the caplets already fixed by shorter caps), the result is `E_ARBITRAGE`, not a clipped vol. Search lower bound: 1e-6 (Black) or 1e-7 (Bachelier) |
| E-B11 | Bond futures options | Black-76 on the futures price, premium paid at the given discount date; futures-style margined options are out of scope. `yield_vol = price_vol / (modified_duration x yield)`, first order, CTD duration and yield given by the caller |
| E-B12 | YoY caplet time | Option time to the fixing (`expiry_years`), discounting to payment; YoY forwards are inputs (no ZC-to-YoY convexity here) |
| E-B13 | ZC inflation cap strike | `(1 + K)^T`, compounded annually over `T` years (a real number); the simple `1 + KT` is a wrong-convention check |

## Oracle coverage

Outside-oracle cases are verified by `oracle/python/outside_e_b.py` against QuantLib 1.44, every convention object taken from `oracle/python/qf_oracle/convmap_e_b.py` (reviewed copy `oracle/CONVENTION_MAP_E_B.md`), with one register row per counted case in `oracle/outside_register_e_b.json` (library, version, convention rows, review state). The stage E floor of 60% applies to spec B's suites taken together once E4, E6 and E8 land; the running share is in `program/STAGE_E_HANDOVER_B.md`.

E4: all 35 non-error cases are outside-checked (70% of the suite, errors in the denominator). E7 alone is below the floor, for stated reasons: QuantLib's Python wheel has no `Garch11` and no VIX method. Those suites are pinned by hand cases, 50-digit or exact-rational replicas, and a separately written float replay, and carry most of the 74 caught wrong-convention checks.
