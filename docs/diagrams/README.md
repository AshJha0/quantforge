# Diagrams

Mermaid, which GitHub draws directly. Per-domain flows are added with each domain's specs.

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
