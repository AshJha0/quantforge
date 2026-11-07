# Calibration core

Spec version 1.0.0. Status: Implemented, not Validated.

Calibration fits parameters to data. Different solvers take different paths, so results are judged on the objective and on repricing. Parameters are compared only when the minimum is unique and well identified, and never by iteration count.

Proven numerical libraries are allowed here (plan rule 4).

## `calib.fit`

Inputs:

| Key | Meaning |
|---|---|
| `model` | `LINEAR`, `EXPONENTIAL`, `NELSON_SIEGEL`, `ROSENBROCK` |
| `x`, `y` | Data, same length (`E_INPUT` otherwise). Empty for `ROSENBROCK` |
| `start` | Initial parameters, of the model's length, else `E_INPUT` |
| `method` | `GAUSS_NEWTON`, `LEVENBERG_MARQUARDT`, `BFGS` |
| `weights` | Optional, default 1. Negative: `E_DOMAIN` |
| `regularisation` | Optional `lambda >= 0`, default 0, else `E_DOMAIN` |
| `prior` | Optional, default zeros |
| `lower`, `upper` | Optional bounds. `LEVENBERG_MARQUARDT` only; other methods: `E_INPUT` |
| `max_iter` | Optional, default 1000 |
| `report_parameters` | Optional, default true. False leaves `parameters` out, for models judged on fit alone |

Outputs: `parameters`, `objective`. Diagnostics, required: `iterations`, `status`, `residuals`. They are not compared.

Objective: `sum w_i (m(x_i; p) - y_i)^2 + lambda |p - prior|^2`.

| Model | `m(x; p)` |
|---|---|
| `LINEAR` | `p0 + p1 x` |
| `EXPONENTIAL` | `p0 exp(-p1 x)` |
| `NELSON_SIEGEL` | `p0 + p1 e + p2 (e - exp(-x/p3))`, `e = (1 - exp(-x/p3))/(x/p3)` |
| `ROSENBROCK` | Objective is `(1 - p0)^2 + 100 (p1 - p0^2)^2` |

Methods:
- `GAUSS_NEWTON`: full step `-(J^T W J)^-1 J^T W r`, halved until the objective falls. A singular `J^T W J`: `E_SINGULAR`.
- `LEVENBERG_MARQUARDT`: damped Gauss-Newton. With bounds, steps are projected on the box, so the result meets the first-order conditions of the bounded problem.
- `BFGS`: inverse-Hessian updates with a line search.

Stop when the gradient norm is at most 1e-8, or the step is at most 1e-12 relative. Reaching `max_iter`: `E_NO_CONVERGENCE`. For non-finite values, see `../stage-b-rulings.md`, B22. Jacobians may be analytic or numeric.

`ROSENBROCK` is used with `BFGS` only; `NELSON_SIEGEL` is not used with `GAUSS_NEWTON`, whose unsafeguarded steps suit it badly.

## `calib.check_bid_ask`

Inputs: `fitted`, `bid`, `ask`, same length (else `E_INPUT`). `bid > ask`: `E_INPUT`. Output: `breaches`: `{index, side, distance}` for each fitted value outside its quote, with `side` `BID` or `ASK`. A value on the boundary is inside.

## `calib.curve_report`

The calibration sensitivity report. Inputs: as `rates.ois.bootstrap`, less `method`. Outputs: `jacobian`, with row `i`, column `j` being `d z_i / d q_j`, the zero rate at pillar `i` against quote `j`, both as decimals; and `condition_number`, the 2-norm condition number of it. Analytic or bumped; a central bump of 1e-5 is the reference. Diagnostics, required: inputs with their timestamps if given, `status`, `max_repricing_error`, and any tolerance breach. Large condition numbers mean quotes barely pin a pillar.

## Acceptance

Unique minima: parameters within 1e-6, objective with them. Known-truth cases: objective zero. `NELSON_SIEGEL` is judged on objective at 1e-10 only, because its parameters are poorly identified. Oracle: closed forms, NumPy, SciPy. `gen_stage_b.py` checks that plain Gauss-Newton, BFGS and Levenberg-Marquardt reach these minima, so no case rests on one solver's path.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Nocedal, J. and Wright, S. J., *Numerical Optimization*, 2nd ed., Springer, 2006, chapter 6 (BFGS) and chapter 10 (Gauss-Newton, Levenberg-Marquardt) (not opened)
- [S2] Marquardt, D. W., "An algorithm for least-squares estimation of nonlinear parameters", *SIAM Journal on Applied Mathematics* 11(2), 1963, 431-441 (not opened)
- [S3] Nelson, C. R. and Siegel, A. F., "Parsimonious modeling of yield curves", *Journal of Business* 60(4), 1987, 473-489 (not opened)
