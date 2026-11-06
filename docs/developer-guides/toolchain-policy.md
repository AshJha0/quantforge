# Toolchain policy

Versions are pinned so that a result can be reproduced. The pins, unchanged by stage B:

| Part | Pin | Where |
|---|---|---|
| Java | JDK 25.0.5 | `java25/pom.xml`, workflows |
| C++ | C++26, GCC 16.2, Clang; Catch2 v3.16.1 for tests | `cpp26/CMakeLists.txt`, workflows |
| Python implementation | 3.15.2, dependencies locked | `python/.python-version`, `python/uv.lock` |
| Oracle | Python 3.12, QuantLib 1.44, Strata 2.12.78 | `oracle/python/`, `oracle/strata/pom.xml` |
| Rust | 1.99.1, edition 2024 | `rust/rust-toolchain.toml` |
| CI actions | Commit SHAs | `.github/workflows/` |

ADR-0008 asks for a C++ feature matrix. Today it is short: beyond C++20 the code uses `#embed` only, as `cpp26/README.md` records.

For releases, capture compiler and runtime versions, lockfiles, OS and build flags.
