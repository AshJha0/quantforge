# Stage K wave 2, lane A Java port: FRTB DRC and RRAO (K-8a) and FRTB IMA (K-8f)

Branch `k-w2-java-a` (off `k-w2-py-a` at fc3ea73f), Java only, written 2026-11-19 by Claude Opus 5.5. The Python reference, specs, rulings (KR-50 to KR-69, KR-300 to KR-310) and goldens are those of `program/STAGE_K_W2A_HANDOVER.md`; nothing here changes them, and no golden was touched. The pattern is the SA-CCR port of `program/STAGE_K_W1B_PORTS_HANDOVER.md` (origin/k-r1). None of the central files was edited: `cli/Operations.java`, `cli/In.java`, `cli-contract.md`, `name-map.json`, registries and generated checklists are untouched. Evidence class of every result below: measured, 2026-11-19, local laptop, not the acceptance machine.

## Files added

| Path | What |
|---|---|
| `java25/src/main/java/org/quantforge/risk/FrtbDrc.java` | K-8a core: `drcNonsec`, `drcSecNonctp`, `drcCtp`, `rrao`, with `grossJtd`, `maturityWeight`, `offset` (KR-53 greedy), `ctpTotal`; plain input records (no validation on construction) and result records |
| `java25/src/main/java/org/quantforge/risk/FrtbIma.java` | K-8f core: `pla`, `plaKsPvalue`, `liquidityHorizon`, `esLh`, `esStressed`, `imcc`, `ses`, `capital`, `rfet`, `rfetBucket`, with `spearman`, `ksCount`, `kolmogorovQ`, `doubledRanks`, `monthsBack` |
| `java25/src/main/java/org/quantforge/risk/FrtbDrcTables.java`, `FrtbImaTables.java` | GENERATED from `specifications/tables/stage_k/mar22_drc.json`, `mar23_rrao.json`, `mar31_rfet.json`, `mar32_pla.json`, `mar33_ima.json` |
| `tools/gen_k_w2a_tables.py` | the generator; `--check` exits 1 when a generated class is stale (sibling of `tools/gen_k_w1b_tables.py`) |
| `java25/src/main/java/org/quantforge/cli/OpsStageKW2a.java` | handlers for the 14 verbs (`register(table)`), every E_SCHEMA check, the KR-67 list sizes, and `PAGE_LIMITED` |
| `java25/src/test/java/org/quantforge/cli/StageKW2aCliTest.java` | in-process replay of every case of `drc_k` and `ima_k`, limits order, input-layer details |
| `java25/src/test/java/org/quantforge/risk/FrtbDrcTest.java`, `FrtbImaTest.java` | tables against the JSON (KR-50), units mirroring `python/tests/test_stage_k_w2a.py`, jqwik properties |

## Registration lines (apply at integration)

1. `java25/src/main/java/org/quantforge/cli/Operations.java`, `MODULES`: add after the last module (put a comma on the line before):
   ```java
               new Registry.Module("stage_k_w2a", OpsStageKW2a::register)
   ```
2. `java25/src/main/java/org/quantforge/cli/In.java`, `pageLimited`: add to the returned expression
   ```java
                   || OpsStageKW2a.PAGE_LIMITED.contains(operation)
   ```
   This is the Java form of the Python limits hook (`limits_k_w2a.py`): `risk.frtb.pla` and `risk.frtb.ima.es_lh` take P&L lists of up to 1,000,000 points (KR-67), so the general 100,000 per-array scan must be skipped for them; the two handlers apply the KR-67 sizes themselves (`hpl`, `rtpl`, each `pnl` row 1,000,000; `es_t`, `sigma`, `pnl` 100,000). Without this line every golden still passes (none is that large), but a list of 100,001 to 1,000,000 points is wrongly `E_LIMIT`.
3. Then in `StageKW2aCliTest.registersFourteenVerbsNotYetInOperations` delete the `assertNull(Operations.find(op), ...)` line (it asserts the verbs are not yet registered); `pageLimited` in that test can then call `In.pageLimited` alone. `GoldenSuiteTest` will replay `drc_k` and `ima_k` through `Main.handle` as well.
4. Suggested CI line (coordinator's choice of job): `python tools/gen_k_w2a_tables.py --check` next to `gen_k_w1b_tables.py --check`.
5. Contract: the Python handover's entry says "Implemented in Python only"; after integration it becomes "Python and Java".

## Shared tables: one source (KR-50)

The five JSON files stay the only copy. The generator writes every number and list from them (decimal strings through `float`, the shortest round-trip literal); the KS thresholds become whole percentages 9 and 12 through `Decimal`, and the generator refuses a threshold that is not a whole percentage. `FrtbDrcTest.parametersMatchTables` and `FrtbImaTest.parametersMatchTables` also compare every generated constant with the JSON at test time, as the Python `test_parameters_match_tables` does. Constants not in the tables stay in the code with their source, as in Python: the KR-53 ranks, the rw cap 12.5 (`frtb-drc-rrao.md` Errors), `n >= 3` (KR-56), the surcharge factor 0.5 (MAR33.45 formula text in `mar33_ima.json`), and the normal ES factor, which is computed (`Rng.ppnd16`), one ulp from the KR-57 printed constant.

## Error order (KR-67 = HR-122) as built

Each handler reads every input first (E_SCHEMA, enum values included: bucket, seniority, rating, kind, LH category, zone, row, risk-class keys, and the `AAA/BBB` form of `fx_pair`), notes the KR-67 sizes with `In.limit`, then calls `in.gate()` (held E_LIMIT, then the finite rule), then the core: structural E_INPUT over every position before any E_DOMAIN. The core entry points also apply their own E_LIMIT first, as the Python core does. The records validate nothing on construction, so the raw-input order is kept. `In.structural` (HR-66, wave 1: E_INPUT ahead of the finite rule) is deliberately not used: KR-67 puts the finite rule first, and drc_ke-0018, ctp_ke-0008, pla_ke-0008 and es_ke-0009 pin it.

## PLA statistics (from the spec's definitions, no library)

- Spearman (MAR32.36 to MAR32.38, KR-56, KR-305): average ranks as doubled integer ranks, ties found with primitive `==` after a stable sort with a primitive comparator (so -0.0 ties 0.0, as in Python); centred doubled ranks `2r - (n + 1)`; `S_xy`, `S_xx`, `S_yy` in `long` (exact up to n = 1,000,000); `S_xx` and `S_yy` converted to binary64 before the product; clamped to [-1, 1].
- KS (MAR32.39 to MAR32.41): `d` by one merge of the two sorted lists, counting the values at or below each pooled value; `ks = d / n`; zones on integers (`100 d < 9 n`, `100 d > 12 n`).
- `Q_KS` (KR-305): 1 at x <= 0, the theta series for 0 < x < 1, the alternating series for x >= 1, terms added until one is 0, summed with the repo's correctly rounded `fsum`.
- Checks without SciPy (`FrtbImaTest`): a brute-force Spearman on average ranks in doubles and a brute-force KS over every pooled value agree on 300 random tied series; the two `Q_KS` series agree with each other on x from 0.3 to 3.9; the printed MAR32.42 p-values 0.264 and 0.055 within 1e-3.

## Evidence

| Command (JDK 25, Windows, offline, under the Maven lock) | Result |
|---|---|
| `mvn -o test -Dtest=StageKW2aCliTest` | 5 tests pass; drc_k 61 cases (18 value, 43 error, 7 two-error, 6 E1), ima_k 99 cases (33 value, 66 error, 11 two-error, 11 E1), every case passes at its golden tolerance |
| `mvn -o -Pcoverage test jacoco:report -Dtest=StageKW2aCliTest,FrtbDrcTest,FrtbImaTest` | 26 tests pass (5, 8, 13; jqwik properties at 100 to 300 tries); JaCoCo lines: FrtbDrc 292/292, FrtbIma 344/344, OpsStageKW2a 194/194, FrtbDrcTables 2/2, FrtbImaTables 9/9 (branches 153/154, 306/308, 75/76): every new file above the 90% per-file floor (R6-26), read from `java25/target/site/jacoco/jacoco.xml` |
| `python tools/gen_k_w2a_tables.py --check` | `checked 2 files` |

Largest relative difference between Java and the golden values (value cases, every number of every output, expected value nonzero): **drc_k 1.24e-16, ima_k 2.81e-15**; at the expected zeros the absolute difference is 0 in both suites. The golden tolerance is 1e-12 relative, 1e-15 absolute.

Not verified: the full Java suite, `GoldenSuiteTest` and the conformance runner through `Main` (the verbs are unregistered), mutation testing, and `tools/quality_gate.py --per-file` over the whole library (run on a report of three test classes only, so only the rows of the new files are meaningful). Property tests run 100 to 300 tries each, not the 10,000 of A3.

## Points for the coordinator (ambiguities found while porting; nothing chosen silently)

0. **A3 of `frtb-drc-rrao.md` states a false property (decision needed).** "Adding a long only to a bucket never lowers that bucket's DRC" does not hold under MAR22.25. Plain idea: DRC_b = WtdLong - HBR x WtdShort, and a new long raises the HBR, so it also raises the weight on the shorts; if its own risk weight is small next to the shorts', DRC_b falls. Formal: adding a long L with risk weight r changes DRC_b at the rate r - WS x S / T^2 (WS weighted short sum, S short sum, T = long sum + short sum), negative whenever r < WS x S / T^2, while DRC_b can still be above 0. Worked example (measured 2026-11-19): the jqwik property failed at seed -24; the same book run through the Python reference `frtb_drc.drc_nonsec` gives CORPORATE DRC_b 18.67915216395695 before and 17.739318324443047 after adding a covered long of 885 to obligor A (HBR 0.288 to 0.395). Java gives the same two values; the case is pinned as `FrtbDrcTest.a3MonotonicityCounterexample`. The Java property no longer asserts monotonicity; the other three A3 statements are asserted. The Python test `test_drc_properties` asserts the false statement and passes only because its 300 Hypothesis examples have not drawn such a book; it will fail at the 10,000 cases A3 asks for. No golden is affected. Options for the coordinator: replace the A3 sentence (for example "adding a long to an obligor with no short and a risk weight at least that of every short in the bucket never lowers DRC_b", which needs its own proof before it is used), or drop it; then align the Python test.
1. **Lane rules and the brief disagree on error order.** `LANE_RULES_K.md` (lesson, HR-66) lists "E_SCHEMA, structural E_INPUT, E_DOMAIN, E_LIMIT"; the brief, KR-67 and the goldens say E_SCHEMA, E_LIMIT, finite rule, E_INPUT, E_DOMAIN. This port follows KR-67 (the goldens fail otherwise). The lesson line in the lane rules should be updated for wave 2.
2. **Commit trailer.** `LANE_RULES_K.md` says to end commits with "Claude Fable 5.2"; the brief says to use the actual model name. The commits on this branch carry "Claude Opus 5.5", the model that wrote them.
3. **The page-limit line (registration line 2) touches `In.java`**, a central file the brief did not list. It is left as a registration line, not edited here, to avoid a merge conflict with other lanes.
4. **KR-310, carried over:** the A3 sentence of `frtb-ima.md` on single-horizon scaling is wrong; the Java properties test the two corrected statements, as Python does. "An LH class key repeated" cannot occur in Java either (a JSON object).
5. **SES underflow, carried over:** squares of charges below about 1e-154 underflow to 0 in binary64; the single-entry property is tested from 1e-100, as in Python.
