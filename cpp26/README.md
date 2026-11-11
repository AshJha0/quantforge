# C++26 implementation

Stages A to G of QuantForge (stage G released as v0.7.0): the specs in `specifications/` that `stage-b-followups.md` names, behind the CLI in
`specifications/cli-contract.md`. It is written from the specs alone.

## Layout

| Path | Holds |
|---|---|
| `include/quantforge/core/`, `src/core/` | The library. No CLI knowledge |
| `src/cli/` | Case parsing (`dispatch.cpp`), shared input readers (`readers.inc`), one `ops_<domain>.inc` per verb domain, each ending with its `<domain>_ops` array, and the test function registry. The verb registry in `dispatch.cpp` lists the domain arrays; dispatch and the `operations` command are generated from it |
| `tests/` | Catch2 tests, from the specs' worked examples and numeric targets |
| `SPEC_QUESTIONS.md` | Golden cases that disagree with a spec, and gaps in the specs |

The other folders in `include/quantforge/` are empty placeholders for later stages. There are no dependencies beyond the standard library, apart from Catch2 for tests. The Sobol table is compiled in
with `#embed`, so no command reads a file.

## Stage G modules

| File | Holds | Spec |
|---|---|---|
| `core/shortrate.{hpp,cpp}` | Vasicek, CIR and Hull-White bonds and bond options (noncentral chi-square started at the Poisson mode, upper tails for CIR puts), Jamshidian swaptions (bracket `[-1, 1]`, G-29), caps and floors, Hull-White sigma calibration, the pinned G-18 scheme for Bermudan swaptions and callable bonds, G2++ (series below `max(a, b) tau = 0.1`, G-33), closed-form swap EE and CVA, and the MC Greeks of Q9 part 1 | `04-pricing/short-rate-models.md`, `06-risk/mc-greeks.md`, `06-risk/xva-exposure.md` |
| `core/aad_ladder.cpp` | Q3b: reverse-mode ladder of the G-18 Bermudan scheme with respect to every curve discount factor, `a` and `sigma`. Hand-written adjoint: the forward pass stores each step; the reverse pass solves the transposed tridiagonal system per step and maps coefficient adjoints to the parameters through forward-mode gradients of `h`, `alpha(t)` and the exercise values. The unit test prints the G-9 cost ratio (price plus ladder over one price; pass at 5 or less) | `06-risk/aad-core.md` |
| `core/lmm.{hpp,cpp}` | LMM caplets and Rebonato swaptions on the abcd volatility (covariance by composite 20-point Gauss-Legendre), and the simulated terminal-measure LMM used by the G-26 caplet acceptance test | `04-pricing/lmm.md` |
| `cli/ops_shortrate.inc` | CLI side of the short-rate, G2++, LMM, MC Greeks and exposure operations, including the G-31 limits (combined grid work `nx x steps <= 5e8`) | `cli-contract.md`, "Stage G operations" |
| `cli/ops_xva.inc` | xVA on given paths: collateralised exposure (CSA, MTA, MPoR), CVA, DVA, FVA with the overlap rule, MVA, KVA, SIMM-style IR delta, Hull-White wrong-way risk; the model-reserve dispersion statistic | `06-risk/xva-framework.md`, `06-risk/model-reserve.md` |
| `cli/ops_risk_gb.inc`, `cli/ops_frtb_gb.inc` | Stage F carry-overs landed in stage G: inflation01, dividend and borrow, correlation sensitivities; reverse stress, limits, concentration, liquidity-adjusted VaR, horizon volatility; FRTB FX, equity, CSR and commodity delta, vega and curvature (one sensitivities-based engine with the MAR21.6 scenarios) | `06-risk/f3-sensitivities.md`, `portfolio-risk-tools.md`, `frtb-sa-fx-equity.md`, `frtb-sa-vega-curvature.md` |

Property tests for these waves are in `tests/test_stage_g.cpp`: the acceptance checks of each spec (R9 barrier MC, G-10 report and G-10b gate, LMM caplets against simulation, Q3b ladder against Richardson bumps and its cost ratio), plus parity and limit cases. Bounds on the G-18 scheme compare with the scheme's own value of the bounding product (G-28).

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
cmake -S . -B build-clang -G Ninja -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_CXX_COMPILER_TARGET=x86_64-w64-mingw32 "-DCMAKE_CXX_FLAGS=--sysroot=<mingw64 folder, as C:/...>" -DCMAKE_CXX_STANDARD_LIBRARIES=-lwinpthread
```

## Conformance

From the repository root:

```bash
python conformance/runner/runner.py --impl cpp
```

## Toolchains

Checked with GCC 16.2 and Clang 23.1 on Windows (MinGW-w64 UCRT, libstdc++). Beyond C++20 the code relies on
`#embed` only. Number parsing uses `strtod`, and printing `std::to_chars`. libc++ has not been
tried here. CI's Clang job builds with it, and passed on stage A; it has not yet run stage B.

Windows Application Control blocks freshly built Clang binaries at times, so Clang conformance relies on CI. Do not change that policy; retry later. When it was not blocked, on 2026-11-06 at commit `13d9871`, a local Clang 23.1.5 build with libstdc++ passed all 4,731 golden cases.
