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
| HR-109 | 32nds third digit (coordinator decision 2026-11-18, maintainer under owner delegation) | CME convention: the third digit is a quarter-32nd, one of 0, 2, 5, 7 (0, 1/4, 1/2, 3/4), and `+` is a half; any other third digit, including 3, is E_SCHEMA; resolutions 32, 64, 128; A3 round trip on the 1/128 grid. Reason: matches the published market convention instead of an invented eighths code; source [CME-32NDS] unverified until a CME page is read. Amends HR-90; rtc_h-0004 changes value (99.52734375 to 99.5234375) and loses blind status |
No existing golden changed value under HR-104 to HR-108 (eqc_h-0001..0008, fxc_h-0001..0007, auc_h-0001..0008 are identical), so none loses blind status. Added hand goldens, not blind: eqc_h-0009..0017, fxc_h-0008, auc_h-0009.
| HR-110 | Compliance date (coordinator decision 2026-11-18) | Current regime is the default. `compliance_date` default 2025-11-03: the adopting release 34-101070, section VI (read 2026-11-18), gives the first business day of November 2025 for Rules 612, 610 and the round-lot definition. Any later SEC extension stays **unverified** (order listings not read); retry from the SEC exemptive-order pages. Reason: a read primary source beats the earlier unverified 2026-11-03 guess; no golden changes (eqc_h-0012 and 0017 use as_of 2024-01-02) |
| HR-111 | Labels (coordinator decision 2026-11-18) | Pure convention operations (`micro.eq.*`, `micro.fx.*`, `micro.rates.*`) carry no label, because they are not venue output; every venue or simulator operation (`exec.sim.*`) keeps its HR-94 label. Reason: a "simulated venue" label on a rounding rule or a formula is wrong information. Golden outputs of eqc_h, fxc_h, rtc_h lose the `label` field only; values are unchanged, labels were never compared by the blind lane, so blind status is kept |
| HR-112 | Session phases in `exec.sim.lit.run` (coordinator decision 2026-11-18: in scope now) | Optional `session` and `PHASE` events as written in `asset-conventions.md` (module table); the closing cross takes on-close orders only (stated simplification); goldens `ses_h` hand, not blind |
| HR-113 | HR-93 error code (coordinator decision 2026-11-18 overnight, owner delegation) | A dark-pool request (or a DARK venue in the router) for an asset class with no dark venue is an invalid input combination: **E_INPUT** (structural cross-field consistency under HR-66), not E_UNSUPPORTED_OPERATION, which the runner reads as "not implemented". Amends HR-93. Goldens acls_h-0004/0005 pin it for all four languages |
| HR-114 | H-24 below 60 % (coordinator decision overnight) | H-24 stays in stage H for now. A second blind packet with the hand-only rtc and fut value cases (rtc_h-0004, 0007, 0011, 0012; fut_h-0004, 0005, 0006) is built at `institutional-quant-engine-plan/stage_h_blind/rates2_packet/` for a blind lane; the leak list is outside the packet |
| HR-115 | CME 32nds source (retry overnight) | Retried the CME rulebook chapter 19 PDF and the 10-Year Note contract-spec page: both timed out twice (2026-11-18). [CME-32NDS] stays **unverified**. Note for the owner: a common reading of the CBOT third digit is eighths (1 = 1/8 ... 7 = 7/8), which conflicts with the HR-109 quarters; unconfirmed either way |
