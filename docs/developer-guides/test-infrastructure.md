# Test infrastructure

None of these workflows has run on GitHub yet: the remote had no commits when this was written, so every result so far is local, on Windows.

CI minutes are capped at about 2,000 a month with a hard stop, so pull-request workflows run only when their paths change. Everything runs on Linux.

| Workflow | Runs on | What it does |
|---|---|---|
| `conformance.yml` | Pull request, push to main, manual | Builds each CLI and runs all golden cases, and tests the runner itself |
| `java25.yml`, `cpp26.yml`, `python.yml`, `rust.yml` | Pull request and push to main, own paths only | Each language's own build and unit tests. `cpp26.yml` has GCC and Clang jobs |
| `sanitizers.yml` | Same, C++ paths only | Unit tests and golden cases under ASan and UBSan |
| `fuzz.yml` | Monday, manual | Three minutes of fuzzing per language; C++ uses the sanitizer build |
| `mutation.yml` | Manual only | One language and one target per run |
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

Java, Python and Rust scores measure unit tests only, not the golden cases, so a survivor there may still be caught by conformance.
