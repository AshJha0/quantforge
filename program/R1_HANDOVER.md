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

## R5 rulings R1-1 to R1-5 (ready)

Read `specifications/r1-rulings.md`, and the changed text in `04-pricing/bonds.md` (`bond.futures.conversion_factor`), `04-pricing/credit.md` (Curves) and `edge-case-register.md` (row E13). New suite `datasets/golden/stage_d/rulings_r1.json`, 15 cases. No existing golden changes.

Behaviour to build:
1. `bond.futures.conversion_factor` takes an optional `contract` (`TWO_YEAR`, `THREE_YEAR`, `FIVE_YEAR`, `TEN_YEAR`, `ULTRA_TEN_YEAR`, `BOND`, `ULTRA_BOND`, or `null` = `TEN_YEAR`; another string `E_SCHEMA`). It rounds the coupon to the nearest 1/8 of 1% (ties up) first. 2Y, 3Y and 5Y use whole months. `v = z - 6` for `z >= 7`.
2. Every `credit.*` operation: `discount.interpolation` other than `LOG_LINEAR_DF` is `E_INPUT`, before every other rule check.
R1-1, R1-2 and R1-5 change only labels.

## Ruling R1-6: USGS Good Friday early closes (ready)

Read `specifications/01-core/calendars.md` (USGS, version 1.1.0), `specifications/02-curves/overnight-compounding.md` (SOFR calendar), `specifications/r1-rulings.md` R1-6 and register row E14.

1. `USGS`: Good Friday is a holiday except 2007-04-06, 2010-04-02, 2012-04-06, 2015-04-03, 2021-04-02, 2023-04-07 and 2026-04-03, which are business days (SIFMA early closes).
2. SOFR compounding (`rates.ois.compound_dated`, `rates.fallback.rate` on SOFR) treats every Good Friday as a non-business day, because the NY Fed publishes no SOFR then.

Changed goldens: `core/calendar.json` cases `calendar-0033`, `-0035`, `-0037`, `-0040` (USGS holidays for 2012, 2021, 2023, 2026). New: `stage_d/edge_d` cases `edge_d-0018` to `edge_d-0024`. No other golden changed (full `run_all.py` regeneration, 2026-11-07).
