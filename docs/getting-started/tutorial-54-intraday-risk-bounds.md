# Tutorial 54: a fast risk number, and how wrong it can be

<!-- tutorial:only python -->

The plain idea: revaluing a whole book on every market move is slow. Delta and gamma, computed once, give a fast estimate of the P&L for a move. The estimate is only worth showing with a statement of how far off it can be, and for smooth instruments Taylor's theorem gives that statement exactly: the error is at most a known constant times the cube of the move.

You will compute the delta-gamma estimate and its bound for a zero-coupon position under four shifts and for a two-position book, compare each with exact revaluation, and see how close to the bound the true error comes. Budget 10 minutes.

<p class="note">Stage K. The operation <code>risk.intraday.delta_gamma_bound</code> is merged to <code>main</code> in all four builds (2026-11-19; not in a tag) (spec <code>specifications/06-risk/intraday-risk-bounds.md</code> 1.0.0, rulings KR-7, KR-10, KR-15, KR-17). Acceptance evidence files: Python and Java; C++ and Rust run the same properties in their unit tests without writing evidence files (<code>program/STAGE_K_W1_HANDOVER.md</code>). Its outside-check share is 5 of 5 value cases after the K-5a blind packet (see "Evidence" below). Every output carries the label "latency-aware analytics on simulated data". Step 1 restates the rule with the standard library on the golden inputs; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. A zero-coupon position pays notional `N` at maturity `T`; at continuous yield `y` it is worth `V(y) = N exp(-y T)`. A parallel **shift** `h` moves every yield by the same amount. The **estimate** is `V'(y) h + V''(y) h^2 / 2`; the **bound** is the most the estimate can miss the exact change by.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: estimate, bound and exact change

```python
# Delta-gamma estimate and its Lagrange bound for zero-coupon positions (risk.intraday.delta_gamma_bound),
# goldens idr_k-0001 to 0005, restated with the standard library.
import math


def position(n, t, y, h):
    v = n * math.exp(-y * t)
    estimate = v * (-t * h + t * t * h * h / 2)  # V' h + V'' h^2 / 2
    m3 = t ** 3 * abs(n) * math.exp(-t * min(y, y + h))  # max |V'''| on the segment
    exact = n * math.exp(-(y + h) * t) - v
    return estimate, m3 * abs(h) ** 3 / 6, exact


GOLDEN = {  # case: (positions, h, golden estimate_pnl, golden bound)
    "idr_k-0001": ([(1e6, 5, 0.04)], 0.01, -39913.124212551616, 17.05689068912462),
    "idr_k-0002": ([(1e6, 5, 0.04)], -0.01, 41959.95109524657, 17.93141617552204),
    "idr_k-0003": ([(1e6, 5, 0.04)], 0.0025, -10170.171073390556, 0.2665139170175722),
    "idr_k-0004": ([(1e6, 5, 0.04)], 0.05, -179097.35223580853, 2132.1113361405783),
    "idr_k-0005": ([(1e6, 5, 0.04), (-5e5, 2, 0.03)], 0.01, -30589.655330067555, 17.684733711514124),
}
for case, (book, h, g_est, g_bound) in GOLDEN.items():
    parts = [position(n, t, y, h) for n, t, y in book]
    est, bound, exact = (sum(p[i] for p in parts) for i in range(3))  # bounds add with no netting
    assert abs(est - g_est) <= 1e-9 * abs(g_est) and abs(bound - g_bound) <= 1e-9 * g_bound, case
    err = est - exact
    print(f"{case} h {h:+.4f} estimate {est:,.2f} exact {exact:,.2f} error {err:,.4f} bound {bound:,.4f} error/bound {abs(err) / bound:.3f}")
print("label: latency-aware analytics on simulated data")
```

Output (CI checks that Step 2 prints these lines):

<!-- tutorial:expect -->
```text
idr_k-0001 h +0.0100 estimate -39,913.12 exact -39,929.97 error 16.8458 bound 17.0569 error/bound 0.988
idr_k-0002 h -0.0100 estimate 41,959.95 exact 41,977.22 error -17.2723 bound 17.9314 error/bound 0.963
idr_k-0003 h +0.0025 estimate -10,170.17 exact -10,170.44 error 0.2657 bound 0.2665 error/bound 0.997
idr_k-0004 h +0.0500 estimate -179,097.35 exact -181,102.60 error 2,005.2492 bound 2,132.1113 error/bound 0.940
idr_k-0005 h +0.0100 estimate -30,589.66 exact -30,605.88 error 16.2211 bound 17.6847 error/bound 0.917
label: latency-aware analytics on simulated data
```

### Reading the numbers

- **One position, +1%.** `V(y) = 1,000,000 exp(-0.2) = 818,730.75`. The estimate is `V (-T h + T^2 h^2 / 2) = 818,730.75 x (-0.05 + 0.00125) = -39,913.12`. The exact change is -39,929.97, so the estimate is 16.85 too high. The bound is `T^3 V h^3 / 6 = 125 x 818,730.75 x 1e-6 / 6 = 17.06` (`idr_k-0001`).
- **The bound is tight.** The error is 0.94 to 0.997 of the bound. For a zero bond the third derivative barely changes over the shift, so the Lagrange remainder is nearly the whole error. A test where the bound was loose by a factor of ten would not catch a bound that is wrong by a factor of two; this one would.
- **Downward shifts cost more bound.** `M3` is the largest `|V'''|` on the segment, which for a falling yield sits at the far end, `y + h`, so the bound for -1% (17.93) is larger than for +1% (17.06) (`idr_k-0002`).
- **Cubic scaling.** A quarter of the shift gives about 1/64 of the bound: 0.2665 against 17.06 (`idr_k-0003`). Five times the shift gives about 125 times: 2,132 (`idr_k-0004`).
- **A book.** Adding a short of 500,000 at 2 years, the bounds add with no netting, because the signs of the two remainders are not known in general; the error uses 0.917 of the summed bound (`idr_k-0005`, filled by the oracle lane at 50 digits, not blind).

### The formal statement, checked against the spec

From `specifications/06-risk/intraday-risk-bounds.md` (read 2026-11-19).

- For `V` three times differentiable between `x` and `x + h`: `|V(x + h) - V(x) - V'(x) h - V''(x) h^2 / 2| <= M3 |h|^3 / 6`, `M3 = max |V'''|` on the segment (Lagrange remainder; Apostol, *Calculus* vol. 1, section 7.7, cited for the definition only, recalled).
- Zero-coupon position: `V' = -T V`, `V'' = T^2 V`, `|V'''| = T^3 |V|`, decreasing in `y`, so `M3 = T^3 |N| exp(-T min(y, y + h))` (absolute value for a short, KR-15). For a book the position bounds are summed. KR-17 derives the rounding budget of the binary64 bound.
- `T = 0` is `E_DOMAIN` (`idr_k-0006`); an empty book `E_INPUT` (`idr_k-0007`). Instruments without an `M3` are reported as "no bound" and excluded from the "with error bounds" claim.
- Acceptance (fixed before the run): the goldens at 1e-9 relative; 1,000 seeded parallel moves, `h` uniform in [-0.02, 0.02], on a seeded 50-position book: `|estimate - full revaluation| <= bound` on every move. Evidence (measured by the k-w1 lane): zero violations in Python (worst error over bound 0.0105) and Java (0.382; Java draws its own book), key `intraday_bound_1000_moves`; rechecked at 50 digits by `oracle/python/check_stage_k_idr_moves.py`, zero exact violations (`oracle/IDR_K_MOVES_CHECK_W1.json`). That recheck is our own oracle, not an outside check.

### Evidence: the outside-check share

Plan section 15 asks for outside checks on at least 60% of an item's value cases. For this item it is 5 of 5 (`oracle/OUTSIDE_SHARES.md`, stage K section, generated by `tools/outside_shares.py`). The wave-1 blind lane had checked the four single-position bounds only to 6 decimals and did not have `idr_k-0005`, so the item stood at 0 of 5; a second, clean blind packet re-derived `idr_k-0001` to `0005` at 1e-9 relative, 5 of 5 MATCH (`program/STAGE_K_BLIND_K5A.md`, evidence class measured). What this shows: the spec is unambiguous and the arithmetic is right. It does not check the bound's derivation; the evidence for that is the 50-digit recheck of the 1,000 moves (`oracle/IDR_K_MOVES_CHECK_W1.json`), which is our own oracle and does not count as outside.

## Step 2: the same cases through the library

This block calls the library on the goldens in `datasets/golden/stage_k/`. It was turned on at integration (2026-11-19) and printed the same lines as Step 1; CI now checks them. The exact revaluation is not an output of the operation, so the block computes it.

<!-- tutorial:run python -->
```python
# Goldens idr_k-0001 to 0005 through risk.intraday.delta_gamma_bound; exact revaluation computed here.
import json
import math

from quantforge_core.cli.main import run_case

cases = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_k/idr_k.json", encoding="utf-8"))["cases"]}
for n in range(1, 6):
    c = cases[f"idr_k-{n:04d}"]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]}))
    out, want, h = r["outputs"], c["expected"]["outputs"], c["inputs"]["shift"]
    assert all(abs(out[k] - want[k]) <= 1e-9 * abs(want[k]) for k in ("estimate_pnl", "bound")) and out["label"] == want["label"]
    exact = sum(p["notional"] * (math.exp(-(p["yield"] + h) * p["maturity"]) - math.exp(-p["yield"] * p["maturity"]))
                for p in c["inputs"]["positions"])
    est, bound = out["estimate_pnl"], out["bound"]
    err = est - exact
    print(f"{c['case_id']} h {h:+.4f} estimate {est:,.2f} exact {exact:,.2f} error {err:,.4f} bound {bound:,.4f} error/bound {abs(err) / bound:.3f}")
print("label:", out["label"])
```

## For practitioners

- **A bound, not an estimate of the error.** The bound says the estimate is off by at most 17.06 for +1%; it does not say by how much in a given move. Here it is tight because the instrument is simple.
- **Zero-coupon positions only.** Swaps, options and anything with a kink have no `M3` in this operation, so they get no bound. A fast number with no bound is the old intraday risk, not this one.
- **Large moves.** At +5% the error is 2,005 on a P&L of 181,103, about 1.1%. The bound grows with the cube of the move: an intraday stress needs full revaluation.

## Common mistakes

- **Netting the bounds.** Two positions whose remainders happen to cancel today may not tomorrow; the bound adds absolute values.
- **Evaluating `M3` at the start point.** For a falling yield the third derivative is larger at the end of the segment; taking it at `y` understates the bound for negative shifts.

## What you just did

You computed delta-gamma estimates and their Taylor bounds for four shifts and a two-position book, compared each with exact revaluation, and saw that the true error uses most of the bound.

## Try next

- Halve the shift of `idr_k-0001` to +0.5% and predict the bound before you run it (a factor of 8 smaller).

## References and further reading

- This project: `specifications/06-risk/intraday-risk-bounds.md`, `specifications/stage-k-rulings-w1.md`; bump-and-revalue risk in [Tutorial 5](tutorial-5-risk.md).
- T. M. Apostol, *Calculus*, vol. 1, 2nd ed., Wiley, 1967, section 7.7 (cited in the spec for Taylor's formula with remainder; not free; recalled).
