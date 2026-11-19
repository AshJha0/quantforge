# Tutorial 55: why a Bermudan ladder lost second order, and how it got it back

<!-- tutorial:only python -->

The plain idea: a sensitivity ladder is the derivative of a price with respect to each curve node and model parameter. If the pricing scheme is second order, halving the grid should cut the ladder's error by four, every time. In the first stage K build it did not: some entries shrank irregularly, changed sign, or shrank only by two. Two separate faults caused it, one in time and one in space. This tutorial shows how the fault was seen (an order test on three grids), what each cause was, what the fixed method does, and what is still restricted.

You will run the order test on recorded ladder values from before and after the fix, and work the new exercise smoothing by hand on its three-node example. Budget 15 minutes.

<p class="note">Stage K. The method <code>CN_RANNACHER_SMOOTHED</code> of <code>rates.shortrate.bermudan_ladder</code> and <code>rates.shortrate.bermudan_swaption</code> is on the integration branch <code>k-r1</code> in all four builds (merged 2026-11-19; not in a tag) (spec <code>specifications/06-risk/bermudan-ladder-k8.md</code> 0.2.0, PROPOSED; rulings KR-8, KR-9, KR-15, KR-16, KR-18, KR-19, KR-110). Acceptance 1 to 3 pass in all four builds (<code>oracle/K8_ACCEPTANCE_W2.json</code>, <code>oracle/K8_ACCEPTANCE_PORTS.json</code>); outside share 7 of 7 by blind re-derivation (<code>program/STAGE_K_BLIND_K8.md</code>). <strong>The R6 use restriction is lifted for <code>CN_RANNACHER_SMOOTHED</code> only (ruling KR-110, 2026-11-19); it stays for the default method, which is unchanged (<code>G18_IMPLICIT</code>).</strong> The ladder row at 0.4986 years is not judged (owner decision 2026-11-19; <code>program/K8_ROW0_FINDING.md</code>: no bug, its true value is zero). Step 1 uses the standard library on recorded values; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. **Observed order** `p` from values `f(h), f(h/2), f(h/4)` on three grids is `log2((f1 - f2)/(f2 - f3))`; a second-order scheme gives about 2. **Richardson extrapolation** uses that to estimate the limit, `(2^p f3 - f2)/(2^p - 1)`, and is only safe when the differences shrink regularly. A grid is written `nx/steps per year`; the default is 201/100. **Rannacher start-up** replaces the first Crank-Nicolson steps after a kink by implicit half steps, which damp the high-frequency error Crank-Nicolson leaves.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: the order test before and after, and the smoothing by hand

```python
# K-8: the Richardson order check (num.richardson.check, KR-9) on recorded ladder values, and the smoothing
# kernel of CN_RANNACHER_SMOOTHED on its worked example, restated with the standard library.
import math
from fractions import Fraction as F


def richardson(f1, f2, f3, ratio=2, assumed=2):
    d1, d2 = f1 - f2, f2 - f3
    if d1 == 0 or d2 == 0 or (d1 > 0) != (d2 > 0):
        return "NON_MONOTONE", None
    p = math.log(d1 / d2) / math.log(ratio)
    return ("OK" if abs(p - assumed) <= 0.5 else "ORDER_MISMATCH"), p


# First definition (spec 0.1.0), case aadladder_g-0001, row 1 (curve node 0.4986 y), time-only refinement:
# K8_DIAGNOSIS.md section 3(A). The model derivative of this row is exactly 0.
status, p = richardson(-337.0, -104.9, 11.1)
print(f"first definition, row 1: {status} observed order {p:.2f} (values -337.0, -104.9, 11.1; true value 0)")

# Second run (KR-15), case aadladder_g-0001 at 201/100, 401/200, 801/400: oracle/K8_ACCEPTANCE_W2.json.
ROWS = {
    "price": (22737.43110152093, 22752.349043012942, 22756.086431321997, 22757.33103779482),
    "row 2 (node 1y)": (222756.97927658106, 223121.2511211628, 223212.47798442983, 223243.7217182066),
    "row 3 (node 2y)": (157306.48127138885, 157148.28814080716, 157108.80897095392, 157091.56174054227),
    "row 5 (node 5.0027y)": (-234107.76717224217, -234182.02821738692, -234200.7306873398, -234209.64522075362),
    "row 11 (d/da)": (-53342.23688107165, -53437.321253233575, -53461.17960657085, -53464.798658751526),
}
for name, (f1, f2, f3, ref) in ROWS.items():
    status, p = richardson(f1, f2, f3)
    print(f"{name:<21} {status} order {p:.3f}  default grid against QuantLib reference {100 * abs(f1 / ref - 1):.3f}%")
print("row 1 (node 0.4986y): 0.0 on all three grids, skipped by the all-zero-row rule (owner decision 2026-11-19)")


def m(p, q):  # M(p, q) = int_0^1 (1 - u) max(p + (q - p) u, 0) du, the spec's closed form
    if p >= 0 and q >= 0:
        return p / 3 + q / 6
    if p > 0 > q:
        t = p * p / (2 * (p - q))
        return t - t * (p / (p - q)) / 3
    if p < 0 < q:
        r = q / (q - p)
        return q * r * r / 6
    return F(0)


f = [F(-1), F(0), F(1)]
ext = [2 * f[0] - f[1]] + f + [2 * f[2] - f[1]]  # linear extension at both ends
h = [m(ext[i + 1], ext[i]) + m(ext[i + 1], ext[i + 2]) for i in range(3)]
s1 = h[1] - (h[0] - 2 * h[1] + h[2]) / 6
print(f"smoothing f = (-1, 0, 1): h = {[str(x) for x in h]}, S_1 = {s1}; pointwise max 0, cell average 1/8")
```

Output (CI checks that Step 2 prints these lines):

<!-- tutorial:expect -->
```text
first definition, row 1: ORDER_MISMATCH observed order 1.00 (values -337.0, -104.9, 11.1; true value 0)
price                 OK order 1.997  default grid against QuantLib reference 0.087%
row 2 (node 1y)       OK order 1.997  default grid against QuantLib reference 0.218%
row 3 (node 2y)       OK order 2.003  default grid against QuantLib reference 0.137%
row 5 (node 5.0027y)  OK order 1.989  default grid against QuantLib reference 0.043%
row 11 (d/da)         OK order 1.995  default grid against QuantLib reference 0.229%
row 1 (node 0.4986y): 0.0 on all three grids, skipped by the all-zero-row rule (owner decision 2026-11-19)
smoothing f = (-1, 0, 1): h = ['0', '1/6', '1'], S_1 = 1/18; pointwise max 0, cell average 1/8
```

### Reading the numbers

- **The symptom.** The first definition gave row 1 (the curve node at 0.4986 years) the values -337.0, -104.9 and 11.1 on three time grids, where the model's derivative is exactly 0. The differences shrink by two, not four: first order, and acceptance 3 fails. Eighteen entries failed in all, with mixed signs that changed between grids (measured, `program/K8_DIAGNOSIS.md` section 1, branch `k-k8`). Mixed, grid-dependent signs point to an error that depends on where something sits in the grid, not to a slow smooth error.
- **After the fix.** On case `aadladder_g-0001` the price and every judged ladder entry show observed order 1.99 to 2.00, status `OK`. Over the three cases, 24 entries (3 prices, 21 ladder entries) are all `OK` with orders 1.84 to 2.15 (measured, `oracle/K8_ACCEPTANCE_W2.json`).
- **Size at the default grid.** At 201/100 each entry above is within 0.23% of the QuantLib bump reference; the worst of the 21 judged entries over all three cases is 0.40% (case 0002 row 2), against the 1% limit of acceptance 2.
- **The zero row.** Row 1 is now exactly 0.0 on every grid, because the fix takes the curve out of the time stepping. An entry exactly zero on all three grids is not put through the order test; that rule existed before the run, and the owner decided on 2026-11-19 that the row stays skipped under it.
- **The smoothing.** With `f = U - E = (-1, 0, 1)` the new exercise step gives 1/18 at the middle node, where the pointwise `max(U, E)` gives 0 and the first definition's cell average gives 1/8 (the spec's worked example).

### Why second order was lost: two causes

**(A) Time: a curve node inside a time step.** The Hull-White drift contains the instantaneous forward rate, which for log-linear discount factors jumps at every curve node. The first definition sampled it at step ends. Nodes at 1, 2 and 3 years are time-grid points; the node at 0.4986 years is not, so the one step holding it used the wrong mix of the two forwards. The price barely notices, but the derivative of the jump with respect to the two neighbouring discount factors is of order one over the node spacing, so rows 1 and 2 got an error of first order in `dt` with opposite signs. Measured on a time-only refinement: row 1 order 1.00, row 2 differences +117.7 and +58.9, half of row 1's and opposite (`K8_DIAGNOSIS.md` 3(A)).

*Fix (KR-15 a):* solve for `U = V exp(-int_0^t alpha)` instead of `V`. The curve term commutes with the rest of the operator, so the change is exact; the operator becomes the same at every step and the curve appears only in the exercise value at exercise and payment dates. Measured after the change: order 2.00 on every row in the same study, row 1 exactly 0.

**(B) Space: the smoothing depended on where the exercise boundary sits in its cell.** A discount-factor entry is, by the envelope property, an exercise probability times a discount factor, so it is the derivative of something that starts as a step at the exercise boundary. If the price error has a part that depends on the boundary's position inside its grid cell, differentiating it with respect to an input that moves the boundary divides that part by `dx`. A price error of size `dx^3 g(position)` becomes a ladder error of size `dx^2 g'`: the same order as the regular error, but with a coefficient that changes from grid to grid, which is exactly what the order test sees. The first definition's cell average is a first-order smoothing operator and leaves such a `dx^3` term (derived in the lane, with Pooley, Vetzal and Forsyth 2003 sections 2.2 and 2.4 read, and Kreiss, Thomee and Widlund 1970 recalled, not read). Measured on a space-only refinement with cause (A) removed: the first definition's row 2 error went -1064, -997, -379, -223, -158 and -63 on 101 to 601 nodes, while the price on the same grids was clean second order. Scaled by the square of the grid ratio, the hat smoothing without the end correction still swung between -392 and -546; with the end correction it stayed between -454 and -483, the slow drift being the error of the comparison grid itself (`K8_DIAGNOSIS.md` 3(B)).

*Fix (KR-15 b):* weight the `max` with the hat function, `M(p, q) = int_0^1 (1 - u) max(p + (q - p) u, 0) du`, which is a second-order smoothing operator; subtract an end correction `rho (1 - rho)(2 rho - 1)/12` times the mean second difference in the cell where `f` changes sign (derived in the lane, not taken from a paper); and apply the stencil `1 - delta^2/6`, so that away from the boundary the result is the pointwise `max`.

Candidates checked and not the cause (measured or inferred, `K8_DIAGNOSIS.md`): a missing Rannacher start-up (already present; going from two to four implicit half steps changed the space-only study by less than 1 in 2e5; four are adopted on the analysis of Giles and Carter 2006, read), exercise dates off the time grid (they are knots), the boundary conditions (every row is second order after the fix), and the tangent through the `max` (the ladder equals its own Richardson bumps to 1e-8).

### The formal statement, checked against the spec

From `specifications/06-risk/bermudan-ladder-k8.md` 0.2.0 (PROPOSED; read 2026-11-19).

- Scheme: `U(t, x) = V(t, x) D(t)` with `D(t) = P(0, t) exp(-c2 I(t))`; `U_t = A U` with a time-independent operator; Crank-Nicolson steps, the first two in each interval replaced by two implicit half steps each; at each exercise date `U_i = Ehat_i + S_i` with the hat-weighted, end-corrected, stencil-filtered smoothing `S`. The ladder is the exact derivative of the discrete scheme (`aad-core.md`), the grid included.
- `num.richardson.check` (KR-9): status `OK` iff the two differences have the same sign and `|observed - assumed| <= 0.5`; Richardson is used only through it, never unguarded. Goldens `rich_k-0001` to `0008`.
- Acceptance, fixed before any run: (1) the QuantLib `FdHullWhiteSwaptionEngine` bump reference at two bump sizes agrees within 0.1%, and the method at 801/400 and 1601/800 agrees within 0.2%; (2) at 201/100 every judged entry within 1% of the reference; (3) observed order on 201/401/801 in [1.5, 2.5] with status `OK` on every entry; (4) the R6 restriction is lifted only for this method and only after 1 to 3 pass; (5) the ladder equals its own Richardson bumps to 1e-8.
- Results (`oracle/K8_ACCEPTANCE_W2.json`, measured 2026-11-19): (1) PASS, worst bump gap 0.016% (reference grid 8,000/3,201 by KR-16, set before the judged run), method grids 0.019%; (2) PASS, worst 0.40%; (3) PASS, 24 entries. Java: acceptance 3 PASS, values equal to the Python record to 3.8e-14 of the row scale. The first run (`oracle/K8_ACCEPTANCE_W1.json`) is kept unchanged as a recorded miss.

### What is still restricted

- **The R6 use restriction is lifted for `CN_RANNACHER_SMOOTHED` only.** Acceptance 4 was met on the integration branch on 2026-11-19 (ruling KR-110): `specifications/06-risk/aad-core.md` and `docs/model-inventory.md` (entry MG-6) keep the restriction for the default `G18_IMPLICIT`, which is still not for hedging at the default grid.
- **The 0.4986-year row is not judged.** It is 0.0 on all three grids, so the all-zero-row rule skips it (owner decision 2026-11-19). `program/K8_ROW0_FINDING.md` found no bug: the true value is zero, and QuantLib's -14.27 there (`oracle/K8_ACCEPTANCE_W2.json` reference) is the time-stepping error of QuantLib's finite-difference engine.
- **The default method is unchanged.** Without a `method` input the operations run the G-18 scheme bit for bit; `CN_RANNACHER_SMOOTHED` must be asked for.
- **Four languages.** All four builds carry the method; the C++ and Rust ports pass acceptance 3 with values within 3.85e-14 of the row scale of Python (`oracle/K8_ACCEPTANCE_PORTS.json`), and the `k8_k` goldens pass in every build through the conformance runner.
- **The end correction is the lane's own derivation**, supported by measurements and unit tests, not by an outside source.

## Step 2: through the library

This block calls the library on the goldens in `datasets/golden/stage_k/`. It was turned on at integration (2026-11-19) and printed the same lines as Step 1; CI now checks them. The smoothing has no operation of its own, so its last line stays a hand restatement.

<!-- tutorial:run python -->
```python
# The order test through num.richardson.check; k8_k-0001 (default grid, CN_RANNACHER_SMOOTHED) against its golden.
import json
from fractions import Fraction as F

from quantforge_core.cli.main import run_case


def call(op, inputs, case_id="t55"):
    return run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": op, "inputs": inputs}))


def richardson(f1, f2, f3):
    o = call("num.richardson.check", {"values": [f1, f2, f3], "ratio": 2.0, "assumed_order": 2.0})["outputs"]
    return o["status"], o["observed_order"]


status, p = richardson(-337.0, -104.9, 11.1)
print(f"first definition, row 1: {status} observed order {p:.2f} (values -337.0, -104.9, 11.1; true value 0)")
ROWS = {
    "price": (22737.43110152093, 22752.349043012942, 22756.086431321997, 22757.33103779482),
    "row 2 (node 1y)": (222756.97927658106, 223121.2511211628, 223212.47798442983, 223243.7217182066),
    "row 3 (node 2y)": (157306.48127138885, 157148.28814080716, 157108.80897095392, 157091.56174054227),
    "row 5 (node 5.0027y)": (-234107.76717224217, -234182.02821738692, -234200.7306873398, -234209.64522075362),
    "row 11 (d/da)": (-53342.23688107165, -53437.321253233575, -53461.17960657085, -53464.798658751526),
}
for name, (f1, f2, f3, ref) in ROWS.items():
    status, p = richardson(f1, f2, f3)
    print(f"{name:<21} {status} order {p:.3f}  default grid against QuantLib reference {100 * abs(f1 / ref - 1):.3f}%")
print("row 1 (node 0.4986y): 0.0 on all three grids, skipped by the all-zero-row rule (owner decision 2026-11-19)")

golden = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_k/k8_k.json", encoding="utf-8"))["cases"]}["k8_k-0001"]
out = call(golden["operation"], golden["inputs"], "k8_k-0001")["outputs"]
assert out.keys() == golden["expected"]["outputs"].keys()  # values are compared by the conformance runner at 1e-9 of the row scale


def m(p, q):
    if p >= 0 and q >= 0:
        return p / 3 + q / 6
    if p > 0 > q:
        t = p * p / (2 * (p - q))
        return t - t * (p / (p - q)) / 3
    if p < 0 < q:
        r = q / (q - p)
        return q * r * r / 6
    return F(0)


f = [F(-1), F(0), F(1)]
ext = [2 * f[0] - f[1]] + f + [2 * f[2] - f[1]]
h = [m(ext[i + 1], ext[i]) + m(ext[i + 1], ext[i + 2]) for i in range(3)]
s1 = h[1] - (h[0] - 2 * h[1] + h[2]) / 6
print(f"smoothing f = (-1, 0, 1): h = {[str(x) for x in h]}, S_1 = {s1}; pointwise max 0, cell average 1/8")
```

## For practitioners

- **An order test catches what a size test misses.** The first definition was already within 0.39% at the default grid (acceptance 2 would have passed); only the order test showed that its errors were not under control. A ladder whose error changes sign from grid to grid cannot be extrapolated, and a hedge built on it moves when someone changes the grid.
- **Do not hedge from the default G-18 ladder.** Until the restriction is lifted in an integration commit, `docs/model-inventory.md` MG-6 governs.
- **Exact zeros are part of the contract.** A node the price does not depend on must give 0.0, not 1e-13. The QuantLib bump reference itself shows -14 on row 1, below the 1e-3 floor of acceptance 2 but a reminder that a bump reference has artefacts too.

## Common mistakes

- **Extrapolating without the guard.** Richardson on a `NON_MONOTONE` triple produces a confident wrong number; `rich_k-0004` is such a triple from the G-18 ladder.
- **Blaming the start-up steps first.** Adding implicit half steps was the obvious fix and changed almost nothing here; the measurements pointed elsewhere.

## What you just did

You ran the order test that exposed the fault, read its two causes and their fixes, checked the second run's orders and default-grid gaps from the recorded values, worked the new smoothing on three nodes, and listed what remains restricted.

## Try next

- Compute the observed order of row 12 (`d/dsigma`) for case `aadladder_g-0001` from `oracle/K8_ACCEPTANCE_W2.json`; the record gives 1.997.

## References and further reading

- This project: `specifications/06-risk/bermudan-ladder-k8.md`, `program/K8_DIAGNOSIS.md`, `program/K8_PORT_NOTE.md`, `oracle/K8_ACCEPTANCE_W1.json` and `W2.json`; the G-18 scheme in [`short-rate-models.md`](../../specifications/04-pricing/short-rate-models.md) and the ladder in [Tutorial 15](tutorial-15-advanced-risk.md).
Bibliographic details below are recalled; the reading status is the K-8 lane's.

- D. M. Pooley, K. R. Vetzal and P. A. Forsyth, "Convergence remedies for non-smooth payoffs in option pricing", *Journal of Computational Finance* 6(4), 2003, sections 2.2 and 2.4 (read by the K-8 lane, 2026-11-19).
- M. B. Giles and R. Carter, "Convergence analysis of Crank-Nicolson and Rannacher time-marching", *Journal of Computational Finance* 9(4), 2006, section 1 and Table 1 (read by the K-8 lane, 2026-11-19).
- R. Rannacher, "Finite element solution of diffusion problems with irregular data", *Numerische Mathematik* 43, 1984 (not free; recalled). H.-O. Kreiss, V. Thomee and O. Widlund, "Smoothing of initial data and rates of convergence for parabolic difference equations", *Communications on Pure and Applied Mathematics* 23, 1970 (not free; recalled).
