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
