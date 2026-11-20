# Glossary

Terms are listed under the stage that first needed them. The [Curves gallery](docs/curves/README.md) shows most stage B terms on real output.

## Stage A: Foundation

| Term | Meaning |
|---|---|
| As-of view | What was known at a given instant |
| Batch mode | Running many cases through one CLI process, one JSON document per line in and one result line out, each equal to what `run` gives (`specifications/cli-contract.md`, 1.6.0) |
| Bitemporal | Tracking both when something happened and when it became known |
| Business-day convention | How a date that falls on a holiday moves |
| Canonical form | The one byte spelling of a document, used for hashing |
| Clean room | Writing an implementation from the spec alone, unable to see the other three |
| Compounding | How interest is reinvested: simple, periodic, continuous |
| Conformance | An implementation matching golden cases within tolerance |
| COS method | Option pricing from a characteristic function, by cosine series |
| Crossed quote | Bid above ask |
| Day count | The rule that turns two dates into a year fraction |
| Discount factor | The value today of one unit paid later |
| Evidence class | How a claim is backed: analytic, simulated, proxy or observed |
| Forward log | An append-only, hash-chained record of dated entries |
| Honest ceiling | What free public data can show (correct pricing and risk, curve quality, honest statistics) and what it cannot (tradable profitability) |
| Golden case | A stored case with an independently obtained expected result |
| Golden suite | A file of golden cases on one topic, such as `daycount` |
| Jacobian | Dimensionless sensitivity of each bootstrapped zero rate to each par quote (bp of zero per bp of quote); lower triangular for a bootstrap (`risk.curve.jacobian`) |
| Key-rate risk | Value change per 1 bp shift of the zero curve around one maturity: a triangular tent around a key date, or a bump of one curve pillar |
| Knowledge time | The instant the store learned a value |
| Locked quote | Bid equal to ask |
| Method test | A test on synthetic data, proving a method and not market accuracy |
| Monotone convex | Forward-rate interpolation that reprices all inputs (Hagan and West) |
| Oracle | The source of expected results, separate from the implementations |
| P&L explain | The daily check that risk times the market move matches full revaluation, within a stated unexplained threshold (`risk.pnl.explain`) |
| Par risk | Value change per 1 bp move in a market par quote, with the curve rebuilt (`risk.curve.par`) |
| Rannacher start-up | Implicit half steps that damp a payoff kink before Crank-Nicolson |
| Ruling | A recorded decision on a point a spec left silent, in `rulings.md` or `stage-b-rulings.md` |
| Snapshot | A frozen, hashed document of everything a calculation read |
| Sobol sequence | Deterministic points that fill a cube evenly |
| Tension spline | A spline with a parameter pulling it towards straight lines |
| Tolerance class | A named, justified comparison rule |

## Stage B: FX and rates slices

| Term | Meaning |
|---|---|
| Basis point | 0.0001 |
| Bootstrap | Solving a curve so that each input quote reprices |
| DV01 | Change in PV for rates up 1 bp, signed, by bumping quotes and rebuilding the curve |
| Forward points | The forward minus spot, in pips |
| FRA | Forward rate agreement: one fixed-against-floating payment on a future period |
| Key-rate DV01 | The same change for one quote at a time, showing where on the curve risk sits |
| OIS | Overnight indexed swap: fixed against a compounded overnight rate such as SONIA or SOFR |
| Par rate | The fixed rate that makes a swap worth zero |
| Pillar | A dated node of a curve, holding a solved discount factor |
| Projection curve | A curve that forecasts floating rates, while another curve discounts |
| Quote-driven basis | The gap between the FX-implied base rate and the base OIS rate, taken straight from quotes |
| Zero rate | The continuously compounded rate from today to a date: `-ln(D)/t` |

## Stage C: Equity vol slice

| Term | Meaning |
|---|---|
| Arbitrage-free SABR | SABR prices from a one-dimensional forward equation for the density, absorbing at zero, so density cannot go negative (Hagan and others, 2014) |
| Bachelier model | Option model with a normally distributed forward; vol is in price units |
| Black-76 | Option model with a lognormal forward; Black-Scholes is Black-76 with the forward taken from spot |
| Borrow curve | Discount factors `B` for the fee earned by lending the stock out |
| Carry factor | `C = D/B`: grows the stock and carries dividends to expiry (ruling C2) |
| Delta convention | Whether a quoted delta is spot delta, with a discount factor, or forward delta, without one |
| Greeks | Slopes of a price: delta, gamma, vega, theta, rho, vanna, volga |
| Implied vol | The vol at which a model reprices a given option price |
| Risk reversal, butterfly | Quotes of the call-put vol gap, and of the wings over ATM, at one delta |
| SABR | Model in which the forward's vol is itself random; Hagan's 2002 formula approximates its Black vol |
| SVI, SSVI | Smile shapes in total variance: SVI per expiry, SSVI across expiries with simple no-arbitrage conditions |
| Total variance | `w = v^2 T`, the vol squared times time to expiry |

## Stage D: Curves and fixed income

| Term | Meaning |
|---|---|
| ESTR | Euro short-term rate, the euro overnight rate |
| Lookback, observation shift, lockout | Ways to move an overnight coupon's fixing window so the amount is known before payment (`overnight-compounding.md`) |
| IBOR fallback | The ISDA rule replacing a LIBOR fixing by compounded overnight rates plus a fixed spread |
| Turn of year | A one-off jump in discount factors over year end |
| Convexity adjustment | The gap between a futures rate and the forward rate, from daily settlement |
| CSA discounting | Discounting at the rate paid on the collateral |
| Z-spread | A constant spread over the curve that reprices a bond |
| Asset swap spread | The spread over the floating leg that swaps a bond to floating at par |
| Repo, special repo | A sale with an agreed buy-back, in effect a secured loan; special when one bond lends below the general rate |
| CTD | Cheapest to deliver: the bond a futures seller delivers, here the one with the highest implied repo |
| Cross-currency basis | The spread on one leg of a cross-currency swap that makes it par |
| NDF | Non-deliverable forward: settled in USD on the fixing, without delivering the other currency |
| CDS | Credit default swap: protection against a named borrower's default, paid for with a running premium |
| Hazard rate | The default rate per year, given survival so far |
| Sector or rating curve | A credit curve for a group of names: a weighted average of the constituents' CDS spreads, times a rating multiplier, bootstrapped like one name (`credit.curve.composite`, `04-pricing/credit.md`) |
| Index ratio | Reference CPI over base CPI, scaling an inflation-linked bond |
| Seasonality | A repeating monthly pattern in CPI or commodity prices |
| Convenience yield | The benefit of holding a commodity, implied by its forward curve |
| CPR, SMM, PSA | Annual and monthly prepayment rates, and the standard ramp of CPR by loan age |
| MBS | Mortgage-backed security: a bond paid from a pool of mortgages, whose cash flows depend on prepayment |
| WAL | Weighted average life: the average time to repayment of principal |

## Stage E: full volatility, exotics, rates vol, correlation and credit

| Term | Meaning |
|---|---|
| Total variance | `w = sigma^2 T`: implied variance times time, the quantity that must rise with expiry |
| SVI, SSVI | The Gatheral five-parameter smile for one expiry, and its surface form with one ATM-variance curve (`specifications/05-volatility/arb-free-surfaces.md`) |
| Butterfly arbitrage | Call prices not convex in strike, so the implied density is negative somewhere; for SVI, `g(k) < 0` |
| Calendar arbitrage | Total variance falling as expiry grows at a fixed moneyness |
| Lee bound | The wings of total variance grow at most like `2|k|` (Lee 2004) |
| Local vol | The spot- and time-dependent vol that reprices every vanilla (Dupire 1994) |
| Forward vol | The vol between two expiries, from the difference of their total variances |
| Sticky strike, sticky delta | Smile regimes: vol fixed at each strike, or fixed at each moneyness (delta) as spot moves (Derman 1999) |
| Vol of vol | Here, the annualised standard deviation of daily changes in an implied vol |
| Premium-adjusted delta | An FX delta reduced by the option premium, used when the premium is paid in the foreign currency |
| DNS | Delta-neutral straddle: the ATM strike at which call and put deltas cancel |
| Risk reversal, butterfly | Call vol minus put vol at one delta; the average of the two minus ATM vol |
| Heston, Bates, Merton | Stochastic variance; stochastic variance plus jumps; constant vol plus jumps (`specifications/05-volatility/heston-family.md`) |
| Leverage function | The local correction in a stochastic-local vol model that makes it fit the local vol surface |
| Barrier option | An option that comes alive (knock-in) or dies (knock-out) when spot touches a level |
| Rebate | Cash paid when a knock-out option is knocked out, or when a knock-in option never knocks in |
| Geometric Asian | An option on the geometric average of prices, which has a closed form |
| Lookback | An option struck at the best price seen over its life |
| Quanto | An option on a foreign asset, paid in domestic currency at a fixed exchange rate |
| Chooser | An option whose holder decides at a set date whether it is a call or a put |
| Kirk approximation | A closed form for an option on the spread of two forwards |
| BAW | Barone-Adesi-Whaley: a quadratic approximation to American option prices |
| Swaption cube | Swaption vols by expiry, swap length and strike; here, SABR parameters per (expiry, length) node (`rates-vol-cube.md`) |
| Caplet stripping | Turning flat cap vols into one vol per caplet so every cap reprices |
| Price vol, yield vol | Vol of a bond futures price, and of the cheapest-to-deliver's yield; linked by duration times yield |
| YoY and ZC inflation cap | Options on one year's inflation, and on cumulative inflation to maturity |
| GARCH(1,1) | A variance recursion: constant, plus a share of the last squared return, plus a share of the last variance (`garch.md`) |
| Long-run variance | `omega/(1 - alpha - beta)`, the level a stationary GARCH forecast returns to |
| Variance swap | Pays realised variance minus a fixed strike, times a variance notional (`variance-swaps.md`) |
| Log contract, strip | The payoff whose value is expected variance, and the weighted puts and calls that copy it |
| VIX-style index | 100 times the square root of 30-day variance from two option strips (Cboe methodology v5.0) |
| K0 | The listed strike at or immediately below the forward, in the VIX method |
| Nearest correlation matrix | The valid correlation matrix closest in the Frobenius norm (Higham 2002; `correlation.md`) |
| Dykstra's correction | The step that makes alternating projections reach the nearest point, not just a feasible one |
| Implied correlation | The single average correlation that makes index vol consistent with member vols |
| Dispersion trade | Long member variance, short index variance; a bet that realised correlation stays below implied |
| CDS option, payer, receiver | The right to buy (payer) or sell (receiver) protection at a fixed spread on a future date (`credit-options-and-copulas.md`) |
| Knock-out, front-end protection | A knock-out option dies on default before expiry; otherwise a payer is also owed the protection lost before the forward CDS starts |
| Risky annuity | The value of 1 per year of premium paid while the name survives |
| Copula | A rule joining single-name default probabilities into joint ones; Gaussian (no tail dependence) or Student t |
| Large homogeneous pool (LHP) | Vasicek's limit of a very large pool of identical names: losses depend on one common factor only |
| Tranche, attachment, detachment | A slice of pool losses between two levels; the slice's expected loss as a fraction of its width |

Stage E is Implemented in all four languages (6,817 of 6,817 golden cases (value-checked and error cases counted together) at merge `597abf2`). All inputs are synthetic. QuantLib's Python wheel has no GARCH, VIX, bivariate t or large-pool model, and no SLV or American FD reference, so those goldens rest on hand cases and high-precision replicas; 557 of 895 stage E cases (62.2%) are outside-checked under rule 11.2.5 and rulings E-A17 and E-B28.

## Stage F terms

| Term | Meaning |
|---|---|
| Bit-exact | Identical binary64 bits in every language and on every platform; see [determinism](docs/determinism.md) |
| Name map | `specifications/name-map.json`: each operation's public name in each language, generated from the specs ([ADR-0011](architecture/decisions/ADR-0011-api-style.md)) |
| Value at risk (VaR), expected shortfall (ES) | A loss quantile, and the mean loss beyond it, over a horizon |
| FRTB-SA | The Basel standardised approach to market-risk capital |
| Funding curve | The curve for unsecured borrowing: the OIS curve times a spread factor, used to discount uncollateralised cash flows and in FVA (`rates.funding.curve`, `02-curves/joint-solve-and-funding.md`) |

## Stage G terms

| Term | Meaning |
|---|---|
| Short-rate model | A model of the instantaneous rate `r(t)` from which bond prices follow; here Vasicek, CIR, Hull-White and two-factor G2++ (`04-pricing/short-rate-models.md`) |
| Jamshidian decomposition | Writing a swaption on a one-factor model as a sum of bond options struck at one critical rate |
| Bermudan swaption | A swaption exercisable on several dates, priced by rolling back a lattice (ruling G-18) |
| LIBOR market model (LMM) | A model of the quoted forward rates themselves, each lognormal under its own measure (`04-pricing/lmm.md`) |
| Pathwise and likelihood-ratio Greeks | Monte Carlo derivatives taken through the payoff, or through the density of the paths (`06-risk/mc-greeks.md`) |
| EE, ENE, PFE, EPE | Expected positive and negative exposure at a date, a high quantile of exposure, and EE averaged over time (`06-risk/xva-exposure.md`) |
| Margin period of risk (MPoR) | The time between the last collateral call met and the close-out after a default |
| CVA, DVA, FVA (FCA, FBA) | Prices of counterparty default, own default, and funding of uncollateralised exposure (`06-risk/xva-framework.md`) |
| Sensitivity-based initial margin (sbim) | The project's own initial-margin aggregation from weighted sensitivities, on placeholder weights; not a regulatory or industry-standard calculation, and no ISDA material is used (owner decision 2026-11-19). In stage G, `xva.sbim.ir_delta` is a single-bucket IR delta aggregation on weights the caller supplies; its old id `xva.simm.ir_delta` is a deprecated alias in v1.0.0, removed in the first release after it (KR-152, KR-256). Why there is no industry model here: `docs/model-inventory.md#why-there-is-no-isda-simm-here` |
| Wrong-way risk | Exposure that grows when the counterparty is more likely to default |
| BGK correction | Broadie, Glasserman and Kou's barrier shift `exp(0.5826 sigma sqrt(dt))`, which turns a continuous barrier formula into a discrete one (ruling G-7) |

## Stage I terms

| Term | Meaning |
|---|---|
| Hedge ratio | Units of a hedge instrument held per unit of the exposure; a positively correlated hedge is held short (`hedge.minvar.ratio`, ruling I-8) |
| Minimum-variance hedge | The holding that minimises the variance of the hedged position's value change, from return or price-change series (`08-hedging/hedge-solvers.md`) |
| Constrained least squares | Minimising a weighted sum of squared residual risks, with optional equalities and bounds on positions (`hedge.qp.solve`) |
| Ridge | A penalty `ridge sum x_j^2` added to the objective, which makes a near-singular hedge regular at the price of a small bias |
| Minimum-norm solution (`MIN_NORM`) | Among all hedges with the least objective, the one with the smallest Euclidean norm; the answer to a singular problem when asked for (ruling I-5) |
| Residual risk | The book's risk left after the hedge, `A x + b`, and its variance (`hedge.residual.report`) |
| Integer lots | Positions in whole contracts; found by exact search, since rounding the continuous answer can be far from best (`hedge.integer.solve`, `hedgeint_i-0010`) |
| CS01 | The change in value for a 1 bp move in credit spread, taken here as half the difference of two repricings with hazards bumped by `±1e-4/(1 − R)` (ruling I-15) |
| Jump to default (JTD) | The loss or gain if the reference name defaults now: `(1 − R) − pv` per unit of bought protection (ruling I-16) |
| Correlation01 | The change in value per 0.01 of correlation (ruling I-18) |
| Quadratic cost (stage I) | The hedge solver's impact charge, quadratic in the traded amount (`hedge-costs-and-frontier.md`); one of three impact forms, see Market impact under Stage H terms |
| Risk-against-cost frontier | The hedges that minimise risk plus a cost weight times cost, traced over a list of weights (`hedge.frontier.solve`) |
| Dollar offset | Minus the sum of the hedge's value changes over the sum of the hedged item's changes; 1 is a perfect offset, and it swings widely when the item's total change is small (`hedge.effectiveness`, `08-hedging/dynamic-hedge-and-effectiveness.md`) |
| Implementation shortfall | Execution cost against the decision price plus the opportunity cost of the unfilled quantity, `(Q − q_f)(final_price − d)` (`hedge.slippage.report`, ruling I-36) |
| Slippage | Execution cost less the cost the model predicted (`hedge.slippage.report`) |
| Switch point | The point where an instrument with a trading cost moves from being left out (`x_j = 0` exactly) to being held: the risk gradient there equals the cost weight times its half-spread (ruling I-54, `hedgecost_i-0023`) |
| Sign-state active-set method | A solve of the cost problem that fixes each instrument's sign (long, short or zero), solves that smooth problem exactly, and changes a sign only where the subgradient test fails; it replaced enumeration of every sign state in Java and C++ (ruling I-48) |
| Outside-oracle share | The fraction of a stage's golden cases, error cases included in the denominator, that an independent library reproduces within the case tolerance; the floor is 60% (rule 11.2.5, ruling I-2) |

## Stage J terms

| Term | Meaning |
|---|---|
| Execution lag | Bars between a strategy's decision and the close at which the backtester holds the new position; `lag = 0` is allowed only to show look-ahead (`11-research/backtester.md`, J-2) |
| Purging | Dropping a training row whose label span overlaps the test fold's time span, so the model cannot learn the test answer (`11-research/purged-cv.md`) |
| Embargo | Dropping a further fraction of rows just after each test fold, against serial correlation that outlasts the label span |
| CPCV | Combinatorial purged cross-validation: split into `N` groups, test on every choice of `k`, and recombine the test groups into backtest paths (`research.cv.cpcv_paths`) |
| Viterbi path | The single most likely sequence of hidden states of a given hidden Markov model; used here only to label regimes, not to forecast (`11-research/regimes.md`) |
| PSR | Probabilistic Sharpe ratio: the probability that the true Sharpe ratio exceeds a benchmark, allowing for sample length, skew and kurtosis (Bailey and López de Prado 2012) |
| DSR | Deflated Sharpe ratio: the PSR against the best Sharpe ratio expected by chance from the number of trials run (Bailey and López de Prado 2014) |
| PBO | Probability of backtest overfitting: how often the configuration best in-sample ranks below the median out of sample (Bailey, Borwein, López de Prado and Zhu 2017) |
| Mean-variance optimisation | Choosing fully invested weights within bounds to maximise expected return minus `gamma/2` times variance (Markowitz 1952; `07-portfolio/optimisation.md`, J-W2-2) |
| `at_bound` | Per-asset output of mean-variance: `-1` at the lower bound, `+1` at the upper bound, `0` free (J-W2-4) |
| Risk parity | Long-only weights whose risk contributions are proportional to chosen budgets, equal by default; expected returns are not used (Maillard, Roncalli and Teiletche 2010; J-W2-5) |
| Euler risk contribution | An asset's weight times the derivative of portfolio volatility with respect to that weight; the contributions add up exactly to the volatility (Tasche 1999; `risk.contrib.euler`) |
| Ledoit-Wolf shrinkage | A weighted average of the sample covariance and a multiple of the identity, with the weight `delta` estimated from the data (Ledoit and Wolf 2004; J-W2-7) |
| Black-Litterman | Moving prior expected returns towards investor views, each weighted by its uncertainty against the prior's (Black and Litterman 1992; J-W2-8) |
| Z2 statistic | The Acerbi-Szekely expected-shortfall backtest: one minus the sum of losses beyond VaR, each over `T alpha ES_t`; about 0 for a correct model, negative when ES is understated (Acerbi and Szekely 2014; J-W2-10) |
| Baum-Welch | The EM algorithm for a hidden Markov model: estimate state probabilities (E-step), re-estimate the parameters from them (M-step), repeat until the log-likelihood gain is below a tolerance (Rabiner 1989; `11-research/baum-welch.md`) |
| Half spread | Half the bid-offer gap, in basis points of price; the backtester charges `abs(d) p half_spread_bps / 10^4` per trade (`11-research/backtester.md`) |
| Turnover | The money value traded over a backtest, `sum_t abs(d_t) p_t m`; spread cost is turnover times the half spread (`research.backtest.run`) |
| Break-even spread | The half spread at which a backtest's net P&L is zero; because spread cost is linear in the half spread it follows from one run (Tutorial 27) |
| Look-ahead canary | A deliberately wrong backtest with `lag = 0` that shows how much a rule gains from seeing the close it trades at (Tutorial 23, J-2) |
| Trial | One strategy configuration tried during research, kept or not; counted in `research/trials.csv` and passed as `n_trials` to the DSR |
| SR0 | The Sharpe ratio the best of `N` worthless trials is expected to show; the DSR's benchmark (Bailey and López de Prado 2014; J-13) |
| Minimum detectable Sharpe (MDS) | The smallest annual Sharpe a study of a given length detects with the chosen power at the chosen `alpha`, `z_sum / sqrt(years)`, iid (Lo 2002; `research.stats.power`) |
| Power | The probability that a test detects an effect of a given size; the R3 studies had a pass probability of 13 % to 15 % at their MDS (`research/r3/RESULTS.md`) |
| Holm correction | A step-down rule for testing several hypotheses at once that keeps the chance of any false rejection at `alpha`; used across the R3 studies (`research/preregs/R3-01-amendment-1.md`, display erratum `research/DEVIATION-2026-11-14-holm-display.md`) |
| Label horizon | The time between a label's decision `t0` and the moment it is known `t1`; longer horizons mean more purging (Tutorial 31) |
| Leakage | Information from the test period reaching the training data, here through training labels whose windows overlap the test span |
| Efficient frontier | The expected return and volatility of the mean-variance portfolio at each risk aversion; without bounds its return is linear in `1/gamma` (Tutorial 28) |
| Certainty-equivalent return | `mu'w - (gamma/2) w' Sigma w`: the riskless return an investor with risk aversion `gamma` would accept instead of the portfolio; used to price a constraint |
| Minimum-variance portfolio | The fully invested portfolio with the lowest volatility; each asset's Euler risk share equals its weight there |
| Binding constraint | A bound the optimum sits on, so that removing it would change the answer; `at_bound` reports which bounds bind |
| Market-implied prior | The expected returns `pi = delta Sigma w_mkt` that make the market weights optimal; the starting point of Black-Litterman |
| View confidence | For one Black-Litterman view, the fraction `c = tau P Sigma P' / (tau P Sigma P' + Omega)` of the gap between prior and view that the posterior closes (Tutorial 29) |
| Shrinkage target | What Ledoit-Wolf pulls the sample covariance towards; in QuantForge a multiple of the identity only (J-W2-7) |
| Risk budget | The share of portfolio risk each asset should carry in risk parity; budgets must sum to 1 (J-W2-5) |
| Q6-02 | The redesigned calibration method test on synthetic quotes: signed before the run, run once on seed 20261113, passed with 87.4 % of fitted vols inside the spread against 80 % (`research/q6/q6_02_output.json`) |
| Mutation kill test | A unit test written to make a specific surviving code mutant fail; stage J item J-0 adds them for Rust `hedge.rs`, `var.rs` and `hedge_solvers.rs` (`program/J0_EQUIVALENT_MUTANTS.md`) |
| Historical shock | The per-tenor move of a yield curve between two dates of a stored history, in basis points, replayed on today's curve (`06-risk/scenario-stress.md`, J-W3-2) |
| Leave-one-out backtest | Hiding each inner knot of an interpolation, rebuilding from the rest and recording the miss (`11-research/interp-backtest.md`, J-W3-8) |
| CUSUM | Cumulative sum control chart: running sums of standardised deviations less an allowance `k`, with an alarm above `h` (Page 1954; J-W3-10) |
| Page-Hinkley test | A CUSUM-type test against the running mean: alarm when the cumulative deviation rises more than `lambda` above its minimum (J-W3-11) |
| ARL0 | Average run length in control: the mean number of steps to a false alarm when nothing has changed; ARL1 is the mean delay after a change |
| PSI | Population stability index: `sum (a - e) ln(a / e)` over binned shares of a test and a reference sample; 0.25 is a common alarm level (J-W3-12) |
| Two-sample KS test | Kolmogorov-Smirnov: the largest gap between two empirical distribution functions, with an exact p-value for small samples (J-W3-13) |
| Term repo rate | A simple money-market rate for financing secured on a named asset over a fixed term `[0, T]`: one unit borrowed returns `1 + R T` (`repo.term.curve`, `02-curves/financing-term-structure.md`) |
| Financing spread curve | The cumulative spread `S(t)` of secured financing over the funding curve, one pillar per term repo quote, linear between pillars (flat forward spreads); extends ruling D22 (J-C-2, J-C-3) |
| Borrow fee curve | The term structure of the fee a stock lender earns, from term-average fees; the cumulative fee must not fall, so forward fees are never negative (J-C-4) |
| Liquidity cost curve | Cost per unit of liquidating an order evenly over a horizon: half spread plus impact `Y sigma (Q/(V h))^delta` plus timing risk `z sigma sqrt(h/3)` (`liq.curve.cost`, `10-execution/liquidity-curve.md`) |
| Square-root law | Market impact proportional to volatility times the square root of order size over daily volume, with a coefficient of order one (Toth et al. 2011) |
| Optimal liquidation horizon | The horizon that minimises impact plus timing risk on the liquidity cost curve, in closed form `(2 delta a / b)^(1/(delta + 1/2))` (J-C-8) |

## Stage H terms

Stage H (v0.10.0, execution and microstructure) is implemented in all four languages, the `paper.*` operations included; these terms are defined as its specs use them (`specifications/09-microstructure/`, `specifications/10-execution/`).

| Term | Meaning |
|---|---|
| Market impact | The price move caused by your own trading. QuantForge has three forms: a quadratic cost in the traded amount (stage I hedge solver), the square-root law for the average move over an order (`exec.impact.sqrt`), and transient impact that decays as the book refills (`exec.impact.ow_optimal`). They answer different questions and are not interchangeable |
| Temporary and permanent impact | Temporary impact affects only the trade that causes it and then fades; permanent impact shifts the price for all later trades (Almgren-Chriss `eta` and `gamma`) |
| Square-root law (stage H) | `I = Y sigma sqrt(Q / V)`, [TLD11] eq. (1); `Y` is an input, labelled assumed (HR-10). See also the stage J entry |
| Transient impact | Impact that decays over time after trading, as in Obizhaeva-Wang's block-shaped book with resilience |
| Resilience | The rate `rho` at which the book refills after a trade (Obizhaeva-Wang); the optimal blocks are `X / (rho T + 2)` |
| TWAP | Time-weighted average price schedule: equal slices per time bucket (`exec.schedule.twap`) |
| VWAP | Volume-weighted average price schedule: slices in proportion to an expected volume profile, given as an input (`exec.schedule.vwap`) |
| POV | Percentage-of-volume schedule: trade a fixed share `p` of all volume, own fills included, so the child is `p v / (1 - p)` against outside volume `v` (HR-4) |
| Participation rate | Your share of total traded volume in a bucket, own fills included (DR-H4) |
| Parent and child orders | The whole order to be worked, and the slices sent to the market |
| Implementation shortfall (stage H) | Delay plus execution plus opportunity cost plus fees, against the decision price (`exec.tca.shortfall`, Perold split, HR-8). Same idea as the stage I entry, with the delay part added |
| Decision price | The price when the decision to trade was made; the paper portfolio trades at it |
| Arrival price | The price when the order reached the market |
| Delay cost | `s Q (P_0 - P_d)`: the move between decision and arrival, on the filled quantity |
| Opportunity cost | `s (X - Q)(P_c - P_d)`: the move on the part never filled |
| Almgren-Chriss | Optimal execution with linear impact and a mean-variance objective; holdings decay like `sinh(kappa (T - t)) / sinh(kappa T)` ([AC00]) |
| Risk aversion (execution) | `lambda` in `E + lambda V`; 0 gives the straight-line schedule |
| Efficient frontier (execution) | Expected cost against variance of the optimal schedules over `lambda` (`exec.ac.frontier`) |
| MBP and MBO | Market by price (quantity per price level) and market by order (each order in its queue). The recorded Kraken feed is MBP; MBO exists only in the simulated venues |
| Price-time priority | Best price first, then earliest arrival at that price (FIFO) |
| Queue position | How much quantity is ahead of an order at its price; it decides whether a passive order fills |
| IOC and FOK | Immediate-or-cancel: fill what you can now, cancel the rest. Fill-or-kill: fill in full now or not at all |
| Iceberg order | Shows part of its size; each refill joins the back of the queue (CME FIFO rule) |
| Post-only | A limit order that must not trade on arrival; rejected if it would cross (HR-26) |
| Pegged order | An order whose price follows a reference, the mid (PEG_MID) or the same-side best (PEG_PRIMARY) |
| Midpoint cross | A dark-pool trade at the lit market's mid |
| Minimum quantity | The smallest fill an order accepts, applied per fill (HR-33) |
| Conditional order | A dark order that rests without commitment and must firm up when invited (HR-34) |
| Smart order router | Splits an order across venues to minimise expected cost including fees, rebates and fill risk (`exec.sor.allocate`, Cont-Kukanov model) |
| Markout | The move of the mid after a fill, signed so that positive is good for the trader, in bp at fixed horizons |
| Fill rate | Filled quantity over submitted quantity |
| Adverse selection | Fills that come more often just before the price moves against you; measured by markouts |
| Toxicity | Informally, how much adverse selection a venue's flow carries |
| Reservation price | The price at which a market maker is indifferent to one more unit, `s - q gamma sigma^2 (T - t)` ([AS08] eq. (29)) |
| Book checksum | Kraken's CRC32 of the top 10 levels per side, used to check a rebuilt book against the venue |
| Paper trading | Running a book with real checks, a ledger and daily P&L, but with simulated fills and no path to a live venue (HR-42) |
| P&L explain | The day's NAV change split into market, trading, fees and financing, summing exactly (HR-53) |
| Average cost | Position cost method: buys that grow the position average in; sells realise against the average (HR-50) |
| Hash-chained ledger | Append-only records, each holding the SHA-256 of its own canonical bytes and of the previous record, so an edit breaks the chain (HR-45, HR-46) |
| Pre-trade check | A deterministic limit check run before an order is sent: kill switch, order count, size, price band, notional, position, short sale, cash (HR-49) |
| Kill switch | A flag that rejects every new order while set |
| Resilience | The rate at which the spread returns to its resting level after a shock, `kappa` in `S_t - S_inf = (S_0 - S_inf) e^{-kappa t}` |
| Liquidity decay | The rate at which depth falls with distance from the touch, `alpha` in `D_k = D_0 e^{-alpha k}` |
| Planted truth | A parameter value put into simulated data so an estimator can be checked by recovering it (here within 3 SE, HR-70) |
| Markout horizon | The time after a fill at which the mid is read for a markout; results should be shown at several |
| Arrival price algorithm | Front-loads an order by the Almgren-Chriss `sinh` profile with urgency `kappa` per bucket |
| Close algorithm | Puts up to a participation cap of the forecast closing auction into the auction and spreads the rest over a profile |
| Liquidity seeking | Takes a fixed share of the depth inside a limit price in each bucket |
| Cash-balanced pair | Two legs on opposite sides traded so that cash paid and received stay close in every bucket |
| Tick size | The smallest price step on a venue. US equities: 0.0001 below 1.00 and 0.01 at or above; the amended Rule 612 adds a 0.005 tier with compliance date 2027-11-01 (`micro.eq.round_price`, HR-81, HR-120) |
| Round lot | The standard order size: 100, 40, 10 or 1 shares by price since the first business day of November 2025, 100 at every price before (`micro.eq.round_lot`, HR-82, HR-120) |
| Access fee cap | The most a venue may charge to take a displayed quote: 0.003 a share today; the amended 0.001 cap has compliance date 2027-11-01 (`micro.eq.fee_check`, HR-85, HR-120) |
| Compliance date | The date from which an amended rule must be followed. An input (`compliance_date`) with a default per rule; `as_of` on or after it selects the amended text, and so does no `as_of` at all (HR-120) |
| T+1 | Settlement one good business day after the trade date (`micro.eq.settle_date`, HR-86) |
| Pip | The unit of an FX spot quote: 0.0001, or 0.01 when JPY is the quote currency (`micro.fx.pip_value`, HR-87) |
| Spot date | The normal FX value date: T+2 good days, T+1 for USDCAD (`micro.fx.spot_date`, HR-89) |
| Last look | A dealer's short hold before accepting a request. In the simulated FX venue: reject `LL_PRICE` if the mid moved past a threshold, `LL_RANDOM` at a stated random rate, else fill (HR-97). The thresholds are the spec's own, not from the FX Global Code (HR-119) |
| 32nds | Treasury price notation `H-FF[q]`: handle, 32nds, and an optional third digit in quarters of a 32nd (0, 2, 5, 7, or `+` for a half). Eighth-tick contracts are not supported (HR-109, HR-118) |
| Tick value | The cash value of one tick on one futures contract: face x tick / 100, 15.625 for ZN and 31.25 for ZB (HR-91) |
| Variation margin | The daily cash move from marking a futures position to the settlement price (`exec.sim.fut.variation`) |
| Call auction and uncrossing | Orders collect without trading; uncrossing picks the one price with the largest matched volume and fills everyone there (`exec.sim.auction.uncross`, HR-84) |
| Imbalance (auction) | Buy minus sell quantity at the uncrossing price; positive is a buy surplus |
| Session phase | PRE_OPEN, CONTINUOUS, PRE_CLOSE or CLOSED in the simulated lit engine; an order sent in the wrong phase is rejected `PHASE` (HR-112) |
| Blind re-derivation | A second lane works out the expected outputs from the rules and inputs alone, without seeing the answers. It catches arithmetic and convention slips; it cannot catch a wrong rule, because it reads the same rules (DR-H2) |
| Order of checks | The fixed order in which a stage H operation validates its inputs, so that a request with two faults gets the same code in every build: `E_SCHEMA`, `E_LIMIT` on input size, non-finite `E_DOMAIN`, structural `E_INPUT`, `E_DOMAIN` (HR-122) |
| I-star | Pre-trade impact form `a1 (X/ADV)^a2 sigma^a3` in bp, split into temporary and permanent parts by `b1` ([Kis13], recalled) |
| Timing risk | One standard deviation of the price move while the order works; reported beside, not added to, expected cost |
| Spread cost | In attribution, what fills paid against the mid at the fill time; negative means price improvement |
| Coordinated omission | Undercounting slow samples when a load generator waits for a slow response; not corrected here because replay is unpaced |

## Stage K terms (in progress)

Stage K round 1 is merged to main by 2026-11-20 (pull requests #58 and #59), not tagged, and released with v1.0.0; these terms are defined as its specs use them (read 2026-11-19). [Tutorials 51 to 58](docs/getting-started/README.md#stage-k-in-progress) use them.

| Term | Meaning |
|---|---|
| Bitemporal (stage K) | A record carries two times: a valid-time interval `[valid_from, valid_to)`, the period it describes, and a knowledge time, when the store learned it. Nothing is overwritten; a correction is a new record (`core.store.bitemporal_query`, KR-2) |
| As-of (knowledge as of) | The knowledge instant `K` of a query: only records with `knowledge_time <= K` are seen, so an answer as of `K` never changes when later records are appended (KR-4) |
| Valid time | The period a stored value is meant to describe, `valid_from` inclusive, `valid_to` exclusive, null meaning open-ended |
| Withdrawn | The answer of a bitemporal query when the latest record known by `K` that covers `V` is a deletion |
| Incremental curve update | Rebuilding a sequential bootstrap from the first changed quote only, with earlier pillars copied; must equal a full rebuild bit for bit (`curve.incremental.update`, KR-5) |
| Recalibration trigger | A rule that fires when an input has moved since the last calibration by more than `k sigma sqrt(d)`, `sigma` the sample standard deviation of past daily changes (`calib.trigger.check`, KR-6) |
| False-alarm rate | The share of pure-noise checks on which a trigger still fires; `2 (1 - Phi(k))` when `sigma` is known |
| Lagrange remainder bound | The bound `M3 abs(h)^3 / 6` on the error of a delta-gamma estimate, `M3` the largest third derivative on the segment; for a zero-coupon position it is exact to compute (`risk.intraday.delta_gamma_bound`, KR-7) |
| Observed order | `log((f1 - f2)/(f2 - f3)) / log r` from values on three grids refined by `r`; a second-order scheme gives about 2 (`num.richardson.check`, KR-9) |
| Richardson extrapolation | Estimating the limit of a grid sequence as `(r^p f3 - f2)/(r^p - 1)` for order `p`; used only after the order check returns `OK`, never unguarded (KR-9) |
| Rannacher start-up (stage K) | In `CN_RANNACHER_SMOOTHED`, the first two Crank-Nicolson steps of each interval between exercise dates replaced by two implicit half steps each, to damp the high-frequency error a kink leaves [Rannacher 1984, recalled; Giles and Carter 2006, read by the K-8 lane] |
| Exercise smoothing | Replacing the pointwise `max(U, E)` at an exercise date by a hat-weighted average with an end correction, so the result does not depend on where the exercise boundary sits inside its grid cell (K-8, KR-15) |
| SA-CCR | The Basel standardised approach for counterparty credit risk: a fixed recipe from trade data to exposure at default, with no model (CRE52; `risk.saccr.ead`) |
| EAD | Exposure at default: `1.4 x (RC + PFE)` under SA-CCR; a margined EAD is capped at the unmargined one |
| Replacement cost (RC) | What the bank loses now if the counterparty defaults: `max(V - C, 0)` unmargined, `max(V - C, TH + MTA - NICA, 0)` margined |
| PFE (SA-CCR) | Potential future exposure: `multiplier x AddOn`, a supervisory estimate of how far the exposure could grow before replacement |
| PFE multiplier | `min{1; 0.05 + 0.95 exp((V - C) / (2 x 0.95 x AddOn))}` when `V - C < 0`, else 1: excess collateral lowers the PFE but never below 5% of the add-on (CRE52.23, KR-36) |
| Add-on | Supervisory factor times a hedging set's aggregated effective notional; summed over hedging sets and asset classes |
| Hedging set | A group of trades allowed to offset each other: interest rates by currency, FX by currency pair, one each for credit and equity, four for commodities; basis and volatility trades in their own sets (CRE52.45 to 52.47) |
| Adjusted notional | Trade size in SA-CCR: notional times supervisory duration for interest rate and credit trades, the notional itself for FX, equity and commodity |
| Supervisory duration | `(exp(-0.05 S) - exp(-0.05 E)) / 0.05`, floored at 10 business days, `S` and `E` the start and end in years (CRE52.34) |
| Supervisory delta | +1 or -1 for linear trades; a Black-type delta with a fixed supervisory volatility for options; a formula in attachment and detachment for CDO tranches (CRE52.40, 52.41) |
| Effective notional | Adjusted notional times maturity factor times supervisory delta |
| Traffic light (FRTB) | The backtesting zones of the internal models approach: GREEN, AMBER, RED by the binomial cumulative probability of the exception count, amber from 95% and red from 99.99%; at 250 days amber from 5 and red from 10, with a capital multiplier from 1.50 to 2.00 (`risk.frtb.backtest.zone`, MAR32, MAR99). The stage F operation follows the 1996 framework with a plus factor ([Basel traffic light](#tutorial-terms)) |
| Exception (backtesting) | A day whose loss exceeds the VaR, strictly; a day with a missing P&L or VaR counts as one. FRTB uses the greater of the actual and hypothetical counts |
| Desk eligibility | Whether a trading desk may keep using its internal model: not if it has more than 12 exceptions at 99% or more than 30 at 97.5% in the last 12 months (MAR32.19, KR-44) |
| Paper ledger (stage K) | The daily, hash-chained record of a fixed-rule paper book marked on the recorded Treasury par curve, labelled "paper marks on a fitted curve; not tradable"; plumbing evidence, no performance claim (`tools/paper_daily/`, KR-70 to KR-89) |
| Anchor | The head hash and row count of a ledger stamped with OpenTimestamps on a separate branch, so that a consistent rewrite of old rows or a truncated tail becomes visible |
| Blind re-derivation | An outside check where no library exists: a lane on a different model derives the answers from a spec stripped of every expected value, freezes them with a hash, and a fixed script compares them with the goldens; a leaked case does not count (DR-H2) |
| Placeholder weights | Risk weights or impact parameters that are not calibrated to any market; every output that uses them says "placeholder weights" (the sensitivity-based margin, `sbim`, in stages G and K) |

## Tutorial terms

Terms the [tutorials](docs/getting-started/README.md) use that the stage sections above do not define.

| Term | Meaning |
|---|---|
| Accrued interest | The share of the current coupon earned by the seller of a bond since the last coupon date; here ACT/ACT ICMA (`04-pricing/bonds.md`) |
| Clean price, dirty price | The quoted bond price without accrued interest, and the price actually paid, with it |
| Yield to maturity | The single rate that, used to discount every cash flow of a bond, gives back its price; here compounded at the coupon frequency |
| Macaulay duration | The present-value-weighted average time to a bond's cash flows, in years |
| Modified duration | Macaulay duration times `1/(1 + y/f)`: the fall in price, as a fraction of price, per unit rise in yield |
| Convexity | The second derivative of price with respect to yield, divided by price |
| Carry | What holding a position earns or costs over time, such as a bond's coupon less its repo financing |
| Implied repo rate | The repo rate that links a bond's spot and forward prices |
| Black-Scholes model | Lognormal stock with constant volatility, rate and dividend yield; gives closed-form European option prices |
| Survival probability | The probability that a borrower has not defaulted by a date |
| Recovery rate | The fraction of the notional recovered after a default |
| Risky annuity (RPV01) | The value of 1 a year paid until maturity or default, whichever is first |
| Upfront | The amount paid at the start of a standard CDS because its fixed coupon differs from the par spread |
| Bump and revalue | A sensitivity found by repricing with one input moved up and down |
| AAD | Adjoint (reverse-mode) algorithmic differentiation: every sensitivity of a price from one backward pass through the pricing code |
| Backtest | Counting how often realised losses exceeded VaR, and testing that count (Kupiec, Christoffersen, traffic light) |
| Mean reversion | In a short-rate model, the speed `a` at which the rate is pulled back toward its drift; shocks halve in about `ln 2 / a` years |
| Collateral agreement (CSA), threshold, minimum transfer amount | A collateral agreement; the exposure left uncollateralised; the smallest collateral call that is made |
| Implied volatility | The volatility that makes the Black-Scholes price equal a given price (`vol.option.implied`, `05-volatility/black-models.md`) |
| Smile | Implied volatility plotted against strike for one expiry; flat in Black-Scholes, curved in the market |
| At the money (ATM) | A strike at the spot or the forward; FX also uses the delta-neutral straddle (DNS) strike |
| Gamma | The change in delta per 1.00 move in the underlying (`06-risk/vol-greeks.md`) |
| Vega | The change in price per 1.00 of volatility (100 percentage points); divide by 100 for one vol point |
| Theta | `−dV/dT`: the change in price as time to expiry shortens, per year |
| Rho | The change in price per 1.00 of interest rate; divide by 100 for a 1% move |
| Forward price | The price agreed today for delivery on a later date; for a bond on repo, the dirty price grown at the repo rate less coupons paid in the term (`repo.forward`) |
| Floor | A strip of floorlets, each a put on one period's forward rate; the mirror of a cap |
| OIS curve | The discount curve bootstrapped from overnight indexed swap quotes, one pillar per quote at that swap's last payment date (`02-curves/ois-curves.md`) |
| Joint solve | Solving several curves (OIS discount, term projection, cross-currency) as one system with one unknown per instrument, which also gives the Jacobian (`rates.curve.joint_solve`, `02-curves/joint-solve-and-funding.md`) |
| Sector curve, rating curve | A CDS curve built from the weighted average of constituent spread curves, times a rating multiplier (1 for the sector itself), then bootstrapped (`credit.curve.composite`, `04-pricing/credit.md`) |
| Protection leg | The value of the CDS default payment, `(1 − R)` per unit notional paid at default, summed over the hazard buckets (`04-pricing/credit.md`) |
| Par spread | The running CDS spread that makes the contract worth zero: protection leg over the clean risky annuity (`04-pricing/credit.md`) |
| Down-and-out call | A call that is cancelled if the underlying touches or falls through a barrier below spot; on a daily-monitored contract the check is at each date (`04-pricing/exotics.md`) |
| CRR tree | The Cox-Ross-Rubinstein binomial tree: up factor `e^{v√dt}`, down factor its inverse, risk-neutral probability `(e^{(r−q)dt} − d)/(u − d)` (`exotic.american.crr`) |
| Early-exercise premium | An American option's price less the European option's with the same terms: the value of being able to exercise early |
| AAD ladder | A price and its full sensitivity ladder (here to every curve node, sigma and mean reversion) from one reverse sweep (`rates.shortrate.bermudan_ladder`) |
| Model reserve | A valuation reserve for model risk: the largest distance between the booked model's price and the other calibrated models' prices (`risk.model_reserve.dispersion`, `06-risk/model-reserve.md`) |
| Basel traffic light | The backtest zones for a VaR model: green, yellow or red by the binomial probability of the exception count; at 250 days and 99%, green for 0 to 4 exceptions, yellow for 5 to 9, red from 10 (`risk.backtest.traffic_light`) |
| Exposure profile | Expected exposure (and PFE) at each date of a time grid; CVA integrates it against default probabilities (`06-risk/xva-framework.md`) |
| Expected negative exposure (ENE) | The mean over paths of the negative part of the portfolio value at a date: what the counterparty is exposed to |
| Potential future exposure (PFE) | A high quantile of exposure at a date, by the inverted-CDF rule (`06-risk/xva-framework.md`) |
| Effective EPE | The time average over the first year of effective EE, where effective EE is EE made non-decreasing in time (Basel CRE53; `06-risk/xva-framework.md`) |
| abcd volatility | The LMM instantaneous volatility of a forward fixing at `T`: `σ(t) = (a + b(T − t)) e^{−c(T − t)} + d` (`04-pricing/lmm.md`) |
| Humped volatility | An abcd shape with `b > 0` whose volatility rises then falls with time to fixing; it peaks at `T − t = 1/c − a/b` |
