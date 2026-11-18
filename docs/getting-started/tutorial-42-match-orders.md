# Tutorial 42: match orders on a simulated lit venue

<!-- tutorial:only python -->

The plain idea: a lit exchange keeps every resting order in a book and matches an incoming order against the best price first, and at one price against the oldest order first (price-time priority). An order that crosses the book trades, and whatever is left rests. Some order types change the rules: a post-only order must never take liquidity, so if it would cross, the venue rejects it.

You will run two of the spec's golden event lists through `exec.sim.lit.run`: a buy that sweeps two price levels, and a post-only buy that would cross. Budget 10 minutes.

<p class="note">Available from v0.10.0 (unreleased). The operation is implemented in all four builds on branch <code>stage-h2</code>; this page drives the Python build in process. Every output is labelled "simulated venue; not a real exchange". Every number below is a spec golden from <code>datasets/golden/stage_h/lit_h.json</code>, and the script stops if the build disagrees with it.</p>

Terms, defined here. The **maker** is the resting order in a trade and the **taker** the incoming one. **MBP** (market by price) is the book summed per price, what a level-2 feed shows. **Conservation** is the per-order account `submitted = filled + resting + cancelled + rejected`, which the engine reports for every order so you can check nothing was lost.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.

## Step 1: run two event lists

<!-- tutorial:run python -->
```python
# A simulated lit venue (exec.sim.lit.run): price-time priority and a post-only reject, goldens lit_h-0002 and 0005.
import json

from quantforge_core.cli.main import run_case

cases = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_h/lit_h.json", encoding="utf-8"))["cases"]}


def run(case_id):
    c = cases[case_id]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": c["operation"], "inputs": c["inputs"]}))
    assert r["outputs"] == c["expected"]["outputs"], case_id
    return r["outputs"]


out = run("lit_h-0002")
print("lit_h-0002 buy 8 at 102 against asks 5 at 101, 5 at 102, 5 at 103")
for f in out["fills"]:
    print(f"  fill {f['qty']} at {f['price']} from {f['maker_id']}")
print("  asks left", out["mbp"]["asks"], " B1", out["conservation"]["B1"])
out = run("lit_h-0005")
print("lit_h-0005 post-only buy at 101 against an ask at 101:", out["rejects"])
print("  bids", out["mbp"]["bids"], " label:", out["label"])
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
lit_h-0002 buy 8 at 102 against asks 5 at 101, 5 at 102, 5 at 103
  fill 5 at 101 from A1
  fill 3 at 102 from A2
  asks left [['102', '2'], ['103', '5']]  B1 {'submitted': '8', 'filled': '8', 'resting': '0', 'cancelled': '0', 'rejected': '0'}
lit_h-0005 post-only buy at 101 against an ask at 101: [{'id': 'B1', 'reason': 'POST_ONLY_WOULD_CROSS'}]
  bids [['100', '5']]  label: simulated venue; not a real exchange
```

### Reading the numbers

- **The sweep.** The buy of 8 at limit 102 takes all 5 at 101 first, then 3 of the 5 at 102. Each fill is at the maker's price, not the taker's limit, so the buyer pays 101 for the first five. The 103 level is beyond the limit and untouched (`lit_h-0002`).
- **Conservation.** The buy was 8 submitted and 8 filled, with nothing resting, cancelled or rejected.
- **Post-only.** A post-only buy at 101 would trade with the ask at 101, so it is rejected whole with `POST_ONLY_WOULD_CROSS`. The second post-only buy, at 100, does not cross and rests (`lit_h-0005`).

### The formal statement, checked against the spec

From [`10-execution/lit-matching.md`](../../specifications/10-execution/lit-matching.md), rulings HR-25 to HR-31 and HR-57/HR-58.

- Price-time priority: better price first, then lower `seq`; a trade prints at the resting order's price.
- Order types `LIMIT`, `MARKET`, `IOC`, `FOK`, `ICEBERG`, `POST_ONLY`, `PEG_MID`, `PEG_PRIMARY`; an iceberg's refresh goes to the back of its level.
- Prices on the tick grid and quantities on the lot grid, as exact decimals; every computed value inside the 36-digit range or `E_LIMIT`.

Evidence: `lit_h-0002` to `0009` and `0011` were re-derived blind from the spec alone (DR-H2, `program/STAGE_H_BLIND_WAVE2.md`); `lit_h-0010` was a mismatch that found an error in the spec lane's golden, which was corrected (the blind lane was not rerun, so it does not count).

## For practitioners

- **Simulated, not a venue model.** There is no latency, no queue position from a real feed and no other participants beyond the events you send.
- **Fees.** `fee_schedule` takes a maker rebate and a taker fee; both are applied exactly and reported per trader.

## Common mistakes

- **Expecting the taker's limit as the trade price.** The maker's price is the print.
- **Reading a reject as a cancel.** The conservation account keeps them apart.

## What you just did

You swept two price levels with one order, read the per-order conservation account, and saw a post-only order rejected for crossing.

## Try next

- [Tutorial 43](tutorial-43-dark-pool-and-routing.md) sends orders to a simulated dark pool and splits an order across venues.

## References and further reading

- This project: [`10-execution/lit-matching.md`](../../specifications/10-execution/lit-matching.md); all sources in [References](../references.md).
