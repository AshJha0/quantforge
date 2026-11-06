# C++26 implementation

Stage A of QuantForge: every spec in `specifications/01-core/`, behind the CLI in
`specifications/cli-contract.md`. It is written from the specs alone.

## Layout

| Path | Holds |
|---|---|
| `include/quantforge/core/`, `src/core/` | The library. No CLI knowledge |
| `src/cli/` | Case parsing, the operation table, and the test function registry |
| `tests/` | Catch2 tests, from the specs' worked examples and numeric targets |
| `SPEC_QUESTIONS.md` | Golden cases that disagree with a spec, and gaps in the specs |

There are no dependencies beyond the standard library, apart from Catch2 for tests. The Sobol table is compiled in
with `#embed`, so no command reads a file.

## Build

```bash
cmake -S . -B build -G Ninja -DCMAKE_CXX_COMPILER=<g++ or clang++>
cmake --build build
ctest --test-dir build --output-on-failure
```

The build sets `-ffp-contract=off`, as the contract requires. Never add `-ffast-math`.

Sanitizers, on Linux: add `-DQF_SANITIZE=address,undefined,float-cast-overflow`. The last one matters here, because `undefined` alone does not check a double converted to an integer that cannot hold it.

Clang on Windows, using the WinLibs headers and libraries:

```bash
cmake -S . -B build-clang -G Ninja -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_CXX_COMPILER_TARGET=x86_64-w64-mingw32 "-DCMAKE_CXX_FLAGS=--sysroot=<mingw64 folder>" -DCMAKE_CXX_STANDARD_LIBRARIES=-lwinpthread
```

## Conformance

From the repository root:

```bash
python conformance/runner/runner.py --impl cpp
```

## Toolchains

Checked with GCC 16.2 and Clang 23.1 on Windows (MinGW-w64 UCRT, libstdc++). Beyond C++20 the code relies on
`#embed` only. Number parsing uses `strtod`, and printing `std::to_chars`. libc++ has not been
tried here; CI's Clang job will be its first run.
