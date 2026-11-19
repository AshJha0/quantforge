# K-8 porting note for the C++ and Rust lanes: `CN_RANNACHER_SMOOTHED` (spec 0.2.0, KR-15)

Lane K-8c, 2026-11-19. Reference builds: `python/quantforge_core/bermudan_k8.py` (the definition) and `java25/src/main/java/org/quantforge/pricing/BermudanK8.java` (a line-by-line port; read this one if your language has no array broadcasting). Spec: `specifications/06-risk/bermudan-ladder-k8.md`, section "Method". Why the method looks like this: `program/K8_DIAGNOSIS.md`.

## What to build

A new value `CN_RANNACHER_SMOOTHED` of the optional input `method` on `rates.shortrate.bermudan_swaption` and `rates.shortrate.bermudan_ladder`. Absent or `G18_IMPLICIT` stays the G-18 scheme bit for bit. Any other value is `E_SCHEMA`. The default method does not change in this lane and the R6 use restriction is not lifted here; the coordinator does both in the integration branch.

Outputs are the same fields as the G-18 method. The ladder is the exact derivative of the discrete scheme. Python and Java carry tangents forward (value plus one column per curve node, then `a`, then `sigma`); a reverse sweep is equally valid as long as it differentiates the same arithmetic, including the grid (`h`, `dx` and the nodes depend on `a` and `sigma`).

## The scheme, in the order the reference builds compute it

Notation: dual numbers `(value, tangents)`; `P` curve nodes; `expm1`, `exp`, `sqrt` applied to duals.

1. Curve: nodes `(0, t_1..t_P)`, logs `(0, ln DF_1..ln DF_P)`. `ln P(0, t)`: `j = min(bisect_right(nodes, t) - 1, P - 1)`, `w = (t - n_j)/(n_(j+1) - n_j)`, `logs_j + (logs_(j+1) - logs_j) * w`. There is **no forward-rate function** in this method. Do not port `alpha(t)`; if you find yourself needing it, something is wrong.
2. Grid: `g = -expm1(-2 t_m a)/(2a)`, `sx = sigma sqrt(g)`, `h = width sx`, `dx = 2h/(nx - 1)`, `x_i = -h + i dx` (all duals in `a`, `sigma`).
3. Operator rows for interior nodes `i = 1..nx-2`, constant in time: `diff = sigma^2 / (2 dx^2)`, `conv_i = a x_i / (2 dx)`, `lower_i = -(diff + conv_i)`, `upper_i = -(diff - conv_i)`, `diag_i = 2 diff + x_i`.
4. Implicit solve with weight `w`: rows `w lower`, `1 + w diag`, `w upper`; boundary substitution exactly as G-18 (`diag_first += 2 lower_first; upper_first -= lower_first; lower_last -= upper_last; diag_last += 2 upper_last`); Thomas elimination on the values, tangents by `M0 dy = dr - dM y0` with the same pivots; then `y_0 = 2y_1 - y_2`, `y_(nx-1) = 2y_(nx-2) - y_(nx-3)`.
5. Explicit part with weight `w`: `v_i - w (lower_i v_(i-1) + diag_i v_i + upper_i v_(i+1))`, summed in that order.
6. Scaled exercise value at `t` (spec step 3): `e1 = expm1(-a t)`, `e2 = expm1(-2 a t)`, `I = 2 e1/a - e2/(2a) + t`, `c2 = sigma^2/(2 a^2)`, `c4 = sigma^2/(4a)`, `lead = exp(lnP(0,t) - c2 I)`. For each payment `s > t` in order: `B = -expm1(-a (s - t))/a`, `drift = c2 (I + B e1^2) - c4 e2 B^2`, `Q_i = exp(lnP(0,s) - drift - B x_i)`, `fixed_i += tau Q_i` (`tau` = `s - t` for the first, then differences of payment times). Result `phi ((lead - Q_last,i) - K fixed_i)`.
7. Smoothing `S(U, Ehat)` (spec step 5), with `f = U - Ehat`:
   - `h_i = M(f_i, f_(i-1)) + M(f_i, f_(i+1))` in that order, with `f_(-1) = 2 f_0 - f_1`, `f_nx = 2 f_(nx-1) - f_(nx-2)`.
   - `M(p, q)`: `p >= 0 and q >= 0`: `p/3 + q/6`. `p > 0 and q < 0`: `d = p - q`, `t = p^2/(2d)`, `t - (t (p/d))/3`. `p < 0 and q > 0`: `r = q/(q - p)`, `(q r^2)/6`. Otherwise 0 (this includes `p = 0, q < 0` and `p < 0, q = 0`).
   - `d_i = (f_(i-1) - 2 f_i) + f_(i+1)` for interior `i`, 0 at both end nodes.
   - For `j = 0..nx-2` in increasing order, if `(f_j > 0 and f_(j+1) < 0) or (f_j < 0 and f_(j+1) > 0)` (strict, on the values): `pos` = the node with `f > 0`, `neg` the other; `rho = f_pos/(f_pos - f_neg)`; `rest = 1 - rho`; `g = (rho rest (2 rho - 1))/12`; `corr = g * (0.5 (d_j + d_(j+1)))`; `h_pos -= rest corr`; `h_neg -= rho corr`. The corrections accumulate in `h`; `d` is not updated.
   - `S_i = h_i - ((h_(i-1) - 2 h_i) + h_(i+1))/6` for interior `i`, `S_i = h_i` at both end nodes, using the corrected `h`.
   - Result `Ehat_i + S_i`.
8. Start: `U = S(0, Ehat(t_m))`. For each interval from the last to the first: `steps = max(1, ceil(steps_per_year (t_hi - t_lo)))` in binary64 exactly as G-18 (R5 L9), `half = (t_hi - t_lo)/steps/2`. For `j = steps-1` down to 0: if `j >= steps - 2`, two implicit solves with weight `half` on the interior of `U`; otherwise one implicit solve with weight `half` on the explicit part with weight `half`. Then, if `t_lo` is an exercise date (not 0), `U = S(U, Ehat(t_lo))`.
9. `price = notional * U[nx / 2].value`; `d/dDF_j = notional * tangent_j / DF_j`; `d/da`, `d/dsigma = notional * tangent`.

## Things that will bite

- **Divide, do not multiply by a reciprocal**: `/3`, `/6`, `/12` are divisions in both reference builds. `0.5 *` and `2 *` are multiplications.
- **Adding a constant to a dual touches the value only** (`1 - rho`, `2 rho - 1`, `1 + w diag`, `... + t` in `I`). A first draft of this lane added `t` to every tangent column and shifted the whole ladder by about 0.4%.
- **Exact zeros are part of the contract.** Curve nodes the price does not depend on (here the node at 0.4986 years and the four after the last payment) must come out as exactly `0.0`, not as 1e-13. They do if the tangent seeds are exact 0/1 and nothing but `ln P(0, t)` at exercise and payment times touches the curve. A reverse-mode port must check this explicitly (tests `curveNodesThePriceDoesNotDependOnGiveExactZeros`).
- **Error order.** Checks run in the order of the Java build: fields read (the `nx` and `steps_per_year` size limits apply there), unlisted `method` is `E_SCHEMA`, curve and model, `start_years`, payments, type, exercise schedule (`E_INPUT`), then the grid (`nx` odd and at least 5, `steps_per_year >= 1`: `E_INPUT`; `width > 0`: `E_DOMAIN`). Golden `k8_k-0013` has a bad exercise time and `width = 0` together and expects `E_INPUT`.
- Golden count: `datasets/golden/stage_k/k8_k.json` has 14 cases (7 values, 7 errors, 3 of them with two errors). A test that hard-codes golden counts needs the new number.
- C++: the names `h`, `d`, `g` and `rest` above are local; mind `-Wshadow` under clang.
- Cost: one ladder at 201/100 is about 500 time steps of 201 nodes times 13 columns; nothing here needs more than the G-18 ladder's memory.

## How to know the port is right

1. Goldens `k8_k` (values at 1e-9 of the row scale; the Java build is within 4e-14).
2. Small-grid parity rows in `BermudanK8Test.PYTHON_41_20` (three cases at 41/20, 1e-10 of the row scale).
3. The unit tests to mirror: worked example of the smoothing (`f = (-1, 0, 1)` gives `E`, 1/18, `V`); `M(p, q)` against a fine sum; pointwise `max` kept away from the crossing; exact zeros; time order 2 on every entry; scaled space error constant to 10% on non-nested grids; ladder against its own Richardson bumps at 1e-8.
4. Acceptance 3 with `QF_K8_ACCEPTANCE=1` against `oracle/K8_ACCEPTANCE_W2.json` (about 4 minutes in Python, under a minute in Java).

## Reported to the coordinator, outside this lane's files

- **Python G-18 path, two errors at once**: with a bad exercise time and `width = 0`, `rates.shortrate.bermudan_swaption` and `bermudan_ladder` without `method` return `E_DOMAIN` in Python (grid checked first, `shortrate.py` / the two ops files) and `E_INPUT` in Java. HR-66 says `E_INPUT`. The K-8 path gives `E_INPUT` in both builds. No stage G golden covers the combination.
- The conformance runner globs every golden file, so `k8_k` will fail for the C++ and Rust builds until they carry the method.
- `specifications/cli-contract.md` line on `method` still describes the K-8 scheme by its first definition's ruling only (KR-8); it should cite KR-15 and the suite `k8_k`.
- `oracle/K8_ACCEPTANCE_W1.json` (first run, a miss) is kept unchanged.
