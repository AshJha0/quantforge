# R1 handover

From the spec and oracle session to the four clean-room language sessions. Date 2026-11-07. Kept current as R1 items land.

## R1.7 batch mode (ready)

Contract 1.6.0. The wire format does not change, so `version` still reports `contract_version` `1.0.0`.

What to build, in every language:
1. `quantforge --batch` as an exact synonym of `quantforge batch`.
2. The optional `--timings` flag on `batch`, `--batch` and `run`: `diagnostics.elapsed_ns` on every result, and nothing else changes.
3. BT5: a line over 16,777,216 bytes is `E_LIMIT` with `case_id: "unknown"`, decided on length, without parsing; the stream continues.
4. Every other rule (BT1 to BT4, BT6 to BT8) already holds in all four v0.4 builds. Keep it holding.

Read only these:
- `specifications/cli-contract.md`: the Invocation table and the "Batch mode" section. Read the rest of the file as before.
- `specifications/01-core/limits.md`
- `datasets/batch/streams.json`, the stream fixtures
- `conformance/runner/batch_check.py`: run it; do not change it

Do not read `oracle/` or any other session's language tree.

Check:

```bash
python conformance/runner/batch_check.py --impl <lang>
```

The full run includes a `run` call per sampled case, which is slow on the JVM. `--skip-run` leaves out that one check. `python conformance/runner/runner.py --impl <lang>` must still pass every golden.

Status on the v0.4 builds (observed 2026-11-07, all four the same): 14 of 19 streams pass, plus equivalence, reorder and interactive. The 5 failures are the new items: bt-0012 (BT5), bt-0015 to bt-0017 (`--batch` and `--timings`) and timings_identity.

Questions go in your `SPEC_QUESTIONS` file as before; the spec session rules on them and pins each ruling with a fixture.
