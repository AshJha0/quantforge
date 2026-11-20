# Runbooks

One page per thing that can go wrong in operation, read when it has. Plan item 14.8 K-7 asks for runbooks; the spec is `specifications/12-platform/release-evidence.md` (check RE3, ruling KR-224, both PROPOSED).

| Runbook | Use it when |
|---|---|
| [Releasing v1.0.0](release-v1.0.0.md) | preparing, tagging, verifying or rolling back the release |
| [Daily jobs](daily-jobs.md) | the paper ledger or the daily curve run is red, or you want to check their hash chains |
| [Mutation gate red](mutation-gate-red.md) | `mutation-report` fails on a pull request or the weekly sweep |
| [Recorder](recorder.md) | the public-data recorder is red or shows a gap |
| [CI failure triage](ci-failure-triage.md) | any other check is red |

**How the pages are kept honest.** `tools/check_runbooks.py` reads every `bash` block of these pages and fails if a command names a repository path, a script option or a workflow that does not exist; it runs in `repo-gates` and fails its own planted faults (`--self-test`). It cannot show that a command works, only that what it names is there. Every page follows the house order: plain idea, formal statement, worked example, with the source of each statement and its evidence class (read, recalled, measured, inferred).

Each runbook was written on 2026-11-20 from the workflow files and tools named in it; none has been used in an incident yet.
