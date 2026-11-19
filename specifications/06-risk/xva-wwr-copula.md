# Wrong-way risk with a Gaussian copula between exposure and default

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-167, KR-173 to KR-176; stage G G-16, G-44. Gate: `program/STAGE_K_XVA_GATE.md`.

**Plain idea.** Plain CVA multiplies the average exposure by the default probability, which assumes the two are unrelated. Often they are not: a bank that sold protection to an airline, or lent through a cross-currency swap to a country whose currency is falling, is most exposed exactly when the counterparty is most likely to fail. That is wrong-way risk. The simplest way to model it is to tie the counterparty's default to the exposure through one correlation number: draw the exposure driver and the default driver as two correlated standard normals. With a normal exposure the conditional expected exposure given default in a period has a closed form, so the CVA and a "wrong-way factor" (how much bigger the exposure is in the periods where default happens) can be computed exactly and checked by direct numerical integration.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [MV19] | Mbaye and Vrins, arXiv:1909.02474v1, p. 12 (Definition 2: default time through a Gaussian variable, the dynamized Gaussian copula), pp. 14-16 (Section 4.1: CVA as `E[(1 - R) V^+_tau / beta_tau 1{tau < T}]`, eq. 39; the independent CVA, eq. 42; WWR enters through the correlation of the exposure and default drivers; "the EPE needs to be replaced by a conditional EPE") | read 2026-11-19 | the idea and the CVA definition |
| [CHRS10] | Cespedes, Herrero, Rosen, Saunders (2010), Gaussian copula on ordered exposure scenarios | **not read** | not used; the static construction below is the project's own (KR-167) |
| [Pyk12] | Pykhtin (2012) | **not read** | not used |
| G-16, G-44 | `xva-exposure.md`, `xva-framework.md` | read (repo) | bucket convention; the Hull-White hazard model this does not replace |

## Formal statement

### `xva.wwr.cva_gaussian_copula`

Inputs: `times` `t_1 < ... < t_n` (buckets from `t_0 = 0`); `discount_factors` `D_i`; exposure `mean` `mu_i` and `stdev` `s_i > 0` (the netted value at `t_i` is `mu_i + s_i Z_i`, `Z_i ~ N(0, 1)`); `hazard_rate` `h > 0`; `recovery` `R in [0, 1)`; `rho` in `(-1, 1)`.

Model (KR-167): default by `t` iff `Y > b(t)`, `b(t) = Phi^-1(1 - PD(t))` (equivalently `-Y < Phi^-1(PD(t))`), `PD(t) = 1 - exp(-h t)`; `corr(Z_i, Y) = rho`; `rho > 0` is wrong way.

Bucket term, with `c = -rho`, `a_i = -mu_i / s_i`, `beta_i = Phi^-1(PD(t_i))` (`beta_0 = -inf`), `r = sqrt(1 - c^2)`:
`G(beta) = mu P(Z > a, U <= beta) + s E[Z 1{Z > a, U <= beta}]` for `U = -Y` (`corr(Z, U) = c`), where
- `P(Z > a, U <= beta) = Phi(beta) - Phi_2(a, beta; c)`,
- `E[Z 1{Z > a, U <= beta}] = phi(a) Phi((beta - c a)/r) - c phi(beta) Phi((c beta - a)/r)`.

`CVA = (1 - R) sum_i D_i (G_i(beta_i) - G_i(beta_(i-1)))`; per bucket `wwr_factor_i = (G_i(beta_i) - G_i(beta_(i-1))) / (EE_i (PD(t_i) - PD(t_(i-1))))`, `EE_i = mu_i Phi(mu_i/s_i) + s_i phi(mu_i/s_i)`.

Outputs: `cva`, `cva_independent` (the same with `rho = 0`), `wwr_factor` per bucket, `bucket_terms`.

`Phi_2` to 1e-14 absolute (KR-167). The identity for `E[Z 1{...}]` follows by writing `Z = c U + r W` and integrating (inferred; the L check below tests it).

## Case inputs (kept for the blind packet)

Single bucket `t_1 = 1`, `PD = 0.02` (`beta = Phi^-1(0.02)`), `D = 1`, `R = 0` (so the output is the bucket term itself), `s = 1`:

| Case | Inputs |
|---|---|
| wwr_k-0001 | `mu 0`, `rho 0.5` |
| wwr_k-0002 | `mu 0`, `rho 0` |
| wwr_k-0003 | `mu 0`, `rho -0.5` |
| wwr_k-0004 | `mu 0.5`, `rho 0.3` |
| wwr_k-0005 | `mu -0.5`, `rho 0.3` |

(For 0001 to 0005 `PD` is given directly as 0.02; the operation accepts `pd_at_times` instead of `hazard_rate` for this purpose, an input variant stated here.)

Two buckets `times (1, 2)`, `h 0.02`, `R 0.4`, `D_i = exp(-0.03 t_i)`, `s_i = sqrt(t_i)`, `mu_i = mu t_i`:

| Case | Inputs |
|---|---|
| wwr_k-0006 | `mu 0`, `rho 0` |
| wwr_k-0007 | `mu 0`, `rho 0.5` |
| wwr_k-0008 | `mu 0`, `rho -0.5` |
| wwr_k-0009 | `mu 0.2`, `rho 0.3` |
| wwr_k-0010 | ten annual buckets, `mu_i = 0.05 t_i (10 - t_i)`, `s_i = 0.3 sqrt(t_i)`, `h 0.03`, `R 0.4`, `D_i = exp(-0.02 t_i)`, `rho 0.4` |

<!-- strip:begin -->
## Worked examples

**wwr_k-0002 (independence).** `mu = 0`, `s = 1`: `EE = phi(0) = 0.3989422804`; bucket term `EE x PD = 0.007978845608028654`; factor 1.

**wwr_k-0001 (wrong way, rho 0.5).** `c = -0.5`, `beta = -2.0537489106`, `a = 0`, `r = 0.8660254`. `E[Z 1{Z > 0, U <= beta}] = phi(0) Phi(beta / r) + 0.5 phi(beta) Phi(-0.5 beta / r)`. `Phi(-2.371465) = 0.0088589`, `phi(beta) = 0.0484181`, `Phi(1.185732) = 0.882136`: `0.3989423 x 0.0088589 + 0.5 x 0.0484181 x 0.882136 = 0.0035342 + 0.0213557 = 0.0248899`, the bucket term `0.024889865831758267`; factor `0.02488987 / 0.00797885 = 3.119482072282866`. At 50% correlation the exposure on default paths is about three times the average.

**wwr_k-0003 (right way, rho -0.5).** Factor 0.0853. Defaults happen where the exposure is low.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | L value (SciPy `dblquad`, measured 2026-11-19) | Outside check |
|---|---|---|---|
| wwr_k-0001 | term 0.024889865831758267; factor 3.119482072282866 | 0.024889865831758274 | **L** |
| wwr_k-0002 | term 0.007978845608028654; factor 1 | 0.007978845608028655 | **L** |
| wwr_k-0003 | term 0.0006807978913872508; factor 0.08532536219302239 | 0.0006807978913872518 | **L** |
| wwr_k-0004 | term 0.025438333326790498; factor 1.8227614522437943 | 0.025438333326790494 | **L** |
| wwr_k-0005 | term 0.010127126375944304; factor 2.559985499494197 | 0.010127126375944326 | **L** |
| wwr_k-0006 | cva 0.010787339602702142 | 0.010787339602702152 | **L** |
| wwr_k-0007 | cva 0.029999146946385117 | 0.029999146946385134 | **L** |
| wwr_k-0008 | cva 0.0013268543824397623 | 0.0013268543824397727 | **L** |
| wwr_k-0009 | cva 0.026384614677401826 | 0.02638461467740185 | **L** |
| wwr_k-0010 | oracle, 50 digits | to be measured with the same script | B (L candidate) |
<!-- strip:end -->

L method: `scipy.integrate.dblquad` of the defining integral `int_{u in bucket} int_{z > a} (mu + s z) phi_2(z, u; c) dz du` (bivariate normal density written out, integration bounds at 12 standard deviations, `epsabs 1e-14`, `epsrel 1e-12`). It does not evaluate `Phi_2` or the identity above, so it is a different formulation (KR-173). The expected values in the table came from SciPy 1.17.1 `multivariate_normal.cdf` for `Phi_2` in scratch; the oracle lane recomputes them with mpmath at 50 digits before freezing, and any change beyond 1e-13 relative is recorded. Largest relative difference between the two columns: 7.8e-15 (wwr_k-0008).

## Errors (order KR-175)

`E_SCHEMA`: missing field, wrong type. Structural `E_INPUT`: profile lengths differ from `times`; both `hazard_rate` and `pd_at_times`, or neither. `E_DOMAIN`: `s_i <= 0`; `|rho| >= 1`; `h <= 0`; `pd_at_times` not strictly increasing in `(0, 1)`; `R` outside `[0, 1)`; non-finite. Error goldens: wwr_ke-0001 `rho 1` (`E_DOMAIN`); wwr_ke-0002 `stdev` of length 1 with two times (`E_INPUT`); wwr_ke-0003 `rho "high"` and `stdev 0` at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 Value goldens to 1e-12 relative plus 1e-15 absolute (class `special_function`; `Phi_2` dominates).
- A2 Properties: `rho = 0` gives `cva_independent` exactly (to 1e-14 relative); `cva` is non-decreasing in `rho` for `mu = 0` (tested on a grid of 41 values); `sum_buckets` of the unconditional bucket terms with `rho` arbitrary but one bucket covering all of `(0, T]` and `R = 0` is at most `EE`; as `rho -> 1` with `mu = 0` the single-bucket term tends to `E[Z 1{Z > -beta}] = phi(beta)` (checked at `rho = 0.999999`, envelope edge).
- A3 Gate: at least 6 of 10 value cases outside-checked; 9 L measured.
- A4 AAD of `cva` with respect to `rho`, `h`, `mu_i`, `s_i` to KR-161 (no kink: the integrand's kink at `Z = a` is integrated out).
<!-- strip:end -->

## Accuracy envelope (plan 14.10 rule 4)

The closed form is exact for the stated model. Numerical edges: `|rho| -> 1` (`r -> 0`, the arguments `(beta - c a)/r` blow up; builds switch to the limit form when `r < 1e-7`, a ruling to confirm), very small `PD` (`beta < -8`, tail of `Phi_2`; checked by a golden at `PD = 1e-12` in the oracle lane), and `mu/s` large (the `Phi_2(a, beta)` term cancels against `Phi(beta)`). The model error (one Gaussian factor, constant correlation over time, normal exposure) is not measured here: it is a modelling choice, stated as such, and the docs must say that the wrong-way factor depends entirely on `rho`, which nobody observes.

## Outside-check design (registered here before any run)

- **L (9, measured):** wwr_k-0001 to 0009 as above.
- **B (1):** wwr_k-0010 (also an L candidate once measured).
- **O: none.** ORE's wrong-way risk is a stochastic-credit correlation model (`dynamicCredit`, IR-credit correlation; [ORE-E] Wrong-Way-Risk table), a different model; running it would check only the sign (survey section 4). Not counted, not planned.

## Limits

- Exposure is normal at each date and the same correlation applies at every date; a path-based version (ranking simulated exposures by a systematic factor, as recalled from [CHRS10]) is not specified because its source was not read.
- No relation to G-44 (Hull-White hazard on paths); the two answer the same question with different models and are not expected to agree.
- The correlation is an input; no calibration.
