# C++26 implementation

Configure with a compiler that supports the required C++26 subset:

```bash
cmake -S . -B build -DCMAKE_CXX_COMPILER=<supported-cxx26-compiler>
cmake --build build
ctest --test-dir build --output-on-failure
```

The initial CI compiler is a provisional baseline and may not support every C++26 facility. Keep the portable baseline small; feature-test optional library/language facilities and document the compiler matrix before relying on them.
