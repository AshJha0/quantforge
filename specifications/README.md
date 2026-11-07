# Specification index

A specification says what must be true before any language implements it. No non-trivial model starts until its equations, conventions, inputs, outputs, failure modes, validation cases and acceptance criteria are written down.

The contract every implementation's CLI follows is `cli-contract.md`.

| Domain | Folder | Stage | State |
|---|---|---|---|
| 01 Foundation | `01-core` | A, B | Real specs; see its README |
| 02 Curves | `02-curves` | B, D | Stage B implemented; the rest a capability list |
| 03 Calibration | `03-calibration` | B, D | Stage B implemented; the rest a capability list |
| 04 Pricing | `04-pricing` | B to E | Framework and use cases 1, 2 implemented; the rest a capability list |
| 05 Volatility | `05-volatility` | C, E | Stage C at Specified; the rest a capability list |
| 06 Risk and xVA | `06-risk` | B, F, G | Stage B rates sensitivities implemented; the rest a capability list |
| 07 Portfolio | `07-portfolio` | J | Capability list |
| 08 Hedging | `08-hedging` | B, I | Stage B implemented; the rest a capability list |
| 09 Microstructure | `09-microstructure` | H | Capability list |
| 10 Execution and market making | `10-execution` | H | Capability list |
| 11 Research and backtesting | `11-research` | J | Capability list |
| 12 Platform and governance | `12-platform` | K | Capability list |

Stage A and the stage B specs are at Implemented: all four builds pass their golden cases. None is Validated, as validation is self-assessment until the human review after the project. Everything else in domains 02 to 12 is unspecified and unbuilt. Each real spec is written before its own stage, with numeric targets first; `02-curves/stage-b-targets.md` is the first of these targets. `stage-b-rulings.md` is normative for stage B and lists each suite's oracle. `stage-b-followups.md` is the build list, kept as a record. Stage C specs are at Specified: `stage-c-rulings.md` is normative for them, targets are in `05-volatility/stage-c-targets.md`, and `stage-c-handover.md` lists what a language session reads.
