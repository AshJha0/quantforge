# Stage H rulings, wave 1 (spec lane): DRAFT

DRAFT written 2026-11-15 before v0.9.0 is tagged; not normative until the stage H coordinator confirms it at the start of stage H (plan 15 gate rule: source, acceptance test fixed before the run, outside checks on at least 60% of value cases). Earlier rulings still hold, among them `stage-j-rulings-w1.md` J-1 (the backtester's close fill is unchanged by stage H). Append-only once confirmed.

## Wave 1

| # | Point | Ruling (proposed) |
|---|---|---|
| H-1 | Operations and contract | Wave 1 adds `exec.schedule.twap`, `exec.schedule.vwap`, `exec.schedule.pov` (`10-execution/schedules.md`), `exec.ac.trajectory`, `exec.ac.frontier` (`10-execution/almgren-chriss.md`), `exec.impact.sqrt`, `exec.impact.ow_optimal` (`10-execution/impact.md`), `exec.tca.shortfall` (`10-execution/tca.md`), `micro.mm.as_quotes` (`09-microstructure/avellaneda-stoikov.md`). No new error code; target contract 1.15.0 (minor). Confirm the number at the v0.9.0 tag |
| H-2 | Sign convention | Quantities are positive; `side` is `BUY` or `SELL`. Costs are positive when they hurt the order. Prices in currency per unit, volumes in units |
| H-3 | Integer lots | `UNITS` mode returns integers: TWAP floors each slice and gives the remainder one unit at a time to the earliest slices; VWAP uses largest remainder, ties to the earliest. `CONTINUOUS` returns reals. Slices sum exactly to the order (UNITS) or to 1e-12 relative (CONTINUOUS) |
| H-4 | POV participation base | Participation `p` is own fills over total volume including own fills, so the child in a bucket with outside volume `v` is `p v / (1 - p)`, capped at the remaining order. `0 < p < 1`, else `E_DOMAIN` |
| H-5 | Almgren-Chriss model | Discrete model of [AC00] with `eta_tilde = eta - gamma tau / 2`; `eta_tilde <= 0` is `E_DOMAIN`. `lambda = 0` returns the linear trajectory exactly, not the `kappa -> 0` limit by cancellation. Fixed cost enters as `epsilon X` (monotone trajectories only) |
| H-6 | `kappa` evaluation | `kappa_tilde = acosh(1 + y) / tau`, `y = lambda sigma^2 tau^2 / (2 eta_tilde)`, computed as `log1p(y + sqrt(y (y + 2)))`; the sinh ratio is evaluated in exponential form when `kappa T > 700` |
| H-7 | Avellaneda-Stoikov | Closed forms of [AS08] (finite horizon, exponential utility, intensity `A exp(-k delta)`), quotes symmetric about the reservation price; no inventory cap in wave 1 (bounded-inventory Gueant-Lehalle-Fernandez-Tapia form is wave 2) |
| H-8 | Shortfall decomposition | Perold paper portfolio: total = delay + execution + opportunity + fees, summing to 1e-10 relative. Delay charged on executed quantity (open question O-3) |
| H-9 | `E_LIMIT` sizes | Schedule buckets 100,000; AC steps 100,000; TCA fills 1,000,000. Checked after `E_SCHEMA`, before F-2 |
| H-10 | Labels | Outputs resting on assumed parameters carry `"model": "assumed parameters; not calibrated to any venue"` until the crypto calibration lane (14.7 H-1) reports with standard errors |
