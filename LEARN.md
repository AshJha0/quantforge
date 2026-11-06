# Learn QuantForge

A path through the project. Each topic goes from the plain idea, to the formal statement in a spec, to a worked example.

## Start here

QuantForge has four equal implementations of the same maths, in Java, C++, Python and Rust. None is the reference. Expected answers come from `oracle/`, because four programs agreeing proves only that they agree.

## Path for stage A

| Step | Plain idea | Read | Try |
|---|---|---|---|
| 1 | A year fraction depends on who is counting | `specifications/01-core/daycount.md` | EX-001 |
| 2 | Business days are rules plus surprises | `calendars.md` | Find why 2022-09-19 is a holiday |
| 3 | A rate needs its compounding | `compounding.md` | EX-002 |
| 4 | Solvers must say how they stopped | `root-finders.md` | EX-003 |
| 5 | Interpolation decides what your forwards look like | `interpolation.md` | Compare `linear` and `monotone_convex` forwards |
| 6 | Random numbers can be made reproducible | `rng.md`, `sobol.md` | Reproduce a golden case in `rng` |
| 7 | Three ways to price one option | `monte-carlo.md`, `pde.md`, `cos.md` | Price the same call all three ways |
| 8 | Never overwrite a number | `asof-store.md` | Follow a correction through the `store` cases |

## Worked example

A 182-day period from 2024-01-01 to 2024-07-01 is 182/360 = 0.50556 under ACT/360, and 182/365 = 0.49863 under ACT/365F. On 1,000,000 at 5%, simple interest differs by about 346 for the same dates.

## Validate and backtest

Stage A tests correctness with analytic, hand and outside-library answers. Later stages add calibration, backtests and new-model tests. Evidence is always labelled analytic, simulated, proxy or observed, and validation reports are self-assessment until the human review at the end of the project.
