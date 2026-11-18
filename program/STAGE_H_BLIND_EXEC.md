# Stage H blind re-derivation: execution packet (H-14 adaptive algos, H-17 TCA)

Date 2026-11-18. Method DR-H2: the second lane got only the inputs-only packet built by `program/stage_h_blind_w2/wave2_make_packet.sh <checkout> <dir> exec` (stripped `adaptive-algos`, `tca-pretrade`, `tca`, `schedules` specs; rulings w1, h21, w2-exec; `alg_h.inputs.json`, `tcx_h.inputs.json`; MANIFEST.sha256). The per-case leak list (`coordinator/LEAKS.tsv`, not given to the blind lane) showed 98 expected values clean, 14 error codes, 0 leaks.

Frozen blind output: `stage_h_blind/exec/blind_results.json`, SHA-256 `f914374b25a0d90a7c3f9e9efa82ff34372f1a1bb50102c21835fc288827c168` (verified before comparing; copied unedited with `blind_ref.py`, `notes.md`, `blind_results.sha256`). No rerun.

Comparison: `python -I program/stage_h_blind_w2/wave2_compare.py . stage_h_blind/exec/blind_results.json exec` (simple_analytic, 1e-12 abs + 1e-10 rel).

| Suite | Cases | MATCH | SHAPE-ONLY | VALUE MISMATCH |
|---|---|---|---|---|
| alg_h | 25 | 14 | 11 (error wrapper only) | 0 |
| tcx_h | 11 | 6 | 5 (error wrapper only) | 0 |

No value mismatch, so nobody was wrong on a value. alg_h-0004 differs by float noise of about 2e-16 relative (sinh in doubles), which is inside the tolerance. All SHAPE-ONLY rows are the blind lane writing `{"error": CODE}` where the conformance format has `{"status": "error", "error_code": CODE}`.

## Post-blind shape changes (no value changed)
1. Output field names are fixed as one name each in both specs (new section "Post-blind shape changes"). The blind lane's choices are adopted: `cash_imbalance` of length N (one entry per bucket), attribution echoes `fees`, and close returns `auction_quantity`. The spec goldens already used these names.
2. The error wrapper stays the repo conformance format. The blind `{"error": CODE}` maps to it one to one.

## Error precedence (decided 2026-11-18: HR-66 in stage-h-rulings-w2-exec.md; no expected value changed)
The blind lane put `E_INPUT` before `E_DOMAIN` (tcx_h-0005: X = 0). Micro-lane HR-75 says `E_DOMAIN` before `E_INPUT`. Repo precedent: B11 (length checks before domain), C15 and C17 (structural `E_INPUT` first, "before every `E_DOMAIN`"), D53 (duplicates before `divisor <= 0`), R1-4 (first check), and HR-58 (`E_SCHEMA` before `E_LIMIT`). Proposed repo-wide order: `E_SCHEMA`, then structural `E_INPUT` (missing or empty lists, lengths, ordering, enum or mode consistency, cross-field consistency), then `E_DOMAIN` (single values out of range), then `E_LIMIT`. Under this order HR-75 would be amended. No exec golden has two errors at once, so alg_h and tcx_h do not change under either order.

## Goldens moved to the oracle
`oracle/python/gen_stage_h_w2_exec.py` now writes `datasets/golden/stage_h/alg_h.json` and `tcx_h.json`. The hand values live in the generator and are re-checked there with exact fractions. Two runs give byte-identical files (sha256 checked). The only change from the hand-written files is the `generator` field.
