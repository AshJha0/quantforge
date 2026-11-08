# Sobol sequence

Spec version 1.0.0. Status: Specified.

Sobol points fill the unit cube more evenly than random draws, so integrals often converge
faster. The sequence is deterministic: it is defined by direction numbers, and those are data.

## Data

`specifications/01-core/data/sobol-joe-kuo-d6-64.json` holds the first 64 dimensions of the Joe-Kuo
`new-joe-kuo-6.21201` table: for each dimension `d`, degree `s`, coefficient word `a`, and initial
numbers `m[1..s]`. Maximum dimension is 64. Licence: see `oracle/LICENCES.md`.

## Direction integers (32 bits)

Dimension 1: `v[k] = 1 << (32 - k)`, `k = 1..32`.

Other dimensions, for `k <= s`: `v[k] = m[k] << (32 - k)`. For `k > s`:

```
v[k] = v[k-s] ^ (v[k-s] >> s)
for j in 1..s-1:
    if bit (s-1-j) of a is set:  v[k] ^= v[k-j]
```

## Points

Gray-code construction. `x[d]` starts at 0, for point index 0, which is the origin. To go from index
`i` to `i+1`, let `c` be the position (from 1) of the lowest zero bit of `i`, then `x[d] ^= v_d[c]`.
The point is `x[d] * 2^-32`, exact in binary64.

Index 0 is never returned: the first point served is index 1, `(0.5, 0.5, ...)`, because the origin
maps to minus infinity under the inverse normal. There is no scrambling and no digital shift.

## Operation `core.sobol.points`

Inputs: `dimensions` (1 to 64), `count` (at least 1), optional `skip` (default 0: points thrown away
after index 0). Output: `points`, `count` arrays of `dimensions` reals. Indices used run
`skip+1 .. skip+count`.

Upper limits on `count` and `skip` are in `limits.md`. Other out-of-range values are `E_INPUT`.

## Acceptance

Exact (class `bit_exact`). Oracle: QuantLib `SobolRsg` with `JoeKuoD6`, and SciPy `qmc.Sobol`
unscrambled. The oracle's own bit code must match both, and did at generation time.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Sobol', I. M., "On the distribution of points in a cube and the approximate evaluation of integrals", *USSR Computational Mathematics and Mathematical Physics* 7(4), 1967, 86-112 (not opened)
- [S2] Joe, S. and Kuo, F. Y., "Constructing Sobol sequences with better two-dimensional projections", *SIAM Journal on Scientific Computing* 30(5), 2008, 2635-2654; direction numbers file `new-joe-kuo-6.21201` (opened 2026-11-07: UNSW direction-numbers page confirms the file and the paper reference)
- [S3] Glasserman, P., *Monte Carlo Methods in Financial Engineering*, Springer, 2003, chapter 5 (quasi-Monte Carlo, Gray-code construction) (not opened)
