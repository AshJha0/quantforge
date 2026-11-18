# Stage H multi-asset blind re-derivation (H-22, H-23, H-24), 2026-11-18

## What was run
- Packet: `stage_h_blind_w2/wave2_make_packet.sh` mode `m` (commits dd2e13a0, 62a617c8). Packet files were built at 20:21, after the one prose leak (the eqc_h-0005 example) had been removed. Leak list: `stage_h_blind/multiasset_LEAKS.tsv`, outside the packet.
- Blind lane: Sonnet, given the packet only. Its output was frozen at 20:23. The lane's `blind_results.json` has SHA-256 `b7fa4a939f2e4fc8b0b8b4247929c5fc41f8d01a3022fff9e230a8e23c2cfee5` (verified). Copies of `blind_results.json`, `blind_results.sha256`, `notes.md` and `blind_ref.py` are in `stage_h_blind/multiasset/`. None of them was edited.
- Case count: the specs hold **48** golden cases, not 60: auc 8, eqc 8, fxc 7, fxv 9, rtc 10, fut 6. The lane computed all 48, so no case is missing and none was skipped.

## Order of work (each step committed before the next)
1. Pre-comparison spec fixes in commit 9bd8da06:
   - HR-100: output field names and shapes, added as "Output shapes" sections in all four specs.
   - HR-101: what an auction with no candidate price outputs.
   - HR-102: fut_h-0004/0005 are one participant's round trip; the fee is charged per contract per side.
   - HR-103: on the trade day, the previous mark for variation margin is the fill price.
2. Field mapping and compare script: `program/stage_h_blind_w2/multiasset_compare.py`, in the same commit 9bd8da06, before the first run. The lane's field names equal the spec names, so nothing is renamed. Extra blind fields are ignored. Decimals are compared by value.
3. Comparison: one run, and no rerun of the lane.

## Result
| Class | Cases |
|---|---|
| MATCH | 41 |
| REPRESENTATION-ONLY | 7: fxc_h-0001/0002 ("100.0000" vs "100"), rtc_h-0007 ("15.625000"), rtc_h-0008/0010 (12 dp vs golden 9 dp, within 5e-10), rtc_h-0009 ("100.000000000000") |
| VALUE MISMATCH | 0 |

No mismatch needed investigating, so neither side was found wrong. The lane's interpretations in `notes.md` agree with the rulings written afterwards (HR-101 to HR-103).

## Blind status (cases decided by a spec gap or by a value given in the spec text do not count)
- fut_h-0004, fut_h-0005: the answer depended on the round-trip reading, which the spec did not state (now HR-102). **Not blind.**
- fut_h-0006: the answer depended on taking the fill price as the previous mark, which the spec did not state (now HR-103). **Not blind.**
- rtc_h-0007: the tick value 15.625 appears in the spec text as the ZN contract default. **Not blind** (a soft leak).
- Noted but still counted as blind:
  - fut_h-0001/0002 are an inverse pair.
  - auc_h-0002 has the same input as auc_h-0001.
  - fxv_h-0001/0002 needed a one-point mid path (the lane's own reading; the answer does not depend on it).

| Item | Cases | Blind and agreeing | Share | 60 % rule |
|---|---|---|---|---|
| H-22 equities (eqc, auc) | 16 | 16 | 100 % | met |
| H-23 FX (fxc, fxv) | 16 | 16 | 100 % | met |
| H-24 rates (rtc, fut) | 16 | 12 | 75 % | met |
| All | 48 | 44 | 92 % | met |

## Limits
- All sources in the specs are still tagged unverified (HR-98). Agreement with the blind lane checks the arithmetic, not whether the venue rules are right.
- Labels were not compared.
- The goldens state only some fields (for example, auc_h-0003..0006 state price, volume and imbalance, not the fills).

## Rule-version fixes after the source check (2026-11-18, implementation lane)
Coordinator rulings HR-104 to HR-108 (Rule 612 half-penny tier, Rule 610 $0.001 cap, Rule 600 round lots, FX USD-only T+1 holiday, auction tie-break as a venue parameter). The goldens were regenerated through `oracle/python/gen_stage_h_ma.py`. **No blind case changed its expected value**: the defaults keep the penny tier for eqc_h-0001..0006; eqc_h-0007 (0.0031 at $20) is still E_DOMAIN under the $0.001 cap; fxc_h-0004 still settles 2026-11-27 (Thursday is not good in both currencies at T+2); auc_h rows use the default CBOE tie-break. So no case loses blind status and the shares above stand. New cases eqc_h-0009..0017, fxc_h-0008 and auc_h-0009 are hand-derived and **not blind**; they do not count toward the 60 % rule.
