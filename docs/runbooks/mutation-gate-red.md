# Runbook: the mutation gate is red

**Plain idea.** The mutation check changes one small thing in the code (a `<` to `<=`, a `+` to `-`), runs the tests and goldens, and counts how many of those changes ("mutants") the tests catch. A red `mutation-report` says that, in one module and language, too many changed programs still passed. The fix is a test that catches them. It is never a new sample, a lower target or an exception nobody can sign.

**Formal statement** (read from `.github/workflows/mutation-stage.yml`, `conformance/mutation/stage_report.py` and `conformance/mutation/test_gates.py`, 2026-11-20):

- Sample: 40 mutants per module and language (`max`, default 40) for Python, Rust and C++; Java runs PIT on the target classes.
- Gate per module and language: killed share at least 80% **and** the 95% Wilson lower bound of that share at least 65%. With 40 mutants that allows up to 8 survivors (`test_gates.py`, check 6).
- Seed on a pull request: `conformance/mutation/content_seed.py` hashes the mutated source, so the same code always draws the same sample (owner decision 2026-11-18). A re-run of the same code gets the same verdict. The weekly sweep (Sunday 05:41 UTC) uses the run number as its seed, so samples do not stay frozen.
- Skips: samplers leave out only the mutants listed in `conformance/mutation/skip-equivalents.json`, which takes signed Equivalent rows only. With no second review (owner decision 2026-11-18), a new Equivalent row has no second signature, so it stays counted as a survivor; scores are lower bounds.
- Exceptions: `conformance/mutation/reasons.json` clears a module only with a non-empty `second_reviewer`; it is empty, and stays empty under the same decision.
- A mutant that times out counts as caught (an endless loop is a detected change); a segfault does not (`test_gates.py`, check 7).

## Worked example: why a re-run does not help

A module whose tests truly catch 90% of mutants: with the old 12-mutant sample and a fresh seed per run, the gate allowed no survivor and passed only 28% of the time (`mutation-stage.yml` header; `test_gates.py`, check 6). With 40 mutants it passes with probability at least 0.9. With the content seed, re-running the same code redraws nothing, so the only way from red to green is a change to the tests (or to the code, which draws a new sample from the new content; a change made only to get a new draw is fishing and is not done).

## Steps

1. Read the report. The run artefact `mutation-report-<stage>` holds `mutation-report.md`: score, killed, survived and the 95% Wilson bound per module and language. The per-mutant results (each mutant's change and verdict) are in the artefacts `mutation-<lang>-<module>`, one per matrix job.
2. Reproduce the plan locally (seconds, standard library):

   ```bash
   python conformance/mutation/plan_matrix.py --stage K
   python conformance/mutation/content_seed.py --lang python --target <mutmut target from the plan>
   ```

   The printed seed must equal the one in the run log; if it does not, the source differs from the run's.

3. For each survivor, decide which it is:
   - **a missing test**: write a unit test whose expected value is derived independently (by hand, from the spec's formula, or from the oracle), not copied from the build's own output. Name it after the behaviour, not the mutant.
   - **an equivalent mutant** (the change cannot alter any output): write the argument in `conformance/mutation/equivalents-<lang>.md`. It stays counted until a signed row exists in `skip-equivalents.json`, which under the no-second-review decision does not happen.
4. Re-run only the affected module, planned as a pull request that touches it:

   ```bash
   gh workflow run mutation-stage.yml --ref <your branch> -f paths=<source path>
   ```

5. Check the gate scripts themselves still fail their planted faults:

   ```bash
   python conformance/mutation/check_stages.py
   python conformance/mutation/test_gates.py
   ```

Both run in `repo-gates` on every pull request.

## What not to do

- Do not pass a `seed` input to fish for a sample with fewer survivors.
- Do not lower `target` in `conformance/mutation/stages.json` (0.8 for every stage) or the Wilson bound.
- Do not add a row to `skip-equivalents.json` or `reasons.json` without the second signature the files require.

## Limits

- Scores are of a 40-mutant sample, not of every mutant; a pass says the true kill rate is probably above about 65%, not that it is above 80%.
- KF-31 (open, `docs/known-issues.md`): mutmut may skip the five `@limits_first` functions in `quantforge_core.stage_k`, so their score may rest on fewer mutants than listed. Unconfirmed.
