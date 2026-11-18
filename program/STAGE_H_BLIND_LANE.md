# Stage H blind golden lane (wave 2): plan

Written 2026-11-18 by the stage H coordinator (spec lane). No goldens generated yet. Rule: DR-H2 (a golden counts as outside-checked by re-derivation only when a second lane that never saw the first lane's numbers computes it) and HR-31 (lit engine, dark pool and router value cases are outside-checked this way). Model of the wave-1 run: `institutional-quant-engine-plan/STAGE_H_BLIND_REDERIVATION.md` (27/27 match).

## Scope
- `ob_h-*` order book rebuild (`specifications/09-microstructure/order-book.md`), synthetic message lists only (recorded rows are never goldens, HR-41).
- `lit_h-*` matching engine event traces (`specifications/10-execution/lit-matching.md`), one per order type plus FIFO and conservation cases.
- Later in wave 2, the same process for `dark_h-*` and `sor_h-*` value cases (HR-31).

## Lanes
1. **Spec lane** writes each case's inputs and its own expected output, and commits the expected values (or stores them hashed) before the blind lane starts. It does not share them.
2. **Blind lane**: a separate session (different model where available, never the spec lane's context), working outside the repo in its own scratch folder. It is given only:
   - the normative spec text with the Expected and Derivation columns, worked examples and any numeric outputs removed by a script (the wave-1 awk extraction that prints only Case and Input columns, extended to these tables), plus the rulings files;
   - the cited venue documents ([KR-BOOK], [KR-CRC], [KR-ADD]) for rule meaning.
   It is not given: the expected columns, any repo goldens, oracle output, implementations, or the spec lane's scratch files. Leaks found in prose (an output figure in a preamble, as with ac_h-0001's standard deviation in wave 1) are listed per case and that case is counted as not blind.
3. The blind lane writes its own small reference (plain Python, no repo imports), runs it on the inputs, and freezes `blind_results.json` with its file hash before any comparison.
4. **Comparison** by a script: event traces compared byte for byte after canonical JSON (sorted keys, decimal strings, HR-12, HR-29); book states compared level by level. No formula or code changes after freezing; a mismatch is investigated, and if the spec lane was wrong the golden is fixed with the reason; if the blind lane was wrong, its error is recorded and it is not rerun to agree.

## Recording
- `program/STAGE_H_BLIND_WAVE2.md`: date, lane, model, inputs given (file list and hashes), leaks, per-case MATCH / MISMATCH / NOT BLIND, and the resolution of each mismatch.
- Each golden table row gets "Blind re-derived (DR-H2)" or the reason it is not; the outside-check share per item is recomputed against the 60% rule (plan 15).
- Scripts and frozen results are copied to `stage_h_blind/` next to the wave-1 ones.
