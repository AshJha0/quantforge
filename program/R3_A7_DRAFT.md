# R3 amendment 7 (shared text): DRAFT, unsigned

<!-- body -->
Amends each of `R3-01-treasury-fly.md`, `R3-02-bill-repo-spread.md` and `R3-03-breakeven-seasonality.md` (one shared text; the file header names the study it amends) and that study's earlier amendments (R3-01: 1 to 6; R3-02 and R3-03: 1 to 4 and 6). They stand; where this amendment differs, this amendment governs. Common rules: `README.md`. Source: the owner question left open by amendment 6 ("Not decided here (owner)"), answered by the stage J coordinator under the owner's delegation on 2026-11-14, and the second read `program/R3_A7_REVIEW.md`.

**State at signing.** Fixed before any forward judgement. No forward outcome has been evaluated: no forward return, P&L, Sharpe, confidence interval or agreement test has been computed for any study on any date, and none is computed by the writer. The companion rows written so far (`research/r3/forward_signals.jsonl`, back-fill of 2026-11-14) carry signals and positions only: R3-01 and R3-02 null (insufficient recorded history), R3-03 a defined position. The holdout results (`research/r3/RESULTS.md`, all three fail) are known to the signer and unchanged. The rule below depends only on whether a position is defined, never on its value or on any outcome.

## Change 1: which days count toward the 250-day forward judgement

Replaces "after 250 US business days" in amendment 1's forward-log rule (and the common rules' "judged after 250 business days") with the following count. The agreement test itself (amendment 1: same sign, 95% interval) is unchanged.

- A **counted day** of a study is a US business day (a weekday not listed in `tools/recorder/holidays.txt`, as extended) on which at least one companion row of the study, dated that day (UTC date of `event_time`, amendment 6 Change 2), has a non-null `position`. A position of 0 decided from a defined signal is a defined position and counts; a null position (insufficient recorded history, or any other null) does not count.
- When several companion rows of a study are dated the same day, the day's position is that of the row filling the highest forward-log `sequence`. Rows dated on a weekend or holiday add no day.
- Back-filled companion rows count like any other (amendment 3 rule 4 rows are rows of the forward log).
- The **judgement date** of a study is the counted day on which its count reaches 250. Each study has its own; the three are not aligned. Until that day the study's forward log is not judged, and the 60-day pipeline check (common rules) is unchanged.
- The count is computed by `judgement` in `research/r3_forward.py` from the companion rows only, and reported in `research/r3/RESULTS.md` when a judgement date is reached. It reads no return.

**Why.** A null day has no position, so it has no forward return under the study's rule; counting it would judge a study on fewer than 250 days of its rule, or on none (R3-01's window fills around December 2027). The principle is the one amendment 4 R3-02 item 5 applies to flat months: a defined zero position is part of the rule's record; an undefined one is not.

## Change 2: where the daily companion rows are written

Amends amendment 6 Change 1 and Change 4 for rows written by the scheduled job. Needed because the recorder job writes only to branch `forward-log` and cannot commit to `main`.

- From the wiring of `r3_forward.py daily` into `.github/workflows/recorder.yml`, daily companion rows go to `actions/signals.jsonl` on branch `forward-log` (same chained format), and each writer run's line to `actions/signals_runs.csv` there. The back-fill file `research/r3/forward_signals.jsonl` on `main` is not written again.
- One companion row per forward-log study row across both files, never two: the daily writer skips every row already filled in either file.
- The job runs the writer from a clean checkout of `main`; the record's `commit` is that `main` commit, which holds the run lines, so amendment 6 Change 5 check (d) applies unchanged. The rule-5 check reads both files.
- A failure of the writer step does not stop the recorder rows from being pushed; it marks the run red, like the other soft steps.

## What is unchanged

Everything amendment 6 lists as unchanged; the agreement test of amendment 1; the signal and position definitions of amendment 6 Change 3; the holdout results.

## Prior knowledge

As in amendment 6. Since then the back-fill was run (33 companion rows; R3-03 November position -1, R3-01 and R3-02 null). No forward return or outcome has been computed.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-14.
- What it did: drafted this amendment from the coordinator's decision and signed it under the owner's delegation.
- Claims checked by a human: none yet. The second read was by a separate Claude subagent, not a person.
