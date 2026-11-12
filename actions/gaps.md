# Recorder gaps

Business days Monday to Friday up to 2026-11-12, holidays from code/tools/recorder/holidays.txt. A gap is a day with no successful recording in any log given.

| Series | From | Expected | Missing | Longest run of unchanged bytes |
|---|---|---:|---|---:|
| recorder/bls-cpi-u-nsa | 2026-11-09 | 3 | none | 0 |
| recorder/boe-sonia | 2026-11-07 | 3 | none | 0 |
| recorder/cftc-cot-disaggregated | 2026-11-07 | 3 | none | 2 |
| recorder/ecb-aaa-yield-curve | 2026-11-07 | 3 | none | 0 |
| recorder/ecb-estr | 2026-11-07 | 3 | 2026-11-10 | 0 |
| recorder/ecb-reference-rates | 2026-11-07 | 3 | none | 0 |
| recorder/eia-ng-bulk | 2026-11-07 | 3 | none | 2 |
| recorder/eurostat-hicp | 2026-11-07 | 3 | none | 2 |
| recorder/fiscaldata-treasury-auctions | 2026-11-09 | 3 | none | 2 |
| recorder/frb-h10 | 2026-11-07 | 3 | none | 2 |
| recorder/nyfed-bgcr | 2026-11-07 | 3 | none | 0 |
| recorder/nyfed-sofr | 2026-11-07 | 3 | none | 0 |
| recorder/nyfed-tgcr | 2026-11-07 | 3 | none | 0 |
| recorder/ons-chaw | 2026-11-07 | 3 | none | 2 |
| recorder/ons-d7bt | 2026-11-07 | 3 | none | 2 |
| recorder/ons-l522 | 2026-11-07 | 3 | none | 2 |
| recorder/us-treasury-bill-rates | 2026-11-09 | 3 | none | 0 |
| recorder/us-treasury-par-yields | 2026-11-07 | 3 | none | 0 |
| recorder/us-treasury-real-yields | 2026-11-09 | 3 | none | 0 |
| study/R3-01 | 2026-11-09 | 3 | none | 0 |
| study/R3-02 | 2026-11-09 | 3 | none | 0 |
| study/R3-03 | 2026-11-09 | 3 | none | 0 |

Prereg inputs and study rows missing on a business day (any age fails): none

Recent gaps (last 3 business days): recorder/ecb-estr 2026-11-10
