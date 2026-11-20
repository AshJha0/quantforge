# Stage K: tlk_k blind packet, version 2 (risk.backtest.traffic_light after KR-253)

Written 2026-11-20 by lane k-r2-tlblind (Claude Opus 5.5, branch `k-r2-tlblind`). The packet builder is not the blind lane. Pattern: `program/STAGE_K_BLIND_TRIG_V2.md` and `program/STAGE_K_BLIND_K5A_V2.md` (DR-H2). Finding answered: KF-19 (`STAGE_K_R1_FOLLOWUP_AUDIT.md`, fix (a)).

## Why

Plain idea: KR-253 added nine value goldens, `tlk_k-0012` to `-0020`, checked only by the project's own exact rationals, mpmath and SciPy, which do not count (KR-250, D6). `tools/outside_shares.py` therefore counts `tlk_k` at 11 of 20 (55.0%), under the 60% per-item floor (evidence class: read, `oracle/OUTSIDE_SHARES.md` on k-r2 ef411039). A second model, given only the stripped rules and the case inputs, computes the nine cases again.

## What was built (evidence class: measured, 2026-11-20, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/tlk_v2_make_packet.py` | writes the packet from the spec section, KR-237 and KR-253 and the case inputs; never reads the expected file | builds the packet |
| `program/stage_h_blind_w2/tlk_v2_expected.json` | expected outputs and each case's `tolerance_limit`, copied from the goldens | hidden |
| `program/stage_h_blind_w2/tlk_v2_compare.py` | compare, with `--self-test` | hidden |

Packet: `C:/Work/Claude/qf-blind/tlk_k_v2_packet/` (outside every worktree; not committed). **MANIFEST.sha256 file hash: `fc14469e44177b08f02936d649c8b64765fd4f8f3e8047821feebffdc5cbce75`.**

What was stripped: from the spec section, the sentence giving the n = 1 answer ("`c` itself", the 0.95 YELLOW example), the worked example (prints the tlk_k-0020 value to 7 digits) and the accuracy paragraph naming the goldens; from KR-237, the accuracy figures and the golden sentences; from KR-253, its status line, "`c` exactly at `n = 1`", the first-version reason (prints a value next to 0.95), the double-double accuracy, and the golden lists.

- Leak check (inline, run by the builder): every expected `cumulative_probability` printed to 3, 4, 6, 8, 10, 12 and 17 significant digits, searched in every packet file: no hit except 0.9999 (tlk_k-0018), which is the RED threshold in the rule text; that case is not counted (below). Case ids appear only in the inputs and template files.
- Compare self-test on fabricated data: PASS (`python -I program/stage_h_blind_w2/tlk_v2_compare.py . --self-test`).

## Fixed now, before any blind result exists

This file, the compare script and the expected file are committed and pushed before the deriver is started (KF-6, KF-23); the results commit comes after, in a separate commit.

- Tolerances, the goldens' own, with the runner's rule (`|a - e| <= abs + rel * max(|a|, |e|)`): `cumulative_probability` relative 1e-12, absolute 1e-15 (0012 to 0015, 0019, 0020) and exact (0016 to 0018); `zone` exact string; `plus_factor` exact (number or null).
- A case counts only if every output matches.
- tlk_k-0016, -0017, -0018 (n = 1, x = 0): with `q = c` exact, `P(X <= 0) = c` is the input itself, so the rules text gives the answer (as btk_k-0017 in `program/STAGE_K_BLIND_BTK.md`). Compared, **not counted** (`R_NOCREDIT`) whatever the result.
- **Eligible: 6 of 9.** tlk_k after this lane: 11 + counted, of 20. Needed for 60%: 12 of 20, so at least 1 match.
- KF-22 note: tlk_k-0019 and -0020 repeat the inputs of tlk_k-0006 and -0001 (the q meant differs: binary64 c here, decimal there). They are counted if they match, under the rule as written; this is stated, not hidden.
- The deriver must be a model other than Claude Opus 5.5. Hash first, commit the frozen results, then one compare run; a mismatch is recorded, never tuned.

## Results

Run 2026-11-20, the first and only compare run (evidence class: measured; hashes and output are in the repository).

- Time gap: packet, compare and tolerances committed and pushed in 51180fb2 (09:20:24 UTC); the deriver was started after the push; frozen results committed in 370f24d7 (09:26:41 UTC); the compare ran after that commit.
- Deriver: a separate subagent on Claude Sonnet (not Opus 5.5), given only the packet folder and its own folder `C:/Work/Claude/qf-blind/tlk_k_v2/`, told not to read the repository. Value source: exact integer and rational arithmetic (Python `fractions`, `q = Fraction(c)`), rounded once to binary64; it did not implement the KR-237 floating-point algorithm, so this is a genuinely independent computation of the value, not a second copy of our algorithm. Its own statements, not independently logged: it read nothing outside the two folders; the manifest matched on all 5 files.
- Frozen results: `stage_k_blind/tlk_v2/` (`blind_results.json`, `blind_ref.py`, `notes.md`). SHA-256 of `blind_results.json` as handed back: `8944efa5fc95df26aa73f0f5ba0c0df192d948bb8fa20692871ca8acf1a10fcc`, recomputed by the builder, equal (git stores it with LF line ends).
- Compare: `python -I program/stage_h_blind_w2/tlk_v2_compare.py . stage_k_blind/tlk_v2/blind_results.json`; output `stage_k_blind/tlk_v2/compare_output.txt`.

| Item | Cases | MATCH | MISMATCH | Eligible | Counted |
|---|---:|---:|---:|---:|---:|
| `tlk_k` 0012 to 0020 (KR-253) | 9 | 9 | 0 | 6 | 6 |

Every output of every case matches. tlk_k-0016 to -0018 match but are not counted, as fixed above. Reading the deriver recorded (`notes.md`): at n = 1 the zone edge compares the binary64 value against the literals 0.95 and 0.9999 with strict "below"; not ruled a gap.

Credit: `oracle/python/gen_stage_k_w1b.py` adds `BLIND_TLK` to the six counted cases and a "not blind" note to 0016 to 0018; KF-22: the tag `outside_checked` is now set only on counted cases (0016 to 0018 do not carry it). `python tools/outside_shares.py --check`: exit 0; `tlk_k` **17 of 20, 85.0%, met** (was 11 of 20, 55.0%); stage K 97 of 122 (79.5%).

What this does not show: the six counted cases include tlk_k-0019 and -0020, whose inputs repeat earlier rows (KF-22), so they add little new coverage. The per-item floor is still not enforced by a gate (rest of KF-19, outside this lane).

## Corrections (audit KF-25, KF-26; lane k-r2-gate, 2026-11-20)

- **Two hashes (KF-25).** The deriver handed back `blind_results.json` with CRLF line ends (1,062 bytes): SHA-256 `8944efa5fc95df26aa73f0f5ba0c0df192d948bb8fa20692871ca8acf1a10fcc`, the hash in `blind_results.sha256` and above. `.gitattributes` stores the file with LF line ends (1,014 bytes): SHA-256 `7231ad7581bb4de06bfb0c36cbc12272e9d05265aa7448c4f02bbd7840ef5fef`, so `sha256sum -c` in a checkout fails. Same content; converting the committed file back to CRLF gives the recorded hash (measured, as the trig lane did in `program/STAGE_K_BLIND_TRIG_V2.md`).
- **What the match shows (KF-26).** The deriver is the same model family as the author (Claude Sonnet against Claude Opus 5.5) and was told the method class: exact `fractions.Fraction` at the binary64 `c`, rounded once, the method that produced the expected values. The match is a second, separately written program for a stated formula: it shows the rule is unambiguous and the arithmetic right, not that the rule reads the Basel source correctly. For 0019 and 0020 the zone and plus factor are printed in the rule text and the inputs repeat 0006 and 0001 (KF-22), so only the probability is derived; new coverage is four cases, 0012 to 0015. None of this changes the KR-250 count as the rule is written.
- `tlk_k-0021` (audit KF-21, lane k-r2-gate) was added after this packet; it was not in the packet and is not counted.
