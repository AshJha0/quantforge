# Paper trading with simulated fills

Spec version 0.1.0 (stage H item H-21, moved from stage K by the owner 2026-11-18). Status: Specified; ledger, book (positions, cash, financing, P&L explain) and pre-trade checks implemented in Python (`quantforge_core/paper.py`); fills from the lit, dark and SOR simulators, per-order TCA records and the session close implemented in Python (`quantforge_core/paper_fills.py`, A7). Rulings HR-42 to HR-55 (proposed, `stage-h-rulings-h21.md`). Plan items: section 2 owner decision "proper paper trading", 12.7 Q8k (TCA and the fill simulator wired into paper trading; the ledger carries TCA per order). The public dashboard stays in stage K and is out of scope here.

**Every output is labelled "crypto venue; simulated"** (HR-43), and every report also carries the 11.6 honest-ceiling sentence: "Paper trading on free data; simulated fills; no evidence of tradable profitability." **No live order is ever placed**: there is no code path to any venue's order entry, and a request with `mode` other than `"simulated"` is `E_UNSUPPORTED_OPERATION` (HR-42).

**Plain idea.** A paper book behaves like a real trading book except that nothing leaves the machine. An order passes the same pre-trade checks a desk would apply, is filled by the simulated venues of this folder against the recorded crypto book, and every order, rejection and fill is written to a ledger that cannot be edited without the change showing. Each day the book is marked to the recorded close, financing is accrued, and the day's P&L is split into parts that add up exactly.

## Sources
- [Per88] as in `tca.md` (implementation shortfall; recalled, not read).
- [FIX-ER] FIX Trading Community, FIX 4.4 ExecutionReport (35=8) fields OrdStatus, CumQty, LeavesQty, AvgPx; recalled from the public FIX specification, not re-read 2026-11-18. Evidence class: standard, recalled. Used only for the order-state vocabulary (NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED).
- [SHA] NIST FIPS 180-4, SHA-256. Standard, recalled; checked by the outside tool `sha256sum` (GNU coreutils) on the stated bytes for pt_h-0020.
- [RFC8785] JSON Canonicalization Scheme. Recalled. The canonical form here is a stated subset (HR-45), not a claim of RFC 8785 conformance.
- No source is claimed for the risk limits; they are the conventional desk set (size, notional, position, price collar, cash, order count, kill switch), chosen by ruling HR-49.

Evidence for goldens: hand calculation in exact decimal (shown in each row), plus `sha256sum` for hashes. All value cases are written so that a later blind lane (DR-H2) can recompute them from the inputs alone.

## Model

### Numbers
Prices, quantities, cash and rates are decimal strings in inputs, outputs and the ledger (HR-44); arithmetic is exact decimal. Cash postings from financing are rounded to the cash precision (2 decimal places for USD) half-even when posted; fill cash is exact (quantity x price + fee, no rounding). Floats never enter the ledger.

### Rulings HR-77 and HR-78 (proposed 2026-11-18, from the Java port; numbers to be confirmed by the coordinator)

| Ruling | Rule |
|---|---|
| HR-77 | **Exact decimals and range.** Every input decimal is in the HR-57 input range (36 digits, at most 18 decimals), and every computed value (notional q x p, each cash flow and the cash balance, fees, cost basis, position, realised, market value, NAV, each explain term, the financing products before division, q x p_chk) is in the HR-57 range (36 digits, 36 decimals); outside either is **`E_LIMIT`** (HR-58), checked after `E_SCHEMA`, never a rounded value. Inside the range sums, differences and products are exact in every build (Python in the 200-digit context, as HR-58). There are exactly three divisions, each with a stated rounding: the average cost c = (\|n\| c + q p) / (\|n\| + q), rounded half-even to 18 decimals; cash interest and short borrow, the exact product divided by 365 and rounded half-even to 0.01; the mid (bid + ask) / 2, exact. The price-band check is cross-multiplied, \|limit - P_ref\| > band x P_ref, so no division. TCA values stay binary64 (cli-contract.md). Goldens pt_h-0050 (31-digit cash, wrong under a 28-digit context), 0051 (5/3 to 18 decimals), 0052 and 0053 (`E_LIMIT`). |
| HR-78 | **Duplicate keys.** A ledger line whose JSON repeats a key at any level is `PARSE` in `paper.ledger.verify`, even when the values agree: a last-wins parser would let an edited copy of a field pass the hash check. Golden pt_h-0054. |

### Orders and fills
An order: `order_id`, `symbol`, `side` (BUY, SELL), `type` (LIMIT, MARKET, IOC, plus the lit types of HR-25 passed through), `quantity` (> 0), `limit_price` (required unless MARKET), `venue` (`LIT`, `DARK`, `SOR`). States as [FIX-ER].

Fill source (HR-47, `paper_fills.py`): the order is replayed into `lit-matching.md`, `dark-pool.md` or `smart-order-router.md`, seeded with the recorded book snapshot at the order time (forward-log per-second 100-level snapshots, form B of HR-11). Spread and slippage come from walking that book; partial fills come from the venue (IOC remainder cancelled; resting remainder cancelled at the daily close, HR-48). The simulated book does not remember our own past fills (no permanent impact on the recorded data) and this is stated as a limitation. Fees are the venue simulator's signed fees (HR-30).

### Positions and cash (`paper.book.apply_fill`)
Per symbol, signed position `n` and average cost `c` (HR-50, average-cost method). For a fill of side s (+1 BUY, -1 SELL), quantity q, price p, fee f (fee >= 0 charged, < 0 rebate):
- cash -= s q p + f.
- If the fill increases |n| or n = 0: c := (|n| c + q p) / (|n| + q), n += s q.
- If it reduces: realised += min(q, |n|) x (p - c) x sign(n); if it crosses zero, the remainder opens at c = p.
- Fees are not in c and not in realised; they are reported separately.

### Daily mark and financing (`paper.book.end_of_day`)
Close price P_t per symbol: the mid of the recorded snapshot at 00:00:00 UTC (HR-51). Accrual days d = calendar days between marks (ACT/365, HR-52).
- Cash interest = cash_open x r x d / 365, with r = `cash_rate` if cash_open >= 0 else `debit_rate`; rounded half-even to 0.01.
- Short borrow = - sum over short positions |n_open| x P_{t-1} x `borrow_rate` x d / 365, rounded the same way.
- Financing is posted to cash at the end of the day, on opening balances only (HR-52).

### Daily P&L explain (`paper.pnl.explain`)
For each day, with n_open, P_{t-1} the opening state and fills during the day:
- `market` = sum n_open (P_t - P_{t-1})
- `trading` = sum over fills s q (P_t - p)
- `fees` = - sum f
- `financing` = cash interest + short borrow
- `total` = market + trading + fees + financing

Identity (HR-53): `total` = NAV_t - NAV_{t-1} exactly, with NAV = cash + sum n P. A residual other than exactly zero is a defect, not a reported term. On the first day n_open = 0 and P_{t-1} is not needed.

### Pre-trade checks (`paper.pretrade.check`)
Inputs: the order, the reference price P_ref (current recorded mid), current position, current cash, orders already sent today, and `limits`: `max_order_qty`, `max_notional`, `max_abs_position`, `price_band` (fraction), `max_orders_per_day`, `kill_switch`, `allow_short` (HR-49). Check price p_chk = limit price, or for MARKET P_ref x (1 + s x price_band).
Checks, all evaluated, failures reported in this fixed order (HR-49):
1. `KILL_SWITCH`: kill_switch is true.
2. `MAX_ORDERS`: orders today >= max_orders_per_day.
3. `MAX_QTY`: quantity > max_order_qty.
4. `PRICE_BAND`: |limit_price - P_ref| / P_ref > price_band (limit orders only).
5. `MAX_NOTIONAL`: quantity x p_chk > max_notional.
6. `MAX_POSITION`: |n + s q| > max_abs_position.
7. `NO_SHORT`: allow_short is false and n + s q < 0.
8. `INSUFFICIENT_CASH`: BUY and quantity x p_chk > cash.
Result `{accepted, reasons}`. A rejection is a ledger record of kind `REJECT`, not an error. `mode` not `"simulated"`: `E_UNSUPPORTED_OPERATION`. Quantity <= 0 or a price <= 0: `E_DOMAIN`. Unknown side or type: `E_INPUT`.

The checks are deterministic code; no agent or model sits in front of them (12.8: no orders without the deterministic risk gate).

### Ledger (`paper.ledger.append`, `paper.ledger.verify`)
Append-only JSON Lines, one record per line, in the `forward-log` branch (HR-46). Record fields: `seq` (integer from 0), `ts` (UTC, ISO 8601, `Z`), `kind` (`ORDER`, `REJECT`, `FILL`, `CANCEL`, `EOD`, `TCA`), `label` (`"crypto venue; simulated"`), `body` (object, decimal strings), `prev` (hex hash of the previous record; 64 zeros for seq 0), `hash`.

Canonical bytes (HR-45): the record without `hash`, JSON with keys sorted by code point at every level, separators `,` and `:` with no whitespace, ASCII only (non-ASCII escaped `\uXXXX`), integers only for `seq`, every other number a string. `hash` = lowercase hex SHA-256 of those bytes.

`verify` re-reads the file and returns `{ok, records, first_bad_seq, reason}`; reasons `HASH` (stored hash differs), `LINK` (prev differs from the previous hash), `SEQ` (gap or repeat), `LABEL` (missing or wrong label), `PARSE` (including a repeated key, HR-78). It never repairs.

### TCA per order
When an order reaches a final state, a `TCA` record carries `exec.tca.shortfall` (`tca.md`) with decision price = P_ref at the pre-trade check, arrival price = mid at venue entry, end price = close P_t, the order's fills and fees.

## Errors
`E_UNSUPPORTED_OPERATION` live mode; `E_DOMAIN` non-positive quantity or price; `E_INPUT` unknown side/type/kind, a fill for an unknown order, a fill over the order quantity; `E_SCHEMA` missing field, a JSON number where a decimal string is expected, or a non-finite token ("NaN", "Infinity", "-Infinity") in a decimal string (HR-12, ruling F-2a).

## Acceptance tests (fixed before any run, HR-55)
- A1 Ledger: every golden pt_h-0020..0023 passes; appending 10,000 random records and flipping any one byte in any line makes `verify` fail at that seq or earlier; truncating the last line leaves a valid shorter chain (detected only by the published head hash, HR-46).
- A2 Book: goldens pt_h-0001..0005; property: for random fill sequences, cash + sum n c + realised - fees reconciles to initial cash exactly.
- A3 Explain: property over random days: `total` = NAV_t - NAV_{t-1} exactly (Decimal, no tolerance).
- A4 Pre-trade: goldens pt_h-0010..0018; property: an order accepted never makes |n| exceed max_abs_position when fully filled.
- A5 No live path: a static test that no module under `quantforge_core/paper*` imports a network library or names an order-entry endpoint; mode `"live"` raises.
- A6 Labels: every ledger record and report has the label; `verify` fails on a record without it.
- A7 fills: lit, dark and SOR goldens of their own specs reproduced through the paper path, and every final order has one `TCA` record whose components sum to total to 1e-10 (tca.md).
- A8 Determinism: the same order list and recorded snapshots give a byte-identical ledger.

## Golden cases
Common: symbol BTC-USD, USD cash precision 0.01.

| Case | Input | Expected | Derivation |
|---|---|---|---|
| pt_h-0001 | cash 10000; BUY 2 @ 100 fee 0.20; SELL 1 @ 110 fee 0.11 | cash 9909.69, n 1, c 100, realised 10, fees 0.31 | 10000 - 200 - 0.20 + 110 - 0.11; 1 x (110 - 100) |
| pt_h-0002 | pt_h-0001 then close P = 105, first day | market 0, trading 15, fees -0.31, financing 0, total 14.69; NAV 10014.69 | 2 x (105 - 100) + (-1)(105 - 110); 9909.69 + 105 - 10000 |
| pt_h-0003 | day 2 from pt_h-0002: no fills, close 102, d 1, cash_rate 0.0365 | financing 0.99, market -3, total -2.01, cash 9910.68, NAV 10012.68 | 9909.69 x 0.0365 / 365 = 0.990969 -> 0.99; 1 x (102 - 105) |
| pt_h-0004 | n_open -2, P_prev 50, close 50, cash 10100, cash_rate 0.0365, borrow_rate 0.0730, d 1 | interest 1.01, borrow -0.02, financing 0.99 | 10100 x 0.0001; 2 x 50 x 0.0002 |
| pt_h-0005 | n 1, c 100; SELL 3 @ 90 fee 0 | n -2, c 90, realised -10 | crosses zero: 1 x (90 - 100); remainder 2 opens at 90 |
| pt_h-0006 | cash -1000, n 0, debit_rate 0.0730, d 3 | financing -0.60 | -1000 x 0.073 x 3 / 365 |
| pt_h-0010 | limits L*; BUY LIMIT 3 @ 101, P_ref 100, n 0, cash 10000, today 0 | accepted, reasons [] | 303 <= 1000; |n| 3 <= 5; band 0.01 |
| pt_h-0011 | L*; BUY LIMIT 11 @ 100 | [MAX_QTY, MAX_NOTIONAL, MAX_POSITION] | 11 > 10; 1100 > 1000; 11 > 5 |
| pt_h-0012 | L*; BUY LIMIT 3 @ 106 | [PRICE_BAND] | 6 / 100 = 0.06 > 0.05 |
| pt_h-0013 | L*; SELL LIMIT 10 @ 100, n 4 | [MAX_POSITION] | 4 - 10 = -6 |
| pt_h-0014 | L*; BUY MARKET 3, cash 300 | [INSUFFICIENT_CASH] | p_chk = 105; 315 > 300 |
| pt_h-0015 | L*; today 3 | [MAX_ORDERS] | 3 >= 3 |
| pt_h-0016 | L* with kill_switch true; otherwise pt_h-0010 | [KILL_SWITCH] | |
| pt_h-0017 | L* with allow_short false; SELL LIMIT 2 @ 100, n 1 | [NO_SHORT] | 1 - 2 = -1 |
| pt_h-0018 | pt_h-0010 with mode "live" | `E_UNSUPPORTED_OPERATION` | HR-42 |
| pt_h-0020 | record seq 0, ts 2026-11-18T00:00:01Z, kind ORDER, body {order_id O1, symbol BTC-USD, side BUY, type LIMIT, quantity "3", limit_price "101"}, prev 64 zeros | canonical bytes `{"body":{"limit_price":"101","order_id":"O1","quantity":"3","side":"BUY","symbol":"BTC-USD","type":"LIMIT"},"kind":"ORDER","label":"crypto venue; simulated","prev":"0000000000000000000000000000000000000000000000000000000000000000","seq":0,"ts":"2026-11-18T00:00:01Z"}`; hash `72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81` | `sha256sum` of those bytes (outside tool) |
| pt_h-0021 | pt_h-0020 with `limit_price` changed to "102" after writing | verify: ok false, first_bad_seq 0, reason HASH | |
| pt_h-0022 | two records, the second with `prev` of 64 zeros | ok false, first_bad_seq 1, reason LINK | |
| pt_h-0023 | pt_h-0020 with label removed (hash recomputed) | ok false, first_bad_seq 0, reason LABEL | HR-43 |

Golden output shapes (added 2026-11-18 as a fix after blind lane 2b, which had to invent them; no value changed). Canonical JSON, decimal strings with no exponent and no trailing zeros (HR-12, HR-44), so "-0.60" in pt_h-0006 is written "-0.6":
- Book cases 0001, 0005: `{"position", "avg_cost", "realised", "fees", "cash"}`; 0005 has no starting cash and gives `cash_delta` instead of `cash`.
- Day cases 0002 to 0004, 0006: `{"market", "trading", "fees", "financing", "cash_interest", "short_borrow", "total", "position", "cash_close", "nav_open", "nav_close"}` (`nav_open` and `nav_close` omitted in 0006, where no price is given).
- Pre-trade 0010 to 0017: `{"accepted", "reasons"}` with reasons in check order; 0018: `{"error": "E_UNSUPPORTED_OPERATION"}`.
- Ledger 0020: `{"canonical_bytes", "hash", "record"}`; 0021 to 0023: `{"verify": {"ok", "first_bad_seq", "reason", "records"}}`.

CLI form (2026-11-18, cross-language lane; shapes only, no value changed): the operations, inputs and byte-exact hash rule are in `cli-contract.md`, "Stage H paper trading operations". Every output also carries `label` (HR-43). `paper.ledger.verify` returns the verify object itself (not wrapped in `verify`) plus `head`; `records` is the number of records that verified before the first bad one, so 0021 and 0023 give 0 and 0022 gives 1 (the blind lane counted all lines; the spec stated no value). pt_h-0018 is pinned by unit tests, not by the golden file, because the runner reads `E_UNSUPPORTED_OPERATION` as "not implemented". Further hand cases in the golden file, not blind: pt_h-0030 and 0031 (`paper.session.run`, one LIT order filled over two levels and one rejected, then the close with TCA and EOD; hashes recomputed with `hashlib` from the canonical bytes), pt_h-0040 to 0047 (errors), and `e1_hpt` (a non-finite token in a decimal string is `E_SCHEMA`, HR-12 and F-2a). Blind status after a field-by-field comparison (`program/stage_h_blind_w2/pt_compare.py`, mapping fixed before comparing): 0001 to 0006 and 0010 to 0017 MATCH; 0020, 0021, 0022 and 0023 not counted (shape or `records` differences; 0021 to 0023 also not blind).

L* = max_order_qty 10, max_notional 1000, max_abs_position 5, price_band 0.05, max_orders_per_day 3, kill_switch false, allow_short true.

## Limitations
- Fills are simulated against recorded books that do not react to our orders; queue position for resting orders is the venue simulator's assumption, not observed.
- Per-second snapshots (form B) miss intra-second moves; slippage is understated for fast markets.
- Average cost only; FIFO lot accounting is not offered (HR-50).
- Financing rates are inputs, not quoted rates of any venue or broker.
- On free data paper results are never evidence of tradable profitability (11.6).
