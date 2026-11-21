# Collateral valuation adjustment (ColVA) and the collateral floor

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-163, KR-173 to KR-176. Gate: `program/STAGE_K_XVA_GATE.md`.

**Plain idea.** Collateral is not free money. The party holding cash collateral pays interest on it at the rate the CSA names, usually an overnight rate, sometimes plus or minus a spread, sometimes floored at zero. Prices are discounted at the overnight rate, so any gap between the rate actually paid on collateral and the discount rate is a stream of small payments over the life of the netting set. ColVA is the value today of that stream: the expected collateral balance in each period, times the rate gap, times the period length, discounted. When we hold collateral and must pay more than the discount rate on it, ColVA is a cost.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [ORE-X] | ORE 1.8.17.0 User Guide, `methods/xva.tex`, COLVA and collateral floor paragraphs | read 2026-11-19 | the formula and the floor term, both as written; the ORE comparison |
| [GK14] | Green and Kenyon, arXiv:1405.0508v2, PDF p. 7, COLVA in eq. group 33-37 | read 2026-11-19 | the survival-discounted variant (`survival: BOTH`) |
| [P10] | Piterbarg, *Risk*, February 2010 | **not read** (paywall) | background only; no formula taken |
| G-40 | `xva-framework.md`, `xva.exposure.collateralised` | read (repo) | expected collateral profile from given paths |

## Formal statement

### `xva.colva.value`

Inputs: `times` `t_0 < t_1 < ... < t_n` (`n >= 1`); `collateral` `C_0 .. C_(n-1)` (expected balance at the start of each bucket, positive = received by us); `discount_factors` `D(t_1) .. D(t_n)` in `(0, inf)`; `spread` either one number or `n` numbers `Delta_i` (collateral rate minus discount rate on `(t_i, t_(i+1)]`); optional `survival` `NONE` (default) or `BOTH` with `counterparty` and `own` `{hazard_rate >= 0}`; optional `overnight_rates` `r_0 .. r_(n-1)` (enables the floor output).

- `colva = - sum_(i=0)^(n-1) C_i Delta_i delta_i D(t_(i+1)) W_i`, `delta_i = t_(i+1) - t_i`, `W_i = 1` (`NONE`) or `exp(-(h_C + h_B) t_i)` (`BOTH`): both names alive at the START of the bucket `(t_i, t_(i+1)]`, the same survival point as FCA, FBA and MVA (KR-297, proposed 2026-11-20, confirmed 2026-11-21; the version-0.1.0 text had `t_(i+1)`).
- `collateral_floor = - sum C_i max(-r_i, 0) delta_i D(t_(i+1)) W_i` (only with `overnight_rates`; reported, not added).

Outputs: `colva`, `terms` (the `n` summands), `collateral_floor` (or absent).

Path form: `xva.colva.value` also accepts `paths` (G-40 inputs and CSA) instead of `collateral`; then `C_i` is the path mean of G-40's held collateral at `t_i` for `i = 0 .. n-1` (G-40's `C_i = K_(max(i - l, 0))`, `l = mpor_steps`), `discount_factors` are given at `t_1 .. t_n`, and the output adds `collateral_profile` (those `n` means, KR-298). Label "simulated" on the path form.

## Case inputs (kept for the blind packet)

Common: `times = (0, 0.5, 1, 1.5, 2)`, `D(t) = exp(-0.03 t)` at `t_1..t_4`.

| Case | Inputs |
|---|---|
| colva_k-0001 | `collateral (100, 80, 50, 20)`, `spread 0.001`, `NONE` |
| colva_k-0002 | as 0001, `BOTH`, `h_C 0.02`, `h_B 0.01` |
| colva_k-0003 | as 0001 with `overnight_rates (-0.005, 0, 0.01, -0.002)`; floor output |
| colva_k-0004 | `collateral (100, -40, -60, 20)`, `spread (0.001, 0.001, -0.0005, -0.0005)`, `NONE` |
| colva_k-0005 | `collateral (100, 80, 50, 20)`, `spread (0.002, 0.0015, 0.001, 0.0005)`, `BOTH`, `h_C 0.03`, `h_B 0.015` |
| colva_k-0006 | path form: `collexp_g-0004` paths and CSA (G-40), `spread 0.001`, `D(t) = exp(-0.03 t)` on its grid |
| colva_k-0007 .. 0010 | ORE cases, see "Outside-check design" |

<!-- strip:begin -->
## Worked examples

**colva_k-0001.** Buckets of half a year. Terms `-C_i x 0.001 x 0.5 x exp(-0.03 t_(i+1))`: `-100 x 0.0005 x 0.98511194 = -0.04925560`; `-80 x 0.0005 x 0.97044553 = -0.03881782`; `-50 x 0.0005 x 0.95599748 = -0.02389994`; `-20 x 0.0005 x 0.94176453 = -0.00941765`. Sum `colva = -0.12139100070376345`. Holding 100 of collateral for half a year and paying 10 bp over the discount rate costs about 0.05.

**colva_k-0002.** Each term times `exp(-0.03 t_i)` (KR-297): `colva = -0.11969232863755361` (`-0.11791034201974765` under the version-0.1.0 bucket-end weight, smaller in size by `exp(-0.015)`).

**colva_k-0003.** Floor terms `-C_i max(-r_i, 0) x 0.5 x D`: `-100 x 0.005 x 0.5 x 0.98511194 = -0.24627798`, 0, 0, `-20 x 0.002 x 0.5 x 0.94176453 = -0.01883529`; `collateral_floor = -0.2651132755724506`. The floor is worth more than the spread here because a 50 bp negative overnight rate is floored at zero.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | Arithmetic | Outside check |
|---|---|---|---|
| colva_k-0001 | colva -0.12139100070376345 | above | B |
| colva_k-0002 | colva -0.11969232863755361 (KR-297; -0.11791034201974765 at bucket end) | above | B |
| colva_k-0003 | colva as 0001; collateral_floor -0.2651132755724506 | above | B |
| colva_k-0004 | candidate file `oracle/xva_k8b_candidates/colva_k.json` | signs mixed: received and posted with positive and negative spreads | B |
| colva_k-0005 | candidate file `oracle/xva_k8b_candidates/colva_k.json` | time-dependent spread with survival | B |
| colva_k-0006 | candidate file `oracle/xva_k8b_candidates/colva_k.json` | G-40 held collateral averaged over paths | B |
| colva_k-0007 .. 0010 | one-factor quadrature (see below) | `-Delta sum delta_i E^N[V(t_i) / N(t_(i+1))]` | O |
<!-- strip:end -->

## Errors (order KR-175)

`E_SCHEMA`: missing field, wrong type, unknown `survival`. Structural `E_INPUT`: `collateral` length not `n`; `discount_factors` length not `n`; `spread` list length not `n`; `BOTH` without hazards; `overnight_rates` length not `n`; both `collateral` and `paths` or neither. `E_DOMAIN`: times not strictly increasing; a discount factor `<= 0`; a hazard rate `< 0`; non-finite numbers. `E_LIMIT`: KR-175. Error goldens: colva_ke-0001 `spread` of length 3 with `n = 4` (`E_INPUT`); colva_ke-0002 `survival "BOTH"` with `hazard_rate -0.01` (`E_DOMAIN`); colva_ke-0003 `survival "SOME"` and a negative discount factor at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 All value goldens in all four builds to 1e-12 relative plus 1e-12 absolute (class `simple_analytic`).
- A2 Properties (10,000 random cases): `spread = 0` gives 0; `colva` is linear in `C` and in `Delta`; `survival BOTH` with zero hazards equals `NONE`; flipping the sign of every `C_i` flips `colva`; the path form equals the profile form on the path-mean collateral.
- A3 Gate (plan 15): at least 6 of the 10 value cases outside-checked under KR-173 (`STAGE_K_XVA_GATE.md`).
- A4 AAD (KR-161): `d colva / d C_i`, `d / d Delta_i`, `d / d D_i`, `d / d h` equal the Richardson bump to `1e-10 + 1e-8 |ref|`.
<!-- strip:end -->

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Closed-form sum on a profile | exact to rounding | candidate oracle `colva_k` (50 digits, 2026-11-20) | zero spread gives 0 exactly | KR-163 |
| Path form: sample mean of held collateral | Monte Carlo `1 / sqrt(paths)` (the caller's paths) | colva_k-0006 on four given paths (exact mean) | one path: the mean is that path | G-40 |

## Accuracy envelope (plan 14.10 rule 4)

The profile form is exact arithmetic (no approximation). The path form is a sample mean of the given paths: its error is the caller's Monte Carlo error, reported as `collateral_se` per date. The ORE route is the check at the edge that matters: a full-VM collateralised swap where the collateral equals the netted value, so ColVA has a one-factor reference.

## Outside-check design (registered here before any run)

- **B (6 cases, 0001 to 0006):** formulas on given numbers; a DR-H2 blind lane re-derives them from the rules above and KR-163.
- **O (4 cases, 0007 to 0010), ORE `xva` analytic with `colva = Y`, stage G route:** four G-42b netting sets (two single payer swaps, two portfolios, `a = 0.03`, `sigma = 0.01`), each with a CSA of threshold 0, MTA 0, independent amount 0, and the collateral compounding spread `Delta = 0.001` over the overnight index of the generated market. Golden: with full VM and no lag, `C(t_i) = V(t_i)`, so `colva = -Delta sum delta_i E^N[V(t_i) / N(t_(i+1))]`, each expectation a one-dimensional Gaussian integral in the G-42 LGM coordinates (`E^N[V(t_i) P(t_i, t_(i+1), x) / N(t_i, x)]`), quadrature to 1e-10 relative. Seeds 20261311 to 20261314, 5,000 samples, annual grid. Check: (1) reconstruct ORE's printed `COLVA` from its own cube to 1e-6 relative (KR-174); (2) `|golden - ORE| <= max(3, z_Bonf) SE`, SE from the cube's per-sample sums. Fallback, registered now: if ORE refuses an MPoR of 0 with `calculationType NoLag`, use MPoR = one grid step; the golden then uses `C(t_i) = V(t_(i-1))`, a two-dimensional Gaussian integral, same tolerance.
- **None:** 0.
- **Wheel question:** whether the wheel's `OREApp` runs `xva` with `colva = Y` is unverified (the stage G runs used `colva = N`); test in `STAGE_K_XVA_GATE.md` section 4.

## Limits

- Expected collateral is an input (or a path mean); no collateral choice option (cheapest-to-deliver currency) and no multi-currency CSA.
- The floor output is ORE's approximation (an expectation of a floored rate times the expected balance, not an option on the rate path); it is labelled "approximation as ORE's collateral floor" and is not used inside any other output.
- No interaction with MPoR: ColVA uses the collateral actually held at each date.
