# Workflow (b): Treasury and gilt rich/cheap screen

Spec version 1.0.0. Status: Specified (phase R2, plan 11.2.7(b)). Infra builds the scheduled job, `tools/workflows/rich_cheap.py`, from this spec. Like workflows (a) and (c), the job holds no financial logic. It selects and filters bonds, sends cases through the CLI's batch mode, and ranks what comes back.

**Label on every report:** *fitted-curve residuals from end-of-day reference prices; not executable prices; tradability not established.*

## Data

| Market | Source | What it gives | Terms |
|---|---|---|---|
| US Treasury | TreasuryDirect FedInvest "Securities prices", daily | CUSIP, type, coupon, maturity, end-of-day buy, sell and EOD prices | US government work; `sources.json` row to add, terms read before the first run |
| UK gilts | UK DMO "Gilt reference prices", daily | ISIN, coupon, maturity, clean and dirty reference prices | Read the DMO terms before recording; publish only derived residuals if redistribution is unclear |

Both are recorded by the Actions recorder under `tools/recorder/sources.json` rules: raw files are not committed until the owner reviews the source.

## Universe and filters

Keep fixed-coupon nominal bonds only. Drop bills, FRNs, TIPS and index-linked gilts, STRIPS, and callable or rump issues. Drop bonds with less than 1 year to maturity, which are dominated by money-market effects. Treasuries use the EOD price, or the buy/sell midpoint if EOD is missing; gilts use the clean reference price. Settlement: T+1 for both. Every bond goes through `bond.yield.from_price` first, and one that returns an error is dropped and listed.

Conventions: Treasuries semi-annual, ACT/ACT ICMA. Gilts semi-annual, ACT/ACT ICMA, but gilts trade ex-dividend for 7 business days before a coupon, which `04-pricing/bonds.md` does not model (edge register E9). A gilt inside its ex-dividend period is dropped and listed.

## Calculation (all through the CLI)

1. `bond.fit.nelson_siegel` on the day's universe, per market, with `tau` fixed at 2.5 years (the stage D setting) and equal weights. The fit's repricing error is reported.
2. The fit's `residuals` output is model minus market dirty price for every bond (`bonds.md`), so the job computes no price itself. `model_clean = market_clean + residual`.
3. Per bond:
   - `price_residual = residual` (per 100): positive means the bond is cheap against the curve;
   - `yield_residual_bp` = (market yield - model yield) x 10,000, with both yields from `bond.yield.from_price`, at `market_clean` and at `model_clean`;
   - `zscore` = the yield residual against that bond's own trailing 60 published days in the forward log, or `null` with fewer than 20 days.
4. Rank by `yield_residual_bp` within maturity buckets: 1-3, 3-7, 7-15 and 15+ years.

## Report

A dated Markdown report and JSON twin per market, in `reports/workflows/YYYY-MM-DD/`, with:
- the header: date, source notice, universe size, dropped bonds with reasons, implementation version, and the label above;
- the fit: betas, `tau`, RMS and worst repricing error;
- a table per bucket: identifier, coupon, maturity, market clean, model clean, yield residual (bp), z-score, rank. The five cheapest and five richest bonds are marked;
- checks: fit RMS below 0.25 per 100 (warn), at least 20 bonds per market (fail), no CLI error (fail).

The JSON twin holds every number. Raw prices appear in the report only if the source's terms allow it; otherwise only residuals and ranks do.

## Acceptance (R2)

The job runs daily on the scheduled workflow and writes a report for both markets. The R2 deliverable is the report and its checks. Any study of whether residuals mean-revert is an R3 prereg, held to the 11.3 standard, not this workflow.
