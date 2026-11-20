# Stage K rulings, K-9 review fixes (lane k-v1-rev1): PROPOSED 2026-11-20

Status: **PROPOSED**, not confirmed. Each row changes a behaviour that a golden or a spec states; the coordinator confirms or rejects it.

**Numbering check (read 2026-11-20 with `git grep -E "KR-3[4-9][0-9]"` over every remote branch after `git fetch`).** No branch uses KR-340 to KR-399. This lane takes KR-340 to KR-349.

Source of the findings: the K-9 different-model review of stages A to J, coordinator's record `institutional-quant-engine-plan/STAGE_K_K9_REVIEW_PART1.md` (findings 1, 7, 8, 12, 19, 21, 22).

| ID | Topic | Ruling |
|---|---|---|
| KR-340 | SABR `chi(z)` (finding 7) | `vol.sabr.hagan` evaluates `chi` by the cancellation-free form in `specifications/05-volatility/sabr.md` (hypot, `log1p`, the `s + z - rho` rearrangement) in all four builds; the series switch at `|z| < 1e-7` stays. Measured: the direct form's relative error in `m` was 2.7e-9 at `z = 1.01e-7` and up to 1e-4 at `z = -3.7e6`; the new form 3 ulp or less. Goldens `sabrz_k` (32 cases, relative limit 1e-12); 22 of them fail the old Python build |
| KR-341 | Implied vol acceptance (finding 8) | `vol.option.implied` (and every caller of the same solver, such as `vol.sabr.arbfree`) returns `v` only if the estimated relative vol error `e` in `specifications/05-volatility/black-models.md` is at most `1e-10`, else `E_NO_CONVERGENCE`; the solve is Newton on `ln V - ln price` in a bracket. Before: Python and Java returned vols 2 % to 29 % wrong for prices below about `1e-199` (goldens `ivdeep_k-0008` to `-0010`, `-0012`). No existing golden moves: their largest `e` is `1.9e-13` |
