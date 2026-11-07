# R3-02: Overnight funding against Treasury bills (OIS against T-bill and repo)

Status: **signed**. Signed by Claude (signing delegated by the owner, 2026-11-07) on 2026-11-07.
- SHA-256 of the body below the marker line: `48c3759c6d936305fd3f79f672c7afbe2957f87723d6440953939a956955af6a`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- Holdout data has not been read, downloaded or summarised. No study data of any period has been downloaded at signing.
- This file is not edited after signing; a change is a new prereg.

<!-- body -->
Common rules: `README.md`. This replaces the futures-against-cash-carry study, because no free, redistributable futures settlement history exists (plan 11.1.2).

**Label:** signal on a fitted curve; tradability not established.

## Question
Does the spread between 3-month Treasury bill yields and expected overnight funding mean-revert, so that its z-score predicts its change over the next month? Expected funding is measured three ways: SOFR, TGCR and BGCR.

## Data
- NY Fed reference rates: SOFR, TGCR and BGCR, and the 90-day SOFR average, daily from 2018-04-02 (free with attribution under NY Fed terms).
- US Treasury daily bill rates, 13-week coupon-equivalent (public domain, home.treasury.gov).
- In-sample: 2018-04-02 to 2022-12-30. Holdout: 2023-01-03 to 2026-10-30, unread. Forward log: from signing.

## Method (fixed)
- Spread `s_t = bill_3M,t - r_t`, in bp, where `r_t` is the trailing 20-business-day mean of the overnight rate (SOFR, TGCR or BGCR). A 3-month OIS quote is not free, so the trailing mean stands in for expected funding (a stated limit).
- Signal `z_t` over a trailing window `L`. Position: long bills against funding when `z_t > k`, the reverse when `z_t < -k`; held 21 business days; non-overlapping monthly entries on the first business day of each month.
- Outcome: the change in `s` over the holding period, in bp, times the position.
- Grid (12 trials): funding rate in {SOFR, TGCR, BGCR} by `L` in {60, 250} by `k` in {1.0, 2.0}.
- Month-end, quarter-end and year-end days are kept. A dummy-controlled check, which drops those days, is reported alongside but is not the test.

## Costs and financing (sensitivity only)
1x = 0.5 bp per round trip on bills, and 2 bp a year of balance-sheet charge on gross notional.

## Statistics and pass rule
- Monthly non-overlapping outcomes. Sharpe standard error from a stationary block bootstrap, mean block 3 months, 10,000 draws.
- Holdout T = 3.83 years, MDS = 1.27. **Low power, stated in advance:** a true annualised Sharpe below about 1.3 is unlikely to be detected. **Threshold:** holdout deflated Sharpe ratio above 0.95, and holdout net Sharpe at least 1.27.
- Regime note: the 2023 holdout includes the debt-ceiling episode and reserve changes. Sub-period sign stability is the guard.
- **Pass rule (all three, per `research/TEMPLATE.md` section 5):** (1) holdout deflated Sharpe ratio above 0.95 and holdout net Sharpe at least the MDS above; (2) holdout net Sharpe still above 0 at 2x costs; (3) the holdout Sharpe has the same sign in each third of the holdout. Otherwise the study fails and is published as a null result.
- **Forward log:** live paper out-of-sample from the signing date, 2026-11-07, judged on the same rule after 250 US business days.

## Known limits
Bill coupon-equivalent yields are not executable prices. Repo is a published average, not a dealer's rate. No balance-sheet or SLR modelling.
