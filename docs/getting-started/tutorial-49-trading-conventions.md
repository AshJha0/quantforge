# Tutorial 49: equity, FX and rates trading conventions

<!-- tutorial:only python -->

The plain idea: before any venue or model can run, a price has to sit on the right grid, a trade has to settle on the right day, and a bond quote has to be read the way the desk writes it. These are conventions, not models: there is one right answer, fixed by a rule or by market practice, and this page runs that answer.

You will round equity prices to the tick, find a round lot and a settlement date, value a pip and find FX spot dates, read and write Treasury prices in 32nds, price a bond and a bill, and see which SEC rule applies on which date. Budget 15 minutes.

<p class="note">Available from v0.10.0. The operations are implemented in all four builds (Python, Java, C++ and Rust); this page drives the Python build in process. Convention outputs carry no label (HR-111): they are arithmetic, not venue output.</p>

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


def outcome(case_id):  # the first output value, or the error code; either is checked against the golden
    c = cases[case_id]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": c["operation"], "inputs": c["inputs"]}))
    if c["expected"]["status"] == "error":
        assert r["error"]["code"] == c["expected"]["error_code"], case_id
        return r["error"]["code"]
    assert r["outputs"] == c["expected"]["outputs"], case_id
    return next(iter(r["outputs"].values()))


for cid, what in (("eqc_h-0020", "half-penny tier"), ("eqc_h-0021", "half-penny tier"), ("eqc_h-0022", "half-penny tier"),
                  ("eqc_h-0023", "fee 0.0015 at price 20"), ("eqc_h-0024", "fee 0.0015 at price 20"),
                  ("eqc_h-0026", "round lot at 500"), ("eqc_h-0027", "round lot at 500")):
    print(f"{cid} {what}, as_of {cases[cid]['inputs']['as_of']}: {outcome(cid)}")
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
eqc_h-0020 half-penny tier, as_of 2026-11-19: E_INPUT
eqc_h-0021 half-penny tier, as_of 2027-10-29: E_INPUT
eqc_h-0022 half-penny tier, as_of 2027-11-01: 10.005
eqc_h-0023 fee 0.0015 at price 20, as_of 2026-11-19: 0.003
eqc_h-0024 fee 0.0015 at price 20, as_of 2027-11-01: E_DOMAIN
eqc_h-0026 round lot at 500, as_of 2025-10-31: 100
eqc_h-0027 round lot at 500, as_of 2025-11-03: 40
```

### Reading the numbers

- **Rounding never helps the order.** A buy at 10.005 rounds down to 10.00 and a sell rounds up to 10.01, so rounding can only make an order less aggressive (`eqc_h-0001`, `0002`; acceptance A3). Below 1.00 the tick is 0.0001. On the half-penny tier the grid is 0.005 (`eqc_h-0009`, `0010`).
- **Round lot by price.** At 250.01 the round lot is 40 shares, not 100 (`eqc_h-0015`); the tiers follow the amended rule, in force since 2025-11-03, and the older 100-share lot with an `as_of` before that date (HR-110, HR-120).
- **Settlement skips the weekend.** T+1 from Friday 2026-11-20 is Monday 2026-11-23 (`eqc_h-0008`).
- **Spot dates.** EURUSD is T+2 and skips the weekend (Tuesday 2026-11-24); USDCAD is T+1 (Monday). A USD holiday on 2026-11-26 moves EURUSD spot from the 26th to the 27th (`fxc_h-0004`).
- **32nds.** 99-16 is 99 and 16/32 = 99.5; the `+` adds 1/64; a third digit 2 adds 1/4 of a 32nd under HR-109 (quarter-tick contracts; eighth-tick contracts are not supported, HR-118), so 99-162 = 99.5078125.
- **Bond and bill.** A 4 % semi-annual bond with two periods left, at a 5 % yield, is worth 99.036287924; solving back from the exact price returns 5 %. A 91-day bill at a 5 % discount is 100 (1 - 0.05 x 91/360) = 98.736111111.

## Step 2: which rule applies on which date

The plain idea: a rule change has a date, and three SEC rule changes adopted together did not keep the same date. The last seven lines of the output above ask the same question on each side of each date.

The formal statement (HR-120). The 2024 amendments changed the tick table (Rule 612), the access-fee cap (Rule 610(c)) and the round lot (Rule 600(b)(93)). SEC order 34-105656 of 2026-06-11 deferred compliance with the first two to the first business day of November 2027; the round-lot definition was not stayed. So the default `compliance_date` is 2027-11-01 for `micro.eq.round_price` and `micro.eq.fee_check` and 2025-11-03 for `micro.eq.round_lot`. With no `as_of` each operation applies the amended text. With an `as_of` it applies the rule in force on that date.

| Rule | Operation | Before the date | From the date | Compliance date |
|---|---|---|---|---|
| Tick table, Rule 612 | `micro.eq.round_price` | penny only at 1.00 or more; `HALF_PENNY` is `E_INPUT` | half-penny tier allowed | 2027-11-01 |
| Access-fee cap, Rule 610(c) | `micro.eq.fee_check` | 0.003 a share (0.3 % below 1.00) | 0.001 a share (0.1 % below 1.00) | 2027-11-01 |
| Round lot, Rule 600(b)(93) | `micro.eq.round_lot` | 100 shares at every price | 100, 40, 10 or 1 by price | 2025-11-03 |

The worked example. On 2026-11-19 the half-penny tier is refused (`eqc_h-0020`), and it is still refused on Friday 2027-10-29 (`eqc_h-0021`); on Monday 2027-11-01 a sell at 10.003 rounds to 10.005 (`eqc_h-0022`). A fee of 0.0015 at a price of 20 passes on 2026-11-19 against the 0.003 cap, which is the value printed (`eqc_h-0023`), and is `E_DOMAIN` from 2027-11-01 (`eqc_h-0024`). The round lot at 500 is 100 on 2025-10-31 and 40 on 2025-11-03 (`eqc_h-0026`, `0027`).

Evidence: the SEC order was read on 2026-11-19; goldens `eqc_h-0020` to `0027` sit at both sides of each date and pass in all four builds. Until that day every build used 2025-11-03 for all three rules, which was a wrong rule date for any `as_of` from 2025-11-03 to 2027-10-31 (`CHANGELOG.md`, 0.10.0). The SEC has the deferred rules under review, so 2027-11-01 may move; `compliance_date` is an input for that reason.

### The formal statement, checked against the spec

From [`09-microstructure/asset-conventions.md`](../../specifications/09-microstructure/asset-conventions.md) (rulings HR-80 to HR-120 in `specifications/stage-h-rulings-multiasset.md`).

- Equity tick: 0.01 at or above 1.00, 0.0001 below; the half-penny tier 0.005 from the compliance date, 2027-11-01 after the SEC deferral (HR-120). Buy rounds down, sell rounds up.
- Spot date: T+2 good days, T+1 for USDCAD. The first day after the trade needs only the non-USD currency to be open, so a USD-only holiday on that day does not stop the count; the value date itself must be a good day in both currencies and rolls forward if it is not. USDCAD T+1 is market convention; no primary source was read for it (HR-119).
- Bond: P = sum over i of (100 c/f)/(1+y/f)^i + 100/(1+y/f)^n on a coupon date; the yield is Brent on (-0.99 f, 10) with tolerance 1e-12, so `rtc_h-0012` is compared within tolerance, not byte for byte.
- Integer inputs are within +-(2^53-1); outside is `E_LIMIT` in all four builds (HR-116).

Evidence: most value cases were re-derived blind from the spec alone (DR-H2, `program/STAGE_H_BLIND_MULTIASSET.md`); [`oracle/OUTSIDE_SHARES.md`](../../oracle/OUTSIDE_SHARES.md) gives the share per item. The quarter digits 0, 2, 5 and 7 of the 32nds third digit were confirmed against a CME education page on 2026-11-19 (HR-118, which corrects the doubt recorded in HR-115).

## For practitioners

- **Calendars are inputs.** Holidays are passed in; nothing here knows a real exchange or currency calendar.
- **Fee cap.** `micro.eq.fee_check` tests an access fee against the cap for the date; it is not a fee schedule.
- **Pass `as_of` for the rule in force.** With no `as_of` the tick and fee operations apply the amended text, which is not in force before 2027-11-01.
- **Two wrong inputs, one code.** Checks run in one order in every build: `E_SCHEMA`, then `E_LIMIT` for a size limit on the input, then a non-finite number (`E_DOMAIN`), then structural `E_INPUT`, then `E_DOMAIN` (HR-122).

## Common mistakes

- **Reading the default as today's rule.** No `as_of` means the amended text. For an order sent today, pass today's date.
- **Reading 99-162 as more digits of 32nds.** The third digit is a fraction of one 32nd.
- **Assuming T+2 everywhere.** USDCAD spot is T+1, and US equities settle T+1.

## What you just did

You put prices on equity tick grids, found a round lot and settlement and spot dates, converted 32nds both ways and priced a bond and a bill.

## Try next

- Move the USD holiday in `fxc_h-0004` to 2026-11-25 and predict the spot date before you run it.
- [Tutorial 50](tutorial-50-auction-fx-and-futures-venues.md) runs these conventions inside three simulated venues.

## References and further reading

- This project: the spec above and its source list; all sources in [References](../references.md).
