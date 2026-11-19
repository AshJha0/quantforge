# Stage K wave 1b: SA-CCR blind re-derivation (DR-H2)

Date 2026-11-19. Process: `program/STAGE_H_BLIND_LANE.md`, record format of `program/STAGE_K_BLIND_W1.md`. Scope: the 11 hand value cases saccr_k-0006 to 0016 (0001 to 0005 are checked against published Basel examples; the 21 error cases are out of scope).

- Lane: Claude Sonnet 5.5 (a different model from the spec lane, which wrote the goldens with an mpmath oracle). Blind side saw: the SA-CCR spec with Expected/Check columns removed and the sections Worked example, Goldens and Acceptance cut, `sa-ccr-parameters.json`, `stage-k-rulings-w1b.md`, and the inputs of the 11 cases (`program/stage_h_blind_w2/saccr_blind_packet.py`; hashes in `stage_k_blind/saccr/packet_MANIFEST.sha256`). It did not open the SA-CCR module, the generator, the tests or any expected value before freezing.
- Frozen: `stage_k_blind/saccr/blind_results.json`, SHA-256 `370a54bd09f9a68c8041c9d5ecd18bed857b704b960cc15333e9ec6e4738e47b`, committed and pushed (1c66df94) before the compare script existed. Own reference `blind_ref.py`, assumptions in `notes.md` (12 listed).
- Compare: `program/stage_h_blind_w2/saccr_compare.py`, mapping and tolerances committed before the first run (identity field names, `simple_analytic` 1e-12 absolute + 1e-10 relative as the spec states; arrays by position; booleans, strings, null exact).

## Leaks (one process failure, stated plainly)
The lane read the unstripped spec once, before the packet was built (the instruction listed the spec as readable; the packet is stricter). That showed output facts for four cases, so these are compared but NOT counted as blind: 0006 (Example 1 intermediates in the Worked example), 0013 (the Acceptance text names MPOR 40), 0015 (names the cap), 0016 (names multiplier 0.05).

## Runs
- Run 1: compared nothing. The golden wraps outputs in an `outputs` object and the script read the wrapper level, so every leaf was shape-only (output kept in `compare_run1_wrapper_error.txt`; no value was compared or seen). Fixed as representation only (the script docstring records it) and rerun. Run 2 is the record: `stage_k_blind/saccr/compare_output.txt`.
- No blind result was changed after either run.

## Result (run 2): 11 MATCH, 0 mismatch

| Case | Result | Counted as blind |
|---|---|---|
| saccr_k-0006 | MATCH | no (leak) |
| saccr_k-0007 to 0012 | MATCH | yes |
| saccr_k-0013 | MATCH | no (leak) |
| saccr_k-0014 | MATCH | yes |
| saccr_k-0015, 0016 | MATCH | no (leak) |

Every named output leaf (all top-level fields, hedging sets, and the seven named per-trade fields; 27 to 74 leaves per case) agrees within tolerance; no unnamed per-trade key exists in the goldens.

Notable: the lane's open assumptions (option MF from `maturity`, not `exercise`; scaled `supervisory_factor` per trade; commodity hedging-set key names; margined per-trade `maturity_factor`) all agreed with the goldens, so there is nothing to attribute to the spec, the implementation or the lane. No disagreement for the coordinator.

## Outside share
Published checks 5 plus blind-matched 7 = 12 of 16 value cases = 75% (floor 60%). The four leaked cases matched but are excluded; counting them would give 16 of 16, which this record does not claim. The goldens' `verified_by` and the spec Acceptance line (31%) were not edited by this lane; the coordinator updates them.
