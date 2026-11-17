# Review request: SSVI surface (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage C). Evidence line from the project's status table: 3 golden cases for `vol.ssvi.evaluate`, 3 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. No library has an SSVI object. Total variance is checked through the raw-SVI form of each slice (Gatheral and Jacquier 2014, Lemma 3.3) with QuantLib `SviSmileSection`; the mapping itself is arithmetic.
9. `butterfly_free` and `calendar_free` are sufficient conditions on the parameters (G-J 2014 Theorem 4.2, Corollary 4.1), recomputed as arithmetic: no library checks them. A surface can fail them and still be free of arbitrage.

## Spec

### `specifications/05-volatility/smile-and-surface.md`

# Delta, smile, SVI, SSVI, surface

Spec version 1.0.0. Status: Specified. Stage C.

Log-moneyness is `k = ln(K/F)`, with `F` the forward of that expiry. Total variance is `w = v^2 T`. Times are years, as `expiry_years`.

## Delta conventions

`Delta = phi s N(phi d1)`, lognormal, `delta` signed: a put's is negative.

| `convention` | `s` | Meaning |
|---|---|---|
| `FORWARD` | 1 | `scale` must be `null`, else `E_INPUT` |
| `SPOT` | `scale`, given | `dV/dS`. On an equity, `D(T)/C(T)`. `null`: `E_INPUT`. Must be above 0, else `E_DOMAIN` |

`vol.delta.to_strike`. Inputs: `forward`, `vol`, `expiry_years`, `option_type`, `delta`, `convention`, `scale`. With `d1 = phi Ninv(phi delta/s)`, output `strike = F exp(-d1 v sqrt T + v^2 T/2)`. `phi delta/s` outside the open interval `(0, 1)`: `E_DOMAIN`. `forward`, `vol`, `expiry_years` must be above 0, else `E_DOMAIN`. `Ninv` must be good to 1e-12.

`vol.delta.from_strike`. Same, with `strike` (above 0) for `delta`. Output: `delta`.

`vol.smile.rr_bf`. Inputs: `forward`, `expiry_years`, `atm_vol`, `atm_convention`, `rr`, `bf`, `delta` (positive, such as 0.25), `convention`, `scale`. `call_vol = atm + bf + rr/2`, `put_vol = atm + bf - rr/2`. `bf` here is the smile strangle: no broker-strangle iteration. `atm_strike`: `F` for `ATM_FORWARD`, `F exp(atm^2 T/2)` for `DELTA_NEUTRAL`. Outputs: `atm_strike`, `call_vol`, `put_vol`, `call_strike`, `put_strike`, the last two from `vol.delta.to_strike` with `delta` and `-delta`, each at its own vol. A vol `<= 0`: `E_DOMAIN`.

## SVI

Raw form, at one expiry: `w(k) = a + b (rho (k-m) + R)`, `R = sqrt((k-m)^2 + sigma^2)`.

Parameter object `svi`: `{a, b, rho, m, sigma}`. `b < 0`, `|rho| >= 1`, `sigma <= 0`, or `a + b sigma sqrt(1-rho^2) <= 0`: `E_DOMAIN`.

`w' = b (rho + (k-m)/R)`, `w'' = b sigma^2/R^3`.

Gatheral density function: `g = (1 - k w'/(2w))^2 - (w'^2/4)(1/w + 1/4) + w''/2`. `g < 0` at any `k` is butterfly arbitrage.

`vol.svi.evaluate`. Inputs: `svi`, `log_moneyness`, `expiry_years` (above 0, else `E_DOMAIN`). Outputs: `total_variance`, `implied_vol`, `g`, arrays; `min_g`; `butterfly_free`, `min_g >= 0` on the given points.

`vol.svi.calibrate`. Inputs: `log_moneyness` (strictly increasing, else `E_INPUT`), `total_variance`, optional `weights`. Minimise `sum weight (w_model - w)^2`, inside the domain above. Fewer than 5 points, or lengths that differ: `E_INPUT`. A `total_variance <= 0`, or non-positive weight: `E_DOMAIN`. Outputs: `svi`, `rmse`, the root of `sum weight e^2 / sum weight`. Any solver. Use several starts: a single one can stop in a local minimum. A build must find the global one on the golden cases.

## SSVI

`w(k, theta) = theta/2 (1 + rho phi k + sqrt((phi k + rho)^2 + 1 - rho^2))`, with the power law `phi(theta) = eta theta^-gamma (1+theta)^(gamma-1)`. `theta` is ATM total variance.

`|rho| >= 1`, `eta <= 0`, `gamma` outside `(0, 1]`, `theta <= 0`: `E_DOMAIN`. `thetas` not strictly increasing: `E_INPUT`.

`vol.ssvi.evaluate`. Inputs: `rho`, `eta`, `gamma`, `thetas`, `log_moneyness`. Outputs: `total_variance`, one row per theta; `butterfly_free`; `calendar_free`.

- `butterfly_free`: at every theta, `theta phi (1+|rho|) < 4` and `theta phi^2 (1+|rho|) <= 4`. These are Gatheral and Jacquier's **sufficient** conditions, not necessary ones (R6-25): `butterfly_free = true` proves the slice free of butterfly arbitrage, but `false` can be a false alarm, a slice that is in fact arbitrage-free. Check the density (`vol.svi.evaluate` `g`) before acting on a `false`.
- `calendar_free`: at every theta, `rho^2 (1-gamma)/(1+theta) <= 1 + sqrt(1-rho^2)`. This is the Gatheral-Jacquier bound with the power-law derivative `d(theta phi)/d theta = phi (1-gamma)/(1+theta)`. The lower bound holds by `gamma <= 1`.

`vol.ssvi.calibrate`. Inputs: `thetas`, `log_moneyness`, `total_variance` (rows per theta). Outputs: `rho`, `eta`, `gamma`, `rmse`. Unweighted. Fewer than 3 points in all, or ragged rows: `E_INPUT`.

## Surface

Object `surface`: `{expiry_years, log_moneyness, vols}`, `vols` one row per expiry. Grids strictly increasing and shape matching, else `E_INPUT`. A grid time or vol `<= 0`: `E_DOMAIN`. Each grid at most 100 long, else `E_LIMIT`. Nodes hold at fixed log-moneyness, so a surface is in forward-moneyness terms.

`vol.surface.query`. Inputs: `surface`, `points`, array of `{expiry_years, log_moneyness}`. Outputs: `total_variance`, `vols`.

Rule: on each slice, `w` is linear in `k`, with `k` clamped to the grid. Between slices, `w` is linear in `T`. Before the first slice `w = w_1(k) T/T_1`, and after the last `w = w_n(k) T/T_n`, so flat vol in both directions. `expiry_years <= 0`: `E_DOMAIN`.

`vol.surface.check`. Input: `surface`. Outputs: `calendar_violations`, `butterfly_violations`, `arbitrage_free`. Lists are in row order, 0-based. All compare with a tolerance of `1e-12`.

- Calendar: `{expiry_index, k_index}` where `w[j][i] < w[j-1][i] - 1e-12`, `expiry_index` being `j`.
- Butterfly: per slice, undiscounted Black call `c_i` with `F = 1`, `K_i = exp(k_i)`, slopes `s_i = (c_{i+1}-c_i)/(K_{i+1}-K_i)`. `{expiry_index, k_index, kind}`: `SLOPE` at `i` if `s_i < -1 - 1e-12` or `s_i > 1e-12`; `CONVEXITY` at `i+1` if `s_{i+1} < s_i - 1e-12`. Within a slice, slope entries come first, then convexity.

## Limits of this stage

Linear surface interpolation can create butterfly arbitrage between nodes: the check covers nodes only. Stage E adds arbitrage-free interpolation and local vol.

## Acceptance

Targets in `stage-c-targets.md`. Suites `smile`, `surface`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Gatheral, J., *The Volatility Surface: A Practitioner's Guide*, Wiley, 2006 (SVI) (not opened)
- [S2] Gatheral, J. and Jacquier, A., "Arbitrage-free SVI volatility surfaces", *Quantitative Finance* 14(1), 2014, 59-71 (SSVI, density function g, calendar and butterfly conditions) (not opened)
- [S3] Clark, I. J., *Foreign Exchange Option Pricing*, Wiley, 2011 (spot, forward and premium-adjusted delta conventions) (not opened)
- [S4] Reiswich, D. and Wystup, U., "FX volatility smile construction", *Wilmott Journal* 2012 / Frankfurt School CPQF working paper 20, 2010 (delta conventions) (not opened)


## Golden cases (3 of 3 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"smile-0039","operation":"vol.ssvi.evaluate","inputs":{"rho":-0.4,"eta":1.0,"gamma":0.5,"thetas":[0.01,0.04,0.09,0.16],"log_moneyness":[-0.4,-0.1,0.0,0.1,0.4]},"expected":{"status":"ok","outputs":{"total_variance":[[0.035335341190401444,0.015335924789558916,0.01,0.00847359942420315,0.015517706394966413],[0.08634531879296155,0.04947710218262603,0.04,0.03449671467825325,0.04051692282720563],[0.15399165093288086,0.10317450974618779,0.09,0.0806558903106293,0.07909848553173927],[0.23882764360494826,0.1764967629457208,0.16,0.14711329876589196,0.13492585785786426]],"butterfly_free":true,"calendar_free":true}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","atm-equals-theta","quantlib-1.44-svi-slices"]}
{"case_id":"smile-0040","operation":"vol.ssvi.evaluate","inputs":{"rho":-0.7,"eta":3.0,"gamma":0.5,"thetas":[0.01,0.04,0.09,0.16],"log_moneyness":[-0.4,-0.1,0.0,0.1,0.4]},"expected":{"status":"ok","outputs":{"total_variance":[[0.11009457973309267,0.03421624637084954,0.01,0.006522630471227271,0.019523984850000814],[0.23481085812372463,0.08629856555023963,0.04,0.020424390875725288,0.04228017343178713],[0.3721116934838781,0.15640105268909307,0.09,0.048995131883534444,0.06884077333886807],[0.5206112540029885,0.24446638261150724,0.16,0.09813614954471117,0.1003613694105123]],"butterfly_free":false,"calendar_free":true}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","quantlib-1.44-svi-slices"]}
{"case_id":"smile-0041","operation":"vol.ssvi.evaluate","inputs":{"rho":0.0,"eta":0.15,"gamma":1.0,"thetas":[0.01,0.04,0.09,0.16],"log_moneyness":[-0.4,-0.1,0.0,0.1,0.4]},"expected":{"status":"ok","outputs":{"total_variance":[[0.0354138126514911,0.014013878188659974,0.01,0.014013878188659974,0.0354138126514911],[0.056055512754639894,0.04136000936329383,0.04,0.04136000936329383,0.056055512754639894],[0.09908326913195982,0.09062071897723664,0.09,0.09062071897723664,0.09908326913195982],[0.16544003745317531,0.160350793399941,0.16,0.160350793399941,0.16544003745317531]],"butterfly_free":true,"calendar_free":true}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","quantlib-1.44-svi-slices"]}
```

## Outside-library evidence and limits (from the project's own page)

SSVI evaluation has analytic cases, including the check that total variance at `k = 0` equals `theta` (1e-15). No outside library has an SSVI object. Since the validation evidence pack (2026-11-17), each slice's total variance is checked with QuantLib `SviSmileSection` through the raw-SVI form of an SSVI slice (Gatheral and Jacquier 2014, Lemma 3.3); the two no-arbitrage flags are the spec's sufficient conditions on the parameters, recomputed as arithmetic (`oracle/OUTSIDE_VALIDATION.json`).

Golden cases with an `ok` result for `vol.ssvi.evaluate`: 3, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

| Verified by | Operation | Cases |
|---|---|---|
| analytic, atm-equals-theta, quantlib-1.44-svi-slices | vol.ssvi.evaluate | 1 |
| analytic, quantlib-1.44-svi-slices | vol.ssvi.evaluate | 2 |

Limits:

- The grid is total variance against `theta`, because the SSVI operation takes `theta` and not calendar time. Expiry in years is not an input.
- The flags are checks at the grid points. A wider grid could find a violation this one does not.
- One parameter set, chosen by hand.

Synthetic inputs, not market data.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free option quotes or vol surfaces. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-c-rulings.md) | C17 | Empty arrays | `E_INPUT`, as B3 and B6, for every stage C list but `dividends`, which may be empty: `strikes`, `log_moneyness`, `thetas`, `points`, `positions`, `quotes`, `slices`, `k_grid`. This is the first rule check, before every `E_DOMAIN`, and applies to `vol.sabr.hagan`, `density`, `arbfree` and `vol.svi.evaluate`, `vol.ssvi.evaluate` as much as to fits |
