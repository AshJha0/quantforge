# Traceability

Maps every item in both blueprints and the additions to a stage or an explicit exclusion, as plan section 4 requires. 498 rows: 162 Explicit, 233 Implied, 100 Added, 3 Excluded.

Explicit: named in the plan's stage row. Implied: inside a named item or a ticket; each must be named in its stage's tickets. Added: scheduled after the first check found it missing. Excluded: a decided exclusion.

Sources: v1 is the original blueprint, exp the expanded proposal, v2 and s11, s12 the reviewed blueprint. `Wnn` are tickets. Rows record where work is scheduled, not that it is done.

## Domain 01: Foundation

| Item | Source | Stage | Status |
|---|---|---|---|
| Date and time abstraction | v1 W1; exp D01 | A | Implied: W02 dates |
| Business calendars, holidays, business-day adjustment | v1 W1; exp D01 | A | Implied: W02 |
| UK, US government, TARGET calendars; one-off holidays | v1 W1 datasets | A | Implied: W02 calendars |
| Day counts ACT/360, ACT/365F, 30/360, ACT/ACT | v1 W1; exp D01 | A | Explicit: "all day counts" |
| Compounding: simple, periodic, continuous; rate conversion | v1 W1; exp D01 | A | Implied: W02 compounding |
| Settlement conventions and convention registry | exp D01 | A | Implied: W02 conventions |
| Coupon and payment schedules, stubs, end-of-month | v1 W1, W7 | B | Implied: W12 schedules |
| Linear, log-linear interpolation | v1 W2 | A | Implied: W04 interpolation |
| Cubic spline with boundary conditions | v1 B, W2 | A | Implied: W04 interpolation |
| Monotone cubic interpolation | v1 B, W2 | A | Implied: W04 interpolation |
| Extrapolation policy | v1 B, W3 | B | Implied: W06 curve framework |
| Root finding: bisection, Newton-Raphson | v1 W2; exp D01 | A | Explicit: "root finders" |
| Numerical differentiation | v1 W2; exp D01 | A | Implied: W04 finite differences |
| Numerical integration | v1 W2; exp D01 | A | Added: Not in W04 or the row; ZIP spec list only |
| Linear algebra: matrices, decompositions, eigenvalues, solvers | v1 W2; exp D01 | A | Implied: Plan rule 4 allows libraries; needed by PCA and QP. No conformance item named |
| Statistics: distributions, moments, covariance, correlation | exp D01 | A | Explicit: "statistics" |
| Time series: resampling, missing data, returns, rolling windows | exp D01 | A | Explicit: "time series" |
| Market-data model: quotes, trades, timestamps | exp D01 | A | Implied: W03 |
| Units and types: currency, rates, prices, quantities, bp | exp D01 | A | Implied: W03 |
| Snapshots with hash | exp D01; v1 W3 | A | Explicit: "snapshot hash" |
| Deterministic fixtures and generator | exp D01; v1 s6 | A | Implied: W05 |
| Quality flags on data | exp D01 | A | Implied: W03 quality types; kept data contract |
| Stale, crossed and outlier quote checks (logic) | v2 s5; exp D01 | A | Added: W03 defines types only; no checking engine named |
| Market-data fallback rules | v2 s5 | F | Added: Not named anywhere |
| Quote provenance | v2 s5 | A | Implied: W03 and kept data-contracts.md |
| Timezone and cut-off handling | v2 s5 | A | Added: Contract has a timezone field; cut-off logic is not named |
| End-of-day snapshots | v2 s5 | F | Implied: "end-of-day marks" |
| Intraday snapshots | v2 s5 | K | Implied: "Incremental updates" |
| Curve interface, points, metadata, serialisation, versioning | v1 W3, s5 | B | Implied: W06 curve framework |
| Typed curve classes (Discount, Forward, Yield, Dividend, Credit, Vol, Correlation, Liquidity, Risk, Hedge) | v1 s5 | B-H | Implied: Inside each stage's curve items |

## Domain 02: Curves (equity)

| Item | Source | Stage | Status |
|---|---|---|---|
| Spot price curve (EQ-01) | v1 A, 5.1 | C | Explicit: "Spot" |
| Forward price curve (EQ-02) | v1 A, 5.1 | C | Explicit: "parity-implied forward"; W07 |
| Dividend curve, discrete and continuous (EQ-03) | v1 A, 5.1 | D | Explicit: "Dividend"; discrete also in C |
| Borrow/rebate curve (EQ-04) | v1 A, 5.1 | D | Explicit: "borrow" |
| Financing curve (EQ-05) | v1 A, 5.1 | D | Explicit: "financing" |
| Equity futures fair value | v1 W4 | D | Implied: "futures" plus forward; row does not say equity |
| Futures basis decomposition (EQ-06) | v1 5.1, W4 | D | Added: In BLUEPRINT_v2 phase 2, dropped from the plan row |
| Equity yield term structure (EQ-07) | v1 5.1 | D | Implied: Dividend curves |
| Equity discount curve | v1 A | B | Implied: W06 discount factors |
| Equity vol term structure (EQ-08) | v1 A, 5.1 | C | Implied: "surface" |
| Equity vol smile (EQ-09) | v1 C, 5.1 | C | Explicit: "smile" |
| Equity vol skew (EQ-10) | v1 A, 5.1 | C | Implied: W14 smile |
| Equity vol surface (EQ-11) | v1 A, 5.1 | C | Explicit: "surface" |
| Correlation curve/surface (EQ-12) | v1 A, 5.1 | E | Explicit: "correlation" |
| Liquidity curve (EQ-13) | v1 A, 5.1 | H | Explicit: "liquidity curves" |
| Market impact curve (EQ-14) | v1 A, 5.1 | H | Explicit: "Almgren-Chriss"; W29 |
| Forward carry attribution, carry analytics | v1 W5, W6 | C | Implied: W07 equity carry |
| Dividend and borrow from put-call parity | v2 s5 | C | Implied: "parity-implied forward"; borrow split not named |
| Index against single-stock dividends | v2 s5 | D | Added |
| Dividend futures | v2 s5 | D | Added |
| Index rebalancing | v2 s5 | D | Added |
| Corporate-action adjustment | v1 Phase 2, s2; v2 s5 | D | Added: In BLUEPRINT_v2 phase 2, dropped from the plan row |
| Total return swaps | v2 s5 | D | Added: In BLUEPRINT_v2 phase 2, dropped from the plan row |
| Cash and synthetic positions | v1 Phase 2 | F | Implied: "position lifecycle" |

## Domain 02: Curves (rates and sovereign)

| Item | Source | Stage | Status |
|---|---|---|---|
| Government yield curve (FI-01) | v1 B, 5.2 | B, D | Implied: W08 in B; "sovereign fits" in D |
| Zero curve (FI-02) | v1 B, 5.2 | B | Implied: W08 |
| Discount factor curve (FI-03) | v1 B, 5.2 | B | Implied: W06 |
| Forward rate curve (FI-04) | v1 B, 5.2 | B | Implied: W10 |
| OIS curve, SONIA (FI-05) | v1 B, 5.2 | B | Explicit: "SONIA" |
| OIS curves, SOFR and ESTR | v1 Phase 3 | B, D | Explicit: "minimal SOFR"; "full SOFR, ESTR" |
| Projection curve (FI-06), IBOR-style conventions | v1 B, 5.2, W9 | B | Implied: W10 projection |
| Swap curve (FI-07) | v1 B, 5.2 | B | Implied: W12; "swap" |
| Basis curve, basis swaps, tenor basis (FI-08) | v1 B, 5.2; v2 s5 | B | Implied: W10 basis relationships |
| Repo curve (FI-09) | v1 B, 5.2 | D | Explicit: "repo" |
| Government spread curve (FI-10) | v1 B, 5.2 | D | Implied: "RV" |
| Credit spread curve (FI-11) | v1 B, 5.2 | D | Implied: "credit" |
| Z-spread curve | v1 B | D | Explicit: "Z-spread" |
| Inflation curve (FI-12) | v1 B, 5.2 | D | Explicit: "inflation" |
| Duration (FI-13) | v1 5.2 | B, F | Implied: W20 |
| Key-rate risk (FI-14) | v1 5.2 | B | Explicit: "key-rate" |
| Par yield curve | exp D02 | D | Implied: "sovereign fits" |
| Sequential bootstrapping | v1 B; exp D03 | B | Implied: W08 |
| Multi-curve construction | v1 B | B | Implied: W10 |
| Curve dependencies and ordered rebuilds | v1 B; v2 s5; exp D02 | B | Implied: W10 dependencies |
| Historical reconstruction of curves | exp D02 | A, K | Explicit: "as-of store and replay"; "bitemporal store" |
| Global (non-sequential) curve solve | v2 s5; exp D03 | B | Added |
| Tension interpolation | v2 s5 | A | Added |
| Monotone-convex interpolation | v2 s5 | A | Added |
| Smoothing fits | v2 s5 | D | Implied: "sovereign fits" |
| Regularised fits | v2 s5 | D | Added |
| Nelson-Siegel-Svensson | v2 s5 | D | Implied: "sovereign fits" |
| Outlier-robust bond fits | v2 s5 | D | Added |
| Joint calibration across curves | v2 s5 | D | Added |
| Quote bid/ask handling in curve builds | v2 s5 | B | Added |
| Futures convexity adjustment | v2 s5 | D | Added |
| Central-bank meeting-date step curves | v2 s5 | D | Added |
| Turn-of-year effects | v2 s5 | D | Added |
| Fixings history | v2 s5 | F | Explicit: "fixings" |
| Compounded in arrears | v2 s5 | B | Implied: OIS instrument (W09, W12) |
| Lookback, lockout, observation shift | v2 s5 | D | Added: "full SOFR" does not clearly include them |
| IBOR fallback spreads | v2 s5 | D | Added |
| CSA and collateral-currency discounting | v2 s5 | D | Added: G has CSA terms for exposure only, not discounting |
| Asset swap spreads | v2 s5 | D | Added |
| Bond-OIS spreads | v2 s5 | D | Added |
| CTD | v2 s5 | D | Explicit: "CTD" |
| Implied repo | v2 s5 | D | Implied: "repo, CTD" |
| Special repo | v2 s5 | D | Added |
| Sovereign fitted, on-the-run and off-the-run curves | v2 s5 | D | Implied: "sovereign fits" |
| Rich/cheap, butterfly, swap-spread analytics | v2 s5 | D | Implied: "RV" |
| MBS prepayment | v2 s5 (later option) | D | Explicit: owner addition |
| Commodity curves | v2 s5 | D | Explicit: owner addition |

## Domain 02: Curves (inflation, FX, credit)

| Item | Source | Stage | Status |
|---|---|---|---|
| Inflation indexation lag, RPI/CPI conventions | v2 s5 | D | Implied: "inflation, linkers" |
| Inflation seasonality | v2 s5 | D | Added |
| Linkers | v2 s5 | D | Explicit: "linkers" |
| Breakeven inflation | v2 s5; exp D02 | D | Implied: "inflation, linkers" |
| Inflation options vol (extension) | v2 s5 | E | Added: v2 calls it an extension; decide or exclude |
| FX spot | exp D02 | B | Implied: W07 |
| FX forward points and forward curves | exp D02; v2 s5 | B | Explicit: "FX forwards" |
| FX swap curve | exp D02 | B | Explicit: "swaps" |
| Cross-currency basis | exp D02; v2 s5 | B, D | Explicit: "quote-driven basis"; "cross-currency" |
| NDF implied yields | v2 s5 | D | Explicit: "NDF" |
| FX smile with delta conventions | v2 s5 | E | Added: No FX vol in any row |
| Credit spread term structure (CR-01) | v1 F, 5.5 | D | Implied: "credit" |
| CDS spread curve | v1 F | D | Explicit: "ISDA CDS" |
| Hazard rate curve (CR-02) | v1 B, F, 5.5 | D | Implied: "ISDA CDS" |
| Survival probability (CR-03) | v1 F, 5.5 | D | Implied: "ISDA CDS" |
| Default probability (CR-04) | v1 5.5 | D | Implied: "ISDA CDS" |
| Recovery curve (CR-05) | v1 F, 5.5 | D | Implied: "credit"; sensitivity test not named |
| CDS repricing (CR-06) | v1 5.5 | D | Explicit: "All instruments reprice" |
| Index CDS | v2 s5 | D | Explicit: "index CDS" |
| Index basis to constituents | v2 s5 | D | Added |
| Sector and rating curves | v2 s5 | D | Added |
| Jump-to-default | v2 s5 | F | Added: F has default lifecycle, not the risk measure |
| CDS options (extension) | v2 s5 | E | Added: v2 calls it an extension; decide or exclude |
| Copula correlation for baskets | v2 s5 | E | Added |

## Domain 03: Calibration

| Item | Source | Stage | Status |
|---|---|---|---|
| Linear, nonlinear, weighted least squares | exp D03 | B | Implied: W11 objectives, weighting |
| Levenberg-Marquardt | exp D03; v2 s5 | B | Implied: W11 optimiser; needed by W15 |
| Gauss-Newton | exp D03 | B | Added: ZIP spec list only |
| BFGS | exp D03 | B | Added: ZIP spec list only |
| Bounds and parameter constraints | exp D03 | B, C | Implied: W11; W15 |
| Regularisation | exp D03 | B | Added: ZIP spec list only |
| Volatility calibration: SABR, Heston, local vol | exp D03 | C, E | Explicit: Named in C and E rows |
| Credit calibration: hazard, CDS | exp D03 | D | Implied: "ISDA CDS" |
| Maximum likelihood | exp D03 | E | Implied: "GARCH" requires it |
| Bayesian estimation | exp D03 | J | Added |
| Residual analysis | exp D03 | B | Implied: W11 diagnostics |
| Parameter stability tests | exp D03 | J | Implied: Section 11 Stability row |
| Out-of-sample calibration tests | exp D03 | J | Implied: Section 11 studies |
| Report: inputs with timestamps | exp D03 | B | Implied: W11 diagnostics |
| Report: initial and final parameters, objective, residuals | exp D03 | B | Implied: W11 diagnostics |
| Report: convergence status, iterations | exp D03 | B | Implied: W11 |
| Report: tolerance breaches | exp D03 | B | Implied: W11 |
| Report: sensitivity to quotes and starting parameters | exp D03 | B | Added: ZIP spec list only |
| Reproducible from frozen snapshot and model version | exp D03 | A | Implied: "snapshot hash"; "replay" |

## Domain 04: Pricing

| Item | Source | Stage | Status |
|---|---|---|---|
| Framework: Instrument, Product Model, Market Data, Pricing Model, Valuation Result | exp D04 | B | Explicit: "Pricing framework" |
| Valuation exposes PV, currency, model, data version, conventions, time, sensitivities | exp D04 | B | Implied: Pricing framework; W12 |
| Equity cash instruments | exp D04 | C | Implied: "Spot" |
| Equity forwards | exp D04; v1 | C | Explicit: W07; forward |
| Equity futures | exp D04 | D | Implied: "futures" |
| Equity options, European | exp D04 | C | Explicit: "BS" |
| American options | v1 s16 | E | Explicit: "American" |
| De-Americanisation | v2 s5 | C | Explicit: Row says "or European index options only", so it may be skipped |
| FX spot, forwards, swaps | exp D04 | B | Explicit: "FX forwards and swaps" |
| NDFs | exp D04 | D | Explicit: "NDF" |
| FX vanilla options | exp D04 | E | Added: No row names them |
| IRS | exp D04 | B | Explicit: "swap" |
| OIS | exp D04 | B | Explicit: "OIS" |
| FRAs | exp D04; v2 s5 | B | Added |
| Interest-rate futures | exp D04 | D | Explicit: "futures" |
| Caps, floors | exp D04 | D | Explicit: "caps"; floors assumed with caps |
| Swaptions | exp D04 | D | Explicit: "swaptions" |
| Bermudan swaptions | v2 s5 | G | Explicit: "Bermudans" |
| Bonds, clean/dirty, accrued, YTM | exp D04; v1 W7 | D | Explicit: "bonds" |
| Callable bonds | v2 s5 | G | Added |
| Floating-rate bonds | v2 s5 | D | Added |
| Repo | exp D04 | D | Explicit: "repo" |
| CDS | exp D04 | D | Explicit: "ISDA CDS" |
| Credit derivatives beyond CDS and index CDS | exp D04 | D | Added: Only CDS and index CDS named |
| Barriers, baskets, selected exotics | exp D04; v1 s16 | E | Explicit: Named |
| Multi-leg and multi-currency instruments | exp D04 | D | Implied: "cross-currency" |
| Variance swaps | v2 s5 | E | Explicit: Named |
| VIX-style index | v2 s5 | E | Added |
| Black-Scholes, Black-76, Bachelier | v1 W11 | C | Explicit: Named |

## Domain 05: Volatility

| Item | Source | Stage | Status |
|---|---|---|---|
| ATM volatility (VOL-01) | v1 C, 5.3 | C | Implied: W14 quote conventions |
| Strike smile (VOL-02) | v1 C, 5.3 | C | Explicit: "smile" |
| Delta smile (VOL-03) | v1 C, 5.3 | C | Implied: W14 quote conventions |
| 25-delta risk reversal (VOL-04) | v1 C, 5.3 | C | Implied: W14 |
| 25-delta butterfly (VOL-05) | v1 C, 5.3 | C | Implied: W14 |
| Term structure (VOL-06) | v1 C, 5.3 | C | Implied: "surface" |
| Surface (VOL-07) | v1 C, 5.3 | C | Explicit: "surface" |
| Forward volatility (VOL-08) | v1 C, 5.3 | E | Explicit: "forward vol" |
| Realised volatility (VOL-09) | v1 C, 5.3 | E | Implied: W17 |
| Historical, rolling, EWMA | exp D05 | E | Implied: W17 estimators |
| SABR (VOL-10) | v1 C, 5.3 | C | Explicit: "SABR" |
| Heston (VOL-11) | v1 C, 5.3 | E | Explicit: "Heston" |
| Swaption cube (VOL-12) | v1 C, 5.3 | E | Explicit: "swaption cube" |
| Cap/floor surface | v1 C | E | Explicit: "cap surface" |
| Bond futures implied vol | v1 C | E | Explicit: "bond futures vol" |
| Local vol, Dupire | v1 C; v2 s5 | E | Explicit: "local vol" |
| Stochastic local vol | v2 s5 | E | Explicit: "SLV" |
| SVI/SSVI | v2 s5 | C | Explicit: Named |
| Merton jump model | v2 s5 | E | Added: Bates named, Merton not |
| Bates | v2 s5 | E | Explicit: Named |
| GARCH and related forecasting | exp D05 | E | Explicit: "GARCH" |
| Implied vol solver | v1 W11 | C | Implied: W13 |
| Maturity interpolation | v1 C | C | Implied: "surface" |
| Arbitrage checks: calendar, butterfly | v1 C; exp D05 | C, E | Implied: "density check"; E demo |
| Density and Durrleman checks | v2 s5 | C | Implied: "density check" |
| Smile dynamics: sticky strike, sticky delta | v2 s5 | E | Added |
| Vol-of-vol analytics | v2 s5 | E | Added |
| Implied correlation | v2 s5 | E | Added: "correlation" reads as the catalogue curve, not index-implied |
| Dispersion | v2 s5; v1 A | E | Added |
| Normal and shifted-lognormal quote conversion | v2 s5; v1 C | C | Implied: Bachelier, Black, W14 |
| Vega, volga, vanna, skew risk | exp D05 | C | Implied: W18 |
| Stable characteristic functions | v2 s5 | A, E | Implied: "COS"; Heston |

## Domain 06: Risk and xVA

| Item | Source | Stage | Status |
|---|---|---|---|
| Delta (RISK-01) | v1 D, 5.4 | C | Explicit: "Greeks" |
| Gamma (RISK-02) | v1 D, 5.4 | C | Explicit: "Greeks" |
| Vega (RISK-03) | v1 D, 5.4 | C | Explicit: "Greeks" |
| Theta (RISK-04) | v1 D, 5.4 | C | Explicit: "Greeks" |
| Rho (RISK-05) | v1 D, 5.4 | C | Explicit: "Greeks" |
| DV01 (RISK-06) | v1 D, 5.4 | B | Explicit: "DV01" |
| Key-rate DV01 (RISK-07) | v1 D, 5.4 | B | Explicit: "key-rate" |
| CS01 (RISK-08) | v1 D, 5.4 | D | Implied: W21 part |
| Duration (RISK-09) | v1 D, 5.4 | B | Implied: W20 |
| Convexity (RISK-10) | v1 D, 5.4 | B | Implied: W20 |
| Portfolio risk (RISK-11) | v1 5.4 | F | Implied: W24 |
| Spread duration, credit exposure | exp D06 | F | Implied: W21 |
| FX delta | v1 D | B | Explicit: "FX delta" |
| Cross-currency exposure | exp D06 | F | Implied: W21, W24 |
| Correlation sensitivity | v1 D; exp D06 | F | Added: Named as a gap in v2 s2; no row or ticket |
| Inflation01 | v1 D | F | Added: Named as a gap in v2 s2; no row or ticket |
| Dividend and borrow sensitivity | v1 W6 | F | Added |
| Parallel shifts, bucketed risk | v1 D | B | Implied: W20 |
| Twist and butterfly scenarios | v1 D, W16 | F | Implied: W23 |
| Full revaluation | v1 D | F | Implied: W23 |
| First- and second-order sensitivities | v1 D | F | Implied: W19; "cross-gamma" |
| Portfolio aggregation, cross-product netting | v1 D | F | Implied: W24 |
| Common risk representation across assets | v1 D | F | Implied: "factors" |
| Risk at instrument, trade, portfolio, group level | exp D06 | F | Implied: W24 |
| VaR | exp D06; v2 s5 | F | Implied: W22; should be named in the row |
| Monte Carlo VaR | v1 s16 | F | Added: W22 scopes historical or parametric |
| Expected shortfall | exp D06; v1 H | F | Implied: W22 |
| Stress testing, historical and hypothetical scenarios | exp D06 | F | Implied: W23 |
| Historical shock library | v2 s5 | F | Implied: W23; section 11 Scenarios |
| P&L explain with residual limits | exp D06; v2 s5 | F | Implied: W23 |
| Risk attribution | exp D06 | F | Explicit: "attribution" |
| Bump-and-revalue reconciled with analytic risk | exp D06 | C | Implied: W19 |
| AAD | v2 s5 | F | Explicit: "AD for named products" |
| Par-to-zero Jacobians | v2 s5 | F | Explicit: "Jacobians" |
| Vega grids | v2 s5 | C | Implied: W18 surface risk |
| Cross-gamma | v2 s5 | F | Explicit: Named |
| PCA curve factors | v2 s5 | F | Explicit: "PCA" |
| Carry and roll-down | v2 s5; v1 H | J | Implied: Section 11 Carry row needs it; no build item named |
| Reverse stress | v2 s5 | F | Explicit: Named |
| Risk backtests: Kupiec, Christoffersen, traffic light, Acerbi-Szekely | v2 s5, s11 | J | Implied: Section 11 studies |
| Liquidity-adjusted risk | v2 s5; v1 H | F | Explicit: Named |
| Limits and breach alerts | v2 s5 | F | Implied: "limits" |
| FRTB-style sensitivities | v2 s5 | F | Explicit: "FRTB-style" |
| SIMM-style IM | v2 s5 | G | Explicit: Named |
| Model-risk reserves | v2 s13 | F | Explicit: Named |
| Counterparty exposure curve | v1 F | G | Explicit: "exposure" |
| CVA, DVA, FVA, MVA curves | v1 F | G | Explicit: Named |
| Wrong-way risk | v1 s16 | G | Explicit: Named |
| Vasicek, CIR, Hull-White, G2++, LMM | v1 s16; v2 s5 | G | Explicit: Named |
| KVA | plan G | G | Explicit: owner addition |

## Domain 07: Portfolio

| Item | Source | Stage | Status |
|---|---|---|---|
| Position and exposure aggregation | exp D07 | F | Implied: W24 |
| Multi-asset, multi-currency valuation | exp D07 | F | Implied: W24 |
| Net and gross exposures | exp D07 | F | Implied: W24 |
| Factor exposure (value, momentum, quality, size) | exp D07; v1 H | F | Explicit: "factors" |
| Sector exposure | exp D07 | F | Implied: "factors" |
| Correlation and covariance analysis, covariance matrix | exp D07; v1 H | A, F | Implied: "statistics"; W24 |
| Concentration risk | exp D07 | F | Added: ZIP spec list only |
| Liquidity risk | exp D07 | F | Implied: "liquidity-adjusted risk" |
| Portfolio P&L and attribution | exp D07 | F | Explicit: "attribution" |
| Portfolio constraints and limits | exp D07 | F | Explicit: "limits" |
| Scenario aggregation and reporting | exp D07 | F | Implied: W23 |
| Equity beta curve | v1 H | F | Implied: "factors"; beta hedges in I |
| Correlation term structure | v1 H | E | Implied: "correlation" |
| Portfolio volatility across holding periods | v1 H | F | Added |
| Drawdown curve | v1 H | J | Added: In BLUEPRINT_v2 phase 10, dropped from the plan row |
| Expected shortfall curve | v1 H | F | Implied: W22 |
| Liquidity-adjusted risk curve | v1 H | F | Explicit: Named |
| Risk contribution curve | v1 H | F | Implied: "attribution"; risk parity in J |
| Funding curve | v1 H | F | Added: In BLUEPRINT_v2 phase 10, dropped from the plan row |
| Carry curve | v1 H | J | Implied: Section 11 Carry row |
| Roll-down curve | v1 H | J | Implied: Section 11 Carry row |

## Domain 08: Hedging

| Item | Source | Stage | Status |
|---|---|---|---|
| Single-instrument hedge | v1 Phase 6 | B | Implied: W25 |
| Multi-instrument hedge (HEDGE-04) | v1 5.4; exp D08 | I | Implied: W25 |
| Delta hedge (HEDGE-01) | v1 E, 5.4 | I | Explicit: Named |
| Gamma hedge | v1 E | I | Explicit: Named |
| Vega and volatility hedge | v1 E; exp D08 | I | Explicit: Named |
| DV01 hedge (HEDGE-02) | v1 E, 5.4 | B | Explicit: "swap, DV01" |
| Key-rate hedge (HEDGE-03) | v1 E, 5.4 | B | Explicit: Named |
| Duration hedge | v1 E | B | Implied: W25; DV01 hedge |
| Equity beta hedge | v1 E | I | Explicit: "beta" |
| Credit hedge | v1 E | I | Explicit: "credit" |
| Correlation hedge | v1 E | I | Explicit: "correlation" |
| Cross-asset hedge curve (equity/rates) | v1 E | I | Added: Multi-instrument solver could carry it; no such hedge named |
| Cross-currency hedge | exp D08 | B | Implied: "FX hedges" |
| Dynamic hedge, rebalancing | v1 E; exp D08 | I | Explicit: "dynamic hedge backtest" |
| Hedge effectiveness | exp D08 | I | Implied: Dynamic hedge backtest |
| Minimum-variance hedge | exp D08 | I | Explicit: Named |
| Constrained least-squares hedge (HEDGE-05) | exp D08; v1 W18 | I | Explicit: "QP" |
| Integer contracts | v1 E | I | Explicit: "integer solvers" |
| Instrument selection | v1 E | I | Implied: W26 eligibility |
| Transaction cost and bid/offer optimisation | v1 E | B, I | Implied: Cost model in B; W26 |
| Liquidity constraints | v1 E | I | Explicit: Named |
| Market impact in hedge cost | v1 E | I | Implied: W26 costs |
| Margin requirements | v1 E | I | Explicit: "margin constraints" |
| Position and portfolio constraints | v1 E | I | Implied: W26 bounds |
| Residual risk reporting | v1 E; W17 | I | Implied: W25 |
| Hedge slippage estimation | v1 Phase 6 | I | Implied: W26 costs |
| Real-time hedge calculation | v1 Phase 7 | K | Added |
| Risk against cost frontier | v1 W18 | I | Implied: W26 |
| Singular matrix handling | v1 W17 | I | Implied: QP solvers; conditioning row in section 11 |

## Domain 09: Microstructure

| Item | Source | Stage | Status |
|---|---|---|---|
| Limit order book reconstruction | exp D09 | H | Explicit: "Book" |
| Market-by-order and market-by-price | exp D09 | H | Implied: W27 event-driven updates |
| Bid/ask spread curve (EX-01) | v1 G, 5.5 | H | Implied: W28 |
| Depth curve (EX-02) | v1 G, 5.5 | H | Implied: W28 |
| Queue position, dynamics (EX-03) | v1 G, 5.5 | H | Implied: W28 |
| Order arrival and cancellation rates | exp D09 | H | Added |
| Order-flow imbalance | exp D09 | H | Implied: W28 |
| Fill probability (EX-04) | v1 G, 5.5 | H | Implied: W28 |
| Adverse selection (EX-09) | v1 G, 5.5 | H | Explicit: Named |
| Market resilience | exp D09 | H | Added |
| Liquidity decay curve | v1 G | H | Added |
| Liquidity prediction | v1 G | H | Added |
| Venue-level liquidity comparison | exp D09 | H | Implied: W30 |

## Domain 10: Execution

| Item | Source | Stage | Status |
|---|---|---|---|
| Market impact, square-root (EX-05) | v1 G, 5.5 | H | Implied: W29 impact baseline |
| Impact coefficient by instrument, venue, liquidity, regime | v1 G | H | Added |
| Volatility-impact curve | v1 G | H | Implied: W29; square-root form includes volatility |
| Temporary and permanent impact | exp D10 | H | Implied: "Almgren-Chriss" |
| Slippage (EX-06) | v1 G, 5.5 | H | Implied: W30 TCA |
| VWAP (EX-07), TWAP | v1 G, 5.5 | H | Implied: W29 |
| POV, participation (EX-08) | v1 G, 5.5 | H | Implied: W29 |
| Implementation shortfall | v1 G; exp D10 | H | Implied: W29 |
| Benchmarks: arrival, decision, VWAP | exp D10 | H | Implied: W30 TCA |
| Explicit and implicit costs | exp D10 | H | Implied: W30 TCA |
| Fill rate, completion, price improvement | exp D10 | H | Implied: W30 TCA |
| Venue quality and routing | exp D10 | H | Explicit: "SOR"; W30 |
| Smart order routing | v1 G | H | Explicit: "SOR" |
| Execution simulation, replay, simulated fills | exp D10 | H | Explicit: "simulated engine" |
| Almgren-Chriss | exp D10 | H | Explicit: Named |
| Passive against aggressive execution | v1 G | H | Added |
| Adaptive execution and dynamic schedule | v1 W21, s16 | H | Added |
| Market making: inventory-aware quoting, skew | v1 s16; v2 s13 | H | Explicit: "market making" |
| Market making: dynamic hedging | v1 s16 | H | Implied: "market making" |
| Live orders and real exchange connections | v1 s2; v1 1.3 | None | Excluded: Decided exclusion; simulated only |

## Domain 11: Research and backtesting

| Item | Source | Stage | Status |
|---|---|---|---|
| Historical market-data replay | exp D11 | A, H | Explicit: "replay" |
| Signal generation and evaluation | exp D11 | J | Added: ZIP spec list only |
| Feature engineering | exp D11 | J | Added: ZIP spec list only |
| Portfolio construction | exp D11 | J | Explicit: "mean-variance" |
| Mean-variance, risk parity, factor optimisation | v1 s16 | J | Explicit: Named |
| Event-driven backtesting | exp D11 | J | Explicit: Named |
| Vectorised backtesting | exp D11 | J | Explicit: Named |
| Transaction-cost modelling in backtests | exp D11 | J | Implied: Cost models from B and H |
| Walk-forward validation | exp D11 | J | Explicit: Named |
| Out-of-sample testing | exp D11 | J | Implied: "walk-forward" |
| Look-ahead and survivorship controls | exp D11 | J | Explicit: "bias tests" |
| Performance attribution and risk-adjusted metrics | exp D11 | J | Added: F attribution is risk, not strategy performance |
| Curve history store | v2 s5 | A, K | Explicit: "as-of store"; "bitemporal store" |
| As-of and bitemporal queries | v2 s5 | K | Explicit: Named |
| Regime views | v2 s5 | J | Added |
| Signal and RV screens | v2 s5 | J | Added |

## Domain 12: Platform and governance

| Item | Source | Stage | Status |
|---|---|---|---|
| Market-data ingestion and normalisation | exp D12 | A, K | Implied: Recorder in A; feeds in K |
| FIX and ITCH-format simulated feeds | v1 s2 | K | Explicit: Named |
| FAST, OUCH, multicast formats (simulated) | v1 s2 | K | Added: Real connections are out; simulated formats are unscheduled |
| Reference data, instrument mapping | v1 s2 | K | Implied: "PostgreSQL" |
| Immutable snapshot management | exp D12 | A | Explicit: "snapshot hash" |
| Atomic, versioned snapshot publication | v1 W22 | K | Implied: "Incremental updates"; wording dropped from v2 phase 11 |
| Model and configuration versioning | exp D12 | K | Implied: "governance" |
| Reproducible calculation runs | exp D12 | A | Explicit: "replay" |
| Incremental updates | v1 s2 | K | Explicit: Named |
| Recalibration triggers | v1 s2 | K | Explicit: Named |
| REST/gRPC APIs | exp D12 | K | Explicit: "gRPC/REST" |
| Per-language APIs | exp D12 | K | Implied: W32; change 2 in v2 s13 |
| Cross-language bindings (pybind11, PyO3, JNI) | v1 s3 | None | Excluded: Banned by plan rule 1 |
| Arrow, Aeron, Kafka, PostgreSQL, ClickHouse | v1 s3 | K | Explicit: Named |
| Event-driven integration | exp D12 | K | Implied: "Kafka" |
| Batch and streaming calculations | exp D12 | K | Implied: "Kafka"; "Incremental updates" |
| Observability, metrics, structured logging | exp D12 | K | Explicit: "Prometheus/Grafana"; W32 |
| Performance and memory profiling | exp D12 | K | Implied: W34 |
| Audit trails | exp D12; v1 Phase 8 | K | Implied: "governance" |
| Failure recovery and failover | exp D12; v1 Phase 8 | K | Implied: W35 |
| Operational dashboards, curve explorer | v2 s5; v1 Phase 8 | K | Explicit: "dashboard" |
| Lock-free snapshots, low-latency risk | v1 s16 | K | Added: Keep as latency-aware analytics on simulated data |
| Intraday risk, approximation with error bounds | v1 s2 | K | Added |
| HFT trading application | v1 s2 | None | Excluded: Part of the simulated-only decision; plan s8 makes no HFT claims |
| Model inventory | v2 s5 | K | Implied: "governance" |
| Assumptions and limitations register | v2 s5 | K | Implied: "governance" |
| Calibration drift monitors | v2 s5 | K | Implied: "governance" |
| Challenger models | v2 s5 | K | Added: Needs models, not only paperwork |
| Change approval records | v2 s5 | K | Implied: "governance" |
| Data lineage | v2 s5 | K | Implied: "governance" |
| ADRs | v2 s5 | A | Implied: W01 |
| SBOM | v2 s5 | K | Added |
| Signed releases | v2 s5 | K | Added |
| Licence checks on every dataset | v2 s5 | A | Implied: "data-availability" table; plan s8 |
| Threat model | v2 s5 | K | Implied: W35 security |
| Fuzzing of parsers | v2 s5 | A | Explicit: "fuzz" |
| Reproducible builds | v2 s5 | K | Implied: "Clean-machine run" |
| CLI | v2 s5 | A | Explicit: "CLI" |
| Jupyter notebooks | v2 s5 | K | Explicit: "notebooks" |
| Learning path | v2 s5 | K | Implied: LEARN, plan s6 |
| Public results page from CI | v2 s5 | K | Added: Docs site is not this |

## Test layers: software (v2 s11, v1 s6)

| Item | Source | Stage | Status |
|---|---|---|---|
| Unit tests | s11 | All | Implied: Stage exit |
| Property-based tests | s11 | All | Implied: Stage exit; content of the "minimum test set" is undefined |
| Integration tests | s11 | All | Implied: Stage exit |
| Regression against stored results | s11 | K | Implied: W36 |
| Golden and cross-language conformance | s11 | A | Explicit: "conformance CI" |
| Fuzzing | s11 | A | Explicit: "fuzz" |
| Mutation testing | s11 | A | Explicit: "mutation" |
| Concurrency and race tests | s11 | K | Added: In BLUEPRINT_v2 phase 12, dropped from the plan row |
| Sanitizers | s11; v1 s10 | A | Added: In BLUEPRINT_v2 phase 12, dropped from the plan row |
| Memory-leak and soak tests | s11 | K | Added |
| API and schema compatibility | s11 | K | Implied: W35 schema evolution |
| Serialisation round trips | s11 | A | Implied: "snapshot hash" |
| Clean-machine build | s11 | K | Explicit: Demo |
| Example and documentation code in CI | s11 | K | Implied: Demo covers examples; docs code not stated |
| v1 layers: mathematical, calibration, market, risk, performance | v1 s6 | A-K | Implied: Stage exit; W34 |

## Test layers: model validation and backtests (v2 s11)

| Item | Source | Stage | Status |
|---|---|---|---|
| Independent replication | s11 | A-K | Explicit: Stage exit oracle |
| Calibration repricing | s11 | D | Explicit: "All instruments reprice" |
| Challenger and benchmarking | s11 | J | Implied: Section 11 studies |
| Assumption tests | s11 | J | Implied: Section 11 studies |
| Stability | s11 | J | Implied: Section 11 studies |
| Limit cases | s11 | J | Implied: Section 11 studies |
| Arbitrage tests | s11 | E | Explicit: Demo |
| Convergence | s11 | J | Implied: Section 11 studies |
| Conditioning | s11 | J | Implied: Section 11 studies |
| Ongoing monitoring with alerts | s11 | K | Implied: "governance"; no alert item |
| Backtests: curves, interpolation, vol surface, hedging, P&L explain, VaR/ES | s11 | J | Implied: Section 11 studies; plan s8 limits data |
| Scenario replay 2008, 2013, 2020, 2022, 2023 | s11 | J | Implied: Section 11 studies |
| Backtests: credit, xVA exposure, execution, carry | s11 | J | Implied: Section 11 studies; some are method tests |
| Backtest rules: point-in-time, fixed split, registered design | s11 | J | Implied: Section 11 studies |
| Multiple-testing adjustment, confidence intervals | s11 | J | Implied: Section 11 studies |

## Test layers: operational (v2 s11)

| Item | Source | Stage | Status |
|---|---|---|---|
| End-of-day run rehearsal | s11 | K | Added |
| Late or bad data | s11 | K | Implied: W35 failure modes |
| Failed calibration keeps last good curve | s11; v1 W22 | K | Implied: W35 failure modes |
| Restart and recovery | s11 | K | Implied: W35 |
| Deterministic replay | s11 | A | Explicit: "replay" |
| Reproducing an old valuation | s11; v1 1.2 | A | Implied: "as-of store and replay" |
| Holiday, clock-change, year-end, leap days | s11 | A | Implied: W02; clock change not stated |
| Load and burst tests | s11 | K | Added |
| Latency percentiles, throughput, memory, GC | s11 | K | Implied: W34 |
| Capacity limits | s11 | K | Added |
| Dependency failure | s11 | K | Implied: W35 failure modes |
| Security scans | s11; v1 s10 | K | Implied: W36 |

## New-model testing (v2 s12)

| Item | Source | Stage | Status |
|---|---|---|---|
| Known-truth simulation | s12 | H, J | Implied: Plan s8 for execution only; other domains not stated |
| Misspecification test | s12 | J | Added |
| Analytic and limit cases | s12 | A-K | Explicit: Stage exit oracle |
| Independent replication (second method) | s12 | A-K | Explicit: Stage exit oracle |
| No-arbitrage and invariants | s12 | C, E | Implied: Density check; E demo |
| Proxy data | s12 | J | Added |
| Benchmark model | s12 | J | Added |
| Sensitivity and stress on model parameters | s12 | J | Added |
| Parameter uncertainty | s12 | F | Implied: "model-risk reserves" |
| Expert review | s12 | K | Implied: Plan s8: after the project; fresh-session review until then |
| Scenario narratives | s12 | J | Added |
| Shadow run | s12 | J | Added |
| Forward test | s12 | A | Explicit: "forward log" |
| Staged rollout | s12 | J | Added: Nothing goes live; decide or exclude |
| New-model rules: purpose, range, triggers, fallback model | s12 | J | Added |
| Evidence labels | s12 | A | Implied: Plan rule 6 |
| Forward log append-only, format schema | s12 | A | Explicit: "forward log" |
| Conditional verdicts | s12 | K | Implied: Plan s8 evidence limit |
| New-model checklist | s12 | J | Added |
| Simulation harness in each implementation | s12 | J | Added |
| LEARN new-model chapter | s12 | K | Implied: "final docs" |

## Documentation deliverables

| Item | Source | Stage | Status |
|---|---|---|---|
| README, LEARN, COOKBOOK, ARCHITECTURE, CHANGELOG, GLOSSARY, ROADMAP | plan s6; v1 s8 | K | Explicit: "final docs"; review per stage (rule 8) |
| Per-package README and API docs | plan s6 | K | Implied: Plan s6; "final docs" |
| Per-curve spec set | v1 s8; exp s6 | All | Implied: Plan s5 rewrite specs before each stage |
| Validation report per model | s11 | All | Implied: Plan s6 |
| Diagrams | plan s6 | K | Implied: "final docs" |
| Docs site in CI | plan s6 | K | Implied: "final docs" |
| Spec questions, including computational complexity | v1 s8 | All | Implied: Spec rewrite |
| Test plan and traceability matrix | s11 | A | Explicit: Plan s4 traceability table |
| Backtest reports with design, manifest, commit, rerun command | s11 | J | Explicit: "Published study reports" |
| Known-issues register | s11 | K | Added |
| Runbooks for failed builds and recovery | s11 | K | Added |
| Release evidence pack | s11; v1 s13 | K | Added |
| CI-published conformance matrix | s11; exp s6 | A | Implied: "conformance CI" |
| LEARN "Validate and backtest" chapter, COOKBOOK recipes | s11 | K | Implied: "final docs" |
| Exercises with data and solutions | v1 s11 | None (add to All) | Added: Plan s5 says add; no stage owns it |
| Final engineering report | v1 W24 | K | Implied: W36 |

## Benchmark deliverables

| Item | Source | Stage | Status |
|---|---|---|---|
| Single-instrument pricing latency | exp s8 | K | Explicit: "benchmarks" |
| Portfolio pricing throughput | exp s8 | K | Explicit: "benchmarks" |
| Curve construction latency | exp s8 | K | Explicit: "benchmarks" |
| Calibration time and convergence | exp s8; v1 W23 | K | Explicit: "benchmarks" |
| Risk calculation throughput | exp s8 | K | Explicit: "benchmarks" |
| Market-data ingestion rate | exp s8 | K | Implied: W34 kernels |
| Order-book reconstruction latency | exp s8 | K | Implied: W34 kernels |
| Execution simulation throughput | exp s8 | K | Implied: W34 workflows |
| Peak memory and allocation rate | exp s8; v1 W23 | K | Implied: W34 |
| Tail latency p95, p99, p99.9 | exp s8 | K | Implied: W34 |
| C++ and Rust cache behaviour, Java GC, Python vectorised split | exp s8 | K | Implied: W34 |
| Each language benchmarked for its role | v2 s13 | K | Implied: "benchmarks" |
| Hardware, dataset, warm-up disclosure | exp s8 | K | Implied: Plan rule 6 |
| Numerical error measured beside latency | v1 s6 | K | Implied: "benchmarks" |
| Baseline and regression threshold per capability | exp s10 | K | Added |
| Curve lookup, batch bond, concurrent reader benchmarks | v1 s6, W23 | K | Implied: W34 |

## Use cases and milestones

| Item | Source | Stage | Status |
|---|---|---|---|
| Use cases 1 and 2 | exp s11 | B | Explicit: Demo |
| Use case 3 | exp s11 | C | Explicit: Demo |
| Use case 4 | exp s11 | F | Explicit: Demo |
| Use case 5 | exp s11 | H | Explicit: Demo |
| Use case 6 | exp s11 | I | Explicit: Demo |
| v1 milestones M1-M9, M11 | v1 s8 | B-I | Implied: Covered by stage demos |
| M10 replay and intraday analytics | v1 s8 | K | Implied: "Incremental updates" |
| M12 connect to simulated engine | v1 s8 | H | Explicit: "simulated engine" |
