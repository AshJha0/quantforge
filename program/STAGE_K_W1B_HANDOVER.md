# Stage K round 1, wave 1b handover: SA-CCR (K-8d) and FRTB IMA backtesting (K-8e)

Branch `k-w1b` (off `k-r1` at f2d90738), Python and specs only, written 2026-11-19. Nothing here touches `cli/registry.py`, `cli/operations.py`, `cli-contract.md`, `name-map.json` or any generated checklist; the coordinator applies the lines below at integration.

## What is on the branch

| Path | What |
|---|---|
| `python/quantforge_core/saccr.py` | SA-CCR core (`ead`, `Trade`, `Margin`, `supervisory_duration`, `supervisory_delta`, `mpor_floor`, `multiplier`) |
| `python/quantforge_core/frtb_backtest.py` | FRTB backtesting core (`backtest_zone`, `backtest_desk`, `count_exceptions`, `binomial_cdf`) |
| `python/quantforge_core/cli/ops_k_w1b.py` | handlers for the four verbs (registered only when imported, see below) |
| `python/tests/test_stage_k_w1b.py` | unit, published-example, SciPy and Hypothesis property tests; registers the verbs locally in a fixture |
| `specifications/06-risk/sa-ccr.md`, `frtb-ima-backtest.md` | specs (house format) |
| `specifications/06-risk/sa-ccr-parameters.json`, `frtb-ima-backtest-tables.json` | shared data tables for all four builds |
| `specifications/stage-k-rulings-w1b.md` | rulings KR-30 to KR-47 |
| `specifications/06-risk/var-es-and-backtests.md` | one sentence: the MAR99 Table 2 outside check of `risk.backtest.traffic_light` |
| `oracle/python/gen_stage_k_w1b.py` | independent mpmath oracle; asserts every published figure; writes the three suites |
| `datasets/golden/stage_k/saccr_k.json`, `btk_k.json`, `tlk_k.json` | goldens |

## Operations

| Operation | Inputs | Outputs |
|---|---|---|
| `risk.saccr.ead` | `trades` (class, notional, market value, maturity, position, kind, treatment, S/E, hedging set, entity, subclass, option or CDO fields), optional `collateral`, `margin`, `ir_offset` | EAD, RC, PFE, multiplier, add-ons by class and hedging set, per-trade SD, d, MF, delta, D, SF; margined MPOR and the unmargined cap |
| `risk.frtb.backtest.zone` | `observations`, `exceptions_actual`, `exceptions_hypothetical` | max count, cumulative probability, zone GREEN/AMBER/RED, amber_from, red_from, multiplier (250 only, else null) |
| `risk.frtb.backtest.desk` | `observations`, four counts (99% and 97.5%, actual and hypothetical) | the two max counts, two cumulative probabilities, breach flags, `eligible` |
| `risk.frtb.backtest.count` | `var`, `actual`, `hypothetical` (Real or null arrays) | counts per series, max, exception day indices |

## Registration lines (apply at integration)

1. `python/quantforge_core/cli/registry.py`, `CORE_MODULES`: add `"saccr",` and `"frtb_backtest",` (for example after `"venue_analytics",`).
2. `python/quantforge_core/cli/operations.py`: add `ops_k_w1b,` to the `from . import (...)` list.
3. `python/quantforge_core/cli/limits.py`: nothing required. `observations` > 1,000,000 is checked first inside `frtb_backtest` (same order as J-W3-17); `trades`, `var`, `actual`, `hypothetical` are bounded by the generic `MAX_ARRAY` cap. Adding `"risk.frtb.backtest.zone": _caps(observations=1_000_000)` and the same for `.desk` would not change any result.
4. Optional: add `tests/test_stage_k_w1b.py` to `[tool.mutmut] tests_dir` in `python/pyproject.toml`.

Until 1 and 2 are applied, `tests/test_conformance.py` fails on `saccr_k` and `btk_k` on this branch (unknown operation); with them applied locally all three suites pass (checked 2026-11-19, then reverted).

## Contract entry (`specifications/cli-contract.md`, proposed text)

```
### Stage K wave 1b (K-8d SA-CCR, K-8e FRTB IMA backtesting)

Rulings `stage-k-rulings-w1b.md` KR-30 to KR-47. No new error code. Error order HR-122: E_SCHEMA (enum values included), E_LIMIT, the finite rule, structural E_INPUT, E_DOMAIN. Reals binary64, class `simple_analytic`; counts, zones, flags, `mpor_days` and the tabulated multiplier exact. Shared tables `06-risk/sa-ccr-parameters.json` and `06-risk/frtb-ima-backtest-tables.json`. Goldens `datasets/golden/stage_k/saccr_k.json`, `btk_k.json`, `tlk_k.json` (`oracle/python/gen_stage_k_w1b.py`). Implemented in Python only.

| `risk.saccr.ead` | `06-risk/sa-ccr.md` | K-8d |
| `risk.frtb.backtest.zone`, `risk.frtb.backtest.desk`, `risk.frtb.backtest.count` | `06-risk/frtb-ima-backtest.md` | K-8e |
```

Also add the four rows to the operations-by-spec table in the same file, and bump the contract minor version as the coordinator numbers it.

## Generator and tool commands

```
cd oracle/python && uv run python -W ignore gen_stage_k_w1b.py      # rewrites the three suites; stops if a published figure fails
python tools/build_references.py          # docs/references.md lacks the two new specs' sources (check mode said so)
python tools/gen_name_map.py              # name-map.json is stale once the goldens and specs are in
python tools/case_figures.py --write      # docs/case-figures.md is stale
python tools/validation/build_checklists.py --check   # passed on this branch (33 checklists)
python tools/outside_shares.py            # needs a stage K entry, below
python research/test_preregs.py           # passed on this branch
```

`tools/outside_shares.py` has no stage K. Proposed: `STAGE_DIRS["K"] = ["stage_k"]`, plan items `{"saccr_k": "K-8d", "btk_k": "K-8e", "tlk_k": "F (existing traffic_light)"}`, and a per-case classification from `verified_by` (the coordinator decides the class; see the next section).

## Outside-check share (value cases only)

| Suite | Value cases | Published check | Independent library | Either | Share |
|---|---|---|---|---|---|
| `saccr_k` (K-8d) | 16 | 5 (CRE99 Examples 1 to 5, with BCBS 279 Annex 4a) | 0 | 5 | 31% |
| `btk_k` (K-8e) | 24 | 12 (MAR99 Table 2 rows) | 23 (`scipy.stats.binom.cdf`) | 23 | 96% |
| `tlk_k` (existing `risk.backtest.traffic_light`) | 11 | 11 | 11 | 11 | 100% |

Decision for the coordinator: under the R6-13 / D6 classes in `tools/outside_shares.py` a published worked example alone counts as `none`, and stage F classed SciPy binomial checks of Kupiec as `reimplementation`. Under that reading SA-CCR has 0% counted and the backtest share depends on whether `binom.cdf`, which is itself the compared quantity here (no formula rebuilt around it), is `library-primitive`. SA-CCR is below the 60% floor either way; the only route I know to raise it is ORE's SA-CCR (open source), not attempted in this lane.

## Acceptance evidence

- K-8d: `oracle/python/gen_stage_k_w1b.py` output (every line "published check MATCH"): the five EADs 569, 381, 5,406, 936, 1,879 and the printed intermediates of CRE99 reproduce under KR-30 (full precision, rounded to the printed digits); one printed intermediate, CRE99.90's -7,100 (full precision -7,099.30), is a source rounding accepted within one unit (KR-31), found by the first test run and recorded. Tests `test_cre99_printed_ead`, `test_cre99_intermediates`, `test_cre99_54_table`.
- K-8e: MAR99 Table 2 rows 0 to 10 match for both the new and the existing operation (`test_mar99_table2_new_operation`, `test_mar99_table2_existing_traffic_light`); MAR99 Table 1 (176 printed numbers, transcribed into the tables JSON) matches SciPy at one decimal (`test_mar99_table1_against_scipy`).
- Python: ruff check and format clean, mypy strict clean on the four files, `pytest tests/test_stage_k_w1b.py` 25 passed, line coverage 100% on `saccr.py`, `frtb_backtest.py`, `cli/ops_k_w1b.py`. `test_cli.py`, `test_core.py` and the three stage K conformance suites passed with the local registration.
- Source read: Basel Framework PDF generated 11/11/2026 (1,429 pages, SCO to BCP), CRE52 pp.434-462, CRE99 pp.524-540, MAR32 pp.658-668, MAR99 pp.753-761. BCBS 279 is not on disk.

## Porting note for the C++, Rust and Java lanes

- Read the parameters from `specifications/06-risk/sa-ccr-parameters.json` and `frtb-ima-backtest-tables.json` (generate a source table at build time, or load at start-up); do not hand-type a fourth copy. The Python test checks its literals against the JSON; add the same test per build.
- SA-CCR algorithm: follow `sa-ccr.md` steps 1 to 8. Points that decide bit-level agreement within `simple_analytic`: Phi(x) = 0.5 erfc(-x / sqrt 2); compensated sums (`fsum`) are used in Python for V, bucket sums, entity sums and the aggregate, plain summation is within tolerance for the goldens but keep the order; hedging-set output order is (class IR, FX, CREDIT, EQUITY, COMMODITY; treatment NORMAL, BASIS, VOLATILITY; key by code-point order); credit and equity NORMAL key is ""; the multiplier returns exactly 1 when V - C >= 0 before any exponential (KR-36); the margined cap compares to an unmargined run of the same trades with the same C (KR-37); `supervisory_duration` is null outside IR and credit.
- Error order: enum values are E_SCHEMA in the input layer; class-conditional required fields are structural E_INPUT and are all checked (every trade) before any E_DOMAIN check. Java: validate from the raw input, not inside typed records that validate on construction (stage H lesson). Eight of the 35 error cases across the suites carry two errors at once.
- Backtesting: reuse each build's existing `traffic_light` binomial sum (log-gamma terms, compensated sum) for `cumulative_probability`; `amber_from` and `red_from` are the first k with the running sum >= 0.95 and >= 0.9999, the same running sum. Rust has no `lgamma` in std: reuse the function the Rust traffic light already uses. The observations cap (1,000,000, E_LIMIT) is checked before the domain checks.
- Golden counts: saccr_k 37 (16 value, 21 error), btk_k 38 (24, 14), tlk_k 11 (11, 0). Do not hard-code these counts in a language test (stage H lesson); read them from the files.

## Limits and open points

- Python only. No C++, Rust or Java; no CI run on this branch; the full Python suite was not run (only the files above, `test_cli.py`, `test_core.py` and the stage K conformance suites).
- SA-CCR scope limits are in KR-39 (no multiple margin agreements, no shared margin agreements, no haircut computation, no CCP floors, caller-side notional and digital-option rules).
- K-8e covers backtesting only; the PLA test, the 10% criterion and capital are not part of it (KR-47).
- KR-44 (MAR32.19 "more than ... 30") and KR-32 (inclusive middle IR bucket) are readings of ambiguous text; both are pinned by goldens and flagged inferred.
- Commit trailer: the lane rules ask for "Claude Fable 5.2"; this lane ran on Claude Opus 5.5 and the commits say so, to keep the attribution true.
