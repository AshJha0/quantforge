# Stage K ruling on xVA error codes (KR-258)

Written 2026-11-20 by the lane `k-v1-fix`. **Status: PROPOSED** (awaits the stage K coordinator). Separate file so the branches merge without conflict. Source: the KR-257 lane recorded, under "Not changed" in `stage-k-rulings-wwr.md`, that a non-positive first time in `xva.wwr.cva_hw` is `E_INPUT` in Python and Rust and `E_DOMAIN` in C++ and Java, and that no golden sends it (read, 2026-11-20).

## What was found

**Plain idea.** Two builds called a first time of 0 a malformed input and two called it a value out of range. A caller that branches on the error code got a different answer depending on the build. Conformance did not see it because no golden case sent such a time.

**Measured (code read, commit fbf3998e, 2026-11-20).** `xva.wwr.cva_hw`: Python `xva.py` `wwr_cva` and Rust `xva.rs` `wwr_cva_hw` raise `E_INPUT` ("times must be positive and increasing"); C++ `ops_xva.inc` `op_xva_wwr` and Java `OpsXva` raise `E_DOMAIN` ("times must be after 0"). The sibling `xva.adjustments.value` has the same split, in the same builds, with the same messages (read). `xva.exposure.collateralised` allows `t_0 = 0` (its grid starts at the valuation date) and checks only strict increase, `E_INPUT` in all four builds (read).

## Which code the rules give

**Formal statement.** HR-122 (`stage-h-rulings-audit.md`), adopted for stage K by KR-67 and KR-230, lists under step (4), structural `E_INPUT`: "an empty or missing list, a count below 1, lengths, ordering, ..., cross-field consistency"; step (5), `E_DOMAIN`, is "one value outside its domain". For both operations the spec defines the buckets as `(t_(i-1), t_i]` with an implied `t_0 = 0` (`06-risk/xva-framework.md`, "buckets from 0"). A first time at or below 0 makes the first bucket empty or reversed: it is the strict-increase condition `t_0 < t_1` applied to the implied first point, so it is an ordering fault of the grid, step (4).

**Precedent in other specs (read, 2026-11-20).** The same condition is `E_INPUT` wherever a spec names it: `02-curves/financing-term-structure.md` ("a time array not positive and strictly increasing: `E_INPUT`"), `08-hedging/cross-asset-hedge.md` ("a first time at or below 0: `E_INPUT`"), `08-hedging/dynamic-hedge-and-effectiveness.md` (`times[0] != 0`: `E_INPUT`), and `01-core/interpolation.md` treats `t_1 > 0` as part of the strictly increasing grid with `t_0 = 0` implied. No spec classifies a non-positive grid point as `E_DOMAIN` (inferred from a `git grep` over `specifications/`, which found none).

**Worked example.** `xva.wwr.cva_hw` with `times = [0, 0.5, 0.75, 1]` and `hazard_rate = -0.01`: two faults, the first an ordering fault (step 4), the second a domain fault (step 5). The answer is `E_INPUT` in all four builds after this ruling; before it, C++ and Java said `E_DOMAIN` for the first fault alone and Python and Rust said `E_INPUT`.

## Ruling

| # | Point | Ruling | Evidence |
|---|---|---|---|
| KR-258 | Code for a first time at or below 0 in `xva.wwr.cva_hw` and `xva.adjustments.value` | **`E_INPUT`** (HR-122 step 4: ordering of the time grid against the implied `t_0 = 0`), checked together with the strict increase of `times` and before every `E_DOMAIN` check. C++ (`op_xva_wwr`, `op_xva_adjustments`) and Java (`OpsXva`) change from `E_DOMAIN`; Python and Rust are unchanged. `06-risk/xva-framework.md` says so in both input lists. Goldens (`gen_stage_g_w4b.py`, `first_time_cases`, tag `kr258`): six per operation, appended to `wwr_g` (26 to 32) and `xvaadj_g` (12 to 18): first time 0, negative, two equal times, decreasing times, and two two-error cases (a non-positive first time with a negative hazard rate: `E_INPUT` first). | Code read and four-build probe, this file; HR-122, KR-67, KR-230 |

**Behaviour change.** A request with a first time at or below 0 returned `E_DOMAIN` from the C++ and Java builds of both operations since v0.7.0 and now returns `E_INPUT`, as Python and Rust always did. No valid request changes; no golden changes its code.

**Not changed.** The models, the tolerances, the outputs, and every other error code. `xva.exposure.collateralised` keeps `t_0 = 0` allowed.

## Sweep of the other xva operations (2026-11-20)

**Plain idea.** If two builds disagreed on one error code that no golden sent, others may too. A small random differential run sends many slightly broken requests to the four command-line builds and compares only the error codes.

**Method (measured, 2026-11-20).** `program/stage_k_fix/fuzz.py` takes the valid golden inputs of `xva.exposure.collateralised`, `xva.adjustments.value`, `xva.sbim.ir_delta` (and its alias), `xva.wwr.cva_hw`, `xva.exposure.portfolio_hw` and `xva.exposure.swap_ee_hw`, and applies one or two random faults each (a deleted key, a wrong type, an empty, short, long, reversed or repeated list, a boundary or out-of-range number, 1e400). Two seeded runs (258 and 259), 300 requests per operation each, 3,600 requests in all, sent to the four builds of this branch by `program/stage_k_fix/probe.py`. Codes only; numeric outputs were not compared beyond noting ok against error.

**Fixed here (HR-122, clear).** C++ read and checked each input in turn in the three stage G wave 4b handlers, so a structural or domain fault reported before an `E_SCHEMA` fault in a later field, and a structural fault before a non-finite token (about 40 of the 3,600 requests). The handlers now read every input first. Goldens: 11 two-error cases, tag `hr122` (`collexp_g-0018` to `-0020`, `xvaadj_g-0019` to `-0021`, `wwr_g-0033` to `-0037`), red on C++ before the change.

**Found and not fixed (listed for the coordinator).**

| # | Operation | Divergence (codes: Python, Java, C++, Rust) | Why not fixed here |
|---|---|---|---|
| S1 | `xva.exposure.swap_ee_hw`, `xva.exposure.portfolio_hw` | The same read-as-you-check pattern in C++: `E_INPUT` or `E_DOMAIN` where the other three say `E_SCHEMA` (about 40 requests) | Shared helpers `sr_hw`, `sr_curve`, `sr_payments` serve every `rates.shortrate.*` operation; a change there needs its own conformance pass |
| S2 | `xva.exposure.portfolio_hw` | A non-positive exposure time: `E_INPUT`, `E_INPUT`, `E_DOMAIN`, `E_INPUT`; the spec says only "reset dates ... else `E_INPUT`" | Clear by the spec; `expsim_g` is written by `gen_stage_g_w4c.py`, which needs the ORE run files to rewrite the suite, so this lane had no generator to add the golden through |
| S3 | `xva.exposure.portfolio_hw` (all Hull-White curve inputs in C++) | C++ `sr_curve` checks `df > 0` in the same loop as increasing times, so an earlier domain fault beats a later structural one: `E_INPUT`, `E_INPUT`, `E_DOMAIN`, `E_INPUT` | Shared helper, as S1 |
| S4 | `swap_ee_hw`, `portfolio_hw` | A curve-time structural fault with `sigma <= 0`: `E_DOMAIN`, `E_DOMAIN`, `E_DOMAIN`, `E_INPUT`. Rust follows HR-122; the other three check the model parameters first | Shared model-parameter code in three builds |
| S5 | `swap_ee_hw` | The spec (G-16) puts the exposure-time value check (`E_DOMAIN`) before the order check (`E_INPUT`); all four builds follow it, against the HR-122 order | Explicit spec text; a spec decision |
| S6 | `swap_ee_hw` | A discount factor of 1e308: `E_NON_FINITE`, `E_DOMAIN`, `E_DOMAIN`, `E_DOMAIN` (the G-29 "no critical rate" check meets a non-finite intermediate). R6-8.1 says a non-finite result from finite inputs is `E_NON_FINITE`, never `E_DOMAIN`, so Python follows the rule | Shared Jamshidian code in three builds |
| S7 | `sbim.ir_delta`, `portfolio_hw` | Extreme inputs give ok in some builds and `E_NON_FINITE` in others: sensitivities -1e308 (Java alone `E_NON_FINITE`); a notional of -1e308 (Python alone ok, CVA 2.6e305); a discount factor 1e-310 (Java and Rust `E_NON_FINITE`); `mean_reversion` 700 (C++ alone ok, CVA 0) | Whether an intermediate overflows depends on how each build arranges the formula; no rule picks one |
| S8 | `portfolio_hw` | Empty `pfe_quantiles`: `E_DOMAIN`, ok, ok, ok | Spec silent |
| S9 | `portfolio_hw` | A payment time of 700 years: `E_INPUT`, `E_INPUT`, ok, ok | Not investigated |

No divergence was found in `xva.sbim.ir_delta` except S7. After the fix the same two runs, repeated on the fixed builds of this branch, show no error-code difference in the three wave 4b operations (measured, 2026-11-20 19:40 UTC); the 44 remaining code differences of the 3,600 requests are all S1 to S9.
