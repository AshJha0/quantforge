# Stage K round 1: daily curve run lane handover (2026-11-19)

Branch `k-curve-daily` (off `k-r1` at f2d90738). Plan 14.8 K-11; 14.10 rules 1 and 6. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18).

Row label: "fitted to public US Treasury par yields with a library Nelson-Siegel fit; not an official curve". Fed comparison label: "consistency check, not proof".

## What is built

| Item | Where | Evidence |
|---|---|---|
| Spec, fixed before any scheduled run | `specifications/12-platform/daily-curve-run.md` | acceptance table C1 to C4 in the spec |
| Rulings KR-90 to KR-107 (proposed) | `specifications/stage-k-rulings-curve.md` | need the coordinator's confirmation |
| Job | `tools/curve_daily/curve_core.py`, `run_day.py`, `config.json` | `python/tests/test_curve_daily.py`, 23 tests, measured 2026-11-19 on the local laptop (Windows, Python 3.15), not on CI |
| Verifier, anchor, rebuild | `tools/curve_daily/verify_chain.py` | same test file; one planted fault per check (spec table) |
| Workflow | `.github/workflows/curve-daily.yml` | not triggered; `tools/check_job_names.py` 59 jobs, 0 problems |
| Site stub | `tools/curve_daily/site_page.py`, placeholder data `tools/curve_daily/site/latest.json` | test renders the placeholder and a real summary |

## Data terms (KR-90)

Read 2026-11-19 through the web-fetch agent (URLs in the spec). Fed Board: public domain unless otherwise indicated, citation asked; GSW posted weekly, typically Tuesday for the week to the previous Friday; staff research product, may be revised. Treasury: no page found states copyright, reuse or automated-access terms (two policy URLs 404). Neither source says anything about automated fetching. Decision: rows hold only fitted parameters, diagnostics, fitted zero rates and input SHA-256 hashes; no source row or file is committed, uploaded or printed by the scheduled job. This publishes less than the recorder already does for the same Treasury file.

## What runs when

- **Not scheduled (2026-11-19).** The workflow's `schedule:` trigger is withheld until the different-model audit findings KA-C1, C2, C3, C9, C11 and C12 are closed (`docs/known-issues.md`); it can only be started by hand (`workflow_dispatch`). It has never run on a GitHub runner and 0 days are recorded. Planned crons, now comments in the workflow file:
- `curve-daily.yml`: 23:45 UTC Monday to Friday (Treasury posts usually by 6:00 PM ET) and 14:15 UTC Tuesday to Saturday (second chance, before the 19:30 UTC on-time cut-off), plus `workflow_dispatch` with `dry_run`. Concurrency group `curve-daily`. It starts by itself once the file is on `main`. **Not triggered; branches `curve-daily` and `curve-daily-anchors` not created.**
- Output: branch `curve-daily`, `ledger/curves.jsonl` and `ledger/summary.json`. Anchors: branch `curve-daily-anchors`, `anchors/`. Optional signing with `FORWARD_LOG_SIGNING_KEY`, as the recorder.
- A row with a problem (gap, failed fetch or fit, stale input, holdout block) is pushed and then the run turns red (exit 2), so the owner is emailed.

## Dry run for the coordinator

```bash
python tools/curve_daily/run_day.py --ledger-ref origin/curve-daily --dry-run
```

Run in this worktree on 2026-11-19 at 13:36:47 UTC (live Treasury and Fed files, Python CLI, local laptop) it printed the label, then

```
2026-11-18: ok on_time tau 2.25 rmse 10.58 bp max 17.91 bp at 1 Mo
2026-11-18: consistency pending (Fed file ends 2026-11-13)
{"counts": {... "ok": 1 ...}, "dry_run": true, "head": "376a530b...", "last_date": "2026-11-18", "rows_added": 2, ...}
```

and the GENESIS and DAY rows. With `--now 2026-11-13T23:45:00Z`: fit RMSE 10.25 bp (largest 15.91 bp at 20 years), and the Fed comparison RMSE 17.36 bp, largest 25.71 bp at 22 years: **`outside` the 15 bp tolerance**, which was committed (7440c936) before any real-day run. Both days are also just over the 10 bp fit flag. The first live dry run (13:36:05 UTC) used an unweighted fit and gave 31.58 bp RMSE, 70.58 bp at 1 month; inverse squared duration weights (KR-98) were added after seeing that one day, which the spec records as a change made after seeing data. Thresholds were not moved.

**Recorded miss (integration, 2026-11-19).** On the one real day tried (2026-11-13) the consistency check against the Fed's fitted curve missed: RMSE 17.36 bp against the 15 bp tolerance fixed before the run. This is a consistency check, not proof. The fit weights were changed once after one real day had been seen (disclosed in the spec); the tolerance and the method are not changed. A row outside the tolerance is recorded as `outside`, never dropped. The site stub (`tools/curve_daily/site_page.py`) prints this on every page. The three missing library operations are listed in `ROADMAP.md` as stage K follow-ups.

## How to verify the real ledger later

```bash
git fetch origin curve-daily curve-daily-anchors
git show origin/curve-daily:ledger/curves.jsonl > curves.jsonl
git worktree add ../cd-anchors origin/curve-daily-anchors   # or copy anchors/
python tools/curve_daily/verify_chain.py verify --ledger curves.jsonl --anchors ../cd-anchors/anchors
python tools/curve_daily/verify_chain.py rebuild --ledger curves.jsonl --date YYYY-MM-DD --treasury-file YOUR_COPY.csv
```

`ots verify` on an anchor's `.ots` file checks the Bitcoin attestation, as `docs/developer-guides/forward-log-anchors.md`.

## Library operations missing (not changed by this lane)

1. **Svensson (four-factor) fit.** Both real days left an RMSE just over 10 bp with a wave the three-factor curve cannot follow, and the Fed comparison came out `outside`. The library has the Svensson formula only in `tools/validation/cb_consistency.py`. A `bond.fit.svensson` (or a `shape` input on `bond.fit.nelson_siegel`) in four languages, with goldens, would let this job fit the same family as the Fed. Adding it to the job then needs a new format string and ledger (KR-102).
2. **Sovereign par bootstrap.** No operation bootstraps a zero curve from Treasury par yields (`rates.ois.bootstrap` takes swap quotes). The brief named it; it is not run.
3. Nelson-Siegel curve evaluation at arbitrary times has no operation; the job reads zero rates through weight-0 probe bonds, which is exact but indirect.

## Registrations other lanes must add (not edited here)

- `specifications/cli-contract.md`, `name-map.json`, registries, generated checklists: nothing (no new operation). `build_references`, `build_checklists`, `gen_name_map`, `case_figures`, `outside_shares` all report up to date.
- `specifications/12-platform/README.md`: list `daily-curve-run.md` when the folder gets its index.
- `tools/README.md`: a line for `tools/curve_daily/`. `CHANGELOG.md`, `docs/diagrams/README.md`, `ROADMAP.md`: the daily run and its two branches, for the docs lane.
- `python/pyproject.toml`: nothing (the test is fully typed).
- Branch protection: `curve-daily` and `curve-daily-anchors` writable only by the workflow, as `forward-log`. Owner setting.
- Dashboard and curves gallery: call `site_page.render(json.load(summary))` from `tools/build_site.py` or `tools/build_gallery.py` with `ledger/summary.json` from branch `curve-daily` copied to `tools/curve_daily/site/latest.json` (or fetched at build time). It prints the date, timing, tau, RMSE, six zero rates, the consistency status with its label and the chain head. Keep the labels; show late days and gaps as what they are. Run `python research/test_preregs.py` on any page that prints dates.

## Gate results on this branch (2026-11-19, local laptop, not the acceptance machine)

| Command | Result |
|---|---|
| `uv run pytest tests/test_curve_daily.py` | 23 passed |
| `uv run ruff check`, `ruff format --check` on the test; `uv run mypy .` | clean; 227 source files, no issues |
| `python research/test_preregs.py` (files staged) | 10 tests OK |
| `python tools/test_tools.py` | exit 0 |
| reference, checklist, name-map, case-figure and outside-share `--check` runs | up to date |
| `tools/quality_gate.py --check-register --check-specs --check-docs` | 0 new gaps (10 baseline) |
| `tools/check_job_names.py`, `tools/check_hygiene.py` | 59 jobs, 0 problems; 0 problems |
| `git grep -i` for the banned word on the new files | none |

## Not done, not verified

- The workflow has never run on a GitHub runner; the first `workflow_dispatch` with `dry_run` is its test and pushes nothing.
- Python CLI only; Linux bit-equality of fits with this Windows run is expected (pure binary64 arithmetic in the same order) but not checked.
- Tools under `tools/curve_daily/` are standard-library scripts outside the mypy and ruff scope of `python/`, as other tools are.
- The reading of the terms is a reading, not legal advice.
- Commit trailer: the brief asked for the actual model name, so commits say Claude Opus 5.5, not the trailer in `LANE_RULES_K.md`.
