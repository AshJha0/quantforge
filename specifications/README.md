# Specification index

A specification says what must be true before any language implements it. No non-trivial model starts until its equations, conventions, inputs, outputs, failure modes, validation cases and acceptance criteria are written down.

The contract every implementation's CLI follows is `cli-contract.md`.

| Domain | Folder | Stage | State |
|---|---|---|---|
| 01 Foundation | `01-core` | A | Real specs; see its README |
| 02 Curves | `02-curves` | B, D | Capability list, plus `stage-b-targets.md` |
| 03 Calibration | `03-calibration` | B, D | Capability list |
| 04 Pricing | `04-pricing` | B to E | Capability list |
| 05 Volatility | `05-volatility` | C, E | Capability list |
| 06 Risk and xVA | `06-risk` | F, G | Capability list |
| 07 Portfolio | `07-portfolio` | J | Capability list |
| 08 Hedging | `08-hedging` | B, I | Capability list |
| 09 Microstructure | `09-microstructure` | H | Capability list |
| 10 Execution and market making | `10-execution` | H | Capability list |
| 11 Research and backtesting | `11-research` | J | Capability list |
| 12 Platform and governance | `12-platform` | K | Capability list |

Domains 02 to 12 are not specified yet. Each real spec is written before its own stage, with numeric targets first, and nothing in those folders has been implemented. `02-curves/stage-b-targets.md` is the first of these targets.
