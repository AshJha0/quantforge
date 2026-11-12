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

Stage E is Implemented in all four languages (6,817 of 6,817 golden cases (value-checked and error cases counted together) at merge `597abf2`), not Validated. All inputs are synthetic. QuantLib's Python wheel has no GARCH, VIX, bivariate t or large-pool model, and no SLV or American FD reference, so those goldens rest on hand cases and high-precision replicas; 557 of 895 stage E cases (62.2%) are outside-checked under rule 11.2.5 and rulings E-A17 and E-B28.

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
| SIMM | ISDA's standard initial-margin model; here a SIMM-style IR delta only (`xva.simm.ir_delta`) |
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
| Market impact | A cost that grows with trade size, here quadratic in the traded amount (`hedge-costs-and-frontier.md`) |
| Risk-against-cost frontier | The hedges that minimise risk plus a cost weight times cost, traced over a list of weights (`hedge.frontier.solve`) |
| Dollar offset | Minus the sum of the hedge's value changes over the sum of the hedged item's changes; 1 is a perfect offset, and it swings widely when the item's total change is small (`hedge.effectiveness`, `08-hedging/dynamic-hedge-and-effectiveness.md`) |
| Implementation shortfall | Execution cost against the decision price plus the opportunity cost of the unfilled quantity, `(Q − q_f)(final_price − d)` (`hedge.slippage.report`, ruling I-36) |
| Slippage | Execution cost less the cost the model predicted (`hedge.slippage.report`) |
| Switch point | The point where an instrument with a trading cost moves from being left out (`x_j = 0` exactly) to being held: the risk gradient there equals the cost weight times its half-spread (ruling I-54, `hedgecost_i-0023`) |
| Sign-state active-set method | A solve of the cost problem that fixes each instrument's sign (long, short or zero), solves that smooth problem exactly, and changes a sign only where the subgradient test fails; it replaced enumeration of every sign state in Java and C++ (ruling I-48) |
| Outside-oracle share | The fraction of a stage's golden cases, error cases included in the denominator, that an independent library reproduces within the case tolerance; the floor is 60% (rule 11.2.5, ruling I-2) |

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
