# Python mutation survivors: equivalent and accepted

R6-14 (review finding 5): one list per language, same columns as `equivalents-cpp.md`. At v0.8.0 no
Python list existed; survivors of the weekly run (`mutation-stage.yml`, stage ALL, 40 seeded mutants per
module) are entered here by the language lane after the first full run. Under rule M a row with an empty
second-reviewer cell still counts as surviving, and `stage_report.py --gate` clears a module below target only
through a countersigned entry in `reasons.json`.

Classes: **Equivalent** (no input changes any output); **Accepted** (not equivalent, but only an exact
floating-point tie or an unreachable bound tells it apart; state which).

| File:line | Operator | Mutant | Class | Author reason | Second reviewer, date |
|---|---|---|---|---|---|
