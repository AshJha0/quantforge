# Stage K wave 2b Java port: CVA capital (K-8g) and leverage ratio and large exposures, simplified (K-8i)

Branch `k-w2-java-b` (off `k-w2-py-b` at 85f4ad12), written 2026-11-19 by the wave 2b Java port lane (Claude Opus 5.5). The Python reference, specs, rulings (KR-50 to KR-69, KR-311 to KR-326) and the nine goldens are those of `program/STAGE_K_W2B_HANDOVER.md`; nothing here changes them. Java only: no C++, no Rust. None of the central registration files was edited: `cli/Operations.java`, `specifications/cli-contract.md`, `name-map.json`, the registries and the generated checklists are untouched. The coordinator applies the lines below at integration. The pattern is the wave 1b SA-CCR port (`program/STAGE_K_W1B_PORTS_HANDOVER.md` on `k-r1`).

## Files

| Path | What |
|---|---|
| `java25/src/main/java/org/quantforge/risk/Cva.java` | BA-CVA reduced and full (`baCva`, `discountFactor`), SA-CVA (`saCva`); typed records, checks in the order of `cva.py` |
| `java25/src/main/java/org/quantforge/risk/Leverage.java` | leverage ratio (`leverage` and its part functions) and large exposures (`largeExposures`, `offsetBySeniority`, `jtd`) |
| `java25/src/main/java/org/quantforge/risk/KW2bTables.java` | GENERATED: the `entries` of `mar50_cva.json`, `lev_leverage.json`, `lex_large_exposures.json` as read-only trees (maps in JSON order, decimal strings unchanged, integers `Long`, null kept) |
| `tools/gen_k_w2b_tables.py` | extended: writes the Java class next to the Python module; `--check` now also fails when `KW2bTables.java` differs from what it would write |
| `java25/src/main/java/org/quantforge/risk/FrtbSbm.java` | `bucketRadicand` and `crossRadicand` extracted from `aggregate` (same arithmetic, same order), plus two functional interfaces `FactorRho`, `PositionGamma` |
| `java25/src/main/java/org/quantforge/cli/OpsStageKW2b.java` | CLI handlers of the four verbs, `register(table)`; NOT registered |
| `java25/src/test/java/org/quantforge/cli/StageKW2bCliTest.java` | in-process replay of every case of the nine suites through `OpsStageKW2b` with `In`, the Main.apply gate order and `GoldenSuiteTest.judge`; input-layer order tests |
| `java25/src/test/java/org/quantforge/cli/FrtbAggregationReplayTest.java` | every golden case of a registered `risk.frtb.*` sensitivity verb (not backtesting), in every suite, through `Main.handle` |
| `java25/src/test/java/org/quantforge/risk/CvaTest.java`, `LeverageTest.java`, `KW2bTablesTest.java` | unit tests and jqwik properties mirroring `python/tests/test_stage_k_w2b.py`; the generated trees against the JSON |

## Registration lines (apply at integration)

`java25/src/main/java/org/quantforge/cli/Operations.java`, `MODULES`: add after the last module line (put a comma on that line; on `k-r1` that is `new Registry.Module("stage_k_w1b", OpsStageKW1b::register)`):

```java
            new Registry.Module("stage_k_w2b", OpsStageKW2b::register)
```

Then delete the test `registersFourVerbsAndNoCollision` in `java25/src/test/java/org/quantforge/cli/StageKW2bCliTest.java` (it asserts the verbs are not yet registered). `GoldenSuiteTest` will then replay the nine suites through `Main.handle` as well. No `In.pageLimited` entry: the 100,000 caps are the generic per-array cap (KR-317), which `In` already applies.

Suggested CI line (coordinator's choice of job): `python tools/gen_k_w2b_tables.py --check` next to `gen_k_w1b_tables.py --check`. Contract text: the wave 2b Python handover's "Contract entry" with "Implemented in Python only" changed to "Implemented in Python and Java".

## Error order (KR-67 = HR-122) as built

The handler reads every input first; anything missing, mistyped or an enum value outside its list (`version`, `sector`, `quality`, `relation`, CCS `tenor` and `quality`, IR factor names, `ccf_category`, `seniority`, and an unlisted `classes` key) is E_SCHEMA at the read. `CCS.VEGA` is read as a valid key and refused later as E_INPUT (spec, Errors). Then `in.gate()`: a held E_LIMIT (generic per-array cap, nested arrays included), then the finite rule (the first non-finite Real read). Then the core: every structural E_INPUT of the whole input, then E_DOMAIN. The records do not validate on construction; the core functions are the checked entry points and also raise E_SCHEMA for unlisted enums, so a direct library caller gets the same codes as the CLI (the stage H lesson on typed records).

## The three open readings (another lane is checking them; one-line edits)

| Reading | Where | As built (= Python reference) |
|---|---|---|
| KR-324 G-SIB 15% group limit: any member or every member | `Leverage.GSIB_GROUP_ANY_MEMBER` (one boolean, marked `OPEN READING KR-324`) | `true`: any member flagged, with `bank_gsib` |
| KR-312 CCS buckets 1a and 1b | `Cva.CCS_MERGE_1A_1B` (marked `OPEN READING KR-312`), used only by `Cva.ccsAggregationBucket` | `true`: one aggregation bucket `1` |
| KR-315 equity vega 78% buckets | `Cva.EQ_VEGA_LARGE_CAP` (marked `OPEN READING KR-315`), used only by `Cva.eqVegaKey` | buckets 1 to 8 and 12 |

If KR-312 changes to two buckets, Table 6 has no gamma between 1a and 1b; `ccsGamma` maps both labels to row 1 today, which would give gamma 1 between them, so that case also needs a ruling.

## Evidence (measured 2026-11-19, local laptop, not the acceptance machine)

Targeted Maven run only, not the full CI chain: `mvn -o -Pcoverage test jacoco:report -Dtest=StageKW2bCliTest,CvaTest,LeverageTest,KW2bTablesTest,FrtbAggregationReplayTest,PortfolioRiskToolsTest` (JDK 25, Windows), all passing (JUnit and jqwik; properties at 200 or 300 tries as in Python). `python tools/gen_k_w2b_tables.py --check` passes.

Line coverage (JaCoCo, that run; `tools/quality_gate.py --per-file` lists none of these files below the floor; the other library files are below only because the run is targeted): `Cva.java` 455/455 (branches 296/302), `Leverage.java` 292/292 (152/154), `OpsStageKW2b.java` 171/171 (62/62), `KW2bTables.java` 78/78, `FrtbSbm.java` 156/161 (131/143; the five missed lines are pre-existing FX, CSR and commodity paths the targeted run does not reach).

Golden replay, largest relative difference between Java and the golden value over every non-zero expected number (absolute difference at expected 0 was 0 in every suite):

| Suite | Cases (value, error) | Max relative difference |
|---|---|---|
| cva_k | 8 (8, 0) | 3.96e-16 |
| df_k | 2 (2, 0) | 1.96e-16 |
| sacva_k | 11 (11, 0) | 2.22e-16 |
| lev_k | 13 (13, 0) | 1.88e-16 |
| lex_k | 9 (9, 0) | 0 |
| cva_ke, sacva_ke, lev_ke, lex_ke | 19, 28, 18, 20 (all error) | error code matched in every case |

All 128 cases pass at the goldens' own tolerances (`simple_analytic` with `tolerance_limit` 1e-12 relative, 1e-15 absolute; labels exact).

FRTB extraction: `FrtbAggregationReplayTest` replays all 85 FRTB sensitivity golden cases (frtb_f, frtb_f2b, frtb_f2c, sbm_total_r6, e1_r6, e1_risk; the set is read from the files) through `Main.handle`, all pass; `PortfolioRiskToolsTest` (the FRTB property tests, unchanged) passes.

## Notes on the reference (no golden changed)

1. Summation. `cva.py` uses `math.fsum` (ported as `StressDrift.fsum`, correctly rounded) and, in SA-CVA, Python's built-in `sum` for `sum_ws`, the hedge term and inside `frtb.bucket_radicand` and `cross_radicand`. On Python 3.12 and later (`requires-python ==3.15.*`) the built-in `sum` of floats is Neumaier-compensated, not plain; `Cva.pySum` reproduces it for the sums `cva.py` owns. The shared radicands keep the existing Java FRTB arithmetic, as the brief asks: Java adds the diagonal inside the double loop as `ws_i * ws_j * 1.0`, Python adds `sum(w * w)` first and then the off-diagonal terms. The goldens absorb the difference (2.2e-16 relative on sacva_k), but a bucket whose radicand nearly cancels could differ between the two builds by more than 1e-12 relative; no golden exercises that.
2. `tools/gen_k_w2b_tables.py` write mode rewrites `_k_w2b_tables.py` in pprint layout, which differs from the committed ruff-formatted text (values equal; `--check` compares values for Python and text for Java). Run `ruff format` on the Python module after a write, or the diff is noisy. Unchanged behaviour of the Python lane's tool.
3. Group and report ordering use binary64 comparisons; the Java report sort treats -0.0 and 0.0 as equal, as Python's tuple sort does.
4. The wave 2b Python handover's finding 1 (error-order wording in the brief versus KR-67) applies here unchanged: KR-67 is implemented.

## Not verified

The full Java suite, `GoldenSuiteTest` over the whole tree (the targeted FRTB replay stands in for it), the conformance runner against the built CLI (verbs unregistered), mutation testing, the C++ and Rust ports (not this lane).
