# Central-bank curve consistency checks (H-20)

Status: acceptance criteria fixed 2026-11-18, before any comparison was run (plan section 15 gate rule). Results are added below in a later commit; the criteria above the results line are not edited after that.

## What this is, and what it is not

Rebuilding a central bank's fitted curve from the parameters that the same central bank publishes is circular. Agreement shows that our formula and conventions match theirs and that nothing is lost in parsing and rounding. It does not show that the fitted curve is right, that it prices the bonds it was fitted to, or that our calibration would choose the same parameters. These are consistency checks, not validation, and no curve is marked Validated by them.

## Sources

| Source | URL | Licence or terms | Use here |
|---|---|---|---|
| Federal Reserve, Gürkaynak-Sack-Wright (2006) fitted Treasury curve, `feds200628.csv` | https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv | Federal Reserve Board public data; free to use with attribution | parameters BETA0-3, TAU1-2; published zeros SVENYnn and instantaneous forwards SVENFnn |
| ONS series D7BT (CPI INDEX 00: ALL ITEMS 2015=100), dataset MM23 | https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7bt/mm23 | Open Government Licence v3.0 | monthly index levels |

Downloads live outside the repository in their own folder (`C:/Work/Claude/qf-downloads/h20-2026-11-18/`), are read only with `python -I`, and are never committed. Retrieval date and SHA-256 are recorded in `data/cb-consistency.json`. Real rows are never goldens: the output is a reconciliation record, not a golden suite. No London Stock Exchange or LSEG material is used.

## Acceptance criteria (fixed before the run)

Fed GSW (all rows with all six parameters present; maturities 1-30 years where the published value is present):

- **A1 zeros, circular.** Svensson zero yield from the published parameters vs published SVENYnn: at least 99.9 % of points within 0.05 bp and every point within 0.5 bp. (Published values carry 4 decimals in percent, so rounding alone is up to 0.005 bp; parameter rounding adds more.)
- **A2 forwards, circular.** Same test for the instantaneous forward vs SVENFnn, same thresholds.
- **A3 library Nelson-Siegel fit, informational gate.** On each month-end row since 2000-01-01, fit `quantforge_core.curve_fits.robust` (three-factor Nelson-Siegel; delta 1.0, which makes it plain least squares at these magnitudes; tau picked from the grid 0.25, 0.5, ..., 10 years by lowest objective) to the 30 published zeros. Pass if the median RMSE is at most 5 bp and the 95th percentile at most 15 bp. A three-factor model fitted to a four-factor curve is expected to miss at the long end; this measures how much, it does not test the Fed's fit.

ONS CPI (D7BT):

- **B1 base year.** The mean of the twelve 2015 monthly index values equals 100 within 0.05 (values are published to one decimal).
- **B2 library base and pillars, circular.** `quantforge_core.inflation.CpiCurve` with base month January 2016, base CPI the published January 2016 value, and annual pillar rates computed from the published January values of each later year (seasonality off): the curve returns the base value exactly (within 1e-9) and every pillar value within 1e-6 index points.
- **B3 between pillars, informational, no gate.** Largest and mean absolute gap between the log-linear interpolated index and the published monthly index for non-January months. It measures seasonality and the interpolation rule, not a defect.

A failed criterion is reported as failed; thresholds are not moved after the run.

Reproduce: `python -I tools/validation/cb_consistency.py --gsw <dir>/feds200628.csv --ons <dir>/ons_d7bt_mm23.csv --retrieved 2026-11-18 --out docs/validation/data/cb-consistency.json`

---

## Results (run 2026-11-18, data retrieved 2026-11-18)

Record: [`data/cb-consistency.json`](data/cb-consistency.json) (SHA-256 of both downloads inside). GSW rows 1980-01-02 to 2026-11-13 (11,699 rows, 334,365 points per test); ONS D7BT to 2026-10.

| Check | Result | Criterion | Verdict |
|---|---|---|---|
| A1 zeros (circular) | 100 % within 0.05 bp; max 0.038 bp | 99.9 % within 0.05 bp, max 0.5 bp | pass |
| A2 forwards (circular) | 99.990 % within 0.05 bp; max 0.156 bp | same | pass |
| A3 library NS fit, 323 month-ends | median RMSE 3.81 bp; p95 9.21 bp; max 19.99 bp | median 5 bp, p95 15 bp | pass |
| B1 2015 base | mean 100.008 | 100 within 0.05 | pass |
| B2 base and 10 pillars (circular) | errors below 1.2e-13 | 1e-9 / 1e-6 | pass |
| B3 between pillars | mean gap 0.85, max 3.22 index points | none | informational |

Reading: A1, A2 and B2 confirm that our Svensson formula, units and CPI curve indexing match the publishers' conventions; they say nothing about whether the curves are correct. A3 shows a three-factor Nelson-Siegel fit leaves a few bp against the Fed's four-factor curve, worst in 2000s-era humped curves. B3's gaps are mostly seasonality and the 2021-2023 inflation path, which a pillar-only log-linear curve cannot follow; they are not defects.
