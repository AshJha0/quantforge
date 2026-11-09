# Contributing

QuantForge is one set of specifications implemented four times. A change usually touches a spec, the oracle that
produces expected values, and up to four implementations. This page says how to set each one up, how the checks fit
together, and how work is planned.

## Check your machine

```bash
python tools/doctor.py              # all four toolchains
python tools/doctor.py --only rust  # one language
```

It reads the pinned versions from the repository and prints one line per tool. It exits 1 and lists every problem if
anything is missing or at the wrong version. The free devcontainer in `.devcontainer/` has all four toolchains and
runs the doctor after it is built; it starts from the same GCC 16.2 image as CI's C++ job.

## Per-language setup

Each block runs from the repository root and ends with that language's unit tests.

**Python** (3.15.2 from `python/.python-version`, managed by [uv](https://docs.astral.sh/uv/)):

```bash
uv python install 3.15.2
uv sync --locked --project python
cd python && uv run ruff check . && uv run pytest
```

**Rust** (1.99.1 from `rust/rust-toolchain.toml`, 2024 edition; rustup installs the pinned toolchain on first use):

```bash
cd rust
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

**Java** (Temurin JDK 25.0.5, as in `.github/workflows/java25.yml`, and Maven 3.9 or later):

```bash
cd java25
mvn -B test
mvn -B -DskipTests package   # the CLI jar the conformance runner calls
```

**C++** (C++26: GCC 16.2, or Clang 23 with libc++; CMake 3.25 or later; Ninja):

```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build cpp26/build --parallel
ctest --test-dir cpp26/build --output-on-failure
```

The oracle has its own Python, 3.12, kept apart from the implementation's 3.15 on purpose (`oracle/README.md`).

## How the checks fit together

**Goldens.** `datasets/golden/<stage>/*.json` hold the cases every language must answer: inputs, the expected status
and outputs or error code, a tolerance class from `conformance/tolerances/policy.yaml`, and `verified_by`, the
sources that agreed on the value. Goldens are generated, never edited by hand.

**The oracle.** `oracle/` writes the goldens from outside libraries (QuantLib, Strata, mpmath and others), exact
arithmetic and hand derivations. No implementation may import it, and no golden value may come from one of the four
implementations. A generator stops when its sources disagree, unless the difference is recorded in the spec.
`oracle/README.md` says how to regenerate everything (about three minutes). A case whose only source is by the spec's
author is self-assessment, and is labelled as such.

**The conformance runner.** `conformance/runner/runner.py` knows no finance. It strips the answers, sends each case to
a language's CLI (`conformance/runner/implementations.json` says how each CLI is started), and compares the reply
within the case's tolerance:

```bash
python conformance/runner/runner.py --impl rust            # or java, cpp, python
python conformance/runner/runner.py --impl rust --suite daycount
python conformance/runner/batch_check.py --impl rust       # batch-mode stream fixtures
```

Build the CLI first; `COOKBOOK.md` has the four build commands. Agreement between languages proves nothing by itself:
a build passes when it matches the oracle.

**Mutation and quality gates.** `conformance/mutation/` and `tools/quality_gate.py` check that the tests catch planted
faults. CI runs them per stage.

## How work is planned

There are no GitHub issues to pick from. Work is planned in stages (`ROADMAP.md`), and each stage has a plan with
item IDs and acceptance tests, kept outside this repository, plus handovers in `program/`. A pull request names the
plan items it closes (for example "E5") and shows the evidence their acceptance tests ask for. Each stage ends in one
pull request and one tag. To propose work, open a draft pull request that says which
stage it belongs to.

## Workflow for a change

1. Read the relevant spec under `specifications/` and any ADRs.
2. Add or update tests before changing model behaviour.
3. Implement in the target language from the spec alone. No language is a reference, and expected values come only
   from `oracle/`.
4. Run formatting, static analysis, unit tests and the conformance suites you touched.
5. Add benchmark evidence when performance is affected.
6. Update documentation, limitations and `CHANGELOG.md`. A release tag (`vMAJOR.MINOR.PATCH`) fails in
   `.github/workflows/release.yml` if the changelog has no section for that version.

## Pull request checklist
- [ ] Mathematical specification reviewed and unchanged or updated.
- [ ] Inputs, outputs, units and conventions are explicit.
- [ ] Normal, boundary, invalid and numerical stress cases tested.
- [ ] Determinism and reproducibility verified.
- [ ] Cross-language goldens regenerated through the oracle where applicable.
- [ ] CLI changes pass `python conformance/runner/batch_check.py --impl <lang>` as well as the golden runner.
- [ ] Independent expected values or external reference evidence supplied.
- [ ] Performance impact measured where relevant.
- [ ] Limitations and unsupported cases documented.
- [ ] No licensed or sensitive market data committed without permission.

## Definition of done
A feature is not complete because the happy-path example works. It must meet its domain's acceptance criteria and
`program/definition-of-done.md`.
