# Stage H blind golden lane, use case 5: record

Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2).

- Date: 2026-11-18.
- Spec lane: the oracle lane (commit cabdd8f4) wrote use case 5 and `uc5_h` with `oracle/python/gen_stage_h_w1.py` first.
- Blind lane: Sonnet, separate context, given only the uc5 packet (schedules, almgren-chriss, impact, tca and use-case-5 text stripped of Expected, Derivation and Check columns by `program/stage_h_blind_w2/wave2_extract.awk`; rulings w1 and w1b; `uc5_cases.blind.md` with Case and Input only). Packet hashes in `stage_h_blind/uc5/packet_MANIFEST.sha256`, known leaks in `stage_h_blind/uc5/packet_LEAKS.md`. Own plain-Python reference; results frozen before comparison: `blind_results.json` SHA-256 `2bab6fb7c55b19b0f4698d6f4e0d444c9465ab3637062f678eb0b02cf118fe33` (verified before comparing).
- Comparison: the coordinator, then the integration lane again: integer outputs (`lots`, `filled`) exactly, reals by relative difference.

## Result: 3 MATCH, 0 VALUE MISMATCH (3 value cases)

| Case | Result | Note |
|---|---|---|
| uc5_h-0001 | MATCH | max relative difference 4.2e-15; lots identical |
| uc5_h-0002 | MATCH, NOT BLIND | the packet printed the linear-case standard deviation 1.0407e6 on parameter set P (almgren-chriss.blind.md), which gives away `variance` |
| uc5_h-0003 | MATCH | max relative difference 2.1e-14; lots [334, 333, 333] identical |

Outside-checked by re-derivation (DR-H2): 2 of 3 (H-6 meets the plan 15 item floor at 66.7%). Not counted: uc5_h-0002. The error cases were not sent to the blind lane.

Files: `stage_h_blind/uc5/` (blind_ref.py, blind_results.json, blind_results.sha256, notes.md, packet_MANIFEST.sha256, packet_LEAKS.md).
