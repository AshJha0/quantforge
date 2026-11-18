# Stage H blind golden lane, wave 2: record

Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2, HR-31).

- Date: 2026-11-18.
- Spec lane: Claude Opus 5.5 (commit a459a53a), cases and expected outputs written first.
- Blind lane: Claude Sonnet, separate context, given only `stage_h_blind/wave2_packet/` (order-book.blind.md, lit-matching.blind.md, stage-h-rulings-w1.md, stage-h-rulings-w1b.md; hashes in its MANIFEST.sha256). Its own plain-Python reference; results frozen before comparison: `blind_results.json` SHA-256 `d5804576cbd64b0afcaac81541a259a28dbdcfbaaf482fc961545e6f7579eaa5`.
- Comparison: `program/stage_h_blind_w2/wave2_compare.py` (canonical JSON byte compare; book states level by level).

## Result: 19/20 MATCH on first comparison; 20/20 after one spec-lane fix

| Case | Result | Note |
|---|---|---|
| ob_h-0001 | MATCH, NOT BLIND | the cited [KR-CRC] source note prints the checksum 3310070434 |
| ob_h-0002..0008, 0010 | MATCH | |
| lit_h-0001 | MATCH, NOT BLIND | case description hints at the partial fill ("fills 1.5 of them") |
| lit_h-0002..0009, 0011 | MATCH | |
| lit_h-0010 | MISMATCH, spec lane wrong, golden fixed | P1's reprice from 100 to 99 takes the next `seq`. Counter: B1 1, B2 2, P1 3; S1 fills fully on arrival and takes none (spec: "an order that never rests ... takes none"), so the new `seq` is 4. The spec lane wrote 5. Blind lane was not rerun. |

Blind-lane interpretations recorded in its notes.md (fees as one signed net string per trader; zero-display levels omitted from `mbp`; UNKNOWN_ID cancel in `rejects` only; gap rows emit a GAP event but do not count in `messages`; crossed/locked reported after every applied message; unpriced pegs not exercised). All agree with the spec lane's values.

Outside-checked by re-derivation (DR-H2): 18 of 20 cases (ob_h 8/9, lit_h 10/11).
