# Oracle licences

All are used in tests only. Nothing here is linked into, or shipped with, an implementation.

| Tool or data | Version | Licence | How checked |
|---|---|---|---|
| QuantLib (Python wheel) | 1.44 | BSD-3-Clause | PyPI metadata, 2026-11-06 |
| OpenGamma Strata | 2.12.78 | Apache-2.0 | Licence file in the jar |
| mpmath, NumPy, SciPy, PyYAML, jsonschema, tzdata | `python/uv.lock` | Believed BSD, MIT or Apache-2.0 | Not read per package. To confirm in a licence scan |
| Joe-Kuo Sobol direction numbers | new-joe-kuo-6.21201 | BSD-style | The authors' page says so. Their notice must travel with the 64-dimension extract: copy it in before any public release |
| `rand_xoshiro` 0.7.0 test vectors | 0.7.0 | Believed MIT or Apache-2.0 | Not read. Only numeric vectors are copied |

## Not yet used

| Tool | Status |
|---|---|
| ISDA CDS Standard Model | Published under the "ISDA CDS Standard Model Public License"; [cdsmodel.com](https://cdsmodel.com/) is described as allowing change and redistribution. The licence text has not been read. Read it before stage D |
| Open Source Risk Engine | Believed to be modified BSD. Not verified. Check before stage G |
| ISDA SIMM | Believed to be proprietary and licensed by ISDA. Not verified. Plan: own parameters, "SIMM-style", no ISDA parameters and no compliance claim |
