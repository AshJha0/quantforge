# Soak, capacity and end-of-day rehearsal

**Plain idea.** Three scripts answer three operating questions: does a long-running batch process stay the same size and give the same answers (soak); how much can each build do and where does it stop (capacity); can one recorded day be taken from the recorder's log to the dashboard pages by a script, step by step, with evidence (end-of-day rehearsal). Use this page to run them, to read a red result, and to rehearse a day before trusting the daily jobs with it.

**Formal statement.** The rules are in `specifications/12-platform/soak-eod-capacity.md` (section 5, frozen before the first counted run; rulings KR-217 to KR-221, confirmed 2026-11-20). The soak verdict comes only from `benchmarks/soak/analyse.py`; the capacity row rule and the end-of-day checklist rule are in the same spec. Results and figures are on [Capacity and operations](../capacity.md). Source of every statement on this page: the scripts named (read).

## Run a soak

Use when: before a release, after a change to a CLI's batch loop or to memory handling, or when the weekly `k6-soak` workflow is red.

```bash
export PYTHONUTF8=1
# one build at a time on a shared machine; 130 minutes; below-normal priority is the default
python benchmarks/soak/soak.py --impl python --minutes 130 --progress soak-progress.json
python benchmarks/soak/analyse.py benchmarks/results/k6/soak-python-<date>.csv benchmarks/results/k6/soak-python-<date>.summary.json
# the planted leak, which must come back "LEAK CAUGHT"
python benchmarks/soak/soak.py --impl python --minutes 20 --plant-leak
# all four builds on a runner (manual run; also weekly)
gh workflow run k6-soak.yml
```

A run longer than about 90 minutes on the laptop is started detached, with a watcher on its progress file (lane rules). The verdict names its reasons when it misses:

| Reason | Read it as | First thing to check |
|---|---|---|
| `SLOPE` | the judged memory climbs more than 1 MiB an hour after warm-up | the CSV columns `judged_bytes` and `cases_total`: a steady climb per case is a leak; a single step is a cache filling late |
| `RANGE` | the judged memory moved more than 5 % of its median | whether one sample is an outlier (Windows paging, a GC at the wrong moment) or the series wanders |
| `DRIFT` | a later answer differs from the first answer to the same case | `drift_examples` in the summary: the case and the pass; rerun that case alone twice |
| `GOLDEN` | a first answer fails its golden | the conformance runner on that suite: the build is wrong, not the soak |
| `STALL`, `DIED`, `EXIT`, `STDERR`, `ERRORS` | the process hung, crashed, failed to exit cleanly, wrote to stderr, or wrote an unreadable line | the summary's `exit_code` and `stderr_bytes`; rerun with the same tag and read stderr |
| `SHORT`, `FEW_SAMPLES`, `NO_FULL_PASS` | the run was too short to judge | the run length and the first-pass time in `warmup_end_s` |

A miss is recorded as a miss in `docs/known-issues.md`; the rule is not changed after a run.

## Measure capacity

```bash
python benchmarks/soak/capacity.py --impl python
python benchmarks/soak/capacity.py --impl java --procs 1
# the planted wrong result, which must come back "WRONG_RESULT CAUGHT"
python benchmarks/soak/capacity.py --impl python --plant-wrong
```

A row with `WRONG_RESULT` has no figure: fix the build (or the golden, with a ruling) before reading any number.

## Rehearse an end of day

Use when: before relying on the daily jobs for a date, after a change to the curve run, the paper ledger or the site pages, or to check a recorded date by hand. It is a dry run: it writes only to a temporary folder and `benchmarks/results/k6/`, never to `forward-log`, `curve-daily` or `paper-ledger`, and starts no workflow. Never trigger the scheduled daily workflows by hand for a date they have already recorded.

```bash
export PYTHONUTF8=1
uv run --project python python tools/eod/rehearse.py --date 2026-11-19 --source forward-log
uv run --project python python tools/eod/rehearse.py --date 2026-11-19 --source synthetic --plant GAP
uv run --project python python tools/eod/test_rehearse.py
```

The human checklist is `tools/eod/CHECKLIST.md`. A failed step stops the run; read its `evidence` in the JSON, then the runbook for that job: [Daily jobs](daily-jobs.md) for E1, E3 and E4, [Recorder](recorder.md) if E1 reports a gap in the log.

## Worked example

On 2026-11-20 the rehearsal of 2026-11-19 from the forward log passed all eight steps in about 12 s on the laptop (`benchmarks/results/k6/eod-2026-11-19-forward-log.json`, measured, local laptop, not the acceptance machine). The same date with `--plant EXPLAIN` failed at E4 with reason `EXPLAIN`, and E5 to E8 were recorded as "not run".
