# R3-03 amendment 1: Seasonality in US breakeven inflation

Status: **signed**. Signed by Claude (signing delegated by the owner, 2026-11-07) on 2026-11-09.
- SHA-256 of the body below the marker line: `4e3a54b20dc07ee67d04a5d65d3c56e760e4d4efd7e12d196c79bae08e91d356`
- SHA-256 of the amended prereg `R3-03-breakeven-seasonality.md` (whole file): `de1c6d5b5dab03924e8f0f48346976e678d687252fa6a61acc84892a41494dd2`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- Holdout data has not been read, downloaded or summarised. No study data of any period has been downloaded at signing.
- This file is not edited after signing; a further change is a new amendment.

<!-- body -->
Amends `R3-03-breakeven-seasonality.md` (body SHA-256 `08537a3964958f91e1c7dafd6963612236853244e5b4bb8fd6af91ba2937646a`, file SHA-256 `de1c6d5b5dab03924e8f0f48346976e678d687252fa6a61acc84892a41494dd2`). The original text stands; where this amendment differs, this amendment governs. Common rules: `README.md`.

Date: 2026-11-09. Source of the changes: plan section 13.1, items R1, R2, R5, R6 and R12 (`QUANTFORGE_PLAN.md`, outside this repository).

## Change 1 (R1): pass condition (1) becomes a one-sided test

Reason: the original condition "holdout net Sharpe at least the MDS" passes only about half the time when the true Sharpe equals the MDS, because the estimate is centred on the truth. That is a coin flip at the design point, not 80% power.

Replaces condition (1) of the pass rule and the "Threshold" sentence with:

- `SE` is the preregistered standard error of the holdout annualised net Sharpe at 1x costs (Lo (2002), 3 lags).
- Deflation benchmark: `SR0 = SE * E[max of N standard normals]`, with `N` = 24, the family trial count from `research/trials.csv` (Bailey and Lopez de Prado 2014; E[max] = 1.9798 at N = 24). Under the null of no skill and independent trials the variance of each trial's Sharpe estimate is `SE^2`, so the other trials' holdout values are not needed.
- One-sided p-value: `p = 1 - Phi((SR_hat - SR0) / SE)`; the deflated Sharpe ratio is `1 - p`.
- Condition (1) holds if Holm's procedure across the three R3 studies (Change 2) rejects this study's null. Equivalently, the one-sided lower confidence bound of the deflated Sharpe `SR_hat - SR0`, at the Holm level, is above 0.
- Selection, made explicit because the original text left it implicit: the holdout is run once, on the trial with the highest in-sample net Sharpe at 1x costs.
- Conditions (2) and (3) are unchanged.

Simulated pass probability (`research/power/r3_power.py`, numpy, seed 20261109, 4,000 paths per cell; Gaussian AR(1) net returns; holdout 10.83 years, monthly (130 returns); condition (3) applied; condition (2) not simulated because turnover is unknown before the data is read, so these are upper bounds). Evidence class: simulation.

| True annualised SR | Pass, Holm level 0.05 | Pass, Holm level 0.05/3 |
|---|---|---|
| 0 | 0.0000 | 0.0000 |
| 0.5 | 0.0225 | 0.0060 |
| 0.76 (MDS) | 0.1265 | 0.0508 |
| 0, AR(1) 0.2 | 0.0005 | 0.0000 |

Size at true SR 0 is at most 5% in every cell (`research/power/test_r3_power.py` asserts it). Power at the original MDS of 0.76 is between 5.1% and 12.7%. **This study is underpowered under the amended rule:** a null result says little about a true Sharpe near the MDS. That is stated now, before any data is read.

## Change 2 (R6): Holm correction across the three studies

The three R3 studies are one family. Their p-values from Change 1 are ordered `p_(1) <= p_(2) <= p_(3)`; the null of `p_(j)` is rejected while `p_(j) <= 0.05 / (4 - j)`, stopping at the first failure (Holm 1979). Combined with deflation at N = 24 this is conservative; the conservatism is accepted.

## Change 3 (R6): family trial count

The deflated Sharpe ratio uses N = 24, the number of rows in `research/trials.csv` (8 for R3-01, 12 for R3-02, 4 for R3-03), not this study's own 4. `python tools/quality_gate.py --check-dsr --trials N` rejects any N below the ledger count (tested in `tools/test_tools.py`).

## Change F: forward-log rule

Reason: the original "same rule after 250 US business days" fails by construction, because 250 days can only detect a Sharpe near 2.5 (common rules table).

Replaces the forward-log bullet with: after 250 US business days the forward log **agrees** with the holdout if (a) its annualised net Sharpe has the same sign as the holdout estimate, and (b) its two-sided 95% confidence interval (Lo 2002, iid, daily) contains the holdout estimate. Agreement is reported; it never turns a failed holdout into a pass. Simulated (same script, 20,000 paths): probability of agreement when the true SR and the holdout estimate both equal the MDS, 0.7529; when the true SR is 0 and the holdout estimate is the MDS, 0.4971. The forward log therefore cannot confirm a modest signal by itself; it checks the pipeline and look-ahead.

## Change 5 (R5): vintage CPI seasonal factors

Reason: BLS revises CPI seasonal factors every February for the previous five years (BLS, CPI seasonal adjustment notes; documentation). Factors downloaded today embed holdout-period data and would leak it into the "CPI NSA seasonal factors" forecast source.

Procedure (specified here; nothing is fetched now):
1. Source: ALFRED (St. Louis Fed archival FRED) vintages of `CPIAUCSL` and `CPIAUCNS`, or the archived BLS seasonal-factor release file. Take the latest vintage whose real-time start date is on or before the in-sample end, 2015-12-31.
2. The factor for month `m` is the ratio NSA/SA of that vintage, averaged by calendar month over the in-sample years.
3. Log in `research/vintages.csv`: series id, vintage date, source URL, download time (UTC), SHA-256 of the raw file as downloaded, SHA-256 of the parsed values.
4. The study runner refuses factors whose vintage date is after 2015-12-31 and refuses a run whose logged hash does not match the file.
5. The T5YIE and T10YIE breakevens are market data and are not revised in the same way; their download is logged with its hash as for every source.

## Holdout knowledge (R5)

"Unread" means that no holdout file has been downloaded, opened or summarised by this project. It does not mean "unknown". The owner, and Claude, which signed under delegation, may know the general history of inflation and breakevens from 2016 to 2026, including the 2021 to 2022 shock from experience or training data. A language model trained on text covering that period may hold such knowledge without any study file being read. The grid and rules were fixed without looking at study data; that is the only claim made.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-09.
- What it did: drafted this amendment, wrote `research/power/r3_power.py`, ran the simulations, and signed under the owner's delegation.
- Prompts kept: the task brief and replies are in the maintainer's session log, outside this repository; they are not published.
- Claims checked by a human: none yet. All numbers above are unchecked by a person until the owner's review.
- Prior knowledge: see the section above.
