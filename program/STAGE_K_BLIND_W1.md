# Stage K wave 1: blind re-derivation (DR-H2)

Date 2026-11-18. Packet: `institutional-quant-engine-plan/stage_k_blind/w1_packet/` (built by `program/stage_h_blind_w2/wave2_make_packet.sh <checkout> <dir> k1`, MANIFEST.sha256 inside, leak list `stage_k_blind/w1_LEAKS.tsv` outside it: 0 hard leaks). The blind lane (a model other than the spec lane's, given the packet only; which model was not written down on the day, and no file read on 2026-11-19 names it, so it is not named here) froze `blind_results.json`, SHA-256 `feba0b810c3f53cb2070faae99c6e2edfa96a654525a5cf6149b56462b3b81b9`, verified. The blind files are copied unchanged to `stage_k_blind/w1/`. Compare: `program/stage_h_blind_w2/k1_compare.py`, whose field mapping and tolerances were committed before the first run. Output: `stage_k_blind/w1_COMPARE.tsv`. There was one run and no rerun.

## Gaps the blind lane hit, ruled before the compare

- KR-12: `maturity <= 0` (idr_k-0006) and `ratio <= 1` (rich_k-0007) return `E_DOMAIN`. The spec did not state the code; the lane assumed `E_DOMAIN`. These two cases are gap-decided and not counted as blind.
- KR-13: a move equal to the threshold does not fire. KR-6 already said "strictly greater", and the lane read it that way. trig_k-0004 `fire` is still treated as gap-decided, so its blind fields are sigma, threshold and rate.
- KR-14: `row` is null for `WITHDRAWN` and `NONE`. bt_k-0004 and bt_k-0006 count as blind on `status` only.

## Result (38 cases; idr_k-0005 is oracle-pending and was not in the packet)

| Item | Cases | MATCH | Value mismatch | Shape mismatch | Gap-decided (whole case or field) | Provisional |
|---|---|---|---|---|---|---|
| bt_k (bitemporal store) | 10 | 10 | 0 | 0 | 2 (`row` of 0004, 0006) | 0 |
| inc_k (incremental update) | 6 | 6 | 0 | 0 | 0 | 0 |
| trig_k (recalibration triggers) | 8 | 8 | 0 | 0 | 1 (`fire` of 0004) | 0 |
| idr_k (intraday bounds) | 6 | 6 | 0 | 0 | 1 (0006, whole case) | 4 (0001-0004 `bound`) |
| rich_k (Richardson guard) | 8 | 8 | 0 | 0 | 1 (0007, whole case) | 0 |
| **Total** | **38** | **38** | **0** | **0** | 5 | 4 |

Fully blind cases (every field independent of a gap): 36 of 38. No value mismatch, so there is nothing to attribute to either side.

What this shows and what it does not. The deriver's statement that it read nothing outside its folders is its own statement, not independently logged. A match shows that the rules text is unambiguous enough to implement and that the expected values are not one author's arithmetic slip; it does not show that the rules text reads its source correctly, because the deriver reads the same rules we wrote. It is not independent or human review (no second review, owner decision 2026-11-18).

Each tolerance is the one its spec states. Small binary64 differences against the hand decimals sit inside those tolerances, for example trig `false_alarm_rate` 0.002699796063260186 against the blind 0.0026997960632601913, and rich `observed_order` last digit 7 against 9.

## Provisional

The golden `bound` of idr_k-0001..0004 is given to only 6 decimals, so it was compared at 5e-7 absolute. The blind values (for example 17.056890689124625) agree at that precision. These cases stay provisional until the oracle lane (mpmath, 30 digits) fills the bound to full precision, at which point they are re-compared at 1e-9 relative. idr_k-0005 is still oracle-pending.

## Oracle fill (2026-11-18, after the compare)

The oracle lane (`oracle/python/gen_stage_k_w1.py`, mpmath 50 digits) filled idr_k-0001..0004 `bound` to full binary64 precision and wrote idr_k-0005. The blind check of the four bounds is not upgraded: it stays a check to 6 decimals (5e-7 absolute), and `verified_by` in `datasets/golden/stage_k/idr_k.json` says so. idr_k-0005 was not in the packet and is not blind. The oracle `false_alarm_rate` of trig_k-0001..0003 is 0.002699796063260189 (the spec printed ...186, inside the 1e-14 tolerance).
