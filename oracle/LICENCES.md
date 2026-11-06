# Oracle licences

Outside tools and data used by QuantForge. Two rows are not test-only, and say so: the Sobol direction numbers and NumPy reach an implementation. Everything else is used to produce or check results and is not linked into, or shipped with, an implementation.

Oracle packages were read from installed metadata on 2026-11-06; `oracle/python/uv.lock` holds the exact set. This is metadata, not a legal review.

| Tool or data | Version | Licence | How checked |
|---|---|---|---|
| QuantLib (Python wheel) | 1.44 | BSD-3-Clause | Installed metadata |
| OpenGamma Strata | 2.12.78 | Apache-2.0 | Licence file in the jar. `oracle/strata/out/` holds its computed output, not its code |
| mpmath | 1.4.1 | BSD-3-Clause | Installed metadata |
| NumPy | 2.5.4 in the oracle | BSD-3-Clause, with 0BSD, MIT, Zlib, CC0-1.0 parts | Installed metadata. **Also a runtime dependency of the Python implementation**, for symmetric eigenvalues and condition numbers; it is not vendored here |
| SciPy | 1.18.1 | BSD | Installed metadata |
| PyYAML, jsonschema, attrs, referencing, rpds-py, jsonschema-specifications | `oracle/python/uv.lock` | MIT | Installed metadata |
| tzdata | 2026.6 | Apache-2.0 | Installed metadata |
| typing_extensions | 4.16.0 | PSF-2.0 | Installed metadata |
| Joe-Kuo Sobol direction numbers | new-joe-kuo-6.21201 | BSD-style | Licence text read on the authors' site. **Copied into all four implementations**; the notice is in `THIRD_PARTY_NOTICES.md` and must travel with source and binaries |
| `rand_xoshiro` 0.7.0 test vectors | 0.7.0 | Believed MIT or Apache-2.0 | Not read. Only numeric vectors are copied |

Test and build tools, not shipped: JUnit 5, PIT, Catch2 v3.16.1, pytest, hypothesis, ruff, mypy, mutmut, cargo-mutants. Their licences were not read for this table. The rust implementation has no third-party crates.

## Public data sources

From the stage B data survey of 2026-11-06, which is a reading of published terms and not legal advice. No raw data is committed. `tools/recorder/sources.json` is the recorder's manifest; it holds only the three recorded sources and still lags this table on the SONIA and ECB rows.

| Source | Use | Terms as read | Raw redistribution |
|---|---|---|---|
| Bank of England SONIA (`IUDSOIA`) | Recorded | Open Government Licence v3.0, with its own attribution line. **Conflict:** the SONIA key features page says a direct licence is needed for activities such as redistributing to clients. How that fits with the OGL is not confirmed | No: local only until the Bank answers. The owner would ask |
| ECB reference rates | Recorded | Free reuse, commercial or not, if the source is quoted and values are unchanged; any modification must be stated. Third-party data is excluded | Allowed on those conditions |
| ECB €STR | Not recorded yet | As above. The ECB does not charge for it or license its use | Allowed on those conditions |
| ECB fitted yield curves | Not recorded | As above, but the effect of MTS inputs is not confirmed | Not confirmed |
| US Treasury par yields | Recorded | Believed a US government work. Treasury's own terms not found | Believed yes, unconfirmed |
| New York Fed SOFR | Not recorded yet | May be copied and distributed, with the required notice and the same terms passed on | Allowed, with the notice in `THIRD_PARTY_NOTICES.md` |
| Federal Reserve H.10, H.15 | Not recorded yet | Public domain, citation requested, non-Board material excepted | Allowed with citation |
| Bank of England FX spot and forwards (`XUDL*`, `XUDLDS*`, `XUDLDF*`) | Not recorded | "Selected exchange rate data" is excluded from the licence, and which series is not published. This may limit local use too | No, until the Bank confirms. Owner decides |
| Bank of England fitted curves, OIS included | Not recorded | Storage allowed; OGL cover not confirmed, as inputs come from Bloomberg and Tradeweb | No: local only |
| DTCC swap repository data | Not used | Site terms not read | No: owner reads the terms first |
| UK DMO | Not used | Terms not read | No, until read |
| **FRED** | **Dropped** | Terms bar storing, caching or archiving content, and the API needs a key | Do not record, do not use |
| CME, ICE | Not usable | Personal non-commercial use only; CME from search snippets only | No |

## Not yet used

| Tool | Status |
|---|---|
| ISDA CDS Standard Model | Published under the "ISDA CDS Standard Model Public License"; [cdsmodel.com](https://cdsmodel.com/) is described as allowing change and redistribution. The licence text has not been read. Read it before stage D |
| Open Source Risk Engine | Believed to be modified BSD. Not verified. Check before stage G |
| ISDA SIMM | Believed to be proprietary and licensed by ISDA. Not verified. Plan: own parameters, "SIMM-style", no ISDA parameters and no compliance claim |
