# Question bank 1: Foundations and numerical methods

This set is for anyone learning the core layer of QuantForge: students meeting day counts for the first time, and practitioners who want to check that they read the library's conventions the way the specifications state them. It covers dates and calendars, compounding, units and money, root finders, quadrature, interpolation, differences and linear algebra, the PDE and COS engines, and the statistics helpers. Each answer gives the plain idea first, then the rule as the specification states it, then a worked example whose numbers were produced by running `quantforge_core` (the script `verify/v01_foundations_numerics.py` recomputes every one). Levels: foundation (definitions and first use), practitioner (what a desk or validator relies on), advanced (edge cases, convergence and design decisions). Try to answer before reading.

## Day counts

### Q1.1 How do ACT/360 and ACT/365F differ, and what year fraction does each give from 1 January to 1 July 2024?

*Level: foundation. Evidence: computed; spec. Source: [Day counts](../../specifications/01-core/daycount.md)*

Both count the actual calendar days between the dates and divide by a fixed number; they differ only in the denominator. ACT/360 is the money-market convention for USD and EUR rates; ACT/365F is used for GBP (SONIA, per the [convention registry](../../specifications/01-core/conventions.md)).

Formal statement: `days` counts the start and not the end; `ACT_360 = days / 360`, `ACT_365F = days / 365`.

**Worked example.** From 2024-01-01 to 2024-07-01 there are 182 days (a leap year, so February has 29). `core.daycount.year_fraction` gives ACT_360 = 0.505556 and ACT_365F = 0.498630.

The gap is about 1.4% of the accrual. Applying the wrong one to a 5% coupon on 100m mis-states a half-year accrual by roughly 35,000, which is why the convention is data in the registry and never a default.

### Q1.2 What does ACT/ACT ISDA give from 1 November 2003 to 1 May 2004, and how does ACT/ACT ICMA differ on the same dates?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Day counts](../../specifications/01-core/daycount.md)*

ACT/ACT ISDA splits the period at each 1 January and divides each piece by the length of its own calendar year. ACT/ACT ICMA instead divides by the length of the coupon period times the frequency, so a full regular coupon period is always exactly `1/frequency`.

Formal statement: ISDA is `(Jan1(y1+1) - start)/D(y1) + (y2 - y1 - 1) + (end - Jan1(y2))/D(y2)`; ICMA is `days / (frequency * (ref_end - ref_start))`, and needs `frequency`, `ref_start` and `ref_end` (missing ones give `E_SCHEMA`).

**Worked example.** ISDA: 61 days in 2003 over 365 plus 121 days in 2004 over 366, so ACT_ACT_ISDA = 0.497724380567, the value in the spec's table from the ISDA comparison of ACT/ACT methods. ICMA with `frequency = 2` and the reference period equal to the accrual period gives ACT_ACT_ICMA = 0.500000.

ICMA is the bond convention because it makes each coupon equal. A long stub that spans two notional periods is `E_INPUT`: the caller splits it and adds the parts.

### Q1.3 How do the 30/360 variants treat 29 February 2024 to 31 August 2024?

*Level: practitioner. Evidence: computed; spec. Source: [Day counts](../../specifications/01-core/daycount.md)*

All 30/360 conventions use `(360 (Y2-Y1) + 30 (M2-M1) + (D2-D1)) / 360` but adjust the day numbers differently first, and month ends are exactly where they disagree.

Formal statement (spec table): Bond basis changes `D1 = 31` to 30, and `D2 = 31` to 30 only if `D1 = 30`. US (EOM) treats the last day of February as 30. Eurobond (30E/360) changes any 31 to 30. German (30E/360 ISDA) also treats end of February as 30 unless the end date is the termination date. 30E+/360 rolls a 31st end date to the 1st of the next month.

**Worked example.** From 2024-02-29 to 2024-08-31, with termination 2029-08-31 for the German rule:
THIRTY_360_BOND = 182/360, THIRTY_360_US = 180/360, THIRTY_E_360 = 181/360, THIRTY_E_360_ISDA = 180/360, THIRTY_E_PLUS_360 = 182/360.

Five names, three answers. A validator checks the exact variant in the term sheet, and the spec gives each its other market names so that "30/360" alone is never accepted.

### Q1.4 What does QuantForge return when the start equals the end, or the end is before the start?

*Level: foundation. Evidence: computed; spec. Source: [Day counts](../../specifications/01-core/daycount.md)*

An empty period accrues nothing, and a backwards period is an input error rather than a negative fraction.

Formal statement: "`start == end` gives 0 for every convention, including `ONE_ONE`", and this test comes before any day-number adjustment. `end` before `start` is `E_DATE_ORDER`; a caller wanting a signed value swaps the dates and negates, which is its own decision because 30/360 is not symmetric.

**Worked example.** `year_fraction("ONE_ONE", 2024-02-29, 2024-02-29)` gives ONE_ONE same day = 0. Swapping 2024-02-29 and 2024-08-31 under ACT_360 gives reversed dates: E_DATE_ORDER.

The spec records the two places where this differs from other libraries: Strata documents 1/1 as always 1, and QuantLib 1.44 and Strata return -1/360 for German 30/360 on an empty period ending on 29 February that is also the termination date. QuantForge returns 0 in both.

### Q1.5 Why does ACT/ACT AFB give the same answer from 28 February 2004 to both 28 and 29 February 2008, and why does Strata disagree?

*Level: advanced. Evidence: computed; spec; literature. Source: [Day counts](../../specifications/01-core/daycount.md)*

AFB counts whole years back from the end date and then adds a fraction for the remainder. The ISDA clarification says that counting back from 28 February into a leap year lands on 29 February, and that rule creates the oddity.

Formal statement: `back(n)` is `end` moved back `n` years; from 28 February into a leap year it is 29 February. `n` is the largest integer with `back(n) >= start`, `e = back(n)`, and the result is `n + (e - start)/d`, with `d = 366` only if a 29 February lies in `[start, e)`.

**Worked example.** End 2008-02-28: `back(4)` is 2004-02-29, one day after the start, and no 29 February lies in `[2004-02-28, 2004-02-29)`, so AFB to 2008-02-28 = 4.002739726 (that is `4 + 1/365`). End 2008-02-29 lands on the same `e`, so AFB to 2008-02-29 = 4.002739726. Strata rolls back from 29 February instead and gives `Strata 4 + 1/366 = 4.002732240` for both (scratch arithmetic, not the library). The spec's own example, AFB 1994-02-10 to 1997-06-30 = 3.383561644, is `3 + 140/365`.

QuantForge keeps the ISDA text, as QuantLib does; the 11 Strata differences are listed in the spec's "Known library differences" so a cross-check does not flag them as bugs.

### Q1.6 How is BUS/252 computed, and what does it give on the GBLO calendar for the first half of 2024?

*Level: practitioner. Evidence: computed; spec. Source: [Day counts](../../specifications/01-core/daycount.md), [Calendars](../../specifications/01-core/calendars.md)*

BUS/252 is the Brazilian-style convention: it counts business days, not calendar days, and divides by 252. It therefore needs a calendar input.

Formal statement: "Business days in `[start, end)` on `calendar`, divided by 252". Without `calendar` the call fails with `E_SCHEMA`.

**Worked example.** From 2024-01-01 to 2024-07-01 on `GBLO`, `business_days_between` gives GBLO business days = 125 (it excludes New Year, Good Friday, Easter Monday and the two May holidays), and `year_fraction` gives BUS_252 = 0.496032.

QuantForge offers only `GBLO`, `EUTA` and `USGS`; there is no Brazilian calendar, so BUS/252 here is a convention exercise rather than a BRL pricing tool.

## Calendars and business-day rules

### Q1.7 How does QuantForge find Good Friday, and when is Good Friday 2026?

*Level: foundation. Evidence: computed; spec; literature. Source: [Calendars](../../specifications/01-core/calendars.md)*

Easter moves every year, so it is computed, not listed. Good Friday is two days before Easter Sunday and Easter Monday one day after.

Formal statement: the anonymous Gregorian algorithm (Meeus, Jones, Butcher), integer division throughout, as printed in the spec. All calendars are valid from 2000 to 2099; outside that range is `E_DATE_RANGE`.

**Worked example.** `easter_sunday(2026)` gives Easter Sunday 2026 = 2026-04-05, so Good Friday 2026 = 2026-04-03. On the London calendar, GBLO 2026-04-03 business day = False.

The Easter dates drive four of the eight GBLO holidays and two of the six TARGET holidays, so an error here would move a large share of every schedule.

### Q1.8 Why is Good Friday 2026 a business day on the USGS calendar but Good Friday 2025 is not?

*Level: practitioner. Evidence: computed; spec; design. Source: [Calendars](../../specifications/01-core/calendars.md), [R1 rulings](../../specifications/r1-rulings.md)*

SIFMA usually recommends a full close on Good Friday, but in some years, when Good Friday is also the day of the US employment report, it recommends an early close instead. An early close is still a trading day.

Formal statement (ruling R1-6): an early close is a business day for settlement, accrual and schedules. The years are a published list, 2007, 2010, 2012, 2015, 2021, 2023 and 2026, not the first-Friday pattern: a future first-Friday Good Friday stays a holiday until SIFMA publishes and the list is extended.

**Worked example.** USGS 2026-04-03 business day = True; USGS 2025-04-18 business day = False.

Two pitfalls. QuantLib projects early closes into future years (2034, 2037 and so on), so the libraries diverge after 2026 by design. And SOFR is not published on any Good Friday, so SOFR compounding keeps Good Friday as a non-business day in every year (R1-6).

### Q1.9 What do FOLLOWING, MODIFIED_FOLLOWING and PRECEDING do to Saturday 31 August 2024 in London?

*Level: foundation. Evidence: computed; spec. Source: [Calendars](../../specifications/01-core/calendars.md)*

A business-day convention moves a date that falls on a holiday or weekend. FOLLOWING goes forward, PRECEDING goes back, and the modified forms go forward (or back) unless that leaves the month, in which case they search the other way.

Formal statement: "The modified forms take the plain result unless it leaves the month, and then search the other way." Conventions are `UNADJUSTED`, `FOLLOWING`, `PRECEDING`, `MODIFIED_FOLLOWING`, `MODIFIED_PRECEDING`.

**Worked example.** On `GBLO` (with GBLO holidays Aug 2024 = ['2024-08-26'], the summer bank holiday): FOLLOWING -> 2024-09-02, MODIFIED_FOLLOWING -> 2024-08-30, PRECEDING -> 2024-08-30.

Modified following is the default in every QuantForge rates convention because it keeps a period end inside its month, so a monthly or quarterly accrual never silently absorbs part of the next month.

### Q1.10 How does `add_tenor` treat month ends when `end_of_month` is true?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Calendars](../../specifications/01-core/calendars.md)*

The end-of-month rule says that a date on the last business day of a month rolls to the last business day of the target month, so a schedule that starts at month end stays at month end.

Formal statement: for `M` and `Y` tenors, add months with the day clipped to the month. If `end_of_month` is true, the convention is not `UNADJUSTED`, and the date is on or after the last business day of its month, the result is the last business day of the target month; the date itself need not be a business day. Otherwise the convention is applied. This is QuantLib's `Calendar::advance` rule, checked on every day from 2021 to 2026.

**Worked example.** From 2023-02-28 plus `1M` on `GBLO` with modified following: EOM true -> 2023-03-31, EOM false -> 2023-03-28. From Saturday 2024-03-30, which is after the last business day of March (the 28th, as the 29th was Good Friday): EOM true from 2024-03-30 -> 2024-04-30.

Without the flag, one February start drags every later date to the 28th.

### Q1.11 How do `add_business_days` and `business_days_between` count?

*Level: foundation. Evidence: computed; spec. Source: [Calendars](../../specifications/01-core/calendars.md)*

Adding business days steps one calendar day at a time and counts only business days, never the start date. Counting between two dates includes the start and excludes the end.

Formal statement: `add_business_days` with `days = 0` returns the `FOLLOWING`-adjusted date; otherwise it steps in the sign of `days` until `|days|` business days are counted. `business_days_between` counts `[start, end)`, and `end` before `start` is `E_DATE_ORDER`.

**Worked example.** add_business_days(0) from Saturday -> 2024-09-02 (31 August 2024). add_business_days(2) from Friday 2024-08-23 -> 2024-08-28, because Monday 26 August is a bank holiday. business_days_between Mon-Mon = 5 for 2024-09-02 to 2024-09-09.

The same rules settle spot lags: SOFR's `spot_lag` of 2 in the registry counts business days on `USGS`.

## Schedules

### Q1.12 How does QuantForge generate a coupon schedule, and where does the stub go?

*Level: practitioner. Evidence: computed; spec. Source: [Schedules](../../specifications/02-curves/schedules.md)*

Dates are rolled backwards from the maturity, so any odd-length period falls at the start (a short first stub). Every date except the start is then adjusted.

Formal statement: unadjusted dates step back from `end` by `k * frequency_months`, from the original `end` each time (no drift from repeated clipping), while they stay after `start`. Each is adjusted with `MODIFIED_FOLLOWING`, or set to the last business day of its month if `end_of_month`. A date on or before `start` after adjustment is dropped. `payment` is `end` plus `payment_lag` business days.

**Worked example.** `generate(2024-01-15, 2025-04-15, 6, "GBLO", False, 0)` gives:

| start | end | payment |
|---|---|---|
| 2024-01-15 | 2024-04-15 | 2024-04-15 |
| 2024-04-15 | 2024-10-15 | 2024-10-15 |
| 2024-10-15 | 2025-04-15 | 2025-04-15 |

The first period is a three-month short stub. Long stubs and ex-dividend periods are not implemented in stage B; the result is checked exactly against QuantLib `Schedule` with backward generation.

## Compounding

### Q1.13 What discount factor does a 5% rate give over two years under simple, semi-annual and continuous compounding?

*Level: foundation. Evidence: computed; spec. Source: [Compounding](../../specifications/01-core/compounding.md)*

A rate means nothing until its compounding is stated: the same 5% compounds more often, and so discounts more, under the more frequent rule.

Formal statement: `SIMPLE` `D = 1/(1 + r t)`; `PERIODIC` `D = (1 + r/n)^(-n t)`; `CONTINUOUS` `D = exp(-r t)`. Rates are decimals, so 0.05 is 5%.

**Worked example.** With `r = 0.05`, `t = 2`: simple D = 0.909090909, semi-annual D = 0.905950645, continuous D = 0.904837418, matching the spec's examples.

The difference between simple and continuous is about 0.43% of the PV here, which is far larger than any tolerance in the conformance suite.

### Q1.14 How do you convert a 5% semi-annual rate to its continuous and annual equivalents, and why is `t = 0` rejected?

*Level: practitioner. Evidence: computed; spec. Source: [Compounding](../../specifications/01-core/compounding.md)*

Two rates are equivalent when they give the same discount factor over the same time. So conversion computes `D` with the source rule and then solves for the rate under the target rule.

Formal statement: `core.compounding.convert` computes `D` with `from`, then the rate with `to`: `-ln(D)/t` for continuous, `n (D^(-1/(n t)) - 1)` for periodic. `t = 0` in `convert` is `E_DOMAIN`, as the rate is undefined, while `discount_factor` at `t = 0` is 1.

**Worked example.** From 5% semi-annual over 2 years: continuous rate = 0.049385225 and annual rate = 0.050625000. With `t = 0`: t = 0 convert: E_DOMAIN.

For periodic and continuous rules the answer does not depend on `t`; it does when simple is involved, which is why `t` is an input at all.

### Q1.15 Are negative rates allowed, and when does a rate fail the domain check?

*Level: practitioner. Evidence: computed; spec. Source: [Compounding](../../specifications/01-core/compounding.md)*

Negative rates are allowed and simply give discount factors above 1. What is rejected is a rate so negative that the compounding base itself is not positive.

Formal statement: "Negative rates are allowed." `SIMPLE` with `1 + r t <= 0`, or `PERIODIC` with `1 + r/n <= 0`, is `E_DOMAIN`. Checks run in order: frequency (`E_SCHEMA`), `t < 0`, `t = 0` in `convert`, then this base check.

**Worked example.** At -0.5% continuous over 3 years, negative continuous D = 1.015113065. A rate of -400% quarterly makes `1 + r/4 = 0`: r = -4 quarterly: E_DOMAIN.

EUR and CHF curves spent years below zero, so a library that refuses negative rates cannot price them. Continuous compounding has no domain limit on `r` at all.

## Units and money

### Q1.16 How does `round_money` round 2.675 GBP and 1234.5 JPY, and why not ordinary rounding?

*Level: foundation. Evidence: computed; spec. Source: [Units and money](../../specifications/01-core/units-and-money.md)*

Money is held as an exact decimal string, never binary floating point, and is rounded half to even at the currency's minor unit. Half to even (banker's rounding) does not drift upwards over many roundings.

Formal statement: amounts match `^-?[0-9]{1,18}(\.[0-9]{1,8})?$`; GBP, USD and EUR have 2 places, JPY 0; other currencies are `E_SCHEMA`. `round_money` "rounds half to even, at the currency's minor unit".

**Worked example.** round 2.675 GBP -> 2.68 and round 2.665 GBP -> 2.66; round 1234.5 JPY -> 1234 and round 1235.5 JPY -> 1236. Additions are exact: 0.1 + 0.2 = 0.3 and 1.50 + -1.5 = 0.

In binary64, 2.675 is stored as 2.67499999..., so a float-based round gives 2.67. The decimal string avoids that, and PVs stay in binary64 until they become money at a boundary.

### Q1.17 How are percent and basis points handled, and what happens when you add GBP to USD?

*Level: foundation. Evidence: computed; spec. Source: [Units and money](../../specifications/01-core/units-and-money.md)*

Inside the libraries a rate is always a decimal; percent and basis points exist only at the edges, and money carries its currency so it cannot be mixed by accident.

Formal statement: `core.units.convert`: 1 = 100 `PERCENT` = 10,000 `BP`. `core.units.add_money` with different currencies is `E_CURRENCY_MISMATCH`.

**Worked example.** 25 BP = 0.0025 DECIMAL = 0.25 PERCENT. Adding 1 GBP to 1 USD gives GBP + USD: E_CURRENCY_MISMATCH.

A factor-of-100 unit error is the commonest silent bug in rates code; this is why every risk output in QuantForge states its unit (for example "per 1bp").

## Root finders

### Q1.18 How do bisection, Brent and Newton compare on `x^3 - 2x - 5` from the bracket `[2, 3]`?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Root finders](../../specifications/01-core/root-finders.md), [Test functions](../../specifications/01-core/test-functions.md)*

Bisection halves a bracket and always converges, slowly. Newton uses the derivative and converges fast near a simple root. Brent mixes inverse quadratic interpolation, secant and bisection, so it keeps the bracket's safety with near-Newton speed and needs no derivative.

Formal statement: defaults `x_tol = 1e-12`, `f_tol = 0`, `max_iter = 200`. Each result carries `iterations`, `residual` and `termination` (`X_TOL`, `F_TOL` or `EXACT`). Only `root` is compared in conformance.

**Worked example.** On `cubic_wallis` (Newton from `x0 = 2`):
bisection root = 2.094551481541, 39 iterations; brent root = 2.094551481542, 7 iterations; newton root = 2.094551481542, 5 iterations.

The iteration counts are diagnostics, not contract: the spec says Brent's count differs by a step between correct builds (6 or 7 on this function). A validator compares roots, never counts.

### Q1.19 What error codes do the root finders raise, and what does the Newton safeguard do?

*Level: practitioner. Evidence: computed; spec. Source: [Root finders](../../specifications/01-core/root-finders.md)*

Each failure has its own code so a calibration loop can tell "no root here" from "the method broke down".

Formal statement: bad tolerances are `E_INPUT`; no sign change at the ends is `E_NOT_BRACKETED` (signs are compared, not multiplied); a zero derivative in Newton is `E_ZERO_DERIVATIVE`; `max_iter` reached is `E_NO_CONVERGENCE`; a non-finite `f` is `E_NON_FINITE`. Safeguarded Newton with a bracket shrinks the bracket after each evaluation and takes the midpoint if a step leaves it.

**Worked example.** Bisection of `cubic_wallis` on `[3, 4]`: no bracket: E_NOT_BRACKETED. Newton on `x^2 + 1` from 0: zero derivative: E_ZERO_DERIVATIVE.

Implied-vol solvers hit both: a price outside the no-arbitrage bounds has no bracket, and deep out-of-the-money vega is close to zero, which is why the safeguarded form exists.

## Numerical integration

### Q1.20 How accurate are trapezoid, Simpson and 16-point Gauss-Legendre on `exp` over `[0, 1]`?

*Level: foundation. Evidence: computed; spec. Source: [Numerical integration](../../specifications/01-core/integration.md)*

Trapezoid and Simpson use equally spaced points with fixed weights. Gauss-Legendre chooses both points and weights optimally, so `n` points integrate any polynomial of degree `2n - 1` exactly.

Formal statement: `trapezoid` `h (f_0/2 + f_1 + ... + f_n/2)`; `simpson` (even `n`) `(h/3)(f_0 + 4 f_1 + 2 f_2 + ... + f_n)`; `gauss_legendre` `(b-a)/2 sum w_i f(...)`, `n` from 1 to 64, nodes the roots of `P_n`. The spec's target: Gauss-Legendre `n = 16` on `exp` over `[0, 1]` has error below 1e-14.

**Worked example.** Against `e - 1`, with 16 points or intervals each: trapezoid n=16 error = 5.59e-04, simpson n=16 error = 1.46e-07, gauss_legendre n=16 error = 4.44e-16.

These fixed rules are exact recipes, so all four language builds agree to rounding and are held to tight tolerance (class `quadrature`).

### Q1.21 How does the adaptive Gauss-Kronrod rule integrate `1/sqrt(x)` on `[0, 1]` when the integrand is infinite at 0?

*Level: advanced. Evidence: computed; spec; literature. Source: [Numerical integration](../../specifications/01-core/integration.md)*

Gauss-Kronrod nodes are all interior, so the rule never evaluates the singular end point. Adaptivity then bisects the worst interval until the error estimate is small, which concentrates intervals near the singularity.

Formal statement: globally adaptive G7-K15 (QUADPACK). Each interval gets the 15-point Kronrod value and error estimate `|K15 - G7|`; while the sum of estimates exceeds `max(tol, 1e-14 |value|)`, bisect the interval with the largest estimate. Over `max_intervals` (default 500) is `E_NO_CONVERGENCE`. Target: with `tol = 1e-10`, error below 1e-9 on every registered function including `inv_sqrt`.

**Worked example.** With `tol = 1e-10` against the true value 2: gauss_kronrod inv_sqrt error = 4.3e-11.

Adaptive rules are held to the requested accuracy, not to a recipe, because the chosen intervals depend on the error estimate, so different correct builds can differ well beyond rounding.

## Interpolation

### Q1.22 Why interpolate discount factors log-linearly rather than linearly?

*Level: foundation. Evidence: computed; spec. Source: [Interpolation](../../specifications/01-core/interpolation.md), [Interpolation methods](../curves/interpolation-methods.md)*

Log-linear interpolation of discount factors is linear interpolation of `r t`, which means a constant instantaneous forward rate between knots. Linear interpolation of discount factors has no such meaning.

Formal statement: `linear` is `y_i + u (y_{i+1} - y_i)`; `log_linear` is `exp((1-u) ln y_i + u ln y_{i+1})`, any `y <= 0` is `E_DOMAIN`. A query outside the knots is `E_OUT_OF_RANGE`; extrapolation belongs to curves.

**Worked example.** Knots `DF(1) = 0.97`, `DF(2) = 0.93`: linear DF(1.5) = 0.950000; log_linear DF(1.5) = 0.949789, the geometric mean = 0.949789.

The difference is small per point but systematic: linear DFs give a forward curve that drifts within each interval. `linear` and `log_linear` return no derivatives, because a query on a knot has no single slope.

### Q1.23 Why can a natural cubic spline overshoot step-like data, and what does monotone PCHIP do instead?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Interpolation](../../specifications/01-core/interpolation.md)*

A cubic spline is smooth because each piece feels its neighbours, so a jump in the data rings into flat regions. PCHIP chooses slopes from local data only and sets a slope to zero where the data changes direction or is flat, so monotone data stays monotone.

Formal statement: `cubic_natural` has `s'' = 0` at both ends. `monotone_pchip` is a Hermite cubic with Fritsch-Butland slopes: interior `m_i = 0` if `d_{i-1}`, `d_i` differ in sign or either is 0, else a weighted harmonic mean. Target: PCHIP on monotone data never overshoots.

**Worked example.** Knots `x = 0..4`, `y = 0, 0, 0, 1, 1`: cubic_natural at 1.5 = -0.100446, at 3.5 = 1.127232; monotone_pchip at 1.5 = 0.000000, at 3.5 = 1.000000.

On a curve, overshoot means negative forwards or a hump nobody quoted. The cost of PCHIP is a discontinuous second derivative.

### Q1.24 What does Hagan-West monotone convex interpolation guarantee, and how does it behave between knots?

*Level: advanced. Evidence: computed; spec; literature. Source: [Interpolation](../../specifications/01-core/interpolation.md), [Interpolation methods](../curves/interpolation-methods.md)*

Monotone convex interpolates forward rates, not zero rates, and is built so that each input zero rate is reproduced exactly while the forward curve stays continuous and avoids the oscillation of splines.

Formal statement (Hagan and West 2006, the original method): discrete forwards `fd_i = (r_i t_i - r_{i-1} t_{i-1})/(t_i - t_{i-1})`, node forwards as weighted averages, and on each interval `f(s) = fd_i + g(x)` with `g` from one of four regions. "Each `g` integrates to 0 on `[0, 1]`, which is why every input zero rate reprices." Target: repricing to 1e-12. With `positive` true, node forwards are clamped to `[0, 2 fd]`.

**Worked example.** Continuously compounded zero rates 3%, 3.5%, 4%, 4.2% at 1, 2, 5, 10 years: zero rate at 2 = 0.035000000000, zero rate at 5 = 0.040000000000 (inputs reproduced); between knots, zero rate at 3 = 0.037611 and forward at 3 = 0.043583.

QuantLib's `ConvexMonotone` is a later variant with extra parameters, so the spec does not use it as a second source; this method rests on the paper alone.

## Finite differences and linear algebra

### Q1.25 Why does a central difference get worse when the step is made very small?

*Level: practitioner. Evidence: computed; spec. Source: [Finite differences and linear algebra](../../specifications/01-core/differentiation-and-linalg.md)*

Two errors compete. Truncation error falls as `h^2`, but rounding error in `f(x+h) - f(x-h)` is divided by `2h` and so grows as `h` shrinks. The best step balances them, near `eps^(1/3)` for a first derivative.

Formal statement: order 1 is `(f(x+h) - f(x-h))/(2h)`, order 2 is `(f(x+h) - 2 f(x) + f(x-h))/h^2`. Each case's rounding limit is `8 eps M / h` for order 1 and `32 eps M / h^2` for order 2, `eps = 2^-52`.

**Worked example.** Derivative of `exp` at `x = 1` (scratch stencil, the same formula as `core.diff.central`): h = 1e-01: error 4.5e-03; h = 1e-04: error 4.5e-09; h = 1e-08: error 6.6e-09.

This is why QuantForge's bump-and-reprice risk uses stated bump sizes (1bp for rates) and why the AAD ladder is checked against Richardson-extrapolated differences rather than a single tiny bump.

### Q1.26 When does Cholesky fail on a correlation matrix, and what does QuantForge return?

*Level: practitioner. Evidence: computed; spec. Source: [Finite differences and linear algebra](../../specifications/01-core/differentiation-and-linalg.md)*

Cholesky writes a symmetric positive definite matrix as `L L^T`; it is how correlated normals are made from independent ones. A matrix of pairwise correlations that is not jointly consistent has a negative eigenvalue, and Cholesky meets a non-positive pivot.

Formal statement: `core.linalg.cholesky` returns lower-triangular `l` with positive diagonal; a pivot `<= 0` is `E_NOT_POSITIVE_DEFINITE`; asymmetry above 1e-12 relative is `E_INPUT`. `eigen_symmetric` returns values ascending.

**Worked example.** For correlations 0.8, 0.3, 0.5: L = [[1.000000], [0.800000, 0.600000], [0.300000, 0.433333, 0.849837]]. For 0.9, 0.2, 0.9 (A close to B, B close to C, A far from C): eigenvalues = -0.176715, 0.800000, 2.376715 and cholesky: E_NOT_POSITIVE_DEFINITE.

The repair (nearest correlation matrix) is a separate risk-layer tool, covered in LEARN's correlation section ([LEARN](../../LEARN.md)); the core never alters the input silently.

## PDE and Fourier engines

### Q1.27 How accurate is QuantForge's Crank-Nicolson PDE on an at-the-money call, and what does Rannacher start-up fix?

*Level: advanced. Evidence: computed; spec; literature. Source: [PDE engine](../../specifications/01-core/pde.md)*

The engine solves Black-Scholes in `x = ln S` on a uniform grid with spot on the middle node. Crank-Nicolson is second order but rings when the payoff kink is the initial condition; a few fully implicit half steps at the start (Rannacher) damp that, and cell-averaging the payoff stops the strike's grid position from mattering.

Formal statement: `h = 2 w sigma sqrt(t)/J`, `dt = t/M`; the first `R` (default 2) steps are each two implicit half steps, then `M - R` Crank-Nicolson steps solved by Thomas. Target at `S = K = 100`, `r = 0.05`, `q = 0.02`, `sigma = 0.2`, `t = 1`: `J = 400`, `M = 200` price error below 1e-3, and doubling both cuts the error by a factor between 3 and 5.

**Worked example.** Black-Scholes call = 9.227006 (scratch closed form). J = 400, M = 200: price 9.227097, error 9.12e-05. J = 800, M = 400: price 9.227028, error 2.28e-05, a ratio of 4, so second order.

The recipe is exact, so all four builds land on the same grid solution, not merely near the true price. American exercise and barriers belong to later stages.

### Q1.28 How does the PDE engine turn grid values in `ln S` into delta and gamma?

*Level: advanced. Evidence: computed; spec. Source: [PDE engine](../../specifications/01-core/pde.md)*

The grid is uniform in `x = ln S`, so the natural differences are in `x`. Converting to spot needs the chain rule, and the second derivative picks up a first-derivative term.

Formal statement: with `m = J/2`, `V_x = (V_{m+1} - V_{m-1})/(2h)`, `V_xx = (V_{m+1} - 2 V_m + V_{m-1})/h^2`, `delta = V_x / spot`, `gamma = (V_xx - V_x)/spot^2`. Targets at `J = 400`, `M = 200`: delta and gamma errors below 1e-4.

**Worked example.** Same inputs as Q1.27: the engine gives delta 0.586863, gamma 0.018951; the closed forms (scratch formula) give analytic delta 0.586851, gamma 0.018951.

Forgetting the `- V_x` term is the usual bug: it gives a gamma that is wrong by `delta/spot`, here about 0.0059, a third of the true value.

### Q1.29 Why does QuantForge's COS method always price the put and get the call by parity?

*Level: advanced. Evidence: computed; spec; literature. Source: [COS Fourier pricing](../../specifications/01-core/cos.md)*

COS expands the density of the log price in a cosine series on a truncated range `[a, b]` and integrates the payoff against it. A call payoff grows like `exp(y)` towards `b`, so its coefficients grow with `exp(b)` and lose accuracy; the put payoff is bounded.

Formal statement: `a, b = c1 -+ L sqrt(w)`, `w` the total variance; `put = exp(-r t) sum' Re[phi(u_k) exp(i u_k (x - a))] V_k`, `k = 0..N-1`, first term halved; call `= put + spot exp(-q t) - strike exp(-r t)`. A range not holding the strike is `E_INPUT`. Target: Black-Scholes, `N = 256`, `L = 10`, error below 1e-10.

**Worked example.** `S = 100`, `K = 110`, `r = 0.05`, `q = 0.02`, `sigma = 0.2`, `t = 1`: COS call K=110 = 5.1885817538 against analytic = 5.1885817538 (scratch closed form), with range a = -2.085310, b = 1.914690. With only 16 terms, N = 16: 5.194648.

Convergence is exponential for smooth densities, so a few hundred terms suffice; Heston is priced through the Albrecher form of the characteristic function, which stays on the right branch of the complex log.

## Statistics and time series

### Q1.30 How does `core.stats.quantile` compute quantiles, and what does it give for a small sample?

*Level: foundation. Evidence: computed; spec; literature. Source: [Statistics and time series](../../specifications/01-core/statistics-and-time-series.md)*

There are several sample-quantile definitions; QuantForge fixes one, Hyndman-Fan type 7 (the NumPy and R default), which interpolates linearly between order statistics.

Formal statement: sort `x`; `h = (n - 1) p`; `k = floor(h)`; value `x[k] + (h - k)(x[k+1] - x[k])`, indices from 0, `x[n-1]` at `p = 1`; `p` outside `[0, 1]` is `E_DOMAIN`.

**Worked example.** For `3, 1, 4, 1, 5, 9, 2, 6` at `p = 0.25, 0.5, 0.9`: quantiles = 1.75, 3.5, 6.9. The sample variance (divisor `n - 1`) is variance = 7.553571.

Historical VaR on a few hundred scenarios moves noticeably between quantile definitions, so a cross-system reconciliation must start by agreeing the type.

### Q1.31 Why do QuantForge's statistics shift by the first value, and what is the EWMA variance recursion?

*Level: advanced. Evidence: computed; spec; literature. Source: [Statistics and time series](../../specifications/01-core/statistics-and-time-series.md)*

The textbook shortcut `sum(x^2) - n mean^2` subtracts two huge, nearly equal numbers and can lose every digit. Subtracting the first value first makes the data small, so the two-pass formula stays exact.

Formal statement: "Never use `sum(x^2) - n mean^2`." `summary`, `covariance`, `ols`, `autocorrelation` and `ar1` first shift by `x_0`, then use deviations from the shifted mean. EWMA: `v_0 = r_0^2`, `v_t = lambda v_{t-1} + (1 - lambda) r_t^2`, zero mean assumed, `lambda` in `(0, 1)`.

**Worked example.** For `1e9 + (4, 7, 13, 16)`: two-pass variance = 30, while the naive formula = 0 (scratch formula, not the library). EWMA with `lambda = 0.94` on returns 1%, -2%, 1.5%: ewma = 1.000000e-04, 1.180000e-04, 1.244200e-04.

Prices near 1e9 are rare, but cumulative P&L and timestamps in nanoseconds are not; golden case stats-0006 exists to catch exactly this loss in `skewness`.
