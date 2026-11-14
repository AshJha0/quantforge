# Q6-02: robust fit and shape-only churn penalty, method test on synthetic quotes

Status: **signed**. Signed by Claude (stage J lane J-11; signing delegated by the owner, as for Q6-01 and the R3 amendments) on 2026-11-14.
- SHA-256 of the body below the marker line: `6e3935a49ee77a90183fa3abb07fa573f69287bd20e093b365313d268e70efa1`
- SHA-256 of `Q6-01-churn-bound.md` (whole file): `c2700712e02141586d9e5a3d5301a348d1d3e1d20305a65e3eaebb5fce46e198`
- SHA-256 of `q6_02_method_test.py` (whole file): `78c66a68ac04ed395e9694e6ea6d07d5577375d356937d2f9a97b63bbbe2c63f`
- SHA-256 of `q6_method_test.py` (whole file): `db00dc4e08f1daddb11ad6955b14ce21214cad68f469530d928f672af663ff21`
- Generator and runner freeze commit: `72e780c13dea14cf066b0f98d732e9a2df4dcf00`
- No quote of seed 20261113 has been drawn and no Q6-02 fit has been run at signing.
- This file is not edited after signing; a change is a new prereg.

<!-- body -->
Plan item J-11 (QUANTFORGE_PLAN.md 14.6). Q6-02 is a new method test on synthetic quotes. Q6-01 (signed 2026-11-11) failed at 78.4% fit quality and stays published; it is not re-run. Label: *method test on synthetic quotes; real quotes not done*. The R3 common rules in `README.md` are not part of this prereg (no trading signal is tested).

## Prior knowledge

The method below was designed after the Q6-01 result on seed 20261112 was published (`program/J11_Q6_02_DESIGN.md` section 2; review `program/J11_REVIEW.md`). That is why a fresh seed is used. No quote of seed 20261113 has been drawn and no Q6-02 fit has been run on any seed of 60 days; the unit tests of the runner use other seeds and at most 15 days.

## Reused from Q6-01 by reference, unchanged

Grid `G` (45 nodes); `C_t`, `A_t`, `R_t` and the 0.1 vol point floor; rule 3 (churn bound: test-sample median `R_t <= 1.5` and 95th percentile `<= 3.0`); rule 4 (at least 80% of test-sample quotes with `|model - mid| <= h`); rule 5 (no calendar or butterfly arbitrage on `G` on every test day, to 1e-10); rule 6 (pass only if 3, 4 and 5 hold; a failure is reported with the same prominence). The generator, the grid and arbitrage checks and `x_start` are the functions of `research/q6/q6_method_test.py` at the freeze commit.

## Method

1. **Data.** `numpy.random.default_rng(20261113)`; `truth_path(60, rng)` then, day by day, `quotes(truth_t, rng, previous day's mid)` (Q6-01's draw order); unchanged noise `N(0, (h/2)^2)`, 10% stale, 2% outliers at `+-5h`. Selection sample: the first 12 days; test sample: the other 48.
2. **Fit term.** `e_q = (model_q - mid_q) / h_q`; `rho(e) = e^2` for `|e| <= 1`, `2|e| - 1` otherwise (twice the Huber function with threshold 1, so equal to Q6-01's squared loss inside the spread). Day fit term `sum_q rho(e_q)` over the day's 75 quotes.
3. **Penalty.** Shape change at node `g`: `u_g = (s_t(g) - s_{t-1}(g)) - (a_t(T_g) - a_{t-1}(T_g))`, `a(T)` the fitted vol at `k = 0` and expiry `T` of the same day's fit. Noise scale: with `x` the 7 unconstrained fit parameters of day `t-1`, `J_q` (75 x 7) and `J_g` (45 x 7) the central-difference derivatives (step 1e-6) of the model quote vols and of the grid vols, `W = diag(4 / h_q^2)` over all of day `t-1`'s quotes, `Sigma = pinv(J_q^T W J_q)` (relative cutoff 1e-10), `sigma_g = max(sqrt(2 (J_g Sigma J_g^T)_gg), 1e-6)`, computed once and held fixed during day `t`'s optimisation. Penalty `lambda * mean_{g in G} (u_g / sigma_g)^2`.
4. **Fit.** Day loss = fit term + penalty, minimised by scipy L-BFGS-B with default settings, warm-started from the previous day's parameters. Each sample is fitted as a separate run starting from `x_start` of its first day, with no penalty on that first day; `R_t` is computed for each day with a previous day in the same sample (11 selection, 47 test ratios).
5. **Grid and trials.** `lambda` in {0, 1, 3}. No value outside the grid without a new prereg. All three are evaluated on the selection sample and logged; rows `Q6-02-T01..T03` (`lambda=0`, `1`, `3`) are committed to `research/trials.csv` before the run.
6. **Selection.** The chosen `lambda` is the smallest grid value whose selection-sample share (rule 4) is at least 80% and whose selection-sample `R_t` meets rule 3. If none, Q6-02 fails. The test sample is fitted once with the chosen value.
7. **Run once** by `python research/q6/q6_02_method_test.py`, which refuses unless this file is signed and unchanged, the runner and generator match the hashes in its header, the trials are logged and `research/q6/q6_02_output.json` does not exist. Output `research/q6/q6_02_output.json`, published beside Q6-01 (Q6-01 first). The RMS error to the true surface is reported for information only.

## Power (analytic)

Expected test share for a model that recovers the truth: 0.840 from fresh quotes (0.88 x `P(|Z| < 2)`) plus stale quotes inside. With 48 test days of 75 quotes and a binomial day-share sd `sqrt(0.84 x 0.16 / 75) = 0.042`, the test mean has sd 0.0061: `P(share >= 0.80)` is `Phi(6.5)` at 0.84, 0.95 at 0.81 and 0.5 at 0.80. This treats quotes within a day as independent; they share the day's fit error, so the true sd is larger (Q6-01's selection and test shares at `lambda = 0` differed by 0.063) and these powers are optimistic. The churn rule is not expected to bind at `lambda = 0` (Q6-01: median 0.99, 95th percentile 1.64). The arbitrage rule is structural.
