# R3 amendment 4: second read (2026-11-14)

Reader: a separate Claude subagent (Opus 5.5), read-only, given `program/R3_NOTES.md`, the three signed preregs with amendments 1 to 3, `preregs/README.md`, `research/power/r3_power.py` and the draft. It read no market data and ran only `expected_max_z` (no data). Not a human check.

## Result

Every open choice in `R3_NOTES.md` is closed for all three studies (R3-01 items 1-5, R3-02 items 1-6, R3-03 items 1-4). No choice looks tuned to outcomes; each cites a principle or a convention. E[max] 1.9798 (N = 24) and 1.9221 (N = 21) confirmed; 21 distinct strategies (8 + 12 + 1) right; R3-02 holdout 46 months (entries Dec 2022 to Sep 2026) right.

## Findings and what was changed before signing

| # | Severity | Finding | Fix in the signed text |
|---|---|---|---|
| 1 | blocker | Draft said no study data of any period had been downloaded; contradicts amendment 2 Change 1 and the deviation note (recorder downloads) | Intro and Prior knowledge now cite `DEVIATION-2026-11-12.md`; claim narrowed to "no study runner read a file, nothing computed, no choice used those values" |
| 2 | blocker | This review file was cited but did not exist | This file written before signing |
| 3 | minor | R3-01 position index ambiguous | `pos_t` defined as held after close `t`, set from `z_{t-1}` |
| 4 | minor | Bootstrap is circular; draw order matters | "circular ... exactly `boot_sharpe` with `x` of shape (1, n)" |
| 5 | minor | Missing tenor cells undefined | Business day = every input non-missing, no fill |
| 6 | minor | R3-03 month counts not stated | 155 in-sample, 130 holdout added |
| 7 | minor | Thirds cost level, override not flagged | 1x net, governs over "same sign" |
| 8 | minor | Bill price DV01 is `(t/360) P^2`; accrual calendar | `P^2`; accrual on the funding fixing dates |
| 9 | minor | 1:2:1 is not duration-neutral | Stated as governing over "duration-neutral" |
| 10 | minor | Code citation without commit; NY Fed timing without source | `r3_power.py` at 09c596f; NY Fed page named; human check "none" recorded |

After the fixes no finding remains open. Signed as amendment 4 under the owner's delegation.
