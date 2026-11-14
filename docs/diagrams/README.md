# Diagrams

Mermaid, which GitHub draws directly and the site draws in its light or dark theme. The stage J diagrams carry a title and a description for screen readers (`accTitle`, `accDescr`), and the paragraph under it says the same in words. Per-domain flows are added with each domain's specs.

## System

```mermaid
flowchart LR
  S[specifications] --> O[oracle]
  S --> J[java25] & C[cpp26] & P[python] & R[rust]
  O --> G[golden files]
  G --> N[neutral runner]
  J & C & P & R -->|result JSON| N
  N --> Rep[conformance report]
  B[batch stream fixtures] --> BC[batch_check]
  J & C & P & R -->|quantforge --batch| BC
```

From R1 (contract 1.6.0), batch mode is checked on its own: `datasets/batch/streams.json` feeds `conformance/runner/batch_check.py`, apart from the goldens.

## Domain dependencies

```mermaid
flowchart TD
  D01[01 Foundation] --> D02[02 Curves] & D03[03 Calibration]
  D03 --> D02
  D02 --> D04[04 Pricing]
  D04 --> D05[05 Volatility]
  D04 & D05 --> D06[06 Risk and xVA]
  D06 --> D07[07 Portfolio] & D08[08 Hedging]
  D01 --> D09[09 Microstructure] --> D10[10 Execution]
  D07 & D10 --> D11[11 Research]
  D11 --> D12[12 Platform]
```

Domain 11 has CLI operations from stage J wave 1 (backtester, purged CV, Viterbi regimes, research statistics). Its `research` module in each build uses only domain 01; the arrows from 07 and 10 are where studies will take their inputs, not code dependencies.

```mermaid
flowchart LR
  In[prices, targets, labels, returns] --> BT[research.backtest.run]
  In --> CV[research.cv.purged_kfold / cpcv_paths]
  In --> VT[research.regime.viterbi]
  BT -->|returns| ST[research.stats.psr / dsr / pbo / power]
  CV -->|fold returns| ST
  ST --> Rep[study report]
```

## Data flow

```mermaid
flowchart LR
  Src[public sources] --> Rec[recorder]
  Rec --> Raw[raw files, not committed]
  Rec --> Log[forward log: hashes]
  Raw --> Chk[quote checks] --> Store[as-of store]
  Store --> Snap[snapshot and hash] --> Calc[calculation]
  Calc --> Res[result with provenance]
```

## R1 scheduled jobs

GitHub Actions, free runners, no secrets beyond `GITHUB_TOKEN`. Raw data stays on the runner.

```mermaid
flowchart LR
  Src[15 public sources] --> Rec[recorder.yml: record.py]
  Rec --> FL[(forward-log branch)]
  Rec --> Gap[gap_monitor.py] --> FL
  Src --> WF[daily-workflows.yml: eod_curves, sofr_check]
  WF -->|cases| CLI[quantforge --batch]
  CLI -->|results| WF
  WF --> Bands[sanity bands] --> FL
```

## Curve lifecycle

What stage B builds. Each step is one call to the CLI on the inputs it is given, and nothing is stored between calls. A solve that fails is an error, never a clamped curve.

```mermaid
flowchart LR
  Q[synthetic quotes] --> V{input checks}
  V -->|bad| E1[E_INPUT]
  V --> M[mid of bid and ask] --> S[schedules] --> B[bootstrap: sequential or global]
  B -->|no solution| E2[E_NO_CONVERGENCE]
  B --> C[curve and max repricing error]
  C --> P[PV, FX forwards] & R[bump quotes, rebuild: DV01, key rates]
  R --> H[hedge solve with cost]
```

The target for later stages, not built yet: quotes pass the data checks, are frozen in a hashed snapshot, and a curve is published only if its inputs reprice.

```mermaid
flowchart LR
  Q[quotes] --> V[checks] --> Sn[snapshot] --> B[build and calibrate]
  B --> Rp{inputs reprice?}
  Rp -->|yes| Pub[publish curve]
  Rp -->|no| Keep[keep last good curve, report failure]
```

## Valuation parts

The five parts of `specifications/04-pricing/pricing-framework.md`.

```mermaid
flowchart LR
  I[instrument: terms] --> PM[product model: cashflows]
  PM --> M[pricing model: discounting]
  D[market data: curves, spot] --> M
  M --> V[valuation result]
```

## Conformance flow

```mermaid
sequenceDiagram
  participant G as Golden file
  participant N as Runner
  participant I as Implementation CLI
  G->>N: cases with expected values
  N->>I: cases, expected values removed
  I->>N: result JSON
  N->>N: compare by tolerance class
  N->>N: write report
```

## Stage E: volatility and exotics

Plain idea: stage E builds on the stage D curves and pricers rather than beside them. Each box names its slice and spec page; the goldens for spec A live in `datasets/golden/stage_e/` (446 cases) and for spec B in `datasets/golden/stage_e_b/` (449 cases).

```mermaid
flowchart LR
  D[stage D curves and pricers] --> E1[E1 SVI/SSVI surfaces, Dupire local vol, forward vol]
  E1 --> E2[E2 Heston, Bates, Merton, SLV leverage]
  D --> E3[E3 FX smile, delta and ATM conventions]
  D --> E4[E4 SABR swaption cube, caplet strip, bond futures options, inflation caps]
  E1 --> E5[E5 exotics and American options]
  D --> E6[E6 correlation repair, implied correlation, dispersion]
  D --> E7[E7 GARCH, variance swaps, VIX-style index]
  D --> E8[E8 CDS options, copulas, large-pool tranches]
  E1 & E2 & E3 & E5 --> GA[goldens stage_e]
  E4 & E6 & E7 & E8 --> GB[goldens stage_e_b]
  GA & GB --> QL[QuantLib 1.44 outside check: 557 of 895]
```

## Stage F: from quotes to capital and the book

```mermaid
flowchart LR
  Q[OIS, term, futures and xccy quotes] --> JS[rates.curve.joint_solve]
  JS -->|curves| PV[pricers]
  JS -->|IFT Jacobian dx/dq| AAD[risk.book.ois_sensitivity]
  PV --> AAD
  PV -->|scenario P&L| VAR[risk.var.*]
  VAR -->|exceptions| BT[risk.backtest.*]
  AAD -->|delta sensitivities| FRTB[risk.frtb.girr_delta]
  EV[trades and lifecycle events] --> BK[book.lifecycle.apply]
  MK[quote sources and IPV prices] --> MR[book.marks.resolve]
  BK & MR --> PV
```

The joint solve feeds both the prices and the Jacobian that AAD carries back to the quotes (ruling F-29). VaR and the backtests work on P&L scenarios; FRTB-SA works on sensitivities. Specs: `02-curves/joint-solve-and-funding.md`, `06-risk/book-sensitivities.md`, `06-risk/var-es-and-backtests.md`, `06-risk/frtb-sa-girr.md`, `07-portfolio/book-lifecycle.md`.

## Stage I: hedging around one solver

```mermaid
flowchart LR
  BK[book risks b] --> QP[hedge.qp.solve]
  GR[Greeks of options] -->|A, b| GN[hedge.greeks.neutralise] --> QP
  CDS[credit.cds.price legs] -->|CS01, JTD| CR[hedge.credit.cds] --> QP
  RP[repricing on bumped curves] -->|A, b| XA[hedge.crossasset.solve] --> QP
  CO[half-spreads, impact, liquidity, margin] --> QP
  QP --> FR[hedge.frontier.solve]
  QP --> SEL[hedge.select.solve]
  BK -->|same objective, whole lots| INT[hedge.integer.solve]
  QP -->|x| RES[hedge.residual.report]
  PATH[spot path] --> BTD[hedge.backtest.delta] --> EFF[hedge.effectiveness]
  FILLS[orders and fills] --> SLP[hedge.slippage.report]
```

Every hedge that builds a risk matrix passes it to one constrained least-squares solve; the frontier and instrument selection call that solve repeatedly. The checks run in a fixed order, so a bad problem returns the same error code in every build (rulings I-3, I-14). Costs are solved by sign state (long, short or held at zero), with no cap below 200 instruments in the method (I-48), though at v0.8.0 no golden was larger than 6 by 4 (R6-6 adds n = 50 and 200) and exact answers at a switch point (I-54). Specs: `08-hedging/hedge-solvers.md`, `credit-and-correlation-hedges.md`, `cross-asset-hedge.md`, `hedge-costs-and-frontier.md`, `instrument-selection.md`, `dynamic-hedge-and-effectiveness.md`, `hedge-slippage.md`.

## Stage J: research tools

```mermaid
flowchart LR
  accTitle: Stage J research flow
  accDescr: Prices and targets go into the backtester; its per-bar net P&L feeds the probabilistic and deflated Sharpe ratios and, for many trials together, the PBO; purged cross-validation chooses which bars train and which test; the trial registry supplies the number of trials; regime labels describe the sample.
  PR[prices, targets] --> BT[research.backtest.run]
  BT -->|per-bar net P&L| PSR[research.stats.psr]
  REG[trial registry research/trials.csv] -->|N, variance of Sharpe| DSR[research.stats.dsr]
  BT -->|best trial| DSR
  BT -->|P&L of every trial| PBO[research.stats.pbo]
  CV[research.cv.purged_kfold] -->|train and test bars| BT
  CP[research.cv.cpcv_paths] -->|splits, paths| CV
  PW[research.stats.power] -->|minimum detectable Sharpe| REG
  RET[returns] --> VIT[research.regime.viterbi]
```

A study fixes its power and trial count first, backtests each trial with costs and a lag, and reports DSR and PBO beside the Sharpe ratio (plan 11.3). Regime labels describe the sample and never feed a signal (spec limitation). Specs: `11-research/backtester.md`, `purged-cv.md`, `regimes.md`, `research-statistics.md`. Worked through in [Tutorial 23](../getting-started/tutorial-23-backtest-honestly.md), [Tutorial 24](../getting-started/tutorial-24-is-the-sharpe-real.md) and the gallery page [Research workflow](../curves/research-workflow.md).

### Backtest timing: signal at t, trade at t + lag, P&L on the bar after

```mermaid
sequenceDiagram
  accTitle: Backtest event loop timing with lag 1
  accDescr: The strategy decides a target at the close of bar t using data up to that close. With lag 1 the backtester trades to that target at the close of bar t plus 1, paying spread, commission and a fixed fee. The price move over bar t plus 2 is earned by the position held after that trade. With lag 0 the trade would happen at the same close as the decision, which is only allowed for the look-ahead canary.
  participant S as Strategy
  participant B as Backtester
  participant L as P&L ledger
  Note over S,L: close of bar t
  S->>B: target[t], from data up to p_t
  Note over S,L: close of bar t+1 (lag 1)
  B->>B: q_{t+1} = target[t], trade d = q_{t+1} - q_t at p_{t+1}
  B->>L: cost = abs(d) p (half_spread_bps / 10^4) + abs(d) commission + fixed
  Note over S,L: close of bar t+2
  B->>L: gross = q_{t+1} (p_{t+2} - p_{t+1})
  L->>L: net = gross - cost, equity += net
```

The position that earns a bar's move is the one held before that bar's trade (ruling J-2). A rule computed from `p_t` and traded at `p_t` (lag 0) earns moves it could not have known; the canary in Tutorial 23 makes 21 at lag 0 and loses 10 at lag 1 on the same twelve prices.

### Purged k-fold with an embargo

```mermaid
flowchart LR
  accTitle: Purged k-fold split with an embargo, fold 1 of 3
  accDescr: Ten observations, each label covering three bars. The middle fold tests observations 4 to 6, whose labels span times 4 to 8. Observations 2 and 3 before the block and 7 and 8 after it have labels that overlap that span and are purged. A 30 percent embargo removes observations 7, 8 and 9 after the block. Only observations 0 and 1 remain for training.
  subgraph before[before the test block]
    O0[0 train] --- O1[1 train] --- O2[2 purged] --- O3[3 purged]
  end
  subgraph test[test block, labels span t = 4 to 8]
    O4[4 test] --- O5[5 test] --- O6[6 test]
  end
  subgraph after[after the test block]
    O7[7 purged and embargoed] --- O8[8 purged and embargoed] --- O9[9 embargoed]
  end
  before --> test --> after
```

Purging works on both sides of the block and removes any training row whose label window `[t0, t1]` touches the test span; the embargo, `floor(embargo_pct n)` rows, works only after it, where serial correlation carries information forward (rulings J-7, J-8). Numbers from Tutorial 23, `t1 = t0 + 2`, embargo 0.3.

### Combinatorial purged CV: splits to paths

```mermaid
flowchart TB
  accTitle: Combinatorial purged cross-validation with N = 6 groups and k = 2 test groups
  accDescr: Six groups G1 to G6. Every choice of two test groups is a split, fifteen in all. Each group is a test group in five splits. Taking one test result for each group from different splits builds a complete backtest path; there are 2 times 15 divided by 6, which is 5 paths.
  D[data in N = 6 contiguous groups G1 .. G6] --> S[C 6, 2 = 15 splits, each tests 2 groups and trains on 4, purged]
  S --> C[each group is tested in 5 of the 15 splits]
  C --> P1[path 1: G1 .. G6 each from a different split]
  C --> P2[path 2]
  C --> P3[path 3]
  C --> P4[path 4]
  C --> P5[path 5]
  P1 & P2 & P3 & P4 & P5 --> R[5 out-of-sample Sharpe ratios, not one]
```

`n_splits = C(N, k)` and `n_paths = k C(N, k) / N`, an integer because `k C(N, k) = N C(N-1, k-1)` (`research.cv.cpcv_paths`; López de Prado 2018, section 12.4). The operation returns the counts; assigning splits to paths is left to the research package.

### Portfolio pipeline

```mermaid
flowchart LR
  accTitle: Stage J wave 2 portfolio pipeline, from returns to a tested risk model
  accDescr: Returns go into Ledoit-Wolf, which gives a shrunk covariance. The covariance and market weights give the prior returns, which Black-Litterman moves towards the investor's views. Mean-variance takes the posterior returns, the covariance and the weight limits and gives weights; risk parity takes the covariance and risk budgets instead and ignores expected returns. Euler contributions split either portfolio's volatility by asset. After the portfolio has been held, its realised losses and the model's VaR and ES forecasts go into the Z2 backtest, and a Baum-Welch fit describes the calm and turbulent regimes of the same period.
  R[returns T x N] --> LW[research.estimate.ledoit_wolf: shrunk Sigma]
  LW --> PI[prior pi = delta Sigma w_mkt, caller]
  PI --> BL[research.estimate.black_litterman: views P, q, Omega]
  BL --> MV[research.portfolio.mean_variance: weights within limits]
  LW --> MV
  LW --> RP[research.portfolio.risk_parity: weights from risk budgets]
  MV --> EU[risk.contrib.euler: volatility by asset]
  RP --> EU
  EU --> H[hold, record losses and VaR, ES forecasts]
  H --> Z2[risk.backtest.es_z2: tail size tested]
  H --> BW[research.regime.baum_welch: regimes of the period]
```

Estimate, optimise, look at where the risk sits, then test the risk model on what happened. Every arrow is an input the caller passes; no operation calls another, so each step can be replaced or checked on its own. The prior `pi` is computed by the caller, as in [Tutorial 25](../getting-started/tutorial-25-build-and-stress-a-portfolio.md); the Z2 and Baum-Welch steps are in [Tutorial 26](../getting-started/tutorial-26-test-es-and-fit-regimes.md). Specs: `07-portfolio/estimation.md`, `07-portfolio/optimisation.md`, `06-risk/es-backtest.md`, `11-research/baum-welch.md` (rulings J-W2-1 to J-W2-15).

### Baum-Welch: the EM loop and its stop rule

```mermaid
flowchart TB
  accTitle: Baum-Welch iteration and stop rule for a Gaussian hidden Markov model
  accDescr: The run starts with an E-step at the start values, which gives the first log-likelihood. Each iteration is an M-step, which re-estimates the initial probabilities, the transition matrix and each state's mean and standard deviation from the state probabilities, followed by an E-step at the new parameters, which gives new state probabilities and a new log-likelihood. If the gain over the previous log-likelihood is below the tolerance, the run stops as converged. Otherwise, if the iteration count has reached the maximum, it stops as not converged. Otherwise it repeats. A zero scale factor, a zero denominator or a non-positive variance stops the run with E_DOMAIN.
  S[start values: initial, transition, means, sds] --> E0[E-step: scaled forward-backward, L_0]
  E0 --> M[M-step: pi, A, means, sds from gamma and xi]
  M --> E[E-step at new parameters: gamma, xi, L_k]
  E --> G{gain L_k - L_k-1 below tolerance?}
  G -- yes --> C[stop: converged true, parameters and L_k of this E-step]
  G -- no --> K{k = max_iterations?}
  K -- yes --> N[stop: converged false]
  K -- no --> M
  M -. zero denominator or variance at or below 0 .-> X[E_DOMAIN]
  E -. scale c_t = 0 .-> X
```

One iteration is an M-step followed by an E-step, and the outputs are the parameters and log-likelihood of the last E-step (ruling J-W2-11). The likelihood never falls [Rab89, DLR77], so gains shrink towards zero; each golden's tolerance sits at least `1e-11` from every gain it tests, so all four builds stop at the same iteration (J-W2-12). In Tutorial 26 a two-state fit on 24 returns stops after iteration 7 with tolerance `1e-6`, and after iteration 3, not converged, with `max_iterations` 3.
