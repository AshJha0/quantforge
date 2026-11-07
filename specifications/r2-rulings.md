# R2 rulings

Rulings by the spec session in phase R2, from the R2 audit (`R5_R2_AUDIT.md` section 1, outside the repo). Normative.

| # | Point | Ruling |
|---|---|---|
| R2-A1 | Risk sign | Risk is `dV/d(bp)` for rates up. A receiver's DV01 is negative, a payer's positive. The text was wrong and the goldens right; no golden changes |
| R2-A2 | Stability S7 for least-squares fits | Judged against the noise: RMS repricing `<= rms_0 + 1.5 a`. Exact-fit bootstraps keep a solve tolerance |
| R2-A3 | P&L explain floor | `threshold = 0.05 max(|full_pnl|, gross_risk_pnl) + 1e-8 N`. The floor scales with the move, so quiet days cannot pass vacuously; new output `gross_risk_pnl`. `pnl_r2` regenerated: 42 of 44 cases change numbers, and no `explained` flag changes |
| R2-A4 | Threshold status | The 5% level is a project choice, not FRTB P&L attribution. The real-data run reports Spearman and KS over the window, unjudged |
| R2-A5 | Rich/cheap weights | `w = 1/D_mod^2` (duration-scaled errors), after GSW (2007) and the BoE (Anderson and Sleath 2001) |
| R2-A6 | Rich/cheap exclusions | Treasury on-the-run and first off-the-run issues per auction tenor get weight 0 in the fit; their residuals are still reported. Gilts: none excluded |
| R2-A7 | Stability S3 | Gaussian noise `N(0, a^2)` from `core.rng`; a stated amplitude per input type; a units table for `A` |
| R2-A8 | Jacobian basis | Rows are continuously compounded zeros on ACT/365F curve time; columns are par quotes as decimal rates |
| R2-A9 | Stability C3 | Judged on model prices from the op's `residuals`; the tool evaluates no Nelson-Siegel formula. No new op in R2 |
| R2-A10 | Stability C6 | Vol noise applied at `T = 1` (SVI calibration has no expiry input) |
| R2-A11 | Workflow (b) data | Blocked: TreasuryDirect robots.txt and terms, and the DMO anti-bot page. Manual `--data` path; a BLOCKED report without it |
