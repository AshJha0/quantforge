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

## Coordinator decisions 2026-11-18 (HR-109 to HR-113), implementation lane
- **rtc_h-0004 loses blind status**: HR-109 (CME quarter-32nds) changes its expected value from 99.52734375 to 99.5234375 (`7` is now 3/4 of a 32nd, not 7/8). Its verified_by is now `hand` only. H-24 blind share drops by one case.
- HR-111 removes the `label` field from eqc_h, fxc_h and rtc_h outputs. Values did not change and the blind lane never compared labels, so those cases stay blind.
- New hand cases, not blind: rtc_h-0011/0012 (yield solve), fxv_h-0010..0012 (core.rng draw; u from the oracle's own xoshiro), ses_h (session phases), acls_h (asset class on SOR). The rtc_h and fxv_h error-case ids after the table rows were renumbered (hand cases only).

## Rates blind packet 2 (HR-114), 2026-11-18
- Packet: `institutional-quant-engine-plan/stage_h_blind/rates2_packet/` (stripped rates spec, rulings, inputs; leak list `rates2_LEAKS.tsv` outside). Cases: the 7 hand-only H-24 value cases rtc_h-0004, 0007, 0011, 0012, fut_h-0004, 0005, 0006.
- Blind lane: Sonnet, packet only, frozen by the coordinator. `blind_results.json` SHA-256 `3a3a9db05ec1a1a7eeba01bc736672933f27609d050d8020da466496720ca354` (verified); copies unedited in `stage_h_blind/rates2/`.
- Mapping and compare script `program/stage_h_blind_w2/rates2_compare.py`, committed before the comparison ran (one crash fix in loading error cases, committed before any output). Field names equal; decimals by value; `yield` to the root_finding tolerance; labels compared. One run, no rerun.
- Result: 7 of 7 agree. MATCH 3 (rtc_h-0004, 0011, 0012); REPRESENTATION-ONLY 4 (rtc_h-0007 "15.625000", fut_h-0004/0005 pnl and fees with trailing zeros, fut_h-0006 "-31.25000"); VALUE MISMATCH 0, so nobody was found wrong.
- Caveats: fut_h-0004..0006 were computed with HR-102/103 given as written rules (the reason they were not blind before was that those readings were missing from the spec). rtc_h-0007's 15.625 was removed from the packet text. rtc_h-0004 uses HR-109's quarter-32nds, whose CME source is still unverified (HR-115); agreement checks the arithmetic, not the convention.
- H-24 share: 16 of 16 value cases now blind and agreeing = **100 %** (60 % rule met; was 56.2 %). Update 2026-11-19: three hand-only `exec.sim.fut.run` value cases (fut_h-0011 to fut_h-0013) were added, so the share is 16 of 19 = 84.2 %.

## Source record update 2026-11-19 (HR-117)

- [CME-ZN] read in a browser (https://www.cmegroup.com/markets/interest-rates/us-treasury/10-year-us-treasury-note.contractSpecs.html): face $100,000, outright tick 1/2 of 1/32 ($15.625), calendar-spread tick 1/8 of 1/32, quarterly Mar/Jun/Sep/Dec with three consecutive quarters, last trade 12:01 p.m. CT seven business days before the last business day of the month, deliverable 6.5 to under 8 years, conversion factor at 6 %. Verified; no golden or spec value changes.
- [CME-32NDS] still unverified: the page shows quotes like 105'250 but does not define the third digit. rtc_h-0004 stays hand-only.
