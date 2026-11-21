# Stage K fuzz2 lane: stop note

Branch `k-v1-fuzz2` (cut from main 11ba1b40). Worktree C:/Work/Claude/qf-wt/k-v1-fuzz2.

## Done
1. Maven repository cache on every Java job. 14 setup-java jobs already had `cache: maven`; added it to
   release.yml (release-build-java) and tutorial.yml (tutorial-java); lowlat-book.yml has no setup-java, so it
   gets an `actions/cache` step on `~/.m2/repository` (same SHA pin as conformance.yml). Reason: three HTTP 429
   failures from Maven Central on 2026-11-20. YAML parses (read).

2. (in progress) Fuzz findings of main run 44815591552 (seed 5), both reproduced on Windows from the downloaded
   reports: Java `rates.swaption.price_cube` node expiry 2^53 -> DateTimeException; Python `exec.sor.allocate`
   lit_samples row = 1 -> TypeError. Fixes:
   - months 1 to 1200 else E_INPUT (projection-and-fra.md, B19/D40/D59) for cube node and trade expiries
     (Java, Python, Rust), swaption expiry, cap start, strip start (Python, Rust; C++ and Java already had it);
     Java `Calendars.plusMonthsInRange` (E_DATE_RANGE before LocalDate can overflow) in CapSwaption.start and
     Projection.plusMonths; Rust `schedule::add_months` saturates and clamps the year instead of wrapping.
   - SOR: lit_samples present, non-null, non-array -> E_SCHEMA (all four); a non-array row -> E_SCHEMA (Python,
     Java); a non-array dark `tail` -> E_SCHEMA (Python); null tail / null lit_samples = absent (Java, Python).
   - goldens: oracle/python/gen_stage_k_fuzz.py -> datasets/golden/stage_k/fuzzfix_k.json, 16 cases (2 two-error).
   - measured: Python and Java runner pass 256/256 on fuzzfix_k, fuzzfix_j, sor_h, ratesvol_e, capswaption_d,
     rulings*_d, acls_h, e1_h2, e1_h4, sorx_h.
   - C++ (dark_sor.cpp) and Rust (sor.rs, rates_vol.rs, caps.rs, schedule.rs): NOT BUILT, NOT RUN (no WSL this
     session); `cargo fmt --check` passes on Windows.

## Not done
- outside_shares entry for fuzzfix_k, full Python and Java suites, CHANGELOG / known-issues text.
3. docs/known-issues.md row K9-1a text.

## How to resume
Read C:/Work/Claude/qf-wt/_h4ci/LANE_RULES_K.md, then continue at item 2.
