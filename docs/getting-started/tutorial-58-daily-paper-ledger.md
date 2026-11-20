# Tutorial 58: a daily paper ledger you can check from the ledger alone

<!-- tutorial:only python -->

The plain idea: each US business day a small job reads the Treasury par yield curve that the project's recorder has already written down, marks four made-up constant-maturity bonds on it, sends the one order a fixed timetable asks for to a simulated venue, and writes one row: what was held, what it was worth, what was traded, what the trade cost, and how the day's gain or loss splits into carry, roll-down, curve move and trading costs. Each row carries the hash of the row before it, and the latest hash is stamped outside the repository, so an old row cannot be changed quietly. Anyone holding only the ledger can recompute every day's P&L.

**This is plumbing evidence, not a strategy.** Every row is labelled "paper marks on a fitted curve; not tradable"; fills are simulated; the pre-trade estimate uses placeholder weights. The trading rule is a fixed rotation that never looks at the market. Paper trading on free data; simulated fills; no evidence of tradable profitability. No performance claim is made from this ledger.

You will replay the spec's worked day in exact decimal and see the P&L explain close with an unexplained term of exactly zero, then build a two-row chain and catch a one-digit edit. Budget 15 minutes.

<p class="note">Stage K. The daily job and its verifier (<code>tools/paper_daily/</code>), the workflow <code>.github/workflows/paper-ledger.yml</code> and the spec <code>specifications/12-platform/paper-ledger-daily.md</code> 0.1.0 (rulings KR-70 to KR-89, confirmed 2026-11-19) are merged to <code>main</code> (2026-11-19; not yet released). <strong>The ledger is not running yet: 0 of the 20 recorded trading days the v1.0.0 gate needs.</strong> The workflow has never run on a GitHub runner, and its schedule is withheld until the fixes for audit findings KA-C1 to KA-C5 and KA-C9 to KA-C13 (branch <code>k-audit-jobs</code>) are merged; those fixes change the gate command, the day count and the worked day below, and this page will be updated with them (<code>docs/known-issues.md</code>). Step 1 restates the arithmetic with the standard library and is the block CI checks; Step 2 is the verifier, run by hand once the ledger exists.</p>

Terms, defined here. A **DAY row** is one business day's record; a **GAP row** marks a business day with no recorded curve; a row written after its cut-off is **late** and carries no order. **Carry** is the coupon accrued plus interest on cash; **roll-down** is what the bond gains by ageing along yesterday's curve; **curve move** is what today's curve does to it; **fills and costs** is each fill against par. **Unexplained** is the NAV change minus those four. The **anchor** is an OpenTimestamps stamp of the head hash on a separate branch.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: replay one day, then break a chain

The worked day is the spec's own, on synthetic yields invented by the test (not market data): second day of an offline run, 2027-01-05. Opening position 26,500 units (USD 100 face each) of the 2-year exposure struck the day before at a coupon of 4.81%; cash 7,349,714.0625; the 3-month yield of the day before, 4.28%, is the cash rate.

<!-- tutorial:run python -->
```python
# The daily paper ledger, checked from the ledger alone: the worked example of
# specifications/12-platform/paper-ledger-daily.md (synthetic yields, second day 2027-01-05), replayed in exact
# decimal, then a two-row chain in the HR-45 canonical form with one byte changed.
import hashlib
import json
from decimal import ROUND_HALF_EVEN, Decimal as D

units, accrued, clean_roll, clean_close = D(26500), D("0.013287"), D("100.000625"), D("99.925390")
cash_open, rate = D("7349714.0625"), D("0.0428")
fills = [(4200, D("100.0078125")), (2200, D("100.01171875")), (4700, D("100.015625"))]  # BUY 5Y, simulated
nav_open = cash_open + 100 * units

coupon_accrual = units * accrued
cash_interest = (cash_open * rate / 365).quantize(D("0.01"), ROUND_HALF_EVEN)  # posted to the cent
carry = coupon_accrual + cash_interest
roll_down = units * (clean_roll - 100)
curve_move = units * (clean_close - clean_roll)
fills_costs = sum(q * (100 - p) for q, p in fills)  # s q (100 - p), s = +1 for a BUY; fees 0
mark = clean_close + accrued
cash_close = cash_open + cash_interest + units * (mark - 100) - sum(q * p for q, p in fills)  # old bond settled, re-struck at 100
nav_close = cash_close + 100 * (units + sum(q for q, _ in fills))
explained = carry + roll_down + curve_move + fills_costs


def s(x):  # a decimal without trailing zeros
    return format(x.normalize(), "f") if x else "0"


print(f"carry {s(carry)} roll_down {s(roll_down)} curve_move {s(curve_move)} fills_costs {s(fills_costs)}")
print(f"NAV {s(nav_open)} -> {s(nav_close)}: change {s(nav_close - nav_open)}, explained {s(explained)}, unexplained {s(nav_close - nav_open - explained)}")


def canonical(row):  # HR-45: keys sorted, no whitespace, ASCII only; the row without its hash
    return json.dumps({k: v for k, v in row.items() if k != "hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


rows, prev = [], "0" * 64
for seq, body in enumerate(({"start_cash": "10000000"}, {"date": "2027-01-04", "pnl": "-285.9375"})):
    row = {"seq": seq, "kind": "GENESIS" if seq == 0 else "DAY", "label": "paper marks on a fitted curve; not tradable", "body": body, "prev": prev}
    row["hash"] = prev = hashlib.sha256(canonical(row)).hexdigest()
    rows.append(row)


def verify(lines):
    prev = "0" * 64
    for seq, line in enumerate(lines):
        row = json.loads(line)
        if row["prev"] != prev:
            return False, seq, "LINK"
        if hashlib.sha256(canonical(row)).hexdigest() != row["hash"]:
            return False, seq, "HASH"
        prev = row["hash"]
    return True, None, None


text = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows]
print("miniature chain verifies:", verify(text))
print("P&L -285.9375 edited to -285.9374:", verify([text[0], text[1].replace("-285.9375", "-285.9374")]))
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
carry 1213.9355 roll_down 16.5625 curve_move -1993.7275 fills_costs -132.03125
NAV 9999714.0625 -> 9998818.80175: change -895.26075, explained -895.26075, unexplained 0
miniature chain verifies: (True, None, None)
P&L -285.9375 edited to -285.9374: (False, 1, 'HASH')
```

### Reading the numbers

- **Carry.** Coupon accrued over one day on 26,500 units: `26,500 x 0.013287 = 352.1055` (accrued = `2.405 x 1/181`, half the 4.81 coupon over a 181-day period, rounded to 6 decimals). Cash interest `7,349,714.0625 x 0.0428 / 365 = 861.83`, posted to the cent. Carry 1,213.9355.
- **Roll-down.** Yesterday's 2-year bond is now one day shorter; read on yesterday's curve at its new maturity its yield is 4.809585, so its clean price is 100.000625: `26,500 x 0.000625 = 16.5625`.
- **Curve move.** Today's curve gives it 4.849562 and a clean price of 99.925390: `26,500 x (99.925390 - 100.000625) = -1,993.7275`.
- **Fills and costs.** The rule's step 1 buys the 5-year exposure: 11,300 units asked, the simulated book shows 4,200, 2,200 and 4,700 at three prices just above par, so 11,100 fill and 200 are cancelled. Each fill against par costs `q x (p - 100)`: 32.8125 + 25.78125 + 73.4375 = 132.03125.
- **The identity.** `1,213.9355 + 16.5625 - 1,993.7275 - 132.03125 = -895.26075`, which is exactly NAV 9,998,818.80175 minus 9,999,714.0625. Unexplained 0.
- **The chain.** Each row's hash is SHA-256 of its canonical bytes, which include the previous row's hash. Changing one digit of a P&L makes that row's hash wrong. The miniature above uses the same canonical rule (HR-45) but not the full row format of `qf-paper-ledger/1`.

### Why the unexplained term must be exactly zero, and what that does not show

The spec sets the threshold at exactly 0 (KR-79): every term is an exact decimal product of recorded 6-decimal marks and whole lots, the three market terms telescope to `n x (mark - 100)`, and the only rounding, cash interest to the cent, is posted to cash as rounded. So a non-zero residual can only be a bookkeeping fault; the writer refuses to append such a day and the verifier fails a ledger that has one.

That makes the explain a **bookkeeping test**, zero by construction. It is not a test of a risk model, because its terms are successive revaluations, not sensitivities times moves. And it says nothing about performance: the rule ignores the market, the marks are not prices of any security, and the costs are assumptions with no source.

### How to verify from the ledger alone

The verifier (`tools/paper_daily/verify_ledger.py verify`) checks in a fixed order and stops at the first failure, never repairing (KR-84 to KR-86, KR-89):

1. **The chain**, row by row: `PARSE` (including a repeated key), `SEQ`, `HASH`, `LINK`, `LABEL`, `FORMAT`, `KIND`.
2. **The configuration**: the genesis row holds the whole configuration and its hash; a later change to it is `CONFIG`.
3. **Dates**: each a business day, none missing (`MISSING_DAY`), the on-time or late label recomputed from the row's write time (`TIMING`), and no date inside a preregistered study's holdout window (`HOLDOUT`).
4. **Exact replay from the ledger alone**: from the genesis cash, each day opens at the previous day's close, and cash interest, every explain term, cash, positions, NAV and P&L are recomputed in exact decimal from the row's own marks and fills (`CASH`, `POSITION`, `NAV`, `EXPLAIN`, `ORDER`, `COUNT`). This path uses no CLI and no data outside the ledger; it is what Step 1 does for one day.
5. **Rebuild through the CLI** (`RECOMPUTE`): marks, the rule's order, the seed and book, the limit check, the fills and both TCA records are rebuilt and compared, with a 1e-6 relative allowance on decimal fields because bond prices pass through binary64 `pow`. The exact replay of step 4 has no allowance, so the allowance cannot hide a wrong P&L.
6. **Anchors and the day count** (`ANCHOR`, `DAYS`): every anchor held must match the ledger line it names, which catches a consistent rewrite of old rows and a truncated tail; `--require-days 20` is the v1.0.0 gate.

Acceptance tests P1 to P11 were fixed in the spec before the first scheduled run. Planted faults, each shown failing with its own reason, are test P7; they were measured on the local laptop (40 tests, Windows, Python 3.15), not on CI.

## Step 2: the real verifier (by hand, once the ledger exists)

<!-- runs-after-integration: T58 (by hand; not for CI) -->
These commands use `tools/paper_daily/` and, for the second block, the `paper-ledger` branch, which does not exist until the workflow first runs on `main`. They are not for the tutorial checker: their output depends on the day they are run. The handover's dry run on 2026-11-19 printed one DAY row for 2026-11-18 (a BUY of 26,500 units of `UST-CM-2Y`, partly filled; P&L -293.75); its hash changes from run to run until the ledger exists, because the genesis row holds the run time.

```bash
# Dry run: prints the rows a run would add now and writes nothing.
git fetch origin forward-log
python tools/paper_daily/run_day.py --ledger-ref origin/paper-ledger --forward-log-ref origin/forward-log --dry-run
```

```bash
# Once the ledger exists: the exact replay from the ledger alone, then the full check and the gate.
git fetch origin paper-ledger paper-ledger-anchors
git show origin/paper-ledger:ledger/ledger.jsonl > ledger.jsonl
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --no-cli
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --require-days 20
```

`--no-cli` says so in its output (`"calendar_checked": false, "recomputed": false`).

## For practitioners

- **What a hash chain proves.** It proves the rows were not edited after the anchor that covers them. It does not prove the yields were right or that the simulator is realistic.
- **Late days and gaps are counted as what they are.** Only on-time DAY rows count towards the 20 days; a late day carries no order; a gap is never filled in later.
- **Never repair the ledger.** A rewrite, a rebase or a force-push makes it no longer evidence; the anchors make a rewrite visible. A changed configuration needs a new format string and a new ledger.
- **Why not real Treasury prices.** FedInvest end-of-day prices are not used: the site's robots file disallows automated agents and its terms limit use to personal viewing (read 2026-11-19, KR-70). This is a reading of published terms, not legal advice. The ledger uses the plan's fallback, constant-maturity exposures on a curve through the five par yields the recorder already keeps.

## Common mistakes

- **Reading the cumulative P&L as a track record.** Any chart built from the ledger must carry the row label, "simulated" for fills, "placeholder weights" beside the pre-trade estimate, and the sentence that no performance claim is made.
- **Accruing cash interest on the closing balance.** It is on the opening balance at the previous day's 3-month yield, actual/365, rounded to the cent.

## What you just did

You replayed a paper ledger day in exact decimal from its own numbers, saw the explain close to zero by construction, built a hash chain and caught a one-digit edit, and read what the real verifier checks and in what order.

## Try next

- Change the curve-move price 99.925390 to 99.925391 and rerun: which line changes, and why does the unexplained term stay 0? (Because NAV is recomputed from the same mark; the verifier's `RECOMPUTE` step is what catches a wrong mark.)

## References and further reading

- This project: `specifications/12-platform/paper-ledger-daily.md`, `specifications/stage-k-rulings-paper.md`, `docs/developer-guides/paper-ledger.md`, `program/STAGE_K_PAPER_HANDOVER.md`; the stage H paper book in [Tutorial 44](tutorial-44-paper-trading.md) and [`paper-trading.md`](../../specifications/10-execution/paper-trading.md); anchors in [`forward-log-anchors.md`](../developer-guides/forward-log-anchors.md).
- NIST FIPS 180-4, *Secure Hash Standard* (SHA-256), cited in the spec (standard; recalled).
