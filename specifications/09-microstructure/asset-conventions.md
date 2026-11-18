# Asset-class conventions: equities, FX, rates (H-22, H-23, H-24)

Spec version 0.1.0 (stage H, multi-asset spec lane, drafted 2026-11-18; not normative until the stage H coordinator confirms HR-80 to HR-99 in `../stage-h-rulings-multiasset.md`). Plan item: owner decision 2026-11-18 "multi-asset microstructure in stage H (full)".

**Labels.** Equities outputs on real data: "IEX only; one venue". FX and rates outputs: "simulated venue; not a real exchange". No venue's rule book is reproduced; every venue number below is a **parameter** with a documented default, never a hard-coded constant (HR-80).

**Plain idea.** The engine works in integer ticks and lots (HR-20). Each asset class only changes how a human price becomes ticks, how big a lot is, when the venue trades, what a fill costs and when it settles. This page fixes those mappings.

## Sources (free public documents; evidence class in brackets)
- [REGNMS-612] SEC Rule 612 (17 CFR 242.612), minimum pricing increment: no quote below $0.01 increments at $1.00 or more, $0.0001 below $1.00. eCFR, public. [regulation text; **unverified this session**]
- [REGNMS-610] SEC Rule 610(c) (17 CFR 242.610), access-fee cap $0.003 per share for quotes of $1.00 or more, 0.3 % of price below. [regulation text; **unverified this session**]
- [SEC-2024-TICK] SEC 2024 amendments to Rules 612/610 (half-penny tick for some NMS stocks, lower fee cap); compliance dates later moved. [**unverified**; modelled only as an alternative tick table, off by default]
- [SEC-T1] SEC 2023 T+1 standard settlement amendment to Rule 15c6-1, compliance 2024-05-28. [regulation; **unverified this session**]
- [IEX-AUC] IEX Exchange rule book and auction pages (iex.io), opening/closing auction price determination. [venue documentation; **unverified this session**; used only for the shape of the uncrossing criteria]
- [FXGC] Global Foreign Exchange Committee, "FX Global Code", Principle 17 (last look). globalfxc.org. [industry code; **unverified this session**]
- [BIS-FX] BIS Triennial Survey definitions (spot = settlement within two business days). bis.org. [central-bank; **unverified this session**]
- [CME-ZN] CME Group, 10-Year T-Note futures contract specs (face $100,000; tick one-half of 1/32 = $15.625). cmegroup.com. [exchange spec; **unverified this session**]
- [CME-ZB] CME Group, U.S. Treasury Bond futures specs (tick 1/32 = $31.25). [exchange spec; **unverified this session**]
- [UST-BILL] US Treasury (TreasuryDirect), bill discount-basis price formula. [government; **unverified this session**]

Every source tagged unverified must be read and re-tagged "read <date>" before v0.10.0 (HR-98). No London Stock Exchange or LSEG material is used anywhere (HR-99).

## 1. Equities (H-22)

### 1.1 Tick table and rounding (HR-81)
Parameter `tick_table`: list of `(price_floor, tick)`. Default [REGNMS-612]: `[(0, 0.0001), (1.00, 0.01)]`. The tick that applies is that of the highest `price_floor <= price`.
Operation `micro.eq.round_price(price, side, tick_table)`: a buy limit rounds **down** to the grid, a sell limit rounds **up** (never more aggressive than asked). Exact decimals. A rounded sell that lands exactly on a floor is valid on both grids.
Errors: price <= 0 `E_DOMAIN`.

### 1.2 Lots (HR-82)
`round_lot` default 100 shares; `min_qty` 1. Orders below `round_lot` are odd lots: accepted and matched normally, **not** counted in the displayed best quote (stated simplification).

### 1.3 Hours and phases (HR-83)
Parameter `session`: `{tz: "America/New_York", open_auction: "09:30:00", continuous: ["09:30:00","16:00:00"], close_cutoff: "15:50:00", close_auction: "16:00:00"}`. Phases: `PRE_OPEN` (orders accepted, no matching), opening uncross, `CONTINUOUS`, `PRE_CLOSE` (only on-close orders accepted), closing uncross, `CLOSED`. The holiday calendar is an input.

### 1.4 Auction uncrossing (HR-84): see `../10-execution/auction.md`.

### 1.5 Fees (HR-85)
`fee_schedule` per phase: `{maker_rebate, taker_fee, auction_fee}` per share, signed (HR-30). A `taker_fee` above the [REGNMS-610] cap for the price band gives `E_DOMAIN` unless `cap_check=false`.

### 1.6 Settlement (HR-86)
`settle_lag` business days, default 1 [SEC-T1], on the supplied calendar.

## 2. FX spot (H-23)

### 2.1 Pips (HR-87)
`pip` per pair: 0.0001, or 0.01 when JPY is the quote currency. Tick = pip/10 by default. Pip value in quote currency = notional x pip.

### 2.2 Pair order (HR-88)
Base is the currency earlier in `EUR, GBP, AUD, NZD, USD, CAD, CHF, JPY`; a pair given the other way round is `E_INPUT`. Amounts are in base currency.

### 2.3 Spot date (HR-89)
T+2 business days; pairs in `t1_pairs` (default `[USDCAD]`) T+1 [BIS-FX]. A day counts if it is a business day in both currencies; the value date must also be a USD business day (roll forward). Calendars are inputs. Not modelled (stated): the market rule letting a USD-only holiday on T+1 count for non-USD crosses.

## 3. Rates (H-24)

### 3.1 32nds quoting (HR-90)
Text `H-FF[f]`: handle `H`, `FF` = 32nds 00 to 31, optional `f` in eighths of a 32nd: `''`=0, `1`=1/8, `2`=1/4, `+`=1/2, `5`=5/8, `6`=3/4, `7`=7/8. Value = H + (FF + f)/32. Formatting takes a `resolution` (32, 64, 128 or 256 parts per point); a price not exactly on that grid is `E_DOMAIN`; a half is printed `+`.

### 3.2 Futures contract specs (HR-91)
`contract`: `{symbol, face, tick, tick_value, months, last_trade_rule}`. Defaults: ZN face 100,000, tick 1/64 point, tick value 15.625 [CME-ZN]; ZB tick 1/32, tick value 31.25 [CME-ZB]. Tick value = face x tick / 100.

### 3.3 Yield and price (HR-92)
Coupon bond on a coupon date, street convention: P = sum_{i=1..n} (100 c/f)/(1+y/f)^i + 100/(1+y/f)^n. Off coupon dates the existing `04-pricing` bond routines are reused (no new maths). Bill: P = 100 (1 - d days/360) [UST-BILL]. Yield from price: existing `core.solve` Brent, tolerance 1e-12.

## How each plugs into existing modules
| Module | Change |
|---|---|
| `exec.sim.lit.run` (`lit-matching.md`) | optional `asset` block `{class, tick_table or pip or contract, session, fee_schedule}`; prices mapped to integer ticks at the edge; matching unchanged; auction phases call `exec.sim.auction.uncross` |
| dark pool | equities only (midpoint of the lit NBBO); FX and rates `E_UNSUPPORTED_OPERATION` (HR-93) |
| SOR | venues gain `asset_class`; an order routed across classes is `E_INPUT`; FX RFQ venue is a venue of class FX |
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
| fxc_h-0001 | pip value EURUSD notional 1,000,000 | 100 USD | 1e6 x 0.0001 |
| fxc_h-0002 | pip value USDJPY notional 1,000,000 | 10000 JPY | 1e6 x 0.01 |
| fxc_h-0003 | spot EURUSD, trade Mon 2026-11-16, no holidays | 2026-11-18 | T+2 |
| fxc_h-0004 | spot EURUSD, trade Tue 2026-11-24, USD holiday 2026-11-26 | 2026-11-27 | T+2 is a USD holiday, roll to Fri |
| fxc_h-0005 | spot EURUSD, trade Fri 2026-11-20, no holidays | 2026-11-24 | Mon, Tue |
| fxc_h-0006 | spot USDCAD, trade Fri 2026-11-20, no holidays | 2026-11-23 | T+1 pair |
| fxc_h-0007 | pair USDEUR | E_INPUT | EUR ranks before USD |
| rtc_h-0001 | parse 99-16 | 99.5 | 99 + 16/32 |
| rtc_h-0002 | parse 99-16+ | 99.515625 | 99 + 16.5/32 |
| rtc_h-0003 | parse 99-162 | 99.5078125 | 99 + 16.25/32 |
| rtc_h-0004 | parse 99-167 | 99.52734375 | 99 + 16.875/32 |
| rtc_h-0005 | format 101.296875, resolution 64 | 101-09+ | 0.296875 x 32 = 9.5 |
| rtc_h-0006 | format 101.3, resolution 128 | E_DOMAIN | 9.6/32 not on 1/128 grid |
| rtc_h-0007 | tick value, face 100,000, tick 1/64 | 15.625 | 100000 x 0.015625 / 100 |
| rtc_h-0008 | price, 1 y bond, 4 % semiannual, yield 5 %, on coupon date | 99.036287924 (9 dp) | 2/1.025 + 102/1.025^2 |
| rtc_h-0009 | price, 2 y bond, 4 % semiannual, yield 4 %, on coupon date | 100 | coupon equals yield |
| rtc_h-0010 | bill, discount 5 %, 91 days | 98.736111111 (9 dp) | 100 (1 - 0.05 x 91/360) |

## Acceptance (fixed before any run, HR-95)
- A1 all goldens here and in `auction.md`, `fx-rfq-venue.md`, `rates-futures-venue.md` pass in all four languages with byte-identical outputs.
- A2 the blind lane (DR-H2) re-derives at least 60 % of value cases; every mismatch explained before release.
- A3 property tests: rounding never makes an order more aggressive; parse(format(x)) = x on the 1/256 grid; spot date is a good day and at least T+1; auction volume is maximal over the candidate grid.
- A4 every output carries its label (HR-94).
- A5 no source still tagged unverified at release (HR-98).
