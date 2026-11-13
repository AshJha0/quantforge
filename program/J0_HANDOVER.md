# J-0 hand-over: Rust mutation gap (2026-11-13)

Branch `stage-j-j0` (worktree C:/Work/Claude/qf-wt/j0), not pushed. Head: 57308ac + this note.

## Why the 08:05 full run failed
`quantforge-core` does `include_str!("../../../../specifications/01-core/data/sobol-joe-kuo-d6-64.json")`.
cargo-mutants copies only the `rust/` workspace to `/tmp/cargo-mutants-rust-XXX.tmp/`, so the unmutated
build cannot find the file. Fix used: symlink `/tmp/specifications` to the archive's `specifications/`
(the include then resolves from the temp copy), which keeps copy mode and allows `-j 3`.
`--in-place` also works but is serial and far too slow (1007 mutants in hedge_solvers.rs).

## Runner
- Script: C:/Work/Claude/qf-wt/j0-run/j0mut.sh (copied to ~/j0mut.sh), launched by
  C:/Work/Claude/qf-wt/j0-run/launch.cmd `<ref> <tag>` via WMI. Modules run one at a time:
  var, hedge, hedge_solvers. Flags: `cargo mutants -j 3 --timeout 300 -p quantforge-core -f "**/<m>.rs"`.
- RUNNING (launched ~16:40 UTC) on 57308ac, tag h1: log `~/j0mut-h1.log`, results
  `~/j0-h1-<module>/mutants.out/{caught,missed,unviable,timeout}.txt`.
- Rate measured: ~1.3 mutants/min (unit suite ~37 s, many mutants 2-3 min). hedge_solvers needs ~12 h.

## Per-module results
| module | caught | missed | unviable | timeout | kill % |
|---|---|---|---|---|---|
| var.rs | pending (h1) | | | | |
| hedge.rs | pending (h1) | | | | |
| hedge_solvers.rs | pending; aborted baseline sample: 11 caught / 1 missed of 12 | | | | |

First miss seen: hedge_solvers.rs:92 `replace || with && in Costs::any`.

## Done
- tests/var_mutants.rs: 7 value tests for every public fn in var.rs, reference values from an
  independent Python computation of the textbook formulas (pass in WSL).

## Left
1. Read h1 missed.txt per module; add value tests for misses (hedge_solvers: Costs::any first).
2. Note equivalent mutants (none classified yet).
3. Re-run until each module >= 80 %; only then add CHANGELOG Unreleased/0.9.0 line and the v0.8.1
   known-issue note that the Rust mutation gap is closed.
4. CI: mutation-stage.yml uses golden_mutants.py (copies whole repo, so unaffected).
