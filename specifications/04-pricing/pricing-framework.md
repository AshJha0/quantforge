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
