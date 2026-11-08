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
| Jacobian | How each bootstrapped zero rate moves per basis point of each par quote; lower triangular for a bootstrap (`risk.curve.jacobian`) |
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
| Butterfly arbitrage | Call prices not convex in strike, which is a negative density |
| Calendar arbitrage | Total variance falling as expiry rises, at fixed moneyness |
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
| Index ratio | Reference CPI over base CPI, scaling an inflation-linked bond |
| Seasonality | A repeating monthly pattern in CPI or commodity prices |
| Convenience yield | The benefit of holding a commodity, implied by its forward curve |
| CPR, SMM, PSA | Annual and monthly prepayment rates, and the standard ramp of CPR by loan age |
| MBS | Mortgage-backed security: a bond paid from a pool of mortgages, whose cash flows depend on prepayment |
| WAL | Weighted average life: the average time to repayment of principal |

## Stage E (spec A): full vol and exotics

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

## Stage E, spec B: rates vol, correlation, GARCH and variance, credit options

| Term | Meaning |
|---|---|
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

Stage E spec B is Specified, not Implemented: goldens exist and the four builds are being written against them. All inputs are synthetic. QuantLib's Python wheel has no GARCH, VIX, bivariate t or large-pool model, so those goldens rest on hand cases and high-precision replicas; 277 of 449 cases (61.7%) are outside-checked under rule 11.2.5 and ruling E-B28 (`specifications/stage-e-rulings-b.md`).
