# Python sampled mutation runner

`python_sampled_mutants.py` measures a mutation score for one group of Python modules without
mutmut (which needs `fork` and so does not run on Windows). It is module-scoped and sampled, so a
run takes about an hour on the reference laptop instead of the full mutmut run that timed out
under WSL.

## Before a mutmut job: valid mutant syntax

mutmut 3.8.1 aborts the whole run if one mutant of a file is not valid Python. It does this when
it removes the `not` from a wrapped `if (not ...)` guard and drops the outer parentheses (fixed in
`shortrate.swaption`). `mutmut_syntax_check.py` runs mutmut's own generator over every module and
compiles the output. On 2026-11-15 all 115 `quantforge_core` files passed (345 s in WSL); the
pre-fix `shortrate.py` fails it. It is too slow for the unit tests, so run it by hand after a
reformat or a new long boolean guard (usage in the script's docstring).

## How it works

- Mutation sites are every AST node of the profile's modules that one of the operators applies to,
  in `ast.walk` order: arithmetic swaps, comparison swaps, `and`/`or`, removal of unary minus and
  `not`, number + 1, string literal `"XX...XX"` (docstrings skipped), `True`/`False`.
- The sample is `random.Random(seed).sample(sites, n)`. With the same module sources, seed and
  `n`, the same mutants are drawn; `--list` prints them as diffs without running anything.
- Each mutant is written into a scratch copy of `python/` (with `datasets/`, `specifications/` and
  `conformance/` beside it); the checkout is never modified. The profile's tests run with the copy
  first on `PYTHONPATH`, `pytest -x`. Exit 1 or a timeout is killed, exit 0 survived.

## The credit profile

Modules `quantforge_core/credit.py` and `quantforge_core/credit_options.py` (836 sites). Tests:
`test_stage_g_credit_mutants.py`, `test_stage_e8.py`, `test_credit_kills.py` in full, and the
credit-related tests (`-k "credit or cds or hazard or survival ..."`) of the other unit-test files
that touch the credit modules.

Recorded runs (seed **20261111**, sample **90**, 3 workers):

| Date | Tests | Killed | Score |
|---|---|---|---|
| 2026-11-11, first run | unit tests only, before `test_credit_kills.py` | 52 of 90 | 57.8% |
| 2026-11-11, rerun | with `test_credit_kills.py` (goldens in process plus targeted checks) | 77 of 90 | 85.6% |

Of the 13 survivors of the rerun: 8 are iteration caps or bracket factors (equivalent: the solves
converge well inside them), 4 change only message text or the code string of an unreachable
`E_NO_CONVERGENCE` branch, and 1 (`credit._series` fourth-order term) is killed by
`test_credit_series_branch_matches_the_closed_form`, added after the rerun.

Reproduce:

```
python/.venv/Scripts/python conformance/mutation/python_sampled_mutants.py \
    --profile credit --sample 90 --seed 20261111 --workers 3 --work <scratch dir> \
    --python python/.venv/Scripts/python.exe --out <results.json>
```

## Survivors left alive on purpose

Mutants that change only the wording of an error message are not killed: the CLI contract fixes
the error `code` and `field`, not the message text, and a test pinning the text would block every
later rewording. `test_credit_kills.py` pins codes and fields instead. Mutants that only change an
iteration cap or a bracket growth factor are equivalent on every input the specs allow (the solve
converges long before the cap, and any bracket that contains the root gives the same root to the
solver tolerance); each is listed with its reason in the module docstring of `test_credit_kills.py`.

## Which modules a pull request samples

The PR mode of `mutation-stage.yml` lists the files the pull request touches, then passes them
through `semantic_changes.py BASE HEAD --in touched.txt` before `plan_matrix.py --changed`. A
file is dropped when base and head are the same code: for Python, `ast.dump(ast.parse(src))` is
equal (whitespace, comments and line breaks do not count; docstrings do); for Rust, C++ and Java,
the token stream with whitespace and comments removed is equal (string literals kept whole). So a
formatting-only commit such as `ruff format` does not pull every module into `mutation-report`.
The filter is conservative: new, deleted or renamed files, other extensions, parse errors and git
errors all count as changed. `test_gates.py` covers it.

## Pull-request sample size

A pull request samples the same 40 mutants per module as the weekly run. Until 0.9.0 it sampled 12, and
that could not pass a good module: the gate needs a point estimate of at least 80% and a 95% Wilson
lower bound of at least 65%, and with 12 mutants even 11 killed out of 12 has a lower bound of 0.646. So
one survivor failed the module, and a module that really kills 90% of its mutants passed only 28% of
the time. With 40 mutants up to 8 survivors pass; the pass probability is 0.98 at a true 90% kill rate
and 0.93 at 87%. `test_gates.py` reads the PR value from `mutation-stage.yml` and fails if the sample
allows fewer than 3 survivors or passes a 90% module less than 90% of the time. Rust modules keep the
two shards (`plan_matrix.RUST_SHARDS`) and the 120-minute job limit the weekly run already uses.
