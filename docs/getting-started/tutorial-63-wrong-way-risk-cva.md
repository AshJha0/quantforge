# Tutorial 63: wrong-way risk in CVA, and the root that once returned zero

<!-- tutorial:only python -->

The plain idea: ordinary CVA assumes a counterparty is as likely to default when the bank is owed a lot as when it is owed nothing. Wrong-way risk is when that fails: the counterparty defaults more often exactly on the paths where the exposure is high. The Hull-White model makes the default intensity on each simulated path grow with that path's exposure, then shifts a level `a(t)` so that the average survival still matches the counterparty's credit curve. One parameter, `b`, sets the strength: positive is wrong way, negative right way, zero independent.

You will implement the model with the standard library (one bisection per time bucket), sweep `b` on the golden paths, and check the closed form that ruling KR-257 derived for paths with identical exposure, including a case where the solver before KR-257 returned an unconverged root and a CVA of 0. Budget 10 minutes.

<p class="note">Stage G operation <code>xva.wwr.cva_hw</code> (ruling G-44, spec <code>specifications/06-risk/xva-framework.md</code> 1.0.0), in all four builds since v0.7.0. Its root finder was fixed by ruling KR-257 (<code>specifications/stage-k-rulings-wwr.md</code>, confirmed 2026-11-20, merged to <code>main</code>). The paths are four hand-written paths from golden suite <code>wwr_g</code>, not a simulation. Outside check: none; the spec states the operation as formulas on given inputs (G-40). Step 1 uses the standard library; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. `V_p(t_i)` is the exposure on path `p` at the end of bucket `i`; `S_p(t)` the survival probability along path `p`; `h` the counterparty's flat hazard rate from its credit curve, so the target survival is `e^(-h t)`; `R` the recovery rate; `D_i` the discount factor.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: the model by hand

```python
# Hull-White wrong-way-risk CVA (G-44, KR-257) restated with the standard library: bisection for each a_i.
import math

TIMES = [0.25, 0.5, 0.75, 1.0]
PATHS = [[3.0, 5.0, 2.0, -1.0], [-2.0, -4.0, -6.0, -3.0], [1.0, 6.0, 9.0, 4.0], [0.5, -1.0, 2.5, 7.0]]  # wwr_g inputs
DF = [0.995, 0.99, 0.985, 0.98]


def wwr_cva(times, paths, df, h, recovery, b):
    surv, cva, a_all, prev = [1.0] * len(paths), 0.0, [], 0.0
    for i, t in enumerate(times):
        dt, target = t - prev, math.exp(-h * t)
        bv = [b * p[i] for p in paths]

        def mean_survival(a):  # decreasing in a
            return sum(s * math.exp(-math.exp(a + x) * dt) for s, x in zip(surv, bv)) / len(paths)

        lo, hi = math.log(h) - max(bv) - 1, math.log(h) - min(bv) + 1  # the KR-257 bracket
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if mean_survival(mid) > target else (lo, mid)
        a = (lo + hi) / 2
        new = [s * math.exp(-math.exp(a + x) * dt) for s, x in zip(surv, bv)]
        cva += df[i] * sum(max(p[i], 0.0) * (s0 - s1) for p, s0, s1 in zip(paths, surv, new)) / len(paths)
        surv, prev = new, t
        a_all.append(a)
    return (1 - recovery) * cva, a_all


for b in (-0.2, 0.0, 0.1, 0.3, 0.5):
    cva, a = wwr_cva(TIMES, PATHS, DF, 0.03, 0.4, b)
    print(f"b = {b:+.1f}: CVA {cva:.6f}, a_1 {a[0]:.6f}, a_4 {a[3]:.6f}")

for v in (10.0, 600.0):  # identical exposure on every path: closed form a_i = ln h - b V
    cva, a = wwr_cva([1.0, 2.0], [[v, v], [v, v]], [0.97, 0.94], 0.01, 0.4, 1.0)
    closed = 0.6 * v * (0.97 * (1 - math.exp(-0.01)) + 0.94 * (math.exp(-0.01) - math.exp(-0.02)))
    print(f"identical paths, V = {v:g}, b = 1: a {a[0]:.6f} (ln h - bV = {math.log(0.01) - v:.6f}), "
          f"CVA {cva:.6f} (closed form {closed:.6f})")
```

Output (CI checks that Step 2 prints these lines; measured 2026-11-21 on branch `k-v1-docs-a`, Python 3.15.2 through `uv`, local laptop, not the acceptance machine):

<!-- tutorial:expect -->
```text
b = -0.2: CVA 0.015569, a_1 -3.445299, a_4 -3.429922
b = +0.0: CVA 0.043628, a_1 -3.506558, a_4 -3.506558
b = +0.1: CVA 0.061148, a_1 -3.584569, a_4 -3.758147
b = +0.3: CVA 0.086487, a_1 -3.827722, a_4 -4.653972
b = +0.5: CVA 0.097651, a_1 -4.169773, a_4 -5.842943
identical paths, V = 10, b = 1: a -14.605170 (ln h - bV = -14.605170), CVA 0.113471 (closed form 0.113471)
identical paths, V = 600, b = 1: a -604.605170 (ln h - bV = -604.605170), CVA 6.808231 (closed form 6.808231)
```

### Reading the numbers

- **Independent case.** At `b = 0` every path has the same intensity, so `a_i = ln 0.03 = -3.506558` in every bucket and the CVA, 0.043628, equals the independent CVA on the mean positive exposure `(1.125, 2.75, 3.375, 2.75)`: `0.6 x sum D_i EE_i (e^(-0.03 t_(i-1)) - e^(-0.03 t_i))`.
- **The sweep.** CVA rises with `b`: 0.0156 at -0.2 (right way), 0.0436 at 0, 0.0611 at 0.1, 0.0865 at 0.3, 0.0977 at 0.5. The goldens `wwr_g-0001` to `-0004` pin the first four; 0.5 is not a golden. The level `a` falls as `b` grows: the recalibration takes intensity away from the low-exposure paths and gives it to the high ones, keeping the average survival on the credit curve. The CVA flattens at larger `b` because most of the default probability is already on the high-exposure paths.
- **The closed form.** With the same exposure `V` on every path, every path has the same survival, so the bucket equation reduces to `exp(a_i + b V) = h`, that is `a_i = ln h - b V`, and the CVA is the independent one (KR-257, derivation in the ruling). With `h = 0.01`, `b = 1`, `V = 10`: `a = -14.605170`, CVA 0.113471 (golden `wwr_g-0007`). With `V = 600`, `a = -604.605170` and CVA 6.808231 (not a golden; 60 times the `V = 10` figure, because `a` absorbs `b V` and the CVA is then linear in `V`).
- **What KR-257 fixed.** Before it, the solver started Newton's method at `a = ln h` with no finite bracket. For large `|b V|` the function is almost flat there, so the first step jumped far away and the bisection fallback could not recover: for the `V = 10` case the Python and Rust builds returned `a` near -2.6e33 and CVA 0 without an error (measured by the lane, `specifications/stage-k-rulings-wwr.md`). The fix brackets each root in `[ln h - max_p b V_p - 1, ln h - min_p b V_p + 1]`, which Step 1 also uses, and refuses `|b V| > 700` with `E_DOMAIN` because `e^(bV)` would overflow.

### The formal statement, checked against the spec

From `specifications/06-risk/xva-framework.md` 1.0.0, section `xva.wwr.cva_hw` (read 2026-11-21), after J. Hull and A. White, "CVA and wrong-way risk", *Financial Analysts Journal* 68(5), 2012 (recalled through the spec).

- Intensity on path `p` in bucket `i`: `exp(a_i + b V_p(t_i))`.
- Calibration: `a_i` solves `mean_p S_p(t_i) = e^(-h t_i)`, with `S_p(t_i) = S_p(t_(i-1)) exp(-exp(a_i + b V_p(t_i)) dt_i)`; the left side is strictly decreasing in `a_i`, so the root is unique.
- `CVA = (1 - R) sum_i D_i mean_p[max(V_p(t_i), 0) (S_p(t_(i-1)) - S_p(t_i))]`.
- KR-257: safeguarded Newton on the bracket above, to `1e-15 max(1, |a|)`, in a cancellation-free form of the bucket equation; `|b V| <= 700` else `E_DOMAIN`; tolerance class `root_finding` for the goldens (1e-9 absolute plus 1e-12 relative). Step 1 uses plain bisection, which reaches the same six printed decimals.

## Step 2: the same through the library

<!-- tutorial:run python -->
```python
# The same sweep and the KR-257 closed-form cases through xva.wwr.cva_hw.
import json
import math

from quantforge_core.cli.main import run_case


def call(times, paths, df, h, recovery, b):
    inputs = {"times": times, "values": paths, "discount_factors": df, "hazard_rate": h, "recovery": recovery,
              "wwr_b": b}
    o = run_case(json.dumps({"schema_version": "1.0", "case_id": "t63", "operation": "xva.wwr.cva_hw",
                             "inputs": inputs}))["outputs"]
    return o["cva"], o["a"]


TIMES = [0.25, 0.5, 0.75, 1.0]
PATHS = [[3.0, 5.0, 2.0, -1.0], [-2.0, -4.0, -6.0, -3.0], [1.0, 6.0, 9.0, 4.0], [0.5, -1.0, 2.5, 7.0]]  # wwr_g inputs
DF = [0.995, 0.99, 0.985, 0.98]
for b in (-0.2, 0.0, 0.1, 0.3, 0.5):
    cva, a = call(TIMES, PATHS, DF, 0.03, 0.4, b)
    print(f"b = {b:+.1f}: CVA {cva:.6f}, a_1 {a[0]:.6f}, a_4 {a[3]:.6f}")

for v in (10.0, 600.0):
    cva, a = call([1.0, 2.0], [[v, v], [v, v]], [0.97, 0.94], 0.01, 0.4, 1.0)
    closed = 0.6 * v * (0.97 * (1 - math.exp(-0.01)) + 0.94 * (math.exp(-0.01) - math.exp(-0.02)))
    print(f"identical paths, V = {v:g}, b = 1: a {a[0]:.6f} (ln h - bV = {math.log(0.01) - v:.6f}), "
          f"CVA {cva:.6f} (closed form {closed:.6f})")
```

## For practitioners

- **`b` is a modelling choice, not an output.** The operation takes it as an input; calibrating it (from the co-movement of the counterparty's spread with the exposure drivers) is outside the library.
- **Check a root finder on a case with a closed form.** Identical paths reduce the model to `a = ln h - b V`; a solver that fails there fails silently elsewhere, as the pre-KR-257 builds did.
- **Collateral and netting come first.** Apply them to the paths before this step ([Tutorial 7](tutorial-7-counterparty.md)); wrong-way risk scales the exposure you actually have.

## Common mistakes

- **Scaling the hazard without recalibrating.** Multiplying every path's intensity by `exp(b V)` without solving for `a` changes the counterparty's implied credit curve; the recalibration is what keeps the model consistent with the market.
- **Reading CVA 0 as no risk.** A zero CVA with positive exposure and positive hazard is a sign of a failed computation, as the KR-257 finding showed.

## What you just did

You implemented the Hull-White wrong-way-risk CVA with one bisection per bucket, swept the dependence parameter from right way to wrong way, and confirmed the KR-257 closed form, including a case that the solver before the fix got wrong.

## Try next

- Send the `V = 600` case with `V = 800`: the operation returns `E_DOMAIN` on `wwr_b` ([Cookbook](../../COOKBOOK.md#wrong-way-risk-cva-how-the-cva-moves-with-the-dependence-parameter-goldens-wwr_g-0001-to-wwr_g-0004-wwr_g-0007)).

## References and further reading

- This project: `specifications/06-risk/xva-framework.md`, `specifications/stage-k-rulings-wwr.md`, goldens `datasets/golden/stage_g/wwr_g.json`, [Tutorial 7](tutorial-7-counterparty.md).
- J. Hull and A. White, "CVA and wrong-way risk", *Financial Analysts Journal* 68(5), 2012. <https://doi.org/10.2469/faj.v68.n5.6>
