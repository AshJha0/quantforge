# R3 amendment 7: second read (2026-11-14)

Reader: a separate Claude subagent (Opus 5.5), read-only, given the draft `program/R3_A7_DRAFT.md` (27818d5), amendments 1, 3 and 6, `r3_forward.py`, `holdout_scan.py`, the back-fill file, `holidays.txt` and `recorder.yml`. It computed no statistic or forward return. Not a human check.

| # | Severity | Finding | Fix in the signed text |
|---|---|---|---|
| 1 | high | `judgement` named but not in `r3_forward.py` | Added with a test in the signing commit; text says so |
| 2 | high | Rule-5 check did not read `actions/signals.jsonl`; writer must record a `main` commit | `signal_scan_all` reads it in the signing commit; the job runs the writer from `code/` (main), so the record's `commit` is main's |
| 3 | medium | `holidays.txt` ends in 2027; "as extended" open | Source fixed (Federal Reserve schedule, the file's own); extension required before a count passes the last listed year |
| 4 | medium | "Highest sequence" vs any row | Changed to: a day counts if any row that day has a defined position |
| 5 | low | Saturday-UTC rows add no day | Stated and accepted in the text |
| 6 | low | No terminal rule if 250 is never reached | Left to the owner ("Not decided here"); study reported as not yet judged |
| 7 | ok | Rule outcome-free; back-filled rows counting consistent with amendment 3 rule 4 | - |

Verdict: signed after fixes 1-5; 6 is an owner question and does not block.
