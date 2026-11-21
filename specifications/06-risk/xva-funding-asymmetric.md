# Funding valuation adjustment with separate borrowing and lending curves

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-164, KR-173 to KR-176; stage G G-41. Gate: `program/STAGE_K_XVA_GATE.md`.

**Plain idea.** When an uncollateralised trade is worth money to the bank, the bank has paid (or will pay) for an asset its counterparty does not collateralise, and it must borrow to carry it; when the trade is a liability, the bank holds cash it can lend out. A bank borrows at a higher rate than it lends, so the two sides are priced with two different spreads: the borrowing spread on the positive exposure (funding cost, FCA) and the lending spread on the negative exposure (funding benefit, FBA). Stage G did this with two constant spreads. Here the spreads come from two term-structure curves, so each period uses the forward spread for that period.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [ORE-X] | ORE 1.8.17.0 User Guide, `methods/xva.tex`, FVA section (`f_b`, `f_l` relative to OIS; survival at `t_(i-1)`; exposure `[NPV - C]^+` and `[-NPV + C]^+` at `t_i`) | read 2026-11-19 | the formula, as written; the ORE comparison |
| [ORE-C] | ORE source `staticcreditxvacalculator.cpp` (`calculateNettingSetFcaIncrement`, `...FbaIncrement`, `...MvaIncrement`), tag v1.8.16.0 and master: survival at `d0`, the bucket start, for FCA, FBA and MVA alike | read 2026-11-20 (GitHub API) | KR-296: one survival point for FVA and MVA |
| [ORE-P] | same, `parameterisation/ore.tex`: `fvaBorrowingCurve`, `fvaLendingCurve` | read 2026-11-19 | the ORE inputs |
| [GK14] | arXiv:1405.0508v2 p. 7 eq. 35 (FCA by semi-replication, symmetric funding) | read 2026-11-19 | the single-curve special case |
| [BK11] | Burgard and Kjaer, asymmetric funding | **not read** (SSRN 403) | not used for any formula |
| G-41 | `xva-framework.md` `xva.adjustments.value` | read (repo) | flat-curve special case, overlap rule |

## Formal statement

### `xva.funding.asymmetric`

Inputs: `times` `t_1 < ... < t_n` (buckets from `t_0 = 0`); `discount_factors` `D_i`; `ee` (`>= 0`) and `ene` (`<= 0`), collateralised exposures at bucket ends; `counterparty` and `own` `{hazard_rate >= 0, recovery in [0, 1)}`; `borrow_curve` and `lend_curve`, each `{tenors (> 0, increasing), zero_spreads}`; optional `exclude_dva_overlap` (default false).

- Spread at time `T` from a curve: `s(T)` by linear interpolation of `s T` in `T` between pillars, with `s(0) T = 0` at the origin, flat forward beyond the last pillar (KR-164).
- Forward spread on bucket `i`: `f_i = (s(t_i) t_i - s(t_(i-1)) t_(i-1)) / delta_i`.
- `FCA = sum_i f_b,i delta_i S_C(t_(i-1)) S_B(t_(i-1)) D_i ee_i`; `FBA = sum_i f_l,i' delta_i S_C(t_(i-1)) S_B(t_(i-1)) D_i |ene_i|`, `f_l,i' = f_l,i` or, with `exclude_dva_overlap`, `max(f_l,i - h_B (1 - R_B), 0)`; `FVA = FCA - FBA`. `S(t) = exp(-h t)`. Survival at the bucket start `t_(i-1)` is the one convention for FCA, FBA, MVA and the ColVA survival weight (KR-296, proposed 2026-11-20).

Outputs: `fca`, `fba`, `fva`, `forward_borrow`, `forward_lend` (per bucket, after the overlap rule).

## Case inputs (kept for the blind packet)

| Case | Inputs |
|---|---|
| fva_k-0001 | `times (1, 2)`; `D_i = exp(-0.03 t_i)`; `ee (10, 6)`; `ene (-4, -8)`; `h_C 0.02`, `h_B 0.01`, `R 0.4` both; `borrow_curve` tenors `(1, 2)` spreads `(0.010, 0.012)`; `lend_curve` tenors `(1, 2)` spreads `(0.004, 0.005)` |
| fva_k-0002 | as 0001, `R_B 0.6`, `exclude_dva_overlap true` |
| fva_k-0003 | `xvaadj_g-0001` inputs with both curves flat at 0.008 (the G-41 case) |
| fva_k-0004 | `times (0.5, 1, 1.5, 2)`, `xvaadj_g-0001` profiles, borrow curve pillars `(0.75, 3)` spreads `(0.009, 0.015)` (interpolation inside buckets), lend curve one pillar `5` spread `0.004` |
| fva_k-0005 | as 0004, lend curve spreads chosen so the overlap binds in some buckets and not others: pillars `(1, 2)`, `(0.002, 0.009)`, `h_B 0.01`, `R_B 0.4`, `exclude_dva_overlap true` |
| fva_k-0006 | as 0004 (times, discount factors, `ene`, credit, both curves) with `ee (0, 0, 0, 0)` |
| fva_k-0007 .. 0010 | ORE cases, see "Outside-check design" |

<!-- strip:begin -->
## Worked examples

**fva_k-0001 (two dates).** Forward borrow spreads: bucket 1 `0.010 x 1 / 1 = 0.010`, bucket 2 `(0.012 x 2 - 0.010 x 1) / 1 = 0.014`. Lend: `0.004`, `(0.005 x 2 - 0.004) / 1 = 0.006`. Survival at bucket starts: bucket 1 both 1; bucket 2 `exp(-0.02) exp(-0.01) = exp(-0.03)`. FCA terms: `0.010 x 1 x 1 x exp(-0.03) x 10 = 0.09704455`; `0.014 x exp(-0.03) x exp(-0.06) x 6 = 0.07677022`; FCA `0.17381477291763398`. FBA terms: `0.004 x exp(-0.03) x 4 = 0.01552713`; `0.006 x exp(-0.09) x 8 = 0.04386870`; FBA `0.05939582542979509`. FVA `0.11441894748783889`. The second bucket carries most of the lending benefit because its forward lending spread is 60 bp, not the 50 bp zero spread.

**fva_k-0002 (overlap).** `h_B (1 - R_B) = 0.01 x 0.4 = 0.004`. Forward lend `(0.004, 0.006)` becomes `(0, 0.002)`; FBA `0.002 x exp(-0.09) x 8 = 0.01462289896433965`. FCA unchanged.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | Arithmetic | Outside check |
|---|---|---|---|
| fva_k-0001 | fca 0.17381477291763398; fba 0.05939582542979509; fva 0.11441894748783889 | above | B |
| fva_k-0002 | fba 0.01462289896433965; fca as 0001 | above | B |
| fva_k-0003 | fca 1.815622443344568; fba 1.2027298203433914 (equal to `xvaadj_g-0001`) | flat curves | B |
| fva_k-0004 | candidate file `oracle/xva_k8b_candidates/fva_k.json` (50 digits) | pillar interpolation inside buckets | B |
| fva_k-0005 | candidate file `oracle/xva_k8b_candidates/fva_k.json` | overlap partly binding | B |
| fva_k-0006 | fca 0; fba as 0004 | | B |
| fva_k-0007 .. 0010 | exact one-factor EE and ENE (G-42 quadrature) with deterministic survival | ORE `fva = Y` | O |
<!-- strip:end -->

## Errors (order KR-175)

`E_SCHEMA`: missing field, wrong type. Structural `E_INPUT`: profile lengths differ from `times`; curve `tenors` and `zero_spreads` of different length or empty. `E_DOMAIN`: `ee < 0`, `ene > 0`; hazard `< 0`; recovery outside `[0, 1)`; curve tenors not positive or not increasing; non-finite. Negative spreads are allowed (a forward spread can be negative). Error goldens: fva_ke-0001 `lend_curve` tenors `(2, 1)` (`E_DOMAIN`); fva_ke-0002 `ee` of length 1 with two times (`E_INPUT`); fva_ke-0003 `ee` as a string and `R 1.2` at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 Value goldens in four builds to 1e-12 relative plus 1e-12 absolute.
- A2 Properties: flat curves give G-41 `fca`, `fba` exactly (to 1e-14 relative); swapping `ee` with `|ene|` and the two curves swaps FCA and FBA; FVA is linear in each curve's spreads.
- A3 Gate: at least 6 of 10 value cases outside-checked under KR-173.
- A4 AAD (KR-161) on every spread pillar, hazard, recovery and profile entry; the overlap kink is avoided by case design (fva_k-0005 keeps every bucket at least 1 bp away from it).
<!-- strip:end -->

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Closed-form sum with interpolated forward spreads | exact to rounding | candidate oracle `fva_k` (50 digits, 2026-11-20) | flat curves give G-41 exactly (fva_k-0003) | KR-164, KR-296 |
| ORE Monte Carlo (O cases) | `1 / sqrt(samples)`, judged at `max(3, z_Bonf) SE` | not run (needs WSL) | deterministic survival: the expectation factorises | [ORE-X] |

## Accuracy envelope

Exact arithmetic on given profiles. Interpolation is a definition (KR-164), not an approximation. The O cases check the formula at the place it is used in practice: on simulated exposures of a real netting set.

## Outside-check design (registered here before any run)

- **B (6 cases, 0001 to 0006).**
- **O (4 cases, 0007 to 0010), ORE `xva` with `fva = Y`, stage G route:** four G-42b netting sets (uncollateralised), seeds 20261321 to 20261324, 5,000 samples, annual grid; `fvaBorrowingCurve` and `fvaLendingCurve` generated as zero-spread curves over the discount curve with pillars `(1, 2, 5, 10, 20)` years, spreads `(0.010, 0.011, 0.012, 0.013, 0.014)` and `(0.004, 0.0045, 0.005, 0.0055, 0.006)`, our interpolation rule matched by putting ORE pillars at every grid date (we write the interpolated discount factors so ORE's interpolation cannot differ); flat hazards `h_C 0.02`, `h_B 0.01`, `dynamicCredit N`. Golden: KR-164 sums with the exact one-factor EE and ENE (G-42 quadrature). With deterministic survival ORE's `E^N[S_C S_B [NPV]^+ D]` equals `S_C S_B E^N[[NPV]^+ D]`, so the comparison is exact up to Monte Carlo error. Check: reconstruct ORE's `FCA`, `FBA` from its cube to 1e-6 relative (KR-174), then `|golden - ORE| <= max(3, z_Bonf) SE` for each of `FCA`, `FBA`. ORE's sign convention (it labels the `f_l` term FBA, [ORE-X]) is matched by reading the column names in the debug run.
- **None:** 0.

## Limits

- Funding is netted per netting set, not across the bank's whole funding position (no funding netting set).
- No collateral re-use or segregation choices beyond the given collateralised exposure.
- [BK11] was not read; whether its semi-replication strategies give the same discrete formula for asymmetric rates is not claimed.
