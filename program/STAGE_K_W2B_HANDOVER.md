# Stage K wave 2b handover: CVA capital (K-8g) and leverage ratio and large exposures, simplified (K-8i)

Branch `k-w2-py-b` (off the integration branch at dea6af55), Python and oracle only, written 2026-11-19 by Claude Opus 5.5. Nothing here touches `cli/registry.py`, `cli/operations.py`, `cli-contract.md`, `name-map.json` or any generated checklist; the coordinator applies the lines below at integration. One existing library file changed: `frtb.py` (a behaviour-preserving extraction, see "Shared SBM aggregation").

## What is on the branch

| Path | What |
|---|---|
| `python/quantforge_core/cva.py` | BA-CVA reduced and full (`ba_cva`, `discount_factor`) and SA-CVA (`sa_cva`) |
| `python/quantforge_core/leverage.py` | leverage ratio (`leverage` and its part functions) and large exposures (`large_exposures`, `offset_by_seniority`, `jtd`) |
| `python/quantforge_core/_k_w2b_tables.py` | generated copy of the `entries` of `specifications/tables/stage_k/{mar50_cva,lev_leverage,lex_large_exposures}.json` (decimal strings unchanged) |
| `tools/gen_k_w2b_tables.py` | writes that copy; `--check` compares the values with the JSON |
| `python/quantforge_core/frtb.py` | `bucket_radicand` and `cross_radicand` extracted from `aggregate` (same arithmetic, same order) |
| `python/quantforge_core/cli/ops_k_w2b.py` | handlers for the four verbs (registered only when imported) |
| `python/tests/test_stage_k_w2b.py` | golden replay through the CLI (local registration in a fixture, judged by `conformance/runner/runner.py`), unit tests, Hypothesis properties |
| `oracle/python/gen_stage_k_w2b.py` | independent mpmath oracle (does not import `quantforge_core`); asserts the acceptance targets, writes nine suites |
| `datasets/golden/stage_k/{cva_k,df_k,sacva_k,lev_k,lex_k}.json`, `{cva_ke,sacva_ke,lev_ke,lex_ke}.json` | goldens (values; errors) |
| `specifications/stage-k-rulings-w2.md` | new section: KR-120 to KR-135, PROPOSED |

## Operations

| Operation | Inputs | Outputs |
|---|---|---|
| `risk.cva.ba` | `version` (REDUCED, FULL), `counterparties` [{id, sector, quality, netting_sets [{ead, m, imm?}]}], FULL only: `single_name_hedges` [{counterparty, relation, sector, quality, m, notional}], `index_hedges` [{m, notional, constituents [{sector, quality, weight}]}] | `version`, `counterparties` [{id, scva, snh, hma, netting_sets [{df}]}], `ih`, `k_reduced`, `k_hedged`, `k_full` (the FULL-only fields null for REDUCED), `capital`, `rwa`, `label` |
| `risk.cva.sa` | `classes` {`IR.DELTA` ... `COM.VEGA`: [{bucket, factor, s_cva, s_hdg}]} (CCS factor an object {name, tenor, quality, legal_group?, index?, series?}), `reporting_currency`, `m_cva?` (1) | `classes` {key: {buckets [{bucket, k_b, s_b, sum_ws, floored}], k}}, `m_cva`, `total`, `rwa`, `label` |
| `risk.capital.leverage` | `tier1`, `on_balance` [reals], `derivatives` [{v, pfe, cvm_received?, cvm_provided?}], `written_credit_derivatives` [{notional, fair_value, purchased_offset?}], `sfts` [{gross_assets, mna, exposures, collateral}], `off_balance` [{notional, ccf_category}] (lists optional) | `on_balance`, `derivatives` (netting sets + written CDs, KR-129), `derivative_netting_sets`, `written_credit_derivatives`, `sfts`, `off_balance`, `exposure`, `ratio`, `meets_minimum`, `label` |
| `risk.capital.large_exposures` | `tier1`, `bank_gsib?`, `counterparties` [{id, group?, gsib?, exempt?}], `banking_book` [{counterparty, value}], `off_balance` [{counterparty, notional, ccf}], `crm` [{counterparty, provider, protected}], `trading_book` [{id, counterparty, seniority, notional, market_value, maturity_years?, cash_equity?, lgd_applies?}] | `counterparties` [{id, banking_book, off_balance, trading_book_net_long, trading_book_net_short, protected, received, exposure}], `groups` [{group, members, exposure, share, large, limit, breach, exempt}], `report`, `label` |

## Registration lines (apply at integration)

1. `python/quantforge_core/cli/registry.py`, `CORE_MODULES`: add `"cva",` and `"leverage",` (for example after `"frtb_backtest",`).
2. `python/quantforge_core/cli/operations.py`: add `ops_k_w2b,` to the `from . import (...)` list (after `ops_k_w1b,`).
3. `python/quantforge_core/cli/limits.py`: nothing. The 100,000 caps are the generic `MAX_ARRAY` (KR-126).
4. Optional: add `tests/test_stage_k_w2b.py` to `[tool.mutmut] tests_dir` in `python/pyproject.toml`. The test module is mypy-strict clean, so it needs no entry in the mypy overrides.

Until 1 and 2 are applied, `tests/test_conformance.py` fails on the nine new suites on this branch (unknown operation), as on `k-w1b`. I did not apply them locally even temporarily (the edit was refused by the session's permission check, and the brief forbids it); instead `tests/test_stage_k_w2b.py::test_golden` replays all 128 cases through `registry.execute` with the verbs registered in a fixture and judges each one with the runner's own `judge` and `policy.yaml`. All 128 pass.

## Contract entry (`specifications/cli-contract.md`, proposed text)

```
### Stage K wave 2b (K-8g CVA capital, K-8i leverage ratio and large exposures, simplified)

Rulings `stage-k-rulings-w2.md` KR-50 to KR-69 and KR-120 to KR-135. No new error code. Error order KR-67 (= HR-122): E_SCHEMA (enum values and factor names included), E_LIMIT (generic per-array cap), the finite rule, structural E_INPUT, E_DOMAIN. Reals binary64, class `simple_analytic` with `tolerance_limit` 1e-12 relative, 1e-15 absolute (KR-67); flags, labels, bucket and group names exact. Shared tables `specifications/tables/stage_k/mar50_cva.json`, `lev_leverage.json`, `lex_large_exposures.json`. Goldens `datasets/golden/stage_k/{cva_k,df_k,sacva_k,cva_ke,sacva_ke,lev_k,lex_k,lev_ke,lex_ke}.json` (`oracle/python/gen_stage_k_w2b.py`). Implemented in Python only. Every output carries `label`.

| `risk.cva.ba`, `risk.cva.sa` | `06-risk/cva-capital.md` | K-8g |
| `risk.capital.leverage`, `risk.capital.large_exposures` | `06-risk/leverage-large-exposures.md` | K-8i |
```

Also add the four rows to the operations-by-spec table and bump the contract minor version as the coordinator numbers it.

## Generator and tool commands

```
python tools/gen_k_w2b_tables.py --check                      # Python table copy equals the JSON (passes)
cd oracle/python && uv run python -W ignore gen_stage_k_w2b.py  # rewrites the nine suites; stops on any acceptance miss
python tools/gen_name_map.py              # name-map.json is stale once the goldens are in (check mode says so on this branch)
python tools/case_figures.py --write
python tools/outside_shares.py            # needs the nine suites under stage K (below)
python tools/build_references.py --check  # up to date on this branch
python tools/validation/build_checklists.py --check   # passed on this branch (33 checklists)
python research/test_preregs.py           # passed on this branch
```

Golden counts (read them from the files; do not hard-code them in a language test): cva_k 8, df_k 2, sacva_k 11, lev_k 13, lex_k 9 (43 value cases); cva_ke 19, sacva_ke 28, lev_ke 18, lex_ke 20 (85 error cases, 12 of them with two errors at once, 9 of them E1). Every operation has an E1 golden and an E1 golden with a second, structural error: under F-2 a non-finite Real is E_DOMAIN by the finite rule, before structural E_INPUT.

## Acceptance evidence (measured 2026-11-19, local laptop, not the acceptance machine)

- Blind targets: the generator asserts every field of `program/stage_h_blind_w2/k2_expected.json` for the 27 K-8g and K-8i cases (14 + 13) to max(1e-12 |e|, 1e-15) on the binary64 output before writing; all 27 MATCH (output of the run: "blind expected values asserted: 27 cases"). The inputs are taken from `program/stage_h_blind_w2/k2_cases.py`, the same ones the blind lane received, so the case ids and inputs are those of `STAGE_K_BLIND_W2.md`. These 27 cases carry `verified_by` "blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_W2.md): MATCH" and tags `outside_checked`, `blind` (the saccr_k pattern). No expected value was changed.
- L cases: df_k-0001 and 0002 equal the printed spec values exactly and SciPy `integrate.quad` of exp(-0.05 t) / m within 8e-16 (quad 0.8847968677143806 against 0.8847968677143805).
- P cases: lev_k-0001 to 0003 give 569.8, 5,405.4, 936.6, within 1.0 of the printed CRE99 EADs 569, 5,406, 936 (tolerance fixed in the spec); lev_k-0004 and 0005 give 90 and 100 (LEV30.31 footnote 384).
- Library: `uv run python -m pytest tests/test_stage_k_w2b.py` 158 passed (21 s); line coverage 100% on `cva.py`, `leverage.py`, `cli/ops_k_w2b.py`, `_k_w2b_tables.py`; `tests/test_finite.py -k "cva or leverage or frtb"` 54 passed; ruff check, ruff format and mypy strict clean on every new or changed file.
- `frtb.py` refactor: `tests/test_stage_g2.py` and `tests/test_frtb_kills.py` 20 passed; `tests/test_conformance.py` on `frtb_f`, `frtb_f2b`, `frtb_f2c`, `sbm_total_r6`, `e1_r6`, `e1_risk` 6 passed. The full Python suite was not run (brief: targeted runs only, recorder on the laptop).

Outside-check share (KR-68 classes, spec value cases only): K-8g 16 of 16 (14 B, 2 L); K-8i 18 of 18 (13 B, 5 P). The five K-8g and four K-8i cases this lane added (hand, mpmath only, marked "added by the wave 2b Python lane ... not blind re-derived") are not outside-checked: by suite, 16 of 21 and 18 of 22. Proposed `tools/outside_shares.py` items: `{"cva_k": "K-8g", "df_k": "K-8g", "sacva_k": "K-8g", "lev_k": "K-8i", "lex_k": "K-8i"}`.

## Shared SBM aggregation

SA-CVA reuses the FRTB SA aggregation rather than repeating it: `frtb.aggregate` now calls two extracted functions, `bucket_radicand(items, rho)` (sum of WS^2 plus the cross terms, MAR21.4(1)) and `cross_radicand(order, K_b, S_b, gamma)` (MAR21.4(4)), with the scenario scaling passed in as a closure; the arithmetic and its order are unchanged. `cva.sa_cva` adds what MAR50.53 changes: the hedge term R sum (WS^Hdg)^2 under the bucket root, S_b always clipped to [-K_b, K_b], no correlation scenarios, the floor at 0 of KR-62, and m_CVA. Bucket order is `frtb.bucket_key`. A test checks that, with no hedge, SA-CVA K_b equals the medium-scenario SBM K_b of the same weighted sensitivities.

## Limits ("simplified" means exactly this)

K-8g (`cva-capital.md` Limits): no exposure model (EAD, M and every SA-CVA sensitivity are inputs; regulatory CVA of MAR50.31-50.36 is out); hedge eligibility (MAR50.17-50.19, 50.37-50.39) is the caller's; the qualified-index option of MAR50.50 only through the caller's bucket assignment; the MAR50.9 materiality alternative and the MAR50.8 carve-out are not modelled; the KR-62 floors are a ruling.

K-8i leverage (KR-65): Tier 1 and its deductions (LEV30.3) are inputs; PFE is an input (or SA-CCR with the multiplier forced to 1, not wired here); left out are CCP client clearing (LEV30.26-30.29), cash pooling (LEV30.12), trade-date offsets (LEV30.10-30.11), securitisation derecognition (LEV30.5), the central bank reserves exemption (LEV30.7), agent SFTs (LEV30.41-30.44), the purchased-protection eligibility tests (LEV30.31(1)-(5), 30.32-30.34; the caller asserts `purchased_offset`), the exclusion of written CD PFE (LEV30.35), provisions against off-balance sheet items (LEV30.48), the lower-of-two-CCFs rule (LEV30.55), the G-SIB leverage buffer (LEV40) and quarter-end or averaging rules (LEV20.6).

K-8i large exposures (KR-66): connectedness (LEX10.9-10.18) is the caller's group map; exemptions are a flag only (LEX30.31-30.59 not modelled: sovereigns, covered bonds, interbank, CCPs); no look-through for funds and securitisations (LEX30.41-30.53); no LEX30.28 rule for CDS with a non-financial provider or reference; no SFT haircuts (LEX30.5) and no standardised CCFs (LEX30.6: only the 10% floor is applied to the caller's CCF); no CRM maturity mismatch (LEX30.10-30.11: the caller passes the recognised amount); one report list after CRM instead of the before and after lists of LEX20.4(1)-(2).

## Findings and decisions for the coordinator

1. Error order. The brief states the repo order as "E_SCHEMA, structural E_INPUT, E_DOMAIN, E_LIMIT"; both specs and KR-67 say E_SCHEMA, E_LIMIT, the finite rule, structural E_INPUT, E_DOMAIN (HR-122), which is also what `registry._pass_gate` enforces and what wave 1b followed. I implemented KR-67. Decide whether the brief's wording or the specs stand.
2. KR-62 against the spec: KR-62 says "report `floored: [bucket ids]`", the spec's Outputs a per-bucket boolean. Implemented the spec (KR-127).
3. KR-65 against the spec: KR-65 names the written CD field `fv_reduction_in_tier1`, the spec formal statement and case rows use `fair_value`. Implemented `fair_value` (KR-129).
4. G-SIB group rule (KR-133): I chose "any member flagged", the blind lane assumed "every member". No golden has a mixed group, so no matched value depends on it; please confirm one reading.
5. CCS buckets 1a and 1b aggregated as one bucket 1 (KR-121): read from Tables 5 and 6, not stated in the spec. No blind case uses bucket 1.
6. Equity vega large-cap buckets 1 to 8 and 12 (KR-124) and the IR factor names `CURVE`, `IR_VOL`, `INFLATION_VOL` (KR-120) are new names the C++, Rust and Java builds must use.
7. `frtb.py` is an existing file touched by this lane; if another lane edits `aggregate` the merge needs care (the change is the extraction only).

## Porting note for the C++, Rust and Java lanes

- Parameters: read `specifications/tables/stage_k/mar50_cva.json`, `lev_leverage.json`, `lex_large_exposures.json` (Rust `include_str!`, C++ `#embed`, Java a generated class with a check mode as `tools/gen_k_w1b_tables.py` does); `tools/gen_k_w2b_tables.py` is the Python copy and can be extended with a Java writer. Table cells such as `"0.90 legally related"` are read by their leading number. Map the input enums to table keys exactly as `cva.RELATIONS` and `leverage.CCF_CATEGORIES` do.
- Error order (KR-67): enums and factor names are E_SCHEMA in the reader (`CCS.VEGA` is read as a valid key and refused later as E_INPUT); then the generic array cap; then the finite rule over every Real read; then all structural E_INPUT checks of the whole input; then E_DOMAIN. Java: validate from the raw input, not inside records that validate on construction (stage H lesson).
- BA-CVA: DF = `-expm1(-0.05 m) / (0.05 m)` (KR-64); sums with a compensated sum (Python `fsum`) in input order; SCVA = RW x sum / 1.4; r_hc from Table 2; FULL fields null for REDUCED.
- SA-CVA: WS = RW s_cva - RW s_hdg (two products, as written), WSH = RW s_hdg; bucket radicand plain summation in the double-loop order of `frtb.bucket_radicand`, plus R sum WSH^2; `floored` when that sum is below 0; S_b clipped always; K = m_CVA sqrt(max(0, cross radicand)); bucket order by (length, text); CCS rho = tenor x name x quality with the bucket-8 index/series rule; CCS 1a/1b one bucket `1`; RCS gamma by the Table 9 row map of KR-125.
- Leverage: `meets_minimum` = `tier1 >= 0.03 x exposure` in binary64; exposure 0 is E_DOMAIN.
- Large exposures: KR-53 greedy offset per counterparty (shorts by descending rank, stable; each against eligible longs by ascending rank, stable); JTD = market value kept on the position's side; `large`, `limit`, `breach` in binary64 as KR-135; groups sorted by label in code-point order; report by exposure descending then label.
- Commit trailer: the lane rules ask for "Claude Fable 5.2"; this lane ran on Claude Opus 5.5 and the commits say so, as the brief asked.
