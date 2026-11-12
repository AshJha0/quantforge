# R3-02 amendment 2: Bill minus repo spread

Status: **signed**. Signed by Claude (signing delegated by the owner, 2026-11-07; amendment 2 agreed by the owner as decisions D2 and D3 on 2026-11-12) on 2026-11-12.
- SHA-256 of the body below the marker line: `d890e27ef21dd13f364d922b7e22c79c2eeb76c8176fa0d5ec7fe0c90cac219b`
- SHA-256 of the amended prereg `R3-02-bill-repo-spread.md` (whole file): `9e920456b64b57c6c31a94a7b7fc6952990d8db04e932e36aff524010176d7a2`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- SHA-256 of `DEVIATION-2026-11-12.md` (whole file): `b7e9e4d33e14dc164ed2c34312bf52bb894accfa124c3c8c45400d913e67c1db`
- Holdout-period values were downloaded and partly published before this signing; see the deviation note. No study statistic has been computed on them.
- This file is not edited after signing; a further change is a new amendment.

<!-- body -->
Amends `R3-02-bill-repo-spread.md` (body SHA-256 `48c3759c6d936305fd3f79f672c7afbe2957f87723d6440953939a956955af6a`, file SHA-256 `9e920456b64b57c6c31a94a7b7fc6952990d8db04e932e36aff524010176d7a2`) and its amendment 1. The original text and amendment 1 stand; where this amendment differs, this amendment governs. Common rules: `README.md`.

Date: 2026-11-12. Source of the changes: review of 2026-11-12, findings 1, 8 and 9, owner decisions D2 and D3 (`QUANTFORGE_REVIEW_2026-11-12.md` and plan section 14.3, items R6-19 to R6-21, outside this repository). Deviation note: `DEVIATION-2026-11-12.md` (file SHA-256 `b7e9e4d33e14dc164ed2c34312bf52bb894accfa124c3c8c45400d913e67c1db`, body SHA-256 `0cc883a080965d497c76ca237289475c92c86ab31d982a0e43647b5dcf29c803`).

## Change 1 (R6-19): the "not downloaded" sentence is corrected

The header sentence of the prereg and of amendment 1, "Holdout data has not been read, downloaded or summarised. No study data of any period has been downloaded at signing", is wrong and is replaced by:

"Holdout-period values of this study's inputs were downloaded by the project's recorder from 2026-11-07 and partly published on the `forward-log` branch and on pages of the main branch, as listed in `DEVIATION-2026-11-12.md`. No study statistic, signal or position has been computed on holdout-period data. The holdout dates are kept (owner decision D2)."

The holdout window, the grid, the costs and the pass rule are unchanged.

## Change 2 (R6-20): secondary statistic, reported and never deciding

Reason: the amended pass rule has low power by design (finding 8). Simulated at the MDS of 1.27, it passes with probability 0.1515 / 0.0705 (Holm level 0.05 / 0.05/3). A null result under it says little, so a second number is preregistered now, before any holdout is opened.

Added to the report, beside the pass rule:
- `p2 = 1 - Phi(SR_hat / SE)`: the undeflated one-sided p-value of the holdout annualised net Sharpe at 1x costs, on the single trial selected in-sample (amendment 1), with `SE` as preregistered (stationary block bootstrap, mean block 3, monthly).
- `p2` is compared with the study's Holm level among the three R3 studies (0.05/3, 0.05/2, 0.05 by rank of `p2`), and the report says "secondary: below the Holm level" or "secondary: not below".
- The secondary statistic never changes pass or fail. A study that fails the pass rule and has `p2` below its Holm level is reported as "failed the preregistered rule; secondary evidence of a positive Sharpe, not deflated for 24 trials".

Simulated rejection rates (`research/power/r3_power.py`, `both_table`, seed 20261109, 4,000 paths per cell, Gaussian iid net returns; output in `research/power/r3_power_output.txt`), as true Sharpe, then rate at Holm 0.05 and 0.05/3:
`R3-02  0.00 0.0585 0.0215 | 0.50 0.2702 0.1452 | 1.27 0.7977 0.6398`. The size at Sharpe 0 is near the nominal level; the power at the MDS is about 80% at 0.05.

## Prior knowledge

Unchanged from amendment 1, section "Holdout knowledge (R5)", with one addition: the people and the model signing this amendment may have seen the published values listed in the deviation note (general levels of Treasury, bill and SOFR rates in 2026). No study statistic was computed from them.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-12.
- What it did: wrote `research/holdout_scan.py`, the deviation note and this amendment, extended `research/power/r3_power.py`, ran the simulation, and signed under the owner's delegation.
