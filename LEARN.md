# Learn QuantForge

A path through the project, by topic. Each topic goes from the plain idea, to the formal statement in a spec, to a worked example. The order in which the stages were built is in the [appendix](#appendix-stage-history).

## Start here

QuantForge has four equal implementations of the same maths, in Java, C++, Python and Rust. None is the reference. Expected answers come from `oracle/`, because four programs agreeing proves only that they agree.

Two ways in:

- **New to quantitative finance, or to this project.** Work through the [tutorials](docs/getting-started/README.md), starting with [Tutorial 1: price your first swap](docs/getting-started/tutorial-1-swap.md): quotes to curve to PV to DV01 in about 10 minutes, in Python, then the same in Rust, Java and C++. Tutorials 2 to 16 go on, 10 to 15 minutes each, to bonds and repo, options and volatility, credit, risk, interest rate models, counterparty risk, multi-curve building, cross-currency and FX, inflation and commodities, mortgage-backed securities, exotic options, time series and vol indices, the trading book, advanced risk and the LIBOR market model, with every number checked in all four languages. Tutorials 17 to 21 cover stage I, hedging: Greek and dynamic delta hedges, minimum-variance and constrained hedges, credit and correlation hedges, a cross-asset hedge with instrument selection, and what a hedge costs. Tutorials 23 to 35 cover stage J research tools: an honest backtest with purged cross-validation, whether a Sharpe ratio is real, portfolios, costs, trials and power, leakage, shrinkage, stress and drift, financing term structures and liquidity curves. Tutorials 36 to 50 cover stage H execution and microstructure (v0.10.0): schedules, Almgren-Chriss, shortfall, impact, market-making quotes, the book rebuild, the simulated lit engine, dark pool and router, paper trading, estimators, venue analytics, adaptive algorithms, the low-latency book, trading conventions and three more simulated venues. Then read the topics below in order.
- **Test yourself.** The [question bank](docs/question-bank/README.md) has 450 questions with worked answers, at foundation, practitioner and advanced level, across all the topics below; set 14 (32 questions) covers stage K work that is in progress and not released.
- **Practitioner.** Jump to a topic. Each worked example names its golden case, so you can rerun it as `COOKBOOK.md` shows and check the number yourself.

**What the tests check.** 7,990 value-checked golden cases, where each build must return the oracle's numbers within a stated tolerance; 5,707 error cases, which check only that a bad input is refused with the right code; and 2,560 invariance cases (1,280 pairs), which check that two related inputs get the same answer. Counts are generated in [`docs/case-figures.md`](docs/case-figures.md). Outside-library shares per stage, under the tight rule D6, are in [`oracle/OUTSIDE_SHARES.md`](oracle/OUTSIDE_SHARES.md).

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
| [Stage I: hedging](#stage-i-hedging) | Least-squares and QP hedges, costs and switch points, backtests and effectiveness |
| [Stage J: backtest overfitting and research statistics](#stage-j-backtest-overfitting-and-research-statistics) | Lag and look-ahead, purged CV, PSR, DSR, PBO, power, regimes |
| [Stage H: execution and microstructure (v0.10.0)](#stage-h-execution-and-microstructure-v0100) | Schedules, Almgren-Chriss, shortfall, three impact models, order books and quotes, simulated venues, equity, FX and rates conventions, paper trading, and how the stage was checked |
| [Stage K: risk platform and capital (in progress)](#stage-k-risk-platform-and-capital-in-progress) | Bitemporal store, incremental curves, recalibration triggers, intraday risk bounds, the K-8 ladder fix, SA-CCR, backtesting zones, the daily paper ledger, blind re-derivation; merged to `main` (2026-11-19), not released |

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

Stages A to C test correctness with analytic, hand and outside-library answers. Stages B and C add calibration on known truth. Later stages add backtests and new-model tests. `specifications/stage-b-rulings.md` says which stage B suites have an outside oracle. Evidence is always labelled analytic, simulated, proxy or observed, and validation reports are self-assessment; there is no second review (owner decision, 2026-11-18).

R1 adds the records that say how far each result goes. The [model inventory](docs/model-inventory.md) gives every model its spec, oracle, outside-checked share and limits. The [edge-case register](specifications/edge-case-register.md) lists boundary cases and whether a golden pins each one; a row marked out of scope names the stage that would bring it in. `conformance/tolerances/money.md` restates every tolerance as money on 10 million notional, so a reader can judge whether a pass is tight enough to matter. The R1 daily workflows are the first runs on observed public data, and their USD curve is labelled a proxy.

### What a tolerance means in money

A tolerance such as 1e-10 says little to a desk. `conformance/tolerances/money.md` restates every class, and every per-case limit, as an error on a 10m notional: basis points of DV01 on a 10Y swap, 32nds of a bond price, and currency units. The widest class, `numerical_scheme`, allows about 1e-4 bp of a 10Y swap's DV01, under one currency unit on 10m. Present-value limits are 1e-9 of notional, which is 0.01 on 10m.

### What is not checked by an outside library

QuantLib's Python wheel has no GARCH, no VIX method, no bivariate t and no large-pool loss model (the Gaussian copula and pool formulas can be re-evaluated with its bivariate normal, but that checks the spec's algebra with itself, so it does not count), so those goldens rest on hand cases, 50-digit or exact-rational replicas and separate float replays. For slices E4, E6, E7 and E8 the outside share is 277 of 449 (61.7%), counting a case only if every output is a QuantLib value; stage-wide it is 557 of 895 (62.2%) (`specifications/05-volatility/stage-e-targets-b.md`).

### Known limits, by topic

Every topic is Implemented, and all inputs are synthetic unless a section says otherwise. The limits as each stage recorded them:

- **Foundations (stage A).** Many golden cases have hand or replay sources, which can share a misreading with the spec. Constructed inputs test the method only. The recorder is built but not scheduled. See the [Roadmap](ROADMAP.md#stage-status).

- **Curves (stage B).** Stage B is Implemented. Almost all curve inputs are synthetic, so exact repricing says nothing about a market. `usecases` and `rulings_b` have no outside oracle, and `risk` is hand and self-consistency only. Risk is bump and rebuild, with no AD. See `specifications/stage-b-rulings.md` and the [Roadmap](ROADMAP.md#stage-status).

- **Options and vol (stage C).** Stage C is Implemented. All inputs are synthetic: the stage C data survey found no free history of option quotes, vol surfaces, borrow cost or dividends. European options only (C1). Arbitrage checks run on the given points only. `vol.sabr.arbfree` at `nu > 0` lacks a tight outside source. See `specifications/stage-c-rulings.md`.

- **Curves and fixed income (stage D).** Stage D is Implemented. All inputs are synthetic. The ESTR payment lag of 2 is a library choice (Strata), not a market standard; TP ICAP terms use 1 (ruling R1-2). From R1, bond-future conversion factors take an optional `contract` input with CME rounding; `null` keeps the stage D `TEN_YEAR` behaviour (ruling R1-3). The stage D data survey (2026-11-07) found free overnight fixings, fitted Bank of England curves, US Treasury par and real curves and UK CPI, but no free swap quotes, bond-level prices, special repo, cross-currency basis, CDS spreads, borrow, commodity curves or MBS factors; those studies stay method tests. Several suites have no outside oracle (CSA discounting, asset swap, FRN, repo, NDF, equity, inflation, commodities, MBS); `specifications/stage-d-rulings.md` lists them. R1 counts outside-oracle cases under a stricter rule: QuantLib is built from its own convention objects through one reviewed table, `oracle/CONVENTION_MAP.md`. On that rule, 419 of the 654 stage D cases (64.1%; most counted cases are fixed-rate bonds) count, suite by suite in `oracle/REPORT.md`.

## Stage F: curves, portfolio risk and the book

Stage F (v0.6.0) is Implemented. On the merged part 2 tree (`stage-f-part2` at `db99d87`, 2026-11-10, observed on one Windows machine through the neutral runner), each of the four builds passed 12,462 of 12,462 golden cases (value-checked, error and invariance cases counted together): Java (JDK 25.0.5), Python (CPython 3.15.2), Rust (1.99.1) and C++ (GCC 15.2.0 under WSL, built with `-DQF_WERROR=ON`). Specs and rulings F-1 to F-44 are in `specifications/`. Every number quoted here is the expected output of the named golden case, computed by the oracle at 40 or more digits.

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
- **Outside oracle, 417 value-checked cases: 53.0% from outside libraries alone, 84.4% with an independent re-derivation of the spec (78.9% without 23 spec-only book cases); old all-case share 41.9%; the 60% floor is met.** Not counted: `risk_f4-0087`..`0095` (the spec keeps the 1996 plus factors by stated vintage, ruling R6-28.1, which rests on the lane's own reading) and `garch_f-0009`, `joint_f-0004` (unverified at 1e-8). v0.6.0 published 225 of 438 (51.4%); D6 counts only library objects and numpy or scipy primitives, not reimplementations (`oracle/OUTSIDE_SHARES.md`). The checks use QuantLib 1.44, SciPy, NumPy and `arch`. Every case without a free outside source is listed with the reason in `oracle/OUTSIDE_GAPS_F.md`. 79 of the cases without one are error cases, which no library can check; the CDS index option (R7) is the largest value-case gap, because its reference paper is not freely available.
- **All inputs are synthetic.** The 500-swap book, the VaR series and the factor returns are drawn from `core.rng` with fixed seeds.
- [Determinism](docs/determinism.md): what is bit-exact across languages and platforms, and what is within tolerance.

## Stage G: rates models and xVA

Stage G (released as v0.7.0 on 2026-11-11) is Implemented. On the integration tree `stage-g-int` (2026-11-11, observed on one Windows machine through the neutral runner) each of the four builds passed 14,492 of 14,492 golden cases, of which 589 are stage G value and error cases and 1,026 are E1 cases for the first 20 stage G operations.

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
- **Outside oracle: 359 of 441 value-checked cases (81.4%) under the tight rule D6, 61.0% under the old all-case count; v0.7.0 published 57.4%.** From the per-case register (`oracle/OUTSIDE_SHARES.md`, regenerated 2026-11-12). Wave 4c compared portfolio exposure with ORE 1.8.17; 80 of 102 `expsim_g` cases count under ruling G-42. The re-test G-42b needs WSL and is carried to stage I, then to stage J (not run at v0.8.1) (G-52).
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
- **Outside oracle: 102 of 153 value-checked cases (66.7%) under the tight rule D6, from a per-case register, without the wave 5 cases (83.6% with them); 36.7% under the old all-case count; v0.8.0 published 62.8%.** Every stage I counted case is a numpy or scipy primitive check; none uses a library pricing object (`oracle/OUTSIDE_SHARES.md`). Wave 5 (ruling I-55) added 165 value cases from seeded draws, checked against QuantLib, numpy and scipy; draws were rejected only by rules fixed before any outside check (3 in all), never for disagreeing. Error cases are in the denominator and never count, and integer lots, beta futures, residual reports and slippage still have no outside library that solves a different way (`program/STAGE_I_HANDOVER.md`, "WAVE 5 READY").
- **Q6-01, the synthetic method test, failed** (78.4% inside the spread against 80%); kept as published. Q6-02 (prereg signed 2026-11-14, robust Huber-type fit and shape-only penalty, fresh seed 20261113, run once) **passed** on synthetic quotes: 87.4% of test quotes inside the spread, churn median 0.98 and 95th percentile 1.56, no arbitrage on 48 of 48 test days; the selected penalty was 0, so the pass comes from the robust fit, not the penalty (`research/q6/q6_02_output.json`). Real quotes: not done (tutorial 22).
- **Q6 (calibration on real noisy quotes) is blocked** by the data terms of the candidate sources; only its preregistration exists (`research/preregs/Q6-01-churn-bound.md`).
- **The hedges are calculations.** Nothing is traded, and costs, impact and margin are inputs, not estimates from a market.
- **Tested on one machine.** The 14,935-case runs were on one Windows machine; CI on the stage I pull request is the cross-platform check.

## Stage J: backtest overfitting and research statistics

Stage J wave 1 (released in v0.9.0) is specified in `specifications/11-research/` (rulings J-1 to J-23 and J-19a in `specifications/stage-j-rulings-w1.md`) and pinned by the suites `backtest_j`, `purgedcv_j`, `regime_j` and `rstats_j` in `datasets/golden/stage_j/`. All four builds pass every case (15,215 of 15,215 at contract 1.13.0 after wave 1; 15,315 of 15,315 at contract 1.14.0 after wave 2, 2026-11-14). The numbers below were printed by all four builds on 2026-11-14 unless a paragraph says otherwise. Every input is synthetic except the DSR example, which is the paper's own.

[Tutorial 23](docs/getting-started/tutorial-23-backtest-honestly.md) and [Tutorial 24](docs/getting-started/tutorial-24-is-the-sharpe-real.md) work through this section on hand-sized data, Tutorials 27 to 32 take the tools further (see [Using the tools](#using-the-tools-four-questions-every-study-meets)), the [Cookbook](COOKBOOK.md#stage-j-recipes) has one recipe per operation, and the gallery page [Research workflow](docs/curves/research-workflow.md) runs the whole chain on twelve rules.

Why it matters. A strategy's backtest is the evidence most research rests on, and it is easy to make it say more than it can. The three usual ways are look-ahead (using data from after the decision), free trading, and selection (reporting the best of many tries as if it were the only one). The first two are mechanics; the third is statistics, and it is the one that survives careful coding.

### A backtest that cannot see the future

**Plain idea.** At each close the strategy names the position it wants, using only data up to that close. The backtester holds that position from a later close, pays for every change, and books each bar's price move on the position held before that bar's trade. If a strategy's result collapses when its trades are delayed by one bar, it was probably using information it could not have had.

**Formal statement.** For `t = 0 .. T-1`, `q_t = targets[t - lag]` (0 before `lag`), `d_t = q_t - q_{t-1}`, gross `g_t = q_{t-1} (p_t - p_{t-1}) m`, cost `k_t = |d_t| p_t (half_spread_bps / 10^4) m + |d_t| commission_per_unit + fixed_per_trade 1[d_t != 0]`, net `n_t = g_t - k_t` (`backtester.md`, J-2 to J-6). Gross minus the three cost totals equals net as an identity, and the `EVENT` and `VECTOR` engines must agree to 1e-10 (J-3). `lag = 0` is legal only so that a look-ahead canary can be built and caught (J-2) [LdP18, ch. 11].

**Worked example.** `backtest_j-0001`: twelve prices from 100 to 107, ten trades, lag 1, half-spread 5 bp, commission 0.01 a unit, fixed fee 1 a trade. Gross P&L 6.5; costs 1.13975 + 0.22 + 10; net -4.85975, the same in both engines. The canary, `+1` if the next close is higher else `-1`, makes 21 at lag 0 (the sum of all eleven absolute moves) and loses 10 at lag 1. Outside check: vectorbt 1.2.1 reproduces all 14 value-checked `backtest_j` cases; the other 9 are error cases (J-19a).

### Cross-validation when labels overlap

**Plain idea.** A label such as "the return over the next five days" spans time. In ordinary k-fold, a training label can share days with a test label, and a model learns the test answer from it. Purging drops those training rows. Because returns are serially correlated, an embargo also drops a few rows just after each test block.

**Formal statement.** Contiguous folds, the first `n mod k` one row longer (J-7). For a test block `[a, b)` with span `[lo, hi] = [t0_a, max t1_i]`, training row `j` is purged when `t0_j <= hi` and `t1_j >= lo`; the embargo drops rows `b .. b + h - 1`, `h = floor(embargo_pct n)` (J-8). Combinatorial purged CV with `N` groups and `k` test groups has `C(N, k)` splits and `k C(N, k) / N` complete backtest paths [LdP18, sections 7.4 and 12.4].

**Worked example.** `purgedcv_j-0001`: ten rows, row `i` covering `[i, i + 2]`, three folds. The first test block, rows 0 to 3, spans times 0 to 5, so rows 4 and 5 are purged and training is rows 6 to 9; plain k-fold would have trained on 4 to 9. A 30 % embargo (3 rows) also drops row 6. CPCV with `N = 6`, `k = 2` gives 15 splits and 5 paths. Outside checks: timeseriescv 0.2, scikit-learn 1.9.1 and skfolio 1.12.12 reproduce 12 of 15 `purgedcv_j` cases (J-19a; timeseriescv's end-of-data purge defect is recorded in `program/WAVE1_ORACLE_NOTES.md`).

### Is the Sharpe ratio above zero? The PSR

**Plain idea.** A Sharpe ratio measured on a year of data has a wide error band, wider still when returns are skewed or fat-tailed. The probabilistic Sharpe ratio turns the estimate into a probability that the true Sharpe is above a benchmark.

**Formal statement.** With the per-period Sharpe `SR`, `T` observations, skew `g3` and non-excess kurtosis `g4`: `v = 1 - g3 SR + (g4 - 1)/4 SR^2`, `z = (SR - SR*) sqrt(T - 1) / sqrt(v)`, `PSR = Phi(z)`; `v <= 0` is `E_DOMAIN` (J-14) [BLdP12].

**Worked example.** An annual Sharpe of 1.0 from 252 daily returns is a daily Sharpe of 0.0630. With normal returns, `z = 0.9970` and PSR = 0.8406; with skew -1 and kurtosis 6, PSR = 0.8329. A full year at Sharpe 1 does not reach the 0.95 of a one-sided 5 % test.

### Is it above luck? The deflated Sharpe ratio

**Plain idea.** Try enough useless strategies and the best of them will show a good Sharpe ratio. The deflated Sharpe ratio raises the benchmark of the PSR to the Sharpe the best of `N` useless trials is expected to show, given how much their Sharpe ratios vary.

**Formal statement.** `SR0 = sqrt(V) ((1 - gamma) Phi^{-1}(1 - 1/N) + gamma Phi^{-1}(1 - 1/(N e)))`, with `V` the variance of the trials' per-period Sharpe ratios and `gamma` the Euler-Mascheroni constant; `DSR = PSR` with `SR* = SR0`; `N = 1` gives `SR0 = 0` (J-13) [BLdP14]. `N` is the count logged in `research/trials.csv` before results are seen.

**Worked example.** The paper's own (`rstats_j-0001`; [BLdP14] pp. 9-10, read 2026-11-13): annual Sharpe 2.5 over 1,250 days, skew -3, kurtosis 10, 100 trials, variance of annual Sharpe 0.5. `SR0` = 0.1132 a day against an observed 0.1581, and DSR = 0.9004, not significant at 5 %; with 46 trials, 0.9505. Both match the printed values to four digits; with 1,000 trials the same Sharpe gives 0.6399 (Python build). On the gallery page, the best of twelve rules on a driftless random walk has an annual Sharpe of 1.043 and PSR 0.9061, but DSR 0.5491: luck, correctly flagged. DSR and PSR have no free outside library; the check is the paper (J-19a).

### How often does the winner fail out of sample? PBO

**Plain idea.** Split the history into blocks. For every way of choosing half the blocks, pick the strategy that did best on them and rank it on the other half. If the in-sample winner keeps landing in the bottom half, the selection is overfitting.

**Formal statement.** Combinatorially symmetric cross-validation: `T x N` performance, `S` contiguous blocks, `C(S, S/2)` splits in lexicographic order; for each, the training winner `n*` (lowest index on ties), its average test rank `r`, `omega = r / (N + 1)`, logit `lambda = log(omega / (1 - omega))`; `PBO = #{lambda <= 0} / C(S, S/2)` (J-15 to J-17) [BBLdPZ17, section 2].

**Worked example.** `rstats_j-0025`: rows `[1, 0], [1, 0], [0, 2], [0, 2]`, two blocks, mean metric. Each block's winner is last on the other block, `omega = 1/3`, both logits `log(1/2) = -0.6931`, PBO = 1. In Tutorial 24, eight periods of three strategies give PBO 5/6 = 0.8333. On the gallery page's driftless prices, PBO = 0.4571 over 70 splits: near one half, which is what noise gives. The paper prints no fully specified example, so the hand cases are the goldens and no outside library counts (J-19).

### Could the study have found it? Power

**Plain idea.** Before running a study, ask how large a Sharpe ratio its sample could tell apart from zero. Below that size a real edge and no edge look the same.

**Formal statement.** `z_sum = Phi^{-1}(1 - alpha) + Phi^{-1}(power)`, `mds = z_sum / sqrt(years)` (annual, one-sided, iid), `years_required = (z_sum / SR_target)^2`, `se_at_target = sqrt((1 + SR^2/2)/years)` [Lo02].

**Worked example.** At 5 % and 80 % power, `z_sum = 2.4865`. One year detects only an annual Sharpe of 2.49, five years 1.11, and 13.83 years 0.6686, the 0.67 of the R3-01 preregistration (`rstats_j-0017`). Detecting 0.5 needs 24.73 years. Outside check: statsmodels 0.15.0 reproduces 5 of the `rstats_j` power cases (J-19a). Serial correlation makes the true minimum larger; the preregistrations report a simulated power beside the formula.

**What this meant for R3.** The full pass rule (deflated Sharpe, 2x costs, every third positive) is stricter than the bare test, so its simulated pass probability at the MDS was only 12.6 % to 15.2 %. All three studies failed on the holdout (`research/r3/RESULTS.md`). With power that low, a fail mostly tells you the in-sample choice did not carry over; it cannot show that no edge near the MDS exists. Plan the sample length before the study, not after.

### Regimes, as description

**Plain idea.** A hidden Markov model says the market moves between a few states, calm and turbulent for example, each with its own return distribution. The Viterbi algorithm finds the single most likely sequence of states for the returns observed.

**Formal statement.** `delta_t(j) = max_i (delta_{t-1}(i) + log A_ij) + log e_t(j)` with back-pointers, ties to the smallest index (J-11), Gaussian or given emissions (J-10) [Rab89, section III.B].

**Worked example.** `regime_j-0001`, the textbook Healthy and Fever model: path 0, 0, 1 with probability 0.01512. In Tutorial 24, twelve returns with standard deviation 0.5 or 2 label the four large moves turbulent: `000011110000`. hmmlearn 0.3.3 reproduces all 10 value-checked `regime_j` cases (J-19a). The labels are smoothed over the whole sample, so using them as a signal is look-ahead.

### Wave 2: building a portfolio and testing a risk model

Wave 2 (rulings J-W2-1 to J-W2-23 in `specifications/stage-j-rulings-w2.md`, suites `optim_j`, `estim_j`, `esbt_j` and `baumwelch_j`) adds the tools a portfolio study needs once it has returns: estimate, optimise, see where the risk sits, and test the risk model afterwards. The seven operations are implemented in all four languages at contract 1.14.0 and merged to `main` (PR #40, 2026-11-14; released in v0.9.0). The numbers in the next six sections were printed by the Python build on 2026-11-14; those that Tutorials 25 and 26 print were printed digit for digit by the Rust, Java and C++ builds too, the same day. [Tutorial 25](docs/getting-started/tutorial-25-build-and-stress-a-portfolio.md) and [Tutorial 26](docs/getting-started/tutorial-26-test-es-and-fit-regimes.md) work through them, and the [diagrams page](docs/diagrams/README.md#portfolio-pipeline) draws the pipeline.

### Mean-variance: return against risk, with limits

**Plain idea.** Each extra unit of expected return costs some variance. An investor with risk aversion `gamma` picks the fully invested weights that make expected return minus `gamma/2` times variance as large as possible, within per-asset limits. Where a limit binds, the asset sits on it; the others share the rest so that one more unit of capital earns the same in each.

**Formal statement.** Maximise `mu'w - (gamma/2) w' Sigma w` subject to `sum w = 1` and `lower <= w <= upper` (defaults 0 and 1), with `Sigma` symmetric positive definite so the optimum is unique (J-W2-2, J-W2-3) [Mar52]. With `g_i = mu_i - gamma (Sigma w)_i - nu`, the optimum has `g_i = 0` for a free asset, `g_i <= 0` at a lower bound and `g_i >= 0` at an upper bound; `at_bound` reports `-1`, `0` or `+1` (J-W2-4) [NW06, ch. 16].

**Worked example.** Three assets with volatilities 20 %, 10 % and 15 % and expected returns `(0.0885, 0.0125, 0.0105)`, `gamma = 2.5` (Tutorial 25). With no limits the weights are `(0.9, -0.1, 0.2)`. Long-only puts asset 2 at zero (`at_bound -1`), and equal marginal utility for the other two, `0.0885 - 2.5 x 0.04 w_1 = 0.0105 - 2.5 x 0.0225 (1 - w_1)`, gives `w_1 = 0.8592`. A 60 % cap on asset 1 gives `(0.6, 0.1887, 0.2113)`. Outside check: the generator certifies every golden's optimum in exact arithmetic and compares scipy SLSQP, within 1.8e-8 (J-W2-15). The DAQP 0.11.2 active-set QP solver then reproduced all 21 value-checked mean-variance goldens, worst weight gap 1.5e-15 (J-W2-16).

### Shrinking the covariance matrix

**Plain idea.** With `T` periods of `N` assets the sample covariance has `N(N+1)/2` entries to estimate from `T N` numbers, and the optimiser leans hardest on its least reliable parts. Ledoit-Wolf replaces it by a weighted average of itself and a multiple of the identity, with the weight estimated from how noisy the sample is.

**Formal statement.** Demean each column; `S = (1/T) sum_t x_t x_t'`, `m = tr S / N`, `d^2 = ||S - m I||^2 / N`, `bbar^2 = (1/T^2) sum_t ||x_t x_t' - S||^2 / N`, `b^2 = min(bbar^2, d^2)`, `delta = b^2 / d^2` (0 when `b^2 = 0`), and the estimate is `delta m I + (1 - delta) S` (J-W2-7) [LW04]. These are scikit-learn's conventions with `assume_centered = False`.

**Worked example.** Four rows `(2, 1), (-2, -1), (1, -1), (-1, 1)`: `S = [[2.5, 0.5], [0.5, 1]]`, `m = 1.75`, `d^2 = 0.8125`, `bbar^2 = 0.84375`, so `b^2 = d^2` and `delta = 1`: the sample is discarded for `1.75 I`. Six months of three assets give `delta = 0.1811`, and a sample correlation of -0.9688 becomes -0.7901. In the golden `estim_j-0005`, 55 rows of 5 assets, `delta = 0.8219`. Outside check: the generator computes the estimator in two algebraic forms that agree in exact arithmetic (J-W2-15), and scikit-learn 1.9.1 `LedoitWolf` reproduces all 13 value-checked Ledoit-Wolf goldens (J-W2-16, J-W2-23).

### Adding views: Black-Litterman

**Plain idea.** Expected returns are much harder to estimate than covariances, and mean-variance weights swing with them. Black-Litterman starts from the returns that would make the market portfolio optimal, then moves them towards an investor's views by as much as the views' uncertainty, set against the prior's, allows.

**Formal statement.** With prior `pi`, scale `tau`, pick matrix `P`, views `q` and view covariance `Omega` (symmetric positive definite): posterior mean `pi + tau Sigma P' (P tau Sigma P' + Omega)^-1 (q - P pi)`; `posterior_covariance = tau Sigma - tau Sigma P' (P tau Sigma P' + Omega)^-1 P tau Sigma`; `predictive_covariance = Sigma + posterior_covariance` (J-W2-8) [BL92, HL99]. The reverse optimisation `pi = delta Sigma w_mkt` is the caller's.

**Worked example.** Market weights `(0.5, 0.3, 0.2)` and `delta = 2.5` imply `pi = (0.0545, 0.0165, 0.0135)`, a spread of 0.038 between assets 1 and 2. A view of 0.08 with variance 0.0002, against the prior's 0.0019 for that spread, moves it to `(0.0002 x 0.038 + 0.0019 x 0.08) / 0.0021 = 0.0760`. The optimal weights move from `(0.5, 0.3, 0.2)` to `(0.9, -0.1, 0.2)`, only along the row of `P`: asset 3, with no view, keeps 0.2. Outside check: the update form against the precision form, exactly (J-W2-15), and PyPortfolioOpt 1.6.0 reproduces all 6 value-checked Black-Litterman goldens (J-W2-16).

### Where the risk sits: Euler contributions and risk parity

**Plain idea.** Weights say where the capital is, not where the risk is. Because a portfolio's volatility doubles when every weight doubles, it splits exactly into one piece per asset, each the weight times the volatility's sensitivity to that weight. Risk parity turns this round: choose the weights so that the pieces match chosen budgets, equal for example, without using expected returns at all.

**Formal statement.** `sigma = sqrt(w' Sigma w)`, contribution `w_i (Sigma w)_i / sigma`, and the contributions add up to `sigma` by Euler's theorem for functions homogeneous of degree 1 (J-W2-6) [Tas99]. Risk parity: long-only `w` with `w_i (Sigma w)_i / (w' Sigma w) = b_i / sum b`, which exists and is unique for positive definite `Sigma`; it solves `Sigma y = b / y`, `w = y / sum y` (J-W2-5) [Spinu13, Roncalli13]. With equal budgets the volatility lies between those of the minimum-variance and the equally weighted portfolios [MRT10].

**Worked example.** The market weights `(0.5, 0.3, 0.2)` have volatility 0.1182, and asset 1 contributes 0.0923 of it: half the capital, 78.1 % of the risk. Equal risk budgets give `(0.2387, 0.4302, 0.3311)`, most capital in the least volatile asset. With two assets and equal budgets the cross terms cancel and `w` is proportional to `1 / sigma_i` for any correlation: volatilities 20 % and 30 % give `(0.6, 0.4)` (`optim_j-0029`). The generator solves risk parity at 50 digits and checks the shares to 1e-40. Outside, cvxpy 1.9.3 with Clarabel 0.11.1 reproduces 6 of the 8 value-checked risk-parity goldens; on `optim_j-0029` and `-0030` Clarabel stops at 2.9e-10 and 2.8e-8, short of the golden's tolerance, and a 50-digit two-asset closed form confirms both goldens. autograd 1.9.1 reproduces all 6 Euler goldens (J-W2-16).

### Backtesting expected shortfall: Z2

**Plain idea.** A VaR backtest counts the days a loss beat VaR. Expected shortfall claims more: how large those losses are on average. Z2 divides each exceedance by the ES forecast for its day and compares the total with what was expected. About 0 means the model sized its tail right; clearly negative means ES was too small.

**Formal statement.** Losses `L_t` are positive; `I_t = 1{L_t > VaR_t}` (strict); `Z2 = 1 - sum_t L_t I_t / (T alpha ES_t)`, with expected value 0 under a correct model (J-W2-10) [AS14, test 2]. The critical values depend on the tail model, so they are not outputs; a study simulates them under its own model (gap G13).

**Worked example.** Twenty losses with two above a VaR of 2.0, at 2.5 and 3.5, and `alpha = 10 %`, so two exceptions are expected and Kupiec's test is passed perfectly (LR 0, p-value 1). With ES 3.0, `Z2 = 1 - 6 / 6 = 0`; with ES 2.2, `1 - 6 / 4.4 = -0.3636`; with ES 4.0, 0.25 (Tutorial 26). The count cannot tell the three apart; Z2 can. Golden `esbt_j-0001`: losses 1, 3, 0.5, 4 against VaR 2, ES 2.5, `alpha = 0.25` give `Z2 = -1.8`. No outside library implements Z2; the checks are hand cases.

### Estimating regimes: Baum-Welch

**Plain idea.** Viterbi (above) labels days when the model's parameters are known. Baum-Welch estimates them from the returns: guess, work out each day's probability of each state, re-estimate the parameters from those probabilities, and repeat. Each round can only raise the likelihood, and the algorithm stops when the gain becomes negligible.

**Formal statement.** A scaled forward-backward E-step gives `gamma_t(i)`, `xi_t(i, j)` and `loglik = sum_t log c_t`; the M-step sets `pi_i = gamma_0(i)`, `A_ij = sum xi_t(i, j) / sum gamma_t(i)` and `gamma`-weighted means and variances [Rab89, sections III.A and III.C]. One iteration is an M-step then an E-step; the run stops after the first gain below `tolerance` or after `max_iterations` (J-W2-11). No variance floor and no relabelling; a collapse is `E_DOMAIN` (J-W2-13). EM never lowers the likelihood [DLR77].

**Worked example.** One state on 24 returns stops at iteration 2 with the sample mean 0.1083 and the population standard deviation 1.3675. Two states, tolerance `1e-6`, stop after iteration 7 with standard deviations 0.317 and 2.173 and nearly equal means, staying probabilities 0.8354 and 0.7582 (average spells of 6.1 and 4.1 days), and a log-likelihood of -31.8744 against -41.5653 for one state. Viterbi with the fitted parameters labels the two turbulent spells, `000011110000000011110000` (Tutorial 26). Outside check: the oracle recomputes every log-likelihood with an independent log-space forward pass (J-W2-15), and hmmlearn 0.3.3 `GaussianHMM.fit` with the same start values and stop rule reproduces all 6 value-checked `baumwelch_j` goldens (J-W2-16).

### Using the tools: four questions every study meets

The sections above define each operation. The four below put them to work on questions a study has to answer before anyone should believe it. Each is worked through on synthetic data, digit for digit in all four builds, in Tutorials 27 to 32; the numbers here are from those pages (2026-11-15).

#### What do costs do to a backtest?

**Plain idea.** A rule that trades often must earn more per trade. The quickest robustness check is the half spread at which the strategy earns nothing.

**Formal statement.** In `research.backtest.run` the spread cost is `sum_t |d_t| p_t m half_spread_bps / 10^4 = turnover x half_spread_bps / 10^4`, and nothing else depends on the half spread, so net P&L is linear in it and the break-even is `b* = (total_gross - total_commission - total_fixed_cost) / (turnover x 10^-4)` (`11-research/backtester.md`). Fills are in full at the close plus or minus the half spread, with no impact (J-1), so real costs are higher.

**Worked example.** A five-bar trend rule on 250 synthetic closes with a built-in cycle: gross 461.73, 47 trades, turnover 93,055.8, commission 9.30, so `b* = 48.62` bp, and a run at that half spread prints net 0.000000. One more bar of execution lag cuts the gross by 37 % (171.94), about what 18.5 bp of spread would cost; a ten-bar rule trades 19 times and ends with a similar net ([Tutorial 27](docs/getting-started/tutorial-27-what-costs-do-to-a-backtest.md)).

#### What does a portfolio constraint cost?

**Plain idea.** Compare the best portfolio with and without the constraint at the same risk aversion, in the investor's own currency: certainty-equivalent return, expected return less the charge for variance.

**Formal statement.** `CE(w) = mu'w - (gamma/2) w' Sigma w`, the mean-variance objective itself; the cost of a constraint is `CE(w_free) - CE(w_constrained) >= 0`, zero exactly when the constraint does not bind at the free optimum. Without bounds `w(gamma) = w_mv + z / gamma`, so the frontier's expected return is linear in `1/gamma` [Mar52].

**Worked example.** Four assets, volatilities 20 % to 5 %: at `gamma = 1` the free portfolio has CE 0.0823 and long-only 0.0627, a cost of 195.5 bp a year; from `gamma = 5` the free optimum holds no shorts and the cost is zero. Near minimum variance each asset's Euler risk share is close to its weight, as `Sigma w = lambda 1` makes it exactly at the minimum ([Tutorial 28](docs/getting-started/tutorial-28-efficient-frontier.md)).

#### How strong is a view?

**Plain idea.** For one Black-Litterman view the posterior moves a fixed fraction of the way from the prior to the view, and that fraction is set by the view's variance against the prior's.

**Formal statement.** With `s^2 = tau P Sigma P'`, the posterior value of `P mu` is `P pi + c (q - P pi)` with `c = s^2 / (s^2 + Omega)`; the mean depends on `tau` and `Omega` only through `Omega / tau`, while `posterior_covariance` scales with `tau` (`07-portfolio/estimation.md`, J-W2-8) [BL92, HL99].

**Worked example.** Tutorial 25's spread view, `s^2 = 0.0019`: `Omega` = 1e-8, 0.0002, 0.0019, 0.019 and 1 give spreads 0.0800, 0.0760, 0.0590, 0.0418 and 0.0381, each equal to `0.038 + c x 0.042` to four digits. Doubling `tau` and `Omega` together leaves the posterior returns unchanged to six digits ([Tutorial 29](docs/getting-started/tutorial-29-view-confidence.md)).

#### How many trials can a Sharpe ratio survive, and does shrinkage help?

**Plain idea.** The deflated Sharpe ratio falls as the number of trials grows, slowly but without limit; the minimum detectable Sharpe falls only with the square root of the sample length. And Ledoit-Wolf, the usual fix for a short covariance history, trades noise for bias towards its target, so it does not always help.

**Formal statement.** `SR0 = sqrt(V) ((1 - gamma_E) Phi^-1(1 - 1/N) + gamma_E Phi^-1(1 - 1/(N e)))` grows roughly as `sqrt(2 ln N)`; `mds = z_sum / sqrt(years)` (J-13, `research-statistics.md`) [BLdP14, Lo02]. Ledoit-Wolf minimises expected squared error under its own assumptions [LW04]; on one sample, or with a target far from the truth, it can lose.

**Worked example.** An annual Sharpe of 1.0 over three years, skew -0.5, kurtosis 5: DSR 0.9555 for one trial (equal to the PSR), 0.6413 for 10, 0.3259 for 100, 0.1429 for 1,000; detecting a Sharpe of 1.0 at 5 % and 80 % power takes 6.18 years ([Tutorial 30](docs/getting-started/tutorial-30-trials-and-power.md)). Purged five-fold CV with 20-bar labels keeps 40 of 100 training rows in the middle folds and lets none leak, against 160 leaking labels in plain k-fold ([Tutorial 31](docs/getting-started/tutorial-31-leakage-and-purging.md)). For five assets with volatilities 6 to 2 and correlation 0.5, Ledoit-Wolf's shrinkage falls from 0.30 at 10 months to 0.006 at 1,000; it brought the estimate closer to the truth at only one of four lengths on that seed, yet halved the risk-parity weight error at 30 months ([Tutorial 32](docs/getting-started/tutorial-32-shrinkage-and-sample-length.md)). One seed is one draw, not a result.

### Stress testing with history: the shock library

**Plain idea.** Take a crisis you remember, measure how far each point of the yield curve moved between two dates, and apply the same moves to today's curve and book. The answer is not a probability; it is "this is what that day would cost us now".

**Formal statement.** `shift_bp_j = 100 (y_j(end) - y_j(start))` for each tenor `j`, in binary64, from stored par yields in percent; level is the mean shift and slope the last tenor's shift minus the first's (J-W3-2, J-W3-3). Replay interpolates the shift linearly in tenor onto the book's tenors, holds it flat outside the shock's own tenors, scales it, adds `applied_bp / 100` to the yields and, given DV01s, reports `pnl = -sum_j dv01_j applied_bp_j` (J-W3-4, J-W3-5; `06-risk/scenario-stress.md`). The library `datasets/scenarios/us_treasury_shocks.json` holds four named moves (2008, 2013, 2020, 2022) from Treasury par yield files with source URL, retrieval time and SHA-256, and every start and end value matches the Fed's H.15 release (worst gap 0.0000 percentage points).

**Worked example.** The 2013 taper tantrum (1 May to 5 September): 2Y +32 bp, 10Y +132 bp, level 64.82 bp, slope 105 bp, a steepener. A book long 1,200 per bp at 2Y and 3,500 at 10Y gains 697,900 in the 2008 move and loses 1,392,700 in the 2022 one (Tutorial 33). Outside check: numpy `interp` reproduces every replay golden, and a pandas date lookup every historical-shock golden (`oracle/OUTSIDE_J.json`).

### Backtesting an interpolation

**Plain idea.** Hide a quoted point, rebuild the curve or smile from the others, and see how far the rebuilt value lands from the quote. Repeat for every inner point; the errors say how much to trust the curve between quotes.

**Formal statement.** Leave-one-out: for each inner knot `i`, `e_i = f_{-i}(x_i) - y_i` with `f_{-i}` the same `core.interp.evaluate` method on the other knots; end knots are never left out (J-W3-8). Surface hold-out: per expiry, interpolate total variance `w = sigma^2 T` across the kept strikes and compare `sqrt(w / T)` with the held-out vols (J-W3-9; `11-research/interp-backtest.md`). Outputs are the errors, their maximum absolute value and their RMSE.

**Worked example.** Knots `(1, 3.0), (2, 3.4), (3, 3.6), (5, 4.0)` with `linear`: hiding `x = 2` rebuilds 3.3, error -0.1; hiding `x = 3` rebuilds 3.6 exactly. The two research backtests, rules committed before the run: B1 (cubic spline on an SSVI smile) **fails**, 0.370 vol points at the 3-month ATM strike against a limit of 0.25; B2 (pchip on Treasury par, 3M to 10Y) passes narrowly, median 2.62 bp and 95th percentile 14.19 bp (`research/interp_backtest/RESULTS.md`). Outside check: numpy `interp` and scipy `CubicSpline` and `PchipInterpolator` reproduce all 16 value goldens.

### Watching for drift: CUSUM, Page-Hinkley, PSI and KS

**Plain idea.** A model is fitted on yesterday's data. A drift detector watches the new data and raises an alarm when it no longer looks like the old: CUSUM and Page-Hinkley add up small deviations of the mean until they are too large to be chance; PSI and KS compare the whole distribution of two windows.

**Formal statement.** CUSUM on `z = (x - mu0) / sigma`: `S+_t = max(0, S+_{t-1} + z_t - k)`, `S-_t` the mirror, alarm when either is strictly above `h`, both restart (J-W3-10) [PAGE54]. Page-Hinkley: `m_t = sum (x_s - xbar_s - delta)` with `xbar_s` the running mean since the last restart, alarm when `m_t - min(0, m_1, ..., m_t) > lambda` (J-W3-11). PSI `= sum_b (a_b - e_b) ln(a_b / e_b)` with bins at the reference's type-1 quantiles, right-closed, shares floored at `1e-4` (J-W3-12). Two-sample KS: `D = max |F_n - G_m|` and the exact p-value by counting lattice paths in big integers (J-W3-13; `11-research/drift-detectors.md`). Siegmund's approximation gives CUSUM with `k = 0.5`, `h = 5` an in-control average run length of about 469 steps two-sided and about 10.3 steps after a one-sigma shift [SIEG85].

**Worked example.** A fixed ten-day pattern with mean 0, then the same plus 1.5 from day 60: CUSUM (`k = 0.5`, `h = 5`) alarms on day 64 and again every six days while the shift lasts; Page-Hinkley (`delta = 0.5`, `lambda = 5`) alarms once on day 64, because after its restart the running mean absorbs the new level; PSI on five bins is 7.37 and KS gives `D = 0.9`, `p = 5.8e-13` (Tutorial 33). The A3 study (prereg `research/preregs/A3-drift.md`, unsigned at the time of writing) measures these operating characteristics on 2,000 simulated paths; its Page-Hinkley `lambda` was changed from the plan's 50 to 5 before any draw, from the analytic calibration only (decision record DR-A3-1), because 50 was predicted to take about 100 steps against a 15-step limit. Outside check: scipy `ks_2samp(method="exact")` reproduces 7 KS goldens and numpy/scipy quantiles, binning and `rel_entr` 6 PSI goldens; no free library implements CUSUM or Page-Hinkley with these conventions (river's Page-Hinkley starts its minimum at infinity and has a warm-up gate), so those 13 value goldens are hand and rational re-implementation checks only.

### Financing and liquidity curves (curves lane)

Two curve families the curves page listed as missing, added in v0.9.0 by the curves lane (rulings J-C-1 to J-C-9 in `specifications/stage-j-rulings-curves.md`, suites `termfin_j` and `liqcurve_j`, contract 1.15.0). Implemented in all four languages; the numbers below were printed by the Python build on 2026-11-15 and by the Rust, Java and C++ builds through Tutorials 34 and 35 the same day.

**Plain idea, financing.** Secured financing costs a different rate at each term, and so does borrowing a stock. Each term repo quote fixes one point of the spread over the funding curve; between quotes the forward spread is flat. Stage D's ruling D22 kept these flat; J-C-2 extends it without changing the stage D operations.

**Formal statement.** `S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i`, linear in `t` between `(0, 0)` and the pillars; `P_f(t) = exp(-Z(t) t - S(t))`; borrow `B(T_j) = b_j T_j`, never falling; forward `F = (S_0 - sum A_i C(t_i)) / C(T)` with `C(t) = P_f(t) e^(B(t))` (`02-curves/financing-term-structure.md`).

**Worked example.** Flat 4 % funding and one 5 % one-year term repo: `S(1) = ln 1.05 - 0.04 = 0.0087901642`; spot 100 then has a one-year forward of exactly 105.

**Plain idea, liquidity.** Selling `Q` units over `h` days costs half the spread, an impact that grows with participation `Q/(V h)`, and timing risk that grows with `h`. The curve gives all three for every size and horizon and the horizon where their sum is smallest.

**Formal statement.** `c(Q, h) = s + Y sigma (Q/(V h))^delta + z sigma sqrt(h/3)` [TLD11, AFTHL05, AC00]; `h* = (2 delta a / b)^(1/(delta + 1/2))` with `a = Y sigma (Q/V)^delta`, `b = z sigma / sqrt 3` (`10-execution/liquidity-curve.md`). Stage H reuses it: at one day and `delta = 1/2` the impact is its draft `exec.impact.sqrt`.

**Worked example.** `sigma` 2 %, `V` 10 million, 100,000 shares in one day: impact `0.02 x sqrt(0.01) = 20` bp. For 1,000,000 shares at `z = 1.645` the optimum is 0.3330 days at 224.21 bp.

**Evidence.** Seven hand cases; the rest reference-computed in mpmath. No free library or published worked example covers either curve, so both are self-assessed (J-C-9).

### What stage J's evidence does and does not show

- **Outside oracle: 41 of 63 value-checked wave 1 cases (65.1 %),** from `oracle/OUTSIDE_J.json` (J-19a). PSR, DSR and PBO have no free library; DSR is checked against the paper's printed example, PBO by hand.
- **Wave 2 outside checks: 58 of 67 value cases** (rulings J-W2-16 and J-W2-23: DAQP, cvxpy with Clarabel, autograd, scikit-learn, PyPortfolioOpt and hmmlearn; `esbt_j` has none). The rest are checked by hand cases, exact KKT certificates, scipy SLSQP agreement and pairs of independent algebraic forms inside the generator.
- **Wave 3 outside checks: 31 of 56 value cases** (`oracle/OUTSIDE_J.json`): numpy `interp` on the eight replay cases, numpy and scipy interpolants on all 16 interpolation-backtest cases (a re-run of the calls that generated those goldens, so a weak second check), and scipy `ks_2samp` exact on seven of the eight KS cases. The five historical-shock cases (a date lookup plus arithmetic), PSI, CUSUM and Page-Hinkley are not counted. The curves lane adds 20 value cases and the hedge rank-cut fix 4 and the sign-state fix 2 (J-I.2), none with an outside check (J-C-9). Stage J as a whole was 130 of 212 value cases (61.3 %) at v0.9.0; after the validation evidence pack and the three v0.9.1 fuzz-fix value cases it is 143 of 215 (66.5 %, `oracle/OUTSIDE_SHARES.md`), above the 60 % floor.
- **The operations are tools, not results.** The gallery page and Tutorials 23 to 32 are teaching examples on synthetic data. The one set of study results in stage J, the three R3 holdout runs, is null with a pass probability of 13 % to 15 % at the minimum detectable Sharpe, so it is weak evidence either way (`research/r3/RESULTS.md`).
- **The iid formulas are optimistic.** PSR, DSR and the power formula assume independent returns; studies add block-bootstrap intervals and simulated power.
- **Tested on one machine, then in CI.** The 15,215-case wave 1 runs and the 15,315-case wave 2 runs were on one Windows machine. The cross-platform workflow passed on the stage J pull request (2026-11-14), and all eleven push workflows passed on `main` at `a148d0e`, including the tutorial check in all four languages (observed with `gh run list`, 2026-11-15).

## Stage H: execution and microstructure (v0.10.0)

Stage H is implemented in all four languages from v0.10.0, the `paper.*` operations included. Its specs are in `specifications/09-microstructure/` and `specifications/10-execution/` (spec version 0.1.0, confirmed 2026-11-18; rulings HR-1 to HR-129 in the `specifications/stage-h-rulings-*.md` files). The worked examples below are spec golden cases, which every build reproduces in conformance (observed, local, 2026-11-18 and 2026-11-19). Every venue in this stage is simulated; the only real data is one crypto venue's public book. [Tutorials 36 to 50](docs/getting-started/README.md) run the same goldens, and question bank [set 13](docs/question-bank/13-execution-microstructure.md) tests them.

### Why slicing exists

**Plain idea.** An order bigger than the quantity at the best price moves the price if sent at once. Cutting it into child orders over time lets the book refill, at the cost of leaving the rest of the order exposed to price moves.

**Formal statement.** `exec.schedule.twap`, `exec.schedule.vwap` and `exec.schedule.pov` (`10-execution/schedules.md`). TWAP gives equal slices, VWAP slices in proportion to an input volume profile, POV a share `p` of all volume including its own, so the child is `p v / (1 - p)` against outside volume `v` (ruling HR-4). In whole units, leftover units go to the earliest slices, so the slices always sum to the order (HR-3). A binary64 value within 1e-12 relative of an integer is taken as that integer before flooring (HR-121).

**Worked example.** `sched_h-0005`: 1,000 units at 20 % against outside volumes 1,000, 2,000 and 4,000 gives 250, 500 and 250 (the last capped by what is left), residual 0. Evidence: hand calculation and a blind re-derivation from the inputs (DR-H2).

### Almgren-Chriss in plain terms

**Plain idea.** Fast trading costs impact; slow trading costs risk. Pick the schedule that minimises expected cost plus a risk aversion times its variance.

**Formal statement.** `exec.ac.trajectory` (`10-execution/almgren-chriss.md`, [AC00] eqs. (5), (8), (16), (17)): holdings `x_j = X sinh(kappa (T - t_j)) / sinh(kappa T)` with `2 (cosh(kappa tau) - 1) = tau^2 lambda sigma^2 / eta_tilde`; `lambda = 0` returns the straight line exactly (HR-5), as does `sigma = 0`, with `kappa = 0` (HR-124).

**Worked example.** On the paper's test parameters, `ac_h-0001` (straight line) costs 662,500 with variance 1.083e12, and `ac_h-0002` (`lambda = 1e-6`) costs 911,226.986 with variance 3.641285721e11. The paper prints `kappa` about 0.6 a day; the exact value is 0.6070761632 (`ac_h-0005`, outside-checked against the printed figure). See the [frontier page](docs/curves/ac-frontier.md).

### Implementation shortfall and its four parts

**Plain idea.** Compare the trade with a paper portfolio that bought everything at the decision price, and split the difference by cause.

**Formal statement.** `exec.tca.shortfall` (`10-execution/tca.md`): delay `s Q (P_0 - P_d)` on the filled quantity, execution `s sum q_i (p_i - P_0)`, opportunity `s (X - Q)(P_c - P_d)`, plus fees (Perold split, HR-8 confirmed by DR-H3). With no fills the whole order is opportunity cost (HR-126).

**Worked example.** `tca_h-0001`: a buy of 1,000 with 800 filled gives delay 80, execution 100, opportunity 200 and fees 5, total 385 or 38.5 bp. Perold's paper was not read; the definition rests on the spec and the blind re-derivation.

### Three ways to model impact, and when each applies

**Plain idea.** Your trading moves the price. How you model that depends on the question.

**Formal statement.** (1) Stage I's quadratic cost in the traded amount, a penalty inside the hedge optimiser (`08-hedging/hedge-costs-and-frontier.md`). (2) The square-root law, `exec.impact.sqrt`, `I = Y sigma sqrt(Q / V)` ([TLD11] eq. (1)), for the average move over an order of a given size; `Y` is an input, labelled assumed (HR-10). (3) Transient impact, `exec.impact.ow_optimal` ([OW13] eq. (31)), where the book refills at rate `rho` and the risk-neutral optimum is a block, a constant rate and a block.

**Worked example.** `imp_h-0001`: 1 % of daily volume at 2 % daily volatility moves the price 20 bp; `imp_h-0002`: four times the size, 40 bp. `imp_h-0004`: on the paper's Fig. 2 parameters each Obizhaeva-Wang block is 23,635.0744504845 of 100,000. See the [impact page](docs/curves/impact-curves.md).

### Order books, queues and why fills are uncertain

**Plain idea.** A limit order waits in a queue at its price. Whether it fills depends on how much is ahead of it and on whether the price moves away first.

**Formal statement.** The simulated lit engine, `exec.sim.lit.run`, keeps a FIFO queue per price level and matches best price first, then by arrival (`10-execution/lit-matching.md`, HR-25 to HR-31). The real book QuantForge records, Kraken's L2 feed, is market by price only, so queue position on the real venue is not observed (`09-microstructure/order-book.md`). `micro.mm.as_quotes` gives inventory-aware quotes ([AS08] eqs. (29), (30)).

**Worked example.** `as_h-0001`: mid 100, long 2 units, `gamma = 0.1`, `sigma = 2`, one unit of time left, `k = 1.5`: reservation price 99.2, spread 1.6907704228. At half the horizon the spreads for three risk aversions match the paper's printed tables to two decimals (`as_h-0005` to `0007`).

### Rebuilding a book from a feed, and counting what went wrong

**Plain idea.** A venue sends a full picture of its book once (a snapshot) and then only the changes (updates). Replaying the changes on the snapshot gives the book at any moment. A feed can drop messages, arrive out of order or show a crossed book, so a rebuild that stopped at the first oddity would be useless over a whole day: it must count every oddity and carry on.

**Formal statement.** `micro.book.rebuild` (`specifications/09-microstructure/order-book.md`, rulings HR-11 to HR-17 and HR-129; venue documentation [KR-BOOK] and [KR-CRC], read 2026-11-17). Prices and quantities are decimal strings (HR-12). An update sets a level's quantity (replace, not add); quantity 0 removes it, and removing a level that is not there is counted in `deletes_of_absent_level`, not refused. After each message each side is cut to the subscribed depth (`truncated_levels`). If the message carries the venue's checksum, the CRC32 of the top 10 levels each side is recomputed and compared (HR-13); a failure is counted in `checksum_failed`, never raised as an error. Best bid above best ask is counted as `crossed`, equal as `locked` (HR-14). A `gap` row (reconnect) clears the book and counts in `gaps`; an update before any snapshot, or after a gap, is ignored and counted until the next snapshot (HR-15). Errors are kept for malformed input: a non-decimal price is `E_SCHEMA`, a negative quantity, a non-positive price or a depth not in Kraken's list is `E_DOMAIN`. The book is market by price only: Kraken's L2 feed does not show individual orders, so queue position on the real venue is not observed.

**Worked example.** `ob_h-0001`: the ten bid and ten ask levels of Kraken's own checksum example give CRC32 3310070434, the value printed in [KR-CRC] (outside-checked against the venue's printed figure). `ob_h-0008`: a snapshot, then a gap row, then an update, then a new snapshot. The gap clears the book (`gaps` 1), the update after it is ignored (event `UPDATE_BEFORE_SNAPSHOT` at message 2) and the final book is the second snapshot alone, bid 90.0 and ask 91.0. Evidence: hand cases; `ob_h` has 10 value cases, 8 of them outside-checked by the venue's printed values or blind re-derivation (80.0 %, `oracle/OUTSIDE_SHARES.md`, item H-2). What a rebuild of the recorded files can claim is limited by how they were recorded: the per-second rows are the recorder's own book, so the H-2 result is stated as the share of seconds on which that book agreed with the venue checksum, not as an independent feed check (`order-book.md`, forms A and B; [Recorded feeds](docs/data/recorded-feeds.md)). Results are labelled "crypto venue; not equities or rates". [Tutorial 41](docs/getting-started/tutorial-41-rebuild-a-book.md).

### The lit matching engine, by hand

**Plain idea.** On a lit venue every resting order is visible. An incoming order trades with the best price on the other side first, and among orders at the same price, the one that arrived first fills first. The order types differ only in what they do when they cannot trade at once: rest, cancel, refuse to trade at all, or hide part of their size.

**Formal statement.** `exec.sim.lit.run` (`specifications/10-execution/lit-matching.md`, HR-25 to HR-31, HR-112, HR-128). Prices are integer ticks and quantities integer lots inside the engine; a price off the tick grid is `E_DOMAIN`. Matching is best price first, then within a price displayed orders by arrival sequence `seq`, then non-displayed pegs by `seq`, then iceberg hidden quantity (HR-27); the trade price is the resting order's price. Order types (HR-25): `LIMIT` trades what it can and rests the rest; `MARKET` trades what it can and cancels the rest; `IOC` likewise at its limit; `FOK` trades in full or is rejected with nothing traded (`FOK_UNFILLABLE`); `POST_ONLY` is rejected if it would trade on arrival (`POST_ONLY_WOULD_CROSS`, HR-26); `ICEBERG` shows `display_qty`, and each refreshed slice joins the back of the queue with a new `seq`; `PEG_MID` and `PEG_PRIMARY` follow the engine's own mid or same-side best, rounded away from crossing (HR-28). Every output carries a conservation record per order (submitted = filled + resting + cancelled + rejected) and the label "simulated venue; not a real exchange". Self-trade prevention is not modelled (one trader id per simulation, stated in the spec).

**Worked example.** `lit_h-0001`: three bids of 10 rest at 100 (B1, B2, B3, in that order) and a sell of 15 at 100 arrives. B1 fills 10 and B2 fills 5; B3 is untouched, and the book shows 15 at 100 (hand case, not blind). `lit_h-0006`: an iceberg I1 for 100 showing 10 rests first, then a limit B2 for 20, then a sell of 15. I1's 10 shown fill first; its next slice of 10 goes to the back of the queue with `seq` 3, so the remaining 5 go to B2, not to I1's hidden size (blind re-derivation matched, `program/STAGE_H_BLIND_WAVE2.md`). Item H-11: 10 of 14 value cases outside-checked by blind re-derivation (71.4 %). The output from the Python build is in the [Cookbook](COOKBOOK.md#replay-an-order-sequence-through-the-engine). [Tutorial 42](docs/getting-started/tutorial-42-match-orders.md).

### Dark pools and the smart order router, simulated

**Plain idea.** In a dark pool nobody sees the resting orders. Buyers and sellers meet at the lit market's midpoint, so both save half the spread, but an order may not trade at all, and the trades it does get tend to come just before the price moves against it. A router decides how much of an order to send at once as a market order and how much to post at each venue. Posting more than needed in total is rational when fills are uncertain, as long as the expected cost of overfilling is smaller than the cost of underfilling.

**Formal statement.** Dark pool, `exec.sim.dark.run` (`specifications/10-execution/dark-pool.md`, HR-32 to HR-36; [GKNV09] and [CST10] read 2026-11-17): at each event, if the lit mid exists and is within both orders' limits, two orders cross at the mid, on the half tick if needed (HR-32); priority is arrival order; a pairing is eligible only if the fill `min(open_a, open_b)` is at least each order's `min_qty` (HR-33, applied per fill); a locked or crossed lit book means no crossing; conditional orders get an invitation and firm up with probability `p_firm` drawn from `core.rng` (HR-34, a stylised version, no venue's rules claimed). Markouts are `side_sign x (mid(t + h) - fill_price) / fill_price` in bp, positive good for us (`exec.sim.dark.markouts`). Router, `exec.sor.allocate` (`smart-order-router.md`, HR-37 to HR-40, HR-129; [CK] arXiv:1210.1625v4, read 2026-11-17): choose integer lots `(M, L_1 .. L_K)` to minimise the sample mean of [CK] eq. (5), `(h + f) M - sum_k (h + r_k - as_k) fill_k + theta (M + sum_k L_k + under) + lambda_u under + lambda_o over`, where a lit fill is `(xi - Q)_+ - (xi - Q - L)_+` for outflow `xi` and queue ahead `Q`, and a dark fill is `min(L, s)` with `s` drawn from the tail `T(s) = P(s_k >= s)` (HR-37). Goldens use the exhaustive integer search with ties to the lexicographically smallest tuple (HR-38, HR-39). Every dark-pool output is labelled "simulated venue; not a real dark pool", and the router is "simulated venues; router scored in simulation only". No real dark-pool data is used; the recorded crypto venue is lit only.

**Worked example.** Dark pool, lit bid 100.00 and ask 100.10, so the mid is 100.05. `dark_h-0001`: buy 100 and sell 60 cross 60 at 100.05; 40 of the buy rests. `dark_h-0002`: the same with a buy `min_qty` of 80, so the only possible fill (60) is too small and nothing trades. `dark_h-0003`: a buy limit of 100.04 is below the mid and waits; when the lit book moves to 100.00 and 100.01 the mid is 100.005 and the 60 cross there, on the half tick. Router, `sor_h-0003` (one lit venue, `S` = 10, queue ahead 2, half spread `h` 0.5, fee `f` 0.3, rebate 0.2, underfill penalty 4, eight equally likely outflows 0, 2, ..., 14): the optimum sends 8 at market and posts 2. In the two scenarios with outflow 0 or 2 the post does not fill, cost `0.8 x 8 + 4 x 2` = 14.4; in the other six it fills, cost `6.4 - 0.7 x 2` = 5.0; the mean is 7.35, expected fill 9.5, P(underfill) 0.25. `sor_h-0005` (a lit venue with no queue and a dark venue, `S` = 4): the optimum posts 4 lit and 3 dark, 7 lots for an order of 4, with expected cost 0 and P(underfill) 0.5, because a lit fill of 0 or 4 and a dark fill of 0 or 3 are equally likely, and overfilling by 3 costs less than the expected saving. `dark_h-0001`, `dark_h-0002` and both router cases were matched by blind re-derivation (`program/STAGE_H_BLIND_WAVE2B.md`); `dark_h-0003` is a hand case only; items H-12 and H-13 are each 3 of 5 value cases outside-checked (60.0 %, `oracle/OUTSIDE_SHARES.md`). The comparison of the router against single-venue routing (10,000 simulated parent orders, seed 20261117) is fixed in the spec before any run and is a simulated result whatever it shows, not a gate (HR-40); no result file for it is in the repository at v0.10.0, so no figure is quoted here. [Tutorial 43](docs/getting-started/tutorial-43-dark-pool-and-routing.md).

### Simulated venues: what a simulator can and cannot tell you

A simulator shows what happens under our rules and our order flow. It can test whether an estimator recovers a rate we planted, and compare two strategies on the same replay. It cannot show how a real venue behaves. The lit engine, the dark pool, the router, the auction, the FX dealer venue, the futures venue and paper trading are simulated only; every venue output carries its label ([Simulators](docs/simulators/README.md)).

### Paper trading: a book that cannot leave the machine

**Plain idea.** Run a trading book exactly as a desk would, with checks, fills, a ledger and a daily P&L, but with every fill from a simulator and no route to any real venue.

**Formal statement.** `specifications/10-execution/paper-trading.md` (HR-42 to HR-55). Positions by average cost (HR-50); daily explain `market + trading + fees + financing = NAV_t - NAV_{t-1}` exactly in decimal, a residual being a defect (HR-53); financing on opening balances, ACT/365, posted half-even to the cent (HR-52); eight pre-trade checks in a fixed order (HR-49); an append-only JSON Lines ledger in which each record carries the SHA-256 of its canonical bytes and of the record before it (HR-45, HR-46). Paper trading is a Python application on the library's four-language operations; its steps are also `paper.*` CLI operations, in all four languages.

**Worked example.** `pt_h-0001` to `0003`: buy 2 at 100, sell 1 at 110, close 105: cash 9909.69, realised 10, day total 14.69; next day close 102 with 3.65 % interest: financing 0.99, total -2.01. `pt_h-0020`: one ORDER record hashes to `72c85984...7e81`, checked with `sha256sum`. Run in [Tutorial 44](docs/getting-started/tutorial-44-paper-trading.md). Fills through the simulated venues come from `paper_fills.py` (Python).

### Estimating a book's rates, with standard errors

**Plain idea.** Arrival, cancel, recovery and impact rates are what a market maker or execution model needs as inputs. Each estimate is useless without a standard error, and an estimator is trusted only after it recovers a value planted in simulated data.

**Formal statement.** `specifications/09-microstructure/micro-estimators.md` (H-4b, HR-70, HR-71, HR-74; available from v0.10.0): Poisson arrival `N / T`, censored exponential cancel `C / sum L`, log-linear resilience and depth decay by OLS with intercept, adverse selection by OLS through the origin, per regime, and a Welch difference for passive against aggressive cost. Acceptance: within 3 SE of the planted value on a fixed seed, at most 4 misses in 200 seeds.

**Worked example.** `mest_h-0008`: signed sizes 1, -1, 2 against mid moves 0.02, -0.01, 0.05 give `lambda_as` 13/600 = 0.0216667 with SE 0.00390868. `mest_h-0009`: the stressed regime's impact is 4 times the calm one's. Evidence: hand calculation checked with mpmath, and a blind re-derivation of all 7 value cases (`program/STAGE_H_BLIND_MICRO.md`). [Tutorial 45](docs/getting-started/tutorial-45-microstructure-estimators.md).

### Markouts: was the fill good or was I picked off?

**Plain idea.** Watch the mid after each fill. A venue whose fills are followed by the price moving against you is costing you more than its fee schedule says.

**Formal statement.** `specifications/10-execution/venue-analytics.md` (H-16, HR-72, HR-73; available from v0.10.0): markout `sum s q (m(t+h) - p) / sum q`, in bp over `sum q p`, toxicity the share of quantity with a negative markout, fill rate filled over sent; sums exact on the printed decimals. VPIN is left out because the source example could not be verified.

**Worked example.** `venue_h-0001` and `0002`: at 5 seconds venue A's markout is 0 and B's 5 bp; at 10 seconds A's is 2.33 bp and B's -2 bp. The ranking flips with the horizon. [Tutorial 46](docs/getting-started/tutorial-46-venue-analytics.md).

### Adaptive algorithms and where the cost went

**Plain idea.** An algorithm that reacts to urgency, the close, visible depth or a second leg still has to add up to the order. Before trading, estimate the cost and, separately, the risk; afterwards, split the cost into causes that sum exactly.

**Formal statement.** `specifications/10-execution/adaptive-algos.md` (H-14, HR-59 to HR-63, HR-67) and `tca-pretrade.md` (H-17, HR-64, HR-65), both available from v0.10.0. Arrival holdings follow [AC00] eq. (17) bucket by bucket; pre-trade impact is the I-star form with parameters as inputs (form recalled from [Kis13], not verified) and timing risk `1e4 sigma sqrt(T/3)`; attribution splits the execution cost of `exec.tca.shortfall` into impact `s sum q_i (m_i - m_0)` and spread `s sum q_i (p_i - m_i)`.

**Worked example.** `alg_h-0002`: 1,000 at `kappa = ln 2` over two buckets is 600 then 400. `tcx_h-0001`: 3.04 bp expected cost against 46.2 bp of timing risk. `tcx_h-0006`: the `tca_h-0001` buy, execution 100 split into impact 60 and spread 40, total 385. Evidence: a second lane re-derived all 36 cases blind, 0 value mismatches. [Tutorial 47](docs/getting-started/tutorial-47-adaptive-algos-and-tca.md).

### Latency targets written before measuring

**Plain idea.** A latency figure is a claim about one machine, one workload and one method. Fix the targets first, publish the machine, and report a miss as a miss.

**Formal statement.** `specifications/09-microstructure/low-latency-book.md` and `low-latency-targets.md` (H-9, HR-18 to HR-24): same answers as `micro.book.rebuild`, one pinned thread, per-message monotonic clock, clock cost published and not subtracted, zero heap allocations after warm-up in C++ and Rust.

**Worked example.** The first run (laptop under WSL, not the acceptance machine; workload S, 9,000,000 timed messages): update p50 39 ns (C++) and 47 ns (Rust) against a 150 ns target, p99.9 264 and 242 against 5,000; Rust `best_bid` p99 105 ns misses its 50 ns target, as does C++ `qty_at` present at 120 against 100. Queries were timed singly near the clock's own 15 to 17 ns; batch timing came in a later session (`benchmarks/results/h9/README.md`). Workload R, the recorded Kraken window 2026-11-18 21:49:17 to 2026-11-19 03:49:17 UTC, is a timing MISS with correctness passing: 0 mismatches, but p99 and p99.9 miss in every language (C++ BTC/USD p99 9,223 ns against 500; figures are the median of 5 runs). A per-level figure of about 40 ns is descriptive only and has no target. Available from v0.10.0. [Tutorial 48](docs/getting-started/tutorial-48-low-latency-book.md).

### Trading conventions: equities, FX and rates

**Plain idea.** Before a model or a venue can run, a price has to sit on the right grid, a trade has to settle on the right day and a quote has to be read the way the desk writes it. These are conventions, not models: each has one right answer, fixed by a rule or by market practice.

**Formal statement.** `specifications/09-microstructure/asset-conventions.md` (H-22 to H-24, rulings HR-80 to HR-120). Equities: `micro.eq.round_price` rounds a buy down and a sell up to the tick (0.0001 below 1.00, 0.01 above, 0.005 on the half-penny tier); `micro.eq.fee_check` tests an access fee against the cap; `micro.eq.round_lot` gives 100, 40, 10 or 1 shares by price; `micro.eq.settle_date` is T+1 on a supplied calendar. FX: `micro.fx.pip_value` is notional times the pip (0.0001, or 0.01 with JPY as quote currency); `micro.fx.spot_date` is T+2 good days, T+1 for USDCAD. Rates: `micro.rates.parse_32nds` reads `H-FF[q]` as `H + (FF + q)/32` with the third digit in quarters of a 32nd (0, 2, 5, 7 only; eighth-tick contracts such as 2-year and 3-year notes are not supported, HR-118); `micro.rates.bond_price`, `.bond_yield` and `.bill_price` are the street formulas on a coupon date. Compliance dates are per rule (HR-120): the amended tick table (Rule 612) and fee cap (Rule 610(c)) have the default `compliance_date` 2027-11-01, deferred by SEC order 34-105656; the round lot (Rule 600(b)(93)) has 2025-11-03. With no `as_of` an operation applies the amended text. The amended tick and fee rules are not in force before 2027-11-01, so pass `as_of` to get the rule in force on a date.

**Worked example.** `eqc_h-0001` and `0002`: a buy at 10.005 rounds to 10.00 and a sell to 10.01. `eqc_h-0020` and `0022`: the half-penny tier is `E_INPUT` with `as_of` 2026-11-19 and allowed from 2027-11-01. `eqc_h-0023`: a fee of 0.0015 at a price of 20 passes on 2026-11-19 (cap 0.003) and fails with no `as_of` (cap 0.001, `eqc_h-0011`). `fxc_h-0004`: EURUSD traded on 2026-11-24 with a USD holiday on the 26th has spot 2026-11-27. `rtc_h-0003`: 99-162 is 99.5078125. Evidence: hand calculation and blind re-derivation; outside shares H-22 66.7 %, H-23 71.4 %, H-24 94.7 % (`oracle/OUTSIDE_SHARES.md`). Sources read are listed in the spec; USDCAD T+1 is market convention with no primary source read (HR-119). [Tutorial 49](docs/getting-started/tutorial-49-trading-conventions.md).

### Three more simulated venues: an auction, an FX dealer and a futures venue

**Plain idea.** Different asset classes trade in different ways. Equities open and close with an auction at one price. FX clients ask a dealer, who may refuse after a last look at the market. Treasury futures trade in a central order book, in ticks. Each is simulated here; none is a real venue.

**Formal statement.** `exec.sim.auction.uncross` (`10-execution/auction.md`, HR-84, HR-127) picks the tick with the largest matched volume, breaks ties by smallest imbalance and then by the `tie_break` rules, and fills everyone at that price; with no cross there is no auction. The lit engine runs the same uncross at the open and the close when it is given a `session` and `PHASE` events (HR-112). `exec.sim.fx.stream` and `exec.sim.fx.request` (`fx-rfq-venue.md`, HR-97) quote around a mid and apply last look: reject `LL_PRICE` if the mid moved more than `threshold_pips` against the dealer, else reject `LL_RANDOM` if a draw is below `p_random_reject`, else fill at the quote. `exec.sim.fut.run` (`rates-futures-venue.md`, HR-90 to HR-92) is the lit engine in integer ticks with prices in 32nds, with fees and a P&L per trader, open positions marked at the last trade. Every output carries its label, for example "simulated venue; not a real exchange; no real FX data" (HR-94, HR-111).

**Worked example.** `auc_h-0001`: six orders uncross at 10.01 for 300 shares with an imbalance of -100. `fxv_h-0004` and `0003`: a 1-pip move fills at 1.0852; a 4-pip move is `LL_PRICE`. `fut_h-0011`: on ZN, trader P buys 3 at 110-16 and sells 3 at 110-17+ for 140.625 less 6 in fees, 134.625; the three traders' figures sum to -12, the fees. `fut_h-0011` to `0016` were added on 2026-11-19, when `exec.sim.fut.run` had unit tests but no shared golden. The last-look thresholds and the random reject are the spec's own toy model, not taken from the FX Global Code (HR-119). [Tutorial 50](docs/getting-started/tutorial-50-auction-fx-and-futures-venues.md).

### When two inputs are wrong: one order of checks

**Plain idea.** A request can break two rules at once. Four builds that each check in their own order would return different error codes for the same input, and conformance would not notice unless a golden had two faults.

**Formal statement.** HR-122 (`specifications/stage-h-rulings-audit.md`; `cli-contract.md`, "Finite rule"), for the stage H operations: `E_SCHEMA`; then `E_LIMIT` for a size limit on the input itself; then a non-finite Real, `E_DOMAIN`; then structural `E_INPUT` (an empty list, a count below 1, lengths, cross-field consistency); then `E_DOMAIN` for one value outside its domain. A limit that arises only after validation is last. A related rule, HR-121: a binary64 value within 1e-12 relative of an integer is that integer before a floor, so whole-unit rounding does not lose a unit to representation error.

**Worked example.** `rule_h-0016`: Almgren-Chriss with `n_steps` 0 and `sigma` -1 is `E_INPUT`. Before 2026-11-19 Python and Rust answered `E_DOMAIN` and Java and C++ `E_INPUT`. `rule_h-0012`: TWAP with quantity -5 and 200,000 buckets is `E_LIMIT`, the limit before the structural check. `rule_h-0003`: a cash-balanced pair with leg prices 0.3 and 0.2 gives 2 units of leg B; `0.3 / 0.2` lands just below 1.5 in binary64 and gave 1 before the fix. Evidence: suite `rule_h`, 40 cases (11 value, 29 error), passing in all four builds.

### How stage H was checked: blind re-derivation and a different-model audit

**Plain idea.** No free library implements these formulas or venues, so there is nothing outside to compare with. Two substitutes were used. In a blind re-derivation a second lane gets the rules and the inputs but not the answers, works the answers out, and the two sets are compared. In the audit a different model reads the specs and code looking for faults, without seeing the goldens.

**Formal statement.** Blind re-derivation (decision DR-H2): a case counts as outside-checked only if the blind lane saw neither the expected value nor anything that leaks it, and every compared output matches; a shape-only match does not count. The audit (plan rule 14.10-5; Claude Opus 5.5, read-only, no view of goldens, oracle or tests) reported 0 Critical, 17 Major and 15 Minor findings. Each was reproduced on the four builds, and all 32 are ruled (HR-121 to HR-129 and the closing notes in `specifications/stage-h-rulings-audit.md`). Three code faults were fixed, each in all four builds: the Almgren-Chriss error code with two faults at once, the POV check order, and the pair leg rounding at an exact half. Both methods are self-assessment: there is no second human review (owner decision 2026-11-18).

**Worked example.** Stage H has 412 golden cases, 205 of them value cases, and 160 of those (78.0 %) are outside-checked by blind re-derivation or a figure printed in a paper; none by a library (`oracle/OUTSIDE_SHARES.md`). The limit of the method showed on 2026-11-19. The blind lane reads the same rules as the first lane, so it catches arithmetic and convention slips but not a wrong rule. Until that day the spec said the amended SEC tick and fee rules applied from 2025-11-03, and all four builds followed it. The date was wrong: the SEC had deferred it to 2027-11-01. A blind lane given that spec text derives the same wrong answer, so the fault was found by reading the SEC order, not by re-derivation (HR-120). The eight goldens added at both sides of each date are checked the same way, against the corrected text.

### What stage H's evidence does and does not show

- Crypto venue only for real data, and lit only: one venue's L2 book, recorded locally, aggregates published ([Recorded feeds](docs/data/recorded-feeds.md)). Not equities or rates.
- No live orders, ever. Paper trading (H-21) uses simulated fills.
- Dark pools and multi-venue routing are simulated; no real dark-pool data is used. The auction, the FX dealer venue and the Treasury futures venue are simulated too: no real equity, FX or rates data is used.
- Validation is self-assessment. 160 of 205 value cases (78.0 %) are outside-checked by blind re-derivation or a printed paper figure, none by a library; a blind lane cannot catch a wrong rule.
- H-9 workload R timing is a miss, recorded as a miss; all H-9 figures are from a laptop under WSL, not the acceptance machine.
- The formula goldens check arithmetic and the papers' printed figures. They do not show that any market follows these models; that needs the crypto study's estimates with standard errors.

## Stage K: risk platform and capital (in progress)

Stage K round 1 is **merged to main 2026-11-20 (pull requests #58 and #59), not tagged; released with v1.0.0** (the last tag is v0.10.0); the different-model audits are answered (open items: [`docs/known-issues.md`](docs/known-issues.md)); each claim names the file it comes from. Status words: every round 1 operation (wave 1, the K-8 method, SA-CCR and the FRTB backtesting operations) is implemented and registered in all four builds (CLI contract 1.17.0); the daily paper ledger and the daily curve run are scheduled on main since 2026-11-20 (pull request #59; rulings KR-200 to KR-214, KR-254, KR-255 confirmed). Outside shares per item are generated by `tools/outside_shares.py` into `oracle/OUTSIDE_SHARES.md`; the stage K share is <!-- generated:stage-k-total -->97 of 123 value cases (78.9%)<!-- /generated --> under ruling KR-250 (audit finding KA-C18, closed), which counts a figure printed in the regulator text only through a blind packet. [Tutorials 51 to 58](docs/getting-started/README.md#stage-k-in-progress) work one example of each, and question bank [set 14](docs/question-bank/14-stage-k-risk-platform.md) tests them. The 60% outside-check rule and the per-item shares are on the [status ladder page](docs/validation/status-ladder.md).

### What did we know, and when: the bitemporal store

**Plain idea.** A stored number has two times: the period it describes and the moment we learned it. Keeping both, and never overwriting, lets a report be rerun exactly as it was first produced, even after corrections.

**Formal statement.** `core.store.bitemporal_query` (`specifications/01-core/bitemporal-store.md` 1.0.0, rulings KR-2 to KR-4, KR-16). For a query at knowledge `K` and valid instant `V`, take the records known by `K` whose `[valid_from, valid_to)` contains `V`; the one with the largest `sequence` wins; a deletion gives `WITHDRAWN`, none gives `NONE`. Acceptance property KR-4: appending a record learned after `K` changes no answer as of `K`.

**Worked example.** On the shared golden log, February reads 100 when asked in mid-March and 105 when asked on 1 April, because the correction was learned on 1 April (`bt_k-0001`, `bt_k-0002`). Evidence: 10,000 generated logs and 500,000 query pairs, zero failures, Python and Java (`program/stage_k_w1/acceptance_python.json`, key `kr4_correction_property`; C++ and Rust run the same property in their unit tests); 6 of 8 value cases blind-checked (`oracle/OUTSIDE_SHARES.md`). The operation reads a log passed in the request; there is no persistent store. [Tutorial 51](docs/getting-started/tutorial-51-bitemporal-store.md).

### Rebuild only what a quote touches: incremental curve update

**Plain idea.** In a sequential bootstrap a quote cannot move a pillar before its own maturity, so after a tick only the later pillars need solving; the shortcut must equal a full rebuild bit for bit and refuse a stale cache.

**Formal statement.** `curve.bootstrap.par_annual` and `curve.incremental.update` (`specifications/02-curves/incremental-update.md` 1.0.0, KR-5): annual par swaps, `P_k = (1 - S_k sum_{i<k} P_i)/(1 + S_k)`; pillars before the first changed index are copied; a cache that is not the bootstrap of its quotes bit for bit is `E_INPUT`.

**Worked example.** Quotes 2%, 2.5%, 3% give 0.980392, 0.951698, 0.914599; moving the 2-year quote to 2.6% copies the first pillar and recomputes two, ending at 0.914654 (`inc_k-0001`, `inc_k-0002`). Evidence: 10,000 random vectors bit-identical to a full rebuild (key `incremental_property`); on the stage B production bootstrap, an incremental path in all four builds patches 10,000 of 10,000 moves bit-identically to a full rebuild (key `incremental_property_stage_b_patched`, `program/STAGE_K_W1_HANDOVER.md`). [Tutorial 52](docs/getting-started/tutorial-52-incremental-curve-update.md).

### When to recalibrate: triggers with a stated false-alarm rate

**Plain idea.** Recalibrate only when an input has moved further since the last calibration than its normal day-to-day noise explains, at a false-alarm rate chosen in advance.

**Formal statement.** `calib.trigger.check` (`specifications/03-calibration/recalibration-triggers.md` 1.1.0, KR-6, KR-13, KR-232, KR-233): fire iff `|x_now - x_ref| > k sigma sqrt(d)`, `sigma` the sample standard deviation of past one-day changes. `false_alarm_rate` is `P(abs(T_(n-1)) > k)`, the rate with `sigma` estimated from `n` changes; `nominal_rate` is `2 (1 - Phi(k))`, the rate if `sigma` were known. Equality does not fire. A window with binary64 `sigma` at most `2^-26 max abs(c_i)` is `E_DOMAIN`.

**Worked example.** Changes `+1, -1, +1, -1` give `sigma = 1.1547`; at `k = 3` a move of 5 fires on day 1 and not on day 4, when the threshold is 6.928 (`trig_k-0001`, `trig_k-0003`); `false_alarm_rate` 0.0577 there against `nominal_rate` 0.0027, because four changes give a noisy `sigma`. The different-model audit measured 22,977 fires in 400,000 noise paths at n = 4, k = 3 (KA-A4, measured), which the 1.0.0 output (0.0027) did not predict; the 1.0.0 simulation at a window of 250 could not see it. Evidence for 1.1.0: simulations at n = 2, 4, 30 and 250 against the operation's own rate (spec acceptance, `python/tests/test_stage_k_audit_a.py`). `nominal_rate` is computed as `2 Phi(-k)` with a tail-accurate normal CDF, checked in the far tail by `trig_k-0009` (k = 30); outside shares in `oracle/OUTSIDE_SHARES.md`. CUSUM and EWMA are out of wave 1. [Tutorial 53](docs/getting-started/tutorial-53-recalibration-triggers.md).

### A fast risk number with an error bound

**Plain idea.** Delta and gamma give a fast P&L estimate for a market move; for smooth instruments Taylor's theorem bounds how wrong it can be, so the estimate can be shown with a guarantee.

**Formal statement.** `risk.intraday.delta_gamma_bound` (`specifications/06-risk/intraday-risk-bounds.md` 1.1.0, KR-7, KR-10, KR-15, KR-17, KR-234): estimate `V' h + V'' h^2/2`; bound = the Lagrange term `M3 |h|^3 / 6`, `M3 = T^3 |N| exp(-T min(y, y + h))` for a zero-coupon position, plus a binary64 rounding allowance (KR-234), so that the bound also holds for moves below about 1e-7, where the audit found the 1.0.0 bound exceeded by a factor of 21.6 at 1e-9 (KA-A6, measured); book bounds summed without netting. Label: "latency-aware analytics on simulated data".

**Worked example.** 1,000,000 at 5 years, 4%, shift +1%: estimate -39,913.12, exact -39,929.97, bound 17.06, error over bound 0.988 (`idr_k-0001`). Evidence: 1,000 seeded moves on a 50-position book, zero violations in Python and Java, rechecked at 50 digits by our own oracle (`oracle/IDR_K_MOVES_CHECK_W1.json`). The KR-234 bound differs from the 1.0.0 one by at most 1.7e-10 relative on these cases (KR-239), which still prints as 17.06. Outside check: the 1.0.0 blind match (5 of 5) no longer covers the changed bound; the version 2 blind packet matched 9 of 11 (all 11 bounds; the estimates of the two cancelling books idr_k-0012 and -0013 differ at 5.4e-05 and 3.3e-07 relative because on a cancelling book the binary64 result depends on the order of operations; recorded as mismatches, `program/STAGE_K_BLIND_K5A_V2.md`). Zero-coupon positions only. [Tutorial 54](docs/getting-started/tutorial-54-intraday-risk-bounds.md).

### The Bermudan ladder at the default grid: why second order was lost (K-8)

**Plain idea.** A ladder is only usable if its error shrinks regularly as the grid is refined. The first stage K method did not: a curve node inside a time step gave a first-order error, and the exercise smoothing left an error that depended on where the exercise boundary sat in its cell, so the ladder's error changed sign from grid to grid. The fixed method removes the curve from the time stepping and replaces the smoothing.

**Formal statement.** `CN_RANNACHER_SMOOTHED` on `rates.shortrate.bermudan_ladder` and `bermudan_swaption` (`specifications/06-risk/bermudan-ladder-k8.md` 0.2.0, PROPOSED, KR-8, KR-9, KR-18, KR-19, KR-113): the scheme carries `U = V exp(-int alpha)` with a time-independent operator; Crank-Nicolson with implicit half steps at the start of each interval (Rannacher start-up); at each exercise date a hat-weighted smoothing of the `max` with an end correction and a `1 - delta^2/6` stencil. Richardson extrapolation only through `num.richardson.check`.

**Worked example.** Case `aadladder_g-0001`, row 2 on 201/401/801 grids: 222,756.98, 223,121.25, 223,212.48, observed order 1.997, and 0.218% from the QuantLib reference at the default grid. Evidence (`oracle/K8_ACCEPTANCE_W2.json`): acceptance 1, 2 (worst 0.40% against 1%) and 3 (24 entries, orders 1.84 to 2.15) pass in Python; acceptance 3 also in Java, C++ and Rust (`oracle/K8_ACCEPTANCE_PORTS.json`); 7 of 7 value cases blind re-derived (`program/STAGE_K_BLIND_K8.md`). The diagnosis is in `program/K8_DIAGNOSIS.md`; the first run's miss is kept in `oracle/K8_ACCEPTANCE_W1.json`. All of that is on the three cases the method was developed on (in-sample) and at 201/100. At 101/50 the worst judged entries on the same cases are +0.93%, -1.53% and +1.49%, and a deep in-the-money receiver is 7% to 9% off on d/da at 201/100 (`program/k8_audit_response/`). **The R6 use restriction stays for both methods (KR-113, 2026-11-19; a lift under KR-110 was withdrawn before release); lifting it needs an out-of-sample acceptance fixed before any run.** The 0.4986-year row is not judged (owner decision 2026-11-19): `program/K8_ROW0_FINDING.md` found no bug, its true value is zero, and QuantLib's -14.27 there is that engine's own time-stepping error. [Tutorial 55](docs/getting-started/tutorial-55-bermudan-ladder-convergence.md).

### Counterparty exposure by the regulator's recipe: SA-CCR

**Plain idea.** Exposure at default is replacement cost now plus a supervisory estimate of how far the exposure could grow, times 1.4; netting rules decide how much opposite trades offset.

**Formal statement.** `risk.saccr.ead` (`specifications/06-risk/sa-ccr.md` 0.1.0, KR-30 to KR-39; CRE52 read 2026-11-19): adjusted notional, maturity factor, supervisory delta, effective notional, hedging sets with the regulator's aggregation formulas, add-on, multiplier, `EAD = 1.4 (RC + PFE)`.

**Worked example.** Basel CRE99 Example 1: two USD swaps offset in adjacent buckets to an effective notional of 59,270 from 114,948 gross; with the EUR swaption the add-on is 346.76, RC 60, `EAD = 1.4 x 406.76 = 569.47`, printed 569 (`saccr_k-0001`). Evidence: the five published Basel examples reproduce; outside share 12 of 19 value cases (63.2%, `oracle/OUTSIDE_SHARES.md`): the 5 published examples through the blind packet that re-derived them (`program/STAGE_K_BLIND_PUB.md`; a printed figure alone does not count, KR-250) plus 7 blind, with 4 blind matches excluded for a process failure (`program/STAGE_K_BLIND_W1B.md`) and the three audit cases saccr_k-0040 to 0042 not blind-checked. All four builds. [Tutorial 56](docs/getting-started/tutorial-56-sa-ccr-example-1.md).

### The backtesting traffic light and desk limits

**Plain idea.** Count the days a model's 99% VaR was beaten; a correct model is beaten about 2.5 days in 250, and the binomial distribution says how many is too many.

**Formal statement.** `risk.frtb.backtest.zone`, `.desk`, `.count` (`specifications/06-risk/frtb-ima-backtest.md` 0.1.0, KR-40 to KR-47; MAR32 and MAR99 read 2026-11-19): amber from the first count whose binomial cumulative probability reaches 95%, red from 99.99%; the count is the greater of actual and hypothetical; multiplier 1.50 to 2.00 at 250 days; a desk with more than 12 exceptions at 99% or more than 30 at 97.5% loses model approval.

**Worked example.** At 250 days `P(X <= 4) = 89.22%` and `P(X <= 5) = 95.88%`, so amber from 5; red from 10. 3 actual and 5 hypothetical exceptions: amber, multiplier 1.70. Evidence: MAR99 Table 2 matches for the new and the existing stage F operation; every value within 1e-12 of SciPy's binomial cdf (not counted, D6 precedent). Outside share 23 of 28 (`oracle/OUTSIDE_SHARES.md`, generated): the 12 MAR99 Table 2 cases re-derived blind (`program/STAGE_K_BLIND_PUB.md`; the printed figure alone does not count, KR-250) and 11 blind re-derivations (`program/STAGE_K_BLIND_BTK.md`). All four builds. `risk.frtb.backtest.zone` takes Integers only and is exempt from the E1 gate under ruling KR-112 (`program/STAGE_K_E1_ZONE_DECISION.md`). [Tutorial 57](docs/getting-started/tutorial-57-backtesting-traffic-light.md).

### A daily paper ledger that anyone can check

**Plain idea.** Each business day a job marks four made-up constant-maturity Treasury exposures on the recorded par curve, sends one fixed-rule order to a simulated venue and writes one hash-chained row; the P&L explain must close exactly, and anyone with the ledger alone can replay it.

**Formal statement.** `tools/paper_daily/` and `specifications/12-platform/paper-ledger-daily.md` 0.1.0 (KR-70 to KR-89, confirmed 2026-11-19; the audit rulings KR-200 to KR-214 are proposed). Label on every row: "paper marks on a fitted curve; not tradable". Explain: carry + roll-down + curve move + fills and costs, unexplained exactly 0 by construction (a bookkeeping test, not a model test). Verification order: chain, configuration, dates and holdout windows, exact replay from the ledger alone, CLI rebuild, the recorder source check, anchors and the 20-day gate. A day counts only from a Bitcoin block time, two hours before its cut-off (KR-200 to KR-202, proposed); the row's own on-time label is declared, not counted.

**Worked example.** The spec's synthetic worked day: carry 1,213.9355, roll-down 16.5625, curve move -1,993.7275, fills and costs -124.21875; NAV change -887.44825; unexplained 0. **Scheduled on main since 2026-11-20 (pull request #59); 0 of 20 recorded trading days as of 2026-11-20 13:00 UTC, before the first scheduled run.** v1.0.0 does not wait for 20 days (owner decision 2026-11-20): the threshold is unchanged, and at the tag K-2 is stated "not met: N of 20 recorded trading days". No performance claim is made: the rule ignores the market, fills are simulated and the pre-trade estimate uses placeholder weights. [Tutorial 58](docs/getting-started/tutorial-58-daily-paper-ledger.md).

### Checking without an outside library: blind re-derivation

**Plain idea.** Most stage K items have no free library that computes them. A second lane, a different model, gets the rules and the inputs but not the answers, works the answers out, freezes them with a hash, and only then is a script run to compare.

**Formal statement.** Decision DR-H2 (`program/STAGE_H_BLIND_LANE.md`): the packet is the spec with every expected value, derivation and worked example stripped by a script; the blind lane works outside the repository with no repo imports; a case counts only if no output fact leaked to the lane and every compared output matches at the golden's tolerance. The [diagram](docs/diagrams/README.md#blind-re-derivation-packet-deriver-compare) shows the steps.

**Worked example.** Wave 1: 38 of 38 cases matched, 36 fully blind; per item K-4a 6 of 8, K-4b 4 of 4, K-4c 4 of 5, K-8 guard 6 of 6, K-5a 0 of 5 (`program/STAGE_K_BLIND_W1.md`). Later packets: K-5a 5 of 5 (`program/STAGE_K_BLIND_K5A.md`), the K-8 method 7 of 7 (`program/STAGE_K_BLIND_K8.md`), FRTB backtesting 12 of 12 matched and 11 counted (`program/STAGE_K_BLIND_BTK.md`; `btk_k-0017` is not counted because the rules text states its answer). SA-CCR: 11 of 11 matched, 7 counted, 4 excluded because the lane had once read the unstripped spec (`program/STAGE_K_BLIND_W1B.md`). Wave 2 (DRC and RRAO, IMA, CVA capital, leverage and large exposures): specified and blind-checked, not implemented; the blind lane matched 58 of 58 and 57 were counted (`program/STAGE_K_BLIND_W2.md`), but the goldens are not on the branch, so nothing is counted in `oracle/OUTSIDE_SHARES.md` (`program/STAGE_K_W2_GATE.md`). A blind lane reads the same rules, so it catches arithmetic and convention slips, not a wrong rule.

### What stage K's evidence does and does not show, so far

- Stage K round 1 is merged to main 2026-11-20 (pull requests #58 and #59), not tagged; it is released with v1.0.0. Every figure above names its file.
- The 60% outside-check rule per item (`oracle/OUTSIDE_SHARES.md`; the list is generated by `tools/outside_shares.py`): <!-- generated:stage-k-items -->K-4a 6 of 10 (60.0%), K-4b 4 of 6 (66.7%), K-4c 13 of 14 (92.9%), K-5a 9 of 12 (75.0%), K-8 method 7 of 7 (100.0%), K-8 guard 6 of 6 (100.0%), K-8d SA-CCR 12 of 19 (63.2%), K-8e FRTB backtesting 23 of 28 (82.1%), `tlk_k` 17 of 21 (81.0%); every item meets the 60% per-item rule<!-- /generated -->. A blind match shows the rules are unambiguous and the arithmetic right, not that the rules read the source correctly.
- The wave 1 property tests write evidence files in Python and Java; C++ and Rust run the same properties in their unit tests.
- K-8: the use restriction stays for both methods (KR-113); `CN_RANNACHER_SMOOTHED` is second order on three in-sample cases at 201/100 and misses 1% at 101/50 on two of them.
- The E1 gate was refined for `risk.frtb.backtest.zone` by ruling KR-112 (owner decision 2026-11-19): an exempt Integer-only operation may carry a Real input only in a golden that expects `E_SCHEMA` (`program/STAGE_K_E1_ZONE_DECISION.md`).
- The paper ledger has 0 of 20 recorded days, is not yet running and makes no performance claim. The daily curve run's consistency check against the Fed's fitted curve is a recorded miss on the one real day tried (2026-11-13: RMSE 17.36 bp against 15 bp; `program/STAGE_K_CURVE_DAILY_HANDOVER.md`); it is a consistency check, not proof.
- The sensitivity-based initial margin (`sbim`, K-8h), when built, runs on placeholder weights from a stated rule, and no published number can check it (`program/STAGE_K_W2_GATE.md`); the stage G margin goldens use the same rule on main since 2026-11-20 (KR-150; released with v1.0.0).
- H-9 R2 not yet run: on 2026-11-19 four recording sessions were cut short by network drops, the longest 3 h 20 min; targets and rules were fixed before any timing (HR-130 to HR-134); the measurement uses the first 6-hour session that completes; the 2026-11-19 workload R result remains a recorded MISS.

## Appendix: stage history

The order things were built, with each stage's own summary. The topics above reuse these stages' worked examples. The [tutorial index](docs/getting-started/README.md) has a Stage column: stage B is tutorial 1; C is 3 and 5; D is 2, 4, 8, 9, 10 and 11; E is 3, 9, 12 and 13; F is 5, 8, 14 and 15; G is 5, 6, 7, 12, 15 and 16; I is 17 to 21; R6 is 22; J is 23 to 35; H is 36 to 50.

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

**Status: built, target v0.4.** Implemented. At merge `95cbf11` on 2026-11-07, each of the four implementations passed 5,514 of 5,514 golden cases (value-checked and error cases counted together) locally, 331 of them in stage D's 20 suites (`conformance/README.md`). `specifications/stage-d-handover.md` lists every stage D spec; rulings D1 to D64 are in `specifications/stage-d-rulings.md`.

### R2: Risk

Phase R2 (target v0.4.2) added `risk.curve.par`, `risk.curve.key_rate`, `risk.curve.jacobian` and `risk.pnl.explain`. Its topics are under [Risk, hedging and use cases](#risk-hedging-and-use-cases).

### Stage E: full volatility, exotics, rates vol, correlation and credit (v0.5.0)

**What was built.** Eight slices: arbitrage-free SVI surfaces with local and forward vol (E1), the Heston family and SLV (E2), FX smile conventions (E3), rates and inflation vol (E4), exotics and American options (E5), correlation (E6), GARCH, variance swaps and a VIX-style index (E7), and CDS options, copulas and the large-pool model (E8). Two spec sessions wrote the specs and goldens in parallel; rulings are E-A1 to E-A40 (`specifications/stage-e-rulings.md`) and E-B1 to E-B40 (`specifications/stage-e-rulings-b.md`), and each language was built from the specs alone.

**Status: implemented in all four languages.** At the stage E merge, `597abf2` (2026-11-08), the golden set holds 6,817 cases (value-checked and error cases counted together) in 91 suite files (counted from `datasets/golden/`). C++, Java and Rust each reported 6,817 of 6,817 passing in their final stage E commits (`5af077d`, `a9cd195`, `141245d`; *reported*). Python passed 6,817 of 6,817 through the neutral runner on the merged tree, built from `597abf2` (*observed*, local, Windows, 2026-11-08). Outside oracle under plan rule 11.2.5, counting a case only if every output is a QuantLib 1.44 value (rulings E-A17, E-B28): 557 of the 895 stage E cases, 62.2% (spec A 280 of 446 in `oracle/outside_register_e_a.json`, spec B 277 of 449 in `oracle/outside_register_e_b.json`; *outside-checked*). All inputs are synthetic, and no model is Validated (`docs/model-inventory.md`).
