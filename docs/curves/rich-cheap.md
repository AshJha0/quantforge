# Rich/cheap screen (workflow b)

<p class="note">Status: Specified, implemented, and <strong>blocked on data</strong>. Fitted-curve residuals from end-of-day reference prices; not executable prices; tradability not established.</p>

Workflow (b) screens Treasuries and gilts against a Nelson-Siegel curve fitted to the day's prices (`specifications/04-pricing/workflow-b-rich-cheap.md`). The job, `tools/workflows/rich_cheap.py`, runs daily, but it has no prices to screen yet: both free sources refuse automated use.

## Why it is blocked

| Source | Finding (terms checked 2026-11-07) |
|---|---|
| US Treasury: TreasuryDirect FedInvest | robots.txt disallows all automated clients; terms allow non-commercial personal use only; redistribution needs Fiscal Service's written consent |
| UK gilts: DMO gilt reference prices | automated requests get an anti-bot challenge; terms not readable by a script; robots.txt 404 |

Until a source is cleared, the daily run writes a dated BLOCKED report. If a person downloads price files and places them in `--data`, the job runs the screen, but it publishes only residuals and ranks, never prices.

## What the screen does

1. Settlement T+1 on the market's calendar (`core.calendar.add_business_days`, USGS or GBLO).
2. Universe filters: fixed-coupon nominal bonds with at least 1 year to maturity. Gilts in their ex-dividend period, 7 business days before a coupon, are dropped (edge register E9).
3. Market yield and dirty price from `bond.yield.from_price`, and modified duration from `bond.price.from_yield`. Then a Nelson-Siegel fit with `tau` = 2.5 (`bond.fit.nelson_siegel`), weighted by 1/D_mod² (ruling R2-A5, after GSW 2007 and Anderson-Sleath 2001). US on-the-run and first off-the-run issues in each auction tenor (2, 3, 5, 7, 10, 20 and 30 years) get weight 0, but their residuals are still reported (R2-A6). They are identified from Fiscal Data's open auction API, which is free to use without restriction. No gilt is excluded. The residuals are model minus market dirty price.
4. Yield residual in bp: market yield minus the yield at market clean plus residual. Positive means cheap. A z-score is computed against the bond's own trailing 60 days, once 20 days exist.
5. Ranks within the 1-3, 3-7, 7-15 and 15+ year buckets, with the five cheapest and five richest bonds marked.

No page of results exists until a source is cleared. A study of whether the residuals mean-revert would be an R3 preregistration, not this workflow.
