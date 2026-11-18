# Oracle

Expected results for conformance. Tests only: no implementation may import or call anything here,
and golden values never come from the four implementations.

To regenerate everything, compile `oracle/strata` with Maven, write its classpath to `cp.txt`
(`mvn dependency:build-classpath -Dmdep.outputFile=cp.txt`), then:

```bash
cd oracle/python && uv run python -W ignore run_all.py
```

This takes about three minutes and writes `datasets/golden/core/*.json`, `datasets/golden/stage_b/*.json`, the exercise data and solutions, `MUTANTS.md` and `REPORT.md`. On Windows it also rewrites `oracle/strata/out/` with CRLF line endings, which git shows as changed; the content is the same. Generators stop with an error when sources disagree,
apart from the differences recorded in the specs. Each case's `verified_by` lists the sources that agreed with it.
The oracle runs on Python 3.12, pinned separately from the Python implementation.

A hand or replay source is written by the same author as the spec, so it can share a misreading with it.
Where a case has no outside library in `verified_by`, this risk stands. These results are self-assessment; there is no second
review (owner decision, 2026-11-18).

`REPORT.md`'s invariant lines cover all three folders: 4,394 stage A cases, 343 stage B cases and 446 stage C cases. Most stage B and C cases have no stated invariant, so for them the check only confirms that none is broken; the lines below each total count the cases that do have one. Stage B's outside and hand sources, suite by suite, are in `specifications/stage-b-rulings.md`.

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
| Stage B rates, FX, hedges | B | Per suite in `specifications/stage-b-rulings.md`. Mutants in `MUTANTS.md` | In use. Strata checks schedules and OIS PVs, not curve building. `usecases`, `rulings_b` and `risk` have no outside source |
| Calibration | B | Closed forms, known truth, NumPy, SciPy | In use |
| Equity forward, Black models, smile, surface, SABR, Greeks | C | Per suite in `specifications/stage-c-rulings.md`. Mutants in `MUTANTS_C.md` | In use. Arbitrage-free SABR at `nu > 0` has no tight outside source |
| Further vol, pricing | D, E | QuantLib, Strata | Planned |
| CDS | D | ISDA CDS Standard Model | Planned; licence text to read first |
| Exposure, xVA | G | Open Source Risk Engine | Planned; licence to verify |
| SIMM-style margin | G | Hand cases on own parameters | See `LICENCES.md` |
| Execution | H | Closed-form Almgren-Chriss, hand cases, known-truth simulation | Planned |
| Portfolio, hedging | I, J | Hand cases, optimality conditions | Planned |
| Market making | H | None outside: method test only | By decision |

## Validation evidence pack (2026-11-17)

`python/outside_validation.py` checks stage B and C curve cases that had no outside library (FX outright forward, equity forward, SVI, SSVI) with QuantLib 1.44 on the goldens' own inputs and tolerances, and writes `OUTSIDE_VALIDATION.json`. It reads the goldens and changes only `verified_by` (`--apply`); a disagreement is reported, never fixed by editing a golden. The generators carry the same tags, so a regeneration keeps them. `--check` (standard library only) runs in CI. See `docs/validation/README.md`.

## ORE re-test (G-42b)

`oracle/ore/` holds the inputs and summaries of the stage G wave 4c checks against the Open Source Risk Engine (ORE 1.8.17.0, Python wheel, Modified BSD; no ORE code is kept here). The six G-42b runs (`runb0..5`, seeds 20261211 to 20261216, 5,000 samples) run in CI as job `ore-retest-g42b` (`.github/workflows/ore-g42b.yml`, on changes under `oracle/ore/`, or by hand). The job installs the wheel from `oracle/ore/requirements-ore.txt` (Python 3.12, hashes checked), runs `oracle/ore/run_g42b.py`, and counts the 96 value cases with `uv run python -W ignore gen_stage_g_w4c.py countb` in `oracle/python`, which writes `oracle/ore/ORE_CHECK_4C_B.json` (uploaded as artefact `ore-g42b-results`). The tolerances are the ones registered in ruling G-42b (`check_case_b`); the count is a result, not a pass/fail gate.

To run it locally on Linux, WSL or Windows: `uv venv --python 3.12 ~/ore-venv && uv pip install --python ~/ore-venv/bin/python --require-hashes -r oracle/ore/requirements-ore.txt`, then `python oracle/ore/run_g42b.py --work <scratch dir on a fast disk>` (about 8 minutes a case on a loaded laptop, only `netcube.csv`, `npv.csv` and `log.txt` are copied back).
