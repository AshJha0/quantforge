# Oracle licences

Outside tools and data used by QuantForge. Two rows are not test-only, and say so: the Sobol direction numbers and NumPy reach an implementation. Everything else is used to produce or check results and is not linked into, or shipped with, an implementation.

Oracle packages were read from installed metadata on 2026-11-06; `oracle/python/uv.lock` holds the exact set. This is metadata, not a legal review.

| Tool or data | Version | Licence | How checked |
|---|---|---|---|
| QuantLib (Python wheel) | 1.44 | BSD-3-Clause | Installed metadata |
| OpenGamma Strata | 2.12.78 | Apache-2.0 | Licence file in the jar. `oracle/strata/out/` holds its computed output, not its code |
| mpmath | 1.4.1 | BSD-3-Clause | Installed metadata |
| NumPy | 2.5.4 in the oracle | BSD-3-Clause, with 0BSD, MIT, Zlib, CC0-1.0 parts | Installed metadata. **Also a runtime dependency of the Python implementation**, for symmetric eigenvalues; it is not vendored here |
| SciPy | 1.18.1 | BSD | Installed metadata |
| PyYAML, jsonschema, attrs, referencing, rpds-py, jsonschema-specifications | `oracle/python/uv.lock` | MIT | Installed metadata |
| tzdata | 2026.6 | Apache-2.0 | Installed metadata |
| typing_extensions | 4.16.0 | PSF-2.0 | Installed metadata |
| Joe-Kuo Sobol direction numbers | new-joe-kuo-6.21201 | BSD-style | Licence text read on the authors' site. **Copied into all four implementations**; the notice is in `THIRD_PARTY_NOTICES.md` and must travel with source and binaries |
| `rand_xoshiro` 0.7.0 test vectors | 0.7.0 | Believed MIT or Apache-2.0 | Not read. Only numeric vectors are copied |

Test and build tools, not shipped: JUnit 5, PIT, Catch2 v3.16.1, pytest, hypothesis, ruff, mypy, mutmut, cargo-mutants. Their licences were not read for this table. The rust implementation has no third-party crates.

## Not yet used

| Tool | Status |
|---|---|
| ISDA CDS Standard Model | Published under the "ISDA CDS Standard Model Public License"; [cdsmodel.com](https://cdsmodel.com/) is described as allowing change and redistribution. The licence text has not been read. Read it before stage D |
| Open Source Risk Engine | Believed to be modified BSD. Not verified. Check before stage G |
| ISDA SIMM | Believed to be proprietary and licensed by ISDA. Not verified. Plan: own parameters, "SIMM-style", no ISDA parameters and no compliance claim |
