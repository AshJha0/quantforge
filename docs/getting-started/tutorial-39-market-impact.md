# Tutorial 39: how price moves with size: square-root and transient impact

<!-- tutorial:only python -->

The plain idea: buying moves the price up, and buying more moves it further, but not in proportion. Across many markets the average move over a large order grows roughly with the square root of its size, so four times the size gives about twice the move. A second question is what happens after you stop: part of the move fades as other traders refill the book. Obizhaeva and Wang model that refill and find that the cheapest way to trade, for a risk-neutral trader, is a block at the start, a steady rate in between, and a block at the end.

You will compute square-root impact for two sizes and the Obizhaeva-Wang optimal blocks for two sets of inputs, one of them the paper's own Figure 2 parameters. Budget 10 minutes. The coefficient `Y` is assumed, not estimated.

<p class="note">Available from v0.10.0. The operations on this page are implemented in all four languages (stage H wave 1; each build passes their goldens, observed, local, 2026-11-18). This page stays a hand check: step 1 checks the spec's golden numbers with a plain-Python restatement of the formulas, and step 2 shows the library call without running it. Every number on the page is a spec golden or simple arithmetic on one.</p>

Terms, defined here. **Impact** `I` is the average relative price change over a metaorder (a parent order worked over time), as a fraction of price. `V` is the daily volume and `sigma` the daily volatility, as a fraction. **Resilience** `rho` is the rate at which the book refills after a trade, per unit of time. **Temporary** impact fades; **permanent** impact stays.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- Nothing else. The script below uses the Python standard library only, so it needs no build.

## Step 1: check the goldens by hand

The script restates the formulas of the spec in a few lines of plain Python and runs them on the inputs of the spec's golden cases. It calls no QuantForge operation: it checks the spec's arithmetic independently of the builds. The operations themselves are built in all four languages and pass these goldens through the conformance runner; Tutorials 41 to 44 call the Python build directly. CI runs this block and checks the printed lines.

<!-- tutorial:run python -->
```python
# Hand check of the impact goldens imp_h-0001..0004 in plain Python (no library call).
import math

def sqrt_impact(q, v, sigma, y=1.0):
    return y * sigma * math.sqrt(q / v)

def ow_optimal(x, t, rho):
    block = x / (rho * t + 2)
    return block, rho * block, block

print(f"imp_h-0001 Q 1e5, V 1e7, sigma 2%: impact {sqrt_impact(1e5, 1e7, 0.02):.4f} ({sqrt_impact(1e5, 1e7, 0.02) * 1e4:.0f} bp)")
print(f"imp_h-0002 Q 4e5: impact {sqrt_impact(4e5, 1e7, 0.02):.4f} (four times the size, twice the impact)")
b0, rate, b1 = ow_optimal(1000, 1, 8)
print(f"imp_h-0003 X 1000, T 1, rho 8: blocks {b0:.0f} and {b1:.0f}, rate {rate:.0f}")
b0, rate, b1 = ow_optimal(1e5, 1, 2.231)
print(f"imp_h-0004 X 1e5, T 1, rho 2.231: blocks {b0:.10f}, rate {rate:.10f}")
print(f"  check: two blocks plus rate x T = {2 * b0 + rate:.6f}")
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
imp_h-0001 Q 1e5, V 1e7, sigma 2%: impact 0.0020 (20 bp)
imp_h-0002 Q 4e5: impact 0.0040 (four times the size, twice the impact)
imp_h-0003 X 1000, T 1, rho 8: blocks 100 and 100, rate 800
imp_h-0004 X 1e5, T 1, rho 2.231: blocks 23635.0744504845, rate 52729.8510990310
  check: two blocks plus rate x T = 100000.000000
```

### Reading the numbers

- **Square root.** 100,000 shares against a 10-million-share day is 1 % of the volume; with `sigma = 2 %` and `Y = 1` the impact is `0.02 x sqrt(0.01) = 0.002`, 20 bp (`imp_h-0001`). Four times the size gives 40 bp, twice the impact (`imp_h-0002`). These two goldens check the arithmetic of the stated form with `Y` supplied; they say nothing about whether a given market follows the law.
- **Obizhaeva-Wang, small case.** With `rho T = 8`, each block is `X / (rho T + 2) = 1000 / 10 = 100` and the rate in between is `rho X / (rho T + 2) = 800` per unit of time (`imp_h-0003`).
- **The paper's parameters.** With `X = 100,000`, `T = 1` day and `rho = 2.231` (Fig. 2, p. 14), each block is `100,000 / 4.231 = 23,635.0744504845` and the rate 52,729.8510990310 (`imp_h-0004`). Two blocks plus the rate over one day give back the 100,000 shares.
- **What the paper prints.** Figure 2 labels the first trade of the discrete solution for 10, 25 and 100 steps as 26,317, 24,697 and 23,899. They fall towards the continuous block of 23,635, which is consistent with it but is not a printed check of it; `imp_h-0004` is a hand calculation confirmed by a blind re-derivation.

### The formal statement, checked against the spec

From [`10-execution/impact.md`](../../specifications/10-execution/impact.md), rulings HR-2 and HR-10.

- `exec.impact.sqrt`: `I = Y sigma sqrt(Q / V)`, [TLD11] eq. (1), read 2026-11-18. The paper says only that `Y` is of order one and that the exponent lies between about 0.4 and 0.7; `Y` is an input here, default 1, labelled assumed (HR-10). `Q < 0` or `V <= 0` is `E_DOMAIN`.
- `exec.impact.ow_optimal`: `initial_block = final_block = X / (rho T + 2)`, `rate = rho X / (rho T + 2)` ([OW13] Proposition 3, eq. (31), p. 17). The optimal strategy does not depend on the impact size or the book depth (section 7.1, p. 17).

Evidence: `imp_h-0001` to `0004` re-derived blind from the inputs only (DR-H2, 2026-11-15); 0001 to 0003 exact, 0004 within 8e-16 relative.

## Step 2: the library call (shown, not run here)

```json
{"operation": "exec.impact.sqrt", "inputs": {"quantity": 100000, "daily_volume": 10000000, "daily_vol": 0.02, "coefficient": 1}}
```

Expected, from golden `imp_h-0001`: `impact` 0.002. The same number already comes out of the stage J liquidity curve at a one-day horizon (`liq.curve.cost`, [Tutorial 35](tutorial-35-liquidity-curve.md)), which is built to agree with it.

## For practitioners

- **Three impact models in the library.** Stage I's hedge solver charges a quadratic cost in the traded amount; this page adds the square-root law and the transient (decaying) model. They answer different questions: a cost to put in an optimiser, an average move for a size, and a schedule that lets the book recover. See the [glossary entry](../../GLOSSARY.md#stage-h-terms).
- **`Y` must be estimated before it means anything.** The crypto study (plan item H-1) will estimate it on one venue's book with standard errors; until it reports, every impact number here is an assumption.
- **A venue's book is not a market.** Impact fitted on one crypto venue's lit book is a proxy for that venue, not for equities or rates.

## Common mistakes

- **Annual volatility in a daily formula.** `sigma` is daily.
- **Shares against money.** `Q` and `V` must be in the same unit.
- **Treating `rho` as a probability.** It is a rate per unit of time; `rho T` is what enters the blocks.

## What you just did

You computed square-root impact for two sizes and the Obizhaeva-Wang block-rate-block schedule for two sets of inputs, and saw which numbers check arithmetic and which would need data.

## Try next

- Let `rho` fall towards 0 and watch each block tend to `X/2`: with no refill, trading in between is pointless.
- Read the [impact curves page](../curves/impact-curves.md).

## References and further reading

- B. Toth et al., "Anomalous price impact and the critical nature of liquidity in financial markets", *Physical Review X* 1, 2011, 021006 (open access); eq. (1) read.
- A. Obizhaeva, J. Wang, "Optimal trading strategy and supply/demand dynamics", *Journal of Financial Markets* 16(1), 2013, 1-32; read in the free copy on the first author's page.
- This project: [`10-execution/impact.md`](../../specifications/10-execution/impact.md); all sources in [References](../references.md).
