# Stage J gap list after wave 1 (2026-11-14)

What stage J (v0.9.0) still owes after wave 1 (backtester, purged CV and CPCV counts, Viterbi labels, PSR, DSR, PBO, power: all four builds, `program/STAGE_J_HANDOVER.md` "WAVE 1 READY") and after J-0, J-0b, J-0c, J-11 and R3 (done). Sources read: `QUANTFORGE_PLAN.md` section 4 row J, 11.3, 12.5, 12.10 (A3, A4 cells), 14.5, 14.6, 14.10.

Columns: **Kind** is `CLI` (a contract operation, built in Python, Rust, Java and C++ with goldens) or `Py` (the Python research package `quantforge_research`, or research scripts and reports; no other language). **Size** in plan-days. **Call**: ship in v0.9.0, or defer, with the reason.

## Gap table

| # | Item | Plan reference | Kind | Size | Call |
|---|---|---|---|---|---|
| G1 | Mean-variance optimiser with budget and box constraints | row J; 12.5; 14.6 J-5 | CLI | 3 | **v0.9.0, wave 2.** Specified: `portfolio.opt.mean_variance` |
| G2 | Risk parity (risk budgets) | row J; J-5 | CLI | 2 | **v0.9.0, wave 2.** Specified: `portfolio.opt.risk_parity` |
| G3 | Euler risk contributions | 14.5; J-8 | CLI | 0.5 | **v0.9.0, wave 2.** Specified: `risk.contrib.euler` |
| G4 | Ledoit-Wolf shrinkage | row J (Bayesian estimation); J-6 | CLI | 1 | **v0.9.0, wave 2.** Specified: `portfolio.est.ledoit_wolf`. The scikit-learn check of J-6 is oracle-only and still to run (no scikit-learn in the oracle environment on 2026-11-14) |
| G5 | Black-Litterman posterior | row J; J-6 | CLI | 1 | **v0.9.0, wave 2.** Specified: `portfolio.est.black_litterman` |
| G6 | Acerbi-Szekely ES backtest statistic | 14.5; J-8 | CLI | 1 | **v0.9.0, wave 2.** Specified: `risk.backtest.es_z2`. The size study (2,000 simulated paths, within 3 SE of nominal) is a research script, G13 |
| G7 | Baum-Welch for a Gaussian HMM | 12.5 A4; 12.10 A4 | CLI | 3 | **v0.9.0, wave 2.** Specified: `research.regime.baum_welch`. 12.10 asks for parameters equal across languages to 1e-9, which only a ported operation can show. The T = 5,000 recovery run is a research script, G12 |
| G8 | Markov-switching AR(1) | 12.5 A4; 12.10 | Py | 3 | **Defer within v0.9.0 to the research lane, not wave 2.** 12.10 asks for the same tolerances "on its own frozen parameters", which needs frozen parameters first; descriptive only, no trading use. If the research lane has not frozen them by the J tag, defer to H with the reason recorded |
| G9 | Drift detectors (PSI, KS, CUSUM, Page-Hinkley) | 12.5 A3; 12.10 A3 | Py | 2 | **v0.9.0, research lane.** 12.10 requires `research/prereg/A3-drift.md` **frozen before code**, so this spec lane writes no `drift.py`; the prereg comes first, then code, then the ARL and delay runs |
| G10 | Walk-forward splits | 12.5 A1 | Py | 0.5 | **Done here.** `python/quantforge_research/cv.py`, tests in `python/tests/test_quantforge_research.py` |
| G11 | Trial-count registry feeding DSR | 12.5 Q7 | Py | 0.5 | **Done here.** `python/quantforge_research/trials.py` reads `research/trials.csv`; a study's `N` for `research.stats.dsr` comes from it (J-13) |
| G12 | A4 recovery and bit-reproducibility run (T = 5,000, seed 20261109) | 12.10 A4 | Py | 1 | v0.9.0, research lane, after G7 lands in Python |
| G13 | ES backtest size study (2,000 paths) | J-8 | Py | 0.5 | v0.9.0, research lane, after G6 lands in Python |
| G14 | Reality Check (White 2000) against a benchmark | J-4 | Py | 1.5 | **Done here** (statistic and stationary-bootstrap p-value): `python/quantforge_research/snooping.py`. Not a CLI operation: the bootstrap needs a shared random stream across four languages for no gain, and the plan asks only for a size property on simulated nulls. Size check with 200 simulated null sets in the test file; the full 5 % size study at publication scale stays with the research lane |
| G15 | Factor optimisation (mean-variance on factor exposures) | row J; J-5 | Py | 1 | v0.9.0 research lane, as a use of G1 with a factor covariance `B F B' + D`; no new operation needed |
| G16 | Ken French portfolios study, labelled "academic portfolio returns, not tradable"; data fetched at run time, never committed | J-5 | Py | 1 | v0.9.0 research lane, after G1 and G2 land in Python |
| G17 | Section 12 methods: misspecification, proxy data, benchmark model, parameter stress, shadow run, staged rollout (simulated), new-model checklist | row J; J-7 | Py | 4 | v0.9.0 research and docs lanes: one scripted example each on a released model with the pass rule written before the run. No new operation |
| G18 | Scenario stress engine and historical shock library (2008, 2013, 2020, 2022) with replay | 14.5; J-8 | Py, maybe CLI later | 3 | **Wave 3** (handover wave plan). Needs Treasury par-yield history on the named dates and a check of those dates against the prereg holdout windows (14.10 rule 6) before anything is committed. Replay can use existing curve and risk operations; a CLI operation only if wave 3 finds the replay cannot be expressed with them |
| G19 | Factor and sector exposure; carry and roll-down | 14.5 | CLI | 2 | **Defer to K.** No acceptance test in J-8 names them; carry and roll-down overlap the R2 P&L explain (`06-risk/pnl-explain.md`). K-8 is the next row that lists 14.5 leftovers |
| G20 | Held-out-strike surface backtest; leave-one-out interpolation backtest | 14.5 | Py | 1.5 | Wave 3, research lane, on existing surface operations. No new operation |
| G21 | Point-in-time feature store with content-hashed manifests | 12.5 A6 | Py | 2 | v0.9.0 research lane (handover "Not in wave 1") |
| G22 | AI-assistance section checked by `quality_gate` | 12.5 A8 | Py (tool) | 0.5 | v0.9.0 research lane. `research/TEMPLATE.md` section 7 exists; `tools/quality_gate.py` does not check it yet (grep 2026-11-14). 14.10 rule 1: the check counts only after a run shows it failing on a report with the section removed |
| G23 | Signals, features, performance metrics, regime views, signal and RV screens, simulation harness | row J | Py | 3 | Partly covered (backtester metrics, Viterbi labels). The rest is research-package scope; ship what the R3 and section 12 examples use, list the remainder as known issues at the J tag |
| G24 | Survivorship statement | 12.5 Q7 | docs | 0.2 | v0.9.0 docs lane: one paragraph in `11-research/backtester.md` Limitations and the study template |
| G25 | Day-60 forward check, about 2027-02-05 | J-9 | Py | 0.2 | **Not before its date.** Recorded as a pipeline check only; if the J tag is earlier, the tag lists it as pending with the date |
| G26 | Stage evidence close-out | J-10; 14.10 rules 1-6 | process | 3 | v0.9.0 coordinator: outside share per operation (wave 2 included), fresh mutation run, different-model audit, E1 goldens, tutorials, CHANGELOG with evidence paths |
| G27 | Model inventory rows MI-J1 to MI-J4, plus wave 2 rows | handover | docs | 0.3 | v0.9.0 docs pass |

## What wave 2 specifies

Seven CLI operations (G1 to G7), rulings `specifications/stage-j-rulings-w2.md` J-W2-1 onwards, contract 1.14.0, suites `optim_j`, `estim_j`, `esbt_j`, `baumwelch_j` in `datasets/golden/stage_j/`, generator `oracle/python/gen_stage_j_w2.py`. Hand-over: `program/STAGE_J_HANDOVER.md` "WAVE 2 READY".

## Sizes

Wave 2 language work: about 10 plan-days per language for G1 to G7. Python research items done here (G10, G11, G14): about 2.5 plan-days. Remaining research-lane items for v0.9.0 (G8, G9, G12, G13, G15 to G17, G21 to G24): about 18 plan-days. Wave 3 (G18, G20): about 4.5 plan-days.
