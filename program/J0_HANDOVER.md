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

## Per-module results (2026-11-13 ~20:45 UTC)
| module | caught | missed | kill % | source |
|---|---|---|---|---|
| hedge.rs | 86 | 18 (all equivalent, path-only) | 82.7 | h1 full run (76/28) + verify run on 21e7d4d+tests: 11 of the 28 killed, `polish -> None` newly missed (flaky in h1) |
| var.rs | h2 partial 195 | 11 | >=94 | h2 (57308ac) still running; verify run killed 73 and 151; later tests target 127, 167 `==`, 229/230/233 (not yet re-verified); 4 equivalent |
| hedge_solvers.rs | pending | | | h2 starts after var; ETA 07:00-11:00 UTC 2026-11-14 |

Equivalent mutants: program/J0_EQUIVALENT_MUTANTS.md (var 4, hedge 18).

## Verify tooling (WSL, does not disturb h2)
- `git archive -o C:/Work/Claude/qf-wt/j0-run/v.tar HEAD`, put regex in `j0-run/re-<module>.txt`,
  launch `cmd /c C:\Work\Claude\qf-wt\j0-runlaunch.cmd <module>` via WMI (Invoke-CimMethod Win32_Process Create).
  Runs `vmut.sh`: -j 2, TMPDIR=~/j0tmp-v, log ~/j0v-<module>.log, results ~/j0-v-<module>/mutants.out/.
- `vcheck.sh` (copy to ~/vcheck.sh): fmt --check, clippy -D warnings, cargo test --release on v.tar.
  All green at this head except `bermudan_aad::g9_ladder_cost_ratio_at_most_five`, a timing ratio
  that fails only under load from the h2 run (passed earlier the same evening).

## Left
1. var: when h2 var finishes, run a verify run on its remaining missed lines (re-var.txt) at this head.
2. hedge_solvers: take ~/j0-h2-hedge_solvers/mutants.out/missed.txt (Costs::any `||`->`&&` at line 92 first),
   add value tests, verify, document equivalents.
3. When all three >= 80 %: change the CHANGELOG Unreleased line from "in progress" to final numbers and add
   the v0.8.1 known-issue note that the Rust mutation gap closed in v0.9.0. Not done yet.
