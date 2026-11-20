# K-6 stop note (lane k-v1-k6, 2026-11-20)

Branch `k-v1-k6` (off `k-v1` at 105f7f96), pushed. No PR. The laptop is shut down at 23:00 UTC; work resumes in a new session.

## Done

- Spec `specifications/12-platform/soak-eod-capacity.md` 0.2.0 and rulings `specifications/stage-k-rulings-k6.md` (KR-217 to KR-221, confirmed 2026-11-20 for the coordinator, numbers kept, "As built" column).
- Acceptance frozen before the runs: commit 1ce167bf (soak rule, capacity row rule, EOD checklist rule; sha256 of the runner scripts in the message). Second freeze 3361a67e before the Python soak rerun (planted-leak miss recorded, 1 KiB-per-case planted run declared, run length 145 min; `analyse.py` unchanged).
- End-of-day rehearsal `tools/eod/rehearse.py`: 2026-11-19 from the forward log and the synthetic day pass all eight steps; each planted fault E1 to E7 fails its own step (`benchmarks/results/k6/eod-*.json`).
- Capacity, Python and Java, local laptop: every row passes; planted wrong result caught (`benchmarks/results/k6/capacity-*.json`, `docs/capacity.md`).
- Planted soak leak (1 KiB per 100 cases): `LEAK MISSED`, a recorded miss (about 0.8 MiB/h at 23 cases/s, under the 1 MiB/h bound). Declared 1 KiB-per-case planted run: `LEAK CAUGHT`.
- Python soak: recorded MISS on SLOPE (see below). Next step for it: a runner soak (VmRSS on Linux) and a heap profile of the Python process.
- Workflow `.github/workflows/k6-soak.yml` (manual and weekly, all four builds), never run yet.
- Docs: `docs/capacity.md` (generated block), `docs/runbooks/soak-and-eod.md`, known-issues rows, CHANGELOG, results page row.

## Running or cut off

- Nothing is running. The Python soak (145 min, 18:19 to 20:45 UTC) finished and was scored: recorded MISS on SLOPE, 2.32 MiB/h (95 % CI 1.70 to 3.80) against 1 MiB/h; range 3.0 % holds; no drift or errors. The declared 1 KiB-per-case planted leak (20:45 to 21:05) was caught (SLOPE, 171.9 MiB/h).
- Cut off: a 130-minute Python soak started at about 18:15 UTC was stopped by the lane after about 4 minutes (sample margin) and is recorded as interrupted, not scored (`soak-python-2026-11-20-interrupted.csv`). Chain 1 was stopped at 17:53 after the coordinator notice; the Java capacity run it had started finished normally.

## Not run yet

- Java soak (would have ended after 22:15 UTC).
- C++ and Rust soaks and capacity rows: runner only.
- The K-5b publisher beside the soak.

## Exact next commands

```bash
# 1. all four soaks and capacity rows on a runner, once the workflow file is on main (GitHub dispatches only
#    workflows present on the default branch); manual, also weekly on Sundays
gh workflow run k6-soak.yml
# 2. or the Java soak on the laptop (detached; about 2 h 25 min), then regenerate the page
python benchmarks/soak/soak.py --impl java --minutes 145 --tag <date> --progress /c/Work/Claude/qf-wt/_h4ci/k6_progress.json
python benchmarks/soak/capacity_page.py
```

Laptop chain scripts and logs: `C:/Work/Claude/qf-wt/_h4ci/k6_chain*.sh`, `k6_chain_summary`, `k6_*.log`.
