# Stage H rulings, multi-asset microstructure H-22, H-23, H-24 (HR-80 to HR-99): DRAFT 2026-11-18

Drafted on branch `h-multiasset` from the owner decision of 2026-11-18 (end of `STAGE_H_START.md`). Not normative until the stage H coordinator confirms them. Numbering starts at HR-80 (HR-59 to HR-79 left free for other lanes). Append-only once confirmed. Covers `09-microstructure/asset-conventions.md`, `10-execution/auction.md`, `10-execution/fx-rfq-venue.md`, `10-execution/rates-futures-venue.md`.

| # | Point | Proposed ruling |
|---|---|---|
| HR-80 | Venue numbers | Every tick, lot, hour, fee, contract and settlement number is a parameter with a sourced default; no venue rule book reproduced |
| HR-81 | Equity ticks | Rule 612 table by default; buy rounds down, sell rounds up; the 2024 half-penny table is an option, off by default |
| HR-82 | Lots | Round lot 100; odd lots trade but are excluded from the displayed quote |
| HR-83 | Session | Phases PRE_OPEN, CONTINUOUS, PRE_CLOSE, CLOSED; times and holiday calendar are inputs |
| HR-84 | Uncrossing | Maximum volume, then minimum absolute imbalance, then imbalance side (all positive: highest, all negative: lowest), then nearest reference price; price-time allocation |
| HR-85 | Fees | Signed per-share maker, taker and auction fees; Rule 610 cap check on by default |
| HR-86 | Settlement | Equities T+1 by default; lag is a parameter |
| HR-87 | Pips | 0.0001, or 0.01 for a JPY quote currency; tick = pip/10 |
| HR-88 | Pair order | Priority EUR, GBP, AUD, NZD, USD, CAD, CHF, JPY; a reversed pair is E_INPUT |
| HR-89 | Spot date | T+2 (USDCAD T+1); good day in both currencies and in USD; the USD-only T+1 holiday exception is not modelled, stated |
| HR-90 | 32nds | `H-FF[f]` with f in {1, 2, +, 5, 6, 7} as eighths of a 32nd; formatting is E_DOMAIN off the requested grid |
| HR-91 | Futures specs | Contract object; ZN and ZB defaults from CME public specs |
| HR-92 | Yield and price | Street convention on coupon dates; existing 04-pricing for accrued; bills on discount basis; futures variation margin daily on the last trade |
| HR-93 | Dark pool | Equities only; FX and rates E_UNSUPPORTED_OPERATION |
| HR-94 | Labels | "IEX only; one venue" on IEX data; "simulated venue; not a real exchange" on FX and rates; on every output |
| HR-95 | Acceptance | A1 to A5 and all goldens (eqc, fxc, rtc, auc, fxv, fut) fixed in this commit before any run; they count as outside-checked only after the blind lane (DR-H2) |
| HR-96 | Auction leftovers | Unfilled MARKET and on-close orders cancelled after the uncross; final tie goes to the higher price |
| HR-97 | Last look | Strict threshold on the mid move in pips over the hold; symmetric by default; random reject from `u` (core.rng in simulation, explicit in goldens) |
| HR-98 | Sources | Every source tagged unverified is read and re-tagged before v0.10.0 |
| HR-99 | Excluded | No London Stock Exchange or LSEG material; no Nasdaq or LOBSTER sign-ups; IEX HIST used only if `IEX_HIST_TERMS_CHECK.md` clears it (no account, no spend); currently not cleared |

## Pre-comparison spec fixes (2026-11-18, after the blind lane froze its file, before comparing)
| # | Point | Ruling |
|---|---|---|
| HR-100 | Output shapes | Field names and shapes fixed in each spec (Output shapes sections); decimals as strings compared by value |
| HR-101 | No auction | price null, volume 0, imbalance 0; limit orders rest, MARKET orders cancelled |
| HR-102 | fut_h-0004/0005 | One participant's round trip against other resting orders; fee per contract per side |
| HR-103 | Variation margin | Previous mark = fill price on the trade day, previous settlement afterwards |
Cases whose answer was decided by HR-102 or HR-103 (fut_h-0004, 0005, 0006) do not count as blind.

## Rule versions after the HR-98 source check (coordinator rulings 2026-11-18; source `MULTIASSET_SOURCE_CHECK.md`)
| # | Point | Ruling |
|---|---|---|
| HR-104 | Rule 612 tick | Dated rule versions: current two-tier rule by default (`tick_tier` PENNY or HALF_PENNY $0.005 at $1.00 or more); `as_of` before `compliance_date` (default 2026-11-03, **unverified**) selects the old penny table. Amends HR-81 |
| HR-105 | Rule 610 cap | Current cap $0.001 per share at $1.00 or more, 0.1 % below; old regime $0.003 / 0.3 % by `as_of`. Amends HR-85 |
| HR-106 | Round lot | Amended Rule 600(b)(93): 100 up to $250, 40 to $1,000, 10 to $10,000, 1 above; old regime 100. Amends HR-82 |
| HR-107 | FX spot | A USD-only holiday on T+1 does not stop the count (convention, partly verified). Amends HR-89 |
| HR-108 | Auction tie-break | Venue parameter `tie_break`: `CBOE` (default, the HR-84 steps, re-cited to the Cboe model) or `IEX` (nearest the reference midpoint, then higher). Amends HR-84 |
| HR-109 | 32nds `3` | The digit `3` (3/8 of a 32nd) is accepted and printed, so every 1/256 point formats (A3); fills a gap in HR-90. Implementation-lane proposal, **needs the owner or coordinator** |
No existing golden changed value under HR-104 to HR-108 (eqc_h-0001..0008, fxc_h-0001..0007, auc_h-0001..0008 are identical), so none loses blind status. Added hand goldens, not blind: eqc_h-0009..0017, fxc_h-0008, auc_h-0009.
