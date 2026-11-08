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

## R5 audit rulings on E7 (2026-11-08)

From `R5_STAGE_E_AUDIT.md` (plan repository), items 1, 4, 6, 7, 8 and 9.

| # | Point | Ruling |
|---|---|---|
| E-B14 | Per-output tolerance | A case's `tolerance_limit` applies to every output not named in `output_classes`; an output named there uses its class and never the limit (`conformance/runner/runner.py`, `judge`). This is the existing case format, so all four languages and the runner read it the same way and nothing in the runner changes. E7 and E4 goldens now name their non-money outputs: `fair_variance`, `fair_vol`, `realized_variance`, `realized_vol`, `near_variance`, `next_variance` in `simple_analytic` (1e-12 abs + 1e-10 rel, as the specs say); `loglik` in the new class `likelihood_sum` (1e-9 abs + 1e-10 rel) with variances under the case limit 1e-16 abs + 1e-11 rel; cube `forward_rate`, `annuity`, `vol`, `sabr` in `interpolation`; ZC `strike_ratio` in `simple_analytic`. Money outputs keep the money limit. Before this ruling, variances were compared at the money figure (1e-6 or 1e-8 absolute) |
| E-B15 | VIX source and the three points | The source is Cboe, *Cboe Volatility Index Mathematics Methodology*, v5.0, revised 26 Feb 2026 (read from the PDF on 2026-11-08), which replaces the white paper. Settled against its text: (a) K0 is "the strike price equal to or otherwise immediately below the forward price" (section 3(a)(ii)), so "at or below" stands, pinned by `vix_e-0004`, `vix_e-0006` (F equals a strike); (b) ATM candidates use bid/ask midpoints, and only series with null quotes or bid above ask are not candidates (3(a)(ii)), so a zero bid stays a candidate, pinned by `vix_e-0018`; (c) dK is computed "for each strike included in the calculation", with edges "of any given set of options" taking the one-sided gap (3(a)(iv)): read as neighbours among the selected strikes, as before. The methodology excludes an option with a zero bid or a zero ask; with bid <= ask enforced (`E_INPUT` otherwise), a zero ask implies a zero bid, so the bid test is equivalent. New rule from 3(a)(iii): if every out-of-the-money put, or every out-of-the-money call, is excluded, the index cannot be calculated: `E_INPUT`, pinned by `vix_e-0021` |
| E-B16 | GARCH fit gate and class | Goldens use class `root_finding` with `tolerance_limit` 1e-6 absolute on `loglik` (the policy class `calibration` has no numeric tolerance and the runner has no `judged_on`). The gate stays 1e-6: a correct build should stop at a log-likelihood gap below 1e-8 (about 1e-4 relative on `omega`); a loose stopping rule is the usual cause of a failure. Optimising over `omega / sample variance` is recommended for conditioning and does not change the optimum |
| E-B17 | Binary64 comparisons and new goldens | `alpha + beta` is computed in binary64 as written and compared with 1; the goldens use pairs whose binary64 sum is exactly 1.0 (`0.1 + 0.9`, `0.3 + 0.7`), so IEEE languages agree. The VIX strip may come in any order and is sorted by strike (`vix_e-0017`). New goldens: index with `N1 = 43200` (`vix_e-0009`) and `N2 = 43200` (`vix_e-0010`); errors `garch_e-0025`, `garch_e-0026`, `varswap_e-0028`, `varswap_e-0029`, `vix_e-0019` to `vix_e-0022` |

## Oracle coverage

Outside-oracle cases are verified by `oracle/python/outside_e_b.py` against QuantLib 1.44, every convention object taken from `oracle/python/qf_oracle/convmap_e_b.py` (reviewed copy `oracle/CONVENTION_MAP_E_B.md`), with one register row per counted case in `oracle/outside_register_e_b.json` (library, version, convention rows, review state). The stage E floor of 60% applies to spec B's suites taken together once E4, E6 and E8 land; the running share is in `program/STAGE_E_HANDOVER_B.md`.

E4: all 35 non-error cases are outside-checked (70% of the suite, errors in the denominator). E7 alone is below the floor (18 of 84 cases, 21.4%, after the R5 additions, which are error cases and non-QuantLib VIX cases), for stated reasons: QuantLib's Python wheel has no `Garch11` and no VIX method. Those suites are pinned by hand cases, 50-digit or exact-rational replicas, and a separately written float replay, and carry most of the 78 caught wrong-convention checks.
