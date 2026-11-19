# Tutorial 38: what did the trade cost? Implementation shortfall

<!-- tutorial:only python -->

The plain idea: compare what you actually got with a paper portfolio that traded the whole order at the price when you decided to trade. The difference is the implementation shortfall. Splitting it shows where the money went: the price moved before you started (delay), your fills were worse than the price at arrival (execution), part of the order never filled while the price ran away (opportunity), and fees.

You will decompose one buy order of 1,000 shares by hand, flip it to a sell, and see an overfilled order rejected. Budget 10 minutes. The fills are synthetic.

<p class="note">Available from v0.10.0. The operations on this page are implemented in all four languages (stage H wave 1; each build passes their goldens, observed, local, 2026-11-18). This page stays a hand check: step 1 checks the spec's golden numbers with a plain-Python restatement of the formulas, and step 2 shows the library call without running it. Every number on the page is a spec golden or simple arithmetic on one.</p>

Terms, defined here. The **decision price** `P_d` is the price when the order was decided; the **arrival price** `P_0` the price when it reached the market; the **end price** `P_c` the price at the end of the horizon. `s` is +1 for a buy and -1 for a sell; `X` is the order and `Q` the quantity filled. A positive cost is a loss to the trader.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- Nothing else. The script below uses the Python standard library only, so it needs no build.

## Step 1: check the goldens by hand

The script restates the formulas of the spec in a few lines of plain Python and runs them on the inputs of the spec's golden cases. It calls no QuantForge operation: the operations are specified but not merged, so this page cannot yet send them through the four builds. CI runs this block and checks the printed lines.

<!-- tutorial:run python -->
```python
# Hand check of the shortfall goldens tca_h-0001 and 0002 in plain Python (no library call).
def shortfall(side, p_d, p_0, p_c, x, fills, fees):
    s = 1 if side == "BUY" else -1
    q = sum(qi for qi, _ in fills)
    if q > x:
        raise ValueError("E_INPUT: fills exceed the order")
    delay = s * q * (p_0 - p_d)
    execution = s * sum(qi * (pi - p_0) for qi, pi in fills)
    opportunity = s * (x - q) * (p_c - p_d)
    total = delay + execution + opportunity + fees
    return delay, execution, opportunity, total, total / (x * p_d) * 1e4

fills = [(600, 100.20), (200, 100.30)]
for case, side, fees in (("tca_h-0001", "BUY", 5.0), ("tca_h-0002", "SELL", 0.0)):
    d, e, o, t, bp = shortfall(side, 100.0, 100.10, 101.0, 1000, fills, fees)
    tail = f"  ({bp:.1f} bp)" if side == "BUY" else ""
    print(f"{case} {side}: delay {d:.2f}  execution {e:.2f}  opportunity {o:.2f}  total {t:.2f}{tail}")
    print(f"  parts sum to the total: {abs(d + e + o + fees - t) < 1e-10}")
try:
    shortfall("BUY", 100.0, 100.10, 101.0, 1000, fills + [(400, 100.4)], 0.0)
except ValueError as err:
    print("tca_h-0003 overfill:", err)
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
tca_h-0001 BUY: delay 80.00  execution 100.00  opportunity 200.00  total 385.00  (38.5 bp)
  parts sum to the total: True
tca_h-0002 SELL: delay -80.00  execution -100.00  opportunity -200.00  total -380.00
  parts sum to the total: True
tca_h-0003 overfill: E_INPUT: fills exceed the order
```

### Reading the numbers

- **Delay.** The price moved from 100.00 to 100.10 before the order arrived. The spec charges that on the filled quantity only: `800 x 0.10 = 80` (ruling HR-8).
- **Execution.** Fills against the arrival price: `600 x 0.10 + 200 x 0.20 = 100`.
- **Opportunity.** 200 shares never filled, and the price ended 1.00 above the decision price: `200 x 1 = 200`.
- **Total.** `80 + 100 + 200 + 5` in fees is 385, or 38.5 bp of the order's value at the decision price (`tca_h-0001`).
- **A sell.** The same prices and fills for a seller give every component with the opposite sign, -380 in total with no fees (`tca_h-0002`): a seller gains when prices rise.
- **An overfill.** Fills of 1,200 against an order of 1,000 are `E_INPUT` (`tca_h-0003`).

### The formal statement, checked against the spec

From [`10-execution/tca.md`](../../specifications/10-execution/tca.md), ruling HR-8 (confirmed by DR-H3).

- delay `= s Q (P_0 - P_d)`; execution `= s sum q_i (p_i - P_0)`; opportunity `= s (X - Q)(P_c - P_d)`;
- total `= delay + execution + opportunity + fees`; `total_bps = total / (X P_d) x 1e4`.

The components sum to the total to 1e-10 relative, and a full fill has zero opportunity cost (property tests). Evidence: hand calculation, then a blind re-derivation from the inputs only (DR-H2, 2026-11-15); `tca_h-0001` to `0003` match. Perold's paper and Kissell's book are not free and were not read; the definition rests on the spec.

## Step 2: the library call (shown, not run here)

```json
{"operation": "exec.tca.shortfall", "inputs": {"side": "BUY", "decision_price": 100, "arrival_price": 100.10, "end_price": 101, "order_quantity": 1000, "fills": [[600, 100.20], [200, 100.30]], "fees": 5}}
```

Expected, from golden `tca_h-0001`: delay 80, execution 100, opportunity 200, total 385, 38.5 bp.

## For practitioners

- **Which quantity carries the delay.** This spec charges delay on the filled quantity and books the rest as opportunity cost (Perold's split). A full-order delay (a Kissell variant) is not offered, so reports built the other way will not reconcile line by line.
- **Execution cost is not yet split into impact and spread.** That needs the mid-price path and is wave 2.
- **Choose the end price before you look.** Opportunity cost depends on `P_c`; fix the rule (close, end of horizon) in advance.

## Common mistakes

- **Forgetting the side.** A sell with buy signs reports a gain as a cost.
- **Dividing by the filled value.** `total_bps` divides by `X P_d`, the paper portfolio, not by `Q` times the average fill.
- **Leaving out unfilled shares.** Without opportunity cost, an order that fills only when the price comes back looks cheap.

## What you just did

You split one order's shortfall into delay, execution, opportunity and fees, checked that the parts add to the total, and saw the signs flip for a seller.

## Try next

- Fill the remaining 200 shares at 100.90 in the script and recompute: opportunity becomes zero and execution grows.
- Read [Tutorial 39](tutorial-39-market-impact.md) for models of how much trading moves the price.

## References and further reading

- A. Perold, "The implementation shortfall: paper versus reality", *Journal of Portfolio Management* 14(3), 1988, 4-9. Recalled per the spec; not read.
- This project: [`10-execution/tca.md`](../../specifications/10-execution/tca.md); all sources in [References](../references.md).
