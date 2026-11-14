# Deviation 2026-11-14: Holm display fields in `research/r3/holdout.json` (post-hoc erratum)

Status: post-hoc erratum, written after the one-shot R3 holdout runs. It changes no verdict, no frozen file and no output file; `research/r3/holdout.json` stays as the runner wrote it.

## What is wrong

Holm's step-down method sorts the family's p-values from smallest to largest and compares the `i`-th smallest (counting from 1) with `alpha / (m - i + 1)`; it stops at the first p above its level, and nothing after it is rejected (Holm 1979, *Scandinavian Journal of Statistics* 6(2), 65-70; not opened, standard result). With `m = 3` and `alpha = 0.05` the levels are 0.0167, 0.025 and 0.05.

R3-02's circular block bootstrap SE is NaN (the selected trial is flat in most holdout months, so some resamples have zero variance), which makes its `p` NaN. Python's sort places a NaN arbitrarily, so the `holm_level` written for R3-01 and R3-02 depends on that accident and means nothing.

## The correct reading

R3-02's holdout Sharpe is -1.09 and its benchmark `SR0 = 1.9798 x SE` is positive for any positive SE, so `p = 1 - Phi((SR - SR0)/SE)` is above 0.5 whatever the SE. The known p-values are R3-03 0.849 and R3-01 0.9999. So:

- the smallest p of the family is R3-03's 0.849 or R3-02's (somewhere above 0.5); either way it is above 0.5;
- the first Holm level is 0.05 / 3 = 0.0167;
- the smallest p is far above it, so Holm stops at step 1 and rejects nothing, whatever the order of the three.

The full order cannot be stated (R3-02's p is undefined), and it is not needed. Every Holm-adjusted p is 1.0 under any order. The `holm_level` fields for R3-03 (0.0167, first) hold only if R3-02's p is at least 0.849; for R3-01 and R3-02 they are artefacts of the sort.

## Effect

None on verdicts: all three studies fail, as `research/r3/RESULTS.md` states. A reader of `holdout.json` should ignore the `holm_level` fields of R3-01 and R3-02. A future runner should place an undefined p last rather than sort it.
