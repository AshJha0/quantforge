# Deviation 2026-11-14: amendment 4 DV01 wording (R3-01, R3-03)

Date: 2026-11-14. Recorded before any R3 study file is downloaded or parsed by a study runner and before any study signal, position or statistic is computed on any date. `research/holdout_runs.csv` has no line. No outcome has been seen.

## What the signed text says

Amendment 4 (signed in 8b8592c, identical body in `R3-01/02/03-amendment-4.md`), R3-01 item 1, defines the leg DV01 as "per unit notional" and gives the shorthand formula `D = modified_duration x dirty / 10^4` from `quantforge_core.bonds.price_from_yield`. R3-03 item 3 uses the same DV01 by reference.

## The slip

`price_from_yield` quotes `dirty` per 100 of face. Taken literally, the formula gives DV01 per 100 face, which is 100 times the DV01 per unit notional the item defines. The slip was found after signing while building `research/r3_runner.py` and is noted in `program/R3_A4_REVIEW.md` ("Note after signing").

## What is done

The runner follows the defined quantity, DV01 per unit notional: `modified_duration x (dirty / 100) / 10^4` (`r3_runner.par_dv01`). The defined quantity governs the shorthand. The signed amendment is not edited.

## Effect

R3-01: `G` and every per-unit-notional return, cost and charge are on the base the item names; with the literal formula the bp P&L would be divided by a `G` 100 times smaller while the balance-sheet charge stayed per unit notional, which would make the charge negligible. R3-03: the ratio `Dn/Dr` is unaffected; the scale `Dn / (1 + Dn/Dr)` follows the defined unit. The choice was fixed by the item's own definition, not by any data.
