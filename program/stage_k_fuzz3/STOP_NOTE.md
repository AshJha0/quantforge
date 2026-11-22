# Stage K fuzz3 lane: stop note

Branch `k-v1-fuzz3` (cut from `k-v1` 1e16a034). Worktree C:/Work/Claude/qf-wt/k-v1-fuzz3. No PR opened, nothing merged (lane rule).

## Done
1. Finding of Fuzz run 44937631714 (seed 8, on `k-v1` 5e4facc9; Java, C++ and Rust green, Python red). Reproduced on
   Windows from the downloaded finding file: `paper.book.apply_fill` with `fills[0].side = [0]` (and `fee = "é"`) ->
   exit 70, `TypeError: unhashable list` in the side lookup. After the fix: `E_SCHEMA` at `fills/0/side`.
2. Same fault class in the sibling `paper.*` handlers (read, then pinned by goldens): Python also crashed on an array
   `side` in `paper.book.end_of_day` and `paper.pretrade.check`, and on an array order `symbol` in `paper.session.run`
   (symbol set). C++, Java and Rust said `E_INPUT` for a side of any non-string type; Java said `E_INPUT` for a
   non-string `order_id`.
3. Fix, all four builds (`paper.py`, `paper_fills.py`, `paper.cpp`, `paper.rs`, `Paper.java`):
   - a present `side` or `type` that is not a JSON string is `E_SCHEMA` (cli-contract.md error table: mistyped);
     an unlisted string stays `E_INPUT` (paper-trading.md, Errors; `rule_h-0040`);
   - `paper.pretrade.check`: `order/side` and `order/type` strings in the schema phase (before `mode`);
   - `paper.session.run`: `order_id`, `symbol`, `side`, `type` and a non-null `venue` strings, else `E_SCHEMA`
     (a null venue stays `E_INPUT`, as before in all four);
   - fills of `paper.book.apply_fill` / `paper.book.end_of_day`: schema of every fill before any other check of the
     case, then over the whole list decimals (malformed, `E_LIMIT`), unknown sides (`E_INPUT`), non-positive
     quantity or price (`E_DOMAIN`), per KR-230 / HR-122. Before, fills were checked one by one.
4. Goldens `datasets/golden/stage_k/fuzzfix_k2.json`, 19 error cases (6 with two errors, steps in brackets), from
   `oracle/python/gen_stage_k_fuzz3.py` (seeds from `pt_h`); reviewer field per lane rules; `outside_shares` entry
   `fuzzfix_k2: None`; generated pages regenerated (case figures, OUTSIDE_SHARES, results, model report mh-11).
5. R6_HANDOVER TOTALS 16,629 (value 8,143, error 5,932, invariance 2,554); K9-1a text; CHANGELOG entry.

## Evidence (measured, local laptop, not the acceptance machine)
- Conformance, full tree, 16,629 of 16,629 pass in each of Python (Windows), Java (Windows), C++ (WSL, Release,
  -Werror gcc) and Rust (WSL, release); `fuzzfix_k2` 19/19 in each.
- C++ ASan/UBSan build: `fuzzfix_k2`, `pt_h`, `rule_h`, `e1_hpt` 98/98 and the finding input -> `E_SCHEMA`, no
  sanitizer report. Its full ctest did NOT finish inside the 10-minute WSL cap (timeout; not a failure seen).
- C++ plain ctest 6/6; Rust fmt, clippy -D warnings, `cargo test --workspace` pass.
- Java `mvn -B -Pcoverage verify` pass; per-file gate 8 modules at 85%, 0 below.
- Python full suite 4,399 passed, 2 skipped; ruff, ruff format, mypy clean; `pytest tools` 121 passed, 1 skipped;
  check_case_total, case_figures, model_reports, results_page, known_issues, share figures, gen_cli_cases --check,
  build_references, test_preregs pass.

## Open
- clang -Wshadow (CI only) not run locally.
- Not changed, consistent in all four builds but against the contract table: a malformed decimal string (e.g. "é")
  in a paper input is `E_PARSE`, which the contract reserves for invalid JSON (`E_SCHEMA` would fit "malformed").
  Needs a ruling; no golden pins it.
- Wider error order of `paper.book.end_of_day` (a fill `E_DOMAIN` before a missing `prev_close` `E_SCHEMA`) and of
  `paper.session.run` (steps checked in turn) not changed.
- K9-1a stays open until a fuzz run on main is green.
