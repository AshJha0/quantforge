# J-11 review: Q6-02 design and the two drafts (prereg Q6-02, R3 amendment 3)

Reviewer: Claude (lane J-11, 2026-11-14), independent of the spec lane that wrote `program/J11_Q6_02_DESIGN.md`. Read: the design note, `Q6-01-churn-bound.md`, `research/q6/q6_method_test.py` and `q6_output.json`, the R3 preregs, amendments 1 and 2, both deviation notes, `research/test_preregs.py`, `tools/forward-log/anchor.py`. No quote of seed 20261113 was drawn and no Q6-02 fit was run while reviewing (`git log` shows no Q6-02 code before this lane).

## Forking paths

1. **The redesign is chosen after seeing Q6-01's outcome** (seed 20261112: trial table, inside share 0.784). That is the purpose of J-11 and is stated openly; it is acceptable only because the confirmatory run uses a fresh seed (20261113) and Q6-01 stays published as failed. Q6-02 is a new test of a new method, not a rescue of Q6-01. Kept, with this said in the prereg's "Prior knowledge" line.
2. **Huber threshold `c = 1`** is tied to the fit-quality rule's own boundary, not tuned. Acceptable.
3. **Grid {0, 1, 3}** is derived from the fit-noise arithmetic of section 2, not from any Q6-02 result. Acceptable, but see finding U1: the arithmetic used the wrong units.
4. **Risk of quiet pilot runs on the new seed.** Nothing in the draft forbade running the new runner on seed 20261113 "to check it works". Fixed: the runner refuses that seed unless the signed prereg and frozen file hashes match, refuses a second run, and unit tests use other seeds only.

## Units and power (recomputed)

- **U1 (wording/definition error, fixed before signing).** Draft A defines `huber_1(e) = e^2/2` inside the spread and claims this keeps `lambda` "in the same units" as the squared loss. It does not: halving the fit term halves its noise (fresh-quote fit term per day mean 9.4, sd `sqrt(75/32) = 1.53`), so every scale argument in design section 3 (lambda = 1 costs a third of a fit-noise sd, lambda = 3 costs one) would be off by a factor of two. Fix, chosen without any data: fit term `rho(e) = e^2` for `|e| <= 1`, `2|e| - 1` otherwise (twice the Huber function). It equals Q6-01's squared loss inside the spread, so section 2's arithmetic (mean 19, sd `sqrt(75 x 0.125) = 3.06`) and the grid bound hold as written.
- **Power.** Day-share sd `sqrt(0.84 x 0.16 / 75) = 0.0423`; test mean sd `0.0423 / sqrt(48) = 0.0061`. `P(share >= 0.80)`: at 0.84, `Phi(6.5)`; at 0.81, `Phi(1.64) = 0.95`; at 0.80, 0.5. The arithmetic is correct. **Caveat (P1):** the day sd is binomial, which assumes quotes within a day are independent, while the note itself says quotes share the day's fit error; and stale quotes depend on the day's move. Q6-01's own selection and test shares at `lambda = 0` (0.847 and 0.784, 48 test days) differ by about 10 of these sds, so the true sampling variance is larger than 0.0061 and the 0.95 figure is optimistic. Stated as such in the prereg; it does not change any rule.
- Q6-01's 0.784 is `(0.800 - 0.784) / 0.0061 = 2.6` sds below the threshold: correct under the same caveat.

## Precision gaps (fixed in the drafts before signing; none depends on results)

- **G1 `sigma_g`.** `J (J^T W J)^{-1} J^T` named one `J` for two Jacobians. Now: `J_q` = derivative of the 75 model quote vols, `J_g` = derivative of the 45 grid vols, both with respect to the 7 unconstrained fit parameters at day `t-1`'s fit, central differences step 1e-6; `Sigma = pinv(J_q^T W J_q)` (rcond 1e-10), `W = diag(4 / h_q^2)` over all of day `t-1`'s quotes; `sigma_g = sqrt(2 (J_g Sigma J_g^T)_gg)` floored at 1e-6; fixed during day `t`'s optimisation.
- **G2 `u_g`.** `a(T_g)` is the fitted at-the-forward vol (`k = 0`) at the node's expiry, same day's fit.
- **G3 restarts.** Q6-01's code fits the selection and test samples as separate runs, each starting from the moment-based start `x_start` with no penalty on the sample's first day; test churn uses the 47 test days that have a previous test day. Now written.
- **G4 selection.** Q6-01's text and code differ slightly (code also needs the churn bound on the selection sample). Q6-02 states the code's rule: smallest `lambda` with selection share >= 0.80 **and** churn bound met on the selection sample; all three values evaluated and logged; none met means FAIL.
- **G5 optimiser and draws.** L-BFGS-B (scipy defaults), warm start from the previous day; quotes drawn by `truth_path` then `quotes` in Q6-01's order from `numpy.random.default_rng(20261113)`.
- **G6 freeze.** The prereg header records the SHA-256 of the runner and the generator file and the commit that froze them; the runner checks both before the real run.
- **G7 logging before the run.** Draft A said "every evaluated value is logged as a trial" but not when or where. Now: rows `Q6-02-T01..T03` are committed to `research/trials.csv` before the run; the output records that commit.

## Amendment 3

- **A1.** "The J-2 run hash" had no defined record in this repo. Now: a line in `research/holdout_runs.csv` (study, UTC date, script path, script SHA-256, commit) committed before the holdout is read; "before the J-2 run" means a row date earlier than that line's date.
- **A2.** The `signal_status` string, the fields after the run and the back-fill marker are now exact. The scan rule is required before the first row carries a non-null signal (today every row is null, so nothing fails yet).
- **A3.** Added the "Prior knowledge" paragraph the repo's prereg test requires of every amendment.

## Signing

Signing is delegated by the owner to Claude (README, Q6-01, R3 amendments); no owner key is used anywhere in the repo's process (SHA-256 in the header, checked by `research/test_preregs.py`; OpenTimestamps stamps are made by the recorder workflow's anchor step, which picks up every prereg file). So signing does not need an owner-only action.
