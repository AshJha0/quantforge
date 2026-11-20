# Stage K: audit of SIMM and ISDA references after the owner decision of 2026-11-19

Written 2026-11-19 by the K-8h rescoping lane (Claude Opus 5.5, branch `k-simm-spec`). Reading and writing only; no build, no golden changed. Owner decision 2026-11-19 (binding): the project uses **no ISDA material**; "SIMM" is not a named, delivered item of v1.0.0. This lane did not open, search for, fetch or quote any ISDA document or parameter set, and did not open any Open Source Risk Engine calibration file. **No value below was compared with any ISDA value**; the classification is by repository history and text only.

Method: `git grep -n -i simm` and `git grep -n -i isda` over the tree at `067a2bab` plus this branch's edits, `git log -S` on the weight vector, and the stage G spec, rulings and generator. Evidence class of every finding: read (the repository files named).

## (a) Documentation wording: fixed on this branch

| File | Before | Now |
|---|---|---|
| `GLOSSARY.md` stage G terms | "SIMM: ISDA's standard initial-margin model; here a SIMM-style IR delta only" | SIMM is an industry methodology ISDA licenses, patented; QuantForge does not implement it and uses no ISDA material; `xva.simm.ir_delta` is SIMM-style, name kept for the contract |
| `specifications/06-risk/xva-framework.md` source [SIMM] (and `docs/references.md`, regenerated) | "ISDA SIMM methodology (...)" | SIMM-style aggregation, a project definition; no ISDA document, parameter or test file read or used |
| `docs/getting-started/tutorial-15-advanced-risk.md` limits and references | listed what ISDA SIMM adds (a description of the methodology) and linked the ISDA SIMM page | the project's own aggregation, not ISDA SIMM; link replaced by the limits section |
| `docs/model-inventory.md` MF-4 retirement trigger, MG-8 limitations | "an ISDA SIMM curve rule"; "SIMM weights are inputs, not an ISDA calibration" | neutral trigger; SIMM-style project definition, no ISDA material |
| `docs/question-bank/09-counterparty-xva.md` Q9.17, Q9.18 | "not an ISDA SIMM calibration", "official SIMM parameters", "future SIMM" | SIMM-style project definition; no official parameters of any industry model; "future initial margin" |
| `oracle/LICENCES.md` ISDA SIMM row | own parameters labelled SIMM-style | the owner decision, the notice and patent, what is not opened, the two items that remain |
| `docs/releases/TEMPLATE.md` | "placeholder SIMM weights say ..." | the sbim label; no release names ISDA SIMM as a feature |
| `ROADMAP.md` stage K row; `program/STAGE_K_W2_GATE.md`; `program/STAGE_K_ORE_SURVEY.md` | | dated decision notes appended (history not rewritten) |
| `docs/model-inventory.md` | | new section "Why there is no ISDA SIMM here" |

Left as they are, already "SIMM-style" at most or history: `CHANGELOG.md` 0.7.0 entry, `COOKBOOK.md` stage G table, `README.md` stage G paragraph, `cpp26/README.md`, `oracle/README.md`, `program/traceability.md`, code comments in the four languages ("SIMM-style IR delta"), `program/STAGE_G_HANDOVER.md`, `program/R6_*` (history), `program/STAGE_K_SOURCES_W2.md` ("not read here"). `specifications/stage-k-rulings-w2.md` KR-69 says "SIMM (K-8h) outputs will carry placeholder weights"; rulings are append-only, so it is left for the coordinator to supersede with a one-line ruling pointing at KR-130 (`stage-k-rulings-sbim.md`).

## (b) Names in the versioned contract: NOT renamed (needs a ruling and four-language work)

| Name | Where | Recommendation |
|---|---|---|
| operation id `xva.simm.ir_delta` | `specifications/cli-contract.md`, `name-map.json`, dispatch tables: Rust `quantforge-cli/src/ops/xva.rs`, C++ `cpp26/src/cli/ops_xva.inc` (`op_xva_simm`), Java `OpsXva.java`, Python `cli/ops_lmm_xva_frtb.py` (`_simm`) | rename to a neutral id (proposal `xva.im.sensitivity_delta`) with the old id kept as a deprecated alias for one minor version, both dispatching to the same function |
| library names `simm_ir_delta` (Rust, Python), `Xva.simm` (Java; the name map says `Xva.simmIrDelta`), C++ computes inside `op_xva_simm` in `ops_xva.inc` (the name map says `qf::xva::simm_ir_delta`, which does not exist in `cpp26/`) | core modules and their unit tests (`PortfolioRiskToolsTest.simmSingleFactorAndConcentration`, Rust `simm_single_factor`, `python/tests/test_equity_xva_fits_kills.py`) | rename with the operation; fix the two name-map mismatches (Java, C++) in the same change |
| golden suite `datasets/golden/stage_g/simm_g.json`, case ids `simm_g-0001` to `-0008`, tag `"simm"` | referenced by `stage_g_e1/e1g_xva.json` (43 cases with this operation, `base:simm_g-0004`), `stage_j/fuzzfix_j.json` (1 case), `cpp26/tests/cli_cases.inc` (4), `oracle/OUTSIDE_SHARES.*`, `oracle/outside_register_g.json`, `docs/model-inventory.md` MG-8 lineage hash, tutorial 15 (doc and `examples/tutorials/t15_advanced_risk.py`), question bank Q9.17 and its verify script, `tools/inventory_counts.py` MG-8, `conformance/mutation/equivalents-python.md` | rename together with the weight change in (c), so the goldens are regenerated once |

Size of the change: about 30 files; four languages; three generators rerun (`gen_stage_g_w4b.py`, the stage G E1 generator, `gen_stage_j_fuzz.py`); a contract minor-version bump with the alias; every golden hash that names the suite. One coordinated round, all four builds green before merge.

## (c) Numeric values in the stage G margin code and goldens

All numbers enter `xva.simm.ir_delta` as caller inputs (G-43); the code holds no weight, correlation or threshold. The values below are the inputs written into the goldens, tests and tutorial.

| Value | Where | Origin in the repository | Class |
|---|---|---|---|
| risk weights `[109, 105, 90, 71, 66, 66]` on tenors `[0.25, 1, 2, 5, 10, 30]` years | `oracle/python/gen_stage_g_w4b.py:237`; goldens simm_g-0001, -0002, -0003, -0005, -0006, -0007 (the last three error cases with one entry changed); fuzzfix_j (from simm_g-0001); `cpp26/tests/cli_cases.inc` (4 cases); tutorial 15 doc and example | introduced in `ca78abb2` (2026-11-11, stage G wave 4b) with the comment "illustrative, regular-volatility-style magnitudes; inputs, not a SIMM table". No ruling, spec line or handover gives a rule that generates them; G-43 says only that weights are inputs. "Regular-volatility-style" names a category of an outside model's weights, which suggests the magnitudes were modelled on recalled outside values | **origin not documented** |
| **90** (simm_g-0002: one sensitivity 10,000, weight 90, margin 900,000) | the third entry of the vector above (the 2Y tenor); repeated in `xva-framework.md:42` worked example, `docs/question-bank/09-counterparty-xva.md` Q9.17, Java `PortfolioRiskToolsTest:67` and Rust `xva.rs:514` unit tests | the same commit and comment; nothing says 90 was invented by a rule | **origin not documented** |
| tenor correlation `exp(-0.3 abs(ln(T_k / T_l)))`, rounded to 6 decimals (0.659754, 0.535887, ...) | generator line 239; stated as a formula in `xva-framework.md:42` | the formula is written down, but nowhere is it labelled an invented placeholder, and the origin of 0.3 is not given | **origin not documented** (formula documented) |
| thresholds `1e9`, `1e6`, `0.0` | simm_g-0001 to -0007 | test choices stated by the case descriptions in the generator ("below concentration", "concentration factor sqrt(6)", "threshold 0" error) | documented as constructed test values (`gen_stage_g_w4b.py:240-242, 248`) |
| weights `[100, 100, 0, 0, 0, 0]`, all-ones correlations (simm_g-0004) and the 43 E1 cases built on it | `gen_stage_g_w4b.py:243`; `stage_g_e1/e1g_xva.json` | constructed hedge case ("perfect correlation hedge: margin 0") | documented as a constructed test value (`gen_stage_g_w4b.py:243`) |
| `4e6`, weight 1, threshold `1e6` | Java and Rust unit tests | constructed so that `CR = 2` | constructed (test code) |

Proposed fix for the "origin not documented" rows (not done here: it changes goldens): replace the vector by weights generated by a stated artificial rule, as the sbim table does (for example `10 x k` for tenor index `k`), and the correlation by a stated rule (for example `1 - 0.1 abs(k - l)`), record the rule in a new stage K ruling and in the generator comment, regenerate simm_g, the E1 cases that copy it and fuzzfix_j through the oracle, rerun all four builds, and update the tutorial, question bank, unit tests and the worked example's margin. Best done in the same round as the (b) rename. For the coordinator to schedule.

## ISDA references that are not SIMM (listed; left alone)

About 1,580 lines mention ISDA. By kind (counts of matching lines, overlapping):

| Kind | Lines (about) | Licence question? |
|---|---:|---|
| ISDA CDS Standard Model: conventions, upfront, IMM dates, `credit.cds.*` specs and goldens, tutorial 4 and 19, `IsdaCdsEngine` in QuantLib | 365 | No new one. `oracle/LICENCES.md` records it as not used, no code or output in the repository; checks ran against QuantLib (BSD-3-Clause). The model's documentation was read on cdsmodel.com (free; its source says "available under an Open Source license"). Following a published pricing convention is not use of ISDA code |
| Day count `ACT/ACT ISDA` and related names | 392 | No: a convention name |
| ISDA 2006 and 2021 Definitions, 2014 Credit Derivatives Definitions, 1998 EMU paper | 124 | Cited as "not opened" (`program/R1_CITATION_FINDINGS.md`, `docs/references.md`); conventions recalled, nothing quoted. No new question, but under a strict reading of "no ISDA material" the coordinator may want these citations reworded to the convention names alone |
| IBOR fallback spread, `ISDA_3M_SPREAD = 0.0026161` in `tools/workflows/sofr_check.py`, and fallback tests | 39 | Low: a single published spread value, used in a data-check script. Flagged so the coordinator can confirm it stays |

## Unverified

- Whether ISDA's notice also covers the "SIMM-style" description of the single-bucket formula in stage G is a legal question this lane cannot answer; the formula is generic and is now described as a project definition.
- The 1,580-line count is from `git grep`, not read line by line; the classification by kind is by keyword.
