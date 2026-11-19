# Stage K: the E1 gate on `risk.frtb.backtest.zone` (owner decision needed)

Written 2026-11-19 by the integration lane (k-r1). Nothing in the gate, the exemption list or the goldens was changed. `python tools/check_e1_coverage.py` stays red on this one operation until the owner chooses (evidence class: measured, local laptop, 2026-11-19: "E1 coverage: 336 of 368 operations have an E1 golden, 31 exempt (no Real input), 1 problems"; the problem line is `risk.frtb.backtest.zone: no E1 golden`).

## Plain idea

The E1 gate wants every operation to show that it refuses a NaN or an infinity with `E_DOMAIN`. An operation whose inputs are all integers cannot be sent a NaN as a number at all, so the gate lets it off, but only if no golden sends it a decimal number. `risk.frtb.backtest.zone` takes three integer counts. One golden, btk_k-0029, sends it the decimal 1.5 to check that a non-integer count is refused (`E_SCHEMA`). That single golden is what blocks the exemption.

## The rule as written

`tools/check_e1_coverage.py`, docstring (read 2026-11-19):

> every operation in specifications/name-map.json has an E1 golden, a case whose inputs carry "NaN", "Infinity" or "-Infinity" and whose expected result is E_DOMAIN (ruling F-2), unless it is listed in conformance/E1_EXEMPT.json, and an exempt operation must have no Real (JSON float) input in any golden.

Code: an operation with any golden whose inputs contain a JSON float is in the set `real`, and `exempt & real` is reported as "exempt but has a Real input in a golden".

## The golden

`datasets/golden/stage_k/btk_k.json`, generator `oracle/python/gen_stage_k_w1b.py`:

```json
{"case_id": "btk_k-0029", "operation": "risk.frtb.backtest.zone",
 "inputs": {"observations": 250, "exceptions_actual": 1.5, "exceptions_hypothetical": 0},
 "expected": {"status": "error", "error_code": "E_SCHEMA"}, "description": "hand: count not an integer"}
```

A NaN golden cannot satisfy the gate either: every build answers a non-finite token in an Integer field with `E_SCHEMA` (not an integer), not `E_DOMAIN` (spec `specifications/06-risk/frtb-ima-backtest.md`, goldens table, row btk_k-0039/0040; checked in all four builds 2026-11-19). The sibling `risk.frtb.backtest.desk` is already exempt (`conformance/E1_EXEMPT.json`).

## Option A: refine the gate

Change the exemption condition to: an exempt operation may carry a Real input only in goldens whose expected result is `E_SCHEMA` (the Real is then the thing being refused, never a value the operation computes with). Add `risk.frtb.backtest.zone` to `conformance/E1_EXEMPT.json` with that reason. Extend `--self-test` with a planted fault: for every non-exempt operation, a planted build path where a NaN input returns a value or `E_SCHEMA` instead of `E_DOMAIN` must still turn the gate red, so the refinement cannot hide a NaN-to-`E_DOMAIN` gap anywhere else.

Cost: one gate edit plus self-test cases (about an hour of tooling work; no build of the four libraries is needed); the shared golden and its cross-build check stay. Risk: it is a change to a gate's condition, which the lane rules reserve to the owner; the refinement is narrow (only `E_SCHEMA` goldens, only exempt operations) but it is still a relaxation of the written rule and should be recorded as a ruling (in the style of F-2a).

## Option B: move the rejection case out of the shared goldens

Remove btk_k-0029 from `btk_k.json` (via the generator) and keep the 1.5 rejection as four per-language unit tests (Python, Java, C++, Rust). Then the operation has no Real input in any golden and can be listed in `conformance/E1_EXEMPT.json` under the existing rule, with no gate change.

Cost: four unit tests and one generator edit; the error-case count drops by one (case figures, README and site regenerate); the neutral runner no longer checks the four builds against each other on this input, so the cross-build guarantee for "a non-integer count is refused with `E_SCHEMA`" becomes four separate tests that could drift. The exemption list still gains one entry. Golden-count tests that use minimums are unaffected; any exact count must be checked.

## What is not decided here

Which option, and whether the refinement in A should be a numbered ruling. Until then the gate is red on this operation and is reported as red.
