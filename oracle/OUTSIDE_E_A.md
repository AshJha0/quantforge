# Stage E spec A: outside-oracle coverage

Written by `oracle/python/outside_e_a.py`. A case counts only if QuantLib, built from the objects in the map below, reproduces every output within the case's own tolerance. Error cases are in the denominator and never count. Register: `oracle/outside_register_e_a.json`.

| Suite | Outside-oracle cases | Cases | Share |
|---|---|---|---|
| `surf_e` | 9 | 28 | 32% |
| `lv_e` | 22 | 39 | 56% |
| `fxs_e` | 114 | 125 | 91% |
| **spec A total** | **145** | **192** | **75.5%** |

Operations with no QuantLib route:

- `vol.ssvi.to_svi`: QuantLib has no SSVI; checked by replay through vol.ssvi.evaluate
- `vol.svi.fit_surface`: fit judged on known-truth parameters; QuantLib's SviInterpolatedSmileSection fits by its own optimiser path
- `vol.local.dupire`: QuantLib's LocalVolSurface needs a BlackVolTermStructure; none reproduces SVI slices linear in total variance. Checked by a 40-digit price-based Dupire

## Convention map (rule 11.2.5)

QuantLib 1.44. Review: self-reviewed 2026-11-08, self-assessment, not an outside review. Written from `oracle/python/qf_oracle/convmap_e_a.py`.

| Row | Spec | QuantLib object | Note |
|---|---|---|---|
| `SVI.RAW` | 05-volatility/arb-free-surfaces.md raw SVI w(k) = a + b(rho(k-m) + sqrt((k-m)^2 + sigma^2)), k = ln(K/F) | `ql.SviSmileSection(T, F, [p["a"], p["b"], p["sigma"], p["rho"], p["m"]]` | QuantLib parameter order is (a, b, sigma, rho, m); variance(K) is total variance w at k = ln(K/F) |
| `SVI.DENSITY` | 05-volatility/arb-free-surfaces.md butterfly: g(k) < 0 iff the risk-neutral density is negative | `sec.density(K, 1.0, 1e-4` | SmileSection::density: second difference of undiscounted calls in strike, gap 1e-4; only its sign is used, on cases guarded |g| > 1e-6 and away from the far tail |
| `VOL.CURVE` | 05-volatility/local-and-forward-vol.md forward vol: total variance linear between expiries, time ACT/365F days/365 | `ql.BlackVarianceCurve(ref, dates, vols, ql.Actual365Fixed(), False` | forceMonotoneVariance off, so QuantLib does not hide a calendar break |
| `DC.ACT_365F` | 01-core/daycount.md ACT_365F | `ql.Actual365Fixed(), ""` |  |
| `OPT.BLACK_FORMULA` | 05-volatility/black-models.md Black-76 on the forward F = S exp((r-q)T), discount exp(-rT) | `ql.blackFormula(ql.Option.Call if ot == "CALL" else ql.Option.Put, K, F, sd, D), ""` |  |
| `OPT.BLACK_CALC` | 05-volatility/local-and-forward-vol.md smile dynamics: spot delta and vega of Black-Scholes with dividend yield | `ql.BlackCalculator(ql.PlainVanillaPayoff(ql.Option.Call if ot == "CALL" else ql.Option.Put, K), F, sd, D` | delta(spot) is dV/dS at fixed vol; vega(T) per unit vol |
| `STAT.SAMPLE` | 05-volatility/local-and-forward-vol.md vol of vol: sample standard deviation, divisor n-1 | `ql.IncrementalStatistics(), "standardDeviation uses n-1"` | standardDeviation uses n-1 |
| `FX.DELTA_TYPE` | 05-volatility/fx-smile.md delta types SPOT, FORWARD, SPOT_PA, FORWARD_PA | `{"SPOT": ql.DeltaVolQuote.Spot, "FORWARD": ql.DeltaVolQuote.Fwd, "SPOT_PA": ql.DeltaVolQuote.PaSpot, "FORWARD_` | QuantLib DeltaVolQuote::DeltaType; PA = premium in foreign currency included |
| `FX.ATM_TYPE` | 05-volatility/fx-smile.md ATM SPOT, FORWARD, DNS | `{"SPOT": ql.DeltaVolQuote.AtmSpot, "FORWARD": ql.DeltaVolQuote.AtmFwd, "DNS": ql.DeltaVolQuote.AtmDeltaNeutral` | QuantLib AtmDeltaNeutral depends on the delta type, as the spec |
| `FX.DELTA_CALC` | 05-volatility/fx-smile.md deltas and strikes; discount factors exp(-r T), continuous | `ql.BlackDeltaCalculator(ql.Option.Call if ot == "CALL" else ql.Option.Put, dtq, S, Dd, Df, sd), ""` |  |
| `FX.GK` | 05-volatility/fx-smile.md Garman-Kohlhagen: flat continuous rd, rf on ACT/365F, expiry days/365 | `ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S` | Garman-Kohlhagen is BlackScholesMertonProcess with the foreign curve as dividend curve (the SWIG wheel has no GarmanKohlhagenProcess); engine AnalyticEuropeanEngine; vega per unit vol |
