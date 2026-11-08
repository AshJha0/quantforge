# Stage E handover, spec B (E4, E6, E7, E8)

From the spec B session (branch `stage-e-spec2`) to the four language sessions. One section per slice, appended as each slice lands. Spec A's slices (E1, E2, E3, E5) have their own handover.

Language sessions may read the spec files, the golden files through the runner, and the CLI contract named below. Do not read oracle code (`oracle/python/*`), the convention map or the outside register: they are the oracle.

## E7 GARCH, variance swaps, VIX (ready, 2026-11-08)

New operations: `vol.garch.loglik`, `vol.garch.forecast`, `vol.garch.fit`, `vol.varswap.fair_strike`, `vol.varswap.realized`, `vol.vix.term_variance`, `vol.vix.index`.

Goldens: `datasets/golden/stage_e_b/{garch_e,varswap_e,vix_e}.json`, 72 cases (49 ok, 23 error). Run with `conformance/runner/runner.py --suite garch_e` (and so on); the runner finds `stage_e_b` by its recursive search.

Read:
- `specifications/cli-contract.md`, section "Stage E operations, spec B"
- `specifications/stage-e-rulings-b.md` (E-B1 to E-B7)
- `specifications/05-volatility/garch.md`
- `specifications/05-volatility/variance-swaps.md`
- `specifications/05-volatility/vix-index.md`
- `specifications/05-volatility/stage-e-targets-b.md`, E7 table

Points that are easy to get wrong (all are wrong-convention checks in the goldens): GARCH `"SAMPLE"` start has divisor `n` and no demeaning, and the likelihood keeps the `t = 1` term and `ln(2 pi)`; forecast exponent is `h - 1`; `vol.garch.fit` is judged on `loglik` only (1e-6), any proven optimiser; variance-swap drift term keeps `q` (QuantLib's engine does not); realized variance has divisor `m`, no mean; VIX `K0` is at or below the forward, `dK` comes from the selected strikes, two consecutive zero bids stop a side.

Oracle: 18 of 72 cases outside-checked by QuantLib 1.44 (all `q = 0` replication cases); the rest by hand cases, 50-digit or exact-rational replicas and a separate float replay. 74 wrong-convention checks caught. Outside share for E7: 18 of 72 (25%).

## E4 rates and inflation vol (ready, 2026-11-08)

New operations: `rates.swaption.price_cube`, `rates.cap.strip`, `rates.bondfut.option_price`, `rates.bondfut.implied_vol`, `infl.cap.yoy_price`, `infl.cap.zc_price`.

Goldens: `datasets/golden/stage_e_b/ratesvol_e.json`, 50 cases (35 ok, 15 error).

Read:
- `specifications/cli-contract.md`, section "Stage E operations, spec B" (E4 row)
- `specifications/stage-e-rulings-b.md` (E-B8 to E-B13)
- `specifications/05-volatility/rates-vol-cube.md`
- `specifications/05-volatility/caps-and-swaptions.md`, `sabr.md`, `black-models.md` (reused, unchanged)
- `specifications/05-volatility/stage-e-targets-b.md`, E4 table

Easy to get wrong (wrong-convention checks): interpolate the SABR parameters, not the vols, on ACT/365F expiry time (not months/12); caplet vols piecewise constant per segment between cap maturities, with `E_ARBITRAGE` when a segment has no positive root; yield vol divides by duration times yield; YoY option time is to the fixing; ZC strike is `(1+K)^T`.

Oracle: 35 of 50 cases (70%) outside-checked by QuantLib 1.44; 34 wrong-convention checks caught. Running spec B outside share (E7 + E4): 53 of 122 (43.4%).

## E7 update after the R5 audit (2026-11-08)

Rulings E-B14 to E-B17 in `specifications/stage-e-rulings-b.md`. Re-read `garch.md`, `variance-swaps.md`, `vix-index.md` (changed sections: checks, acceptance, sources) and the E7 table in `stage-e-targets-b.md`.

What changes for a build:
- Goldens now give non-money outputs their own tolerance through `output_classes` (the existing case format: an output named there uses its class, not the case limit). Variance outputs are compared at 1e-12, not 1e-6. New policy class `likelihood_sum` in `conformance/tolerances/policy.yaml`.
- `vol.vix.term_variance`: the strip may be in any order; if no out-of-the-money put or no out-of-the-money call is selected, `E_INPUT`. A zero bid at the ATM strike still counts for the forward.
- New goldens: `garch_e` 29 cases (was 27), `varswap_e` 33 (was 31), `vix_e` 22 (was 14). Case ids after the insertions moved; refer to them by tag and description, or re-read the files.
- E4 goldens got the same per-output treatment (`ratesvol_e`): no value changed, tolerances on `forward_rate`, `annuity`, `vol`, `sabr`, `strike_ratio` tightened.

Outside share: E7 18 of 84 (21.4%); spec B so far 53 of 134 (39.6%).

## E6 correlation (ready, 2026-11-08)

New operations: `risk.corr.validate`, `risk.corr.nearest`, `risk.corr.implied`, `risk.corr.dispersion`.

Goldens: `datasets/golden/stage_e_b/corr_e.json`, 38 cases (30 ok, 8 error).

Read:
- `specifications/cli-contract.md`, section "Stage E operations, spec B" (E6 row)
- `specifications/stage-e-rulings-b.md` (E-B18 to E-B21)
- `specifications/06-risk/correlation.md`
- `specifications/05-volatility/stage-e-targets-b.md`, E6 table

Easy to get wrong (wrong-convention checks): the nearest matrix needs Dykstra's correction (plain alternating projections, or clipping eigenvalues and rescaling, land elsewhere); converge well past 2e-5 on entries; the implied-correlation denominator counts each pair twice and squares the weights only in the numerator's own-variance term; dispersion legs are variance notionals `N w_i / (2 K_i)`.

Oracle: 18 of 38 (47%) outside-checked by QuantLib 1.44; 29 wrong-convention checks. Running spec B share (E7 + E4 + E6): 71 of 172 (41.3%).

## E8 CDS options, copulas, large pool (ready, 2026-11-08)

New operations: `credit.cdsoption.price`, `credit.cdsoption.implied_vol`, `credit.copula.joint_default`, `credit.lhp.tranche_loss`, `credit.lhp.loss_cdf`.

Goldens: `datasets/golden/stage_e_b/creditopt_e.json`, 96 cases (78 ok, 18 error).

Read:
- `specifications/cli-contract.md`, section "Stage E operations, spec B" (E8 row and batch notes)
- `specifications/stage-e-rulings-b.md` (E-B22 to E-B26)
- `specifications/04-pricing/credit-options-and-copulas.md`
- `specifications/05-volatility/stage-e-targets-b.md`, E8 table

Easy to get wrong (wrong-convention checks): accrual on default runs ACT/360 to the mid date (not half the period); premium ACT/360; option time to expiry; front-end protection only on non-knock-out payers; the t copula is not independence at zero correlation; LHP attachment points are divided by `1 - R`, and `rho` is the asset correlation (loading `sqrt(rho)`); split any fixed quadrature at the kink `m*`.

Oracle: 74 of 96 (77%) outside-checked by QuantLib 1.44; 164 wrong-convention checks.

Spec B outside share, all slices: 145 of 268 (54.1%). Stage-wide with spec A (263 of 410 at b11809f): 408 of 678 (60.2%).

## E8 correction (2026-11-08)

Ruling E-B27: `creditopt_e-0145` (`credit.cdsoption.implied_vol`, `E_DOMAIN`) is now a RECEIVER on the same underlying, premium 1.0 below its zero-vol value 4,859.76. Re-run `creditopt_e`; no other case and no spec text changed.

## Second R5 audit: E4, E6, E8 additions (2026-11-08)

Rulings E-B28 to E-B33 in `specifications/stage-e-rulings-b.md`. Re-read `rates-vol-cube.md` (strip search bounds, YoY zero strike, Bachelier units), `correlation.md` (Higham stopping rule, asymmetric validation, implied-correlation weights) and `credit-options-and-copulas.md` (CDS option schedule: month-end clipping, short final stub).

What changes for a build:
- `rates.cap.strip`: search `[1e-10, 5]` (Black) or `[1e-10, 0.5]` (Bachelier); a root above the upper bound is `E_DOMAIN`.
- `risk.corr.validate`: eigenvalue of `(M + M^T)/2`; flags can be false. `risk.corr.nearest`: stop as Higham with `tol <= 1e-12`; the result must have smallest eigenvalue `>= -1e-10`.
- `risk.corr.implied`: negative weights and fewer than two positive weights are `E_DOMAIN`.
- `credit.cdsoption.*`: schedule dates counted from expiry with the day clipped to the month end; short final stub.
- Goldens grew: `ratesvol_e` 85 (was 50), `corr_e` 49 (was 38), `creditopt_e` 186 (was 96). Case ids moved where cases were inserted (for example the E-B27 case is now `creditopt_e-0145`); docs are updated, so refer to cases by the files.

Outside share under E-B28: spec B 245 of 404 (60.6%); stage-wide with spec A 508 of 814 (62.4%).

## Cross-language SPEC_QUESTIONS rulings (2026-11-08)

Rulings E-B34 to E-B40 in `specifications/stage-e-rulings-b.md`; new suite `datasets/golden/stage_e_b/rulings_e_b.json` (15 cases). Builds change only where a ruling picked another build's reading:
- C++ and Rust: no change for E-B34 (bracket first); Python moves the `vol.vix.index` bracket before the term checks.
- Rust: check `ctd_yield` and `ctd_modified_duration` above 0 (E-B38).
- C++, Java, Rust: `fair_variance < 0` is `E_DOMAIN` (E-B36); `1 + K <= 0` in `zc_price` is `E_DOMAIN` (E-B37).
- Java, Python, C++: `index_vol <= 0` is `E_DOMAIN` (E-B39).
- Every build: negative vol `E_DOMAIN`, zero vol intrinsic, in `rates.bondfut.*` and `infl.cap.*` (E-B38).
`creditopt_e` gained 30 CDS option cases at the end (ids `creditopt_e-0187` onwards; no earlier id moved).

Outside share after these rulings: spec B 277 of 449 (61.7%); stage-wide with spec A at dc16b77 557 of 895 (62.2%).
