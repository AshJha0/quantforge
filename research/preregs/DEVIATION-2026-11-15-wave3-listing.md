# Listing note: stage J wave 3 files with dates inside closed R3 holdout windows

Status: **unsigned draft** (a listing, not a change to any prereg). Written 2026-11-15 by Claude (Opus 5.5) in the wave 3 lane. `research/test_preregs.py` reads the list below in addition to `DEVIATION-2026-11-12.md` (signed, not edited).

## Why these are not holdout breaches

The R3-01, R3-02 and R3-03 holdouts were run once on 2026-11-14 (`research/holdout_runs.csv`) and published (`research/r3/RESULTS.md`, all three fail). Nothing in these files feeds any R3 computation, and no R3 study is re-run. The files carry Treasury par yields of 2008, 2013 and 2020 to 2022 for the G18 shock library (ruling J-W3-6), the B2 interpolation backtest and the wave 3 goldens. Plan 14.10 rule 6 date check: done in `specifications/06-risk/scenario-stress.md`, "Date check".

Scanner blind spot, recorded: `research/holdout_scan.py` matches ISO dates only, so the raw Treasury files (`M/D/YYYY`) and FRED files are listed here by hand; `us_treasury_shocks.json` is listed because it carries the same rows.

## Full list

- `datasets/golden/stage_j/interpbt_j.json` | R3-01 | S | one Treasury par row, 2020-02-19, as LOO goldens
- `datasets/golden/stage_j/scen_j.json` | R3-01 | S | Treasury par rows on the four library windows
- `datasets/scenarios/raw/provenance.csv` | R3-01, R3-03 | S | FRED request range end date in the URL
- `datasets/scenarios/us_treasury_shocks.json` | R3-01, R3-03 | S | library start and end rows
- `datasets/scenarios/raw/ust_2013.csv` | R3-01, R3-03 | S | raw Treasury file (M/D/YYYY)
- `datasets/scenarios/raw/ust_2020.csv` | R3-01, R3-03 | S | raw Treasury file
- `datasets/scenarios/raw/ust_2021.csv` | R3-01, R3-03 | S | raw Treasury file
- `datasets/scenarios/raw/ust_2022.csv` | R3-01, R3-03 | S | raw Treasury file
- `research/interp_backtest/results.json` | R3-01 | S | aggregate LOO errors over 2008 to 2022 rows
- `research/interp_backtest/RESULTS.md` | R3-01 | S | same, prose
- `specifications/06-risk/scenario-stress.md` | R3-01, R3-03 | S | window dates and holdout dates in prose
- `specifications/stage-j-rulings-w3.md` | R3-01 | S | shock-library window dates in ruling text (J-W3-6)
- `docs/question-bank/01-foundations-numerics.md` | R3-02 | S | calendar worked examples (day counts, holidays, schedules); synthetic dates, no market observations
- `docs/question-bank/03-curves-multicurve.md` | R3-02 | S | calendar and fixing dates in worked examples; synthetic rates, no market observations
- `docs/validation/ai-review/ois-full.md` | R3-02 | S | Good Friday calendar dates in spec text copied into the AI review prompt (validation evidence pack, 2026-11-17); no market observation
