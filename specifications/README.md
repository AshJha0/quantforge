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

## Spec template: required sections (stage F, rule F-6)

Every spec page that defines an operation has, in this order: purpose; inputs and outputs (with units in key names, F-5); conventions with a primary-source citation for each; the error checks in order (the F-2 finite check is always first and is not repeated); validation cases and their oracle; acceptance criteria.

A page that defines a numerical method (iterative solve, grid, quadrature, tree, Monte Carlo, optimiser) also has:

```
## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| <name> | <p, as error = O(h^p) or O(N^-p)> | <grid, step or path sequence, at least 4 levels, ratio 2> | <the parameter limit> | <closed form or independent method> |
```

The asserted order must be met by the observed order from the last three levels within 0.2 (for Monte Carlo: the standard error falls as N^-0.5 within 0.1 over 4 doublings). The quality_gate check (infra lane) fails a page with a numerical method and no such section, or with an empty table.
