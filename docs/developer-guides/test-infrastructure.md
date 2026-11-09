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

## Warnings as errors

CI configures the C++ build with `-DQF_WERROR=ON`, which adds `-Werror -Wconversion -Wshadow -Wno-sign-conversion` on top of `-Wall -Wextra` (GCC already leaves sign conversion out of `-Wconversion` in C++; the explicit `-Wno-sign-conversion` keeps Clang in line). Local builds leave it off so a new warning does not stop work in progress. Turn it on before you push C++ changes.

## Limit cases and convergence orders

Some stage E methods have no outside reference to compare against: the SLV leverage scheme, the backward-Euler American scheme, and the Crank-Nicolson and CRR pricers beyond their golden cases. For these, a set of unit tests (`rust/crates/quantforge-core/tests/limits_e.rs`, `java25/.../pricing/LimitsETest.java`, `cpp26/tests/test_limits_e.cpp`, `python/tests/test_limits_e.py`) checks each one against a case whose answer is known and against its own theoretical order. SLV with a flat 20% surface and a Heston model with v0 = theta = 0.04 and vol of vol 0.01 is plain Heston, so the leverage must be 1: the gap within 0.3 of ln(spot) is under 0.07 on a 41x20x20 grid and must fall below 0.6 of that on a 81x40x40 grid, which shows it is discretisation error. The American put on a 401x1600 grid must agree with a 1000-step CRR tree to 5e-3 (the measured scheme error there is about 2e-3, the tree's about 5e-4), and at zero rate and zero yield, where early exercise is worth nothing, it must equal the European to 1e-12. The observed orders, log2 of successive error ratios on doubled grids, must lie in [1.8, 2.2] for Crank-Nicolson with Rannacher start (measured 1.99 to 2.00) and for the backward-Euler scheme in space with dt quartered (2.00 to 2.01), and in [0.8, 1.2] for the same scheme in time (1.00) and for the CRR European at the money (1.00). Python also calibrates SLV to the Dupire local vol of an SVI surface fitted to Heston prices (v0 = theta = 0.04, kappa 1.5, xi 0.3, rho -0.5): the leverage must be within 0.06 of 1 within 0.3 of ln(spot) at 0.5, 0.75 and 1 year, and a seeded 20,000-path Euler Monte Carlo with that leverage must reprice the 1-year Heston calls at strikes 90, 100 and 110 within 3 standard errors (measured 1.3, 0.9 and 0.1). Evidence class: computed in this repository, against closed forms and the methods' own theory; no outside source.

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

### Mutation scores (stage E)

Measured on branch `stage-e`. Pooled CI score before the closeout tests: **84.3%** (2,360 killed, 439 survived; CI run 42590488102, `mutation-report.md`). Two columns: the score before the closeout tests, and the score after them where tests were added.

Evidence classes. Java: PIT on unit tests, full mutant set (observed, CI). C++ "before": local `--unit` runs on a 40-site sample, 0 timeouts (observed, local); the CI report's golden-only C++ scores are lower because they do not run the unit tests. Python and Rust "before": CI sample of 40 mutants, unit or golden (observed, CI). Every "after" score is a hand-applied survivor check: each surviving sampled mutant was applied by hand against the new tests (`cpp26/tests/test_mutants_e.cpp` after commit `996527c`, `python/tests/test_mutants_e.py`, `rust/crates/quantforge-core/tests/mutants_e.rs`). It is not a fresh full mutation run. Remaining survivors are classed as equivalent by the author, with reasons in those test files; a second reviewer's sign-off is scheduled (plan 13.2 T).

| Module | Java (PIT) | C++ before | C++ after | Python before | Python after | Rust before | Rust after |
|---|---|---|---|---|---|---|---|
| surfaces_local_vol (E1) | 91.7% | 85.0% | unchanged | 70.0% | 97.5% (39/40) | 85.0% | unchanged |
| heston_slv (E2) | 94.6% | 82.5% | unchanged | 75.0% | 100% (40/40) | 87.5% | unchanged |
| fx_smile (E3) | 81.7% | 85.0% | unchanged | 72.5% | 90.0% (36/40) | 87.5% | unchanged |
| rates_vol (E4) | 91.7% | 66.7% | 97.4% (38/39) | 57.5% | 90.0% (36/40) | 87.5% | unchanged |
| exotics (E5) | 93.9% | 85.0% | unchanged | 65.0% | 97.5% (39/40) | 97.5% | unchanged |
| correlation (E6) | 86.3% | 85.0% | unchanged | 80.0% | unchanged | 90.0% | unchanged |
| garch_varswap_vix (E7) | 82.2% | 75.0% | 82.5% (33/40) | 65.0% | 100% (40/40) | 70.0% | 87.5% (35/40) |
| credit_options (E8) | 90.4% | 60.0% | 92.5% (37/40) | 70.0% | 82.5% (33/40) | 95.0% | unchanged |

Every cell is at or above the 80% target after the closeout tests, on the evidence classes above.

## Stage quality scope

`conformance/quality/stage_e.json` lists the stage E modules per language: the coverage gate (85% line coverage, `.github/workflows/coverage-stage.yml`, weekly and manual), the scope check and the fuzz focus read it, and `conformance/mutation/stages.json` has the same module names under stage E. Entries start as TODO and every tool skips them. When a module lands, replace its TODO with the source path and run `python tools/quality_gate.py --check-config`: it fails if the path matches nothing, a Rust file is outside a workspace member crate, a C++ file is not in `cpp26/CMakeLists.txt`, or a Python file or test is outside what ruff and mutmut cover. Weekly fuzzing draws about half its seeds from `datasets/golden/stage_e` once that folder exists.
