# Stop note: lane k-v1-docs-c (status documents to the state of main, 2026-11-21)

Branch `k-v1-docs-c`, cut from main 11ba1b40. Docs only; no code, no version bump, no release heading.

## Done
- `specifications/12-platform/soak-eod-capacity.md` line 39: "about 1.2 bytes per case" corrected to 12.7 with the arithmetic (1,048,576 / (23 x 3,600) = 12.66). The 0.8 MiB/h and 80 MiB/h figures on the same line were rechecked and are right.

## In progress
- README, CHANGELOG, known-issues, results, ROADMAP, capacity, site_facts: PRs #60 to #64, wave 2 merged, K-5 merged, runner soak result, fuzz run, daily workflows green.

## Notes for the coordinator
- README question count: no tool generates it; left at 470 (main has 470, read from docs/question-bank/README.md). The branch that brings 485 must edit README.md "Start here" item 5.
