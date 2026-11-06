# Toolchain policy

- Python CI uses the latest stable Python 3.x. Pin exact Python and dependency versions for reproducible published research runs.
- C++ targets C++26. Maintain a compiler/standard-library feature matrix; CI's compiler choice is provisional and must be reviewed against actual feature support.
- Java targets JDK 25.
- Rust uses the latest stable compiler with edition 2024. Record `rustc --version` and `cargo --version` in release evidence.
- For releases, capture compiler/runtime versions, dependency lockfiles, OS and build flags.
