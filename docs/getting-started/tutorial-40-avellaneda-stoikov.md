# Tutorial 40: quote both sides: Avellaneda-Stoikov

<!-- tutorial:only python -->

The plain idea: a market maker posts a bid and an ask and earns the gap when both fill. Holding inventory is risky, so a market maker who is long lowers both quotes, to sell more readily and buy less. The spread widens when the maker is more risk averse, when volatility is higher and when more time is left, and it carries a fixed term that depends on how quickly fills dry up as quotes move away from the mid.

You will compute the reservation price and quotes for a long and a flat book, the spread at the end of the horizon, and check three spreads against the tables printed in the paper. Budget 10 minutes. The inputs are the paper's section 3.3 parameters.

<p class="note">Available from v0.10.0. The operations on this page are specified (spec version 0.1.0, confirmed 2026-11-18) but not merged in any language. Step 1 checks the spec's golden numbers with a plain-Python restatement of the formulas; step 2 shows the library call as it will run once the operations are merged, and is not run here. Every number on the page is a spec golden or simple arithmetic on one.</p>

Terms, defined here. The **mid** `s` is the midpoint of the market. **Inventory** `q` is signed: positive is long. The **reservation price** `r` is the price at which the maker is indifferent to holding one more unit. `gamma` is risk aversion, `sigma` the volatility of the mid per unit of time, `time_left` the time to the end of the horizon, and `k` how fast the arrival rate of fills falls with the distance of a quote from the mid.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- Nothing else. The script below uses the Python standard library only, so it needs no build.

## Step 1: check the goldens by hand

The script restates the formulas of the spec in a few lines of plain Python and runs them on the inputs of the spec's golden cases. It calls no QuantForge operation: the operations are specified but not merged, so this page cannot yet send them through the four builds. CI runs this block and checks the printed lines.

<!-- tutorial:run python -->
```python
# Hand check of the Avellaneda-Stoikov goldens as_h-0001..0003 and 0005..0007 in plain Python (no library call).
import math

def as_quotes(s, q, gamma, sigma, time_left, k):
    if gamma <= 0 or k <= 0:
        raise ValueError("E_DOMAIN")
    r = s - q * gamma * sigma ** 2 * time_left
    spread = gamma * sigma ** 2 * time_left + (2 / gamma) * math.log(1 + gamma / k)
    return r, spread, r - spread / 2, r + spread / 2

for case, q in (("as_h-0001", 2), ("as_h-0002", 0)):
    r, sp, bid, ask = as_quotes(100, q, 0.1, 2, 1.0, 1.5)
    print(f"{case} q {q}, time left 1: r {r:.4f}  spread {sp:.10f}  bid {bid:.10f}  ask {ask:.10f}")
r, sp, _, _ = as_quotes(100, 2, 0.1, 2, 0.0, 1.5)
print(f"as_h-0003 q 2, time left 0: r {r:.4f}  spread {sp:.10f}")
for case, g, printed in (("as_h-0005", 0.1, "1.49"), ("as_h-0006", 0.01, "1.35"), ("as_h-0007", 1.0, "3.02")):
    print(f"{case} gamma {g:g}, time left 0.5: spread {as_quotes(100, 0, g, 2, 0.5, 1.5)[1]:.10f} (paper prints {printed})")
try:
    as_quotes(100, 0, 0.0, 2, 1, 1.5)
except ValueError as err:
    print("as_h-0004 gamma 0:", err)
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
as_h-0001 q 2, time left 1: r 99.2000  spread 1.6907704228  bid 98.3546147886  ask 100.0453852114
as_h-0002 q 0, time left 1: r 100.0000  spread 1.6907704228  bid 99.1546147886  ask 100.8453852114
as_h-0003 q 2, time left 0: r 100.0000  spread 1.2907704228
as_h-0005 gamma 0.1, time left 0.5: spread 1.4907704228 (paper prints 1.49)
as_h-0006 gamma 0.01, time left 0.5: spread 1.3489085437 (paper prints 1.35)
as_h-0007 gamma 1, time left 0.5: spread 3.0216512475 (paper prints 3.02)
as_h-0004 gamma 0: E_DOMAIN
```

### Reading the numbers

- **Long two units.** `r = 100 - 2 x 0.1 x 4 x 1 = 99.2`, eight tenths below the mid. The spread is `0.1 x 4 x 1 + (2/0.1) ln(1 + 0.1/1.5) = 0.4 + 20 ln(16/15) = 1.6907704228`, so the bid is 98.3546147886 and the ask 100.0453852114 (`as_h-0001`). Both quotes sit lower than for a flat book, so the ask is more likely to fill and the inventory to fall.
- **Flat.** With `q = 0` the reservation price is the mid, and the quotes are symmetric about 100 (`as_h-0002`).
- **At the end.** With no time left the inventory term vanishes and only `(2/gamma) ln(1 + gamma/k) = 1.2907704228` remains (`as_h-0003`).
- **Against the paper.** The spread is linear in time left, so its average over the horizon is its value half way. At `time_left = 0.5` the formula gives 1.4907704228, 1.3489085437 and 3.0216512475 for `gamma` 0.1, 0.01 and 1. The paper's Tables 1 to 3 (pp. 222-223) print 1.49, 1.35 and 3.02 (`as_h-0005` to `0007`, tolerance 0.005, since the paper averages a simulation).
- **Zero risk aversion** is `E_DOMAIN` (`as_h-0004`); the limit of the spread as `gamma` goes to 0 is `2/k`, which the spec checks as a property instead.

### The formal statement, checked against the spec

From [`09-microstructure/avellaneda-stoikov.md`](../../specifications/09-microstructure/avellaneda-stoikov.md), ruling HR-7, and [AS08] read in the published version.

- `r = s - q gamma sigma^2 (T - t)` ([AS08] eq. (29), p. 221).
- `delta_a + delta_b = gamma sigma^2 (T - t) + (2/gamma) ln(1 + gamma/k)` (eq. (30), p. 221); `bid = r - spread/2`, `ask = r + spread/2`.
- These are the paper's approximate solution (an expansion in `q`, section 3.2), not an exact solution of the control problem.

Evidence: `as_h-0005` to `0007` are checked against the paper's printed tables; `as_h-0001` to `0004` were re-derived blind from the inputs only (DR-H2, 2026-11-15).

## Step 2: the library call (available from v0.10.0, not run here)

```json
{"operation": "micro.mm.as_quotes", "inputs": {"mid": 100, "inventory": 2, "risk_aversion": 0.1, "sigma": 2, "time_left": 1, "k": 1.5}}
```

Expected, from golden `as_h-0001`: `reservation` 99.2, `spread` 1.6907704228, `bid` 98.3546147886, `ask` 100.0453852114.

## For practitioners

- **No tick rounding.** The operation returns real prices; the simulator rounds to ticks. A two-tick spread on a coarse grid can swamp the inventory shading.
- **No inventory limit.** The model will keep quoting however large `q` grows; a desk caps inventory separately.
- **The fill model is an assumption.** Exponential arrival intensity in the distance from the mid is the paper's choice. The market-making study (plan item H-18) tests it on simulated fills before any claim.

## Common mistakes

- **Sign of inventory.** Long is positive; a short book raises both quotes.
- **`sigma` per the wrong unit of time.** `sigma^2 time_left` must be in price units squared over the same clock as `time_left`.
- **Calling these exact.** They are the first-order approximation from the paper.

## What you just did

You computed reservation prices and quotes for a long and a flat book, saw the inventory term vanish at the end of the horizon, and matched three spreads against the paper's printed tables.

## Try next

- Set `q = -2` and predict both quotes before you compute them.
- Read [Tutorial 36](tutorial-36-slice-an-order.md) for the order-slicing side of execution.

## References and further reading

- M. Avellaneda, S. Stoikov, "High-frequency trading in a limit order book", *Quantitative Finance* 8(3), 2008, 217-224; read in the free copy on the first author's page.
- This project: [`09-microstructure/avellaneda-stoikov.md`](../../specifications/09-microstructure/avellaneda-stoikov.md); all sources in [References](../references.md).
