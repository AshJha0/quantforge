# AAD sensitivities of the xVA set

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-161, KR-162, KR-173 to KR-176; stage G G-9, G-35, G-41; plan 14.8 K-8 ("AAD xVA sensitivities equal bump to 1e-8 relative"). Gate: `program/STAGE_K_XVA_GATE.md`.

**Plain idea.** A desk hedging CVA needs to know how CVA moves when each input moves: the counterparty's spread, recovery, every point of the exposure profile, every discount factor, the funding spreads. Bumping each input and recomputing costs one full recomputation per input. Reverse-mode automatic differentiation (AAD) records the calculation once and runs it backwards, giving every derivative for a small fixed multiple of one calculation. The acceptance is the plan's: each AAD number must equal a careful bump-and-recompute to 1e-8 relative. Because AAD differentiates exactly what the code computes, the bump must recompute the same code; and where the code has a kink (`max(x, 0)` of a path value, a funding overlap floor, an exercise decision) neither number means much, so no test sits on one.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [CG10] | Capriotti and Giles, arXiv:1004.1855v1, pp. 1-6 (cost of AAD against bumping; p. 6: indicator payoffs need regularising for the pathwise method, with a small bias) | read 2026-11-19 | the kink rule |
| `aad-core.md` | stage G Q3b AAD core (G-9, G-35): derivative of the computed scheme, Richardson central bump reference, tolerance `1e-10 + 1e-8 |ref|`, performance ratio `<= 5` | read (repo) | conventions reused unchanged |
| [GG06] | Giles and Glasserman, "Smoking adjoints" | **not read** (404, redirect) | cited by `aad-core.md` as not opened; nothing new taken |
| the K-8b specs | `xva-colva.md`, `xva-funding-asymmetric.md`, `xva-mva-im.md`, `xva-wwr-copula.md`, `xva-mpor-closeout.md`, stage G `xva-framework.md`, `xva-exposure-portfolio.md` | this lane | the functions differentiated |

## Formal statement

### `xva.sens.aad` (KR-162)

Inputs: `operation` (one of `xva.adjustments.value`, `xva.colva.value`, `xva.funding.asymmetric`, `xva.mva.value`, `xva.wwr.cva_gaussian_copula`, `xva.exposure.closeout_normal`, `xva.exposure.portfolio_hw`), `inputs` (that operation's inputs), optional `wrt` (list of input paths such as `counterparty.hazard_rate`, `ee[2]`, `borrow_curve.zero_spreads[0]`; default: every real input; for `xva.exposure.portfolio_hw` only `hazard_rate` and `recovery`).

Outputs: the operation's outputs; `gradient` (map from output name to a map from input path to `d output / d input`, per unit absolute change); `reference` (optional, when `check: true`: the KR-161 Richardson value per entry and the agreement flag).

Definition: the derivative of the operation **as computed** (KR-161). For `xva.exposure.portfolio_hw`, `d cva / d hazard_rate` and `d cva / d recovery` with the exact one-factor EE fixed (it does not depend on them), so `d cva / d R = -cva / (1 - R)` and `d cva / d h = (1 - R) sum_i ee_i (t_i e^(-h t_i) - t_(i-1) e^(-h t_(i-1)))`.

## Case inputs (kept for the blind packet)

| Case | Operation and inputs | Entries in the golden |
|---|---|---|
| aadx_k-0001 | `xva.adjustments.value` on `xvaadj_g-0001` | full gradient of cva, dva, fca, fba, fva |
| aadx_k-0002 | `xva.adjustments.value` on `xvaadj_g-0002` (overlap on; `s_l - h_b (1 - R_b) = 0.002`, 20 bp from the kink) | full gradient |
| aadx_k-0003 | `xva.colva.value` on colva_k-0005 | full gradient |
| aadx_k-0004 | `xva.funding.asymmetric` on fva_k-0004 | full gradient |
| aadx_k-0005 | `xva.mva.value` on mva_k-0002 (IM from `NORMAL_MPOR`; gradient also through `sigma_i`) | full gradient |
| aadx_k-0006 | `xva.wwr.cva_gaussian_copula` on wwr_k-0009 | `d cva / d rho`, `/ d h`, `/ d mu`, `/ d s_i` |
| aadx_k-0007 | `xva.exposure.closeout_normal` on cln_k-0005 | `d ee / d sigma`, `/ d im`, `/ d v0`, `/ d threshold_receive` |
| aadx_k-0008 | `xva.exposure.portfolio_hw` on one G-42b single-swap case with credit | `d cva / d h`, `d cva / d R` |
| aadx_k-0009 .. 0012 | `xva.exposure.portfolio_hw` on four G-42b netting sets (two swaps, two portfolios) | `d cva / d h`, `d cva / d R` (ORE cases) |

<!-- strip:begin -->
## Worked examples

**aadx_k-0001, selected entries (scratch, measured 2026-11-19).** `cva = 2.709861774003028` (G-41). `d cva / d R_C = -cva / (1 - R_C) = -4.516436290005047` (Richardson bump `-4.516436290034435`, relative gap 6.5e-12). `d cva / d h_C = 0.6 x sum D_i ee_i (t_i e^(-0.02 t_i) - t_(i-1) e^(-0.02 t_(i-1))) e^(-0.01 t_(i-1)) = 133.0258166316599` (bump `133.02581663165998`, 6.4e-16). `d cva / d h_B = -1.790935732181199` (own survival at bucket start lowers the first-to-default weight; bump gap 1.2e-11). `d fca / d s_b = fca / s_b = 226.95280541807102` (bump gap 9.7e-13). `d cva / d ee[1] = 0.6 x 0.97 x (e^(-0.01) - e^(-0.02)) x e^(-0.005) = 0.005704780048492915` (bump gap 5.2e-12). A 1 bp rise in the counterparty hazard adds 0.0133 to a CVA of 2.71.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected (selected entries; the oracle writes every entry at 50 digits) | Outside check |
|---|---|---|
| aadx_k-0001 | d_cva_d_h_c 133.0258166316599; d_cva_d_r_c -4.516436290005047; d_cva_d_h_b -1.790935732181199; d_fca_d_s_b 226.95280541807102; d_cva_d_ee[1] 0.005704780048492915 | B |
| aadx_k-0002 | oracle | B |
| aadx_k-0003 | oracle | B |
| aadx_k-0004 | oracle | B |
| aadx_k-0005 | oracle | B |
| aadx_k-0006 | oracle | B |
| aadx_k-0007 | `d ee / d im = -Phi(m/s)`, `d ee / d sigma = phi(m/s) s / sigma` at cln_k-0005 (oracle digits) | B |
| aadx_k-0008 | closed forms above on the exact EE | B, and O as 0009 |
| aadx_k-0009 .. 0012 | closed forms above on the exact EE | O |
<!-- strip:end -->

## Errors (order KR-175)

`E_SCHEMA`: unknown `operation`; `wrt` not a list of strings. Structural `E_INPUT`: a `wrt` path that names no real input, or names an input the operation does not differentiate (`xva.exposure.portfolio_hw` with `wrt` `sigma`). Then the wrapped operation's own errors, in its own order. Error goldens: aadx_ke-0001 `wrt ["counterparty.colour"]` (`E_INPUT`); aadx_ke-0002 wrapped `xva.adjustments.value` with `recovery 1` (`E_DOMAIN`, the wrapped error); aadx_ke-0003 `operation "xva.cva.magic"` and `wrt 5` at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 (plan 14.8 K-8, KR-161) Every gradient entry of every value case in all four builds: `|AAD - ref| <= 1e-10 + 1e-8 |ref|`, `ref` the Richardson central bump of the same build's operation. Entries failing the second-pair kink test are dropped before the golden is frozen, with the list recorded; none is expected in the cases above (aadx_k-0002 sits 20 bp from the overlap kink; the bump moves `s_l` by at most 1e-4 relative, 8e-7 absolute).
- A2 Every gradient entry equals the golden (oracle at 50 digits, closed form where one exists) to 1e-10 relative plus 1e-12 absolute.
- A3 Performance (as G-9): median of 21 timed runs after 5 warm-ups, `time(value + full gradient) / time(value) <= 5` on aadx_k-0001 and aadx_k-0004 inputs scaled to 10,000 buckets.
- A4 Gate: at least 8 of 12 value cases outside-checked (60% of 12 is 7.2).
<!-- strip:end -->

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| AAD of the computed sums (KR-161) | exact to rounding | candidate oracle `aadx_k` (50-digit `mpmath.diff`, 2026-11-20) | an input at a kink (`max(., 0)`): excluded by case design | KR-161 Richardson bump, `h^4` truncation |
| Richardson bump reference | `h^4` truncation plus rounding `eps / h` | aadx_k-0001 scratch, 2026-11-19 | an input equal to 0: absolute bump | `aad-core.md` |

## Accuracy envelope (plan 14.10 rule 4)

AAD is exact to rounding for the computed function; the bump reference carries truncation error `O(h^4)` after Richardson and rounding error about `eps |f| / (h |x|)`. With `h = 1e-4` relative both are below 1e-11 relative for the smooth functions here (measured on aadx_k-0001: largest gap 1.2e-11). The envelope's edges are (1) inputs equal to 0 (absolute bump `h`), covered by aadx_k-0006 at `mu` entries near 0 and by `ee` entries of 0 in an oracle case; (2) proximity to a kink, covered by aadx_k-0002 at 20 bp from the overlap floor; (3) large gradients relative to the value (aadx_k-0001 `d fca / d s_b`, 125 times the value). Path-based operations with `max` on each path are differentiated pathwise and are **not** in the goldens: a bump crosses a path's kink with probability of order `h` times the density at 0, so the 1e-8 acceptance would fail by design; this is stated as a limit, as [CG10] p. 6 notes for indicators.

## Outside-check design (registered here before any run)

- **B (8):** aadx_k-0001 to 0008: closed-form derivatives of the formulas, re-derived blind from the specs.
- **O (5), ORE bump and revalue on the stage G route (two `xva` runs, no `xvaSensitivity` analytic needed):** aadx_k-0008 to 0012 on G-42b netting sets: ORE run with the counterparty hazard `h` and again with `h (1 + 1e-3)` (and recovery `R` and `R + 1e-3` for the recovery entry), same seeds 20261371 to 20261375, 5,000 samples; ORE's finite difference `(CVA(h') - CVA(h)) / (h' - h)` on common paths. Golden: the closed form on the exact EE. Because ORE's CVA with deterministic credit is linear in its EE, its difference quotient equals `(1 - R) sum EE_ORE,i x (difference of survival terms) / (h' - h)`, so: (1) reconstruct ORE's quotient from its own cube to 1e-6 relative (KR-174); (2) `|golden - ORE quotient| <= max(3, z_Bonf) SE` plus the one-sided truncation bound `|d^2 CVA / d h^2| (h' - h) / 2`, computed from the closed form and registered with the case. These check our derivative against ORE's revaluation of ORE's own exposures; ORE's AAD prototype ([ORE-E] Performance) is not used.
- **None:** 0.

## Limits

- Pathwise derivatives of path-based operations (G-40 collateral, `xva.exposure.closeout` on paths, LSMC) are computed but carry no golden and no 1e-8 claim (envelope above).
- Model-parameter sensitivities of exposure (`d EE / d sigma`, `d EE / d curve`) are stage G's `aad-core.md` territory for the Bermudan; for the portfolio exposure they are not specified here.
- Second derivatives (cross-gamma) are out of scope.
