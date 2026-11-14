# Wave 2, C++ build notes

Spec doubts and choices made in `cpp26/src/core/research_w2.cpp` (stage J wave 2).

- `risk.contrib.euler` and `risk.backtest.es_z2` sit outside the `research.` prefix, so the J-20 bypass of the general per-array limit in `dispatch.cpp` now names them explicitly (J-W2-14 says their page limits replace the general one). A prefix-free rule (for example a set of stage J verbs in one table) would be less fragile; left to the coordinator.
- J-W2-14 "assets 500" is applied to the Ledoit-Wolf return width as well (the ruling lists estimation); the page itself names only rows and cells for Ledoit-Wolf.
- Mean-variance length checks: bounds of the wrong length are `E_INPUT` before `gamma` (the page's order: shapes, then domain).
- Baum-Welch row checks use the page's `1e-9` tolerance; `initial` produced by the M-step is not re-checked.
