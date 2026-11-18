# curve_fits Python survivors: row-by-row re-check (2026-11-18)

Scope: the 9 survivors of `curve_fits` (run 44362557841, 31/40, Wilson LB 62.5%), recorded as
unsigned rows in `equivalents-python.md`. Diffs come from mutmut 3.8.1's own mutant source
(`mutate_file_contents` on `python/quantforge_core/curve_fits.py`). Contract sources: the spec
`specifications/03-calibration/curve-fits.md`, goldens `datasets/golden/stage_d/fits_d.json`, and
COOKBOOK.md line 74 ("The message text is not part of the contract and differs by language; the
code is."). Nothing is signed here and `skip-equivalents.json` is unchanged.

Result: no genuine kill test exists for any of the 9, so no test file was added and the score
stays 31/40 (re-score run listed at the end). Verdicts: 6 proven equivalent, 3 not testable
through the contract.

## Per-row verdicts

### 1. `x_smooth__mutmut_104` (line 34): proven equivalent

```
-  zip(w, rows, strict=True)
+  zip(w, rows, strict=False)
```

`strict` changes behaviour only when the iterables differ in length. `rows` has one entry per
maturity (line 32) and line 22 raises `E_INPUT` unless `len(w) == len(maturities)`. So both have
length `len(maturities)` on every call that reaches line 34.

### 2. `x_smooth__mutmut_133` (line 43): proven equivalent

```
-  zip(w, rows, zero_rates, strict=True)
+  zip(w, rows, zero_rates, strict=None)
```

`strict=None` is accepted by `zip` and is falsy (checked: `list(zip([1, 2], [3], strict=None))`
is `[(1, 3)]`). Line 22 makes `w`, `maturities` and `zero_rates` equal in length, and `rows`
follows `maturities`, so the lengths are always equal.

### 3. `x_smooth__mutmut_137` (line 43): proven equivalent

```
-  zip(w, rows, zero_rates, strict=True)
+  zip(w, rows, zero_rates, )
```

Same proof as row 2.

### 4. `x_robust__mutmut_12` (line 68): not testable through the contract

```
-  raise QfError("E_INPUT", "need at least 3 points of equal length")
+  raise QfError("E_INPUT", "NEED AT LEAST 3 POINTS OF EQUAL LENGTH")
```

Only the message changes. The spec defines the code (`E_INPUT`) and no message; COOKBOOK.md says
message text is not part of the contract. A test of the wording would pin an implementation
detail. The code is already asserted by existing tests.

### 5. `x_robust__mutmut_28` (line 70): not testable through the contract

```
-  raise QfError("E_DOMAIN", "tau, delta and maturities must be positive")
+  raise QfError("E_DOMAIN", "XXtau, delta and maturities must be positiveXX")
```

Same reasoning as row 4 (`E_DOMAIN` is the contract).

### 6. `x_robust__mutmut_56` (line 78): proven equivalent

```
-  zip(w, xs, strict=True)
+  zip(w, xs, )
```

`weighted` is called with `w = [1.0] * len(ys)` (line 96), a list built from `new` (line 106),
or from `r` (line 118). `new` and `r` are one per entry of `residuals(...)`, which is one per
`zip(xs, ys)` pair. `xs` and `ys` are one per maturity and line 67 makes `maturities` and
`zero_rates` equal in length. So `len(w) == len(xs)` on every call.

### 7. `x_robust__mutmut_97` (line 92): proven equivalent

```
-  for x, y in zip(xs, ys, strict=True)
+  for x, y in zip(xs, ys, strict=None)
```

`len(xs) == len(maturities) == len(zero_rates) == len(ys)` by lines 67, 73 and 74.

### 8. `x_robust__mutmut_114` (line 98): not testable without pinning the cap

```
-  for _ in range(500):
+  for _ in range(501):
```

Proof that the two differ on exactly one kind of input. In a pass where the exact candidate is
accepted (line 113), `signs == new` and `new` equals the sign pattern of `residuals(exact)`, so
the next pass recomputes that same pattern and breaks. In a pass where it is rejected, line 119
sets `signs = None`, so the next pass cannot break. So the loop breaks at pass `j + 1`, where `j`
(0-based) is the first accepted pass. The original returns iff `j <= 498`; the mutant returns iff
`j <= 499`. They differ only when the first acceptance is at pass 499 exactly. In that case the
original raises `E_NO_CONVERGENCE` and the mutant returns a fit.

A test that kills this mutant would have to assert `E_NO_CONVERGENCE` for an input the method
would solve one pass later. The spec says "any convergent method may be used" and the problem is
convex with one minimum, so that assertion pins the cap and nothing the spec requires. The
opposite test (assert convergence) fails the original, not the mutant. Reaching the cap on purpose
does not help: for an input that never accepts, both forms raise.

Evidence (scratch script, 20,000 random valid inputs, 3-12 points, `delta` 1e-4 to 1e-2): the
first accepted pass was at most 1 for 92% of the inputs that returned and spread out to 491; 10 inputs hit the cap
and raised `E_NO_CONVERGENCE`. The 8 golden `robust` cases accept by pass 1. See
"Findings" below: the cap being reached on valid input is a defect in its own right.

### 9. `x_robust__mutmut_180` (line 119): proven equivalent

```
-  signs = None
+  signs = ""
```

`signs` is read only in `new == signs` (line 101). `new` is a list, and a list never compares
equal to `None` or to `""`. Every other use of `signs` is an assignment. Type checkers would object
to `""`, but no behaviour differs.

## Rows the owner may consider signing

- Equivalent (proof above): `x_smooth__mutmut_104`, `_133`, `_137`; `x_robust__mutmut_56`, `_97`,
  `_180`. If all six are signed into `skip-equivalents.json`, the sample shrinks and 31/34 is
  91.2% (Wilson LB about 77%), above the gate.
- Accepted (not equivalent; differs only in a part the contract does not fix):
  `x_robust__mutmut_12`, `_28` (message text, COOKBOOK.md line 74); `x_robust__mutmut_114`
  (iteration cap; differs only when the first accepted pass is exactly 499).

## Findings outside the mutation score (not fixed here)

- `robust` raised `E_NO_CONVERGENCE` on 10 of 20,000 random valid inputs, for example
  `maturities [7.6748018928508674, 17.075381468763926, 19.309061702000577]`,
  `zero_rates [0.01460379783209027, -0.01450581258617124, 0.02927126312117953]`,
  `tau 0.4265110445087423`, `delta 0.005`. The spec defines no such error for `robust` and says the
  problem is convex with one minimum.
- `robust` raised `E_SINGULAR` on 159 of the same inputs (from `lu_solve`, mostly small `tau` with
  long maturities, where the basis columns are nearly dependent). The spec's check list for
  `robust` has no `E_SINGULAR`; the line 71 check for three distinct maturities is in the code
  only.

Both are worth a spec question and a fix in a later round; they are not mutation-score issues.

## Re-score

Tests unchanged for `curve_fits`, so the seeded sample and verdicts are the same as run
44362557841. Re-score run 44383318047, read from the job log:

| Module | Run | Killed (40) | Gate |
|---|---|---|---|
| curve_fits | 44383318047 | 31/40 (77.5%, Wilson LB 62.5%), seed 355377703 | below gate (same 9 survivors) |
