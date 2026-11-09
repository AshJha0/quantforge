# Rich cheap: 2026-11-09

Result: **PASS** (1 checks, 0 failed, 1 warnings). Generated 2026-11-09T23:44Z by `tools/workflows/`. Batch command: none.

**BLOCKED: no price data.** Fitted-curve residuals from end-of-day reference prices; not executable prices; tradability not established. Both free sources refuse automated use, so this job does not fetch. Place downloaded price files in --data to run the screen (layout in `tools/workflows/rich_cheap.py`).
| Source | Why it is blocked (terms checked 2026-11-07) |
|---|---|
| US Treasury: TreasuryDirect FedInvest | robots.txt disallows all automated clients; terms allow non-commercial personal use only; redistribution needs Fiscal Service's written consent |
| UK gilts: DMO gilt reference prices | automated requests get an anti-bot challenge; terms not readable by a script; robots.txt 404 |


## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| price data available | warn | NOT OK | no source cleared for automated use |

## Data notices

