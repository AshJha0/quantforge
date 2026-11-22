# Blind derivation task: AAD gradients of the valuation adjustments

You are the blind deriver. Work only inside this folder. Do not read, search or open anything outside it (no
repository, no other folder, no web). Use Python with the standard library, mpmath and numpy only.

## Files

- `spec.md`: the definition of the operation `xva.sens.aad` on `xva.adjustments.value` (formulas, gradient keys,
  units, kinks, tolerance).
- `rulings.md`: rulings KR-262 to KR-265 (keys and their order, bucket hazards, the kink convention, `wrt`).
- `inputs.json`: 13 cases, `{case_id: {"operation": ..., "inputs": {...}, optional "wrt": [...]}}`. Numbers are
  binary64.
- `template.json`: for each case the exact output shape with every leaf `null`.
- `MANIFEST.sha256`: SHA-256 of each file; verify it first and say whether it matched.

## What to produce

1. For every case compute every output in `template.json`: `cva`, `dva`, `fca`, `fba`, `fva` (and `mva`, `kva`
   where present) and every `gradient` entry, from `spec.md` and `rulings.md` only. Use your own independent
   method (for example a closed-form derivative, or a high-precision finite difference in mpmath at 50 digits or
   more), then round once to binary64. Each output must be within `1e-12 + 1e-10 max(|a|, |e|)` of the exact value.
2. Write `answers.json` in this folder: exactly the shape of `template.json` (same case ids, same keys, same array
   lengths) with every `null` replaced by a JSON number (17 significant digits, plain or exponent form). No extra
   keys, no strings for numbers.
3. Write `derive.py` (the script that produced `answers.json`) and `notes.md` (method, precision, the MANIFEST
   result, and every ambiguity you met with how you resolved it) in this folder.
4. Report the SHA-256 of `answers.json` when you hand back. Do not change `answers.json` after that.
