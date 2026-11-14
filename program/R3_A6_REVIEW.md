# R3 amendment 6: second read (2026-11-14)

Reader: a separate Claude subagent (Opus 5.5), read-only, given the draft `program/R3_A6_DRAFT.md` (dad0f47), amendments 3 to 5, `r3_runner.py`, `holdout_scan.py`, `test_preregs.py`, `record.py`, `forward_log.py` and the forward log. It opened no file under `research/r3/data` and computed no signal, z-score, return or forecast. Not a human check.

Checks re-run by the reader: runner SHA `f45ce97f...3916` equals all three run lines; 22d0c92 at 11:45:24Z; at forward-log sequence 255 the par yields have 218 dates and SOFR 2 fixings; replayed states match `state_sha256`; no study row has `signal_status`; `git diff faadaa4..HEAD` on the r3 modules is empty.

| # | Severity | Finding | Fix in the signed text |
|---|---|---|---|
| 1 | ok | No verdict, holdout number or frozen output changes | - |
| 2 | ok | No choice depends on outcomes; recorded-only inputs keep R3-01/02 null either way | - |
| 3 | ok | Factual claims verified | - |
| 4 | major | R3-02 business days, units, spread construction open; holdout run aligned all four inputs | Writer rebuilds `r3_data`-shaped series and calls `r3_in_sample.r301_inputs`/`r302_inputs`; `r3_in_sample.py`, `r3_data.py` SHA-pinned |
| 5 | major | R3-03 fit inputs unnamed; missing month null vs runner's 0 | `load_in_sample` + `r303_inputs` + `seasonal_returns` means named; missing month gives 0 |
| 6 | major | R3-01 window full only ~Dec 2027, after the 250-day judgement; R3-02 needs ~80 days | Stated as "Not decided here (owner)"; judgement rule unchanged. Open for the owner, does not block the back-fill |
| 7 | minor | 2026-11-14 03:27Z rows implicit | Sentence added (rule-3 rows) |
| 8 | minor | Once-only and duplicate enforcement, partial failure, daily clean tree | Any back-filled row refuses; all-or-none; duplicate `fills` refused; clean tree in daily mode |
| 9 | minor | Check (d) on shallow clone; absent file | Missing commit fails; absent file passes |
| 10 | minor | `position` meaning differs; R3-02 lag; `n` undefined; inputs per study | `position_basis`; lag stated; `n` defined; inputs listed |
| 11 | minor | Writer not frozen | Frozen at back-fill commit; later change needs deviation note and same-output test |
| 12 | minor | R3-03 override of rule 3 implicit | Stated as replacing rule 3's wording for R3-03 |

Verdict: no blocker; signed after fixes 4, 5, 7-12, with 6 recorded as an owner question.
