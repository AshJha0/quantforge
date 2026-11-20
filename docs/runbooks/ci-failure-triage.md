# Runbook: a CI check is red

**Plain idea.** Find out first whether the check is right. A red check is one of three things: the change broke something (fix the change), the check met something new in the world (a runner image, a mirror, a holiday), or the gate cannot pass as written (fix the gate's arithmetic, never its threshold). Loosening a threshold, skipping a test or resampling until green is never the fix (lane rules; owner decision 2026-11-15 on recurring red checks: compute the gate's pass probability before treating symptoms).

**Formal statement.** The checks a pull request must pass are the 19 names in `.github/required-checks.json`; `tools/check_job_names.py` checks that each is a unique job name in a workflow that runs on every pull request (read 2026-11-20). A required check that is red blocks the merge; the other workflows report but do not block.

## Step 1: which workflow, which job

```bash
gh pr checks <pr number>
gh run view <run id> --log-failed
```

| Required check (job name) | Workflow | Usual first suspect |
|---|---|---|
| `repo-gates` | `repo-gates.yml` | a generated page is stale; run the step's command locally, it prints the regeneration command |
| `python-test`, `rust-test`, `java25-test` | `python.yml`, `rust.yml`, `java25.yml` | a unit test or lint failure in that build |
| `cpp26-gcc`, `cpp26-clang` | `cpp26.yml` | clang `-Wshadow` warnings that gcc does not give (lane rules, "Lessons") |
| `conformance-*` | `conformance.yml` | a golden added without all four builds passing it; a language test that hard-codes golden counts |
| `sanitizers-asan-ubsan` | `sanitizers.yml` | memory or undefined-behaviour error in C++ |
| `mutation-plan`, `mutation-report` | `mutation-stage.yml` | see [mutation-gate-red.md](mutation-gate-red.md) |
| `coverage-stage-*` | `coverage-stage.yml` | a changed file below 90% line coverage |

## Step 2: reproduce locally, cheapest first

The `repo-gates` steps are standard-library Python and take seconds:

```bash
python tools/check_hygiene.py
python tools/check_job_names.py
python tools/case_figures.py --check
python tools/build_references.py --check
python tools/check_e1_coverage.py
python tools/check_share_figures.py
python tools/validation/status_ladder.py --check
python tools/validation/model_reports.py --check
python tools/results_page.py --check
python tools/check_known_issues.py
python tools/check_runbooks.py
python research/test_preregs.py
```

The docs checks (`docs.yml`):

```bash
python tools/test_tools.py
python tools/check_quickstart.py
python tools/build_gallery.py --check
uv run --no-project --with markdown==3.11.2 python tools/build_site.py --out site
python tools/check_md_anchors.py --site site
```

Language builds: the commands in `CONTRIBUTING.md` ("Check your machine" and one section per language). On the owner's laptop, C++, Rust and native Python builds run in WSL, one heavy job at a time, and nothing heavy starts while `C:/Work/Claude/qf-wt/_h4ci/QUIET` exists (lane rules).

## Step 3: is the gate passable?

For a statistical gate, compute the pass probability of a good change before touching code. Worked example (`conformance/mutation/test_gates.py`, check 6, and CHANGELOG 0.9.1): the mutation gate needs a 95% Wilson lower bound of at least 65%. On a 12-mutant sample, 11 of 12 has a lower bound of 0.646, so the gate allowed no survivor, and a module that truly kills 90% passed 28% of the time. The fix was the sample size (40 mutants, up to 8 survivors), not the bound.

## Step 4: a red check on main or on a schedule

| Workflow | What red means | Runbook |
|---|---|---|
| `recorder.yml` | a recent business day has no row for a source | [recorder.md](recorder.md) |
| `paper-ledger.yml`, `curve-daily.yml` | a gap, late day, refused run or failed anchor | [daily-jobs.md](daily-jobs.md) |
| `calendar-expiry.yml` | a holiday calendar's confirmed-through date is near; red until SIFMA publishes its 2027 schedule (ROADMAP, R1) | extend the calendar from the published source |
| `security.yml` | a dependency advisory | update the pinned dependency through a pull request |
| `release.yml` | see [release-v1.0.0.md](release-v1.0.0.md), "Rollback" | |

## Never

- re-run a red check hoping for green without a reason that the cause was transient (a runner outage, a mirror returning HTTP 429; `release.yml` notes the Maven fallback settings for 429);
- change a tolerance, target, threshold or acceptance test to make a run pass; a miss is recorded as a miss;
- push while a local test run is unfinished (owner instruction 2026-10-25).
