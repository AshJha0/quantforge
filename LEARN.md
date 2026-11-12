# Learn QuantForge

A path through the project, by topic. Each topic goes from the plain idea, to the formal statement in a spec, to a worked example. The order in which the stages were built is in the [appendix](#appendix-stage-history).

## Start here

QuantForge has four equal implementations of the same maths, in Java, C++, Python and Rust. None is the reference. Expected answers come from `oracle/`, because four programs agreeing proves only that they agree.

Two ways in:

- **New to quantitative finance, or to this project.** Work through the [tutorials](docs/getting-started/README.md), starting with [Tutorial 1: price your first swap](docs/getting-started/tutorial-1-swap.md): quotes to curve to PV to DV01 in about 10 minutes, in Python, then the same in Rust, Java and C++. Tutorials 2 to 16 go on, 10 to 15 minutes each, to bonds and repo, options and volatility, credit, risk, interest rate models, counterparty risk, multi-curve building, cross-currency and FX, inflation and commodities, mortgage-backed securities, exotic options, time series and vol indices, the trading book, advanced risk and the LIBOR market model, with every number checked in all four languages. Tutorials 17 to 21 cover stage I, hedging: Greek and dynamic delta hedges, minimum-variance and constrained hedges, credit and correlation hedges, a cross-asset hedge with instrument selection, and what a hedge costs. Then read the topics below in order.
- **Practitioner.** Jump to a topic. Each worked example names its golden case, so you can rerun it as `COOKBOOK.md` shows and check the number yourself.

**What the tests check.** 7,441 value-checked golden cases, where each build must return the oracle's numbers within a stated tolerance; 5,122 error cases, which check only that a bad input is refused with the right code; and 2,514 invariance cases (1,257 pairs), which check that two related inputs get the same answer. Counts are generated in [`docs/case-figures.md`](docs/case-figures.md). Outside-library shares per stage, under the tight rule D6, are in [`oracle/OUTSIDE_SHARES.md`](oracle/OUTSIDE_SHARES.md).

Sources: every model and convention cites its papers, books and standards in the sources list of its spec. [References](docs/references.md) collects them all by topic, with each one's status (read, not opened, or paywalled) and the specs that rely on it.

Each result below is real output from the CLIs, on the date each section gives. Unless a section says otherwise, Java, C++, Python and Rust printed the same value.

| Topic | What it covers |
|---|---|
| [Foundations](#foundations) | Day counts, calendars, compounding, solvers, random numbers, the CLI and batch mode |
| [Curves and fixed income](#curves-and-fixed-income) | OIS and projection curves, FX forwards, overnight compounding, bonds, inflation, commodities, MBS |
| [Options and volatility](#options-and-volatility) | Black models, Greeks, smiles and surfaces, SABR, local and stochastic vol, exotics, rates vol, GARCH, variance and the VIX |
| [Credit and correlation](#credit-and-correlation) | ISDA CDS, CDS options, copulas, correlation matrices and dispersion |
| [Risk, hedging and use cases](#risk-hedging-and-use-cases) | Bump and rebuild, par and key-rate risk, the Jacobian, P&L explain, hedges, use cases 1 to 3 |
| [Validation and evidence](#validation-and-evidence) | What a pass means, tolerances in money, what an outside library does not check |
| [Stage F: curves, portfolio risk and the book](#stage-f-curves-portfolio-risk-and-the-book) | Interpolation, joint solve, AAD, VaR and backtests, FRTB GIRR, book |
| [Stage G: rates models and xVA](#stage-g-rates-models-and-xva) | Short-rate models, swaptions and Bermudans, LMM, MC Greeks, exposure, CVA, DVA and FVA |

## Foundations

Specs are in `specifications/01-core/`. Exercises are in `program/exercises/`. Recipes in the [Cookbook](COOKBOOK.md#stage-a-recipes).

### Learning path

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

### Batch mode

**Plain idea.** Starting a program costs time: a JVM can take far longer to start than to price one swap. Batch mode starts the CLI once and feeds it many cases, one JSON document per line, getting one result line back for each. The fuzz driver and the benchmarks depend on it.

**Formal statement.** `specifications/cli-contract.md`, section "Batch mode", contract 1.6.0. Eight rules, BT1 to BT8. The ones worth knowing first:
- a line in gives exactly one line out, in the same order, even when the line is empty or not JSON (BT3);
- the result for a line equals what `run` gives for the same bytes, bit for bit (BT4), so batch is only a faster way to call `run`;
- no state carries between lines, so reordering the input reorders the output and changes nothing else (BT7);
- exit 0 at end of input whatever each case returned; exit 70 only for an internal fault (BT8).

**Worked example.** `examples/batch.jsonl` holds four cases. Through the Rust build, the third gives Brent's root of the Wallis cubic, `2.094551481542327`, the same bits as `run` on that line alone, and the fourth gives `E_DATE_ORDER` while the exit code stays 0. The Cookbook's [Batch mode](COOKBOOK.md#batch-mode) recipe shows the full output.

**Where it is checked.** `datasets/batch/streams.json` has 19 stream fixtures. `conformance/runner/batch_check.py` runs them, and also checks batch against `run`, reordering and interactive use (a caller writes one line and waits). On the v0.4 builds, 14 of the 19 streams passed; the five failures were the R1 additions: the over-long-line rule (BT5), `--batch` and `--timings`. On `r1` at `3f5d97d` the Rust build passes every check, including the per-case `run` comparison, and the Python build passes every check with `--skip-run`; the other two were not rerun in this pass.

## Curves and fixed income

All quotes here are synthetic, because no free quote history exists: you are learning the method, not a market. **See it.** The [Curves gallery](docs/curves/README.md) has a page for each implemented curve, with charts and numbers from real runs of all four CLIs on synthetic inputs. Start with [SONIA OIS](docs/curves/sonia-ois.md), then [SOFR](docs/curves/sofr-ois.md), [the projection curve](docs/curves/usd-term-3m.md) and [the FX forward](docs/curves/gbpusd-fx-forward.md).

### Learning path

Specs are in `specifications/`, under the folder named. Step numbers continue from Foundations.

| Step | Plain idea | Read | Try |
|---|---|---|---|
| 9 | Money has a currency, and a convention is a record | `01-core/units-and-money.md`, `01-core/conventions.md` | Add two currencies and read the error |
| 10 | A swap's dates come from rules | `02-curves/schedules.md` | Find the short first stub in a `schedule` case |
| 11 | A curve says what one unit later is worth today | `02-curves/curve-framework.md` | Compare a forward under both interpolations |
| 12 | A curve is whatever makes every quote reprice | `02-curves/ois-curves.md` | EX-006 |
| 13 | Forecast on one curve, discount on another | `02-curves/projection-and-fra.md` | Price an FRA from a `projection` case |
| 14 | A forward follows from two curves and no arbitrage | `02-curves/fx.md` | EX-005 |

Then the wider curve set, built in stage D:

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

**Curve bootstrap (stage B).** Plain idea: find the discount factors at which every quoted swap is worth zero. Formal statement: solve `K_j(curve) = quote_j` for every quote `j`, in `ois-curves.md`. `examples/ois_bootstrap.json` holds 13 synthetic SONIA quotes from 1W to 30Y, as of 2026-11-06. `rates.ois.bootstrap` gives a 5Y discount factor of 0.8480030126521996 at 2031-11-06, and the Rust build reports a `max_repricing_error` of 1.8e-15. The four builds agree to about 15 digits, not to the last bit. An exact repricing here shows the solve works. It would show the same on any coherent quotes, so it says nothing about a market.

The stage D examples below are golden values in `datasets/golden/stage_d/`, which all four builds match within tolerance.

**Lookback.** Plain idea: a SOFR coupon compounds daily fixings, but with a 2-day lookback each day uses the fixing of two business days earlier, so the amount is known before payment. Formal statement: `growth = prod(1 + r_i w_i/360)`, rate `(growth - 1) 360 / sum w_i`, with weights from the interest period. Case `compound_d-0002`: 2026-11-10 to 2027-02-10, lookback 2: compounded rate 0.04333939898551821, accrual 0.25555555555555554, interest 0.011075624185187987 per unit. QuantLib's `OvernightLeg` agrees within 5e-14 (`oracle/REPORT.md`).

**Meeting steps.** Plain idea: the overnight forward is flat between meetings. Formal statement: `D(d) = exp(-integral f)`, `f` a step function. Case `steps_d-0001`: base 0.0425 until a step to 0.04 on 2026-12-10. The discount factor is 0.9961649070718093 on 2026-12-09 and 0.9960489220202466 on the step date; the forward reads 0.0425, then 0.04. A step takes effect on its date (ruling D6).

**Bond from yield.** Plain idea: discount each cash flow at the yield, compounded at the coupon frequency. Formal statement in `bonds.md`. Case `bonds_d-0001`: 4.25% semi-annual bond to 2029-11-15, settled 2026-11-09, yield 0.041. Clean 100.42085974293727, accrued 2.0557065217391304, modified duration 2.7494914473141594, convexity 9.306657676461866. QuantLib `FixedRateBond` agrees within 1e-10.

**Inflation swap.** Plain idea: one payment swaps realised inflation for a fixed rate. Formal statement in `inflation.md`. Case `inflation_d-0007`: receive 5-year inflation against 2.6% fixed on 10 million. Index ratio 1.1286513715776638, below `1.026^5`, so receiving inflation is worth -69569.4851246751.

**Storage.** Plain idea: a later forward above the earlier one plus financing and storage means cash and carry earns money. Case `commodity_d-0007`: from the March to the June 2027 forward the convenience yield is -0.03607983964691383, and buying forward, storing and selling forward earns 0.6708164887620427 a unit, so `arbitrage` is true for that segment.

**MBS.** Plain idea: a pool pays principal early at a speed, here 150% PSA, which shortens its life. Case `mbs_d-0004`: 60-month pool, 6.5% WAC, 6% net, yield 5.5%, 24-day delay. Price 100.76748931062598, WAL 2.4872786417395525 years.

Nothing in these examples is traded.

## Options and volatility

All inputs are synthetic: no free history of option quotes, borrow cost or dividends was found. Specs in `specifications/05-volatility/`, `02-curves/equity-forward.md` and `06-risk/vol-greeks.md`.

### Learning path

| Step | Plain idea | Read | Try |
|---|---|---|---|
| 19 | A forward is the stock carried, less the dividends carried | `02-curves/equity-forward.md` | `equity_forward-0001` |
| 20 | One formula, three models, told apart by how the forward spreads | `05-volatility/black-models.md` | Price, then solve the vol back |
| 21 | A Greek is a slope of the price | `06-risk/vol-greeks.md` | `risk.vol.greeks` against `risk.vol.bump_greeks` |
| 22 | Desks quote strikes by delta | `05-volatility/smile-and-surface.md` | `vol.smile.rr_bf` |
| 23 | A smile is a curve in total variance, and some curves allow arbitrage | Same | `vol.svi.evaluate`, then read `g` |
| 24 | A surface is smiles that must not cross | Same | `vol.surface.check` |
| 25 | A popular formula can imply a negative density | `05-volatility/sabr.md` | `vol.sabr.density`, then `vol.sabr.arbfree` |

Then the full volatility set, built in stage E:

| Topic | Plain idea | Read |
|---|---|---|
| Arbitrage-free surfaces | A surface must not allow free money across strikes or expiries | `05-volatility/arb-free-surfaces.md` |
| Local and forward vol | One vol function that reprices every option | `05-volatility/local-and-forward-vol.md` |
| FX smile | FX quotes strikes by one of several deltas | `05-volatility/fx-smile.md` |
| Heston family and SLV | Let variance itself move | `05-volatility/heston-family.md` |
| Exotics and American options | Change the payoff, or the exercise | `04-pricing/exotics.md` |
| Rates vol | Caps, swaptions and the swaption cube | `05-volatility/caps-and-swaptions.md`, `rates-vol-cube.md` |
| GARCH, variance swaps, VIX | Vol that remembers, and vol priced from a strip | `garch.md`, `variance-swaps.md`, `vix-index.md` |

### Worked examples

**Option price.** Plain idea: a method can be checked against a formula. For spot and strike 100, `r` 0.05, `q` 0.02, `sigma` 0.2 and `t` 1, the Black-Scholes value is 9.227006 (`oracle/REPORT.md`). `core.cos.european` with 256 terms gives 9.227005508154036, against a golden value of 9.227005508154049, inside class `fourier`. This is an analytic test on constructed inputs, not a market price.

Every number below is from the Rust CLI on 2026-11-07, on the inputs of the named golden case. All four builds pass these cases within the targets.

**Equity forward.** Plain idea: holding the stock to expiry costs funding at `r`, earns the borrow fee `b` if lent out, and pays out the dividends. So the forward is the stock grown at `r - b`, less each dividend grown from its date to expiry. Formal statement, flat rates: `F = S e^{(r-b)T} - sum A_i e^{(r-b)(T - t_i)}`. With curves, dividends are carried on `C = D/B` (ruling C2), and option PVs are discounted on `D` alone (C3). A common slip is `(S - PV(D)) e^{(r-b)T}` with `PV` taken at `r`: it discounts each dividend at `r`, then grows it back at `r - b`, which matches only when `b = 0`. Take the PV at `r - b` and the two forms agree. Case `equity_forward-0001`: `S = 100`, `r = 0.04`, `b = 0.05`, a dividend of 2 at `t = 0.5`, `T = 1`. `eq.forward.flat` gives 97.01495841653144. The wrong form gives 97.0640923: close enough to pass a glance, so it is a named check (tag `wrong-convention`). QuantLib's `AnalyticDividendEuropeanEngine` agrees with the right form (C14).

**Black, Black-76 and Bachelier.** Plain idea: all three price a call as the expected payoff on a driftless forward, discounted. Black-Scholes and Black-76 make the forward lognormal, so vol is relative, written as a decimal: 0.2 is 20% a year (ruling C7). Bachelier makes it normal, so vol is in price units per square root of year and the forward may go negative. Formal statement: Black-76 call `D (F N(d1) - K N(d2))`, `d1,2 = (ln(F/K) ± v^2 T/2) / (v sqrt T)`. Black-Scholes is Black-76 with `F = S e^{(r-q)T}` and `D = e^{-rT}`, from spot, rate and yield. Bachelier call `D ((F - K) N(d) + v sqrt(T) n(d))`, `d = (F - K) / (v sqrt T)`. Puts follow from parity, the same in all three: `call - put = D (F - K)`. Price rises with vol, so an implied vol is unique when the price lies between intrinsic `D max(F - K, 0)` and, for lognormal calls, `D F` (`black-models.md`). Case `black-0001`: `F = K = 100`, `T = 1`, `D = 0.9704455335485082`, vol 0.2. Black-76 gives 7.730149359277918; case `black-0002` sends that price to `vol.option.implied` and expects 0.2. Case `black-0005`: the same under Bachelier with vol 20 gives 7.743035083184538, close to Black-76 because 20 in price units is 20% of 100 at the money.

**Greeks.** Plain idea: delta, gamma, vega, theta and rho are slopes of the price to spot, spot again, vol, time and rate; vanna and volga are second slopes involving vol. Formal statement: closed forms in `vol-greeks.md`, checked against bumps in the oracle. Vega and volga are per 1.00 of vol (C7), theta is `-dV/dT` per year, rho per 1.00 of rate. For Black-Scholes, `delta = e^{-qT} N(d1)`, `vega = S e^{-qT} n(d1) sqrt T`, `rho = K T e^{-rT} N(d2)`. Case `greeks-0001`: Black-Scholes call, `S = K = 100`, `r = 0.03`, yield 0.01, vol 0.2, `T = 1`. Price 8.827321225352126, delta 0.5734959790277754, gamma 0.01935758770796135, vega 38.715175415922694, theta -4.753689862887256, rho 48.5222766774254. Vanna and volga print as about 4e-16 and -8e-15. They are zero up to rounding: both scale with `d2`, and here `d2 = 0`.

**Delta conventions.** Plain idea: a 25-delta call is the strike where the call's delta is 0.25, so the strike depends on the vol and on which delta is meant. Spot delta carries a discount factor; forward delta does not. `scale` says which: `SPOT` needs a number, `FORWARD` needs `null` (C15). Case `smile-0001`: forward 100, vol 0.22, `T = 0.75`, forward delta 0.25 gives strike 115.79573605232507. Case `smile-0025`: ATM 0.2, risk reversal -0.04, butterfly 0.006 give a 25-delta call vol of 0.186 at 115.34449734852197 and a put vol of 0.226 at 88.08246715793778, from `call = atm + bf + rr/2` and `put = atm + bf - rr/2`.

**SVI and SSVI.** Plain idea: write the smile as total variance `w = v^2 T` against log-moneyness `k`. SVI is a five-parameter hyperbola in `k`; it fits well, but some parameter sets imply a negative density. SSVI ties all expiries to one shape driven by the ATM variance `theta`, with simple conditions that rule out arbitrage. Formal statement: `w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + sigma^2))`. A smile is butterfly-free where Gatheral's `g(k) >= 0`. A surface is calendar-free where `w` does not fall as `T` rises at fixed `k`. Case `smile-0028`: `a = 0.03`, `b = 0.12`, `rho = -0.35`, `m = 0.02`, `sigma = 0.15`, `T = 1.5`. At `k = 0`, `w = 0.04899929514050587`, vol 0.180737922861632 and `g = 1.372275771715203`; `g` is positive on all nine points. Case `smile-0039`: SSVI with `rho = -0.4`, `eta = 1`, `gamma = 0.5` and four thetas reports `butterfly_free: true` and `calendar_free: true`, and returns `w = theta` at `k = 0`, as it must.

**The surface.** Plain idea: a grid of vols is useful only if prices read off it cannot be arbitraged. Formal statement: `vol.surface.check` tests that total variance does not fall with expiry (calendar) and that call prices are convex in strike (butterfly), on the grid points. Case `surface-0003`: four expiries by five moneyness points; no violations, `arbitrage_free: true`. A check on grid points says nothing between them.

**SABR.** Plain idea: SABR lets the forward's vol itself be random, which gives skew and smile from four numbers. Hagan's 2002 formula turns them into a Black vol. It is an expansion, good near the money and at short expiries. At low strikes and long expiries the call prices it implies stop being convex in strike: the density, `d^2 C / dK^2`, goes negative. A shift moves the point where this happens; it does not remove it (C4). Formal statement: `vol.sabr.density` checks the density on given strikes; with `REJECT`, a negative value is `E_ARBITRAGE`. Case `sabr-0013`: forward 0.02, `T = 20`, `alpha = 0.03`, `beta = 0.5`, `rho = -0.3`, `nu = 0.5`. Density at strike 0.0005 is -174.57449723243258, and it is negative at the six lowest strikes. The arbitrage-free method (Hagan, Kumar, Lesniewski and Woodward, 2014) solves a one-dimensional forward equation for the density on a fixed grid, absorbing at zero, so density stays non-negative and probability is conserved. Case `sabr_deep-0003`: `T = 2`, `alpha = 0.3`, `beta = 0.5`, `rho = -0.4`, `nu = 0.5`. Mass 1.000000000000003, of which 0.023010749703289823 is absorbed at zero; lowest density 1.4e-6; ATM vol 0.3048962678257784. At `nu > 0` this method has no tight outside source; the `nu = 0` cases are checked against CEV.

**Swaption.** Plain idea: Black on the forward swap rate, times the annuity. Case `capswaption_d-0010`: 1y into 5y payer, strike 3.7%, vol 0.21. Forward rate 0.0357181339683658, annuity 4.351040526247382, price 106969.44213342607 on 10 million.

Evidence classes used in the stage E examples below: *golden* (the oracle's expected value, which every build now reproduces), *outside-checked* (re-priced in QuantLib 1.44 through a reviewed convention map), *observed* (a run on this machine), *reported* (stated in a build's commit), *cited* (a published source; "not opened" in a spec means the reference was checked from memory, and paywalled equation numbers are unverified).

### Arbitrage-free surfaces

**Plain idea.** A vol surface is only usable if no mix of options built from it makes money for nothing. Two things can go wrong. Along one expiry, call prices can stop being convex in strike (butterfly arbitrage: a negative probability density). Across expiries, total variance can fall as time grows (calendar arbitrage).

**Formal statement.** `specifications/05-volatility/arb-free-surfaces.md`. With total variance `w = sigma^2 T` in forward log-moneyness `k`, a slice is butterfly-free iff `g(k) >= 0` and `d_+ -> -inf` (Gatheral-Jacquier 2014, Lemma 2.2), and a surface is calendar-free iff `w(k, T)` rises with `T` at every `k` (Lemma 2.1). `vol.svi.surface_check` tests `g` and `w` on a grid, and tests the SVI wing slopes `b(1 +- rho)` against the Lee bound of 2, flagging a slope of exactly 2 (ruling E-A15).

**Worked example.** `surf_e-0007`: a 1-year slice whose wings sit below the 3-month slice. `calendar_violations` lists `k_index` 0 to 3 at expiry 1. `wing_violations` adds both wings, because the later slice is flatter and must cross below the earlier one far out, beyond the grid. With `reject: true` (`surf_e-0008`) the same surface is `E_ARBITRAGE`.

### Local vol and forward vol

**Plain idea.** Implied vol is one number per option. Local vol is the instantaneous vol, as a function of time and spot, that reproduces every option price at once. Forward vol is the vol that applies between two expiries.

**Formal statement.** `specifications/05-volatility/local-and-forward-vol.md`. Dupire local variance in total-variance form is `w_T / g` (Gatheral 2006, eq. 1.10; Dupire 1994). Forward vol is `sqrt((s2^2 T2 - s1^2 T1)/(T2 - T1))`, because variance adds over time (Hull, 10th ed.). A negative forward variance or a non-positive `g` is `E_ARBITRAGE`.

**Worked example.** `lv_e-0001`, the point `T = 1`, `k = 0` on the three-slice SVI surface: implied vol 0.25269, local vol 0.16776. Local vol is below implied vol at the money here because of the negative skew (`rho < 0`). The golden agrees within 1e-9 relative with a separate 40-digit Dupire computed from call prices (`stage-e-targets-a.md`).

### FX smile conventions

**Plain idea.** FX options are quoted by delta, not strike, and the market uses several deltas. Spot or forward delta, with or without the premium deducted, give different strikes for the same "25-delta" quote.

**Formal statement.** `specifications/05-volatility/fx-smile.md`, after Reiswich and Wystup 2012 and Clark 2011. Four delta types, three ATM types, Garman-Kohlhagen pricing (Garman and Kohlhagen 1983). A premium-adjusted call delta has two strikes; the spec takes the upper one (ruling E-A10).

**Worked example.** `fxs_e-0120`, a USDJPY-like pair (spot 151.20, six months, `rd` 0.10%, `rf` 4.50%, ATM 10.5%, 25-delta risk reversal -1.5, butterfly 0.35, premium-adjusted spot delta). Call vol 10.10%, put vol 11.60%, ATM delta-neutral strike 147.51, 25-delta call strike 155.03, put strike 140.20. All five outputs are reproduced by QuantLib `BlackDeltaCalculator`.

### Heston, Bates, Merton and SLV

**Plain idea.** Let variance itself be random and mean-reverting (Heston), add jumps (Bates), or keep vol constant and add only jumps (Merton). SLV mixes a stochastic vol with a local-vol correction (the leverage function), so the model fits the surface exactly while keeping realistic dynamics.

**Formal statement.** `specifications/05-volatility/heston-family.md`. Prices come from the Lewis single integral of the characteristic function (Lewis 2001), in the "little trap" form (Albrecher et al. 2007). The SLV leverage is `L^2 = sigma_LV^2 / E[v | x]` (Henry-Labordere 2009). It is computed by a fixed-grid Fokker-Planck reference scheme (ruling E-A14), which checks that the four builds follow the same recipe and is not a converged answer.

**Worked example.** `heston_e-0001` (`v0 = theta = 0.04`, `kappa` 1.5, `xi` 0.5, `rho` -0.7, one year): the 100-strike call is 8.1135, matched by QuantLib within 1e-9. As vol of variance tends to 0, Heston tends to Black-Scholes at the average variance, not at `v0` (plan section 8). `heston_e-0011` tests this at `xi = 1e-3`, near zero but not at it.

### Exotics and American options

**Plain idea.** Exotics change the payoff. It can depend on whether a barrier was touched, on an average, on a maximum, on a choice made later, on another currency, or on two assets. American options can be exercised early, which is worth something extra for puts, and for calls on a dividend-paying asset.

**Formal statement.** `specifications/04-pricing/exotics.md`: Reiner-Rubinstein barriers, Kemna-Vorst geometric Asians, Goldman-Sosin-Gatto lookbacks, the Rubinstein chooser, the Kirk spread, Levy moment matching, and for American options a CRR tree, Barone-Adesi-Whaley and a fixed-grid FD scheme (formulas as Haug 2007).

**Worked example.** `american_e-0002`: a one-year at-the-money put (`r` 5%, `q` 2%, vol 25%) on a 200-step tree. American 8.5588, European 8.2148, so early exercise is worth 0.3441. `exotic_e-0019`: a down-and-in call (strike 85, barrier 90, rebate 2) is 7.8991, reproduced by QuantLib `AnalyticBarrierEngine`.

The topics below cover slices E4, E6, E7 and E8. Specs: `specifications/05-volatility/rates-vol-cube.md`, `garch.md`, `variance-swaps.md`, `vix-index.md`, `specifications/06-risk/correlation.md` and `specifications/04-pricing/credit-options-and-copulas.md`; goldens in `datasets/golden/stage_e_b/`.

### Why a swaption cube interpolates parameters, not vols

**Plain idea.** A swaption's vol depends on three things: expiry, swap length and strike. Desks keep a small grid of expiries and lengths, and at each point a smile. Between grid points you could average the vols, but an average of two smiles is not, in general, a smile any model would produce. Averaging the SABR parameters instead keeps every in-between smile a proper SABR smile.

**Formal statement.** Each SABR parameter (`alpha`, `beta`, `rho`, `nu`) is bilinear in expiry time (ACT/365F to the adjusted node date) and swap length (months/12). The vol is the Hagan expansion of `sabr.md` at the swaption's own forward, and the price is D7's Black swaption (`rates-vol-cube.md`, ruling E-B8). The method is Hagan and co-authors (2002), "Managing smile risk", applied node by node.

**Worked example.** `ratesvol_e-0001` sits exactly on the 12M x 5Y node, so its parameters are the node's (`alpha 0.048, rho -0.27, nu 0.44`) and its vol is 25.265%. `ratesvol_e-0006` is 18M x 5Y: `rho` comes out at -0.27995, between the 12M (-0.27) and 24M (-0.29) nodes, weighted by time, not by months. Interpolating vols instead of parameters moves the price by more than 0.01 on 10m in every off-node case; it is one of the 34 E4 wrong-convention checks.

### Stripping caplet vols, and when it must fail

**Plain idea.** Brokers quote one flat vol per cap. A 2Y cap and a 1Y cap share their first four caplets, so the 2Y quote really tells you about caplets 5 to 8. Stripping peels off one segment at a time. If a longer cap is quoted so low that even zero vol on its new caplets is too much, the quotes contradict each other, and the right answer is to say so.

**Formal statement.** Caplet vols are constant on each segment between cap maturities. Segment `k` solves `known caplets + new caplets at v_k = cap k at its flat vol`; the left side rises with `v_k`, so the root is unique when it exists. No positive root gives `E_ARBITRAGE` (rulings E-B9, E-B10). Brigo and Mercurio (2006), chapter 6, describe caplet stripping from cap quotes.

**Worked example.** `ratesvol_e-0049`: flat vols 24.0, 23.5, 22.8, 22.2, 21.5% give caplet vols 24.00, 23.14, 21.96, 21.10, 19.71%. The first segment equals the first quote; later ones fall faster than the quotes, as they must. `ratesvol_e-0058` quotes 30%, 30%, 12%: the third cap is cheaper than the caplets the first two already fix, so the result is `E_ARBITRAGE`.

### GARCH(1,1): volatility that remembers

**Plain idea.** Big moves cluster. GARCH(1,1) says tomorrow's variance is a constant plus a share of today's squared return plus a share of today's variance. Because the two shares add to less than one, variance drifts back to a long-run level.

**Formal statement.** `sigma2_{t+1} = omega + alpha r_t^2 + beta sigma2_t`; Gaussian log-likelihood summed from the first return with the `ln(2 pi)` constant; forecast `E[sigma2_{n+h}] = V_L + (alpha + beta)^(h-1) (sigma2_{n+1} - V_L)` with `V_L = omega / (1 - alpha - beta)` (`garch.md`; Bollerslev 1986; Hull, "Estimating Volatilities and Correlations"). The fit is judged on the log-likelihood at the optimum, not on parameters (ruling E-B16).

**Worked example.** `garch_e-0009`: returns 1% and -2%, `omega = 1e-5`, `alpha = 0.1`, `beta = 0.8`. The start is the mean square, 2.5e-4; then `sigma2_2 = 1e-5 + 0.1 x 1e-4 + 0.8 x 2.5e-4 = 2.2e-4`, and the next variance is 2.26e-4. The log-likelihood is 5.410998350356715. Starting from `r_1^2` instead, or dropping `ln(2 pi)`, is a wrong-convention check.

### Variance swaps: a strip of options prices variance

**Plain idea.** The value of expected variance equals the value of a log contract, and a log contract can be built from out-of-the-money puts and calls weighted about `2/K^2`. So today's option prices set the fair variance strike.

**Formal statement.** The discrete strip of Demeterfi, Derman, Kamal and Zou (1999), with reference point the spot and piecewise-linear weights. Fair variance `(2/T)[(r - q)T - (F/S0 - 1)] + Pi/D`, where `Pi` is the weighted strip (`variance-swaps.md`). QuantLib's engine drops `q` from the drift term, so the spec keeps `q` and treats QuantLib's form as a wrong convention (ruling E-B3).

**Worked example.** Three months, a skewed smile, strips with strike steps 20, 10, 5 and 2.5 (`varswap_e-0009` to `-0012`): fair vol 27.77%, 23.75%, 22.64%, 22.35%. The coarse strip overstates variance; the spec prices the strip it is given and never invents strikes. Realised variance (`varswap_e-0030`): five daily returns give `252/5 x 7.029e-4 = 0.0354`, a vol of 18.82%.

### The VIX method

**Plain idea.** The VIX is the variance-swap strip applied to real quotes for two expiries around 30 days, interpolated to exactly 30 days. Two details matter. The at-the-money strike is the one at or below the forward. Quotes with no bid are dropped, and two in a row end the walk outwards.

**Formal statement.** Cboe *Volatility Index Mathematics Methodology* v5.0 (26 Feb 2026), section 3(a): `sigma^2 = (2/T) sum (dK_i/K_i^2) e^{RT} Q(K_i) - (1/T)(F/K0 - 1)^2`, formula (1); time in minutes over 525,600; section 3(b) interpolates to 43,200 minutes (`vix-index.md`, rulings E-B5, E-B15).

**Worked example.** `vix_e-0001`, five strikes, rate 0, 30 days: the smallest call-put gap is at 100, so `F = 100 + (3.0 - 3.1) = 99.9` and `K0 = 95`, not 100. The strip sum is 0.0046952, times `2/T` gives 0.11425; the correction `(1/T)(99.9/95 - 1)^2 = 0.03237`; variance 0.08188.

## Credit and correlation

Specs: `specifications/04-pricing/credit.md`, `credit-options-and-copulas.md` and `specifications/06-risk/correlation.md`. The discount curve for ISDA CDS must be `LOG_LINEAR_DF` (ruling R1-4).

**ISDA CDS.** Plain idea: protection pays `1 - R` on default; the buyer pays a running coupon, and an upfront settles the difference. Formal statement in `credit.md`. Case `credit_d-0004`: buy 10 million of protection to 2031-12-20, coupon 100 bp, recovery 0.4. Par spread 0.011999999988591251, clean upfront 0.009002551543707455, PV 89977.4324589857. QuantLib's `IsdaCdsEngine` agrees within 7e-16 per unit.

### Repairing a correlation matrix

**Plain idea.** Pairwise estimates, taken on different windows or adjusted by hand, often give a matrix with a negative eigenvalue, which implies some portfolio has negative variance. Higham's method finds the closest valid correlation matrix. The answer is unique, so two correct methods must agree.

**Formal statement.** Minimise `||X - M||_F` over symmetric PSD matrices with unit diagonal. Higham (2002) alternates projections onto the two sets with Dykstra's correction; plain alternation without the correction stops at another point (`correlation.md`, ruling E-B18). Goldens are judged at 2e-5 on entries.

**Worked example.** Higham's own example, `[[1,1,0],[1,1,1],[0,1,1]]` (`corr_e-0001`, `-0002`): smallest eigenvalue `1 - sqrt 2 = -0.414`; nearest matrix with off-diagonals 0.760690 and 0.157298. Clipping the eigenvalues and rescaling, a common shortcut, lands more than 2e-5 away and is a wrong-convention check.

### Implied correlation and dispersion

**Plain idea.** If the index's variance and each member's variance are known, one average correlation makes them agree. A dispersion trade buys member variance and sells index variance, so it profits when realised correlation comes in below that implied level.

**Formal statement.** `rho = (sigma_I^2 - sum w_i^2 sigma_i^2) / sum_{i != j} w_i w_j sigma_i sigma_j`, not clipped (ruling E-B20); dispersion legs are variance notionals `N w_i/(2 K_i)` long and `N/(2 K_I)` short (ruling E-B21; `correlation.md`).

**Worked example.** `corr_e-0036`: weights 0.5 and 0.5, vols 20% and 30%, index 22%: `(0.0484 - 0.0325)/0.03 = 0.53`. Dispersion `corr_e-0046`: implied correlation at the strikes 0.519, realised -0.037; P&L `1,590 + 2,708.33 + 1,916.67 = 6,215` on 100,000 of vega.

### CDS options and front-end protection

**Plain idea.** A payer CDS option is the right to buy protection at a fixed spread later. If the name defaults first, a knock-out option dies. A non-knock-out payer is worth more by exactly the protection the forward CDS would have missed.

**Formal statement.** Black on the forward spread, times the risky annuity, with mid-point legs (QuantLib's `MidPointCdsEngine`; accrual on default ACT/360 to the mid date); front-end protection `N (1 - R)(1 - S(expiry)) P(expiry)` for non-knock-out payers only (`credit-options-and-copulas.md`, rulings E-B22, E-B23; O'Kane 2008).

**Worked example.** `creditopt_e-0001`: hazard 2%, recovery 40%, rate 3.5%, expiry in 134 days, 5Y underlying, strike 1.20%, vol 50%. Forward spread 1.18877%, annuity 4.32865, price 59,847.84 on 10m. The front-end protection is 43,333.06, about 70% of the option's own value at this short expiry.

### Copulas and the large pool

**Plain idea.** A copula decides how defaults move together. The Gaussian copula has no tail dependence; the Student t has some, so joint defaults are likelier at the same correlation. In a very large pool of identical names, the defaulted fraction depends only on one common factor, which gives the loss distribution and tranche losses in closed form (Vasicek).

**Formal statement.** Joint default `Phi_2(Phi^-1 p1, Phi^-1 p2; rho)`, or the bivariate t version. In the pool, `P(M) = Phi((Phi^-1 p - sqrt(rho) M)/sqrt(1 - rho))`, loss `(1 - R) P(M)`, and `E[min(P, k)] = p - Phi_2(c, m*; sqrt rho) + k Phi(m*)` (`credit-options-and-copulas.md`, rulings E-B24, E-B25; Li 2000; Demarta and McNeil 2005; Vasicek 1991, 2002).

**Worked example.** `creditopt_e-0147` and `-0151`: default probabilities 2% and 3%, correlation 0.3. Gaussian joint default 0.229%, t with 4 degrees of freedom 0.510%: more than twice as likely. Pool `creditopt_e-0161` to `-0166` (p 5%, rho 0.3, recovery 40%): the 0-3% tranche expects to lose 54.1% of its notional, the 30-100% tranche 0.008%.

## Risk, hedging and use cases

**What it is.** Phase R2 (v0.4.2) added four risk operations on top of the existing pricers: `risk.curve.par`, `risk.curve.key_rate`, `risk.curve.jacobian` and `risk.pnl.explain`. All risk is bump and revalue (ADR-0010), and every number is money per basis point, signed: risk is the change in value for a +1 bp move, so a receiver of fixed, which loses when rates rise, has a negative DV01 (the 2Y receiver below: -4,806.94). Specs: `specifications/06-risk/par-and-key-rate.md` and `pnl-explain.md`. Goldens: `datasets/golden/r2/`, 41 risk cases and 44 P&L explain cases, each re-priced in QuantLib 1.44. All four builds reproduce these numbers: each passed 5,922 of 5,922 golden cases (value-checked and error cases counted together) on the merged `r2` tree (observed, local, 2026-11-08).

### Learning path

| Step | Plain idea | Read | Try |
|---|---|---|---|
| 15 | Solvers differ, so judge the fit, not the parameters | `03-calibration/least-squares.md` | Run `calib.fit` with two methods |
| 16 | Bump the quotes, rebuild, reprice | `06-risk/rates-sensitivities.md` | EX-008 |
| 17 | A hedge is a least-squares problem with a cost | `08-hedging/stage-b-hedges.md` | EX-009 |
| 18 | Put it together | `04-pricing/use-cases.md` | Use cases 1 and 2, below |
| 26 | Put it together | `04-pricing/use-cases.md` | Use case 3 |

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

**Formal statement.** `risk.curve.jacobian` returns `J[i][j] = dz_i / dq_j` by central difference, with `z_i = -ln D(p_i) / t_i` at pillar `i`. Rows are continuously compounded zero rates on ACT/365F curve time; columns are the par quotes as decimal rates on their own day counts (ruling R2-A8). It is lower triangular, because a bootstrapped pillar depends only on quotes up to its own tenor. By the chain rule, `par_buckets[j] ~ sum_i key_rates[i] J[i][j]`, but only for `PILLAR` key rates. The Jacobian describes how the pillars move; a triangular shift also moves the curve between pillars in a way no combination of pillar moves reproduces.

**Worked example.** `risk_r2-0031` is this curve's Jacobian; its first entry is 1.0131. Multiplying the pillar key rates of `risk_r2-0004` by it gives -4,808.1269 in the 2Y bucket, the par bucket of `risk_r2-0001` to every digit shown, and a total of -4,806.9447, its par DV01. The same sum with the triangular key rates of `risk_r2-0002` gives -4,782.13 in the 2Y bucket, 26 off. The oracle checks the pillar identity on every product, within 1e-3 of `par_dv01`.

### P&L explain

**Plain idea.** If the risk numbers are right, risk times the market move should predict the day's P&L. A desk runs this control every day against full revaluation: a large unexplained part points to a broken curve, pricer, risk number or feed.

**Formal statement.** `risk.pnl.explain` builds curves from `quotes_start` and `quotes_end` on one `as_of`, so no time passes and there is no carry or theta (stage F adds those). `full_pnl = value_end - value_start`; `risk_pnl = sum_j par_buckets[j] (q_end[j] - q_start[j]) / 0.0001`; `unexplained = full_pnl - risk_pnl`. To size the threshold, count every first-order term in full, so offsetting buckets cannot hide a move: `gross_risk_pnl = sum_j |par_buckets[j]| |q_end[j] - q_start[j]| / 0.0001`. The day is explained when `|unexplained| <= 0.05 max(|full_pnl|, gross_risk_pnl) + 1e-8 N`, with `N` the notional; the last term is a numerical floor equal to the golden tolerance, not a risk allowance (ruling R2-A3). The threshold grows with the move, so a quiet day cannot pass vacuously. The 5% is a project choice, fixed in the spec and not tuned per product (R2-A4). It is not the Basel FRTB P&L attribution test, which compares risk-theoretical and hypothetical P&L over 250 days with Spearman correlation and Kolmogorov-Smirnov statistics. The real-move run reports those two statistics alongside, without judging them.

**Worked example.** `pnl_r2-0001`, every quote up 1 bp: full P&L -4,806.23, risk P&L -4,806.94, gross risk P&L 4,809.34, unexplained 0.71 against a threshold of 240.72, so explained. `pnl_r2-0011` shows the control failing: paying fixed on a 10Y swap of 10 million with every quote up 150 bp. Full P&L 1,171,652, risk P&L 1,263,161, unexplained -91,509 against a threshold of 63,158. On a move that size, convexity, which first-order risk leaves out, is too large. Of the 42 goldens that return a result (the other 2 are errors), 4 are unexplained, all large shocks on 10Y and longer products.

**On real moves.** `tools/workflows/pnl_explain.py` runs the control over consecutive days of the US Treasury par curve, a proxy for SOFR swap rates. R2 acceptance is at least 95% of days explained for every product. On the 2025 Treasury moves, every product in the sample book was explained on 100% of days, against the 95% target, in both Java and Python (coordinator run, 2026-11-07). For the 2Y OIS, Spearman was 0.997 and KS 0.044; for the 10Y OIS, Spearman 0.9998 and KS 0.028. Those two statistics are reported, not judged. A clean year says the risk and the revaluation agree on 2025's moves; it says nothing about a year with larger ones.

**Calibration stability and rich/cheap.** R2 also specifies a calibration stability report (`specifications/03-calibration/stability.md`) and workflow (b), a Treasury and gilt rich/cheap screen (`specifications/04-pricing/workflow-b-rich-cheap.md`). Both run existing operations in batch mode. The rich/cheap fit weights each bond by `1/D_mod^2`, with `D_mod` its modified duration, so price errors become roughly yield errors, as Gurkaynak, Sack and Wright (2007) and the Bank of England's spline method (Anderson and Sleath 2001) do (ruling R2-A5). Treasury on-the-run and first off-the-run issues are left out of the fit, because their liquidity premium bends it, but their residuals are still reported (R2-A6). Calibration stability, first run: 28 of 28 rows passed (seven calibrations in four languages), and the languages agreed within 2e-8. C3 was rerun under ruling R2-A9, which judges it on the operation's own `residuals`, and passes in all four languages. Workflow (b) is blocked on price data (ruling R2-A11): TreasuryDirect's robots.txt and personal-use terms rule out automated fetching, and the DMO serves its prices behind an anti-bot page. Prices can be supplied by hand with `--data DIR`; without them the job writes a BLOCKED report. At stage E the recorder's Fiscal Data auction feed (`fiscaldata-treasury-auctions`, open licence) gives a note or bond's `price_per100` only on its own auction day, and from 2026-08-01 to 2026-11-08 at most two notes or bonds were auctioned on any day (23 auctions on 21 days). A fit needs the whole coupon universe priced on one date, so the feed does not qualify as a price source; it stays in use for the on-the-run list. The manual `--data` path stays.

### Use cases

**Use case 1: FX hedge (stage B).** Plain idea: a book of forwards behaves like a position in spot, so spot can hedge it. Formal statement: `hedge_spot_base = -fx_delta`, and `hedge_cost = |hedge_spot_base| * half_spread`. `examples/usecase_fx_hedge.json` holds two synthetic GBPUSD forwards, buying 5,000,000 and selling 3,000,000, at spot 1.28 with a half-spread of 0.00005. `usecase.fx_hedge` gives a PV of 59,903.64653464559 and an FX delta of 2,054,546.4912482663. So the hedge sells 2,054,546.49 of base in spot, at a cost of 102.72732456241332. Delta is not 2,000,000 because each forward's delta is discounted, and the two dates differ. All four builds printed these values. The golden case has a hand source only.

**Use case 2: rates hedge (stage B).** Plain idea: match a trade's risk bucket by bucket, using swaps that sit at the quoted tenors. Formal statement: `hedge_units` solves `min |C x + key_rate|^2`, in `use-cases.md`. `examples/usecase_rates_hedge.json` pays fixed 3.4% on a 6Y SONIA swap, notional 10,000,000, off the quoted tenors, and hedges it with 5Y and 7Y par swaps of 1,000,000 each. From the Rust build: PV 4,688.4635, DV01 5,359.8843, with 2,210.20 in the 5Y bucket and 3,149.66 in the 7Y bucket. `hedge_units` are -4.8713 and -5.1239, so the hedge receives fixed on both, and the largest residual bucket is 0.015. `hedge_cost` at 0.25 bp is 1,339.9648. The four builds agree to about 11 digits, inside the use case's limit. The golden case comes from a replay of parts checked against QuantLib; the sums themselves have no outside source.

**Use case 3: vol surface.** Plain idea: from call and put bid and ask quotes, infer each expiry's forward by put-call parity, fit SVI per expiry, check the surface, then price and risk a target option. Formal statement in `use-cases.md`. Case `usecases_c-0001`: three expiries of 11 synthetic quotes each. Forwards 5012.481305847661, 5024.993768294455 and 5050.250835420839. SVI RMSE below 1e-16 on each, because the quotes were made from an SVI. `arbitrage_free: true`. Buying 3 calls at 5100 expiring 2027-05-07 gets vol 0.17261062692922427, PV 621.6085879585307, delta 1.4063042744345948 and vega 4176.011752554645. A near-zero RMSE shows the fit works; on real quotes it would not be zero.

Nothing in these examples is traded. They are calculations on synthetic data.

## Validation and evidence

Stages A to C test correctness with analytic, hand and outside-library answers. Stages B and C add calibration on known truth. Later stages add backtests and new-model tests. `specifications/stage-b-rulings.md` says which stage B suites have an outside oracle. Evidence is always labelled analytic, simulated, proxy or observed, and validation reports are self-assessment until the human review at the end of the project.

R1 adds the records that say how far each result goes. The [model inventory](docs/model-inventory.md) gives every model its spec, oracle, outside-checked share and limits. The [edge-case register](specifications/edge-case-register.md) lists boundary cases and whether a golden pins each one; a row marked out of scope names the stage that would bring it in. `conformance/tolerances/money.md` restates every tolerance as money on 10 million notional, so a reader can judge whether a pass is tight enough to matter. The R1 daily workflows are the first runs on observed public data, and their USD curve is labelled a proxy.

### What a tolerance means in money

A tolerance such as 1e-10 says little to a desk. `conformance/tolerances/money.md` restates every class, and every per-case limit, as an error on a 10m notional: basis points of DV01 on a 10Y swap, 32nds of a bond price, and currency units. The widest class, `numerical_scheme`, allows about 1e-4 bp of a 10Y swap's DV01, under one currency unit on 10m. Present-value limits are 1e-9 of notional, which is 0.01 on 10m.

### What is not checked by an outside library

QuantLib's Python wheel has no GARCH, no VIX method, no bivariate t and no large-pool loss model (the Gaussian copula and pool formulas can be re-evaluated with its bivariate normal, but that checks the spec's algebra with itself, so it does not count), so those goldens rest on hand cases, 50-digit or exact-rational replicas and separate float replays. For slices E4, E6, E7 and E8 the outside share is 277 of 449 (61.7%), counting a case only if every output is a QuantLib value; stage-wide it is 557 of 895 (62.2%) (`specifications/05-volatility/stage-e-targets-b.md`).

### Known limits, by topic

Every topic is Implemented, not Validated, and all inputs are synthetic unless a section says otherwise. The limits as each stage recorded them:

- **Foundations (stage A).** Many golden cases have hand or replay sources, which can share a misreading with the spec. Constructed inputs test the method only. The recorder is built but not scheduled. See the [Roadmap](ROADMAP.md#stage-status).

- **Curves (stage B).** Stage B is Implemented, not Validated. Almost all curve inputs are synthetic, so exact repricing says nothing about a market. `usecases` and `rulings_b` have no outside oracle, and `risk` is hand and self-consistency only. Risk is bump and rebuild, with no AD. See `specifications/stage-b-rulings.md` and the [Roadmap](ROADMAP.md#stage-status).

- **Options and vol (stage C).** Stage C is Implemented, not Validated. All inputs are synthetic: the stage C data survey found no free history of option quotes, vol surfaces, borrow cost or dividends. European options only (C1). Arbitrage checks run on the given points only. `vol.sabr.arbfree` at `nu > 0` lacks a tight outside source. See `specifications/stage-c-rulings.md`.

- **Curves and fixed income (stage D).** Stage D is Implemented, not Validated. All inputs are synthetic. The ESTR payment lag of 2 is a library choice (Strata), not a market standard; TP ICAP terms use 1 (ruling R1-2). From R1, bond-future conversion factors take an optional `contract` input with CME rounding; `null` keeps the stage D `TEN_YEAR` behaviour (ruling R1-3). The stage D data survey (2026-11-07) found free overnight fixings, fitted Bank of England curves, US Treasury par and real curves and UK CPI, but no free swap quotes, bond-level prices, special repo, cross-currency basis, CDS spreads, borrow, commodity curves or MBS factors; those studies stay method tests. Several suites have no outside oracle (CSA discounting, asset swap, FRN, repo, NDF, equity, inflation, commodities, MBS); `specifications/stage-d-rulings.md` lists them. R1 counts outside-oracle cases under a stricter rule: QuantLib is built from its own convention objects through one reviewed table, `oracle/CONVENTION_MAP.md`. On that rule, 419 of the 654 stage D cases (64.1%; most counted cases are fixed-rate bonds) count, suite by suite in `oracle/REPORT.md`.

## Stage F: curves, portfolio risk and the book

Stage F (v0.6.0) is at Implemented, not Validated. On the merged part 2 tree (`stage-f-part2` at `db99d87`, 2026-11-10, observed on one Windows machine through the neutral runner), each of the four builds passed 12,462 of 12,462 golden cases (value-checked, error and invariance cases counted together): Java (JDK 25.0.5), Python (CPython 3.15.2), Rust (1.99.1) and C++ (GCC 15.2.0 under WSL, built with `-DQF_WERROR=ON`). Specs and rulings F-1 to F-44 are in `specifications/`. Every number quoted here is the expected output of the named golden case, computed by the oracle at 40 or more digits.

Tutorials for this section: [5, risk](docs/getting-started/tutorial-5-risk.md) (VaR, ES, backtests, FRTB delta), [8, multi-curve building](docs/getting-started/tutorial-8-multicurve.md) (joint solve and Jacobian), [14, the trading book](docs/getting-started/tutorial-14-book.md) and [15, advanced risk](docs/getting-started/tutorial-15-advanced-risk.md).

### Five more ways to draw a curve
**Plain idea.** Between quoted dates a curve must be filled in, and the method changes the forward rates a trader sees. Stage F adds monotone convex (Hagan and West), monotonic log cubic, a tension spline and a hybrid that is stepwise at the front and smooth behind. Spec: `02-curves/curve-framework.md`, "Stage F: pluggable interpolation". **Watch for:** monotone convex is piecewise in its data, so its derivative jumps where a section changes rule. Ruling F-28 shows how a too-large bump straddled such a kink and looked like a 2e-3 error.

### Solving several curves at once
**Plain idea.** The OIS curve, the term curve that discounts on it and the cross-currency curve are one system of equations. The same solve gives every curve point's sensitivity to every quote, by the implicit function theorem: `J = -(dR/dx)^{-1} dR/dq`. Spec: `02-curves/joint-solve-and-funding.md`. **Worked number:** in `joint_f-0001` the year-end turn on SOFR is solved from the 2M quote as a discount factor jump of 0.99999890 across 2026-12-31.

### Risk of a whole book in one pass
**Plain idea.** Bumping 12 quotes on 500 swaps means 12,000 revaluations. Algorithmic differentiation (AAD) gets all of them from one forward and one backward pass, exactly to rounding. Rust carries the reference tape, and the other three languages use the chain rule (ruling F-29). Spec: `06-risk/book-sensitivities.md`. **Worked number:** in `risk_f3-0001`, the 500-swap book's value moves by 2.0205 per unit of the 10Y quote, so 1 bp is 0.000202 per unit notional.

### VaR, expected shortfall and backtests
**Plain idea.** Take 250 days of P&L, sort the losses, and read off the third-largest: that is the 99% VaR. ES is the mean of the losses from there up. Then ask whether real losses broke VaR as often as they should. Spec: `06-risk/var-es-and-backtests.md`. **Worked numbers:**
- `risk_f4-0001` (250 days, 99%): VaR 4,597,347.01 and ES 5,360,005.88, over three tail scenarios (ruling F-31).
- A normal P&L with standard deviation 1 million (`risk_f4-0026`) gives VaR 2,326,347.87, which is 2.326 sigma.
- In the Basel traffic light, 4 exceptions in 250 days is green, 5 is yellow (plus factor 0.40), and 10 is red (`risk_f4-0086`, `0087`, `0092`).

### FRTB standardised capital for rates
**Plain idea.** Regulators fix the recipe: weight each sensitivity, add them within a currency with set correlations, then across currencies, under three correlation scenarios, and keep the worst. Spec: `06-risk/frtb-sa-girr.md`, from the Basel Framework MAR21. **Worked number:** a 2Y long and a 10Y short on one curve (`frtb_f-0002`) need 8,812.37 of capital, with the `low` scenario binding. **Checked:** the `low` formula, first transcribed from an image, was confirmed by the owner against MAR21.6 on 2026-11-10 (F-33): `rho_low = max(2 rho - 100%, 75% rho)`, and the same for `gamma`.

### The book, and where returns came from
**Plain idea.** Positions carry an average cost, and selling realises the difference. Expiry, default and rolls are trades at their settlement, recovery or roll prices. At the end of the day each position gets a mark from the best available source, and an independent price flags marks that look wrong. Spec: `07-portfolio/book-lifecycle.md`. **Worked number:** buy 100 at 99.50 and 50 at 100.25 (average 99.75), sell 120 at 100.50: realised P&L 90.00, with 30 left at 99.75 (`book_f-0001`).

Use case 4 regresses a portfolio's returns on factor returns, and each factor's share of the mean return is its beta times the factor mean (`04-pricing/use-cases.md`). In `uc4_f-0002`, the mean monthly return of 0.279% splits into alpha 0.073% and three factor contributions (0.186%, -0.008%, 0.029%) that add up exactly.

### What stage F's evidence does and does not show
- **Outside oracle, 417 value-checked cases: 52.8% from outside libraries alone, 84.2% with an independent re-derivation of the spec (78.7% without 23 spec-only book cases); old all-case share 41.9%; the 60% floor is met.** Not counted: `risk_f4-0087`..`0095` (the spec keeps the 1996 plus factors by stated vintage, ruling R6-28.1, which rests on the lane's own reading) and `garch_f-0009`, `joint_f-0004` (unverified at 1e-8). v0.6.0 published 225 of 438 (51.4%); D6 counts only library objects and numpy or scipy primitives, not reimplementations (`oracle/OUTSIDE_SHARES.md`). The checks use QuantLib 1.44, SciPy, NumPy and `arch`. Every case without a free outside source is listed with the reason in `oracle/OUTSIDE_GAPS_F.md`. 79 of the cases without one are error cases, which no library can check; the CDS index option (R7) is the largest value-case gap, because its reference paper is not freely available.
- **All inputs are synthetic.** The 500-swap book, the VaR series and the factor returns are drawn from `core.rng` with fixed seeds.
- [Determinism](docs/determinism.md): what is bit-exact across languages and platforms, and what is within tolerance.

## Stage G: rates models and xVA

Stage G (released as v0.7.0 on 2026-11-11) is at Implemented, not Validated. On the integration tree `stage-g-int` (2026-11-11, observed on one Windows machine through the neutral runner) each of the four builds passed 14,492 of 14,492 golden cases, of which 589 are stage G value and error cases and 1,026 are E1 cases for the first 20 stage G operations.

Tutorials for this section: [6, interest rate models](docs/getting-started/tutorial-6-hull-white.md), [7, counterparty risk](docs/getting-started/tutorial-7-counterparty.md), [12, exotic options](docs/getting-started/tutorial-12-exotics.md) (discrete barriers), [15, advanced risk](docs/getting-started/tutorial-15-advanced-risk.md) (AAD ladder, MC Greeks, model reserve) and [16, the LIBOR market model](docs/getting-started/tutorial-16-lmm.md).

### Short-rate models

**Plain idea.** Instead of a fixed curve, let the overnight rate itself move at random, pulled back towards a long-run level. A bond price is then the expected discount over every rate path, and options on bonds and swaps get a value.

**Formal statement.** Under Vasicek, `dr = a (theta - r) dt + sigma dW`, and the zero-coupon bond is `P(t, T) = A(tau) exp(-B(tau) r)` with `B = (1 - exp(-a tau)) / a` and `ln A = (theta - sigma^2 / (2 a^2)) (B - tau) - sigma^2 B^2 / (4 a)` (`04-pricing/short-rate-models.md`). CIR and Hull-White have the same affine form; Hull-White fits today's curve exactly. Below `a tau = 1e-2` the spec uses a series to avoid cancellation (ruling G-2).

**Worked example.** `shortrate_g-0001`: `a = 0.15`, `theta = 0.045`, `sigma = 0.012`, `r = 0.035`, one year. `B = 0.928613`, so `P = 0.964937076`, a zero rate of 3.5692%. The golden is checked by mpmath at 50 digits and by QuantLib 1.44's `Vasicek`; the formula above, in double precision, gives the same digits.

### Swaptions, Bermudans and the LMM

**Plain idea.** On a one-factor model a European swaption splits into a portfolio of bond options, one per coupon, all struck at the same short rate (Jamshidian). A Bermudan can be exercised on several dates, so its value is rolled back on a lattice. The LMM models the quoted forward rates directly.

**Formal statement.** Find `r*` with `sum c_i P(T0, T_i; r*) = 1`; the payer swaption is then `sum c_i ZBP(T0, T_i, K_i)` with `K_i = P(T0, T_i; r*)` (`short-rate-models.md`, rulings G-12, G-13). Bermudans and callable bonds share one lattice scheme (G-18). LMM swaption vols use Rebonato's frozen-weights formula (`04-pricing/lmm.md`).

**Worked example.** `swaption_g-0001`: Hull-White with `a = 0.05`, `sigma = 0.01`; a 1y into 5y payer on 1 million at 2.9462%, 100 bp below the forward swap rate of 3.9462%. Price 45,445.78, annuity 4,289,707 (QuantLib's `JamshidianSwaptionEngine` is the outside check). Intrinsic value is `annuity x 1%` = 42,897, so 2,549 is time value.

### Exposure and xVA

**Plain idea.** If a counterparty defaults while it owes you money, you lose what it owed less what is recovered. CVA prices that loss today: expected positive exposure at each date, times the chance of default in that period, times the loss given default, discounted. DVA is the same loss seen from the other side; FVA prices funding the uncollateralised exposure.

**Formal statement.** In outline, `CVA = (1 - R) sum_i DF(t_i) EE(t_i) PD(t_{i-1}, t_i)` with a flat hazard rate; DVA uses `ENE` and the own hazard rate; FVA is FCA less FBA on the borrowing and lending spreads, with the DVA overlap optional. The exact discretisation is in `06-risk/xva-framework.md` (rulings G-40 to G-44). Exposure comes from `xva-exposure.md`: in closed form for a swap under Hull-White, or with collateral, threshold and a margin period of risk. For a portfolio of swaps, `xva-exposure-portfolio.md` integrates the netting-set value exactly over the one Gaussian factor, splitting the integral at the zeros of the value; PFE is the level at which the probability of a lower exposure reaches 95% or 99%.

**Worked example.** `xvaadj_g-0001`: four half-yearly dates, `EE` 120, 150, 130, 80, counterparty hazard 2% and recovery 40%. CVA is 2.7099, DVA 0.8998 and FVA 0.6129 (FCA 1.8156 less FBA 1.2027); checked by mpmath at 50 digits.

### What stage G's evidence does and does not show
- **Outside oracle: 332 of 463 value-checked cases (71.7%) under the tight rule D6, 56.4% under the old all-case count; v0.7.0 published 57.4%.** The figure rests on a suite-level register until a per-case one confirms it. Wave 4c compared portfolio exposure with ORE 1.8.17; 80 of 102 `expsim_g` cases count under ruling G-42. The re-test G-42b needs WSL and is carried to stage I (G-52).
- **The stage demo ran.** ORE's NPV of the demo swap equals the closed form to 1e-6, and its EE is within 1 SE at 8,000 paths (`oracle/ore/ORE_DEMO.json`). ORE is a Monte Carlo check: it confirms the profiles to a few standard errors, not to the goldens' digits.
- **18 PFE goldens were wrong and are fixed** (G-Q4): a grid scan missed level crossings near a flat peak. The four builds found it, because they solve for the crossings exactly.
- **G-10 is inconclusive**; the powered test G-10b passed (`specifications/stage-g-rulings.md`). R9 acceptance has modest power (ruling G-34).
- **All inputs are synthetic.** No market swaption, cap or CDS quotes are used.

## Stage I: hedging

Stage I was released as v0.8.0 on 2026-11-12. Everything below is specified in `specifications/08-hedging/` (rulings I-1 to I-55) and pinned by 443 golden cases in 21 suites in `datasets/golden/stage_i/`. On the integration tree, at CLI contract 1.11.0, each of the four builds passed 14,935 of 14,935 golden cases (7,413 value-checked, 5,008 error, 1,257 invariance and 1,257 `any` base cases), all stages included (2026-11-11, observed on one Windows machine through the neutral runner). Every input is synthetic.

Tutorials 17 to 21 work through this section with real outputs in all four languages: [17, delta hedges](docs/getting-started/tutorial-17-delta-hedge.md), [18, the QP solver](docs/getting-started/tutorial-18-minvar-qp.md), [19, credit and correlation](docs/getting-started/tutorial-19-credit-correlation.md), [20, equity and rates](docs/getting-started/tutorial-20-cross-asset.md) and [21, costs](docs/getting-started/tutorial-21-hedge-costs.md).

### A hedge is a small least-squares problem

**Plain idea.** A book has risks: delta, vega, key-rate DV01s, a CS01. Each hedge instrument has its own risks per unit. Choose how many units of each to hold so that the book's risks, plus the hedges' risks, come as close to zero as you can, perhaps with limits on positions, costs for trading or a whole number of contracts. With as many independent instruments as risks the answer is exact; with fewer it is the best fit, and what is left is the residual risk.

**Formal statement.** With the instruments' risks as the columns of `A` (`m` risks by `n` instruments) and the book's risks `b`, `hedge.qp.solve` minimises `f(x) = sum_i w_i (A x + b)_i^2 + ridge sum_j x_j^2` subject to optional equalities `E x = e` and bounds `lower <= x <= upper` (`hedge-solvers.md`). The checks run in a fixed order, and a problem without a unique minimiser is `E_SINGULAR` unless `singular: MIN_NORM` asks for the least-norm minimiser (rulings I-3, I-5). Integer lots minimise the same `f` over whole numbers by exact search, with a fixed tie rule (I-7); costs, impact, liquidity bounds and margin extend the objective and the constraints (`hedge-costs-and-frontier.md`, I-24 to I-28). Greek, beta, credit, correlation and cross-asset hedges build `A` and `b` from their own pricing and then solve this problem.

**Worked example 1: equity beta.** `hedgebeta_i-0001` is Hull's example (*Options, Futures, and Other Derivatives*, ch. 3): a portfolio of 5,050,000 with beta 1.5, hedged to beta 0 with index futures at 1,010 and a multiplier of 250. `contracts = (beta* - beta) V / (F m) = (0 - 1.5) x 5,050,000 / 252,500 = -30`, thirty contracts short, and `beta_after` is 0 (computed: mpmath at 50 digits; arithmetic only, so no outside library counts for this suite).

**Worked example 2: delta, gamma and vega together.** `hedgegreeks_i-0003` (the input of `examples/hedge_greeks_i.json`): spot 100, rate 3%, dividend yield 1%, volatility 25%, a book short 1,000 six-month 100 calls and long 500 one-year 90 puts. Its Greeks are delta -686.21, gamma -15.760 and vega -11,508.4 (per unit volatility). Three targets need three instruments: hold 504.83 of the underlying, 502.76 three-month 105 calls and 38.27 two-year 95 puts, and all three Greeks are zero after the hedge (computed at 50 digits; outside check QuantLib 1.44 `AnalyticEuropeanEngine` Greeks with a numpy solve). The underlying alone could fix the delta, but only an option can fix gamma, and two options with different expiries are needed to fix gamma and vega at once.

**Worked example 3: rounding is not enough.** `hedgeint_i-0010` (`examples/hedge_integer_i.json`): two strongly correlated instruments, `A = [[1, 0.95], [0.95, 1]]`, `b = (-1.265, -1.27)`, lots of 1. The continuous answer is `(0.6, 0.7)`, objective 0. Rounding it gives `(1, 1)` and an objective of 0.9317; the best whole-number answer is `(0, 1)` with 0.172125, found by searching 756 points (computed: exact rational enumeration, an ellipsoid bound and a wide-box float search agree; no free integer least-squares library exists, so no outside check).

### Trading costs make zero a real answer

**Plain idea.** If every trade pays a spread, a small position in an instrument may cost more than the risk it removes. The best hedge then leaves that instrument out entirely, not at a tiny holding but at exactly zero. Where an instrument goes from "leave out" to "hold" is its switch point.

**Formal statement.** With half-spreads `h_j` and cost weight `c`, the objective adds `c sum_j h_j |x_j|` to `f(x)` (`hedge-costs-and-frontier.md`). The absolute value has a kink at zero, so the solve fixes a sign for each instrument (positive, negative or held at zero), solves the smooth problem on that sign state exactly, and keeps `x_j = 0` while the risk gradient there satisfies `|g_j| <= c h_j`. Java and C++ first enumerated every sign state, which grows as `3^n` and was capped at 20 instruments; ruling I-48 allows no limit below the 200 instruments of I-4, so both now use a sign-state active-set method that changes a sign only where its subgradient test fails, and stops when the KKT conditions of the whole problem hold. At a switch point both neighbouring states give the same `x`, so the answer must be exact there too (I-54).

**Worked example.** `hedgecost_i-0023`: two independent risks `b = (-1, -2)`, one instrument per risk, half-spreads 2 and 0.5, cost weight 1. For instrument 1 the risk gradient at zero is `2 (0 - 1) = -2`, exactly its cost of 2, so it sits on its switch point and is held at 0. Instrument 2 solves `2 (x_2 - 2) + 0.5 = 0`, so `x_2 = 1.75`. Risk is `1 + 0.0625 = 1.0625`, cost `0.5 x 1.75 = 0.875`, objective 1.9375 (computed: mpmath at 50 digits over the sign states; outside check scipy 1.18 SLSQP on the split problem).

### Judging a hedge after the fact

**Plain idea.** A hedge chosen today drifts as prices move, so a delta hedge is rebalanced on dates. Replaying a path shows what the hedged position actually earned, and comparing the changes of the book with the changes of the hedge says how well it worked.

**Formal statement.** `hedge.backtest.delta` replays a given path in a fixed order at each date: interest on cash, dividends on the shares held, the mark, then the rebalance (ruling I-29); optional spread and impact costs are paid on every trade, the first purchase included (I-39, I-40). `hedge.effectiveness` reports the dollar offset, the regression slope and `R^2` of hedge changes on book changes, and the variance reduction; a hedge leg with zero variance is `E_DOMAIN` (I-31, I-43).

**Worked example.** `hedgeeff_i-0001`: a close hedge gives a dollar offset of 0.9712, a slope of -0.9924, `R^2` 0.9964 and a variance reduction of 0.9964 (computed at 50 digits; outside check numpy 2.5 `polyfit`, `corrcoef` and `var`). A perfect offset would give 1, -1, 1 and 1.

### What stage I's evidence does and does not show
- **Outside oracle: 102 of 153 value-checked cases (66.7%) under the tight rule D6, from a per-case register, without the wave 5 cases (83.7% with them); 36.7% under the old all-case count; v0.8.0 published 62.8%.** Every stage I counted case is a numpy or scipy primitive check; none uses a library pricing object (`oracle/OUTSIDE_SHARES.md`). Wave 5 (ruling I-55) added 165 value cases from seeded draws, checked against QuantLib, numpy and scipy; draws were rejected only by rules fixed before any outside check (3 in all), never for disagreeing. Error cases are in the denominator and never count, and integer lots, beta futures, residual reports and slippage still have no outside library that solves a different way (`program/STAGE_I_HANDOVER.md`, "WAVE 5 READY").
- **Q6-01, the synthetic method test, failed** (78.4% inside the spread against 80%); kept as published, redesign in J-11 (tutorial 22).
- **Q6 (calibration on real noisy quotes) is blocked** by the data terms of the candidate sources; only its preregistration exists (`research/preregs/Q6-01-churn-bound.md`).
- **The hedges are calculations.** Nothing is traded, and costs, impact and margin are inputs, not estimates from a market.
- **Tested on one machine.** The 14,935-case runs were on one Windows machine; CI on the stage I pull request is the cross-platform check.

## Appendix: stage history

The order things were built, with each stage's own summary. The topics above reuse these stages' worked examples. The [tutorial index](docs/getting-started/README.md) has a Stage column: stage B is tutorial 1; C is 3 and 5; D is 2, 4, 8, 9, 10 and 11; E is 3, 9, 12 and 13; F is 5, 8, 14 and 15; G is 5, 6, 7, 12, 15 and 16; I is 17 to 21.

### Stage A: Foundation

**What was built.** Domain 01 in all four languages: day counts, calendars, compounding, data checks, snapshot hash, as-of store, random numbers, Sobol, root finders, integration, interpolation, statistics, PDE, Monte Carlo and COS. Also the oracle, the CLI, the neutral runner, fuzz and mutation harnesses, the recorder and the forward log.

**Where it is.** Specs in `specifications/01-core/`. Examples: `examples/daycount.json`, `discount_factor.json`, `root_brent.json`, `error_date_order.json`, `batch.jsonl`. Exercises EX-001 to EX-003 in `program/exercises/`. Recipes in the [Cookbook](COOKBOOK.md#stage-a-recipes).

### Stage B: FX and rates slices

**What was built.** SONIA and minimal SOFR OIS curves, projection curves, FRAs, swaps, FX forwards and swaps, quote-driven basis, calibration, DV01 and key-rate risk, hedges with a spread-based cost, and use cases 1 and 2.

**Where it is.** Specs in `specifications/`, under the folders named below. Examples: `examples/ois_bootstrap.json`, `ois_bootstrap_sofr.json`, `projection_bootstrap.json`, `fx_forward_outright.json`, `fx_curve_implied.json`, `usecase_fx_hedge.json`, `usecase_rates_hedge.json`. Exercises EX-005, EX-006, EX-008 and EX-009. Recipes in the [Cookbook](COOKBOOK.md#stage-b-recipes).

### Stage C: Equity vol slice

**What was built.** Equity forwards with a borrow curve and discrete dividends; Black-Scholes, Black-76 and Bachelier prices and implied vols; analytic and bumped Greeks; delta conventions and risk-reversal and butterfly quotes; SVI and SSVI with no-arbitrage checks; a vol surface with calendar and butterfly checks; Hagan SABR with a density check; arbitrage-free SABR; and use case 3.

**Where it is.** Specs in `specifications/05-volatility/`, `02-curves/equity-forward.md` and `06-risk/vol-greeks.md`. Rulings C1 to C17 in `specifications/stage-c-rulings.md`, targets in `05-volatility/stage-c-targets.md`. Goldens in `datasets/golden/stage_c/`: 446 cases in 11 suites. Recipes in the [Cookbook](COOKBOOK.md#stage-c-recipes).

### Stage D: Curves and fixed income

**Status: built, target v0.4.** Implemented, not Validated. At merge `95cbf11` on 2026-11-07, each of the four implementations passed 5,514 of 5,514 golden cases (value-checked and error cases counted together) locally, 331 of them in stage D's 20 suites (`conformance/README.md`). `specifications/stage-d-handover.md` lists every stage D spec; rulings D1 to D64 are in `specifications/stage-d-rulings.md`.

### R2: Risk

Phase R2 (target v0.4.2) added `risk.curve.par`, `risk.curve.key_rate`, `risk.curve.jacobian` and `risk.pnl.explain`. Its topics are under [Risk, hedging and use cases](#risk-hedging-and-use-cases).

### Stage E: full volatility, exotics, rates vol, correlation and credit (v0.5.0)

**What was built.** Eight slices: arbitrage-free SVI surfaces with local and forward vol (E1), the Heston family and SLV (E2), FX smile conventions (E3), rates and inflation vol (E4), exotics and American options (E5), correlation (E6), GARCH, variance swaps and a VIX-style index (E7), and CDS options, copulas and the large-pool model (E8). Two spec sessions wrote the specs and goldens in parallel; rulings are E-A1 to E-A40 (`specifications/stage-e-rulings.md`) and E-B1 to E-B40 (`specifications/stage-e-rulings-b.md`), and each language was built from the specs alone.

**Status: implemented in all four languages.** At the stage E merge, `597abf2` (2026-11-08), the golden set holds 6,817 cases (value-checked and error cases counted together) in 91 suite files (counted from `datasets/golden/`). C++, Java and Rust each reported 6,817 of 6,817 passing in their final stage E commits (`5af077d`, `a9cd195`, `141245d`; *reported*). Python passed 6,817 of 6,817 through the neutral runner on the merged tree, built from `597abf2` (*observed*, local, Windows, 2026-11-08). Outside oracle under plan rule 11.2.5, counting a case only if every output is a QuantLib 1.44 value (rulings E-A17, E-B28): 557 of the 895 stage E cases, 62.2% (spec A 280 of 446 in `oracle/outside_register_e_a.json`, spec B 277 of 449 in `oracle/outside_register_e_b.json`; *outside-checked*). All inputs are synthetic, and no model is Validated (`docs/model-inventory.md`).
