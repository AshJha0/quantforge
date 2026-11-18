# Tutorial 36: slice an order: TWAP, VWAP and POV

<!-- tutorial:only python -->

The plain idea: a large order sent to the market in one go moves the price against you, so desks cut it into child orders. The three simplest ways to cut it are evenly in time (TWAP, time-weighted average price), in proportion to the volume you expect in each interval (VWAP, volume-weighted average price), or as a fixed share of the volume that actually trades (POV, percentage of volume). Whichever you use, the slices must add up to the order exactly.

You will rebuild six golden schedules by hand, see where the leftover units go when an order does not divide evenly, and see why a POV order can end the day unfinished. Budget 10 minutes. All inputs are synthetic.

<p class="note">Available from v0.10.0. The operations on this page are specified (spec version 0.1.0, confirmed 2026-11-18) but not merged in any language. Step 1 checks the spec's golden numbers with a plain-Python restatement of the formulas; step 2 shows the library call as it will run once the operations are merged, and is not run here. Every number on the page is a spec golden or simple arithmetic on one.</p>

Terms, defined here. A **parent order** is the whole quantity `X`; a **child order** or **slice** is the part sent in one **bucket** (an interval of the trading day). **Participation** `p` is your share of all volume traded in a bucket, your own fills included (ruling HR-4, confirmed by DR-H4). **UNITS** mode returns whole units; **CONTINUOUS** mode returns real numbers.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- Nothing else. The script below uses the Python standard library only, so it needs no build.

## Step 1: check the goldens by hand

The script restates the formulas of the spec in a few lines of plain Python and runs them on the inputs of the spec's golden cases. It calls no QuantForge operation: the operations are specified but not merged, so this page cannot yet send them through the four builds. CI runs this block and checks the printed lines.

<!-- tutorial:run python -->
```python
# Hand check of the spec goldens sched_h-0001..0006 in plain Python (no library call).
def twap_units(x, n):
    base, rem = divmod(x, n)
    return [base + (1 if i < rem else 0) for i in range(n)]

def vwap_units(x, w):
    raw = [x * wi / sum(w) for wi in w]
    out = [int(r) for r in raw]
    order = sorted(range(len(w)), key=lambda i: (-(raw[i] - out[i]), i))  # largest remainder, earliest wins
    for i in order[: x - sum(out)]:
        out[i] += 1
    return out

def pov(x, p, volumes, units=True):
    left, out = x, []
    for v in volumes:
        s = min(left, p * v / (1 - p))
        s = int(s) if units else s
        out.append(s)
        left -= s
    return out, left

print("sched_h-0001 TWAP 1000 in 3:", twap_units(1000, 3))
print("sched_h-0002 TWAP 1000 in 4:", [1000 / 4] * 4)
print("sched_h-0003 VWAP 1000 on [1,2,3,4]:", [1000 * w / 10 for w in [1, 2, 3, 4]])
print("sched_h-0004 VWAP 10 on [1,1,1]:", vwap_units(10, [1, 1, 1]))
s, r = pov(1000, 0.2, [1000, 2000, 4000])
print("sched_h-0005 POV 20%:", s, "residual", r)
s, r = pov(1000, 0.1, [900, 900], units=False)
print("sched_h-0006 POV 10%:", [round(x, 6) for x in s], "residual", round(r, 6))
print("realised participation, sched_h-0005 first two buckets:", [round(a / (a + v), 6) for a, v in zip([250, 500], [1000, 2000])])
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
sched_h-0001 TWAP 1000 in 3: [334, 333, 333]
sched_h-0002 TWAP 1000 in 4: [250.0, 250.0, 250.0, 250.0]
sched_h-0003 VWAP 1000 on [1,2,3,4]: [100.0, 200.0, 300.0, 400.0]
sched_h-0004 VWAP 10 on [1,1,1]: [4, 3, 3]
sched_h-0005 POV 20%: [250, 500, 250] residual 0
sched_h-0006 POV 10%: [100.0, 100.0] residual 800.0
realised participation, sched_h-0005 first two buckets: [0.2, 0.2]
```

### Reading the numbers

- **TWAP with a remainder.** 1,000 units in 3 buckets is 333 each with 1 left over. The spec gives each leftover unit to the earliest slices (ruling HR-3), so the first slice is 334 and the slices still add up to 1,000. In CONTINUOUS mode 1,000 in 4 buckets is 250 each, with nothing to place.
- **VWAP.** The profile `[1, 2, 3, 4]` sums to 10, so slice `i` is `1000 w_i / 10`. In UNITS mode the spec uses the largest-remainder rule: 10 units on a flat profile of three buckets is 3.333 each, the three remainders tie, and the earliest bucket gets the spare unit, `[4, 3, 3]`.
- **POV.** To be 20 % of all volume when others trade `v`, you trade `s` with `s / (s + v) = 0.2`, so `s = v p / (1 - p) = 0.25 v`. Against 1,000, 2,000 and 4,000 units of outside volume that is 250, 500 and 1,000, but only 250 units are left for the third bucket, so it is capped there (`sched_h-0005`). The first two buckets hit 20 % exactly.
- **An unfinished POV order.** At 10 % against 900 units a bucket, each slice is `0.1 / 0.9 x 900 = 100`; two buckets fill 200 and leave 800 (`sched_h-0006`). That is not an error: POV promises a participation rate, not completion, and the residual is reported.

### The formal statement, checked against the spec

From [`10-execution/schedules.md`](../../specifications/10-execution/schedules.md), rulings HR-2 to HR-4.

- `exec.schedule.twap`: UNITS slices are `floor(X/N)`, with the remainder `X mod N` given one unit at a time to slices 0, 1, ...
- `exec.schedule.vwap`: slice `i = X w_i / sum w`; UNITS by largest remainder, ties to the earliest bucket. An all-zero profile is `E_DOMAIN` (`sched_h-0008`).
- `exec.schedule.pov`: child `i = min(remaining, p v_i / (1 - p))`, floored in UNITS; outputs `slices`, `filled`, `residual`. `p` must lie in `(0, 1)`; `p = 1` is `E_DOMAIN` (`sched_h-0007`), because no finite order is 100 % of a volume that includes outside trades.

Evidence: hand calculation for every golden, then a blind re-derivation by a second lane that saw only the inputs (DR-H2, 2026-11-15): `sched_h-0001` to `0008` match. The textbook sources ([Kis13], [BL98]) were not read, so the definitions rest on the spec and the re-derivation, not on a book.

## Step 2: the library call (available from v0.10.0, not run here)

Once merged, the same cases go through any of the four builds with the batch command, for example:

```json
{"operation": "exec.schedule.pov", "inputs": {"quantity": 1000, "participation": 0.2, "market_volume": [1000, 2000, 4000], "mode": "UNITS"}}
```

The expected reply, from golden `sched_h-0005`, is `slices` `[250, 500, 250]` and `residual` 0. The conformance suite will be `sched_h`.

## For practitioners

- **The profile is an input.** `exec.schedule.vwap` takes the expected volume profile as given; it does not forecast one. A poor profile gives a poor VWAP schedule with no warning.
- **POV runs on observed volume.** A real POV algorithm reacts to volume as it prints. The operation takes the outside volume per bucket as a list, so it shows the rule, not the latency of following it.
- **No limit prices.** None of the three schedules carries a price limit in wave 1; adaptive algorithms (arrival price, market-on-close, liquidity seeking) are wave 2.

## Common mistakes

- **Participation of the wrong base.** `p` here is a share of total volume including your own. Using `p v` instead of `p v / (1 - p)` trades less than intended: 200 instead of 250 against 1,000.
- **Rounding each slice and losing units.** Rounding `333.33` three times gives 999. The remainder rule exists so the slices always sum to `X`.
- **Treating the POV residual as a failure.** It is the honest output when the market is thin.

## What you just did

You rebuilt six golden schedules by hand, placed leftover units by the spec's remainder rules, and saw a POV order hit its participation exactly where it was not capped and finish short where volume was thin.

## Try next

- Change the POV participation in `sched_h-0006` to 0.25 and predict the residual before you run it.
- Read [Tutorial 37](tutorial-37-almgren-chriss.md), which asks how fast to trade, not only how to cut the order.

## References and further reading

- R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2013. Recalled per the spec; not read.
- D. Bertsimas, A. Lo, "Optimal control of execution costs", *Journal of Financial Markets* 1, 1998, 1-50. Recalled per the spec; not read.
- This project: [`10-execution/schedules.md`](../../specifications/10-execution/schedules.md); all sources in [References](../references.md).
