# Asset-class conventions: equities, FX, rates (H-22, H-23, H-24)

Spec version 0.1.0 (stage H, multi-asset spec lane, drafted 2026-11-18; not normative until the stage H coordinator confirms HR-80 to HR-99 in `../stage-h-rulings-multiasset.md`). Plan item: owner decision 2026-11-18 "multi-asset microstructure in stage H (full)".

**Labels.** Equities outputs on real data: "IEX only; one venue". FX and rates outputs: "simulated venue; not a real exchange". No venue's rule book is reproduced; every venue number below is a **parameter** with a documented default, never a hard-coded constant (HR-80).

**Plain idea.** The engine works in integer ticks and lots (HR-20). Each asset class only changes how a human price becomes ticks, how big a lot is, when the venue trades, what a fill costs and when it settles. This page fixes those mappings.

## Sources (free public documents; evidence class in brackets)
- [REGNMS-612] SEC Rule 612 (17 CFR 242.612), minimum pricing increment. Current text: $0.0001 below $1.00; at $1.00 or more $0.01, or $0.005 for a stock whose time-weighted average quoted spread is at most $0.015 (tier re-evaluated every six months). law.cornell.edu, public. [regulation text; **read 2026-11-18** (source check, MULTIASSET_SOURCE_CHECK.md)]
- [REGNMS-610] SEC Rule 610(c) (17 CFR 242.610), access-fee cap. Current text: $0.001 per share for quotes of $1.00 or more, 0.1 % of price below (old regime: $0.003, 0.3 %). [regulation text; **read 2026-11-18** (source check)]
- [REGNMS-600] SEC Rule 600(b)(93) (17 CFR 242.600), round lot as amended: 100 shares up to $250.00, 40 to $1,000.00, 10 to $10,000.00, 1 above. [regulation text; **read 2026-11-18** (source check retry)]
- [FX-USD-T1] Market convention for USD pairs: a USD-only holiday on T+1 does not stop the spot count; the spot date itself must be a USD business day. [industry convention; **partly verified**: no central-bank source found, source check retry 2026-11-18]
- [CBOE-AUC] Cboe (Bats) auction model: maximum volume, then minimum imbalance, then imbalance side, then nearest the reference. [venue documentation; **unverified this session**]
- [SEC-2024-TICK] SEC 2024 amendments to Rules 612/610/600 (half-penny tier, $0.001 fee cap, round lots by price). The amended text is codified (read 2026-11-18). Compliance date used as the default switch (parameter `compliance_date`): **2025-11-03**, the first business day of November 2025, for Rules 612, 610 and 600(b)(93) as adopted (SEC release 34-101070, section VI, **read 2026-11-18**). Whether a later SEC order moved it is **unverified** (the order listings were not read); HR-110.
- [SEC-T1] SEC 2023 T+1 standard settlement amendment to Rule 15c6-1, compliance 2024-05-28. [regulation; **unverified this session**]
- [IEX-AUC] IEX Exchange rule book and auction pages (iex.io), opening/closing auction price determination. [venue documentation; **unverified this session**; used only for the shape of the uncrossing criteria]
- [FXGC] Global Foreign Exchange Committee, "FX Global Code", Principle 17 (last look). globalfxc.org. [industry code; **unverified this session**]
- [BIS-FX] BIS Triennial Survey definitions (spot = settlement within two business days). bis.org. [central-bank; **unverified this session**]
- [CME-ZN] CME Group, 10-Year T-Note futures contract specs, https://www.cmegroup.com/markets/interest-rates/us-treasury/10-year-us-treasury-note.contractSpecs.html (read 2026-11-19 in a browser): face $100,000; outright minimum tick 1/2 of 1/32 = $15.625; calendar-spread tick 1/8 of 1/32; quarterly March, June, September, December, three consecutive quarters listed; trading terminates 12:01 p.m. CT seven business days before the last business day of the contract month; physically deliverable; deliverable grade 6.5 to under 8 years remaining; conversion factor at 6 %. [exchange spec; **verified 2026-11-19** (HR-117)]
- [CME-ZB] CME Group, U.S. Treasury Bond futures specs (tick 1/32 = $31.25). [exchange spec; **unverified this session**]
- [CME-32NDS] CME Group Treasury futures price quotation convention (third digit in quarter-32nds: 0, 2, 5, 7). [exchange education page; read 2026-11-19: CME Group, "Calculating U.S. Treasury Pricing", https://www.cmegroup.com/education/courses/introduction-to-treasuries/calculating-us-treasury-pricing , whose futures examples give 134-010 = 1/32, 134-012 = 1 1/4, 134-015 = 1 1/2 and 134-017 = 1 3/4 thirty-seconds. `+` for a half is on that page for cash prices only; accepting it for futures text is this spec's own choice. Eighth-tick contracts (2-year and 3-year notes, tick 1/8 of 1/32) show other third digits (1, 3, 6, 8 seen on the 2-year quote page, 2026-11-19); no CME page read states that mapping, so those contracts are **not supported** (HR-118)]
- [UST-BILL] US Treasury (TreasuryDirect), bill discount-basis price formula. [government; **unverified this session**]

Every source tagged unverified must be read and re-tagged "read <date>" before v0.10.0 (HR-98). No London Stock Exchange or LSEG material is used anywhere (HR-99).

## 1. Equities (H-22)

### 1.1 Tick table and rounding (HR-81)
Parameter `tick_table`: list of `(price_floor, tick)`. The tick that applies is that of the highest `price_floor <= price`. Dated rule versions (coordinator ruling 2026-11-18, after the HR-98 source check): input `as_of` (ISO date, optional) and `compliance_date` (default 2025-11-03; see [SEC-2024-TICK]); with no `as_of`, or `as_of` on or after the compliance date, the **current** rules apply; before it, the old regime. Current default [REGNMS-612]: input `tick_tier` `PENNY` (default) gives `[(0, 0.0001), (1.00, 0.01)]`, `HALF_PENNY` gives `[(0, 0.0001), (1.00, 0.005)]` (the tier is a per-stock input; the six-monthly spread test is not modelled). Old regime: `PENNY` only; `HALF_PENNY` before the compliance date, or with an explicit `tick_table`, is `E_INPUT`.
Operation `micro.eq.round_price(price, side, tick_table)`: a buy limit rounds **down** to the grid, a sell limit rounds **up** (never more aggressive than asked). Exact decimals. A rounded sell that lands exactly on a floor is valid on both grids.
Errors: price <= 0 `E_DOMAIN`.

### 1.2 Lots (HR-82)
Operation `micro.eq.round_lot(price, as_of)`, output `round_lot` (int): current rule [REGNMS-600] 100 shares up to $250.00, 40 to $1,000.00, 10 to $10,000.00, 1 above; old regime 100 shares at every price. `min_qty` 1. Orders below `round_lot` are odd lots: accepted and matched normally, **not** counted in the displayed best quote (stated simplification).

### 1.3 Hours and phases (HR-83)
Parameter `session`: `{tz: "America/New_York", open_auction: "09:30:00", continuous: ["09:30:00","16:00:00"], close_cutoff: "15:50:00", close_auction: "16:00:00"}`. Phases: `PRE_OPEN` (orders accepted, no matching), opening uncross, `CONTINUOUS`, `PRE_CLOSE` (only on-close orders accepted), closing uncross, `CLOSED`. The holiday calendar is an input.

### 1.4 Auction uncrossing (HR-84): see `../10-execution/auction.md`.

### 1.5 Fees (HR-85)
`fee_schedule` per phase: `{maker_rebate, taker_fee, auction_fee}` per share, signed (HR-30). Operation `micro.eq.fee_check(price, taker_fee, cap_check, as_of)`, output `cap`, `taker_fee`. A `taker_fee` above the [REGNMS-610] cap for the price band gives `E_DOMAIN` unless `cap_check=false`. Current cap $0.001 per share at $1.00 or more, 0.1 % of price below; old regime (`as_of` before the compliance date) $0.003 and 0.3 %.

### 1.6 Settlement (HR-86)
`settle_lag` business days, default 1 [SEC-T1], on the supplied calendar.

## 2. FX spot (H-23)

### 2.1 Pips (HR-87)
`pip` per pair: 0.0001, or 0.01 when JPY is the quote currency. Tick = pip/10 by default. Pip value in quote currency = notional x pip.

### 2.2 Pair order (HR-88)
Base is the currency earlier in `EUR, GBP, AUD, NZD, USD, CAD, CHF, JPY`; a pair given the other way round is `E_INPUT`. Amounts are in base currency.

### 2.3 Spot date (HR-89)
T+2 business days; pairs in `t1_pairs` (default `[USDCAD]`) T+1 [BIS-FX]. A day counts if it is a business day in both currencies, except the first day after trade (T+1), which needs only the non-USD currencies: a USD-only holiday on T+1 does not stop the count [FX-USD-T1] (source check retry 2026-11-18; replaces the earlier "not modelled" note). The value date must also be a USD business day (roll forward). T+1 pairs need both currencies on their one day. Calendars are inputs.

## 3. Rates (H-24)

### 3.1 32nds quoting (HR-90)
Text `H-FF[q]`: handle `H`, `FF` = 32nds 00 to 31, optional third digit in quarter-32nds by the CME convention for quarter-tick contracts [CME-32NDS, read 2026-11-19] (HR-109, amends the eighths of HR-90; eighth-tick contracts are not supported, HR-118): `''` or `0` = 0, `2` = 1/4, `5` or `+` = 1/2, `7` = 3/4; any other third digit (1, 3, 4, 6, 8, 9) is `E_SCHEMA`, as is any other malformed text. Value = H + (FF + q)/32. Formatting takes a `resolution` (32, 64 or 128 parts per point); a price not exactly on that grid is `E_DOMAIN`; a half is printed `+`.

### 3.2 Futures contract specs (HR-91)
`contract`: `{symbol, face, tick, tick_value, months, last_trade_rule}`. Defaults: ZN face 100,000, tick 1/64 point, tick value 15.625 [CME-ZN, verified 2026-11-19]; ZB tick 1/32, tick value 31.25 [CME-ZB]. Tick value = face x tick / 100.

### 3.3 Yield and price (HR-92)
Coupon bond on a coupon date, street convention: P = sum_{i=1..n} (100 c/f)/(1+y/f)^i + 100/(1+y/f)^n. Off coupon dates the existing `04-pricing` bond routines are reused (no new maths). Bill: P = 100 (1 - d days/360) [UST-BILL]. Yield from price: existing `core.solve` Brent, tolerance 1e-12.

## Convergence and limit cases
Only `micro.rates.bond_yield` is iterative: Brent (`core.solve`) on the bracket (-0.99 f, 10), absolute tolerance 1e-12 in the yield; no root in the bracket is `E_DOMAIN`. Its golden is compared within tolerance (class `root_finding`); every other operation here is exact decimal arithmetic.

| Limit | Behaviour | Check |
|---|---|---|
| price = 100, coupon c | yield = c (par bond) | rtc_h-0011 |
| yield from an exact price | returns the yield the price was built from, within 1e-12 | rtc_h-0012 against rtc_h-0008 |
| price at or below 0 | `E_DOMAIN` before iterating | rtc_h error cases |
| integer input beyond +-(2^53-1) | `E_LIMIT` (HR-116) | fxv_h-0015 to 0018, fut_h-0009, 0010 |

## How each plugs into existing modules
| Module | Change |
|---|---|
| `exec.sim.lit.run` (`lit-matching.md`) | optional `session` `{phase (default PRE_OPEN), ref_price, tie_break}` and `PHASE` events (HR-112): PRE_OPEN collects LIMIT/MARKET orders in a call book, CONTINUOUS uncrosses it with `exec.sim.auction.uncross` (OPEN) and rests unfilled limits in allocation order, PRE_CLOSE takes only `on_close` orders into a second call book, CLOSED uncrosses it (CLOSE) and cancels on-close leftovers; wrong-phase orders are rejected `PHASE`; `fee_schedule.auction_fee` x notional per auction fill; outputs gain `auctions` and `phase`. Stated simplification: the continuous book does not join the closing cross. Without `session` the engine and its goldens are unchanged. Goldens `ses_h` |
| dark pool | equities only (midpoint of the lit NBBO); `config.asset_class` (`EQUITY` default, `FX`, `RATES`); FX and rates `E_INPUT` (HR-93 as amended by HR-113; goldens acls_h-0004/0005) |
| SOR | order and venues gain `asset_class` (default `EQUITY`); a venue of another class than the order is `E_INPUT`; a DARK venue of class FX or RATES is `E_INPUT` (HR-113); goldens `acls_h` |
| paper trading | label per class (HR-94); settlement lag sets the cash posting date; FX cash per currency; futures P&L = ticks x tick value, variation margin daily |
| order book | unchanged (integer ticks) |

## Golden value cases (hand-derived; Expected and Derivation columns are stripped for the blind lane)
| Case | Input | Expected | Derivation |
|---|---|---|---|
| eqc_h-0001 | round_price 10.005 buy, default table | 10.00 | at least 1, tick 0.01, down |
| eqc_h-0002 | round_price 10.005 sell, default table | 10.01 | up |
| eqc_h-0003 | round_price 0.12345 buy, default table | 0.1234 | below 1, tick 0.0001, down |
| eqc_h-0004 | round_price 0.12345 sell, default table | 0.1235 | up |
| eqc_h-0005 | round_price 0.99995 sell, default table | 1.0000 | up on 0.0001 grid; also on 0.01 grid |
| eqc_h-0006 | round_price 25.00 buy, default table | 25.00 | on grid |
| eqc_h-0007 | taker_fee 0.0031 at price 20, cap_check on | E_DOMAIN | cap 0.003 |
| eqc_h-0008 | settle date, trade Fri 2026-11-20, lag 1, weekends only | 2026-11-23 | next business day |
| eqc_h-0009 | round_price 10.003 buy, HALF_PENNY tier | 10.000 | tick 0.005, down (added 2026-11-18, not blind) |
| eqc_h-0010 | round_price 10.003 sell, HALF_PENNY tier | 10.005 | up (added, not blind) |
| eqc_h-0011 | taker_fee 0.0015 at price 20, current rule | E_DOMAIN | cap 0.001 (added, not blind) |
| eqc_h-0012 | taker_fee 0.0015 at price 20, as_of 2024-01-02 | cap 0.003 | old regime (added, not blind) |
| eqc_h-0013 | taker_fee 0.0005 at price 0.50 | cap 0.0005 | 0.1 % x 0.50 (added, not blind) |
| eqc_h-0014..0017 | round_lot at 250.00, 250.01, 10000.01; 10000.01 as_of 2024-01-02 | 100, 40, 1, 100 | Rule 600(b)(93) tiers; old regime (added, not blind) |
| fxc_h-0001 | pip value EURUSD notional 1,000,000 | 100 USD | 1e6 x 0.0001 |
| fxc_h-0002 | pip value USDJPY notional 1,000,000 | 10000 JPY | 1e6 x 0.01 |
| fxc_h-0003 | spot EURUSD, trade Mon 2026-11-16, no holidays | 2026-11-18 | T+2 |
| fxc_h-0004 | spot EURUSD, trade Tue 2026-11-24, USD holiday 2026-11-26 | 2026-11-27 | T+2 is a USD holiday, roll to Fri |
| fxc_h-0005 | spot EURUSD, trade Fri 2026-11-20, no holidays | 2026-11-24 | Mon, Tue |
| fxc_h-0006 | spot USDCAD, trade Fri 2026-11-20, no holidays | 2026-11-23 | T+1 pair |
| fxc_h-0007 | pair USDEUR | E_INPUT | EUR ranks before USD |
| fxc_h-0008 | spot EURUSD, trade Wed 2026-11-25, USD holiday 2026-11-26 | 2026-11-27 | T+1 USD-only holiday does not stop the count (added 2026-11-18, not blind) |
| rtc_h-0001 | parse 99-16 | 99.5 | 99 + 16/32 |
| rtc_h-0002 | parse 99-16+ | 99.515625 | 99 + 16.5/32 |
| rtc_h-0003 | parse 99-162 | 99.5078125 | 99 + 16.25/32 |
| rtc_h-0004 | parse 99-167 | 99.5234375 | 99 + 16.75/32 (HR-109; was 16.875/32 under HR-90; not blind) |
| rtc_h-0005 | format 101.296875, resolution 64 | 101-09+ | 0.296875 x 32 = 9.5 |
| rtc_h-0006 | format 101.3, resolution 128 | E_DOMAIN | 9.6/32 not on 1/128 grid |
| rtc_h-0007 | tick value, face 100,000, tick 1/64 | 15.625 | 100000 x 0.015625 / 100 |
| rtc_h-0008 | price, 1 y bond, 4 % semiannual, yield 5 %, on coupon date | 99.036287924 (9 dp) | 2/1.025 + 102/1.025^2 |
| rtc_h-0009 | price, 2 y bond, 4 % semiannual, yield 4 %, on coupon date | 100 | coupon equals yield |
| rtc_h-0010 | bill, discount 5 %, 91 days | 98.736111111 (9 dp) | 100 (1 - 0.05 x 91/360) |
| rtc_h-0011 | yield, 2 y bond, 4 % semiannual, price 100 | 0.04 | coupon equals yield (added, not blind) |
| rtc_h-0012 | yield, 1 y bond, 4 % semiannual, price 99.036287923854848305 | 0.05 | inverse of rtc_h-0008 (added, not blind) |

## Acceptance (fixed before any run, HR-95)
- A1 all goldens here and in `auction.md`, `fx-rfq-venue.md`, `rates-futures-venue.md` pass in all four languages with byte-identical outputs.
- A2 the blind lane (DR-H2) re-derives at least 60 % of value cases; every mismatch explained before release.
- A3 property tests: rounding never makes an order more aggressive; parse(format(x)) = x on the 1/128 grid (HR-109; was 1/256); spot date is a good day and at least T+1; auction volume is maximal over the candidate grid.
- A4 every venue or simulator output carries its label (HR-94, HR-111); convention outputs carry none.
- A5 no source still tagged unverified at release (HR-98).

## Output shapes (pre-comparison spec fix, 2026-11-18, HR-100)
Operation names (oracle lane, 2026-11-18): `micro.eq.round_price`, `micro.eq.fee_check`, `micro.eq.round_lot`, `micro.eq.settle_date`, `micro.fx.pip_value`, `micro.fx.spot_date`, `micro.rates.parse_32nds`, `micro.rates.format_32nds`, `micro.rates.tick_value`, `micro.rates.bond_price` (`coupon`, `frequency`, `periods`, `yield`), `micro.rates.bond_yield` (`coupon`, `frequency`, `periods`, `price`; output `yield`, a binary64 Real by Brent, tolerance 1e-12, golden class `root_finding`), `micro.rates.bill_price` (`discount`, `days`). Every decimal input is an HR-12 decimal string. Labels (HR-111): these pure convention operations carry **no** label (they are not venue output); every venue or simulator operation (`exec.sim.*`) keeps its label. Every venue or simulator success output is `{"status": "ok", "label": <HR-94 label>, ...fields}` (convention operations: no `label`, HR-111); every error `{"status": "error", "error_code": <code>}`. Decimals are JSON strings compared by value (trailing zeros are representation only). Fields:
| Operation | Fields |
|---|---|
| `micro.eq.round_price` | `price` (decimal, printed at the tick decimals) |
| equities settle date | `settle_date` (ISO date) |
| FX pip value | `pip_value` (decimal), `currency` (quote currency) |
| FX spot date | `spot_date` (ISO date) |
| 32nds parse | `value` (decimal) |
| 32nds format | `text` |
| futures tick value | `tick_value` (decimal) |
| bond or bill price | `price` (decimal; goldens state 9 dp, compared to 5e-10 absolute) |
