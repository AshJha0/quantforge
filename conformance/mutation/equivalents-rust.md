# Rust mutation survivors: equivalent and accepted

R6-14 (review finding 5): one list per language, same columns as `equivalents-cpp.md`. At v0.8.0 no
Rust list existed; survivors of the weekly run (`mutation-stage.yml`, stage ALL, 40 seeded mutants per
module) are entered here by the language lane after the first full run. Under rule M a row with an empty
second-reviewer cell still counts as surviving, and `stage_report.py --gate` clears a module below target only
through a countersigned entry in `reasons.json`.

Classes: **Equivalent** (no input changes any output); **Accepted** (not equivalent, but only an exact
floating-point tie or an unreachable bound tells it apart; state which).

| File:line | Operator | Mutant | Class | Author reason | Second reviewer, date |
|---|---|---|---|---|---|
| rust/crates/quantforge-core/src/shortrate.rs:846 | `*` -> `+` / `/` | `v[0] = 2.0 * v[1] - v[2]` in `hw_fd` | Equivalent | `v[0]` is written but never read: the Thomas sweep reads `v[1..=nx-2]` only (the boundary rows are folded into `di[1]`, `up[1]`), both `at_knot` callers (`bermudan_swaption`, `callable_bond`) update each node from itself alone, and the result is the centre node `v[(nx-1)/2]`, `nx >= 5`. | Independent review agent, 2026-11-18: agree |
| rust/crates/quantforge-core/src/shortrate.rs:847 | `*` -> `+` / `/` | `v[nx-1] = 2.0 * v[nx-2] - v[nx-3]` in `hw_fd` | Equivalent | As line 846: `v[nx-1]` is never read by the sweep, the knot callbacks or the returned centre node. | Independent review agent, 2026-11-18: agree |
| rust/crates/quantforge-core/src/shortrate.rs:346 | `+=` -> `-=` | `mag` in `swaption_parts` | Accepted | `mag` only sets the stop tolerance `max(1e-15, 2 eps mag)`; mutated, the tolerance is 1e-15 and Newton or the bracket test stops one step later at the same root, so prices move only at the rounding floor of the sum (tolerance 1e-15 > 2 eps x 2 whenever all `c_i > 0`). | |
| rust/crates/quantforge-core/src/shortrate.rs:389 | `<` -> `<=` | `next < hi` in `swaption_parts` | Accepted | Differs only when the Newton step lands exactly on `hi` (an exact floating-point tie); the bracket update then makes the next step bisect and the same root is found. | |
