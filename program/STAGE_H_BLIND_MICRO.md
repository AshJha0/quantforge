# Stage H blind golden lane, micro packet (H-4b, H-16): record

Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2, HR-31).

- Date: 2026-11-18.
- Spec lane: Claude Opus 5.5 (commits 50ac041a, 99549db8). It wrote the `mest_h` and `venue_h` cases and their expected outputs first.
- Blind lane: separate context. It was given only the micro packet: micro-estimators.blind.md, venue-analytics.blind.md and stage-h-rulings-micro.md. The packet was built by `wave2_make_packet.sh <repo> <dir> micro`, and its hashes and leak list are in `stage_h_blind/micro/` (`LEAKS.txt`). The lane wrote its own reference, `blind_ref.py`, using Decimal at 60 digits. Its results were frozen before comparison: `blind_results.json` SHA-256 `975000bfcf123c983b3e444f6234685ce2b666378405f173585ab9318a6bf0f3` (verified before comparing; copy in `stage_h_blind/micro/`).
- Comparison: `program/stage_h_blind_w2/wave2_compare.py <repo> <blind> micro`.
  - The Expected cells are prose. The script compares the numbers in the cell with the blind leaf values as sorted multisets: 1e-12 relative, or 1e-15 absolute at 0, the spec tolerance. Error codes are compared exactly.
  - A case is SHAPE-ONLY when the values agree but a blind field name does not appear in the cell (for example `beta` against `lambda_as`).
  - Limitation: the multiset compare would not catch two values swapped between fields of equal magnitude. The two cases where this could matter, venue_h-0001 and 0002, were checked by hand field by field.

## Result: 12 MATCH (one of them, venue_h-0006, NOT BLIND), 6 SHAPE-ONLY, 0 VALUE MISMATCH (18 packet cases); venue_h-0008 added post-blind

| Case | Result | Note |
|---|---|---|
| mest_h-0001..0007, 0010, 0011 | MATCH | |
| mest_h-0008, 0009 | SHAPE-ONLY | blind field `beta`, spec `lambda_as` / per-regime beta |
| venue_h-0001..0003 | SHAPE-ONLY | the spec cell says `bps`; the blind field is `markout_bps` |
| venue_h-0004 | SHAPE-ONLY | blind keys `fill_rate\|A`; the spec cell says `A 0.6` |
| venue_h-0005, 0007 | MATCH | |
| venue_h-0006 | MATCH, NOT BLIND | spec gap: the packet gave no horizon. The blind lane chose h = 0, but with h = 5 the lookup at t 4 succeeds and no error occurs (blind notes), so the gap decided the answer. Post-blind change: the input now states h = 0 |
| venue_h-0008 | not in packet | post-blind golden for HR-75 (both `E_DOMAIN` and `E_INPUT` apply; `E_DOMAIN` reported). Hand calculation only |

## Post-blind changes (2026-11-18)

1. `venue-analytics.md` venue_h-0006: the input now includes `h = 0` and the case is marked as not blind-checked.
2. Error precedence was unstated; the blind notes flag it ("A case with both is untested"). New ruling HR-75 says `E_DOMAIN` is checked before `E_INPUT`, the order the blind lane also chose. That agreement is not evidence, because the case was untested. The new venue-analytics errors line cites HR-75, and golden venue_h-0008 was added.

No spec golden value was wrong, and the blind lane made no value errors. No rerun.
3. HR-75 as amended (HR-66) (coordinator decision, 2026-11-18, after the implementation lane started) replaces HR-75 with the repo-wide order: structural `E_INPUT`, then `E_DOMAIN`. venue_h-0008 is now `E_INPUT`. mest_h-0006 is now `E_INPUT` (n = 2 is structural); its blind MATCH was under the old order and is no longer claimed, so the golden carries `hand` only.
