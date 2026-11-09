# R3-02 amendment 1: Overnight funding against Treasury bills

Status: **signed**. Signed by Claude (signing delegated by the owner, 2026-11-07) on 2026-11-09.
- SHA-256 of the body below the marker line: `42efca76f4df854a3b4506ce1dec834db5c922015312af97ababd7ec9ea9e2bc`
- SHA-256 of the amended prereg `R3-02-bill-repo-spread.md` (whole file): `9e920456b64b57c6c31a94a7b7fc6952990d8db04e932e36aff524010176d7a2`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- Holdout data has not been read, downloaded or summarised. No study data of any period has been downloaded at signing.
- This file is not edited after signing; a further change is a new amendment.

<!-- body -->
Amends `R3-02-bill-repo-spread.md` (body SHA-256 `48c3759c6d936305fd3f79f672c7afbe2957f87723d6440953939a956955af6a`, file SHA-256 `9e920456b64b57c6c31a94a7b7fc6952990d8db04e932e36aff524010176d7a2`). The original text stands; where this amendment differs, this amendment governs. Common rules: `README.md`.

Date: 2026-11-09. Source of the changes: plan section 13.1, items R1, R2, R5, R6 and R12 (`QUANTFORGE_PLAN.md`, outside this repository).

## Change 1 (R1): pass condition (1) becomes a one-sided test

Reason: the original condition "holdout net Sharpe at least the MDS" passes only about half the time when the true Sharpe equals the MDS, because the estimate is centred on the truth. That is a coin flip at the design point, not 80% power.

Replaces condition (1) of the pass rule and the "Threshold" sentence with:

- `SE` is the preregistered standard error of the holdout annualised net Sharpe at 1x costs (stationary block bootstrap, mean block 3; 400 draws in the simulation, 10,000 in the study).
- Deflation benchmark: `SR0 = SE * E[max of N standard normals]`, with `N` = 24, the family trial count from `research/trials.csv` (Bailey and Lopez de Prado 2014; E[max] = 1.9798 at N = 24). Under the null of no skill and independent trials the variance of each trial's Sharpe estimate is `SE^2`, so the other trials' holdout values are not needed.
- One-sided p-value: `p = 1 - Phi((SR_hat - SR0) / SE)`; the deflated Sharpe ratio is `1 - p`.
- Condition (1) holds if Holm's procedure across the three R3 studies (Change 2) rejects this study's null. Equivalently, the one-sided lower confidence bound of the deflated Sharpe `SR_hat - SR0`, at the Holm level, is above 0.
- Selection, made explicit because the original text left it implicit: the holdout is run once, on the trial with the highest in-sample net Sharpe at 1x costs.
- Conditions (2) and (3) are unchanged.

Simulated pass probability (`research/power/r3_power.py`, numpy, seed 20261109, 4,000 paths per cell; Gaussian AR(1) net returns; holdout 3.83 years, monthly (46 returns); condition (3) applied; condition (2) not simulated because turnover is unknown before the data is read, so these are upper bounds). Evidence class: simulation.

| True annualised SR | Pass, Holm level 0.05 | Pass, Holm level 0.05/3 |
|---|---|---|
| 0 | 0.0008 | 0.0003 |
| 0.5 | 0.0103 | 0.0045 |
| 1.27 (MDS) | 0.1515 | 0.0705 |
| 0, AR(1) 0.2 | 0.0020 | 0.0010 |

Size at true SR 0 is at most 5% in every cell (`research/power/test_r3_power.py` asserts it). Power at the original MDS of 1.27 is between 7.0% and 15.2%. **This study is underpowered under the amended rule:** a null result says little about a true Sharpe near the MDS. That is stated now, before any data is read.

## Change 2 (R6): Holm correction across the three studies

The three R3 studies are one family. Their p-values from Change 1 are ordered `p_(1) <= p_(2) <= p_(3)`; the null of `p_(j)` is rejected while `p_(j) <= 0.05 / (4 - j)`, stopping at the first failure (Holm 1979). Combined with deflation at N = 24 this is conservative; the conservatism is accepted.

## Change 3 (R6): family trial count

The deflated Sharpe ratio uses N = 24, the number of rows in `research/trials.csv` (8 for R3-01, 12 for R3-02, 4 for R3-03), not this study's own 12. `python tools/quality_gate.py --check-dsr --trials N` rejects any N below the ledger count (tested in `tools/test_tools.py`).

## Change F: forward-log rule

Reason: the original "same rule after 250 US business days" fails by construction, because 250 days can only detect a Sharpe near 2.5 (common rules table).

Replaces the forward-log bullet with: after 250 US business days the forward log **agrees** with the holdout if (a) its annualised net Sharpe has the same sign as the holdout estimate, and (b) its two-sided 95% confidence interval (Lo 2002, iid, daily) contains the holdout estimate. Agreement is reported; it never turns a failed holdout into a pass. Simulated (same script, 20,000 paths): probability of agreement when the true SR and the holdout estimate both equal the MDS, 0.8738; when the true SR is 0 and the holdout estimate is the MDS, 0.5001. The forward log therefore cannot confirm a modest signal by itself; it checks the pipeline and look-ahead.

## Change 4 (R2): the outcome is a P&L, not a change in the spread

Reason: the original outcome, the change in `s` over the holding period, uses a spread measured against a trailing 20-day mean of funding. A trailing mean of noise mean-reverts by construction, so the z-score "predicts" the change in `s` even when funding is pure noise. `research/test_r3_02_pnl.py` shows this on simulated i.i.d. funding with a constant bill rate: the original outcome gives an annualised Sharpe of about -1.7 (simulation, this repository, seed 20261109), while the amended outcome gives about 0.05.

Replaces "Outcome: the change in `s` over the holding period, in bp, times the position" with:

- **Outcome:** position times the holding-period P&L of a 13-week bill financed overnight, per unit of entry price, `pnl = (P_exit - P_entry)/P_entry - (F - 1)`. It splits into realised carry `y_mm,entry h/360 - (F - 1)` and price change `(P_exit - P_entry)/P_entry - y_mm,entry h/360`, where `h` is the holding period in calendar days and `F = prod (1 + r_i n_i / 360)` is the realised compounded overnight rate (SOFR, TGCR or BGCR, each ACT/360 per NY Fed methodology; `n_i` calendar days per fixing).
- **Day-count conversion.** Treasury's 13-week rate is a coupon-equivalent yield, `y_ce = 365 d / (360 - d t)` for discount rate `d` and `t` days to maturity, with 366 in place of 365 when the year after issue contains 29 February (Treasury, Daily Treasury Bill Rates, interpretation note; documentation, not re-checked today). The money-market yield on the same price is `y_mm = y_ce * 360 / B` with `B` = 365 or 366, and the price is `P = 1 / (1 + y_mm t / 360)`. Both legs are therefore on ACT/360. The signal spread is also redefined on that basis: `s_t = y_mm,t - r_t`.
- The exit price uses the 13-week rate on the exit day for the remaining `t - h` days. Roll-down along the bill curve is not captured (a stated limit).
- Implementation: `research/r3_02_pnl.py`. Test: on simulated i.i.d. funding (mean 4%, sd 10 bp, 400 years of business days) with a constant bill rate equal to the funding mean, the strategy's annualised Sharpe lies within 3 standard errors of 0, the band being `3 sqrt(12/n)` for `n` monthly outcomes (0.15 at `n` = 4,796). Evidence class: simulation.

## Holdout knowledge (R5)

"Unread" means that no holdout file has been downloaded, opened or summarised by this project. It does not mean "unknown". The owner, and Claude, which signed under delegation, may know the general history of money markets from 2023 to 2026, including the debt-ceiling episodes from experience or training data. A language model trained on text covering that period may hold such knowledge without any study file being read. The grid and rules were fixed without looking at study data; that is the only claim made.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-09.
- What it did: drafted this amendment, wrote `research/power/r3_power.py` and `research/r3_02_pnl.py`, ran the simulations, and signed under the owner's delegation.
- Prompts kept: the task brief and replies are in the maintainer's session log, outside this repository; they are not published.
- Claims checked by a human: none yet. All numbers above are unchecked by a person until the owner's review.
- Prior knowledge: see the section above.
