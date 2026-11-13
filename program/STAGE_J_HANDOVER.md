# Stage J handover

**Status: specified, not implemented (wave 1 code lands in v0.9.0).** In v0.8.3 only this document ships; the stage J goldens, CLI contract block and name-map entries it mentions are not in this release.

From the stage J spec and oracle session to the four language sessions and the lanes. Append-only. Each wave section says what a language session may read. Never read anything under `oracle/`: that is the oracle, and reading it breaks the clean room.

Stage J (v0.9): research and backtesting (plan section 4, row J; 11.3; 12.5 Q7, A1, A4; 14.6 J-1 to J-11). All stage J goldens are in `datasets/golden/stage_j/`, run through `conformance/runner/runner.py` (it finds them by suite name). Always read `specifications/cli-contract.md` (block "Stage J operations", contract 1.13.0) and `specifications/stage-j-rulings-w1.md` with any stage J slice; the J-0b fuzz rulings are in `specifications/stage-j-rulings.md` on branch `stage-j-fuzz`. Stage F rules F-1 to F-3, F-5, F-6 and R6-8.1 apply to every new operation.

## Wave plan

| Wave | Content | Main outside check |
|---|---|---|
| 1 | Backtester (event and vectorised), purged k-fold and CPCV counts, Viterbi regime labels, PSR, DSR, PBO by CSCV, power | Hand and textbook examples (J-19) |
| 2 | Drift (A3), Baum-Welch and Markov-switching AR (A4), Reality Check or SPA (J-4), mean-variance and risk parity (J-5), shrinkage and Black-Litterman (J-6) | scipy QP, scikit-learn Ledoit-Wolf (oracle only) |
| 3 | 14.5 items (shock library, ES backtest, Euler contributions, held-out-strike backtest) | Treasury par-yield history, named dates only |

## WAVE 1 READY (2026-11-13): backtester, CV, regimes, research statistics

Read with every slice: the four spec pages below; `specifications/stage-j-rulings-w1.md` J-1 to J-19; `specifications/cli-contract.md` (block "Stage J operations"); `specifications/name-map.json` (regenerated: 284 operations).

### Suites (97 cases)

| Suite | Spec | Operations | Cases (value, error) |
|---|---|---|---|
| `backtest_j` | `11-research/backtester.md` | `research.backtest.run` | 23 (14, 9) |
| `purgedcv_j` | `11-research/purged-cv.md` | `research.cv.purged_kfold`, `research.cv.cpcv_paths` | 23 (15, 8) |
| `regime_j` | `11-research/regimes.md` | `research.regime.viterbi` | 16 (10, 6) |
| `rstats_j` | `11-research/research-statistics.md` | `research.stats.dsr`, `.psr`, `.power`, `.pbo` | 35 (22, 13) |

Expected totals after wave 1 on top of main `3cca7da` (before the J-0b fuzz goldens): `TOTALS: 15174 value 7502 error 5158 invariance 2514`. `tools/check_case_total.py` reads the last `TOTALS:` line of `program/R6_HANDOVER.md`; this branch does not edit that file because branch `stage-j-fuzz` appends to it. **Coordinator, at merge:** append one combined line (this wave's +97 / +61 / +36 / +0 on top of whatever `stage-j-fuzz` states) to `program/R6_HANDOVER.md`, then run the gate.

Gates run on this branch: `oracle/python/check_error_cases.py` (0 schema mismatches), `tools/gen_name_map.py --check` (clean), `tools/check_golden_copies.py` (0 stale), `tools/check_tolerance_units.py` (0 unexplained); `tools/check_case_total.py` counts 15174 / 7502 / 5158 / 2514 with 0 duplicate ids (fails only on the missing handover line above).

### Build notes

- Backtester: build the `EVENT` loop from the definition; `VECTOR` is shift, diff, multiply, cumsum. Both must give every golden. Holding P&L uses the position **before** the bar's trade (J-2). `trade_count` is an Integer; `max_drawdown` starts the peak at 0 (J-6). Default costs are 0, `lag` 1, `multiplier` 1, `engine` `EVENT`.
- Purged CV: fold sizes in `array_split` order; closed-interval overlap; embargo `floor(pct * n)` indices after the block only (J-8). Indices are 0-based and ascending. `purgedcv_j-0001` is worked in the spec.
- Viterbi: work in logs; `log 0 = -inf` must be handled (the alternation case has zero transitions). Ties: smallest index (J-11). An all-`-inf` end is `E_DOMAIN`.
- DSR: `N = 1` gives `SR0 = 0` (J-13). Normal quantile to full double precision; the goldens use class `per_unit`. Euler-Mascheroni `0.5772156649015329`.
- PBO: combinations in lexicographic order of the train block set; logits in that order; average OOS rank, 1 = worst (J-16). Sample std divisor `n - 1`.
- Check order everywhere: `E_PARSE`, `E_SCHEMA` (unknown enum), `E_LIMIT`, F-2, then each page's list.

### Property tests (each language, own data)

- `EVENT` equals `VECTOR` to 1e-10; attribution identity; zero costs give net = gross; look-ahead canary detected at `lag = 0` and absent at `lag = 1` (Q7).
- No train label overlaps a test span; `t1 = t0` with no embargo equals plain k-fold.
- Viterbi path equals brute force on random `K <= 3`, `T <= 6` models.
- `dsr` is decreasing in `n_trials` and `sr_variance`; `psr` with `sr_benchmark = sr` is 0.5.
- PBO lies in `[0, 1]`; with one strategy dominating every row it is 0.

### Outside-check status (J-19)

Hand or textbook value cases: `backtest_j-0001`, `-0002` (ten-trade hand table), `purgedcv_j-0001` (hand), `purgedcv_j` CPCV `N = 6, k = 2` (15 splits, 5 paths), `regime_j-0001` (textbook example, 0.01512), `rstats_j-0001` (DSR worked example, recalled printed digits 0.1132 and 0.9004), `rstats_j-0017` to `-0020` (prereg MDS table), `rstats_j-0025` (PBO hand). Brute-force (independent method) on four further Viterbi cases. No outside **library** oracle in wave 1, so the R6-13 outside share is 0 library cases of 97; report it as such. J-1 stays open until [BLdP14] and [BBLdPZ17] are opened and their printed examples recorded (the PBO paper's example is not yet a golden).

### Model inventory

Rows to add at the stage J docs pass: MI-J1 backtester, MI-J2 purged CV, MI-J3 Viterbi labels, MI-J4 DSR/PBO/power, with golden hashes.

### Not in wave 1

Walk-forward and the trial registry stay in the Python research package (`quantforge_research`), not CLI operations. A6 feature store and A8 template section belong to the research lane.
