# Runbook: the public-data recorder

**Plain idea.** Twice each US business day the recorder downloads a fixed list of free public files (rates, curves, CPI), keeps only a row per file (hash, size, time, licence, and for public-domain sources the parsed values) on branch `forward-log`, and throws the raw bytes away. Other jobs read that branch: the paper ledger takes its Treasury curve from it. A gap cannot be filled later, because the sources serve today's data, not yesterday's.

**Formal statement** (read from `.github/workflows/recorder.yml` and `docs/developer-guides/recorder-actions.md`, 2026-11-20):

- Schedule: 14:30 and 23:30 UTC, Monday to Friday, plus manual starts. GitHub starts scheduled runs late (3.4 to 9.0 hours measured, 2026-11-09 to 2026-11-19) and turns schedules off after 60 days without repository activity.
- Each run appends one hash-chained row per source in `tools/recorder/sources.json` to `actions/log.jsonl`, verifies the chain (`tools/forward-log/forward_log.py verify`), replays parsed values against each row's `state_sha256` (`tools/recorder/gap_monitor.py recheck`), writes `actions/gaps.md` and `actions/gaps.json`, pushes, and anchors the head with OpenTimestamps.
- The job fails when a business day among the last three has no successful recording, so GitHub emails the owner. Older gaps stay in the report.
- Raw data never leaves the runner, not even as an artefact; no raw recorded market data row is published (lane rules; SONIA may not be redistributed).

## When it is red

| Red step | Meaning | Action |
|---|---|---|
| Record | a source refused or changed format | read the step log; one source failing still records the others. If the format changed, the parser in `tools/recorder/record.py` needs a change through a pull request; never edit `forward-log` |
| verify (chain) | the log fails its own hash chain | stop: nothing should have changed the branch. Compare with the anchors (below) |
| Gap report | a business day in the last three has no row for a source | expected on a UK or TARGET2 holiday for SONIA or the ECB (only US Federal Reserve holidays are listed in `tools/recorder/holidays.txt`); otherwise re-run the same day, before the source moves on |
| Anchor | OpenTimestamps calendars unreachable | the next run stamps the head |

## Check the log yourself

```bash
git fetch origin forward-log forward-log-anchors
git show origin/forward-log:actions/log.jsonl > actions-log.jsonl
python tools/forward-log/forward_log.py verify --log actions-log.jsonl
python tools/recorder/gap_monitor.py gaps --log actions-log.jsonl --holidays tools/recorder/holidays.txt --studies tools/recorder/studies.json --out gaps
```

Re-run today's recording (it appends today's rows only; it cannot recreate an earlier day):

```bash
gh workflow run recorder.yml --ref main
```

Worked example (read from ROADMAP, R2 table, "Carried from R1"): an ECB gap on 2026-11-10 kept the gap monitor red until R6-21. The day stays a gap in the log: a later run fetches the later value, never the missed one.

## The local backup

The Windows task "QuantForge Recorder" writes its own log on the owner's laptop; `tools/recorder/gap_monitor.py reconcile` compares the two logs (`docs/developer-guides/recorder-actions.md`, "Reconciling the two"). The crypto order-book recorder (`tools/recorder/crypto_l2.py`, used for H-9) is separate and ran locally only.

## The crypto order-book recorder: stopped (2026-11-20)

**Not running.** The owner ended the H-9 R2 attempt on 2026-11-20 and the crypto recorder is stopped. All 30 of its sessions on 2026-11-19 and 2026-11-20 ended before hour 6 (websocket keepalive ping timeouts; whole-connection stalls of 50 to 107 s seen before drops; cause not established), so no R2 window exists (read from the recorder log and `benchmarks/h9/r2_status.py`; `benchmarks/results/h9/README.md`). The procedure in `benchmarks/h9/README_R2.md` (status check at each start, raw cleanup, window build) is kept as a record of how the attempt was run; do not restart the recorder for R2 without a new owner decision. The public-data recorder above is unaffected.

## Limits

- The recorder proves when a file was seen and what it hashed to; it does not prove the source's values are right.
- Holidays outside the US calendar show as gaps by design.
