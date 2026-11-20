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
| 1 | merge k-margin (fb65a4ad) | merged; Python conformance 16,129/16,129 and targeted xva tests pass | 9ecd3feb |
| 2 | merge k-audit-a (8106ab22, incl. K-5a v2 blind commits) | merged; Python conformance + targeted tests were running at shutdown (rerun: `/c/Work/Claude/qf-wt/_h4ci/kr2/pyconf.sh m2 <tests>`) | 25ca6c61 |
| 3 | merge k-audit-jobs (552af98e) | merged; KR-209 owner-confirmed; daily-job tests 117 passed | 03772bf6, bcd6835d |
| 4 | merge k-audit-shares (ab7e8a31), renumber KR-210..212 to KR-250..252 | merged on lane k-r2-e1; KR-210..212 renumbered KR-250..252 | 0c225b83 |
| 5 | outside_shares: lim_k, dropped blind credit, KR-250 records | lane k-r2-e1; then K-4c blind lane k-r2-blind 14/14 MATCH, 13 counted; stage K 91 of 113 | 0c225b83, 9c8b8272 |
| 6 | E1 gate: NaN goldens for backtest.zone and .desk | lane k-r2-e1; check_e1_coverage 0 problems | 0c225b83 |
| 7 | risk.backtest.traffic_light binomial (KR-237) in four builds | merged: lane k-r2-tl (KR-253, with the q = c boundary amendment) | 86e3d84d |
| 8 | mutation modules for saccr, stage_k, bermudan_k8; stage F kill tests | lane k-r2-mut: 40/40, 39/40 + 1 Equivalent, 40/40 on CI sample; four stage F survivors killed | 91588373 |
| 9 | generator drift (stage G E1, gen_cli_cases.py) | lane k-r2-gen2: stage G E1 and cli_cases.inc regenerated, --check gates | 49857faa |
| 10 | docs to the merged state | merged: lanes k-r2-docs, k-r2-kf3 (KF-3), k-r2-kf2 (KF-13..16) | b6cdcf8d, 918d7609, ae60e2b9 |
| 11 | verification | early chains at e0f52a65 green except stale case total; follow-up audit KF-1..12 and its check done; chains at 617f3874: Java, Python, repo gates and docs green; status ladder fixed in ef411039; final check before tag KF-17..23 answered on lane k-r2-gate | 91c99115, 617f3874, ef411039 |

## Log

### 2026-11-20 (coordinator, Claude Opus 5.5, owner-delegated decisions)

- Merge 2 interaction fixed (490a9654: sbim_alias_k-0021 note). Lanes run in parallel off k-r2 and merged as listed in State. Follow-up different-model audit (Fable 5.2): STAGE_K_R1_FOLLOWUP_AUDIT.md in the plan folder, 0 Critical, 4 Major, 8 Minor; its check of the responses: 8 of 12 closed, KF-2 open until k-r2-tl merges, new KF-13 (Major) to KF-16. H-9 test sample-time defect fixed (e0f52a65).

### WIP at shutdown (2026-11-20 ~00:15 UTC)

- Committed in the WIP commit, not yet verified: K-5a spec (`specifications/06-risk/intraday-risk-bounds.md`): KR-240 tolerance stated in "Golden value cases" (chosen over fixing evaluation order: expected values are 50-digit, so a fixed order would still miss plain 1e-9 on idr_k-0012); v2 blind result 9 of 11 recorded; KA-A6 marked closed by KR-234; new open line for the two cancelling-book estimates. After a spec edit rerun build_references, build_checklists --check, gen_name_map, case_figures --write, outside_shares, test_preregs.
- Step 7 started: `python/tests/test_traffic_light_binomial.py` written; on the unfixed lgamma code all 6 tests FAIL (measured, 110 s), as intended. Next: switch `var_risk.traffic_light` (Python), `PortfolioRisk.trafficLight` (Java), `backtest_traffic_light` in `cpp26/src/core/var_frtb.cpp`, `var::traffic_light` in `rust/crates/quantforge-core/src/var.rs` to the KR-237 `binomial_cdf(n, x, 1 - c)` of each build's frtb_backtest; write ruling KR-253 (cited in the test docstring, not yet written); large-n goldens; check no existing tlk/traffic golden changes beyond tolerance.
- Step 9 findings (scratch worktree `C:/Work/Claude/qf-wt/k-r2-gen` at 864c6e7d, detached; delete with `git worktree remove`): both generators are deterministic (two runs, different PYTHONHASHSEED, identical bytes). `gen_stage_f_e1.py G`: main's `stage_g_e1` is stale (generated before stage G wave 4c 2d3d62a5 added xva.exposure.portfolio_hw and R6-10 80f9ad12 added output_classes): +79 cases, 32 cases gain output_classes, 162 xva ids renumber. `gen_cli_cases.py`: stale since 9e16e384 (2026-11-12): +345/-11 lines. No gate checks either. Stage F mode of gen_stage_f_e1.py is a patchwork by design (later stages took selected lines; a full rerun adds 115 operations and changes 19): document, do not regenerate. To do: regenerate both on k-r2, add `--check` to both generators, wire into repo-gates.
- Remaining after that: merges 3 (k-audit-jobs 552af98e) and 4 (k-audit-shares ab7e8a31 with KR-210..212 -> KR-250..252), then steps 5, 6, 8, 10, 11. outside_shares --check is red (lim_k unmapped; step 5). Helpers: `/c/Work/Claude/qf-wt/_h4ci/kr2/gates.sh`, `headline.py`, `pyconf.sh`. Coordinator asks: known-issues row "K-5a: two cancelling-book estimates are not reproduced to 1e-9 relative by an independent implementation (order-of-operations sensitivity); bound unaffected"; outside_shares K-5a = 9 of 11 counted (idr_k-0012/0013 not counted).
- Merge 2 checks (finished after the WIP commit): Python conformance 16,166 of 16,166 pass; targeted tests 1 FAILED (run with -x, so later tests not run): `test_stage_k_error_order.py::test_two_error_golden_follows_the_general_order[sbim_alias_k-0021]`: the k-audit-a registry test (KR-230) wants a two-error golden's note to name both steps in brackets, and the k-margin alias golden sbim_alias_k-0021 does not. Interaction of merges 1 and 2: fix the golden's note wording (via the margin generator `tools/gen_sbim_placeholder.py` or the alias golden's generator), then rerun the targeted tests without -x.
