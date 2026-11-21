# Multi-curve joint solve and its Jacobian

<p class="note">Hand-written page, listed under "Method pages" on the Curves index. Every number below is from the Python build in this repository, run on 2026-11-21 through <code>uv run --locked quantforge batch</code> on golden <code>joint_f-0003</code>; the outputs agreed with the golden to 2.1e-10 relative (measured, local laptop, not the acceptance machine). Inputs are synthetic.</p>

Back to [Curves](README.md).

**Plain idea.** Since 2008 a desk has used one curve to discount (the OIS curve, because collateral earns the overnight rate) and other curves to project floating rates (a 3-month term index, say). The projection curve's instruments are discounted on the OIS curve, so the two depend on each other's quotes. Building them one after the other works when the dependence runs one way; solving them together is the general method, and the same solve gives what risk needs: how every point of every curve moves with every quote, the Jacobian.

**Formal statement** (`specifications/02-curves/joint-solve-and-funding.md` 1.0.0, rulings F-24 to F-27; read 2026-11-21).

- `rates.curve.joint_solve` takes `curves` in dependency order (a curve may name only curves before it, else `E_INPUT`) of types `OIS`, `OIS_STEPS`, `PROJECTION` and `XCCY`, and `instruments` (OIS swaps and futures for OIS curves; deposits, FRAs and swaps for a projection curve; cross-currency basis swaps for `XCCY`).
- Unknowns: `ln D` at one pillar per instrument (at its last date); for `OIS_STEPS` the base rate and step rates; `ln factor` for each turn. Residual: model value minus quote. The system is square by construction.
- Solve all residuals to at most 1e-13. Because a curve's residuals depend only on its own unknowns and those of earlier curves, `dR/dx` is block lower triangular, and a build may solve curve by curve (F-25); with a non-local interpolation, nothing inside a block is triangular.
- `jacobian.matrix[i][j] = d unknown_i / d quote_j = -(dR/dx)^(-1) (dR/dq)`, by the implicit function theorem, at the solution. Rows are `<curve>:pillar:<date>` (or `:base`, `:step:<date>`, `:turn:<date>`), columns the instrument ids.
- `rates.curve.joint_bootstrap` (stage D, `specifications/02-curves/csa-and-basis.md`) is the earlier form for an OIS curve and its projection curve; `joint_f-0003` is described in its golden as the stage D joint-bootstrap equivalent.

**Worked example** (`joint_f-0003`). USD-SOFR from eight OIS quotes (1M 4.30% to 10Y 3.64%) and USD-TERM-3M from a 3-month deposit, two FRAs and 2, 5 and 10-year swaps discounted on USD-SOFR; both log-linear in `D`; as of 2026-11-09. 14 quotes, 14 unknowns.

Selected Jacobian entries (`d ln D / d quote`, quotes as decimals, so -0.10 means a 1 bp rise lowers `ln D` by 0.10 bp):

| Unknown | Largest entries |
|---|---|
| USD-SOFR pillar 2026-12-16 (1M) | SOFR-1M -0.10239, nothing else |
| USD-SOFR pillar 2027-11-16 (1Y) | SOFR-1Y -0.99676; SOFR-6M +0.01108; SOFR-1M -0.0083 |
| USD-SOFR pillar 2036-11-14 (10Y) | SOFR-10Y -10.80033; SOFR-5Y +0.70264; SOFR-3Y +0.17067 |
| USD-TERM-3M pillar 2027-02-12 | T-DEP -0.26092, nothing else |
| USD-TERM-3M pillar 2036-11-12 | T-SW10 -10.732; T-SW5 +0.78636; T-SW2 +0.14687; **SOFR-10Y +0.11329** |

How to read it. The diagonal is roughly minus the pillar's time in years scaled by its annuity: the 1-month pillar moves by about `-37/360 = -0.103` per unit of its own quote, and the 10-year by about -10.8 (inferred from the formula of a par rate). The positive entries on earlier quotes are the bootstrap's give and take: with the 10-year quote fixed, a higher 5-year rate means more of the 10-year swap's fixed leg is already paid for, so the 10-year discount factor rises (inferred, the same par-rate algebra). The bold entry is the multi-curve effect: the term curve's 10-year pillar moves with the SOFR 10-year quote, because the term swap is discounted on SOFR. A one-curve model has no such column. The SOFR rows have zeros in every term-curve column: the matrix is block lower triangular, as the dependency order says.

**Where it is used.** The same matrix turns risk to curve points into risk to quotes (the chain rule on [Curve risk](curve-risk.md)); a desk hedges quotes, not zero rates. The funding curve page ([Funding curve](funding.md)) builds on a solved OIS curve; meeting steps and turns are on [Meeting steps](meeting-steps.md).

**What goes wrong.** Two instruments on the same dates with different quotes make `dR/dx` singular, and the operation answers `E_NO_CONVERGENCE` rather than a curve (`joint_f-0015`). A curve that names a later curve (`joint_f-0005`), a turn with no turn instrument (`joint_f-0006`) and a duplicate instrument id (`joint_f-0007`) are `E_INPUT`.

**Evidence.** Suite `stage_f/joint_f`, 15 cases: 9 for `rates.curve.joint_solve` (5 of them errors) and 6 for `rates.funding.curve`; the stage D joint bootstrap has its own suite. Golden counts read 2026-11-21.
