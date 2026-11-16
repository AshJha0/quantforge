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
| python/quantforge_core/variance.py:451 | zip strict | `variance.x_varswap_fair_strike__mutmut_124`, `_133` (`strict=True` dropped or False) | Equivalent | `_weights(ks, ...)` appends exactly one weight per strike in `ks`, so the two zipped sequences always have the same length and `strict` never fires. | |
| python/quantforge_core/variance.py:457 | string | `variance.x_varswap_fair_strike__mutmut_171`, `_178`, `_179` (`"PUT"` to `None`, `"XXPUTXX"`, `"put"`) | Equivalent | `black.Option.phi` (black.py:57) is `+1` only for `"CALL"` and `-1` for every other value, and `black.price` reads the type only through `phi`; any non-`"CALL"` value prices the same put. | |
| python/quantforge_core/variance.py:229-231 | constant | `variance.x__score__mutmut_9`, `_14`, `_36` (the NORMAL defaults of `nu`, `c`, `dc` from 0.0 to 1.0) | Equivalent | `nu`, `c` and `dc` are read only inside `if student:` (lines 235-239); with `student` false the values are never used. | |
| python/quantforge_core/variance.py:345,362,364 | zip strict | `variance.x_garch_estimate__mutmut_207`, `_210`, `_211`, `_294`, `_298`, `_299`, `_304`, `_307`, `_308` | Equivalent | `gu`, `gd` both come from `_score` on a list of length `n`; `theta`, `step` (a solve of an `n x n` system) and `scale[:n]` all have length `n`. Equal lengths, so `strict` never fires. | |
| python/quantforge_core/variance.py:581-582 | compare / constant | `variance.x_vix_term_variance__mutmut_177`, `_178`, `_179` (`len(ks) == 1` to `== 2`; `gap = 0.0` to `None`, `1.0`) | Equivalent | Line 573 refuses a strip without an OTM put or an OTM call, so `ks` = puts + K0 + calls has at least 3 strikes; neither `len(ks) == 1` nor `len(ks) == 2` can hold, so the branch is dead. | |
