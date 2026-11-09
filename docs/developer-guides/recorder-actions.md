# Recorder on GitHub Actions

Plan 11.1.4. The daily recorder runs as `.github/workflows/recorder.yml` on a standard GitHub runner, which is free for a public repository. It needs no secret beyond the built-in `GITHUB_TOKEN`, and no card.

## What it does

The workflow runs at 14:30 and 23:30 UTC, Monday to Friday, and can also be started by hand.

1. It checks out `main` (the code) and the `forward-log` branch (the rows). On the first run it creates `forward-log` as an orphan branch.
2. It runs `tools/recorder/record.py` with the same `sources.json` the local task uses. Raw bytes go to the runner's temp folder and are discarded when the job ends.
3. It appends one hash-chained row per source to `actions/log.jsonl` on `forward-log`, using the same row format as `tools/forward-log/log.jsonl`. It then verifies the chain, and `gap_monitor.py recheck` replays the parsed values kept for public-domain sources (Treasury curves, BLS CPI) against each row's `state_sha256`. One `study/<id>` row per R3 study (`tools/recorder/studies.json`) follows the sources, and every row carries the `sources.json` sha256.
4. It writes `actions/gaps.md` and `actions/gaps.json` with `tools/recorder/gap_monitor.py --studies`, which also fails if a prereg input series or study row is missing on any business day since the study's start, however old.
5. It commits and pushes to `forward-log`, and nothing else. Only the bot account writes to that branch.
6. If a business day in the last three has no successful recording, the job fails, so GitHub emails the repo owner. Older gaps stay in the report: a rerun cannot fill them, because the sources serve today's data, not yesterday's.

**Why two runs a day.** The Treasury curve is published at the end of the US day. SOFR for day T is published at 08:00 ET on T+1. The 14:30 run catches SOFR, and the 23:30 run catches the curve. If one run fails, the other still leaves a row that day.

**No raw data leaves the runner.** That includes artifacts: on a public repo, anyone can download them, and SONIA may not be redistributed until the Bank of England answers (`sources.json`). The rows carry the URL, sha256, size, licence and code commit, and, for public-domain sources only, the parsed values. This matches the local recorder's rule that no source's data is committed.

**Business days.** These are Monday to Friday, minus `tools/recorder/holidays.txt` (Federal Reserve holidays, checked 2026-11-07, covering up to 2027-12-31). UK and TARGET2 holidays are not listed, so a SONIA or ECB gap on such a day shows in the report and can be read as expected. Extend the file every year. The edge-case register's calendar provenance work (plan 11.2.3) will replace it with the library's own calendars.

**Schedule caveats.** GitHub may delay scheduled runs at busy times, and it turns off schedules in a repo with no activity for 60 days. The gap monitor is what catches either problem.

## The local backup

The Windows task "QuantForge Recorder" still runs `C:\Work\Claude\qf-recorder\run_recorder.cmd`. That script writes to `C:\Work\Claude\qf-recorder\tools\forward-log\log.jsonl` in its own checkout, and keeps the raw files under `data\recorder\`. It stays as a backup for days when Actions misses. It also holds the only copy of the raw bytes, and studies need those.

The two logs are separate hash chains. They are never merged into one file: each chain proves that its own file was not rewritten, and merging would break that.

## Reconciling the two

Copy the Actions log down and compare:

```bash
git fetch origin forward-log
git show origin/forward-log:actions/log.jsonl > actions-log.jsonl
python tools/recorder/gap_monitor.py reconcile --log actions-log.jsonl --log C:/Work/Claude/qf-recorder/tools/forward-log/log.jsonl --out reconcile.md
python tools/recorder/gap_monitor.py gaps --log actions-log.jsonl --log C:/Work/Claude/qf-recorder/tools/forward-log/log.jsonl --holidays tools/recorder/holidays.txt
```

Rows are matched by series and UTC date of `event_time`.

| Result | Meaning | Action |
|---|---|---|
| both / match | Same bytes fetched by both | None |
| both / differ | Both fetched, but the bytes differ | Normal for sources whose URL runs "to now" (SONIA), or for a fetch either side of a publication. If the bytes differ on the same publication, compare the raw local file with a fresh fetch. A source that republishes (SOFR revisions) is an edge case for the register. |
| first only | Actions has it, local missed (PC off, Application Control) | None: this is what the Actions recorder is for |
| second only | Local has it, Actions missed | Check the run log. The local row counts for the gap report. |
| neither | Both failed that day | A real gap. Note it in the study's data section. |

A day counts as recorded if either log has a successful row for it. That is why `gaps` accepts several `--log` files. Studies that need the bytes take them from the local raw store. For a day only Actions saw, the hash is known but the bytes are not, and the study must say so.
