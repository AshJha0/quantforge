# Stage K wave 2: five open Basel readings, one recommendation each

Written 2026-11-20 by the k-r3-w2 lane. These are recommendations only: every ruling named here stays PROPOSED in `specifications/stage-k-rulings-w2.md` until the coordinator confirms it. Nothing in code, goldens or rulings was changed for this file.

Sources. The Basel Framework on bis.org, in-force chapter pages fetched 2026-11-20: LEX20, LEX40, MAR50 and LEV30 (the in-force versions linked from `bis.org/basel_framework/chapter/<CHAPTER>/<NN>.htm`). The pages were read through a fetch tool that summarises and quotes in short fragments, so "read" below means the quoted fragment was seen; the tables were seen as rendered by that tool. Footnote numbers on the web pages differ from the consolidated PDF (LEV30.31: footnote 14 on the web page, 384 in the PDF of 11/11/2026). No ISDA and no LSEG material was used.

Naming note. The brief listed the G-SIB group question as KR-322. In the rulings file KR-322 is "LEX trading positions"; the G-SIB group rule and the `bank_gsib` field are both in **KR-324** (with the default in KR-319). Items 1 and 5 below are the two halves of KR-324.

## 1. KR-324, group rule: "any member" or "every member" is a G-SIB

Plain idea: a G-SIB bank must keep its exposure to another G-SIB under 15% of Tier 1 instead of 25%. When the counterparty is a group of connected counterparties with some members flagged G-SIB and some not, which limit applies?

- Text (read): LEX20.1 puts the 25% limit on "a single counterparty or ... a group of connected counterparties" and continues "this figure is set at 15% for a global systemically important bank's (G-SIB's) exposures to another G-SIB". LEX40.1 repeats the 15% for exposure "to another G-SIB"; LEX40.3 says G-SIB status is assessed at the consolidated group level. Neither chapter says how the 15% applies to a connected group that only partly consists of G-SIB entities.
- Reading A, any member (implemented): the group takes 15% when `bank_gsib` and at least one member is flagged. Reading B, every member (the blind lane's assumption): 15% only if all members are flagged.
- Which the text supports: neither directly. Under LEX40.3 a G-SIB is a consolidated group, so every entity of that banking group is "the G-SIB"; a connected group that contains it holds an exposure to another G-SIB, and reading B would let a non-G-SIB member (for example an economically dependent corporate) lift the whole group to 25%. Reading A is the one that never gives a looser limit than the text gives the G-SIB on its own. Evidence class: **inferred** (from read text).
- Recommendation: **confirm A (any member)**, and add one golden with a mixed group (one member flagged, one not, exposure between 15% and 25% of Tier 1) so the reading is pinned in every build.
- Under A: no code change; one new value golden in `gen_stage_k_w2b.py`. Under B: `leverage.py` line 342 `any` becomes `all`, the spec Outputs sentence and KR-324 change, the same new golden expects no breach. No existing golden changes under either (no golden has a mixed group; lex_k-0007 has one counterparty).

## 2. KR-312, CCS buckets 1a and 1b

Plain idea: SA-CVA counterparty credit spread bucket 1 has two sub-sectors (sovereigns; local government and public administration) with different risk weights. Are they one aggregation bucket or two?

- Text (read): MAR50.63 Table 5 prints one bucket number 1 with two sector entries a) and b). Table 6 (cross-bucket correlations) has rows and columns 1 to 8, one row for bucket 1 (100%, 10%, 20%, 25%, 20%, 15%, 0%, 45%). Only Table 7 (risk weights) has separate columns `1 a)` (0.5% IG, 2.0% HY/NR) and `1 b)` (1.0%, 4.0%). No paragraph says 1a and 1b aggregate separately.
- Reading A, one bucket (implemented): 1a and 1b select the risk weight, sensitivities aggregate in bucket `1` with the within-bucket rho of MAR50.64. Reading B, two buckets: they aggregate separately and need a cross-bucket gamma, which Table 6 does not print (its only bucket-1 diagonal entry is 100%).
- Which the text supports: **A**. Reading B needs a correlation the text does not give. Evidence class: **read** (tables seen on bis.org 2026-11-20 and in the PDF 2026-11-19).
- Recommendation: **confirm A**.
- Under A: nothing changes. Under B: `cva.py` line 447 stops mapping to `1`, a gamma for (1a, 1b) has to be invented by a further ruling, sacva_k-0010 changes value and sacva_ke-0013 (same name and tenor in 1a and 1b is a duplicate) becomes a value case.

## 3. KR-315, equity vega 78% buckets

Plain idea: MAR50.73(3) gives equity vega a 78% risk weight in "large market capitalisation buckets" and 100% elsewhere, without listing the buckets.

- Text (read): MAR50.73(3): risk weights "set to 78% for large market capitalisation buckets and to 100% for the other buckets". MAR50.70 Table 11 prints size "Large" for buckets 1 to 8, "Small" for 9 and 10, "Not applicable" for 11 (other sector), "Large cap, advanced economies" for 12 (qualified indices) and "Other" for 13 (qualified indices).
- Reading A (implemented): 78% for 1 to 8 and 12. Reading B: 78% for 1 to 8 only (bucket 12 read as an index bucket, not a "large market capitalisation bucket").
- Which the text supports: **A**. Bucket 12 is the only index bucket whose size column says large cap; "large market capitalisation buckets" matches it as written. Evidence class: **read** for the table, **inferred** for applying the phrase to bucket 12 (the text does not list the buckets).
- Recommendation: **confirm A**.
- Under A: nothing changes. Under B: `_EQ_LARGE_CAP` in `cva.py` line 284 drops 12; sacva_k-0011 (EQ vega buckets 2, 10, 12) changes value and needs regeneration, and its blind credit must be re-checked.

## 4. KR-320, written credit derivative field: `fair_value` or `fv_reduction_in_tier1`

Plain idea: LEV30.31 lets a written credit derivative's effective notional be reduced by a fair value loss that has already reduced Tier 1. The question is whether the input is the signed fair value (operation computes `max(0, -fair_value)`) or the reduction amount itself.

- Text (read): LEV30.31: the effective notional "may be reduced by any negative change in fair value amount that has been incorporated into the calculation of Tier 1 capital with respect to the written credit derivative". The footnote example (web footnote 14, PDF 384): fair value +20 at one date and -10 at a later reporting date; the notional may be reduced by 10, "cannot be reduced by 30".
- Reading A, `fair_value` (implemented, spec formal statement and lev_k-0004/0005 rows): input the current signed fair value; reduction = `max(0, -fair_value)`. This builds in the footnote's cap and assumes the whole negative fair value is in Tier 1. Reading B, `fv_reduction_in_tier1` (KR-65 wording): the caller passes the amount incorporated in Tier 1 (>= 0).
- Which the text supports: the paragraph's condition ("incorporated into ... Tier 1") is closer to B; the footnote's cap is what A encodes. The two agree whenever the full negative fair value is in Tier 1, which is the footnote's case and the only case the goldens test. Since Tier 1 itself is a caller input (KR-65), A is the smaller interface and matches the printed example exactly. Evidence class: **read**.
- Recommendation: **confirm A (`fair_value`)**, and add one sentence to the spec Limits: "assumes the full negative fair value has been incorporated in Tier 1 (LEV30.31); a partial incorporation is not modelled". KR-65's field name stays superseded, as KR-320 says.
- Under A: one spec sentence; no code or golden change. Under B: rename the field in `leverage.py` (dataclass line 78, formula line 104 becomes `notional - reduction - purchased_offset`, a negative reduction is `E_DOMAIN`), the spec, `gen_stage_k_w2b.py`, lev_k-0004/0005 inputs (expected values 90 and 100 unchanged) and the lev_ke error goldens naming the field.

## 5. `bank_gsib` (KR-324 second part, default in KR-319)

Plain idea: the 15% limit depends on the reporting bank being a G-SIB, so the operation needs that fact. KR-66 names no field for it; the Python lane and, independently, the blind packet both added `bank_gsib`.

- Text (read): LEX20.1 and LEX40.1 condition the 15% on the bank being a G-SIB ("a G-SIB's exposure to another G-SIB"). The text says nothing about inputs, so the field name and its default are ours.
- Reading A (implemented): optional boolean `bank_gsib`, default false. Reading B: required boolean (absence is `E_SCHEMA`), so a G-SIB caller cannot get the 25% limit by leaving it out.
- Which the text supports: the text requires the fact (read); the default is a design choice (**inferred**). A default of false is the less prudent failure mode, but it matches the blind packet, lex_k-0007, and the convention that absent flags are false (`gsib`, `exempt`).
- Recommendation: **confirm A**, the name `bank_gsib`, and record in KR-66 that it supplies the bank's G-SIB status; state the default in the spec Inputs line next to `tier1`.
- Under A: spec Inputs line only. Under B: `leverage.py` line 282 loses its default and the reader reports a missing field as `E_SCHEMA`; every lex_k and lex_ke golden without the field gains `"bank_gsib": false`; one new two-error golden (missing `bank_gsib` plus a structural error) keeps HR-122 covered.
