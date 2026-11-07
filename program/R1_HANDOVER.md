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

## R1.1 outside-oracle suite (ready)

New golden suite `datasets/golden/stage_d/outside_d.json`, 284 cases. It uses existing stage D operations only (`bond.*` price, yield, curve price and Z-spread; `rates.ois.compound_dated`; `rates.cap.price`; `rates.swaption.price`; `credit.cds.price`), so no new code should be needed. Run it through the runner as usual. Read nothing new beyond the specs you already have.

Observed 2026-11-07: the stage D builds in the four language worktrees pass 284 of 284 (Rust, C++, Java, Python).

## R1.8 edge-case suite (ready)

New golden suite `datasets/golden/stage_d/edge_d.json`, 17 cases, existing operations only. It pins rows of `specifications/edge-case-register.md` (which you may read). Observed 2026-11-07: all four language-worktree builds pass 17 of 17.
