# Runbook: the daily jobs (paper ledger and curve run)

**Plain idea.** Two scheduled workflows each append one hash-chained row per US business day to a branch of their own and stamp the newest row with OpenTimestamps on a second branch. A row, once pushed, is never changed. A red run means a person should look; it rarely means data was lost, and the fix is almost never to edit a branch.

| Job | Workflow | Writes to | Anchors on | Guide or spec |
|---|---|---|---|---|
| Paper ledger (K-2) | `.github/workflows/paper-ledger.yml` | `paper-ledger` | `paper-ledger-anchors` | `docs/developer-guides/paper-ledger.md` |
| Daily curve run (K-11) | `.github/workflows/curve-daily.yml` | `curve-daily` | `curve-daily-anchors` | `specifications/12-platform/daily-curve-run.md` |

Both read only from `main` (code), run only in `AshJha0/quantforge`, and were scheduled on `main` on 2026-11-20 (pull request #59). Sources for this page: the two workflow files and the guide above (read 2026-11-20).

**Formal statement.** A run ends in one of three states (from each workflow's "Run the day" step comment):

| Exit of `run_day.py` | Meaning | What was pushed |
|---|---|---|
| 0 | every due row written and verified, or nothing was due | the new rows, or nothing (a run with nothing due commits nothing and anchors nothing, ruling KR-205) |
| 2 | rows were written and something needs a person: a gap, a late day, or a day that could not be built | the rows, verified; the last step turns the run red |
| 1 | refused (`REFUSED: <why>` in the log) | nothing |

A separate red cause is the anchor step: rows pushed, head not stamped. The next run stamps it; if that is after the day's cut-off (19:30 UTC on the next business day), the day does not count towards K-2.

## What a red run means, by step

| Failed step | Likely cause | Action |
|---|---|---|
| Check out forward-log / curve-daily | GitHub outage or token scope | re-run the job (step 3 below) |
| Run the day, exit 2 | gap, late day, unbuildable day; read `PROBLEM:` lines | nothing to repair: the row records it. Read the row; if a source page was wrong, see the KA-C10 note below |
| Run the day, exit 1 | refused: `CONFIG` (the config file changed after the first row), `ORDER`, holdout date, chain break | do not re-run until the cause is read. `CONFIG` is deliberate: a new configuration needs a new format string, a ruling and a new ledger |
| Verify | the ledger fails its own verifier; nothing was pushed | treat as a bug report against `tools/paper_daily/` or `tools/curve_daily/` |
| Push rows | the branch changed underneath (no retry on purpose) | look at the branch history before anything else |
| Anchor | OpenTimestamps calendars unreachable | the next run stamps the head |

KA-C10 (closed by fix 03772bf6): a download that is not the data file is no longer recorded as a final failed fit (`docs/known-issues.md`).

## 1. Verify the hash chain yourself

Paper ledger, ledger alone (chain, holdout dates, exact replay), then the full check with the CLI:

```bash
git fetch origin paper-ledger paper-ledger-anchors
git show origin/paper-ledger:ledger/ledger.jsonl > ledger.jsonl
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --no-cli
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl
```

Curve run:

```bash
git fetch origin curve-daily curve-daily-anchors
git show origin/curve-daily:ledger/curves.jsonl > curves.jsonl
git --work-tree=curve-anchors checkout origin/curve-daily-anchors -- anchors
python tools/curve_daily/verify_chain.py verify --ledger curves.jsonl --impl python --anchors curve-anchors/anchors
```

Each prints one JSON line and exits 0 if the chain passes, 1 at the first failure; it never repairs (`tools/curve_daily/verify_chain.py` docstring). `--no-cli` on the paper ledger skips the calendar checks and the per-day rebuild, and the output says so (`"calendar_checked": false, "recomputed": false`).

Worked example (read from the verifier's code, `tools/paper_daily/paper_core.py`, not a recorded run): each row stores `hash`, computed over every other field, and `prev`, the previous row's `hash`. If one digit of a yield in row 7 were changed, the hash recomputed from row 7 would no longer equal its stored `hash`, so `verify` stops at row 7 and exits 1. Changing the stored `hash` as well only moves the failure to row 8, whose `prev` no longer matches, and an anchor over any later head stops matching too.

## 2. Look before re-running: a dry run

```bash
git fetch origin forward-log
python tools/paper_daily/run_day.py --ledger-ref origin/paper-ledger --forward-log-ref origin/forward-log --dry-run
python tools/curve_daily/run_day.py --ledger-ref origin/curve-daily --dry-run
```

Each prints the rows a run would add now and writes nothing. The curve dry run fetches the Treasury and Federal Reserve files (public, no sign-up) unless given `--treasury-file` and `--gsw-file`.

## 3. Re-run without recording a day twice

A run appends only the dates that are due and not yet in the ledger, and a run with nothing due commits nothing (KR-205), so re-running cannot write a day twice. The concurrency group of each workflow (`paper-ledger`, `curve-daily`, `cancel-in-progress: false`) queues a second run behind the first instead of running both. To re-run:

```bash
gh workflow run paper-ledger.yml --ref main -f dry_run=true
gh workflow run paper-ledger.yml --ref main
gh workflow run curve-daily.yml --ref main
```

Start with the `dry_run=true` run and read its log. Manual runs from any branch other than `main` do nothing (the job's `if:` requires `refs/heads/main`).

Never edit, rebase or force-push `paper-ledger`, `curve-daily` or their anchor branches. The anchors make a rewrite visible, and a repaired ledger is no longer evidence (paper-ledger guide).

## 4. The curve run's recorded miss

On the one real day tried (2026-11-13) the consistency check against the Federal Reserve's fitted curve missed: RMSE 17.36 bp against the 15 bp tolerance fixed before the run (CHANGELOG, Unreleased, K-11). A red consistency check on a later day is a result, not an outage: it is recorded in the row and stays recorded. The tolerance is not changed to make a day pass.

## Limits

- No row had been written by either job as of 2026-11-20 13:00 UTC (paper ledger guide; K-2 then stood at 0 of 20). The red-run table is read from the workflow files and tools, not from observed red runs.
- GitHub starts this repository's scheduled runs 3.4 to 9.0 hours late (measured on 24 scheduled runs, 2026-11-09 to 2026-11-19; workflow comments). A late start is why the paper ledger follows the recorder's completion instead of a clock time.
