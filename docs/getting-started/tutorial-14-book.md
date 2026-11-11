# Tutorial 14: the trading book

The plain idea: before any risk number means anything, the book has to be right. You need to know what you hold, at what average cost, and what you have already made or lost. Trades change positions. An option that expires, or a bond whose issuer defaults, closes the position at a settlement or recovery price. Index fixings are recorded for later coupons. At the end of the day every position needs a price (a *mark*), and an independent price check flags marks that look wrong. Finally, the daily *P&L explain* control asks whether the risk numbers predicted the day's P&L.

This tutorial runs the three operations that do this: `book.lifecycle.apply`, `book.marks.resolve` and `risk.pnl.explain`. All data is synthetic: the trades, vendor quotes and curves are made up, and the inputs are taken from golden cases `book_f-0001`, `book_f-0004` to `-0006`, `book_f-0024` and `pnl_r2-0001`. Budget 10 to 15 minutes.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [tutorial 1](tutorial-1-swap.md).
- Tutorial 1 helps for the P&L explain part: it builds the same kind of SOFR curve.

## Step 1: Python

```bash
uv sync --locked --project python
```

Save the next block as `book.py`:

<!-- tutorial:run python -->
```python
from datetime import date

from quantforge_core import book, risk_curve
from quantforge_core.book import Event, Source
from quantforge_core.ois import OisTrade, Quote
from quantforge_core.risk_curve import Product

# 1. Lifecycle: an opening book, then a week of events (synthetic, not market data).
opening = [("SPX-C-6000", 5.0, 42.0), ("BOND-X", 1000.0, 0.97)]
events = [
    Event(date(2026, 11, 2), "TRADE", "UST10", 100.0, 99.5),
    Event(date(2026, 11, 2), "FIXING", index="SOFR", value=0.0431),
    Event(date(2026, 11, 3), "TRADE", "UST10", 50.0, 100.25),
    Event(date(2026, 11, 4), "TRADE", "UST10", -120.0, 100.5),
    Event(date(2026, 11, 20), "DEFAULT", "BOND-X", price=0.38),
    Event(date(2026, 12, 18), "EXPIRY", "SPX-C-6000", price=57.25),
]
after = book.lifecycle_apply(opening, events)
for p in after["positions"]:
    print(f"hold {p['instrument']} {p['quantity']:.0f} @ {p['average_cost']:.4f}")
for r in after["realized_pnl"]:
    print(f"realised {r['instrument']:<10} {r['pnl']:10.2f}")
print(f"realised total {after['total_realized']:.2f}, fixings kept {len(after['fixings'])}")

# 2. End-of-day marks: two vendors in priority order, a 3-day stale limit, an IPV check at 0.5%.
sources = [
    Source("VENDOR_A", (("UST10", date(2026, 11, 10), 99.75), ("SPX", date(2026, 11, 7), 6012.5))),
    Source("VENDOR_B", (("BUND10", date(2026, 11, 10), 131.2), ("UST10", date(2026, 11, 10), 99.8),
                        ("SPX", date(2026, 11, 9), 6020.0), ("ILLIQ", date(2026, 11, 1), 88.0))),
]
ipv = [("UST10", 99.7), ("BUND10", 130.0)]
marks = book.marks_resolve(date(2026, 11, 10), ["UST10", "BUND10", "SPX", "ILLIQ"], sources, 3, ipv, 0.005)
for m in marks["marks"]:
    price = "-" if m["price"] is None else f"{m['price']:.2f} from {m['source']}"
    diff = "-" if m["ipv_diff"] is None else f"{m['ipv_diff']:+.6f}"
    print(f"mark {m['instrument']:<6} {m['status']:<8} {price:<20} ipv {diff} breach {m['ipv_breach']}")

# 3. P&L explain: receive 3.45% on a 2Y SOFR swap, the whole curve up 1bp.
tenors = ["1W", "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]
rates = [0.0387, 0.0386, 0.0383, 0.0377, 0.0365, 0.035, 0.0345, 0.035, 0.036, 0.0375, 0.039, 0.0395, 0.0385]
start = [Quote(t, r) for t, r in zip(tenors, rates)]
end = [Quote(t, r + 0.0001) for t, r in zip(tenors, rates)]
swap = Product("OIS", trade=OisTrade("SOFR", "2Y", 0.0345, 25_000_000.0, "RECEIVE"))
x = risk_curve.pnl_explain(date(2026, 11, 6), "SOFR", "LOG_LINEAR_DF", start, end, swap, 1.0)
print(f"full P&L    {x['full_pnl']:.2f}")
print(f"risk P&L    {x['risk_pnl']:.2f}")
print(f"unexplained {x['unexplained']:.2f} (threshold {x['threshold']:.2f}) explained {x['explained']}")
```

```bash
uv run --project python python book.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
hold UST10 30 @ 99.7500
realised BOND-X        -590.00
realised SPX-C-6000      76.25
realised UST10           90.00
realised total -423.75, fixings kept 1
mark UST10  PRIMARY  99.75 from VENDOR_A  ipv +0.000502 breach False
mark BUND10 FALLBACK 131.20 from VENDOR_B ipv +0.009231 breach True
mark SPX    STALE    6020.00 from VENDOR_B ipv - breach False
mark ILLIQ  MISSING  -                    ipv - breach False
full P&L    -4806.23
risk P&L    -4806.94
unexplained 0.71 (threshold 240.72) explained True
```

### Reading the numbers

**Lifecycle.** The cost rule is *weighted average cost*: buying adds to the position at a blended price, and selling realises the difference between the sale price and that average.

- **UST10.** Buy 100 at 99.50 and 50 at 100.25: the average is (100 × 99.50 + 50 × 100.25) / 150 = 14,962.50 / 150 = 99.75. Selling 120 at 100.50 realises 120 × (100.50 − 99.75) = 90.00. The 30 left keep the average cost of 99.75; a reducing trade never changes it.
- **SPX-C-6000.** Five calls bought at 42.00 expire with a settlement price of 57.25. Expiry is a trade of minus the position at that price: 5 × (57.25 − 42.00) = 76.25. There is no contract multiplier; the price is per unit held.
- **BOND-X.** 1,000 units at 0.97 default with recovery 0.38: 1,000 × (0.38 − 0.97) = −590.00.
- **Total.** 90.00 + 76.25 − 590.00 = −423.75. The SOFR fixing is stored (one row in `fixings`) and touches no position. Expired and defaulted instruments leave the book, so only UST10 remains.

**Marks.** Two vendors in priority order, VENDOR_A first; a quote may be at most 3 calendar days old; the independent price verification (*IPV*) threshold is 0.5%.

- **UST10** has a VENDOR_A quote dated 2026-11-10, the as-of date, so it is `PRIMARY`. IPV difference: (99.75 − 99.70) / 99.70 = 0.000502, below 0.005.
- **BUND10** has no VENDOR_A quote, but VENDOR_B has one dated today, so it is `FALLBACK`. Its IPV difference (131.20 − 130.00) / 130.00 = 0.009231 is above 0.005, so it breaches: someone should look at this mark before it feeds risk.
- **SPX** has no quote dated today. The most recent within 3 days is VENDOR_B's 6,020.00 from 2026-11-09 (1 day old), which beats VENDOR_A's quote of 2026-11-07, so it is `STALE`.
- **ILLIQ** has only a quote from 2026-11-01, 9 days old, so it is `MISSING`: no price rather than an old one.

**P&L explain.** You receive 3.45% fixed on a 2-year SOFR swap of 25 million, and every one of the 13 curve quotes rises 1 bp.

- **Full P&L** −4,806.23 is the swap repriced on the new curve minus the swap on the old one. A receiver loses when rates rise. Head check: 25,000,000 × 0.0001 × an annuity a little under 2 years ≈ 4,800, the right size.
- **Risk P&L** −4,806.94 is each bucket's par-quote risk times its quote move, summed. The 2Y bucket carries almost all of it.
- **Unexplained** −4,806.23 − (−4,806.94) = 0.71. The threshold is 5% of the larger of |full P&L| and the gross risk P&L (every bucket term counted in absolute value), plus a numerical floor of 1e-8 × 25,000,000 = 0.25. With both P&Ls near 4,807 that is about 0.05 × 4,809 + 0.25 ≈ 240.7, matching the 240.72 printed. 0.71 is far inside, so the day is explained. The small gap is the second-order (convexity) term that a first-order risk number cannot see.

## The formal statement, checked against the spec

The lifecycle and marks rules are in `specifications/07-portfolio/book-lifecycle.md`; P&L explain is `specifications/06-risk/pnl-explain.md`.

**Cost rule** (ruling F-34). For a position `q` at average cost `a` and a trade `dq` at price `p`: if `q = 0` or `dq` has the same sign as `q`, then `q' = q + dq` and `a' = (q a + dq p) / q'`. Otherwise the closed quantity is `c = min(|dq|, |q|)` and realised P&L grows by `sign(q) c (p − a)`; the average is unchanged unless the position crosses zero, in which case the remainder opens at `p`. `EXPIRY` and `DEFAULT` are a trade of `−q` at the settlement or recovery price. Events must come in non-decreasing date order; an expiry or default of an instrument not held, or a trade into a closed instrument, is `E_INPUT`. Quantities and prices are in the caller's units; the operation knows no currency or multiplier.

**Mark rule.** For each instrument: the first source in priority order with a quote dated `as_of` (`PRIMARY` if that is the first source, else `FALLBACK`, age 0); otherwise the most recent quote at most `max_age_days` calendar days old, from any source (`STALE`; the earlier source wins a tie on date); otherwise `MISSING`. A quote dated after `as_of` is never used. With an IPV price, `ipv_diff = (mark − ipv) / ipv` and `ipv_breach = |ipv_diff| > ipv_threshold`.

**P&L explain.** Both curves are bootstrapped on the same `as_of` (2026-11-06) with SOFR conventions and log-linear discount-factor interpolation, so no time passes: there is no carry, roll-down or theta in this number. `full_pnl = value_end − value_start`; `risk_pnl = Σ_j par_buckets[j] (q_end[j] − q_start[j]) / 0.0001`, with `par_buckets` the central 1 bp par risk at the start curve; `threshold = 0.05 max(|full_pnl|, gross_risk_pnl) + 1e-8 N`; `explained` is `|unexplained| ≤ threshold`. The 5% level is a project choice (ruling R2-A4), not a Basel rule.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_book.py` sends the three operations to whichever CLI you name and prints the same lines. It uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_book.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_book.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_book.py cpp26/build/quantforge
```

Each prints the lines shown in step 1, digit for digit. The lifecycle and marks rules are exact arithmetic; the P&L figures are printed to the cent, far coarser than the tolerance of the curve solves (`conformance/tolerances`).

## For practitioners

- **Average cost, not FIFO.** Many tax and accounting ledgers use first-in-first-out lots. This book uses weighted average cost, so realised P&L on a partial sale can differ from a FIFO ledger, and there is no lot history to reconcile against.
- **Trade-date book, one currency.** Settlement-date accounting, corporate actions and multi-currency cash are deferred (spec, "Acceptance"). Realised P&L here is not a cash balance.
- **Default at one recovery price.** In practice the final price may come from a credit-event auction or a later sale; here the caller supplies one recovery price and the position closes.
- **Marks and IPV.** The ladder primary, fallback, stale, missing is a simplified price hierarchy. Desk IPV usually uses tolerance bands per asset class and looks at bid-ask, not one relative threshold.
- **P&L explain is not the FRTB attribution test.** Basel's P&L attribution test compares risk-theoretical and hypothetical P&L over 250 days with Spearman and Kolmogorov-Smirnov statistics. This control is a one-day check with a 5% threshold; `tools/workflows/pnl_explain.py` reports the two statistics over real moves, unjudged.

## Common mistakes

- **Unsorted events.** Events out of date order are `E_INPUT`; they are not reordered for you.
- **Closing something not held.** An `EXPIRY` or `DEFAULT` for an instrument with no open position is `E_INPUT` (`book_f-0020`), and so is a trade after expiry (`book_f-0019`).
- **Expecting a reducing trade to move the average.** It does not; only adds and a reversal through zero change `average_cost`.
- **Treating `STALE` as good.** A stale mark is a price, but an old one; the status is there so reports can show it.
- **Different tenors in the two quote sets.** `quotes_start` and `quotes_end` must have the same tenors in the same order.

## What you just did

You replayed a week of trades and lifecycle events into positions and realised P&L by the average-cost rule, chose end-of-day marks from a priority list of sources with a staleness limit and an IPV check, and ran the daily P&L explain control on a swap. Four implementations agree on every line.

## Try next

- Add a `ROLL` event (`from`, `to`, `from_price`, `to_price`) to roll UST10 into another contract; `book_f` has examples.
- Raise `max_age_days` to 10: ILLIQ turns from `MISSING` to `STALE`.
- Make the move larger: `pnl_r2-0011` pays fixed on a 10Y swap with every quote up 150 bp, and the control fails because convexity exceeds the threshold.
- Read [LEARN: the book, and where returns came from](../../LEARN.md#the-book-and-where-returns-came-from) and [LEARN: P&L explain](../../LEARN.md#pl-explain).

## References and further reading

- Specs: `specifications/07-portfolio/book-lifecycle.md` (rulings F-34, F-39) and `specifications/06-risk/pnl-explain.md` (rulings R2-A3, R2-A4).
- Weighted average cost against FIFO: CFA Institute, *CFA Program Curriculum*, Level I, "Inventories", 2024 edition, as cited by the spec, which marks it "not opened". No outside oracle exists for the book rules; they are this project's own conventions, and `book_f` does not count toward the outside-oracle floor.
- P&L explain goldens are re-priced in QuantLib 1.44 (values and par buckets, as `specifications/06-risk/par-and-key-rate.md`).
- The Basel P&L attribution test the spec contrasts with: Basel Committee, *The Basel Framework*, [MAR32](https://www.bis.org/basel_framework/chapter/MAR/32.htm) (free).
- [COOKBOOK: P&L explain](../../COOKBOOK.md#pl-explain-riskpnlexplain) and [COOKBOOK: stage F recipes](../../COOKBOOK.md#stage-f-recipes).
- [GLOSSARY: stage A terms](../../GLOSSARY.md#stage-a-foundation) (P&L explain, par risk) and [stage F terms](../../GLOSSARY.md#stage-f-terms).

Links checked 2026-11-11.
