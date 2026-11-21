# Stage K fuzz2 lane: stop note

Branch `k-v1-fuzz2` (cut from main 11ba1b40). Worktree C:/Work/Claude/qf-wt/k-v1-fuzz2. No PR opened (lane rule).

## Done
1. Maven repository cache on every Java job. 14 setup-java jobs already had `cache: maven`; added it to
   release.yml (release-build-java) and tutorial.yml (tutorial-java); lowlat-book.yml has no setup-java, so it
   gets an `actions/cache` step on `~/.m2/repository` (same SHA pin as conformance.yml). Reason: three HTTP 429
   failures from Maven Central on 2026-11-20. YAML parses (read).
2. Fuzz findings of main run 44815591552 (seed 5, on c55a224e; fuzz-cpp and fuzz-rust green, fuzz-java and
   fuzz-python red). Both reproduced on Windows from the downloaded finding files:
   Java `rates.swaption.price_cube` node expiry 2^53 -> DateTimeException; Python `exec.sor.allocate`
   lit_samples row = 1 -> TypeError. Fixes:
   - month counts 1 to 1200 else E_INPUT (projection-and-fra.md, B19/D40/D59), checked before any date: cube
     node and trade expiries (Java, Python, Rust), swaption expiry, cap start, strip start (Python, Rust; C++ and
     Java already had them). Java `Calendars.plusMonthsInRange` (E_DATE_RANGE before LocalDate can overflow) in
     CapSwaption.start and Projection.plusMonths; Rust `schedule::add_months` saturates and clamps the year
     instead of wrapping through `as i32`.
   - SOR: lit_samples present, non-null, non-array -> E_SCHEMA (all four); a non-array row -> E_SCHEMA (Python,
     Java; C++ and Rust already); a non-array dark `tail` -> E_SCHEMA (Python); null tail / null lit_samples =
     absent (Java, Python, as C++ and Rust).
   - goldens: oracle/python/gen_stage_k_fuzz.py -> datasets/golden/stage_k/fuzzfix_k.json, 16 error cases
     (2 with two errors); outside_shares entry `fuzzfix_k: None`; generated pages regenerated.
   - separate commit 47c3fc31 (droppable): tools/validation/model_reports.py no longer lets an error-only later
     stage hide an operation's value-case share; moves several per-model figures.
3. docs/known-issues.md K9-1a text updated to the true state (still open). CHANGELOG entry.

## Evidence (measured, Windows laptop, not the acceptance machine)
- Python and Java conformance runner 256/256 on fuzzfix_k, fuzzfix_j, sor_h, ratesvol_e, capswaption_d,
  rulings*_d, acls_h, e1_h2, e1_h4, sorx_h.
- Targeted sweep (scratch script, not committed): 2^53, -2^53, 1 and "x" into first/last slots of up to 3
  golden cases per operation: Java 0 internal faults in 9,162 inputs after the fix.
- ruff, ruff format, mypy clean; repo-gate tools run locally pass (hygiene, job names, case_figures, results,
  model_reports, share figures, known issues, quality_gate, gen_cli_cases, build_references, test_preregs).

## NOT BUILT, NOT RUN
- C++ (cpp26/src/core/dark_sor.cpp) and Rust (sor.rs, rates_vol.rs, caps.rs, schedule.rs): written by reading;
  no WSL this session. `cargo fmt --check` passes on Windows. Their answers for fuzzfix_k were derived by reading.

## How to resume
Read C:/Work/Claude/qf-wt/_h4ci/LANE_RULES_K.md. Build and run C++ and Rust (golden replay, unit tests, clippy
-Wshadow) in WSL; run the probe tool on datasets/golden/stage_k/fuzzfix_k.json for all four builds.
