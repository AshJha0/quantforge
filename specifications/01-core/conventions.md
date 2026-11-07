# Convention registry

Spec version 1.0.0. Status: Implemented, not Validated.

A market convention is data, kept in one place. All stage B operations read it.

## `core.conventions.lookup`

Input: `id`. Output: the record below, with the keys shown. Unknown `id`: `E_SCHEMA`.

| `id` | Keys |
|---|---|
| `SONIA` | `kind` `OVERNIGHT`, `currency` `GBP`, `day_count` `ACT_365F`, `calendar` `GBLO`, `spot_lag` 0, `payment_lag` 0, `fixed_months` 12, `fixed_day_count` `ACT_365F`, `business_day_convention` `MODIFIED_FOLLOWING` |
| `SOFR` | `kind` `OVERNIGHT`, `currency` `USD`, `day_count` `ACT_360`, `calendar` `USGS`, `spot_lag` 2, `payment_lag` 2, `fixed_months` 12, `fixed_day_count` `ACT_360`, `business_day_convention` `MODIFIED_FOLLOWING` |
| `ESTR` | `kind` `OVERNIGHT`, `currency` `EUR`, `day_count` `ACT_360`, `calendar` `EUTA`, `spot_lag` 2, `payment_lag` 2, `fixed_months` 12, `fixed_day_count` `ACT_360`, `business_day_convention` `MODIFIED_FOLLOWING`. Stage D |
| `USD-TERM-3M` | `kind` `TERM`, `currency` `USD`, `day_count` `ACT_360`, `calendar` `USGS`, `spot_lag` 2, `months` 3, `fixed_months` 12, `fixed_day_count` `THIRTY_360_BOND`, `business_day_convention` `MODIFIED_FOLLOWING` |
| `GBPUSD` | `kind` `FX`, `base` `GBP`, `quote` `USD`, `spot_lag` 2, `calendars` `[GBLO, USGS]`, `pip` 0.0001 |
| `EURUSD` | `kind` `FX`, `base` `EUR`, `quote` `USD`, `spot_lag` 2, `calendars` `[EUTA, USGS]`, `pip` 0.0001 |

SONIA, SOFR and ESTR match Strata's `GBP-FIXED-1Y-SONIA-OIS`, `USD-FIXED-1Y-SOFR-OIS` and `EUR-FIXED-1Y-ESTR-OIS`, read from its source (ESTR: Strata 2.12.78 bytecode, spot lag 2 and payment lag 2). `USD-TERM-3M` is synthetic: it exists to test multi-curve code now that the IBOR indices it resembles have ended, and no market index is implied. The FX records are standard practice but rest on no outside file.

Spot lags count business days. The FX rule is in `02-curves/fx.md`.

## Acceptance

Exact.
