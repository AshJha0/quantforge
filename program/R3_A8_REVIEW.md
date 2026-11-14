# R3 amendment 8: second read (2026-11-14)

Reader: a separate Claude subagent (Opus 5.5), read-only, given the draft body, the common rules, amendments 1 and 7, `program/R3_A7_REVIEW.md` and `judgement` in `research/r3_forward.py`. It computed no statistic or forward return. Not a human check.

| # | Severity | Finding | Fix in the signed text |
|---|---|---|---|
| 1 | medium | Rows written after the cut-off but dated before it (back-fill, late runs) could reopen the freedom the rule closes | Only rows dated on or before 2027-11-05 and written (`knowledge_time`) by 2027-11-05T23:59:59Z count; status frozen after that |
| 2 | medium | `judgement` had no `as_of`, cut-off or `status` | Added in the signing commit with tests: judged on the cut-off day, short at the cut-off with later and late-written rows, not yet judged before the cut-off |
| 3 | low | Time zone of the cut-off unstated | "UTC date, as in amendment 7 Change 1" |
| 4 | low | `holidays.txt` must cover 2027 | It already lists the 2027 holidays; stated |
| 5 | low | "Never a pass" could confuse under amendment 1's agreement test | "never reported as agreement or disagreement" added |
| 6 | low | Prior knowledge named R3-01 only; R3-02's back-fill is null too | R3-02 named |
| 7 | ok | Rule outcome-free; consistent with amendments 1-7 and the common rules; ban on reusing forward rows sound | - |
| 8 | low | Header must hash amendment 7 and the other amendments; this file must exist before signing | Done in the signing commit |

Verdict: signed after fixes 1-6 and 8.
