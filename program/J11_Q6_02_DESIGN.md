# J-11 design: Q6-02 (redesigned calibration method test) and study rows carrying the daily signal

**Status: design, not implemented (lands in v0.9.0).**

Written 2026-11-13 by the stage J spec lane. Status: **design, not a prereg**. Nothing here is signed; the two drafts in the appendices are for the signer (signing delegated by the owner to Claude, as for Q6-01 and the R3 amendments). No synthetic quote of the new seed has been drawn and no fit has been run while writing this note.

Inputs read: `research/preregs/Q6-01-churn-bound.md` (signed 2026-11-11), `research/q6/q6_output.json` and the docstring of `research/q6/q6_method_test.py` (the published Q6-01 run), `research/preregs/README.md`, `R3-0{1,2,3}` preregs (signal lines only) and their amendments 2, `DEVIATION-2026-11-12.md`, `DEVIATION-2026-11-12-recorder-rule.md`, `tools/recorder/record.py` (study rows), plan 14.6 J-11.

## 1. What stays fixed

- Q6-01 stays failed at 78.4% fit quality against 80% and is never re-run (plan J-11). Its file, hash and output are not touched.
- The three Q6 rules carry over unchanged in meaning: churn bound (median `R_t <= 1.5`, 95th percentile `<= 3.0`), fit quality (at least 80% of test quotes inside the bid-ask), no calendar or butterfly arbitrage on grid `G` at 1e-10. The definitions of `G`, `C_t`, `A_t`, `R_t`, the 0.1 vol point floor and the 20/80 chronological split are taken from Q6-01 by reference.
- The label: "method test on synthetic quotes; real quotes not done".
- The R3 preregs, their amendments 1 and 2, the holdout windows and the pass rules are unchanged by anything below.

## 2. Why the Q6-01 penalty scale was wrong (first principles, from the published design only)

Q6-01 day loss: `L = sum_q ((model_q - mid_q)/h_q)^2 + lambda |G| C_t^2 / 0.001^2`, with 75 quotes a day, `|G| = 45`, quote noise `N(0, (h/2)^2)` plus 10% stale and 2% outlier quotes (the generator's stated design).

1. **Scale of the fit term.** At the true surface each fresh quote contributes `(Z/2)^2`, `Z ~ N(0,1)`, mean 0.25, variance 0.125. Over 75 quotes: mean about 19, standard deviation `sqrt(75 x 0.125) = 3.1`. A change in the fit that costs less than about 3 units is inside the noise of the fit term itself.
2. **Scale of the penalty.** A churn equal to the floor (0.1 vol point) costs `45 lambda`; a churn of 1 vol point costs `4,500 lambda`. At the smallest non-zero grid value `lambda = 0.1` that is 4.5 and 450 units: from 1.5 to 150 times the fit term's noise. So any non-zero `lambda` made the optimiser give up quote fit to hold the surface still, which is what the trial table shows (inside share 0.85 at `lambda = 0`, 0.62 at 0.1, 0.27 at 10).
3. **What the penalty measured.** `C_t` includes the at-the-forward level move. Level moves are real market moves (Q6-01's own `A_t`), so the penalty fought the market, not noise. Churn worth suppressing is the shape change beyond the level move.
4. **The penalty was not the only cause.** The selected `lambda` was 0 and the test-sample share at `lambda = 0` was 0.784. So the failure in Q6-01's single run came from the unpenalised fit, not from the penalty. Arithmetic on the generator's design: fresh quotes (88%) are inside with probability `P(|Z| < 2) = 0.9545`, so 0.840 of all quotes; outliers (2%) are never inside; stale quotes (10%) are inside only when the day's move is small. The ceiling for a perfect model is therefore about 0.84 to 0.87, and the published rms error to truth on the grid (0.0020 vol) is the size of the tightest half-spread (`h = 0.002` at the money), so the fitted surface is not inside the noise. A squared loss lets the 2% outliers at `5h` (each worth 25 units, about 3.7 units per day on average, more than the fit noise) pull the surface. Q6-02 must remove this cause too, or it fails for the same reason whatever the penalty.

## 3. Q6-02 method (new; to be preregistered)

- **Robust fit term.** Huber loss on the normalised error `e_q = (model_q - mid_q)/h_q` with threshold `c = 1` (a quote outside its spread costs linearly). Justification: `c = 1` is the fit-quality rule's own boundary, so the loss is quadratic exactly where the rule counts a quote as good. Not tuned.
- **Shape-only, noise-normalised penalty.** Shape change at node `g`: `u_g = (s_t(g) - s_{t-1}(g)) - (a_t(T_g) - a_{t-1}(T_g))`. Noise scale: `sigma_g = sqrt(2) x` the standard error of `s_t(g)` from quote noise alone, from the previous day's Gauss-Newton covariance `J (J^T W J)^{-1} J^T` with `W = diag(4/h_q^2)` (quote noise sd `h/2`, the generator's stated design). Penalty `P_t = lambda x mean_g (u_g / sigma_g)^2`. At `lambda = 1` a shape change of noise size costs 1 unit, a third of the fit term's noise sd; a shape change three times noise costs 9 units, about three fit-noise sds.
- **Grid, derived before any run:** `lambda` in {0, 1, 3}. Bound: `lambda = 3` makes a noise-sized wiggle cost 3 units, equal to one fit-noise sd, the most the fit term can absorb without a visible loss of fit; larger values repeat Q6-01's error. No value outside the grid without a new prereg.
- **Selection:** as Q6-01 (smallest grid value with selection-sample share >= 80%), so `lambda = 0` is chosen when it suffices.
- **Data:** fresh synthetic quotes from the same SSVI generator design (unchanged noise, stale and outlier rates) with **seed 20261113**, never used by Q6-01 (`20261112`); 60 days, 12 selection days. Generator code frozen by a commit whose hash is in the prereg header before the first draw.
- **Run once**, output beside `q6_output.json` as `q6_02_output.json`; the site shows both, Q6-01 first.

## 4. Power (analytic, no simulation on the new seed)

- Fit quality. Expected share for a model that recovers the truth: 0.840 from fresh quotes plus the stale share inside (bounded below by 0). Test sample: 48 days x 75 = 3,600 quotes. Treating days as the unit (quotes share a day's fit error), take 48 independent day-shares with day-level sd about `sqrt(0.84 x 0.16 / 75) = 0.042`; the sd of the test mean is `0.042 / sqrt(48) = 0.0061`. If the true share is 0.840, `P(share >= 0.80) = Phi(0.040 / 0.0061) = Phi(6.6)`, effectively 1. If the true share is 0.81 (a fit only just better than the threshold), `Phi(1.6) = 0.95`; at 0.80 it is 0.5. So the test has high power to pass a method within one point of the ceiling and is a coin flip at the threshold. The Q6-01 result (0.784) was 2.6 sds below 0.80, so a design that does not move the unpenalised fit cannot pass.
- Churn bound. Under the truth, `R_t` for the true surface is about 1 by construction of the SSVI walk (level move dominant, small `rho` drift); Q6-01 at `lambda = 0` gave median 0.99 and 95th percentile 1.64, both inside the bounds. The penalty is there to keep this when the robust loss is used; the churn rule is not expected to bind.
- Arbitrage: built into the parameterisation; power not applicable (a structural check).

## 5. Study rows carrying the daily signal (recorder, forward log)

Today `tools/recorder/record.py` writes a `study/<id>` row every day with `"position": null, "signal": null` and the day's inputs. Making it carry the signal is not neutral under the preregs:

- Each R3 signal is a z-score over a trailing window `L` (R3-01 and R3-02; R3-03 its seasonal estimate). A forward day's `z_t` in November 2026 uses observations inside the holdout windows (all end 2026-10-30). Computing it is "computing a study statistic or signal on holdout-period data", which amendment 2 and both deviation notes state has not happened.
- The recorder's dated rule (`DEVIATION-2026-11-12-recorder-rule.md`) covers publishing SOFR check rows to 2027-04-30 as general levels. It does not cover signals.

Design (new, needs amendment 3, appendix B):
1. Until the J-2 holdout run of a study is logged (script hash logged before the holdout is read, plan J-2), its forward row keeps `"signal": null` and gains `"signal_status": "withheld: lookback inside holdout until J-2 run"`.
2. After that run, the row carries `signal` (`z_t`), `position` (the rule's position from the parameters selected in-sample under amendment 1) and `params_sha256` (the frozen parameter file). It never carries a P&L claim; the label stays.
3. The forward judgement rule (250 business days; amendment 1's sign and interval rule; v1.1 at about 2027-11-05) is unchanged. Forward days before the J-2 run get their signal back-filled once, by the same script, from recorded inputs only, with `backfilled: true` and the back-fill commit hash.
4. `research/holdout_scan.py` gains a rule: a row with a non-null `signal` dated before the study's J-2 run hash is a failure.

## 6. Preregistered vs new

| Item | Status |
|---|---|
| Q6 rules 3, 4, 5 (churn bound, fit quality, arbitrage), grid `G`, definitions, 20/80 split, selection rule | Preregistered in Q6-01; reused by reference |
| Q6-01 result 78.4%, FAIL | Published; unchanged |
| Huber fit term, shape-only noise-normalised penalty, grid {0, 1, 3}, seed 20261113, output file | New: prereg Q6-02 (appendix A) |
| R3 signals, parameters, holdout windows, pass rules, forward judgement | Preregistered (R3 preregs, amendments 1 and 2); unchanged |
| Signal withheld until the J-2 run, then carried with back-fill; scan rule | New: amendment 3 to each R3 study (appendix B), one shared text |
| J-2 holdout run itself | Preregistered procedure; run script hash logged first (plan J-2) |

## Appendix A: draft prereg `Q6-02-robust-shape-penalty.md` (unsigned)

Header for the signer: `Status: draft, unsigned.` On signing: SHA-256 of the body, SHA-256 of `Q6-01-churn-bound.md` (whole file), the commit hash of the frozen generator and runner, and "no quote of seed 20261113 has been drawn and no fit run at signing". Add the file to `research/test_preregs.py` and the next timestamp stamp.

Body (to be copied below the `<!-- body -->` marker):

> Plan item J-11 (QUANTFORGE_PLAN.md 14.6). Q6-02 is a new method test on synthetic quotes. Q6-01 (signed 2026-11-11) failed at 78.4% fit quality and stays published; it is not re-run. Label: method test on synthetic quotes; real quotes not done.
>
> Reused from Q6-01 by reference, unchanged: grid `G`; `C_t`, `A_t`, `R_t` and the 0.1 vol point floor; rules 3 (churn bound), 4 (fit quality 80%) and 5 (arbitrage at 1e-10); the 20/80 chronological split; the selection rule (smallest grid value with selection-sample share at least 80%); rule 6 (pass only if 3, 4 and 5 hold).
>
> Changed, with reasons (design note `program/J11_Q6_02_DESIGN.md` section 2): day loss `sum_q huber_1((model_q - mid_q)/h_q) + lambda mean_{g in G} (u_g / sigma_g)^2`, `huber_1(e) = e^2/2` for `|e| <= 1`, `|e| - 1/2` otherwise (this is the squared loss halved inside the spread, so `lambda` is in the same units), `u_g` the shape change net of the same-expiry at-the-forward move, `sigma_g = sqrt(2)` times the quote-noise standard error of `s_{t-1}(g)` from the previous day's Gauss-Newton covariance with quote noise sd `h/2`. On the first day there is no penalty. Grid `lambda` in {0, 1, 3}; every evaluated value is logged as a trial.
>
> Data: the generator of `research/q6/q6_method_test.py` at the frozen commit, seed 20261113, 60 days, unchanged noise, stale (10%) and outlier (2%) rates. Run once; output `research/q6/q6_02_output.json`, published beside Q6-01.
>
> Power (analytic, design note section 4): a method within one point of the 0.84 ceiling passes rule 4 with probability above 0.95; at the threshold, 0.5.

## Appendix B: draft amendment 3 (one text for R3-01, R3-02, R3-03; unsigned)

Header for the signer: amended prereg and amendments 1 and 2 by file SHA-256; common rules body SHA-256; both deviation notes by file SHA-256; "no signal has been computed on any date at signing".

> Amends the prereg and amendments 1 and 2; they stand except where this text differs. Source: plan J-11 (study rows carrying the daily signal).
>
> 1. The forward-log study row keeps `signal: null` until this study's holdout run (plan J-2) is logged with its script hash. Until then the row says `signal_status: withheld: lookback inside holdout until J-2 run`. Reason: the trailing window `L` of a forward day reaches into the holdout window.
> 2. After the J-2 run the row carries `signal`, `position` and `params_sha256` computed from recorded inputs only by the frozen script. Days between the forward log's start and the J-2 run are back-filled once, marked `backfilled: true` with the back-fill commit hash.
> 3. The forward judgement (250 business days, amendment 1's rule) and the holdout windows, grid, costs and pass rule are unchanged.
> 4. `research/holdout_scan.py` fails on a non-null `signal` dated before the J-2 run hash of its study.
