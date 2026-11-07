# Golden results

A golden case is a stored case with an expected result obtained without any of the four implementations. They all come from `oracle/`; never write one by hand or from an implementation.

Each file in `core/`, `stage_b/` and `stage_c/` holds `suite`, `spec`, `spec_version`, `generator`, `reviewer` and `cases`. Each case holds `case_id`, `operation`, `inputs`, `expected`, `tolerance_class`, `verified_by` and `tags`.

`reviewer` says "none: self-assessment until the end-of-project human review", which is the true state of every file. `verified_by` names the sources that agreed. A case with only hand or replay sources can share a misreading with the spec, as `oracle/README.md` explains.

Stage A has 22 suites and 4,394 cases. Stage B has 18 suites and 343 cases, so 40 suites and 4,737 cases in all. Which stage B suites have an outside oracle is in `specifications/stage-b-rulings.md`.

Stage C adds 11 suites and 428 cases, in `stage_c/`. Sources per suite are in `specifications/stage-c-rulings.md`.
