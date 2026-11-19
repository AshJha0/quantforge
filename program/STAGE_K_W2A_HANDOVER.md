# Stage K wave 2, lane A handover: FRTB DRC and RRAO (K-8a) and FRTB IMA (K-8f), Python

Branch `k-w2-py-a` (off the integration branch at dea6af55), Python and oracle only, written 2026-11-19 by Claude Opus 5.5. Nothing here touches `cli/registry.py`, `cli/operations.py`, `cli/limits.py`, `cli-contract.md`, `name-map.json`, `conformance/E1_EXEMPT.json`, `tools/outside_shares.py` or any generated checklist; the coordinator applies the lines below at integration. Evidence class of every result below: measured, 2026-11-19, local laptop, not the acceptance machine.

## What is on the branch

| Path | What |
|---|---|
| `python/quantforge_core/frtb_drc.py` | K-8a core: `drc_nonsec`, `drc_sec_nonctp`, `drc_ctp`, `rrao`, with `gross_jtd`, `maturity_weight`, `offset` (KR-53 greedy), `ctp_total` |
| `python/quantforge_core/frtb_ima.py` | K-8f core: `pla`, `pla_ks_pvalue`, `liquidity_horizon`, `es_lh`, `es_stressed`, `imcc`, `ses`, `capital`, `rfet`, `rfet_bucket`, with `spearman`, `ks_count`, `kolmogorov_q`, `months_back` |
| `python/quantforge_core/cli/ops_k_w2a.py` | handlers for the 14 verbs (every E_SCHEMA check is here) |
| `python/quantforge_core/cli/limits_k_w2a.py` | sizes for `risk.frtb.pla` and `risk.frtb.ima.es_lh`, whose P&L lists may hold 1,000,000 points (KR-67), above the generic `MAX_ARRAY` |
| `python/tests/test_stage_k_w2a.py` | goldens, KR-50 table checks, units, Hypothesis properties, SciPy cross-checks; registers the verbs and the limits hook locally in a fixture |
| `oracle/python/gen_stage_k_w2a.py` | independent oracle (fractions and mpmath 50 digits, no `quantforge_core` import); asserts every value before writing |
| `datasets/golden/stage_k/drc_k.json`, `ima_k.json` | goldens: drc_k 61 cases (18 value, 43 error), ima_k 99 (33 value, 66 error) |
| `specifications/stage-k-rulings-w2.md` | new section "Wave 2 lane A implementation rulings", KR-112 to KR-122, PROPOSED |

Case ids are the specs' own (`drc_k-0001`, `ctp_k-0002`, `pla_k-0007`, ...); error cases continue the specs' error ids (`drc_ke-0001` ... `drc_ke-0007` are the spec's, later numbers are new). Two suite files hold them: `drc_k` (K-8a) and `ima_k` (K-8f).

## Operations

| Operation | Inputs | Outputs |
|---|---|---|
| `risk.frtb.drc_nonsec` | `positions` [{id, obligor, bucket, seniority, notional, market_value, maturity_years, cash_equity?, lgd_applies?}], `ratings` {obligor: rating} | `positions`, `obligors`, `buckets`, `drc`, `label` |
| `risk.frtb.drc_sec_nonctp` | `positions` [{id, bucket, pool, tranche, market_value, maturity_years, rw}] | `positions`, `buckets`, `drc`, `label`, `rw_source` |
| `risk.frtb.drc_ctp` | `positions` [{id, index, series, tranche, market_value, maturity_years, rw}] or `bucket_drc` [Real] | `positions`, `hbr_ctp`, `buckets`, `drc`, `label`, `rw_source` (bucket_drc mode: `drc`, `label`, `rw_source`) |
| `risk.frtb.rrao` | `instruments` [{id, gross_notional, kind, listed_or_clearable, back_to_back}] | `instruments`, `rrao`, `label` |
| `risk.frtb.pla` | `hpl`, `rtpl` | `n`, `spearman`, `ks`, `ks_count`, `zone`, `ks_pvalue_asymptotic`, `regulatory_window`, `label` |
| `risk.frtb.pla.ks_pvalue` | `ks`, `n` (Integer) | `pvalue`, `label` |
| `risk.frtb.ima.lh` | one of `category`, `fx_pair`, `constituents` [{weight, n}]; optional `maturity_days` | `n`, `table_n`, `rule`, `label` |
| `risk.frtb.ima.es_lh` | one of `es_t`, `sigma` (five Reals), `pnl` (five lists) | `mode`, `es_by_horizon`, `es`, `label` |
| `risk.frtb.ima.es_stressed` | `es_rs`, `es_fc`, `es_rc` | `ratio`, `ratio_floored`, `es`, `label` |
| `risk.frtb.ima.imcc` | `portfolio` {es_rs, es_fc, es_rc}, `classes` {IR, EQ, FX, COM, CS: triple} | `imcc_c`, `portfolio_floored`, `classes`, `classes_floored`, `imcc`, `label` |
| `risk.frtb.ima.ses` | `idio_credit`, `idio_equity`, `other` | `idio_credit`, `idio_equity`, `other` (the three square roots), `ses`, `label` |
| `risk.frtb.ima.capital` | `imcc_prev`, `ses_prev`, `imcc_avg`, `ses_avg`, `exceptions` (Integer), `qualitative_addon?`, `drc`, `desks` [{zone, sa}], `c_u`, `sa_all` | `m_c`, `c_a`, `ima_ga`, `sa_ga`, `k`, `surcharge`, `acr_total`, `label` |
| `risk.frtb.rfet` | `as_of`, `observations` (ISO dates) | `window_start`, `distinct_days`, `min_window_count`, `first_failing_window_start`, `first_failing_window_count`, `crit1`, `crit2`, `pass`, `label` |
| `risk.frtb.rfet.bucket` | `row` (A to D), `t` (rows A to C) or `delta` (row D) | `bucket`, `lower`, `upper`, `label` |

## Registration lines (apply at integration)

1. `python/quantforge_core/cli/registry.py`, `CORE_MODULES`: add `"frtb_drc",` and `"frtb_ima",` (for example after `"frtb_backtest",`).
2. `python/quantforge_core/cli/operations.py`: add `ops_k_w2a,` to the `from . import (...)` list.
3. `python/quantforge_core/cli/limits.py`: add `from . import limits_k_w2a` with the imports and make these the first two lines of `check_limits`:
   ```python
   if limits_k_w2a.check(operation, raw):
       return
   ```
   Without it the generic `MAX_ARRAY` (100,000) rejects a PLA or ES P&L list of more than 100,000 points, which KR-67 allows up to 1,000,000; every golden passes either way (none is that large). The other 12 verbs use the generic caps, which equal KR-67's 100,000.
4. `conformance/E1_EXEMPT.json`: `"risk.frtb.rfet": "no Real input in any golden: an as_of date and a list of ISO dates"`. Every other new verb has an E1 golden (17 E1 cases, 4 of them with a second error).
5. `tools/outside_shares.py`, `STAGE_K_ITEMS`: add `"drc_k": "K-8a", "ima_k": "K-8f"`.
6. Optional: add `tests/test_stage_k_w2a.py` to `[tool.mutmut] tests_dir` in `python/pyproject.toml`.

Until 1 and 2 are applied, `tests/test_conformance.py` fails on `drc_k` and `ima_k` on this branch (unknown operation; checked 2026-11-19). With the local registration of the test fixture all 160 cases pass.

## Contract entry (`specifications/cli-contract.md`, proposed text)

```
### Stage K wave 2 lane A (K-8a FRTB DRC and RRAO, K-8f FRTB IMA)

Rulings `stage-k-rulings-w2.md` KR-50 to KR-69 and KR-112 to KR-122. No new error code. Error order KR-67 (= HR-122): E_SCHEMA (enum values included), E_LIMIT (100,000 positions, instruments, desks, constituents, charges and dates; 1,000,000 points per P&L list), the finite rule, structural E_INPUT, E_DOMAIN. Reals binary64, class `simple_analytic` with `tolerance_limit` 1e-12 relative, 1e-15 absolute (KR-67); counts, zones, flags, dates, horizons and buckets exact. Every output carries `label` "regulatory formula on caller inputs; not a regulatory return" (KR-69); securitisation and CTP outputs also `rw_source` (KR-55). Shared tables `specifications/tables/stage_k/mar22_drc.json`, `mar23_rrao.json`, `mar31_rfet.json`, `mar32_pla.json`, `mar33_ima.json`. Goldens `datasets/golden/stage_k/drc_k.json`, `ima_k.json` (`oracle/python/gen_stage_k_w2a.py`). Implemented in Python only.

| `risk.frtb.drc_nonsec`, `risk.frtb.drc_sec_nonctp`, `risk.frtb.drc_ctp`, `risk.frtb.rrao` | `06-risk/frtb-drc-rrao.md` | K-8a |
| `risk.frtb.pla`, `risk.frtb.pla.ks_pvalue`, `risk.frtb.ima.lh`, `risk.frtb.ima.es_lh`, `risk.frtb.ima.es_stressed`, `risk.frtb.ima.imcc`, `risk.frtb.ima.ses`, `risk.frtb.ima.capital`, `risk.frtb.rfet`, `risk.frtb.rfet.bucket` | `06-risk/frtb-ima.md` | K-8f |
```

Also add the 14 rows to the operations-by-spec table and bump the contract minor version as the coordinator numbers it.

## Generator and tool commands

```
cd oracle/python && uv run python -W ignore gen_stage_k_w2a.py   # rewrites drc_k and ima_k; stops at the first failed check
python tools/gen_name_map.py              # name-map.json is stale once the verbs are registered
python tools/case_figures.py --write
python tools/build_references.py          # check mode: "references: up to date" on this branch
python tools/validation/build_checklists.py --check   # passed on this branch (33 checklists)
python tools/check_e1_coverage.py         # after registration and the E1_EXEMPT line
python tools/outside_shares.py            # after the STAGE_K_ITEMS line
python research/test_preregs.py           # OK on this branch
```

A second run of the generator reproduces both files byte for byte (checked: `git status` clean after the rerun).

## Acceptance evidence

- Generator: 130 "check MATCH" lines, 0 failures. The 31 blind-matched hand cases equal `program/stage_h_blind_w2/k2_expected.json` field by field at max(1e-12 |e|, 1e-15); the other 20 value cases equal the spec tables at the printed digits; printed Basel figures: MAR22.16 FAQ (`1/4*10 - 1/4*10 = 0`), MAR22.45 (`100 - 0.5 x 100 = 50`), MAR32.42 p-values 0.264 and 0.055 (asymptotic 0.263380632422 and 0.0546463301139, within the 1e-3 fixed in the spec), MAR33.12 FAQ4 (40) and FAQ5 (20).
- SciPy 1.17 (independent library, reported, not counted): `spearmanr`, `ks_2samp` and `kstwobign.sf` equal every PLA golden to 1e-12; `integrate.quad` of the normal tail equals es_k-0001 and es_k-0002 to 1e-12 relative; `kstwobign.sf` equals `kolmogorov_q` to 1e-12 relative on 11 points from 0.05 to 4; random PLA inputs (Hypothesis, 300 examples) agree with `spearmanr` and `ks_2samp` to 1e-12.
- Library: `pytest tests/test_stage_k_w2a.py` 31 passed; line coverage 100% on the four library files; ruff check and format clean; mypy clean on the five files.
- Properties (Hypothesis): DRC non-negative, HBR in [0, 1], a long added never lowers its bucket's DRC, permutation invariance, scaling by c (300 examples, not the spec's 10,000; A3 asks 10,000 for the four-build acceptance run); spearman symmetric and invariant under strictly increasing transforms of either series, KS under a common one; ES cascade for a single horizon and for nested horizons (KR-122); stressed ES never below ES_R,S; SES `other` term between the root-sum-square and the plain sum, a single entry equal to itself; RFET counts against a brute-force window count, duplicates ignored.

## Outside-check share (value cases; stage K loader rule: DR-H2 MATCH or a printed figure)

| Item | Value cases | Printed (P) | Blind (B, counted) | SciPy (L, not counted) | Table lookups (T) | Counted | Share |
|---|---:|---:|---:|---:|---:|---:|---|
| K-8a `drc_k` | 18 | 2 | 15 (rrao_k-0003 compared, not counted) | 0 | 0 | 17 | 94% |
| K-8f `ima_k` | 33 | 4 | 15 | 8 (pla_k-0001 to 0006, es_k-0001, 0002) | 6 | 19 | **58%, under the 60% floor** |

**Finding for the coordinator.** `STAGE_K_BLIND_W2.md` reports K-8f at 27 of 33 (82%), counting the SciPy (L) cases as KR-68 allows. Under the D6 precedent applied to btk_k today (integration 2cef4f98: a SciPy primitive that computes the same quantity is `reimplementation`), the six PLA cases checked by `spearmanr` and `ks_2samp` do not count, and `tools/outside_shares.py`'s stage K loader counts only DR-H2 matches and printed figures, so it would report 19 of 33. The two normal-ES cases are checked by `integrate.quad` of the tail, a different formulation of the closed form, which D6 describes as `library-primitive`; if the coordinator counts those two, K-8f is 21 of 33 (64%). The goldens mark them "not counted here: whether D6 classes it library-primitive is the coordinator's decision". No expected value was changed.

## Rulings added (PROPOSED, `stage-k-rulings-w2.md`)

KR-112 cash equity must be EQUITY with notional = market value; KR-113 one bucket per obligor; KR-114 output shapes and order; KR-115 one rw per netting group; KR-116 empty inputs and the two labels; KR-117 Spearman arithmetic and the evaluation of Q_KS (theta form below 1), `n >= 1`; KR-118 liquidity horizon inputs; KR-119 a negative ES from a P&L list is `E_DOMAIN`; KR-120 capital inputs non-negative, and the no-desk case of MAR33.43 stated; KR-121 RFET bucket inputs; KR-122 the A3 sentence of `frtb-ima.md` on single-horizon scaling is wrong (the correct two properties are tested) and the "LH class key repeated" error cannot occur. Numbering continues after KR-111; no other branch used KR-112 to KR-122 when checked (origin, 2026-11-19).

Error order, stated so nobody is surprised: this lane follows KR-67 (= HR-122: E_SCHEMA, E_LIMIT, finite rule, structural E_INPUT, E_DOMAIN), which the registry gate implements, not the shorter "E_SCHEMA, structural E_INPUT, E_DOMAIN, E_LIMIT" of the lane brief nor the wave 1 `STAGE_K_OPS` order (E_LIMIT last, HR-66). Two-error goldens pin it: drc 7, ima 11.

## Limits

- Python only; no C++, Rust or Java; no CI run on this branch; the full Python suite was not run (only `tests/test_stage_k_w2a.py` and the two suites of `test_conformance.py`, which fail until registration).
- Spec limits stand (securitisation risk weights, look-through, decomposition and replication offsets, the IMA DRC model, ES models, RFET representativeness and lag, PLA alignment are the caller's).
- SES squares charges: a charge below about 1e-154 underflows to 0 (binary64); the single-entry property is tested from 1e-100.
- With no desks, `SA_G,A = 0` and the MAR33.43 formula adds the whole IMA_G,A again (KR-120); applied as written.
- Property tests run 100 to 300 examples each, not 10,000.

## Porting note for the C++, Rust and Java lanes

- Parameters: generate from or test against `specifications/tables/stage_k/*.json` (KR-50); the Python test `test_parameters_match_tables` is the model. The normal ES factor is computed (`ppnd16` and the normal density), one ulp from the KR-57 printed constant.
- DRC: maturity weight before offsetting; KR-53 greedy exactly as `frtb_drc.offset` (shorts by descending rank then input order, longs by ascending rank then input order); sums with a compensated sum (Python `fsum`), plain sums are within tolerance for the goldens. Output order KR-114 (code-point sort of ids, obligors, sec and CTP buckets).
- CTP: HBR over all net amounts before risk weighting; `DRC_b` unfloored; MAR22.45 aggregation; positions netted per (index, series, tranche).
- PLA: integers for the ranks (centred doubled ranks fit i64 at n = 1,000,000: |sum| <= n (n-1)^2 < 9.2e18); `S_xx` and `S_yy` converted to binary64 before the product; clamp to [-1, 1]; zone tests on the integer `d` (`100 d < 9 n`, `100 d > 12 n`). KS count by merging the two sorted lists (`bisect_right` counts at every pooled value). `Q_KS`: KR-117 switch at x < 1, sum until a term is 0.
- ES: `pnl` mode reuses each build's `risk.var.historical` ES at 0.975 (`w = n - n c` in binary64); an empty list is 0; weights (1, 1, 2, 2, 6); `sqrt(fsum(w e^2))`.
- RFET: window start = as_of minus 12 calendar months, day clamped to the month end, plus one day; 90-day windows [s, s + 89] for s up to as_of - 89; distinct days only.
- Error order: enum values and types in the input layer; structural checks over every position before any domain check (Java: validate from the raw input, not inside records that validate on construction). Do not hard-code golden counts in a language test (drc_k 61, ima_k 99; read them from the files).
