# R6 oracle lane 2 hand-over (branch `r6-oracle2`, stages F and G)

Updated 2026-11-12. Nothing pushed. No new golden cases were added (conformance totals unchanged). `r6-evidence` at `b9b2b3c` is merged in (value-only floor, owner 2026-11-12).

## Shares (value-checked cases; old all-case figure beside it; no sweeps)

| Stage | Before (value) | After (value) | Old all-case before / after | With added cases |
|---|---:|---:|---:|---|
| F | 165 / 417 = 39.6% | 202 / 417 = 48.4% | 31.4% / 38.5% | none added |
| G | 332 / 463 = 71.7% | 371 / 463 = 80.1% | 56.4% / 63.0% | none added |

**F is under the 60% floor (needs 251, has 202).** See "Shortfall" below: the classes with no free outside reference hold 140 of the 417 value cases, so 60% would need 251 of the remaining 277 (91%), including plain arithmetic operations. Not reachable by genuine checks without a ruling.

**G without the suite-count assumption.** Four suites now have a real per-case register (`oracle/OUTSIDE_G_R6.json`, loaded by `tools/outside_shares.py` `load_percase_g`): bermudan_g, callable_g, hwcal_g, aadladder_g and barrier_g. The other G suites still hold counts. Those counts come from generator loops that only run the outside check on `ok` cases (for example `gen_stage_g_w1.py` r9, g2a, g2b), so "counted cases are value cases" holds by construction there, not by assumption; a full per-case regeneration of every G generator is still open. Counting only per-case-proven value cases plus suites whose generator proves it gives the same 353.

## Per operation (changes only)

| Op | Before | After | Library | Tolerance and why | Disagreements |
|---|---:|---:|---|---|---|
| `risk.backtest.kupiec` (F) | 0/20 (reimpl) | 20/20 | scipy 1.18.1 `minimize_scalar` bounded Brent maximising the Bernoulli likelihood; `chi2.sf` | judged by the golden's own tolerance (max gap 4.8e-11); Brent xatol 1e-15 | none |
| `risk.backtest.christoffersen` (F) | 0/17 (reimpl) | 17/17 | same, Markov-chain likelihood maximised numerically; numpy transition counts | as above; transitions exact | none |
| `rates.shortrate.bermudan_swaption` (G) | 0/10 | 10/10 | QuantLib 1.44 `FdHullWhiteSwaptionEngine` (Douglas 800x801, 1600x1601; implicit Euler at the golden grid) | `3 |QL_grid - QL_fine| + 3 |QL_fine - QL_finer| + 1e-6 |v|`: the golden is a first-order implicit scheme; QuantLib's own implicit Euler at the same grid measures that error | none |
| `rates.shortrate.callable_bond` (G) | 0/8 | 8/8 | QuantLib 1.44 `TreeCallableFixedRateBondEngine` 2000 and 4000 steps | `3 e_grid + 3 |tree2000 - tree4000|`; `e_grid` the scheme's straight-bond-limit error at 100 steps/yr (BERMUDAN_EVIDENCE_G); QuantLib has no FD callable engine | none |
| `rates.shortrate.hw_calibrate` (G) | 0/3 | 3/3 | scipy bounded Brent on QuantLib `HullWhite.discountBondOption` (Jamshidian) | sigma 2e-8 relative (optimiser resolution at a quadratic minimum); prices 1e-7 relative; rmse 1e-6 relative | none |
| `rates.shortrate.bermudan_ladder` (G) | 0/3 | 0/3 | QuantLib FD + central bump-and-revalue | as Bermudan | **finding for the spec lane**: price agrees; `d_price_d_mean_reversion` (case 1: golden -52,528, gap 900, tol 322) and several `d_price_d_discount_factors` disagree (case 1 entry 1: golden 191,964, gap -30,380, tol 2,119; entry 2 gap 16,700; entry 3 gap 11,880; case 2 entry 1 gap -12,150; case 3 entry 2 gap -17,830). Probably the adjoint of the piecewise-flat forward in `alpha(t)` versus QuantLib's curve-bump response; not resolved. Goldens unchanged. Numbers in `oracle/OUTSIDE_G_R6.json` |
| `exotic.barrier.price` (G) | 2/31 | 22/31 (2 continuous by AnalyticBarrierEngine at 1e-10, 20 discrete by MC) | QuantLib 1.44 `MCPRBarrierEngine`, one step per monitoring date, no bridge (exact discrete contract), 200k antithetic paths | 3 MC standard errors (repo R9 rule); BGK rows outside 3 SE are recorded as BGK approximation gaps, not counted; rebate rows skipped (QL MC pays no rebate) | 6 BGK rows outside 3 SE (approximation error of the continuity correction at coarse monitoring, not a golden error; spec lane may want to document the BGK accuracy limit): 0005 DOWN_OUT PUT m=52 z +5.6; 0006 DOWN_OUT PUT m=12 z +25.0; 0012 DOWN_IN PUT m=12 z -3.7; 0014 UP_OUT CALL m=52 z +5.5; 0015 UP_OUT CALL m=12 z +20.1; 0021 UP_IN CALL m=12 z -4.7. 3 rebate rows not checked |

## Gate (task item 3)

`tools/outside_shares.py` reads the per-case G file; `tools/test_outside_shares.py` plants a per-case downgrade (count drops) and a downgrade that takes G under 60% (floor fails): both caught, 0 failures. **Open:** add `uv run --frozen python -W ignore outside_g_r6.py` (about 15 min, mostly the aadladder bumps) and `outside_g_barrier_r6.py` to `oracle-coverage.yml` and diff `oracle/OUTSIDE_G_R6.json`; I did not edit the workflow because the evidence lane owns it. `outside_f.py` (already in CI) now produces the SCIPY.MLE rows.

## Shortfall: value classes with no free outside reference (F)

| Class | Value cases | Reason |
|---|---:|---|
| FRTB SA (`risk.frtb.*`) | 43 | Basel MAR21 aggregation; no free library implements it (ISDA SIMM/FRTB engines are licensed) |
| Book lifecycle and marks | 23 | position accounting rules of this platform; no library object |
| CDS index option (Pedersen) | 54 | QuantLib 1.44 `CdsOption` is single-name with FEP added outright; F, A, FEP, h_K, A_K are QuantLib-checkable but price, adjusted pair and upfront are the spec's algebra (ruling E-B28 precedent: not counted) |
| Traffic light | 20 | `cumulative_probability` is checkable, but `plus_factor` is the Basel 1996 table (published value, class none) |

Remaining uncounted F value cases (about 75, small operations: curve inspect 11, ois sensitivity 5, jtd 5, dividend/borrow 5, vix 8, dupire 4, MC VaR 4, others) have candidate checks but even all of them leave F at about 66% only if every one passes; not done in this session.

## Files

New: `oracle/python/outside_f_r6.py`, `oracle/python/outside_g_r6.py`, `oracle/python/outside_g_barrier_r6.py`, `oracle/OUTSIDE_F_R6.json`, `oracle/OUTSIDE_G_R6.json`. Changed: `oracle/python/outside_f.py` (Kupiec, Christoffersen handlers; SCIPY.MLE row), `oracle/outside_register_f.json`, `oracle/CONVENTION_MAP_F.md`, `tools/outside_shares.py` (SCIPY.MLE primitive row, per-case G loader), `tools/test_outside_shares.py`, `oracle/OUTSIDE_SHARES.{json,md}`. Installs: none blocked (statsmodels, highspy, cvxpy not needed and not installed).
