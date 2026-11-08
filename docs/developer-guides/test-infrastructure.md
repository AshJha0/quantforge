# Test infrastructure

Pull request #1 ran the workflows it triggers on GitHub, and all passed, including GCC, Clang (libc++) and sanitizers. Whether `fuzz.yml`, `mutation.yml` and `docs.yml` have run there was not checked. Stages A and B passed their pull request and `main` workflows on GitHub.

Pull-request workflows run only when their paths change, so PRs stay fast. The repository is public, so standard runners are free; scheduled jobs that never run on a pull request add Windows and macOS (plan 11.1.5). See `r1-infra.md` for the scheduled jobs.

| Workflow | Runs on | What it does |
|---|---|---|
| `conformance.yml` | Pull request, push to main, manual | Builds each CLI and runs all golden cases, and tests the runner itself. A scope job limits this to the languages changed; the runner, tolerances, datasets, specifications or this workflow run everything |
| `java25.yml`, `cpp26.yml`, `python.yml`, `rust.yml` | Pull request and push to main, own paths only | Each language's own build and unit tests. `cpp26.yml` has GCC and Clang jobs |
| `sanitizers.yml` | Same, C++ paths only | Unit tests and golden cases under ASan and UBSan |
| `fuzz.yml` | Monday, manual | Three minutes of fuzzing per language; C++ uses the sanitizer build |
| `mutation.yml` | Manual only | One language and one target per run |
| `docs.yml` | Markdown, site script, gallery, example, Python or stage B golden change, manual | Reruns the Python CLI against the committed Curves gallery (`curves-gallery.md`), builds the static site with `tools/build_site.py`, fails on a broken relative link, and keeps the site as a 7-day artifact. On a public repository, a push to `main` also deploys to GitHub Pages. |
| `cross-platform.yml` | Sunday, manual | Conformance on Linux, Windows and macOS for all four languages, 12 cells (`r1-infra.md`) |
| `recorder.yml` | 14:30 and 23:30 UTC on weekdays, manual | Public-data recorder; pushes hash rows and a gap report to branch `forward-log` (`recorder-actions.md`) |
| `daily-workflows.yml` | 15:00 UTC on weekdays, manual | Workflows (a) EOD curves and (c) SOFR check on real data; dated reports to `forward-log` (`r1-infra.md`) |
| `mutation-stage.yml` | First of the month, manual | Every module of one stage in all four languages, then one report scored against the stage target (`r1-infra.md`) |
| `oracle-coverage.yml` | PR and push touching `oracle/`, `datasets/`, `specifications/`, tolerances; manual | QuantLib 1.44 rebuilds the stage D cases; fails below 60% outside-oracle share or on a stale register |
| `calendar-expiry.yml` | Monday, manual | Calendar provenance: fails when a calendar's coverage ends within 12 months; expected red until SIFMA's December release |
| `security.yml` | Monday, lockfile change, manual | OSV scan of the Rust, Python and Java dependencies |

Dependabot opens one grouped pull request per ecosystem each month. It does not track the Catch2 pin in `cpp26/CMakeLists.txt`, so update that by hand.

## Build the CLIs

```bash
(cd java25 && mvn -B -DskipTests package)
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
uv sync --locked --project python
(cd rust && cargo build --release -p quantforge-cli)
python conformance/runner/runner.py --impl rust
```

## Sanitizers

```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DQF_SANITIZE=address,undefined,float-cast-overflow
```

Use Linux or WSL. GCC on MinGW has no sanitizer runtime. Inside a container, LeakSanitizer needs `--cap-add=SYS_PTRACE`.

## Fuzzing

```bash
python conformance/fuzz/fuzz_cli.py --impl cpp --seconds 60 --seed 1
```

There is one shared driver, not a native fuzzer per language, because the contract is the CLI and the checks must be identical. It does not use coverage feedback, so it finds less than libFuzzer or Jazzer would. A timeout is a finding: an input that asks for an enormous amount of work counts until the specs set a limit. Such an input can also use a lot of memory, so keep local runs short.

## Mutation

Start small: one file per run.

| Language | Command | Notes |
|---|---|---|
| Java | `mvn -Pmutation test-compile org.pitest:pitest-maven:mutationCoverage -DtargetClasses=org.quantforge.core.Compounding` | From `java25/` |
| C++ | `python conformance/mutation/cpp_mutants.py --file cpp26/src/core/compounding.cpp --max 10 --suite compounding` | Uses golden cases as the test. Mull is the option to try if this proves too coarse; it needs a matching LLVM |
| Python | `uv run --with mutmut==3.8.1 mutmut run 'quantforge_core.compounding*'` | From `python/`. Linux or WSL only. Uses `tests/test_core.py`, because mutmut's copy cannot see files outside `python/` |
| Rust | `cargo mutants --in-place -p quantforge-core -f '**/compounding.rs'` | From `rust/`. `--in-place` is needed because the crate reads files outside `rust/`. It edits the tree while it runs, so use a clean checkout |

The Java score measures unit tests only, so a survivor there may still be caught by conformance.

### Rust and Python against the golden cases

`conformance/mutation/golden_mutants.py` takes the mutants cargo-mutants and mutmut generate, keeps their unit verdict, and runs a seeded sample through the neutral runner in a private copy. Each sampled mutant then has two verdicts. Use Linux or WSL; `mutation.yml` does the same with its `golden` input.

```bash
python3 conformance/mutation/golden_mutants.py --impl rust --target '**/compounding.rs' --max 40
python3 conformance/mutation/golden_mutants.py --impl python --target 'quantforge_core.compounding*' --suite compounding --max 40
```

Observed, WSL Ubuntu, 2026-11-06, source at `a60d814`, seed 1, one run. Unit score is over all viable mutants, with timeouts counted as killed. Sample columns are kills out of 40.

| Target | Golden suites | Unit, all mutants | Sample: unit | Sample: golden | Sample: either |
|---|---|---:|---:|---:|---:|
| Rust `compounding.rs` | all | 25 of 61 (41%) | 16 | 36 | 36 |
| Rust `daycount.rs` | all | 91 of 165 (55%) | 25 | 38 | 38 |
| Python `compounding` | `compounding` | 44 of 192 (23%) | 8 | 21 | 21 |
| Python `daycount` | `daycount` | 173 of 436 (40%) | 15 | 34 | 35 |

This was measured on stage A code. No mutation score exists for stage B code; `oracle/MUTANTS.md` is a different check, of the golden tolerances. Limits: this is two files per language and 40 mutants each, so a sample figure can be several points out. Python ran one suite, because all suites take over a minute per mutant, so it may undercount. Survivors have not been sorted into equivalent mutants and real gaps. mutmut changes error message text, which the runner does not compare, and that may explain some Python survivors. The four Rust compounding survivors include three in `check_rate`, which are worth a look as possible missing cases.

## Stage quality scope

`conformance/quality/stage_e.json` lists the stage E modules per language: the coverage gate (85% line coverage, `.github/workflows/coverage-stage.yml`, weekly and manual), the scope check and the fuzz focus read it, and `conformance/mutation/stages.json` has the same module names under stage E. Entries start as TODO and every tool skips them. When a module lands, replace its TODO with the source path and run `python tools/quality_gate.py --check-config`: it fails if the path matches nothing, a Rust file is outside a workspace member crate, a C++ file is not in `cpp26/CMakeLists.txt`, or a Python file or test is outside what ruff and mutmut cover. Weekly fuzzing draws about half its seeds from `datasets/golden/stage_e` once that folder exists.
