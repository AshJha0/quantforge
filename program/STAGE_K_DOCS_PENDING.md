# Stage K round 1: docs blocks that run after integration

Docs lane, branch `k-docs`, second pass, 2026-11-19. Everything listed here describes an operation, tool or file that lives on another lane branch (`k-w1`, `k-k8`, `k-w1b`, `k-paper`, `k-w2-spec`) and was not run on this branch. The coordinator turns each item on after the merge into `k-r1` and runs the checks in the last section. Nothing here was merged from the lane branches: their files were read with `git show origin/<branch>:<path>`.


## Status at integration (k-r1, 2026-11-19)

Done by the integration lane, evidence class measured, local laptop, not the acceptance machine:

- **T51 to T57:** Step 2 turned on (the `tutorial:run python` marker moved from Step 1 to Step 2). Each printed exactly the lines of Step 1, so no expected block changed and no tutorial needed a behaviour fix. `python tools/check_tutorial.py --lang python --page <page>`: 51 (9 lines), 52 (5), 53 (6), 54 (6), 55 (8, 2 s), 56 (6), 57 (8) match. Page notes and evidence lines brought to the merged state.
- **T58:** stays Step 1 only (the ledger is not running, 0 of 20 days); Step 2 needs the `paper-ledger` branch, which does not exist yet. Step 1 matches (4 lines).
- **C1 to C8:** run once on `k-r1`; the "not run" notes replaced with the observed output. C2, C4 and C7 differ from the golden in the last digit or two, inside each golden's tolerance, and the recipe says so. C6 run in Python only; its text corrected from "Python and Java only" to all four builds, the restriction lifted for `CN_RANNACHER_SMOOTHED` only (KR-110; withdrawn the same day by KR-113: the restriction stays for both methods) and the 0.4986-year row not judged. C7 and C8 corrected from "Python only, needs registration" to registered in all four builds.
- **C9:** not run (no `paper-ledger` branch); `verify_ledger.py --help` lists the options the recipe uses.
- Status ladder: the hand-quoted stage K table is deleted; every stage K share on that page is generated.
- `tools/check_docs_status.py`: 0 problems on `k-r1`.

The sections below are the docs lane's original list, kept as written.

## How the tutorial blocks are built

Tutorials 51 to 58 are marked `<!-- tutorial:only python -->`. Step 1 of each is a standard-library restatement of the spec's rule on the golden inputs, marked `<!-- tutorial:run python -->`, and CI checks its lines today (`python tools/check_tutorial.py --lang python --page <page>`, all eight pass on this branch, 2026-11-19). Step 2 is the library call, preceded by a comment `<!-- runs-after-integration: Tnn -->` and NOT marked `tutorial:run`. The checker allows one run block per language, so turning Step 2 on means moving the `<!-- tutorial:run python -->` marker from Step 1 to Step 2. Steps 2 of T51 to T57 are written to print the same lines as Step 1, so the `tutorial:expect` block should not need to change. **None of them has been run**: if a line differs, the library output wins only if the block's own golden assertion passed; otherwise it is a finding.

| Id | Page | Needs (branch) | Turn on by | Expected output |
|---|---|---|---|---|
| T51 | `docs/getting-started/tutorial-51-bitemporal-store.md` | `core.store.bitemporal_query`, `datasets/golden/stage_k/bt_k.json` (`k-w1`) | moving the run marker to Step 2 | the 9 lines of Step 1 |
| T52 | `docs/getting-started/tutorial-52-incremental-curve-update.md` | `curve.bootstrap.par_annual`, `curve.incremental.update`, `inc_k.json` (`k-w1`) | same | the 5 lines of Step 1; the last prints the error code from the library (`E_INPUT`) |
| T53 | `docs/getting-started/tutorial-53-recalibration-triggers.md` | `calib.trigger.check`, `trig_k.json` (`k-w1`) | same | the 6 lines of Step 1 |
| T54 | `docs/getting-started/tutorial-54-intraday-risk-bounds.md` | `risk.intraday.delta_gamma_bound`, `idr_k.json` (`k-w1`) | same | the 6 lines of Step 1 |
| T55 | `docs/getting-started/tutorial-55-bermudan-ladder-convergence.md` | `num.richardson.check` (`k-w1`); `CN_RANNACHER_SMOOTHED` and `k8_k.json` (`k-k8`) | same; in Python only (the method is not in C++ or Rust) | the 8 lines of Step 1. The `k8_k-0001` call runs one ladder at 201/100 in Python; time it before turning it on (the port note gives about 4 minutes for all of acceptance 3) |
| T56 | `docs/getting-started/tutorial-56-sa-ccr-example-1.md` | `risk.saccr.ead` registered (registration lines 1 and 2 of `program/STAGE_K_W1B_HANDOVER.md`), `saccr_k.json` (`k-w1b`) | same | the 6 lines of Step 1 |
| T57 | `docs/getting-started/tutorial-57-backtesting-traffic-light.md` | `risk.frtb.backtest.zone`, `.desk` registered, `tlk_k.json` (`k-w1b`) | same | the 8 lines of Step 1 |
| T58 | `docs/getting-started/tutorial-58-daily-paper-ledger.md` | `tools/paper_daily/` (`k-paper`); the second block also needs the `paper-ledger` branch | **not for CI**: run by hand once the workflow has run on `main`; keep Step 1 as the checked block | depends on the day; record the first real `--no-cli` and full verify results in the handover |

## Cookbook recipes

`COOKBOOK.md`, section "Stage K recipes (in progress)": every recipe there is headed "runs after integration" and none is executed by any checker. After the merge, run each command once and replace the "not run" note under it with the observed output and date.

| Id | Recipe | Needs (branch) |
|---|---|---|
| C1 | Query a bitemporal log | `core.store.bitemporal_query` (`k-w1`) |
| C2 | Update a curve for one moved quote | `curve.incremental.update` (`k-w1`) |
| C3 | Check whether to recalibrate | `calib.trigger.check` (`k-w1`) |
| C4 | Intraday P&L with an error bound | `risk.intraday.delta_gamma_bound` (`k-w1`) |
| C5 | Guard a Richardson extrapolation | `num.richardson.check` (`k-w1`) |
| C6 | Ask for the smoothed Bermudan ladder | `method: CN_RANNACHER_SMOOTHED` (`k-k8`; Python and Java only) |
| C7 | SA-CCR EAD for a netting set | `risk.saccr.ead` (`k-w1b`, Python only, after registration) |
| C8 | Backtesting zone and desk eligibility | `risk.frtb.backtest.zone`, `.desk`, `.count` (`k-w1b`, Python only, after registration) |
| C9 | Verify the daily paper ledger | `tools/paper_daily/verify_ledger.py` (`k-paper`) |

## Question bank and LEARN

- `docs/question-bank/14-stage-k-risk-platform.md` and its checker `docs/question-bank/verify/v14_stage_k.py` restate every number with the standard library (no build needed), so they run on this branch. After the merge, the checker can also be pointed at the goldens: replace the inline golden constants with reads of `datasets/golden/stage_k/*.json` (to do; the constants are copied from those files and cite them).
- LEARN section "Stage K: risk platform and capital" cites files on lane branches by path in backticks, not as links, so the link checker passes today. After the merge, turn the backticked spec paths into links.

## Generated or quoted figures to refresh after the merge

- `docs/validation/status-ladder.md`: the per-stage and stage H tables are generated from `oracle/OUTSIDE_SHARES.json` by `tools/validation/status_ladder.py`. The stage K per-item table is quoted by hand from lane files, because on this branch no tool computes it. After the merge, `tools/outside_shares.py` (k-w1 version) writes a stage K `per_item` block; rerun `python tools/validation/status_ladder.py` and delete the quoted table (the script prints the generated one as soon as the JSON has stage K).
- `docs/releases/v0.10.1.md` (draft): fill the tag, commit, case totals (`tools/case_figures.py`), contract version, and the H-9 R2 line (left as a placeholder; this lane says nothing about R2's result).
- `CHANGELOG.md` "Unreleased": the evidence paths point at lane-branch files; check each path exists after the merge.
- `ROADMAP.md` K row: same.
- Diagrams in `docs/diagrams/README.md` (stage K section): rendered in the locally built site on `k-docs` (2026-11-19: 54 of 54 diagrams on the page draw an SVG; the four new ones draw 16, 12, 14 and 10 nodes, all of their nodes, with no parse error). Render them again in the built site after the merge (the round-1 audit found one parse error that only the browser showed, F-34).

## Checks to run after the merge (in this order)

```bash
python tools/check_tutorial.py --lang python          # every page; T51 to T57 with Step 2 turned on
python tools/check_md_anchors.py                      # anchors, every tracked .md
python tools/build_site.py && python tools/check_md_anchors.py --site
python docs/question-bank/verify/v14_stage_k.py
python docs/question-bank/verify/build_index.py       # then git diff docs/question-bank/README.md: no change expected
python tools/validation/status_ladder.py --check
python research/test_preregs.py
python tools/check_hygiene.py
# then the banned-word grep of LANE_RULES_K.md on the diff: it must print nothing
```

## For the coordinator

1. **Banned word in branch history.** Commits `c05fbac3`, `0003d944`, `7f8bdbcd` and `3ee5b687` on `k-docs` carry the banned word inside a grep command in this file (removed at the tip in the next commit). A force-push to rewrite them was refused by the session's permission rules, so the history still has it. Squash-merge `k-docs`, or rewrite those commits, before anything reaches `main`.
2. The tutorial checker was run on pages 51 to 58 in Python only; the CI tutorial workflow also runs them in Rust, Java and C++, where `tutorial:only python` skips them (checked locally for Rust on page 51).
3. **`tools/check_docs_status.py` fails on `k-docs` alone** (it runs inside `tools/test_tools.py`, test `DocsStatus.test_shipped_docs_pass`): 27 problems, every one a backticked stage K operation name (`core.store.bitemporal_query`, `calib.trigger.check`, `risk.intraday.delta_gamma_bound`, `risk.saccr.ead`, `risk.frtb.backtest.zone` and the like) that is not yet in `specifications/name-map.json` on this branch. The gate is not changed. Merge `k-docs` after the lane branches and after `python tools/gen_name_map.py`; the check should then report 0 problems. If a name is still flagged after that, the doc names an operation that was not built, and the doc is wrong.
