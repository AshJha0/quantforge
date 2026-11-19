# Tutorial 43: a simulated dark pool, and splitting an order across venues

<!-- tutorial:only python -->

The plain idea: in a dark pool nobody sees the resting orders. A buy and a sell trade when both are present and each side's minimum size is met, at the midpoint of the lit market. A smart order router decides how much of an order to send as a market order now and how much to post at each venue, trading off fees, rebates and the risk of filling too little or too much.

You will run two dark pool goldens through `exec.sim.dark.run` and two router goldens through `exec.sor.allocate`. Budget 15 minutes.

<p class="note">Available from v0.10.0. The operations are implemented in all four builds; this page drives the Python build in process. Every dark pool output is labelled "simulated venue; not a real dark pool", and the router is scored in simulation only. Every number below is a spec golden from <code>datasets/golden/stage_h/dark_h.json</code> and <code>sor_h.json</code>, and the script stops if the build disagrees with it.</p>

Terms, defined here. The **mid** is halfway between the lit best bid and best ask. `min_qty` is the smallest fill an order accepts. For the router, `S` is the order size in lots, `M` the market-order part, `L[k]` the size posted at venue `k`, `h` the half spread, `f` the market-order fee, `r` a venue's rebate, `Q` the queue ahead of us, `lambda_u` and `lambda_o` the penalties per lot of underfill and overfill, and `lit_samples` equally likely draws of how much volume will trade at each venue ([CK] Cont and Kukanov).

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.

## Step 1: two dark pool runs and two allocations

<!-- tutorial:run python -->
```python
# A simulated dark pool and a smart order router, goldens dark_h-0001, 0002 and sor_h-0003, 0006.
import json

from quantforge_core.cli.main import run_case


def load(suite):
    return {c["case_id"]: c for c in json.load(open(f"datasets/golden/stage_h/{suite}.json", encoding="utf-8"))["cases"]}


cases = load("dark_h") | load("sor_h")


def run(case_id):
    c = cases[case_id]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": c["operation"], "inputs": c["inputs"]}))
    assert r["outputs"] == c["expected"]["outputs"], case_id
    return r["outputs"]


out = run("dark_h-0001")
f = out["fills"][0]
print(f"dark_h-0001 mid of 100.00/100.10: {f['qty']} at {f['price']}; resting", out["resting"])
out = run("dark_h-0002")
print("dark_h-0002 buy min_qty 80 against a sell of 60: fills", out["fills"], "| label:", out["label"])
out = run("sor_h-0003")
print(f"sor_h-0003 S 10, one lit venue: M {out['M']} L {out['L']} cost {out['expected_cost']}"
      f" fill {out['expected_fill']} P(underfill) {out['p_underfill']}")
out = run("sor_h-0006")
print(f"sor_h-0006 S 2, two lit venues: M {out['M']} L {out['L']} cost {out['expected_cost']}")
for row in out["ranking"][:3]:
    print(f"  ranked: M {row['M']} L {row['L']} cost {row['expected_cost']}")
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
dark_h-0001 mid of 100.00/100.10: 60 at 100.05; resting [{'id': 'B1', 'side': 'BUY', 'open_qty': '40', 'seq': 1}]
dark_h-0002 buy min_qty 80 against a sell of 60: fills [] | label: simulated venue; not a real dark pool
sor_h-0003 S 10, one lit venue: M 8 L ['2'] cost 7.35 fill 9.5 P(underfill) 0.25
sor_h-0006 S 2, two lit venues: M 0 L ['2', '0'] cost 0.2
  ranked: M 0 L ['2', '0'] cost 0.2
  ranked: M 0 L ['1', '1'] cost 0.3
  ranked: M 0 L ['0', '2'] cost 0.4
```

### Reading the numbers

- **Midpoint fill.** With the lit market at 100.00 bid, 100.10 ask, the buy of 100 and the sell of 60 trade 60 at the mid, 100.05. The buy's other 40 keep resting (`dark_h-0001`).
- **Minimum size.** The same buy with `min_qty` 80 will not accept a 60-lot fill, so nothing trades (`dark_h-0002`). A real pool would show you nothing either way, which is why a dark order risks not trading.
- **One venue.** To buy 10 lots with a queue of 2 ahead and outflow drawn from 0, 2, ..., 14, the cheapest split sends 8 as a market order and posts 2. The expected cost is 7.35 per order, the expected fill 9.5 lots, and a quarter of the draws fill too little (`sor_h-0003`). This matches [CK] Proposition 3 by hand.
- **Two venues.** Posting both lots at the venue with the higher rebate (0.3 against 0.1) costs 0.2; one lot at each costs 0.3; both at the lower-rebate venue 0.4 (`sor_h-0006`). The ranking lists every split by expected cost.

### The formal statement, checked against the spec

From [`10-execution/dark-pool.md`](../../specifications/10-execution/dark-pool.md) (HR-32 to HR-36) and [`10-execution/smart-order-router.md`](../../specifications/10-execution/smart-order-router.md) (HR-37 to HR-40).

- Dark pool: match after every event while a mid exists, buys then sells in `seq` order, at the mid on the tick grid; conditional orders firm up with probability `p_firm` (seeded draws).
- Router cost per scenario, [CK] eq. 5 with the dark extension: `(h + f) M - sum_k (h + r_k - as_k) fill_k + theta (M + sum L + (S - A)_+) + lambda_u (S - A)_+ + lambda_o (A - S)_+`, its expectation exact over the samples, minimised over every integer split (HR-38, HR-39).
- Exact arithmetic inside the 36-digit range, checked at the same steps in all four builds, else `E_LIMIT` (HR-57, HR-58; `sor_h-0010`, `sorx_h-0001`); the optional standard error follows one stated binary64 rule (`sorx_h-0002`).

Evidence: `dark_h-0001`, `0002`, `0004` and `sor_h-0003`, `0005`, `0006` were re-derived blind from the spec and [CK] alone (DR-H2, `program/STAGE_H_BLIND_WAVE2B.md`).

## For practitioners

- **Simulated venues only.** The outflow samples and dark tails are inputs; this computes the best split for the distribution you give it, and says nothing about whether that distribution is right.
- **Adverse selection** enters as a charge `as_k` per venue, subtracted from the rebate; the markouts operation `exec.sim.dark.markouts` measures it on simulated fills.

## Common mistakes

- **Treating the expected cost as a price.** It is per order, in the units of `h` and `f`, over the stated samples.
- **Ignoring underfill.** A cheap split that often fills too little is penalised by `lambda_u`; set it to what missing the order really costs you.

## What you just did

You filled a dark order at the mid, saw a minimum size block a trade, and split an order between a market order and posted size at one and at two venues.

## Try next

- Change `lambda_u` in `sor_h-0003` to 10 and predict the split before you run it.

## References and further reading

- R. Cont, A. Kukanov, "Optimal order placement in limit order markets", arXiv:1210.1625v4; *Quantitative Finance* 17(1), 2017.
- This project: the two specs above; all sources in [References](../references.md).
