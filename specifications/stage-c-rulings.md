# Stage C rulings and oracle coverage

Spec version 1.0.0. Normative: this page is part of every stage C spec, and wins where it is more exact.

## Rulings

| # | Point | Ruling |
|---|---|---|
| C1 | American options | Out of stage C. The plan allows de-Americanisation or European index options only; this stage takes European index options only. No American quote is accepted anywhere |
| C2 | Curve for dividends | The carry factor `C = D/B`, never `D` alone. Plan section 8 |
| C3 | Curve for option PV | The funding curve `D`. Never `C` |
| C4 | Shifted Hagan SABR | Keeps the negative density. It may be used only through `vol.sabr.density` with `REJECT`, or be replaced by `vol.sabr.arbfree`. Plan section 8 |
| C5 | Dividend on `as_of`, on `expiry` | Ignored; counted |
| C6 | Time | `(date - as_of)/365` everywhere in stage C, as in `curve-framework.md`. Operations with `expiry_years` take it as given |
| C7 | Vol units | Decimals: 0.2 is 20%. Greeks per 1.00 of vol. Bachelier vol in price units per square root of year |
| C8 | Bachelier shift | Not offered: it takes negative values already. `shift` on it is `E_SCHEMA` |
| C9 | Optional `shift`, `weights`, `snapshot_id` | May be absent, as may `shift` at 0. `null` for one is `E_SCHEMA`. `borrow_curve` and `scale` are not optional: `null` carries meaning and the key must be present |
| C10 | Order of checks | As each spec lists, after `E_SCHEMA` and `E_LIMIT`. Array limit is 100 for any quote, strike, point, dividend or position list, as ruling B5, and 100 per surface grid |
| C11 | Golden fits | A fit golden is reached from several starts. A build that finds a worse local minimum fails, by design |
| C12 | Non-convergence | Never a golden outcome: whether a solver stops depends on its path |
| C13 | `E_ARBITRAGE` | New in contract 1.4.0. Only `vol.sabr.density` with `REJECT` returns it in stage C |
| C14 | QuantLib and borrow | `AnalyticDividendEuropeanEngine` in 1.44 carries dividends on `r-b`, so agrees with the corrected forward. It is an outside check of C2, measured, not assumed |

## Oracle coverage

"Outside" means a library not written here. Replay and hand sources share an author with the spec, so can share a misreading.

| Suite | Outside oracle | Analytic, hand or replay only |
|---|---|---|
| `equity_forward` | None | Rolled route, plan check case, NumPy for parity |
| `equity_forward_deep` | QuantLib dividend engine on PV, delta, gamma, vega | Spot-bump delta; cases with no dividend |
| `black`, `black_deep` | QuantLib Black, Bachelier, implied vol | Black-Scholes through Black-76; bounds; parity |
| `greeks` | QuantLib Black-Scholes engine | Black-76, Bachelier, vanna, volga; bump Greeks |
| `strata_vol` | Strata Black, Bachelier, Greeks, implied vol, Hagan | None |
| `smile` | QuantLib SVI | Delta, RR and BF, SSVI, fits (known truth, SciPy) |
| `surface` | QuantLib `BlackVarianceSurface` for query | Check lists; bucket vega |
| `sabr` | QuantLib Hagan, shifted too | Density; fits |
| `sabr_deep` | QuantLib CEV at `nu = 0`; QuantLib Doust as a coarse check | Replay of the recipe at `nu > 0`. **The recipe's `nu > 0` values have no tight outside source**: only mass, mean, convexity and closeness to Hagan |
| `usecases_c` | None directly | Known truth, through parts checked above |

`oracle/MUTANTS_C.md` lists the 30 deliberate convention errors; the generator stops if a suite's tolerance would let one through. That proves each named error is caught, not that every plausible one is. All stage C data is synthetic, so an outside oracle here means agreement on method, not fit to a market.

Strata results are read from `oracle/strata/out/vol-out.tsv`, written by `StrataVol`. Regenerate it by hand if `GRID` in the generator changes; the run stops if it is stale.
