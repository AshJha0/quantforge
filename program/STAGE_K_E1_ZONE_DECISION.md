# Stage K: the E1 gate on `risk.frtb.backtest.zone` (decision taken: option A, ruling KR-112)

Owner decision 2026-11-19, 17:44 UTC: option A, refine the gate, as the stage F refinement F-2a was done. Implemented by the integration lane on `k-r1` the same day. Ruling: `specifications/stage-k-rulings-w1b.md`, KR-112.

## Plain idea

The E1 gate wants every operation to show that it refuses a NaN or an infinity with `E_DOMAIN`. An operation whose inputs are all integers cannot be sent a NaN as a number at all, so the gate lets it off, provided no golden sends it a decimal number. `risk.frtb.backtest.zone` takes three integer counts, and one golden, btk_k-0029, sends it 1.5 to check that a non-integer count is refused (`E_SCHEMA`). That golden blocked the exemption, although it is evidence for the exemption's premise.

## The rule before

`tools/check_e1_coverage.py`, as it read before KR-112: "every operation in specifications/name-map.json has an E1 golden, a case whose inputs carry "NaN", "Infinity" or "-Infinity" and whose expected result is E_DOMAIN (ruling F-2), unless it is listed in conformance/E1_EXEMPT.json, and an exempt operation must have no Real (JSON float) input in any golden."

## The rule now (KR-112)

An exempt operation may carry a Real input only in goldens whose expected result is `E_SCHEMA`. A Real in any other golden still makes the exemption a problem. Every other condition is unchanged; nothing changes for operations that are not exempt. In code: a golden's Real input marks its operation as "has a Real input" unless that golden expects `E_SCHEMA`.

Why this is not a weakening: the exemption now permits exactly one more case than before, a Real sent to an Integer field in a golden that checks it is refused. A Real the operation actually computes with would show in a value golden or in an error golden expecting a later code, and is still caught.

## Evidence (measured 2026-11-19, local laptop, not the acceptance machine)

- `python tools/check_e1_coverage.py --self-test`, planted faults, all failing as required before the exemption entry was added: (a) a non-exempt operation without its NaN golden fails; (b) an exempt operation with a Real in a golden expecting `E_DOMAIN`, `E_INPUT`, `E_LIMIT` or a value fails; (c) an operation with a genuine Real input put on the exemption list fails; (d) an exempt Integer-only operation whose only Real is in an `E_SCHEMA` golden (the btk_k-0029 shape) passes.
- On the real tree with the entry added, btk_k-0029 changed to expect `E_DOMAIN` gives `risk.frtb.backtest.zone: exempt but has a Real input in a golden` (red).
- Gate on `k-r1`: "E1 coverage: 336 of 368 operations have an E1 golden, 32 exempt (no Real input outside E_SCHEMA goldens, KR-112), 0 problems".
- `conformance/E1_EXEMPT.json` gains `risk.frtb.backtest.zone`. btk_k-0029 is unchanged.

## Option not taken

Option B (move the 1.5 rejection out of the shared goldens into four per-language unit tests) would have needed no gate change but would have removed the cross-build check of that refusal from the neutral runner.
