# Tutorial 49: equity, FX and rates trading conventions

<!-- tutorial:only python -->

The plain idea: before any venue or model can run, a price has to sit on the right grid, a trade has to settle on the right day, and a bond quote has to be read the way the desk writes it. These are conventions, not models: there is one right answer, fixed by a rule or by market practice, and this page runs that answer.

You will round equity prices to the tick, find a round lot and a settlement date, value a pip and find FX spot dates, read and write Treasury prices in 32nds, and price a bond and a bill. Budget 15 minutes.

<p class="note">Available from v0.10.0 (unreleased). The operations are implemented in the Python, Java and Rust builds on branch <code>stage-h4</code> (C++ to follow in the same round); this page drives the Python build in process. Convention outputs carry no label (HR-111): they are arithmetic, not venue output.</p>

Terms, defined here. A **tick** is the smallest price step. A **round lot** is the standard order size. **T+1** means settlement one good business day after the trade date. A **pip** is 0.0001 of the quote currency (0.01 for JPY pairs). The **spot date** is the normal FX value date: two good days after the trade, one for USDCAD. A **32nd** is 1/32 of a point of par; `+` adds half a 32nd, and a third digit adds quarters of a 32nd (HR-109).

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.

## Step 1: run the convention goldens

<!-- tutorial:run python -->
```python
# Equity, FX and rates conventions, goldens eqc_h, fxc_h and rtc_h.
import json

from quantforge_core.cli.main import run_case


def load(suite):
    return {c["case_id"]: c for c in json.load(open(f"datasets/golden/stage_h/{suite}.json", encoding="utf-8"))["cases"]}


cases = load("eqc_h") | load("fxc_h") | load("rtc_h")


def run(case_id):
    c = cases[case_id]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": c["operation"], "inputs": c["inputs"]}))
    assert r["outputs"] == c["expected"]["outputs"], case_id
    return r["outputs"]


for cid in ("eqc_h-0001", "eqc_h-0002", "eqc_h-0009", "eqc_h-0010"):
    i = cases[cid]["inputs"]
    print(f"{cid} {i['side']} at {i['price']} ({i.get('tick_tier', 'PENNY')}): {run(cid)['price']}")
print("eqc_h-0015 round lot at 250.01:", run("eqc_h-0015")["round_lot"])
print("eqc_h-0008 T+1 from Friday 2026-11-20:", run("eqc_h-0008")["settle_date"])
print("fxc_h-0001 pip value of 1,000,000 EURUSD:", run("fxc_h-0001"))
print("fxc_h-0005 EURUSD spot from Friday 2026-11-20:", run("fxc_h-0005")["spot_date"])
print("fxc_h-0006 USDCAD spot from Friday 2026-11-20:", run("fxc_h-0006")["spot_date"])
print("fxc_h-0004 EURUSD spot from 2026-11-24, USD holiday 11-26:", run("fxc_h-0004")["spot_date"])
for cid in ("rtc_h-0001", "rtc_h-0002", "rtc_h-0003"):
    print(f"{cid} {cases[cid]['inputs']['text']} = {run(cid)['value']}")
print("rtc_h-0005 101.296875 in 64ths:", run("rtc_h-0005")["text"])
print("rtc_h-0008 4 % two-period bond at 5 %:", run("rtc_h-0008")["price"])
c = cases["rtc_h-0012"]  # a root-finding output: compared within tolerance, not byte for byte
y = run_case(json.dumps({"schema_version": "1.0", "case_id": "rtc_h-0012", "operation": c["operation"], "inputs": c["inputs"]}))["outputs"]["yield"]
assert abs(y - c["expected"]["outputs"]["yield"]) < 1e-10
print(f"rtc_h-0012 yield back from that price: {y:.10f}")
print("rtc_h-0010 91-day bill at 5 % discount:", run("rtc_h-0010")["price"])
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
eqc_h-0001 BUY at 10.005 (PENNY): 10.00
eqc_h-0002 SELL at 10.005 (PENNY): 10.01
eqc_h-0009 BUY at 10.003 (HALF_PENNY): 10.000
eqc_h-0010 SELL at 10.003 (HALF_PENNY): 10.005
eqc_h-0015 round lot at 250.01: 40
eqc_h-0008 T+1 from Friday 2026-11-20: 2026-11-23
fxc_h-0001 pip value of 1,000,000 EURUSD: {'currency': 'USD', 'pip_value': '100'}
fxc_h-0005 EURUSD spot from Friday 2026-11-20: 2026-11-24
fxc_h-0006 USDCAD spot from Friday 2026-11-20: 2026-11-23
fxc_h-0004 EURUSD spot from 2026-11-24, USD holiday 11-26: 2026-11-27
rtc_h-0001 99-16 = 99.5
rtc_h-0002 99-16+ = 99.515625
rtc_h-0003 99-162 = 99.5078125
rtc_h-0005 101.296875 in 64ths: 101-09+
rtc_h-0008 4 % two-period bond at 5 %: 99.036287924
rtc_h-0012 yield back from that price: 0.0500000000
rtc_h-0010 91-day bill at 5 % discount: 98.736111111
```

### Reading the numbers

- **Rounding never helps the order.** A buy at 10.005 rounds down to 10.00 and a sell rounds up to 10.01, so rounding can only make an order less aggressive (`eqc_h-0001`, `0002`; acceptance A3). Below 1.00 the tick is 0.0001. On the half-penny tier the grid is 0.005 (`eqc_h-0009`, `0010`).
- **Round lot by price.** At 250.01 the round lot is 40 shares, not 100 (`eqc_h-0015`); the tiers follow the current rule by default and the older 100-share lot with an earlier `as_of` (HR-110).
- **Settlement skips the weekend.** T+1 from Friday 2026-11-20 is Monday 2026-11-23 (`eqc_h-0008`).
- **Spot dates.** EURUSD is T+2 and skips the weekend (Tuesday 2026-11-24); USDCAD is T+1 (Monday). A USD holiday on 2026-11-26 moves EURUSD spot from the 26th to the 27th (`fxc_h-0004`).
- **32nds.** 99-16 is 99 and 16/32 = 99.5; the `+` adds 1/64; a third digit 2 adds 1/4 of a 32nd under HR-109 (quarter-tick contracts; eighth-tick contracts are not supported, HR-118), so 99-162 = 99.5078125.
- **Bond and bill.** A 4 % semi-annual bond with two periods left, at a 5 % yield, is worth 99.036287924; solving back from the exact price returns 5 %. A 91-day bill at a 5 % discount is 100 (1 - 0.05 x 91/360) = 98.736111111.

### The formal statement, checked against the spec

From [`09-microstructure/asset-conventions.md`](../../specifications/09-microstructure/asset-conventions.md) (rulings HR-80 to HR-116 in `specifications/stage-h-rulings-multiasset.md`).

- Equity tick: 0.01 at or above 1.00, 0.0001 below; the half-penny tier 0.005 from the compliance date (HR-110). Buy rounds down, sell rounds up.
- Spot date: T+2 good days on both currencies' calendars, T+1 for USDCAD; a USD holiday on T+1 counts as a settlement-day skip only.
- Bond: P = sum over i of (100 c/f)/(1+y/f)^i + 100/(1+y/f)^n on a coupon date; the yield is Brent on (-0.99 f, 10) with tolerance 1e-12, so `rtc_h-0012` is compared within tolerance, not byte for byte.
- Integer inputs are within +-(2^53-1); outside is `E_LIMIT` in all four builds (HR-116).

Evidence: most value cases were re-derived blind from the spec alone (DR-H2, `program/STAGE_H_BLIND_MULTIASSET.md`); [`oracle/OUTSIDE_SHARES.md`](../../oracle/OUTSIDE_SHARES.md) gives the share per item. The CME reading of the 32nds third digit is still unverified against the rulebook (HR-115).

## For practitioners

- **Calendars are inputs.** Holidays are passed in; nothing here knows a real exchange or currency calendar.
- **Fee cap.** `micro.eq.fee_check` tests an access fee against the cap for the date; it is not a fee schedule.

## Common mistakes

- **Reading 99-162 as more digits of 32nds.** The third digit is a fraction of one 32nd.
- **Assuming T+2 everywhere.** USDCAD spot is T+1, and US equities settle T+1.

## What you just did

You put prices on equity tick grids, found a round lot and settlement and spot dates, converted 32nds both ways and priced a bond and a bill.

## Try next

- Move the USD holiday in `fxc_h-0004` to 2026-11-25 and predict the spot date before you run it.
- [Tutorial 50](tutorial-50-auction-fx-and-futures-venues.md) runs these conventions inside three simulated venues.

## References and further reading

- This project: the spec above and its source list; all sources in [References](../references.md).
