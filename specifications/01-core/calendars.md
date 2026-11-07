# Calendars and business-day rules

Spec version 1.1.0 (R1: Good Friday early closes, ruling R1-6). Status: Specified.

All calendars are valid for years 2000 to 2099. A date outside is `E_DATE_RANGE`. Saturdays and
Sundays are non-business days in every calendar. An unknown calendar or convention is `E_SCHEMA`.

## Easter

Use the anonymous Gregorian algorithm (Meeus, Jones, Butcher). Integer division throughout:

```
a=y%19  b=y/100  c=y%100  d=b/4  e=b%4  f=(b+8)/25  g=(b-f+1)/3
h=(19a+b-d-g+15)%30  i=c/4  k=c%4  l=(32+2e+2i-h-k)%7  m=(a+11h+22l)/451
month=(h+l-7m+114)/31  day=(h+l-7m+114)%31+1
```

Good Friday is Easter Sunday minus 2 days. Easter Monday is plus 1.

## `GBLO`: England and Wales bank holidays

- New Year: 1 January, or the next Monday if it falls on a weekend.
- Good Friday, Easter Monday.
- Early May: first Monday of May. In 2020 it is 8 May instead.
- Spring: last Monday of May. Instead: 2002-06-04, 2012-06-04, 2022-06-02.
- Summer: last Monday of August.
- Christmas and Boxing Day: by the weekday of 25 December: Saturday gives 27 and 28; Sunday gives
  26 and 27; Friday gives 25 and 28; otherwise 25 and 26.
- One-offs: 2002-06-03, 2011-04-29, 2012-06-05, 2022-06-03, 2022-09-19, 2023-05-08.

## `EUTA`: TARGET

1 January, Good Friday, Easter Monday, 1 May, 25 December, 26 December, no substitution.
One-off: 2001-12-31.

## `USGS`: US government securities

- New Year: 1 January, or Monday 2 January if a Sunday. If a Saturday, there is no holiday in lieu.
- Martin Luther King Day: third Monday of January. Presidents' Day: third Monday of February.
- Good Friday, except in years when SIFMA recommended an early close instead of a full close: 2007, 2010, 2012, 2015, 2021, 2023 and 2026. The market is open on an early close, so it is a business day for settlement, accrual and schedules (ruling R1-6). Sources per year: `datasets/calendar_provenance.json`.
- Memorial Day: last Monday of May.
- Juneteenth: 19 June from 2022 on, Friday if a Saturday, Monday if a Sunday.
- Independence Day: 4 July, Friday if a Saturday, Monday if a Sunday.
- Labor Day: first Monday of September. Columbus Day: second Monday of October.
- Veterans Day: 11 November, Monday if a Sunday. If a Saturday, no holiday in lieu.
- Thanksgiving: fourth Thursday of November.
- Christmas: 25 December, Friday if a Saturday, Monday if a Sunday.
- One-offs: 2004-06-11, 2012-10-30, 2018-12-05.

Future one-offs cannot be known. A new one changes this spec's version, and so the golden files.
Sources, check dates and the expiry test: `calendar-provenance.md`.

## Business-day conventions

`UNADJUSTED`, `FOLLOWING`, `PRECEDING`, `MODIFIED_FOLLOWING`, `MODIFIED_PRECEDING`. The modified forms
take the plain result unless it leaves the month, and then search the other way.

## Operations

| Operation | Inputs | Output |
|---|---|---|
| `core.calendar.is_business_day` | `calendar`, `date` | `is_business_day` (boolean) |
| `core.calendar.holidays` | `calendar`, `year` | `dates`: weekday holidays in the year, ascending |
| `core.calendar.adjust` | `calendar`, `date`, `convention` | `date` |
| `core.calendar.add_business_days` | `calendar`, `date`, `days` (signed integer) | `date` |
| `core.calendar.business_days_between` | `calendar`, `start`, `end` | `count` |
| `core.calendar.add_tenor` | `calendar`, `date`, `tenor`, `convention`, `end_of_month` (boolean) | `date` |

`add_business_days`: if `days` is 0, return `FOLLOWING`-adjusted `date`. Otherwise step one calendar day
at a time in the sign of `days`, counting only business days, until `|days|` are counted. The
start date is not counted, and need not be a business day.

`business_days_between`: count in `[start, end)`. `end` before `start` is `E_DATE_ORDER`.

`add_tenor`: `tenor` matches `^[1-9][0-9]{0,3}[DWMY]$`; anything else is `E_SCHEMA`.
- `D` and `W` add calendar days (7 per `W`), then apply `convention`.
- `M` and `Y` add months (12 per `Y`). If the day does not exist in the target month, use the month's
  last day. Call that `t`. Then:
  - `end_of_month` true, `convention` not `UNADJUSTED`, and `date` is on or after the last business day of its
    month: the result is the last business day of the target month. `date` itself need not be a business day, so
    Saturday 30 March 2024 qualifies, as the last business day of that month is the 28th.
  - `end_of_month` true, `convention` `UNADJUSTED`, and `date` is the last calendar day of its month: the result is
    the last calendar day of the target month.
  - Otherwise apply `convention` to `t`.

  This is QuantLib's rule (`Calendar::advance` and `Calendar::isEndOfMonth`, version 1.44), checked on every day
  from 2021 to 2026.

## Acceptance

Class `date_and_convention`, exact. Oracle: the rules above, checked for every weekday from 2000 to
2050 against QuantLib and Strata.

Measured result: `GBLO` and `EUTA` match both libraries on every date. `USGS` matches Strata except
2004-06-11 (QuantLib has it, Strata does not; kept because the market closure is documented, not
confirmed against a primary source). Since ruling R1-6 (2026-11-07), `USGS` matches QuantLib on every date to 2026, including the seven Good Friday early closes. After 2026 it differs on Good Fridays that fall on a jobs-report Friday (2034, 2037, 2042, 2045, 2048): QuantLib projects an early close, while here a future Good Friday is a holiday until SIFMA publishes. Strata treats every Good Friday as a holiday, so it differs on the seven early-close years.

No early closes are modelled. A partial session counts as a full business day.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Meeus, J., *Astronomical Algorithms*, Willmann-Bell, 1991, chapter on the date of Easter (the anonymous Gregorian algorithm) (not opened)
- [S2] UK *Banking and Financial Dealings Act 1971*, Schedule 1, and the annual UK Government bank-holiday proclamations (`GBLO`) (not opened)
- [S3] European Central Bank, TARGET2 / T2 closing days (`EUTA`) (not opened)
- [S4] SIFMA, *Holiday Schedule* recommendations for US bond markets (`USGS`) (not opened)
- [S5] ISDA, *2006 ISDA Definitions*, Section 4.12 (Business Day Convention) and Section 1.4 (Business Day) (not opened)
