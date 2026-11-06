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
```

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

## Curve lifecycle

```mermaid
flowchart LR
  Q[quotes] --> V[checks] --> Sn[snapshot] --> B[build and calibrate]
  B --> Rp{inputs reprice?}
  Rp -->|yes| Pub[publish curve]
  Rp -->|no| Keep[keep last good curve, report failure]
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
