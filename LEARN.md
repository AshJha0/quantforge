# Learn QuantForge

A path through the project. Each topic goes from the plain idea, to the formal statement in a spec, to a worked example.

## Start here

QuantForge has four equal implementations of the same maths, in Java, C++, Python and Rust. None is the reference. Expected answers come from `oracle/`, because four programs agreeing proves only that they agree.

Each stage below says what was built, where it lives, a path through it, worked examples and its limits. Each result below is real output from the CLIs on 2026-11-06. For the stage A examples, Java, C++, Python and Rust printed the same value in each one. The stage B examples say where they differ. Send the cases as `COOKBOOK.md` shows.

## Stage A: Foundation

**What was built.** Domain 01 in all four languages: day counts, calendars, compounding, data checks, snapshot hash, as-of store, random numbers, Sobol, root finders, integration, interpolation, statistics, PDE, Monte Carlo and COS. Also the oracle, the CLI, the neutral runner, fuzz and mutation harnesses, the recorder and the forward log.

**Where it is.** Specs in `specifications/01-core/`. Examples: `examples/daycount.json`, `discount_factor.json`, `root_brent.json`, `error_date_order.json`, `batch.jsonl`. Exercises EX-001 to EX-003 in `program/exercises/`. Recipes in the [Cookbook](COOKBOOK.md#stage-a-recipes).

### Learning path

Specs are in `specifications/01-core/`. Exercises are in `program/exercises/`.

| Step | Plain idea | Read | Try |
|---|---|---|---|
| 1 | A year fraction depends on who is counting | `daycount.md` | EX-001 |
| 2 | Business days are rules plus surprises | `calendars.md` | Find why 2022-09-19 is a holiday |
| 3 | A rate needs its compounding | `compounding.md` | EX-002 |
| 4 | Solvers must say how they stopped | `root-finders.md` | EX-003 |
| 5 | Interpolation decides what your forwards look like | `interpolation.md` | Compare `linear` and `monotone_convex` forwards |
| 6 | Random numbers can be made reproducible | `rng.md`, `sobol.md` | Reproduce a golden case in `rng` |
| 7 | Three ways to price one option | `monte-carlo.md`, `pde.md`, `cos.md` | Price the same call all three ways |
| 8 | Never overwrite a number | `asof-store.md` | Follow a correction through the `store` cases |

### Worked examples

**Day count.** Plain idea: the same dates give different year fractions. Formal statement: `ACT_360 = days / 360`, `ACT_365F = days / 365`. From 2024-01-01 to 2024-07-01 is 182 days, and `core.daycount.year_fraction` gives 0.5055555555555555 under `ACT_360`; 182/365 is 0.49863 under `ACT_365F`. On 1,000,000 at 5%, simple interest differs by about 346 for the same dates.

**Discount factor.** Plain idea: money later is worth less than money now, by an amount set by the compounding. Formal statement: continuous compounding gives `exp(-r t)`. At `rate` 0.05 and `t` 2, `core.compounding.discount_factor` gives 0.9048374180359595.

**Calendar.** Plain idea: one-off holidays are data, not rules. `core.calendar.is_business_day` gives `false` for `GBLO` on 2022-09-19, which `calendars.md` lists as a one-off.

**Good Friday in the US bond calendar.** Plain idea: a market can stay open on a day that looks like a holiday. In `USGS`, Good Friday is a holiday, except in the seven years when SIFMA recommended an early close instead: 2007, 2010, 2012, 2015, 2021, 2023 and 2026, when it is a business day (ruling R1-6). SOFR is never published on Good Friday, even in those years, so SOFR compounding skips the day. For 2015 SIFMA's own records conflict; the archive page was followed. Sources and dates for each calendar are in `datasets/calendar_provenance.json`.

**Snapshot hash.** Plain idea: to prove two languages read the same input, hash one agreed spelling of it. Formal statement: `sha256` of the canonical form in `snapshot-hash.md`. `{"b":1,"a":[true,null,"x"]}` has keys sorted and its number written as binary64 hex, giving `{"a":[true,null,"x"],"b":#3ff0000000000000}` and `sha256:f44e5e9e9da8644c95ac377821cec005c5a1118e581a0d8cfb217ae01d212aed`. This is the stage A demo: the same hash in all four.

**Option price.** Plain idea: a method can be checked against a formula. For spot and strike 100, `r` 0.05, `q` 0.02, `sigma` 0.2 and `t` 1, the Black-Scholes value is 9.227006 (`oracle/REPORT.md`). `core.cos.european` with 256 terms gives 9.227005508154036, against a golden value of 9.227005508154049, inside class `fourier`. This is an analytic test on constructed inputs, not a market price.

### Known limits

Many golden cases have hand or replay sources, which can share a misreading with the spec. Constructed inputs test the method only. The recorder is built but not scheduled. See the [Roadmap](ROADMAP.md#stage-status).

## Stage B: FX and rates slices

**What was built.** SONIA and minimal SOFR OIS curves, projection curves, FRAs, swaps, FX forwards and swaps, quote-driven basis, calibration, DV01 and key-rate risk, hedges with a spread-based cost, and use cases 1 and 2.

**Where it is.** Specs in `specifications/`, under the folders named below. Examples: `examples/ois_bootstrap.json`, `ois_bootstrap_sofr.json`, `projection_bootstrap.json`, `fx_forward_outright.json`, `fx_curve_implied.json`, `usecase_fx_hedge.json`, `usecase_rates_hedge.json`. Exercises EX-005, EX-006, EX-008 and EX-009. Recipes in the [Cookbook](COOKBOOK.md#stage-b-recipes).

**See it.** The [Curves gallery](docs/curves/README.md) has a page for each implemented curve, with charts and numbers from real runs of all four CLIs on synthetic inputs. Start with [SONIA OIS](docs/curves/sonia-ois.md), then [SOFR](docs/curves/sofr-ois.md), [the projection curve](docs/curves/usd-term-3m.md) and [the FX forward](docs/curves/gbpusd-fx-forward.md).

### Learning path

Specs are in `specifications/`, under the folder named. All quotes in these steps are synthetic, because no free quote history exists: you are learning the method, not a market.

| Step | Plain idea | Read | Try |
|---|---|---|---|
| 9 | Money has a currency, and a convention is a record | `01-core/units-and-money.md`, `01-core/conventions.md` | Add two currencies and read the error |
| 10 | A swap's dates come from rules | `02-curves/schedules.md` | Find the short first stub in a `schedule` case |
| 11 | A curve says what one unit later is worth today | `02-curves/curve-framework.md` | Compare a forward under both interpolations |
| 12 | A curve is whatever makes every quote reprice | `02-curves/ois-curves.md` | EX-006 |
| 13 | Forecast on one curve, discount on another | `02-curves/projection-and-fra.md` | Price an FRA from a `projection` case |
| 14 | A forward follows from two curves and no arbitrage | `02-curves/fx.md` | EX-005 |
| 15 | Solvers differ, so judge the fit, not the parameters | `03-calibration/least-squares.md` | Run `calib.fit` with two methods |
| 16 | Bump the quotes, rebuild, reprice | `06-risk/rates-sensitivities.md` | EX-008 |
| 17 | A hedge is a least-squares problem with a cost | `08-hedging/stage-b-hedges.md` | EX-009 |
| 18 | Put it together | `04-pricing/use-cases.md` | Use cases 1 and 2, below |

### Worked examples

**Curve bootstrap (stage B).** Plain idea: find the discount factors at which every quoted swap is worth zero. Formal statement: solve `K_j(curve) = quote_j` for every quote `j`, in `ois-curves.md`. `examples/ois_bootstrap.json` holds 13 synthetic SONIA quotes from 1W to 30Y, as of 2026-11-06. `rates.ois.bootstrap` gives a 5Y discount factor of 0.8480030126521996 at 2031-11-06, and the Rust build reports a `max_repricing_error` of 1.8e-15. The four builds agree to about 15 digits, not to the last bit. An exact repricing here shows the solve works. It would show the same on any coherent quotes, so it says nothing about a market.

**Use case 1: FX hedge (stage B).** Plain idea: a book of forwards behaves like a position in spot, so spot can hedge it. Formal statement: `hedge_spot_base = -fx_delta`, and `hedge_cost = |hedge_spot_base| * half_spread`. `examples/usecase_fx_hedge.json` holds two synthetic GBPUSD forwards, buying 5,000,000 and selling 3,000,000, at spot 1.28 with a half-spread of 0.00005. `usecase.fx_hedge` gives a PV of 59,903.64653464559 and an FX delta of 2,054,546.4912482663. So the hedge sells 2,054,546.49 of base in spot, at a cost of 102.72732456241332. Delta is not 2,000,000 because each forward's delta is discounted, and the two dates differ. All four builds printed these values. The golden case has a hand source only.

**Use case 2: rates hedge (stage B).** Plain idea: match a trade's risk bucket by bucket, using swaps that sit at the quoted tenors. Formal statement: `hedge_units` solves `min |C x + key_rate|^2`, in `use-cases.md`. `examples/usecase_rates_hedge.json` pays fixed 3.4% on a 6Y SONIA swap, notional 10,000,000, off the quoted tenors, and hedges it with 5Y and 7Y par swaps of 1,000,000 each. From the Rust build: PV 4,688.4635, DV01 5,359.8843, with 2,210.20 in the 5Y bucket and 3,149.66 in the 7Y bucket. `hedge_units` are -4.8713 and -5.1239, so the hedge receives fixed on both, and the largest residual bucket is 0.015. `hedge_cost` at 0.25 bp is 1,339.9648. The four builds agree to about 11 digits, inside the use case's limit. The golden case comes from a replay of parts checked against QuantLib; the sums themselves have no outside source.

Nothing in these examples is traded. They are calculations on synthetic data.

### Known limits

Stage B is Implemented, not Validated. Almost all curve inputs are synthetic, so exact repricing says nothing about a market. `usecases` and `rulings_b` have no outside oracle, and `risk` is hand and self-consistency only. Risk is bump and rebuild, with no AD. See `specifications/stage-b-rulings.md` and the [Roadmap](ROADMAP.md#stage-status).

## Stage C: Equity vol slice

**What was built.** Equity forwards with a borrow curve and discrete dividends; Black-Scholes, Black-76 and Bachelier prices and implied vols; analytic and bumped Greeks; delta conventions and risk-reversal and butterfly quotes; SVI and SSVI with no-arbitrage checks; a vol surface with calendar and butterfly checks; Hagan SABR with a density check; arbitrage-free SABR; and use case 3.

**Where it is.** Specs in `specifications/05-volatility/`, `02-curves/equity-forward.md` and `06-risk/vol-greeks.md`. Rulings C1 to C17 in `specifications/stage-c-rulings.md`, targets in `05-volatility/stage-c-targets.md`. Goldens in `datasets/golden/stage_c/`: 446 cases in 11 suites. Recipes in the [Cookbook](COOKBOOK.md#stage-c-recipes).

### Learning path

All inputs are synthetic: no free history of option quotes, borrow cost or dividends was found.

| Step | Plain idea | Read | Try |
|---|---|---|---|
| 19 | A forward is the stock carried, less the dividends carried | `02-curves/equity-forward.md` | `equity_forward-0001` |
| 20 | One formula, three models, told apart by how the forward spreads | `05-volatility/black-models.md` | Price, then solve the vol back |
| 21 | A Greek is a slope of the price | `06-risk/vol-greeks.md` | `risk.vol.greeks` against `risk.vol.bump_greeks` |
| 22 | Desks quote strikes by delta | `05-volatility/smile-and-surface.md` | `vol.smile.rr_bf` |
| 23 | A smile is a curve in total variance, and some curves allow arbitrage | Same | `vol.svi.evaluate`, then read `g` |
| 24 | A surface is smiles that must not cross | Same | `vol.surface.check` |
| 25 | A popular formula can imply a negative density | `05-volatility/sabr.md` | `vol.sabr.density`, then `vol.sabr.arbfree` |
| 26 | Put it together | `04-pricing/use-cases.md` | Use case 3 |

### Worked examples

Every number below is from the Rust CLI on 2026-11-07, on the inputs of the named golden case. All four builds pass these cases within the targets.

**Equity forward.** Plain idea: holding the stock to expiry costs funding at `r`, earns the borrow fee `b` if lent out, and pays out the dividends. So the forward is the stock grown at `r - b`, less each dividend grown from its date to expiry. Formal statement, flat rates: `F = S e^{(r-b)T} - sum A_i e^{(r-b)(T - t_i)}`. With curves, dividends are carried on `C = D/B` (ruling C2), and option PVs are discounted on `D` alone (C3). A common slip is `(S - PV(D)) e^{(r-b)T}` with `PV` taken at `r`: it discounts each dividend at `r`, then grows it back at `r - b`, which matches only when `b = 0`. Take the PV at `r - b` and the two forms agree. Case `equity_forward-0001`: `S = 100`, `r = 0.04`, `b = 0.05`, a dividend of 2 at `t = 0.5`, `T = 1`. `eq.forward.flat` gives 97.01495841653144. The wrong form gives 97.0640923: close enough to pass a glance, so it is a named check (tag `wrong-convention`). QuantLib's `AnalyticDividendEuropeanEngine` agrees with the right form (C14).

**Black, Black-76 and Bachelier.** Plain idea: all three price a call as the expected payoff on a driftless forward, discounted. Black-Scholes and Black-76 make the forward lognormal, so vol is relative, written as a decimal: 0.2 is 20% a year (ruling C7). Bachelier makes it normal, so vol is in price units per square root of year and the forward may go negative. Formal statement: Black-76 call `D (F N(d1) - K N(d2))`, `d1,2 = (ln(F/K) ± v^2 T/2) / (v sqrt T)`. Black-Scholes is Black-76 with `F = S e^{(r-q)T}` and `D = e^{-rT}`, from spot, rate and yield. Bachelier call `D ((F - K) N(d) + v sqrt(T) n(d))`, `d = (F - K) / (v sqrt T)`. Puts follow from parity, the same in all three: `call - put = D (F - K)`. Price rises with vol, so an implied vol is unique when the price lies between intrinsic `D max(F - K, 0)` and, for lognormal calls, `D F` (`black-models.md`). Case `black-0001`: `F = K = 100`, `T = 1`, `D = 0.9704455335485082`, vol 0.2. Black-76 gives 7.730149359277918; case `black-0002` sends that price to `vol.option.implied` and expects 0.2. Case `black-0005`: the same under Bachelier with vol 20 gives 7.743035083184538, close to Black-76 because 20 in price units is 20% of 100 at the money.

**Greeks.** Plain idea: delta, gamma, vega, theta and rho are slopes of the price to spot, spot again, vol, time and rate; vanna and volga are second slopes involving vol. Formal statement: closed forms in `vol-greeks.md`, checked against bumps in the oracle. Vega and volga are per 1.00 of vol (C7), theta is `-dV/dT` per year, rho per 1.00 of rate. For Black-Scholes, `delta = e^{-qT} N(d1)`, `vega = S e^{-qT} n(d1) sqrt T`, `rho = K T e^{-rT} N(d2)`. Case `greeks-0001`: Black-Scholes call, `S = K = 100`, `r = 0.03`, yield 0.01, vol 0.2, `T = 1`. Price 8.827321225352126, delta 0.5734959790277754, gamma 0.01935758770796135, vega 38.715175415922694, theta -4.753689862887256, rho 48.5222766774254. Vanna and volga print as about 4e-16 and -8e-15. They are zero up to rounding: both scale with `d2`, and here `d2 = 0`.

**Delta conventions.** Plain idea: a 25-delta call is the strike where the call's delta is 0.25, so the strike depends on the vol and on which delta is meant. Spot delta carries a discount factor; forward delta does not. `scale` says which: `SPOT` needs a number, `FORWARD` needs `null` (C15). Case `smile-0001`: forward 100, vol 0.22, `T = 0.75`, forward delta 0.25 gives strike 115.79573605232507. Case `smile-0025`: ATM 0.2, risk reversal -0.04, butterfly 0.006 give a 25-delta call vol of 0.186 at 115.34449734852197 and a put vol of 0.226 at 88.08246715793778, from `call = atm + bf + rr/2` and `put = atm + bf - rr/2`.

**SVI and SSVI.** Plain idea: write the smile as total variance `w = v^2 T` against log-moneyness `k`. SVI is a five-parameter hyperbola in `k`; it fits well, but some parameter sets imply a negative density. SSVI ties all expiries to one shape driven by the ATM variance `theta`, with simple conditions that rule out arbitrage. Formal statement: `w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + sigma^2))`. A smile is butterfly-free where Gatheral's `g(k) >= 0`. A surface is calendar-free where `w` does not fall as `T` rises at fixed `k`. Case `smile-0028`: `a = 0.03`, `b = 0.12`, `rho = -0.35`, `m = 0.02`, `sigma = 0.15`, `T = 1.5`. At `k = 0`, `w = 0.04899929514050587`, vol 0.180737922861632 and `g = 1.372275771715203`; `g` is positive on all nine points. Case `smile-0039`: SSVI with `rho = -0.4`, `eta = 1`, `gamma = 0.5` and four thetas reports `butterfly_free: true` and `calendar_free: true`, and returns `w = theta` at `k = 0`, as it must.

**The surface.** Plain idea: a grid of vols is useful only if prices read off it cannot be arbitraged. Formal statement: `vol.surface.check` tests that total variance does not fall with expiry (calendar) and that call prices are convex in strike (butterfly), on the grid points. Case `surface-0003`: four expiries by five moneyness points; no violations, `arbitrage_free: true`. A check on grid points says nothing between them.

**SABR.** Plain idea: SABR lets the forward's vol itself be random, which gives skew and smile from four numbers. Hagan's 2002 formula turns them into a Black vol. It is an expansion, good near the money and at short expiries. At low strikes and long expiries the call prices it implies stop being convex in strike: the density, `d^2 C / dK^2`, goes negative. A shift moves the point where this happens; it does not remove it (C4). Formal statement: `vol.sabr.density` checks the density on given strikes; with `REJECT`, a negative value is `E_ARBITRAGE`. Case `sabr-0013`: forward 0.02, `T = 20`, `alpha = 0.03`, `beta = 0.5`, `rho = -0.3`, `nu = 0.5`. Density at strike 0.0005 is -174.57449723243258, and it is negative at the six lowest strikes. The arbitrage-free method (Hagan, Kumar, Lesniewski and Woodward, 2014) solves a one-dimensional forward equation for the density on a fixed grid, absorbing at zero, so density stays non-negative and probability is conserved. Case `sabr_deep-0003`: `T = 2`, `alpha = 0.3`, `beta = 0.5`, `rho = -0.4`, `nu = 0.5`. Mass 1.000000000000003, of which 0.023010749703289823 is absorbed at zero; lowest density 1.4e-6; ATM vol 0.3048962678257784. At `nu > 0` this method has no tight outside source; the `nu = 0` cases are checked against CEV.

**Use case 3: vol surface.** Plain idea: from call and put bid and ask quotes, infer each expiry's forward by put-call parity, fit SVI per expiry, check the surface, then price and risk a target option. Formal statement in `use-cases.md`. Case `usecases_c-0001`: three expiries of 11 synthetic quotes each. Forwards 5012.481305847661, 5024.993768294455 and 5050.250835420839. SVI RMSE below 1e-16 on each, because the quotes were made from an SVI. `arbitrage_free: true`. Buying 3 calls at 5100 expiring 2027-05-07 gets vol 0.17261062692922427, PV 621.6085879585307, delta 1.4063042744345948 and vega 4176.011752554645. A near-zero RMSE shows the fit works; on real quotes it would not be zero.

Nothing in these examples is traded.

### Known limits

Stage C is Implemented, not Validated. All inputs are synthetic: the stage C data survey found no free history of option quotes, vol surfaces, borrow cost or dividends. European options only (C1). Arbitrage checks run on the given points only. `vol.sabr.arbfree` at `nu > 0` lacks a tight outside source. See `specifications/stage-c-rulings.md`.

## Stage D: Curves and fixed income

**Status: built, target v0.4.** Implemented, not Validated. At merge `95cbf11` on 2026-11-07, each of the four implementations passed 5,514 of 5,514 golden cases locally, 331 of them in stage D's 20 suites (`conformance/README.md`). `specifications/stage-d-handover.md` lists every stage D spec; rulings D1 to D64 are in `specifications/stage-d-rulings.md`.

### Learning path

| Item | Plain idea | Formal statement |
|---|---|---|
| D1 OIS, ESTR, jumps | One discount curve from overnight swap quotes; a year-end jump is a one-off factor | `02-curves/ois-curves.md`, `curve-framework.md` |
| D1 compounding | A coupon compounds one fixing a day; the window may be shifted so the amount is known early | `02-curves/overnight-compounding.md` |
| D1 meeting steps | Overnight rates move on central-bank dates and stay flat between them | `02-curves/meeting-steps.md` |
| D1 convexity, CSA, basis, fits | Futures sit above forwards; collateral sets the discount curve; two indices differ by a spread; fits can be smoothed or made robust | `futures-convexity.md`, `csa-and-basis.md`, `03-calibration/curve-fits.md` |
| D2 bonds, repo | A bond is its cash flows; repo finances it; a futures contract delivers the cheapest bond | `04-pricing/bonds.md` |
| D3 cross-currency | Foreign cash flows under domestic collateral discount on a basis-adjusted curve. The swap is a synthetic constant-notional basis swap, not the market's mark-to-market resetting one (ruling R1-1; register row E13, stage F) | `02-curves/cross-currency.md` |
| D4 credit | Survival probabilities from CDS spreads, by the ISDA model. The discount curve must be `LOG_LINEAR_DF` (ruling R1-4) | `04-pricing/credit.md` |
| D5 equity | Futures imply dividends and borrow; an index changes by its divisor | `02-curves/equity-curves.md`, `04-pricing/equity-index.md` |
| D6 inflation | A CPI curve from zero-coupon swaps, with a monthly seasonal pattern | `02-curves/inflation.md` |
| D7 caps, swaptions | Black or Bachelier on a forward rate, times an annuity. Conventions are stylised: synthetic term index, no fixing lag, annual 30/360 fixed leg (ruling R1-5) | `05-volatility/caps-and-swaptions.md` |
| D8 commodities | Forward curves with seasons; storage links two delivery dates | `02-curves/commodity.md` |
| D9 MBS | A mortgage pool pays down early at a modelled speed | `04-pricing/mbs.md` |

### Worked examples

Every number below is a golden value in `datasets/golden/stage_d/`, which all four builds match within tolerance.

**Lookback.** Plain idea: a SOFR coupon compounds daily fixings, but with a 2-day lookback each day uses the fixing of two business days earlier, so the amount is known before payment. Formal statement: `growth = prod(1 + r_i w_i/360)`, rate `(growth - 1) 360 / sum w_i`, with weights from the interest period. Case `compound_d-0002`: 2026-11-10 to 2027-02-10, lookback 2: compounded rate 0.04333939898551821, accrual 0.25555555555555554, interest 0.011075624185187987 per unit. QuantLib's `OvernightLeg` agrees within 5e-14 (`oracle/REPORT.md`).

**Meeting steps.** Plain idea: the overnight forward is flat between meetings. Formal statement: `D(d) = exp(-integral f)`, `f` a step function. Case `steps_d-0001`: base 0.0425 until a step to 0.04 on 2026-12-10. The discount factor is 0.9961649070718093 on 2026-12-09 and 0.9960489220202466 on the step date; the forward reads 0.0425, then 0.04. A step takes effect on its date (ruling D6).

**Bond from yield.** Plain idea: discount each cash flow at the yield, compounded at the coupon frequency. Formal statement in `bonds.md`. Case `bonds_d-0001`: 4.25% semi-annual bond to 2029-11-15, settled 2026-11-09, yield 0.041. Clean 100.42085974293727, accrued 2.0557065217391304, modified duration 2.7494914473141594, convexity 9.306657676461866. QuantLib `FixedRateBond` agrees within 1e-10.

**ISDA CDS.** Plain idea: protection pays `1 - R` on default; the buyer pays a running coupon, and an upfront settles the difference. Formal statement in `credit.md`. Case `credit_d-0004`: buy 10 million of protection to 2031-12-20, coupon 100 bp, recovery 0.4. Par spread 0.011999999988591251, clean upfront 0.009002551543707455, PV 89977.4324589857. QuantLib's `IsdaCdsEngine` agrees within 7e-16 per unit.

**Inflation swap.** Plain idea: one payment swaps realised inflation for a fixed rate. Formal statement in `inflation.md`. Case `inflation_d-0007`: receive 5-year inflation against 2.6% fixed on 10 million. Index ratio 1.1286513715776638, below `1.026^5`, so receiving inflation is worth -69569.4851246751.

**Swaption.** Plain idea: Black on the forward swap rate, times the annuity. Case `capswaption_d-0010`: 1y into 5y payer, strike 3.7%, vol 0.21. Forward rate 0.0357181339683658, annuity 4.351040526247382, price 106969.44213342607 on 10 million.

**Storage.** Plain idea: a later forward above the earlier one plus financing and storage means cash and carry earns money. Case `commodity_d-0007`: from the March to the June 2027 forward the convenience yield is -0.03607983964691383, and buying forward, storing and selling forward earns 0.6708164887620427 a unit, so `arbitrage` is true for that segment.

**MBS.** Plain idea: a pool pays principal early at a speed, here 150% PSA, which shortens its life. Case `mbs_d-0004`: 60-month pool, 6.5% WAC, 6% net, yield 5.5%, 24-day delay. Price 100.76748931062598, WAL 2.4872786417395525 years.

Nothing in these examples is traded.

### Known limits

Stage D is Implemented, not Validated. All inputs are synthetic. The ESTR payment lag of 2 is a library choice (Strata), not a market standard; TP ICAP terms use 1 (ruling R1-2). From R1, bond-future conversion factors take an optional `contract` input with CME rounding; `null` keeps the stage D `TEN_YEAR` behaviour (ruling R1-3). The stage D data survey (2026-11-07) found free overnight fixings, fitted Bank of England curves, US Treasury par and real curves and UK CPI, but no free swap quotes, bond-level prices, special repo, cross-currency basis, CDS spreads, borrow, commodity curves or MBS factors; those studies stay method tests. Several suites have no outside oracle (CSA discounting, asset swap, FRN, repo, NDF, equity, inflation, commodities, MBS); `specifications/stage-d-rulings.md` lists them. R1 counts outside-oracle cases under a stricter rule: QuantLib is built from its own convention objects through one reviewed table, `oracle/CONVENTION_MAP.md`. On that rule, 419 of the 654 stage D cases (64.1%; most counted cases are fixed-rate bonds) count, suite by suite in `oracle/REPORT.md`.

### What a tolerance means in money

A tolerance such as 1e-10 says little to a desk. `conformance/tolerances/money.md` restates every class, and every per-case limit, as an error on a 10m notional: basis points of DV01 on a 10Y swap, 32nds of a bond price, and currency units. The widest class, `numerical_scheme`, allows about 1e-4 bp of a 10Y swap's DV01, under one currency unit on 10m. Present-value limits are 1e-9 of notional, which is 0.01 on 10m.

## R2: Risk

**What is being built.** Phase R2 (target v0.4.2) adds four risk operations on top of the existing pricers: `risk.curve.par`, `risk.curve.key_rate`, `risk.curve.jacobian` and `risk.pnl.explain`. All risk is bump and revalue (ADR-0010), and every number is money per basis point, signed: risk is the change in value for a +1 bp move, so a receiver of fixed, which loses when rates rise, has a negative DV01 (the 2Y receiver below: -4,806.94). Specs: `specifications/06-risk/par-and-key-rate.md` and `pnl-explain.md`. Goldens: `datasets/golden/r2/`, 41 risk cases and 44 P&L explain cases, each re-priced in QuantLib 1.44. The language builds are landing, so the numbers below are the oracle's expected values, not yet CLI output.

The worked examples share one trade: receive 3.45% fixed against SOFR on 25 million for 2 years, on a synthetic 13-quote SOFR curve (1W to 30Y) as of 2026-11-06. Its value is -24,052.57.

### Par risk against zero risk

**Plain idea.** A desk hedges with instruments it can trade, so it wants risk to the quotes it sees: "if the 2Y swap rate moves 1 bp, I lose this much". That is par risk. Zero-rate risk moves the curve itself instead. It is cheaper, because no curve is rebuilt, but nobody trades a zero rate.

**Formal statement.** `risk.curve.par` bumps the par quotes and rebuilds the curve with `rates.ois.bootstrap`, by central difference: `risk = (V(+h) - V(-h)) / (2 bump_bp)`. `par_dv01` bumps every quote together; `par_buckets[j]` bumps quote `j` alone. `risk.curve.key_rate` shifts continuously compounded zero rates on a given curve, with no rebuild; its `zero_dv01` is the parallel shift `D(t) exp(-h t)`.

**Worked example.** `risk_r2-0001`: par DV01 -4,806.94, nearly all of it (-4,808.13) in the 2Y bucket, the trade's own tenor. On the same curve, `risk_r2-0002` gives zero DV01 -4,913.22. They differ by about 2%, because a 1 bp move in par rates is not a 1 bp move in zero rates.

### Key-rate buckets: triangular against pillar

**Plain idea.** Bucketed risk splits the parallel number by maturity. There are two usual ways to shift "the 2Y point": put a tent of shift around 2 years that falls to zero at the neighbouring key dates, or bump only the curve node at 2 years and let interpolation carry it.

**Formal statement.** In `TRIANGULAR` mode the weight `w_i(t)` is 1 at key date `k_i`, falls linearly to 0 at its neighbours, and stays at 1 beyond the end key dates, so the weights sum to 1 at every date. Bucket `i` revalues on `D(t) exp(-w_i(t) h t)`, a shift at every date, not only at nodes. In `PILLAR` mode bucket `i` multiplies only pillar `i`'s discount factor by `exp(-h t_i)` and re-interpolates. In both modes the buckets sum to `zero_dv01` to first order.

**Worked example.** `risk_r2-0002` (triangular, key dates on the pillars) and `risk_r2-0004` (pillar) both give zero DV01 -4,913.22, but split it differently: the 2Y bucket is -4,802.59 triangular and -4,828.70 pillar, the 1Y bucket -135.59 and -110.67.

### The Jacobian, and why the chain rule holds only for pillars

**Plain idea.** The Jacobian says how each zero rate on the curve moves when one par quote moves. With it, zero risk turns into par risk without rebuilding the curve once per quote.

**Formal statement.** `risk.curve.jacobian` returns `J[i][j] = dz_i / dq_j` by central difference, with `z_i = -ln D(p_i) / t_i` at pillar `i`. It is lower triangular, because a bootstrapped pillar depends only on quotes up to its own tenor. By the chain rule, `par_buckets[j] ~ sum_i key_rates[i] J[i][j]`, but only for `PILLAR` key rates. The Jacobian describes how the pillars move; a triangular shift also moves the curve between pillars in a way no combination of pillar moves reproduces.

**Worked example.** `risk_r2-0031` is this curve's Jacobian; its first entry is 1.0131. Multiplying the pillar key rates of `risk_r2-0004` by it gives -4,808.1269 in the 2Y bucket, the par bucket of `risk_r2-0001` to every digit shown, and a total of -4,806.9447, its par DV01. The same sum with the triangular key rates of `risk_r2-0002` gives -4,782.13 in the 2Y bucket, 26 off. The oracle checks the pillar identity on every product, within 1e-3 of `par_dv01`.

### P&L explain

**Plain idea.** If the risk numbers are right, risk times the market move should predict the day's P&L. A desk runs this control every day against full revaluation: a large unexplained part points to a broken curve, pricer, risk number or feed.

**Formal statement.** `risk.pnl.explain` builds curves from `quotes_start` and `quotes_end` on one `as_of`, so no time passes and there is no carry or theta (stage F adds those). `full_pnl = value_end - value_start`; `risk_pnl = sum_j par_buckets[j] (q_end[j] - q_start[j]) / 0.0001`; `unexplained = full_pnl - risk_pnl`. The day is explained when `|unexplained| <= max(0.05 |full_pnl|, 0.05 |par_dv01|)`, fixed in the spec rather than tuned per product; the floor stops quiet days failing on noise. The threshold formula is under review (audit item 3); the formula below is the one in spec 1.0.0 and may change: TODO.

**Worked example.** `pnl_r2-0001`, every quote up 1 bp: full P&L -4,806.23, risk P&L -4,806.94, unexplained 0.71 against a threshold of 240.35, so explained. `pnl_r2-0011` shows the control failing: paying fixed on a 10Y swap of 10 million with every quote up 150 bp. Full P&L 1,171,652, risk P&L 1,263,161, unexplained -91,509 against a threshold of 58,583. On a move that size, convexity, which first-order risk leaves out, is too large. Of the 42 goldens that return a result (the other 2 are errors), 4 are unexplained, all large shocks on 10Y and longer products.

**On real moves.** `tools/workflows/pnl_explain.py` runs the control over consecutive days of the US Treasury par curve, a proxy for SOFR swap rates. R2 acceptance is at least 95% of days explained for every product. Share of days explained: TODO, waiting on the first run.

**Calibration stability and rich/cheap.** R2 also specifies a calibration stability report (`specifications/03-calibration/stability.md`) and workflow (b), a Treasury and gilt rich/cheap screen (`specifications/04-pricing/workflow-b-rich-cheap.md`). Both run existing operations in batch mode. Stability first run: TODO. Rich/cheap first report: TODO.

## Batch mode

**Plain idea.** Starting a program costs time: a JVM can take far longer to start than to price one swap. Batch mode starts the CLI once and feeds it many cases, one JSON document per line, getting one result line back for each. The fuzz driver and the benchmarks depend on it.

**Formal statement.** `specifications/cli-contract.md`, section "Batch mode", contract 1.6.0. Eight rules, BT1 to BT8. The ones worth knowing first:
- a line in gives exactly one line out, in the same order, even when the line is empty or not JSON (BT3);
- the result for a line equals what `run` gives for the same bytes, bit for bit (BT4), so batch is only a faster way to call `run`;
- no state carries between lines, so reordering the input reorders the output and changes nothing else (BT7);
- exit 0 at end of input whatever each case returned; exit 70 only for an internal fault (BT8).

**Worked example.** `examples/batch.jsonl` holds four cases. Through the Rust build, the third gives Brent's root of the Wallis cubic, `2.094551481542327`, the same bits as `run` on that line alone, and the fourth gives `E_DATE_ORDER` while the exit code stays 0. The Cookbook's [Batch mode](COOKBOOK.md#batch-mode) recipe shows the full output.

**Where it is checked.** `datasets/batch/streams.json` has 19 stream fixtures. `conformance/runner/batch_check.py` runs them, and also checks batch against `run`, reordering and interactive use (a caller writes one line and waits). On the v0.4 builds, 14 of the 19 streams passed; the five failures were the R1 additions: the over-long-line rule (BT5), `--batch` and `--timings`. On `r1` at `3f5d97d` the Rust build passes every check, including the per-case `run` comparison, and the Python build passes every check with `--skip-run`; the other two were not rerun in this pass.

## Validate and backtest

Stages A to C test correctness with analytic, hand and outside-library answers. Stages B and C add calibration on known truth. Later stages add backtests and new-model tests. `specifications/stage-b-rulings.md` says which stage B suites have an outside oracle. Evidence is always labelled analytic, simulated, proxy or observed, and validation reports are self-assessment until the human review at the end of the project.

R1 adds the records that say how far each result goes. The [model inventory](docs/model-inventory.md) gives every model its spec, oracle, outside-checked share and limits. The [edge-case register](specifications/edge-case-register.md) lists boundary cases and whether a golden pins each one; a row marked out of scope names the stage that would bring it in. `conformance/tolerances/money.md` restates every tolerance as money on 10 million notional, so a reader can judge whether a pass is tight enough to matter. The R1 daily workflows are the first runs on observed public data, and their USD curve is labelled a proxy.
