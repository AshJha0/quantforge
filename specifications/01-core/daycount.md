# Day counts

Spec version 1.0.0. Status: Specified.

A day count turns two dates into a year fraction. Different markets count differently, and the
differences matter most at month ends, in leap years and over 29 February.

## Operation `core.daycount.year_fraction`

Inputs: `convention` (enum below), `start`, `end` (dates). Conditional inputs:

| Input | Needed by | Meaning |
|---|---|---|
| `frequency` | `ACT_ACT_ICMA`, `ACT_365L` | Coupons per year: 1, 2, 3, 4, 6 or 12 |
| `ref_start`, `ref_end` | `ACT_ACT_ICMA` | The notional coupon period holding the accrual |
| `termination` | `THIRTY_E_360_ISDA` | Final date of the instrument |
| `calendar` | `BUS_252` | Calendar id from `calendars.md` |

Output: `year_fraction`.

Checks, in order:
1. A needed conditional input is absent, or `frequency` is not listed: `E_SCHEMA`.
2. `end` before `start`: `E_DATE_ORDER`. Year fractions here are never negative; a caller wanting a
   signed value swaps the dates and negates, which is its own decision because 30/360 is not
   symmetric.
3. `ACT_ACT_ICMA` only: `ref_end <= ref_start`, or `start < ref_start`, or `end > ref_end`: `E_INPUT`.
   A long stub spans more than one notional period, so the caller splits it and adds the parts.
   Schedules that do this are a stage B item.

`start == end` gives 0 for every convention.

## Definitions

`days` is the number of calendar days from `start` to `end`: the start is counted, the end is not.
`leap(y)` is the Gregorian rule. `D(y)` is 366 in a leap year, otherwise 365.

| Convention | Year fraction |
|---|---|
| `ACT_360` | `days / 360` |
| `ACT_365F` | `days / 365` |
| `ACT_364` | `days / 364` |
| `ACT_365_25` | `days / 365.25` |
| `NL_365` | `(days - n) / 365`, where `n` counts 29 Februaries in `(start, end]` |
| `ONE_ONE` | 1 if `end > start`, otherwise 0 |
| `BUS_252` | Business days in `[start, end)` on `calendar`, divided by 252 |

### `ACT_365L`
If `frequency` is 1: `days / 366` when a 29 February lies in `(start, end]`, otherwise `days / 365`.
Any other frequency: `days / D(year of end)`.

### `ACT_ACT_ISDA`
Same year: `days / D(y)`. Otherwise, with `y1`, `y2` the years of `start`, `end`:

`(Jan1(y1+1) - start) / D(y1) + (y2 - y1 - 1) + (end - Jan1(y2)) / D(y2)`

### `ACT_ACT_ICMA`
`days / (frequency * (ref_end - ref_start))`, differences in calendar days.

### `ACT_ACT_AFB`
Count whole years back from `end`. Let `back(n)` be `end` moved back `n` calendar years, with:
- if `end` is 28 February and the target year is a leap year, `back(n)` is 29 February of that year;
- if `end` is 29 February and the target year is not a leap year, `back(n)` is 28 February.

Let `n` be the largest integer with `back(n) >= start`, and `e = back(n)` (`e = end` when `n = 0`).
The result is `n + (e - start) / d`, where `d` is 366 if a 29 February lies in `[start, e)`, else 365:
the first day counts and the last does not.

The first rule is the ISDA text on counting back from 28 February. QuantLib follows it and Strata
does not, so Strata results differ for those dates (see "Known library differences").

### 30/360 family

All use `(360 (Y2-Y1) + 30 (M2-M1) + (D2-D1)) / 360` after adjusting the day numbers.
`eofeb(d)` is true on the last day of February.

| Convention | Other names | Adjustments, applied in this order |
|---|---|---|
| `THIRTY_360_BOND` | 30/360 ISDA, Bond Basis | If `D1 = 31`, `D1 = 30`. If `D2 = 31` and `D1 = 30`, `D2 = 30` |
| `THIRTY_360_US` | 30U/360 EOM, SIA | If `eofeb(start)` and `eofeb(end)`, `D2 = 30`. If `eofeb(start)`, `D1 = 30`. If `D2 = 31` and `D1 >= 30`, `D2 = 30`. If `D1 = 31`, `D1 = 30` |
| `THIRTY_E_360` | Eurobond Basis, ISMA | If `D1 = 31`, `D1 = 30`. If `D2 = 31`, `D2 = 30` |
| `THIRTY_E_360_ISDA` | German | If `D1 = 31` or `eofeb(start)`, `D1 = 30`. If `D2 = 31`, or `eofeb(end)` and `end != termination`, `D2 = 30` |
| `THIRTY_E_PLUS_360` | | If `D1 = 31`, `D1 = 30`. If `D2 = 31`, `D2 = 1` and `M2 = M2 + 1`; month 13 is fine in the formula |

## Worked examples

| Convention | From | To | Result |
|---|---|---|---|
| `ACT_360` | 2024-01-01 | 2024-07-01 | 182/360 |
| `ACT_ACT_ISDA` | 2003-11-01 | 2004-05-01 | 61/365 + 121/366 = 0.497724380567 |
| `ACT_ACT_ICMA`, f=2, ref 2003-11-01 to 2004-05-01 | 2003-11-01 | 2004-05-01 | 182/(2 x 182) = 0.5 |
| `ACT_ACT_AFB` | 1994-02-10 | 1997-06-30 | 3 + 140/365 |
| `THIRTY_360_BOND` | 2024-01-31 | 2024-03-31 | 60/360 |
| `THIRTY_E_PLUS_360` | 2024-01-30 | 2024-03-31 | 61/360 |

The ACT/ACT rows come from the ISDA comparison of ACT/ACT methods.

## Acceptance

Tolerance class `simple_analytic`. Golden cases cover each convention on month ends, 29 February,
year boundaries and spans over several leap years. Oracle: exact rational arithmetic from this file,
checked against QuantLib and Strata wherever each has the convention.

## Known library differences

Measured by `oracle/python/gen_dates.py` and recorded in `oracle/REPORT.md`:
- Strata does not apply the 28 February rule in `ACT_ACT_AFB`.
- Strata gives 1 for `ONE_ONE` when `start = end`. Here it is 0, like every other convention.
- Strata differs on 13 tested `ACT_ACT_ICMA` periods, where QuantLib agrees with this file. The cause was not
  investigated and may lie in how the oracle passes schedule data to Strata. Those cases list only the
  sources that agree in `verified_by`.

## Out of scope

`ACT/ACT YEAR`, ACT/366, 30/365, and Italian 30/360 are not offered. Long-stub splitting and ex-dividend
periods arrive with schedules in stage B.
