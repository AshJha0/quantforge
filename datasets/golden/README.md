# Golden results

A golden case is a stored case with an expected result obtained without any of the four implementations. They all come from `oracle/`; never write one by hand or from an implementation.

Each file in `core/` holds `suite`, `spec`, `spec_version`, `generator`, `reviewer` and `cases`. Each case holds `case_id`, `operation`, `inputs`, `expected`, `tolerance_class`, `verified_by` and `tags`.

`reviewer` says "none: self-assessment until the end-of-project human review", which is the true state of every file. `verified_by` names the sources that agreed. A case with only hand or replay sources can share a misreading with the spec, as `oracle/README.md` explains.

Stage A has 21 suites and 4,388 cases.
