# Oracle

Expected results for conformance. Tests only: no implementation may import or call anything here,
and golden values never come from the four implementations.

To regenerate everything, compile `oracle/strata` with Maven, write its classpath to `cp.txt`
(`mvn dependency:build-classpath -Dmdep.outputFile=cp.txt`), then:

```bash
cd oracle/python && uv run python -W ignore run_all.py
```

This takes about three minutes and writes `datasets/golden/core/*.json` and `REPORT.md`. On Windows it also rewrites `oracle/strata/out/` with CRLF line endings, which git shows as changed; the content is the same. Generators stop with an error when sources disagree,
apart from the differences recorded in the specs. Each case's `verified_by` lists the sources that agreed with it.
The oracle runs on Python 3.12, pinned separately from the Python implementation.

A hand or replay source is written by the same author as the spec, so it can share a misreading with it.
Where a case has no outside library in `verified_by`, this risk stands. These results are self-assessment until
the human review at the end of the project.

## Oracle map

| Scope | Stage | Oracle | State |
|---|---|---|---|
| Day counts | A | Exact rationals, QuantLib, Strata | In use |
| Calendars | A | Rules, QuantLib, Strata | In use |
| Compounding | A | mpmath, QuantLib | In use |
| Snapshot hash | A | Own canonical form, NIST vector, `sha256sum` | In use. Single source for the form |
| RNG | A | Published reference vectors, integer replay | In use. Jump has no outside vector |
| Sobol | A | QuantLib, SciPy | In use |
| Roots, integration, differences, linear algebra | A | mpmath, NumPy | In use |
| Interpolation | A | SciPy, QuantLib, mpmath | In use. Tension and monotone-convex: mpmath replay and properties only |
| Statistics, time series | A | Exact rationals, mpmath, NumPy, SciPy | In use |
| PDE | A | Analytic Black-Scholes, independent replay | In use |
| Monte Carlo | A | Analytic, independent replay | In use |
| COS | A | Analytic, QuantLib Heston | In use |
| Data checks, timezones | A | Hand cases, `zoneinfo` | In use |
| As-of store, replay | A | Hand rows, own canonical form | In use. Single source |
| Stage B rates, FX, hedges | B | Per suite in `specifications/stage-b-rulings.md`. Mutants in `MUTANTS.md` | In use |
| Calibration | B | Closed forms, known truth, NumPy, SciPy | In use |
| Vol curves, further pricing | C-E | QuantLib, Strata | Planned |
| CDS | D | ISDA CDS Standard Model | Planned; licence text to read first |
| Exposure, xVA | G | Open Source Risk Engine | Planned; licence to verify |
| SIMM-style margin | G | Hand cases on own parameters | See `LICENCES.md` |
| Execution | H | Closed-form Almgren-Chriss, hand cases, known-truth simulation | Planned |
| Portfolio, hedging | I, J | Hand cases, optimality conditions | Planned |
| Market making | H | None outside: method test only | By decision |
