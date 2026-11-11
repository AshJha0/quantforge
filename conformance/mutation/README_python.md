# Python sampled mutation runner

`python_sampled_mutants.py` measures a mutation score for one group of Python modules without
mutmut (which needs `fork` and so does not run on Windows). It is module-scoped and sampled, so a
run takes about an hour on the reference laptop instead of the full mutmut run that timed out
under WSL.

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
| 2026-11-11, rerun | with `test_credit_kills.py` | see the commit that updates this table | |

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
