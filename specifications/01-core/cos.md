# COS Fourier pricing

Spec version 1.0.0. Status: Specified.

The COS method (Fang and Oosterlee, 2008) prices a European option from the characteristic function of the
log price. It needs no density, and converges exponentially for smooth densities. The series is defined
exactly, so all languages agree closely.

## Operation `core.cos.european`

Inputs: `option` (`CALL`/`PUT`), `spot`, `strike`, `r`, `q`, `t`, `model`, `terms` `N` (at least 2), `truncation` `L` (> 0).
`model` is an object:
- `{"name": "BLACK_SCHOLES", "sigma": ...}`
- `{"name": "HESTON", "v0": ..., "kappa": ..., "theta": ..., "sigma": ..., "rho": ...}`

Output: `price`. Diagnostics: `a`, `b`.

Checks: `spot`, `strike`, `t`, `L`, `sigma`, `v0`, `kappa`, `theta` `<= 0`: `E_DOMAIN`. `|rho| >= 1`: `E_DOMAIN`. `N < 2`: `E_INPUT`.

**Characteristic function** of `ln(S_T/S_0)`:

Black-Scholes: `phi(u) = exp(i u (r - q - sigma^2/2) t - sigma^2 u^2 t / 2)`.

Heston, in the Albrecher form, which stays on the right branch of the complex log:

```
beta = kappa - rho sigma i u
d    = sqrt(beta^2 + sigma^2 (i u + u^2))      principal root
g    = (beta - d) / (beta + d)
phi  = exp( i u (r-q) t
          + (kappa theta / sigma^2) ((beta - d) t - 2 ln((1 - g e^{-d t}) / (1 - g)))
          + (v0 / sigma^2) (beta - d) (1 - e^{-d t}) / (1 - g e^{-d t}) )
```

At `u = 0`, `phi = 1`; return that directly.

**Range.** With `w` the total variance, `c1` the mean of `ln(S_T/K)`:
- Black-Scholes: `w = sigma^2 t`.
- Heston: `w = (theta + (v0 - theta)(1 - exp(-kappa t))/(kappa t)) t`.

`c1 = ln(spot/strike) + (r - q) t - w/2`, `a = c1 - L sqrt(w)`, `b = c1 + L sqrt(w)`.

**Series.** Always price the put, then use parity for a call; the call's coefficients grow with `exp(b)`
and lose accuracy. With `u_k = k pi/(b - a)` and `x = ln(spot/strike)`:

```
chi_k  = [cos(u_k (0 - a)) + u_k sin(u_k (0 - a)) - exp(a) ] / (1 + u_k^2)     integral of e^y cos(u_k (y-a)) on [a, 0]
psi_k  = sin(u_k (0 - a)) / u_k  for k >= 1,  psi_0 = -a                        integral of cos(u_k (y-a)) on [a, 0]
V_k    = (2/(b-a)) strike (psi_k - chi_k)
put    = exp(-r t) sum'_{k=0}^{N-1} Re[ phi(u_k) exp(i u_k (x - a)) ] V_k
```

`sum'` halves the `k = 0` term. If `a >= 0` or `b <= 0`, the range does not hold the strike: `E_INPUT`. Call:
`put + spot exp(-q t) - strike exp(-r t)`.

Sum in order of `k`.

## Acceptance

Class `fourier`. Oracles: 50-digit replay of the series; and truth, with Black-Scholes from mpmath and Heston from
QuantLib `AnalyticHestonEngine`, under a per-case limit.

Numeric targets: Black-Scholes, `N = 256`, `L = 10`: error below 1e-10. Heston with `v0 = theta = 0.04`, `kappa = 1.5`,
`sigma = 0.3`, `rho = -0.7`, `t = 1`, `N = 512`, `L = 16`: error against QuantLib below 1e-7.

Near-zero vol-of-vol: per plan section 8, Heston is tested near zero against Black-Scholes at the average
variance, not at zero. `sigma` must be above 0 here.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Fang, F. and Oosterlee, C. W., "A novel pricing method for European options based on Fourier-cosine series expansions", *SIAM Journal on Scientific Computing* 31(2), 2008, 826-848 (not opened)
- [S2] Heston, S. L., "A closed-form solution for options with stochastic volatility", *Review of Financial Studies* 6(2), 1993, 327-343 (not opened)
