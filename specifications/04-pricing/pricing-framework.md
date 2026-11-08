# Pricing framework

Spec version 1.0.0. Status: Implemented, not Validated.

Five separate things meet in a valuation:

| Part | Holds | Stage B examples |
|---|---|---|
| Instrument | The contract terms only, no market data | `trade` in each operation |
| Product model | Turns terms into dated cashflows or legs | OIS periods, swap legs |
| Market data | Curves and spot, frozen | `curve`, `spot`, `snapshot_id` |
| Pricing model | Combines them | Discounting |
| Valuation result | The answer and where it came from | `valuation` |

Each language keeps these apart in its API. Only the JSON below is conformance.

## Valuation result

Schema: `datasets/schemas/valuation.schema.json`.

| Key | Meaning |
|---|---|
| `pv` | Real, in `currency`, sign from the holder's side |
| `currency` | ISO code |
| `model` | Pricing model name, set in each spec |
| `data_version` | The `snapshot_id` given, or `null` |
| `conventions` | Convention id |
| `as_of` | Curve date |

Sensitivities are separate outputs beside `valuation`, such as `fx_delta`, or come from `risk.*`.

## Acceptance

Via each operation. Strings are exact; `pv` uses the case's limit.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] No external convention: the valuation record is this project's contract
- [S2] IETF RFC 8259, *The JavaScript Object Notation (JSON) Data Interchange Format*, 2017 (opened 2026-11-07)
