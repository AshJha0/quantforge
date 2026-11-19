# Stage K round 1, second pull request: integration log (branch `k-r2`)

Branch `k-r2` (worktree `C:/Work/Claude/qf-wt/k-r2`), cut from main `864c6e7d` (PR #58 merged). Target: v0.10.1 after this branch and a follow-up audit. Not released; no PR, no merge to main, no tag from this lane.

Integration lane: Claude Opus 5.5. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18).

## How to resume

1. `cd /c/Work/Claude/qf-wt/k-r2 && git fetch origin && git status && git log --oneline -15`
2. Read "State" below; continue at the first item not marked done.
3. Locks: Maven `mkdir /c/Work/Claude/qf-wt/_h4ci/mvn.lock.d` (wait while it exists; `rmdir` when done, also on failure). WSL jobs under `flock ~/qf-wsl.lock`. Check `/c/Work/Claude/qf-wt/_h4ci/QUIET` before anything heavy.
4. Push: `git push -u origin k-r2` (retry on network drops).

## State

| Step | What | Status | Commit |
|---|---|---|---|
| 1 | merge k-margin (fb65a4ad) | to do | |
| 2 | merge k-audit-a (e1905bea) | to do | |
| 3 | merge k-audit-jobs (552af98e) | to do | |
| 4 | merge k-audit-shares (ab7e8a31), renumber KR-210..212 to KR-250..252 | to do | |
| 5 | outside_shares: lim_k, dropped blind credit, KR-250 records | to do | |
| 6 | E1 gate: NaN goldens for backtest.zone and .desk | to do | |
| 7 | risk.backtest.traffic_light binomial (KR-237) in four builds | to do | |
| 8 | mutation modules for saccr, stage_k, bermudan_k8; stage F kill tests | to do | |
| 9 | generator drift (stage G E1, gen_cli_cases.py) | to do | |
| 10 | docs to the merged state | to do | |
| 11 | verification | to do | |

## Log
