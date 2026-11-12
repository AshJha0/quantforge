# Third-party notices

QuantForge's own code is under the MIT licence in `LICENSE`. This file carries notices that must travel with parts taken from others. `oracle/LICENCES.md` lists every outside tool and how each licence was checked.

## Public market data

No raw market data is in this repository, so these notices apply to anyone who publishes data the recorder fetches, or results that carry it. `oracle/LICENCES.md` has the terms as read, source by source. This is a reading of published terms, not legal advice.

- **SONIA:** "SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0". The Bank's key features page also says a direct licence is needed for some activities, such as redistributing to clients, so raw SONIA data stays local until the Bank has answered.
- **ECB:** cite the European Central Bank as the source, leave values unchanged, and state any modification.
- **New York Fed:** SOFR data "is subject to the Terms of Use posted at newyorkfed.org", and the Bank has no liability. QuantForge is not affiliated with the Federal Reserve Bank of New York. The full notice is in `tools/recorder/sources.json`.
- **Federal Reserve Board:** cite the Board for H.10 and H.15. H.10 is recorded; H.15 is not.
- **US Treasury:** cite the US Department of the Treasury.
- **FRED:** not used. Its terms bar storing content.

## NumPy

The Python implementation depends on NumPy at run time (symmetric eigenvalues and condition numbers); NumPy is installed from PyPI, not vendored. NumPy is under the BSD-3-Clause licence (copyright NumPy Developers), with bundled parts under 0BSD, MIT, Zlib and CC0-1.0; its licence files ship inside the NumPy wheel. `oracle/LICENCES.md` records the version read.

## Joe-Kuo Sobol direction numbers

The first 64 dimensions of `new-joe-kuo-6.21201` are stored in `specifications/01-core/data/sobol-joe-kuo-d6-64.json` and are compiled or copied into all four implementations (`cpp26/src/core/sobol.cpp`, `java25/.../SobolData.java`, `python/quantforge_core/_sobol_data.py`, `rust/crates/quantforge-core/src/sobol.rs`). The licence below was copied on 2026-11-06 from <https://web.maths.unsw.edu.au/~fkuo/sobol/licence>. A binary release must carry this file in its documentation.

```
Copyright (c) 2008, Frances Y. Kuo and Stephen Joe
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.

    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.

    * Neither the names of the copyright holders nor the names of the
      University of New South Wales and the University of Waikato
      and its contributors may be used to endorse or promote products derived
      from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS ``AS IS'' AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
