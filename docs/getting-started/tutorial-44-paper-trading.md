# Tutorial 44: paper trading end to end, from pre-trade check to a hashed ledger

<!-- tutorial:only python -->

The plain idea: a paper book behaves like a real trading book except that nothing leaves the machine. Each order passes the same checks a desk would apply, is filled by a simulated venue, and is written to a ledger in which any later edit shows. At the end of each day the book is marked to a closing price, financing is accrued, and the day's profit and loss is split into parts that add up exactly.

You will book two fills, explain two days of P&L, reject an order that breaks three limits, write one ledger record and catch a tampered copy of it. Budget 15 minutes.

<p class="note">Available from v0.10.0 (unreleased). The ledger, book, daily explain and pre-trade checks are implemented in Python (<code>python/quantforge_core/paper.py</code>), and this page runs them. They are also CLI operations (<code>paper.*</code> in the name map, goldens <code>pt_h</code>), implemented in all four languages. Fills from the simulated lit, dark and routed venues (ruling HR-47, <code>python/quantforge_core/paper_fills.py</code>) are implemented in Python and shown, not run, in step 2. Every number below is a golden from <code>specifications/10-execution/paper-trading.md</code>. Every output is labelled "crypto venue; simulated"; no live order can be placed.</p>

Terms, defined here. `n` is the signed position and `c` its average cost. **NAV** is cash plus the position marked at the close, `cash + sum n P`. The daily **explain** splits the NAV change into `market` (the opening position times the price move), `trading` (each fill against the close), `fees` and `financing` (interest on opening cash, and a borrow charge on opening shorts, ACT/365). `L*` is the spec's limit set: at most 10 per order, notional 1,000, absolute position 5, price band 5 %, three orders a day.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.

## Step 1: a book, two days, a rejection and a ledger

<!-- tutorial:run python -->
```python
# A paper book, a day's P&L explain, a pre-trade check and the ledger, goldens pt_h-0001, 0002, 0003, 0011, 0020, 0021.
from decimal import Decimal

from quantforge_core import paper

book = paper.Book(Decimal("10000"))
fills = [
    {"symbol": "BTC-USD", "side": "BUY", "quantity": "2", "price": "100", "fee": "0.20"},
    {"symbol": "BTC-USD", "side": "SELL", "quantity": "1", "price": "110", "fee": "0.11"},
]
day1 = paper.end_of_day(book, fills, {}, {"BTC-USD": "105"})
pos = book.pos("BTC-USD")
print(f"pt_h-0001 cash {book.cash} position {pos.n} avg cost {pos.c} realised {book.realised} fees {book.fees}")
print(f"pt_h-0002 market {day1['market']} trading {day1['trading']} fees {day1['fees']} total {day1['total']} NAV {day1['nav']}")
day2 = paper.end_of_day(book, [], {"BTC-USD": "105"}, {"BTC-USD": "102"}, days=1, cash_rate="0.0365")
print(f"pt_h-0003 financing {day2['financing']} market {day2['market']} total {day2['total']} cash {book.cash} NAV {day2['nav']}")
print("label:", day2["label"])

limits = {"max_order_qty": "10", "max_notional": "1000", "max_abs_position": "5", "price_band": "0.05",
          "max_orders_per_day": 3, "kill_switch": False, "allow_short": True}
order = {"order_id": "O1", "symbol": "BTC-USD", "side": "BUY", "type": "LIMIT", "quantity": "11", "limit_price": "100"}
print("pt_h-0011", paper.pretrade_check(order, "100", "0", "10000", 0, limits))

ledger = paper.Ledger()
rec = ledger.append("ORDER", "2026-11-18T00:00:01Z", {"order_id": "O1", "symbol": "BTC-USD", "side": "BUY",
                                                       "type": "LIMIT", "quantity": "3", "limit_price": "101"})
print("pt_h-0020 hash", rec["hash"])
check = paper.verify(ledger.text())
print("verify:", check["ok"], check["records"])
tampered = paper.verify(ledger.text().replace('"limit_price":"101"', '"limit_price":"102"'))
print("pt_h-0021 verify:", tampered["ok"], tampered["first_bad_seq"], tampered["reason"])
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
pt_h-0001 cash 9909.69 position 1 avg cost 100 realised 10 fees 0.31
pt_h-0002 market 0 trading 15 fees -0.31 total 14.69 NAV 10014.69
pt_h-0003 financing 0.99 market -3 total -2.01 cash 9910.68 NAV 10012.68
label: crypto venue; simulated
pt_h-0011 {'accepted': False, 'reasons': ['MAX_QTY', 'MAX_NOTIONAL', 'MAX_POSITION'], 'label': 'crypto venue; simulated'}
pt_h-0020 hash 72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81
verify: True 1
pt_h-0021 verify: False 0 HASH
```

### Reading the numbers

- **The book.** Buy 2 at 100 with fee 0.20, sell 1 at 110 with fee 0.11: cash is 10000 - 200.20 + 109.89 = 9909.69, one unit is left at average cost 100, realised profit is 1 x (110 - 100) = 10, and fees are kept apart at 0.31 (`pt_h-0001`, average-cost method, HR-50).
- **Day one.** No opening position, so `market` is 0. The buy gains 2 x (105 - 100) = 10 against the close and the sell 1 x (110 - 105) = 5, so `trading` is 15; with fees the day makes 14.69, which is exactly NAV 10014.69 less the starting 10000 (`pt_h-0002`).
- **Day two.** No fills. One unit falls from 105 to 102, so `market` is -3. Interest on 9909.69 at 3.65 % for one day is 0.990969, posted as 0.99 (half-even to the cent, HR-52). Total -2.01 (`pt_h-0003`).
- **The rejection.** Eleven units at 100 break three limits at once, and all three are reported in the fixed order of HR-49 (`pt_h-0011`). A rejection is a ledger record, not an error.
- **The ledger.** The record's hash is SHA-256 of its canonical bytes, checked by the spec lane with `sha256sum`. Changing 101 to 102 after writing makes `verify` fail at record 0 with reason `HASH` (`pt_h-0021`).

### The formal statement, checked against the spec

From [`10-execution/paper-trading.md`](../../specifications/10-execution/paper-trading.md) (rulings HR-42 to HR-55).

- Explain identity (HR-53): `market + trading + fees + financing = NAV_t - NAV_{t-1}` exactly, in decimal. The code raises if the residual is anything but zero, so a residual is a defect, never a reported line.
- Ledger record: `{seq, ts, kind, label, body, prev, hash}`, keys sorted, no whitespace, ASCII only, numbers other than `seq` as strings (HR-45); `prev` links each record to the one before, so editing, removing or reordering a record breaks the chain from that point (`HASH`, `LINK` or `SEQ`).
- Pre-trade (HR-49): kill switch, orders per day, size, price band, notional, position, short sale, cash, every check evaluated, reasons in that order. The checks are plain code; no model sits in front of them.

## Step 2: where the fills come from (shown, not run here)

The fill path, `quantforge_core.paper_fills`, replays each order into the simulated venue it names, seeded with the recorded book snapshot at the order time: `LIT` goes to the lit engine of [Tutorial 42](tutorial-42-match-orders.md), `DARK` to the dark pool and `SOR` through the router of [Tutorial 43](tutorial-43-dark-pool-and-routing.md). An IOC remainder is cancelled at once; a resting remainder is cancelled at the daily close (HR-48). When an order reaches a final state, the ledger gets a `TCA` record from `exec.tca.shortfall` ([Tutorial 38](tutorial-38-implementation-shortfall.md)).

```python
from quantforge_core import paper_fills

session = paper_fills.Session("10000", limits, lit_config, dark_config)
session.submit(order, "2026-11-18T10:00:00Z", snapshot)   # ORDER or REJECT, then FILL, CANCEL, TCA records
```

Its acceptance test A7 replays every lit, dark and router golden through this single dispatch and requires the venues' own expected outputs.

## For practitioners

- **No permanent impact.** The replayed book does not remember our earlier fills, so a strategy that trades often against the same level looks cheaper than it would be. The spec states this as a limitation.
- **The ledger proves order, not truth.** A hash chain shows the file was not edited after writing; it does not show the snapshots were right. Truncating the last line leaves a valid shorter chain, which only the published head hash catches (HR-46).
- **The honest ceiling.** Every report carries: "Paper trading on free data; simulated fills; no evidence of tradable profitability."

## Common mistakes

- **Putting fees into the average cost.** Here fees are reported on their own line, so `realised` is price only.
- **Accruing on closing cash.** Financing is on opening balances (HR-52); accruing on the close double counts the day's trades.

## What you just did

You booked fills with exact decimal cash, explained two days of P&L to the cent with no residual, saw three limits reject one order, and caught a one-character edit in a hashed ledger.

## Try next

- Set `allow_short` to `False` and send a sell of 2 against a position of 1; predict the reason before you run it (`pt_h-0017`).

## References and further reading

- This project: [`paper-trading.md`](../../specifications/10-execution/paper-trading.md), [`tca.md`](../../specifications/10-execution/tca.md); all sources in [References](../references.md).
- FIX Trading Community, FIX 4.4 ExecutionReport, for the order-state names (recalled in the spec, not re-read).
