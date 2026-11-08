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

Oracle: 18 of 72 cases outside-checked by QuantLib 1.44 (all `q = 0` replication cases); the rest by hand cases, 50-digit or exact-rational replicas and a separate float replay. 74 wrong-convention checks caught. Running spec B outside share: 18 of 72 (25%); E4 and E8 carry the QuantLib-heavy work towards the 60% floor.
