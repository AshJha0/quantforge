# Question bank 3: Curves: OIS, projection and multi-curve

This set checks your understanding of how QuantForge builds and uses rate curves: the curve object, OIS bootstrapping, overnight compounding, the interpolation methods, turns and meeting steps, futures convexity, projection curves and FRAs, CSA discounting, the joint multi-curve solve, the funding curve, and the regularised curve fits with their stability report. It is written for two readers: a newcomer who wants to check the ideas, and a practitioner who wants to check QuantForge's exact conventions before relying on a number. Each answer starts with the plain idea, then gives the rule as the specification states it, then a worked example where the topic is quantitative. Levels are marked foundation, practitioner or advanced. Every number in a worked example was produced by running `quantforge_core`; the script [v03_curves_multicurve.py](verify/v03_curves_multicurve.py) recomputes each one and checks it is printed here. The data is synthetic throughout. Unless stated otherwise the examples use the six SOFR quotes of [Tutorial 1](../getting-started/tutorial-1-swap.md) (1Y 3.50%, 2Y 3.35%, 3Y 3.30%, 5Y 3.35%, 7Y 3.45%, 10Y 3.60%) with `as_of` 2026-11-06, bootstrapped with `LOG_LINEAR_DF`.

## The curve object

### Q3.1 What is a discount curve in QuantForge, and how is curve time measured?

*Level: foundation. Evidence: computed; spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Tutorial 1](../getting-started/tutorial-1-swap.md)*

A discount curve says what one unit of currency paid on a future date is worth today. QuantForge stores it as a list of pillar dates with their discount factors and fills the gaps by an interpolation rule.

Formally, the object is `{"as_of", "interpolation", "pillars": [{"date", "discount_factor"}]}`. There is an implied node at `as_of` with value 1. Curve time is always `t = (date - as_of) / 365`, whatever day count the instrument uses; day counts enter only through accrual fractions such as `alpha` in a forward rate. Zero rates reported by `rates.curve.discount` are continuous: `z = -ln(D)/t`, and `null` at `as_of`.

**Worked example.** Bootstrapping the Tutorial 1 quotes gives a 1Y pillar 2027-11-15 with D = 0.964899988733, and a 2Y pillar 2028-11-14 with D = 0.934658732578. The pillar dates are the last payment dates of each swap, not the anniversaries of `as_of` (Q3.9 explains the two-day spot and payment lags).

The pitfall: computing `t` with ACT/360 or with the instrument's own day count. That gives a different curve from the same pillars, and every downstream number moves.

### Q3.2 How does `LOG_LINEAR_DF` interpolate between pillars, and how does `LINEAR_ZERO` differ?

*Level: foundation. Evidence: computed; spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Interpolation methods](../curves/interpolation-methods.md)*

`LOG_LINEAR_DF` draws a straight line through the logarithms of the discount factors, which means the instantaneous forward rate is flat between pillars. `LINEAR_ZERO` draws a straight line through the continuous zero rates instead.

With `u = (t - t_i)/(t_{i+1} - t_i)`: `LOG_LINEAR_DF` is `D = exp((1-u) ln D_i + u ln D_{i+1})`; `LINEAR_ZERO` is `D = exp(-z t)` with `z = (1-u) z_i + u z_{i+1}` and `z_i = -ln(D_i)/t_i`. The node at `as_of` takes `z_1`, so the first `LINEAR_ZERO` segment is flat in zero rate.

**Worked example.** For 2028-05-15, between the 1Y and 2Y pillars, t = 1.523288. `LOG_LINEAR_DF` gives D(2028-05-15) = 0.9497004172, a zero rate 0.03387981. On the same pillars, LINEAR_ZERO gives 0.9493454021, a difference of -355.015 per million of notional paid on that date.

Both curves reprice the input quotes exactly, so a reprice test cannot tell them apart. They differ only between pillars, which is where most trade dates fall.

### Q3.3 How is a simple forward rate read off a curve?

*Level: foundation. Evidence: computed; spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md)*

A forward rate is the simple rate, agreed today, for borrowing between two future dates. It follows from the ratio of the two discount factors.

`rates.curve.forward` returns `(D(start)/D(end) - 1)/alpha`, with `alpha` the year fraction of the named `day_count` from `start` to `end`. `end <= start` is `E_DATE_ORDER`. Note the split: the discount factors come from curve time on ACT/365, while `alpha` uses the day count you pass.

**Worked example.** From the 1Y pillar (2027-11-15) to the 2Y pillar (2028-11-14), 365 days, on `ACT_360`: forward = 0.03191217. The 2Y par rate (3.35%) is below the 1Y (3.50%), so the forward between them is lower still.

What a validator checks: that the `day_count` matches the instrument. The same two discount factors on `ACT_365F` give a forward 365/360 times smaller.

### Q3.4 What does a curve return beyond its last pillar, or before `as_of`?

*Level: foundation. Evidence: computed; spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

Beyond the last pillar the curve carries on at the last forward rate it knows. Before `as_of` it refuses.

For `LOG_LINEAR_DF` and `LINEAR_ZERO`: `D = D_n exp(-f (t - t_n))` with `f = -ln(D_n/D_{n-1})/(t_n - t_{n-1})`, the flat forward of the last segment. For the stage F methods, the flat forward is the left-hand instantaneous forward at the last pillar, `f(t_n-)` (ruling F-20, as QuantLib's interpolated discount curves do). A date before `as_of` is `E_OUT_OF_RANGE`.

**Worked example.** The last segment runs from the 7Y to the 10Y pillar and has f = 0.03998558. Two years past the 10Y pillar, D(2038-11-15) = 0.6424611574.

The pitfall: treating extrapolated values as market information. A 12Y discount factor from a curve that ends at 10Y is an assumption, and a risk report should show such trades separately.

### Q3.5 Which errors does a curve object raise, and why does QuantForge never clamp?

*Level: foundation. Evidence: spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [OIS curves](../../specifications/02-curves/ois-curves.md)*

Bad input is rejected with a named error code rather than silently repaired, so a caller always knows whether a number is real.

The curve rules: pillar dates not strictly increasing or not after `as_of` give `E_INPUT`; a discount factor `<= 0` gives `E_DOMAIN`; an unknown `interpolation` gives `E_SCHEMA`; jump dates not increasing give `E_INPUT` and a jump factor `<= 0` gives `E_DOMAIN`; `jumps: null` is `E_SCHEMA` (absent means none). A forward with `end <= start` is `E_DATE_ORDER`, a date before `as_of` is `E_OUT_OF_RANGE`. For bootstraps, the OIS spec says a solve that fails is `E_NO_CONVERGENCE`, "never a silently clamped curve". A curve build order with a dependency cycle is `E_INPUT`.

What the desk cares about: a clamped discount factor produces a plausible-looking but wrong PV that no downstream check can detect. An error code stops the run at the point where the data went wrong.

## OIS bootstrapping

### Q3.6 What does bootstrapping an OIS curve mean, and how exact is it?

*Level: foundation. Evidence: computed; spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md), [Tutorial 1](../getting-started/tutorial-1-swap.md), [SOFR OIS](../curves/sofr-ois.md)*

Bootstrapping finds the discount factors that make every quoted swap worth exactly zero at its quoted rate. Each quote adds one unknown and one equation, so the system is square.

`rates.ois.bootstrap` places one pillar per quote, at the last payment date `p_n` of that swap, so a payment lag leaves every date the swap needs on or before its pillar. It solves `K_j(curve) = quote_j` for every `j` and must stop with every repricing error below 1e-13; the diagnostic `max_repricing_error` is required output. A quote given as `{bid, ask}` uses the mid.

**Worked example.** The six Tutorial 1 quotes bootstrap with max_repricing_error 9.7e-17, well inside the 1e-13 rule. QuantLib's `OISRateHelper` agrees on the pillars within 2e-11 (the spec's acceptance section).

The pitfall: reading an exact fit as evidence that the curve is right. Every interpolation reprices the quotes exactly; the fit says nothing about values between pillars.

### Q3.7 How are the annuity, floating leg and par rate of an OIS defined?

*Level: foundation. Evidence: computed; spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md)*

The annuity is the value of receiving one unit of rate on the fixed leg; the floating leg is the value of the compounded overnight payments; the par rate is the fixed rate that balances them.

Both legs share periods `(s_i, e_i, p_i)`. `A = sum alpha_i D(p_i)`, with `alpha_i` the fixed day-count fraction from `s_i` to `e_i`. `F = sum (D(s_i)/D(e_i) - 1) D(p_i)`: `D(s_i)/D(e_i)` is the expected compounded growth over the period, so no daily loop is needed on a single curve. `K = F/A`. A trade's PV is `pv = sign * notional * (F - fixed_rate * A)`, with sign +1 for `PAY` (paying fixed).

**Worked example.** For the 5Y SOFR swap on the Tutorial 1 curve: A = 4.59108440 and F = 0.15380133 per unit notional, so K = F/A = 0.0335000000, the 5Y quote, as a bootstrap guarantees.

What a validator checks: that the par rate of each input tenor returns its quote, and that the annuity uses payment dates, not period ends.

### Q3.8 Why must the floating leg not be telescoped to `D(s_0) - D(e_n)`?

*Level: practitioner. Evidence: computed; spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md), [Tutorial 1](../getting-started/tutorial-1-swap.md)*

The textbook shortcut that the floating leg equals "start discount factor minus end discount factor" only holds when each period pays on its own end date. SOFR pays two business days later, so the sum does not collapse.

The spec (plan section 8) makes `F = sum (D(s_i)/D(e_i) - 1) D(p_i)` the general form and states that `D(s_0) - D(e_n)` holds only at zero payment lag and unit notional, and must not be used otherwise.

**Worked example.** On the 10Y SOFR swap: general floating leg 0.30318064, telescoped 0.30328683, difference 1.062e-04 per unit notional, which matches the spec's "about 1.1e-4". On 10 million that is about 1,060 USD.

The pitfall is subtle because the error is small and one-signed: a book of payer swaps carries a systematic bias that no single trade check flags.

### Q3.9 How is the spot date of an OIS found, and how do SOFR and SONIA differ?

*Level: foundation. Evidence: computed; spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md), [Conventions](../../specifications/01-core/conventions.md), [SONIA OIS](../curves/sonia-ois.md)*

A swap starts on its spot date, a fixed number of business days after the trade date, and each period pays a fixed number of business days after it ends.

`spot = add_business_days(as_of, spot_lag)`, counting from `as_of` itself even when it is not a business day, as QuantLib does. Conventions: `SOFR` has `spot_lag` 2, `payment_lag` 2, calendar `USGS`, fixed leg annual ACT/360; `SONIA` has `spot_lag` 0, `payment_lag` 0, calendar `GBLO`, ACT/365F; `ESTR` has 2 and 2 on `EUTA` (its payment lag of 2 is Strata's choice, ruling R1-2). A one-period swap ends at `add_tenor(spot, tenor)`, modified following; payment is the end plus `payment_lag` business days.

**Worked example.** A 1Y SOFR swap traded on Saturday 2026-11-07 has spot 2026-11-10, end 2027-11-10 and payment 2027-11-15. A 1Y SONIA swap traded on Friday 2026-11-06 starts the same day: SONIA starts 2026-11-06.

What a validator checks: quotes and the bootstrap must use the same convention record. A SOFR quote bootstrapped with SONIA's lags gives a curve that is wrong by days at every pillar.

### Q3.10 What is the difference between the `SEQUENTIAL` and `GLOBAL` bootstrap methods?

*Level: foundation. Evidence: spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md), [Curve framework](../../specifications/02-curves/curve-framework.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

Both solve the same square system, so they must give the same curve. `SEQUENTIAL` solves one pillar at a time in tenor order; `GLOBAL` solves all pillars together by Newton's method.

The OIS spec: the system has one solution in practice, so the two methods agree to solver tolerance and both must stop with every repricing error below 1e-13. For the non-local stage F methods (`MONOTONE_CONVEX`, `MONOTONIC_LOG_CUBIC`, `TENSION_SPLINE`, `HYBRID`) a later pillar moves earlier sections, so `SEQUENTIAL` means "repeat the one-at-a-time solve until every quote reprices" (ruling F-21). A solve that does not converge is `E_NO_CONVERGENCE`. The curve framework's convergence table asserts quadratic convergence for the global Newton solve.

The pitfall: assuming a one-pass sequential bootstrap is exact with a spline. With a non-local method, a single pass leaves the early quotes mispriced once later pillars are set.

### Q3.11 Can a QuantForge curve have negative rates?

*Level: foundation. Evidence: computed; spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md), [Curve framework](../../specifications/02-curves/curve-framework.md)*

Yes. Negative rates are valid market states, and the curve represents them with discount factors above 1.

The OIS spec states: "Negative rates are valid, and give discount factors above 1." The only domain rule on the curve object is `discount_factor > 0`. The monotone convex method likewise returns a negative forward as computed (ruling F-19).

**Worked example.** An ESTR curve from quotes 1Y -0.50% and 2Y -0.30% has a 1Y discount factor 1.0051792491.

What a validator checks: code that takes `log` of a rate, or rejects `D > 1`, breaks on these curves. The positivity checks in the stage F acceptance are statements about the golden SOFR data, not domain rules.

## Overnight compounding

### Q3.12 How is a compounded overnight rate computed from fixings, and why is it above the simple average?

*Level: foundation. Evidence: computed; spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md)*

Each day's interest is added to the balance and earns interest itself, so compounding gives slightly more than averaging the daily rates. A weekend fixing counts for three days.

`rates.ois.compound` returns `(prod(1 + r_i n_i / B) - 1) * B / sum n_i`, with `n_i` the days each fixing applies (integers at least 1) and `B` 360 or 365. Unequal lengths or a day count below 1 are `E_INPUT`.

**Worked example.** Fixings 4.30%, 4.31% (Friday, 3 days) and 4.29% on ACT/360: compounded_rate = 0.0430471957, against a day-weighted simple average 0.0430400000. The gap is about 0.07 bp over five days and grows with the period and the rate level.

The pitfall is weighting every fixing equally. Friday's fixing carries three days of interest, and ignoring that biases the coupon whenever rates move over a weekend.

### Q3.13 How do lookback, observation shift and lockout change a compounded coupon?

*Level: advanced. Evidence: computed; spec. Source: [Overnight compounding](../../specifications/02-curves/overnight-compounding.md), [Stage D rulings](../../specifications/stage-d-rulings.md)*

All three make the coupon known a few days before payment, by using fixings from earlier dates. They differ in which fixing applies to which day and how the days are weighted.

`rates.ois.compound_dated` steps over business days `d_0 = start < ... < d_n = end` of the calendar. `NONE`: rate `r(d_i)`, weight the days to `d_{i+1}`. `LOOKBACK`: rate `r(back(d_i, k))`, weight from the interest period. `OBSERVATION_SHIFT`: rate `r(o_i)` with `o_i = back(d_i, k)`, weight from the observation period `o_{i+1} - o_i`. `LOCKOUT`: `r(d_i)` up to the cut-off `d_{n-k}`, whose fixing then applies to every later day (the ARRC rule; QuantLib's `lockoutDays = k` locks one day earlier, so this spec's `k` is QuantLib's `k-1`, ruling D3). `compounded_rate = (growth - 1) B / sum w_i`, `accrual = (end - start)/B`.

**Worked example.** SOFR from 2026-12-01 to 2027-01-04 (accrual 0.09444444), with fixings 4.30% before 2026-12-10, 4.05% to 2026-12-29 and 3.90% from 2026-12-30:

- NONE 0.04101528
- LOOKBACK 0.04175325 (k = 5)
- OBSERVATION_SHIFT 0.04194205 (k = 5)
- LOCKOUT 0.04123664 (k = 5)

Lookback and shift pull five more days of the old 4.30% rate into the window, so on a falling path they pay more. They differ from each other because shift weights each fixing by the days of the observation period rather than the interest period.

What a validator checks: the method and `k` in the trade confirmation. On a moving rate path, the methods differ by several basis points.

### Q3.14 Why does QuantForge treat Good Friday as a non-business day for SOFR compounding?

*Level: practitioner. Evidence: spec; design. Source: [Overnight compounding](../../specifications/02-curves/overnight-compounding.md), [R1 rulings](../../specifications/r1-rulings.md)*

The fixings exist only on days the administrator publishes. The New York Fed publishes no SOFR on Good Friday, even in years when the bond market had only an early close.

The spec defines the compounding calendar as the convention's calendar, except that for `SOFR` it is `USGS` with every Good Friday a non-business day; it cites no SOFR on 2021-04-02 or 2023-04-07 (ruling R1-6). `start` or `end` not a business day of that calendar is `E_INPUT`, and a needed fixing missing is `E_INPUT`. Extra fixings are ignored.

The pitfall is using the bond calendar as is. On an early-close Good Friday the bond calendar has a business day, the code asks for a SOFR fixing that does not exist, and either fails or invents one.

### Q3.15 How does the ISDA IBOR fallback rate work in QuantForge?

*Level: foundation. Evidence: computed; spec. Source: [Overnight compounding](../../specifications/02-curves/overnight-compounding.md)*

A legacy LIBOR contract that falls back pays the risk-free rate compounded over the LIBOR period plus a fixed spread, set on 2021-03-05, that stands for the old credit and term premium.

`rates.fallback.rate` computes `compounded_rate` as `rates.ois.compound_dated` with `OBSERVATION_SHIFT` and `shift_days` 2, then `fallback_rate = compounded_rate + spread_adjustment`. The spreads in the spec: USD LIBOR 1M, 3M, 6M, 12M on SOFR: 0.0011448, 0.0026161, 0.0042826, 0.0071513; GBP LIBOR on SONIA: 0.0003260, 0.0011930, 0.0027660, 0.0046440. Other indices are `E_SCHEMA`.

**Worked example.** `USD-LIBOR-3M` from 2026-12-01 to 2027-03-01 on the fixings of Q3.13 (3.90% after 2026-12-30): compounded 0.04010613, plus 0.0026161, gives fallback_rate 0.04272223.

What a validator checks: the shift of two business days and the exact spread digits; QuantLib's `OvernightLeg` agrees within 5e-14 on the goldens.

## Interpolation methods

### Q3.16 How do the interpolation methods compare between pillars on the same quotes?

*Level: practitioner. Evidence: computed; spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Interpolation methods](../curves/interpolation-methods.md)*

Every method reprices the six quotes exactly; they disagree between pillars, and they disagree most on the instantaneous forward.

The stage F methods act on the smooth curve `S = D/J` and define `ln S(t)` and `f(t) = -d ln S/dt`. `rates.curve.inspect` reports discount factors, zero rates and instantaneous forwards for any method.

**Worked example.** Each method bootstrapped on the Tutorial 1 quotes, then read on 2032-05-14 (between the 5Y and 7Y pillars); tension 1.0 for the spline:

| Method | Discount factor | Instantaneous forward |
|---|---|---|
| `LOG_LINEAR_DF` | 0.8299260186 | 0.037159 |
| `LINEAR_ZERO` | 0.8302442932 | 0.036636 |
| `MONOTONE_CONVEX` | 0.8303171580 | 0.036539 |
| `MONOTONIC_LOG_CUBIC` | 0.8303236969 | 0.036465 |
| `TENSION_SPLINE` | 0.8303145670 | 0.036519 |

The discount factors differ by up to about 4e-4, so a cash flow of 10 million on that date moves by up to about 4,000 USD with the choice of method. `LOG_LINEAR_DF` has a flat forward per segment and so a sawtooth forward curve; the smooth methods avoid the jumps at pillars.

What the desk cares about: the method is part of the model. Two systems with identical quotes and different interpolations disagree on off-pillar trades.

### Q3.17 Why does QuantForge run monotone convex with `forcePositive = false`?

*Level: advanced. Evidence: spec; design. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

Hagan and West's method is built so that the forward averages exactly to each discrete forward over its section, which makes the curve return its own pillars. QuantLib's positivity collar breaks that property.

The spec implements QuantLib 1.44 `ConvexMonotone` with `quadraticity = 0`, `monotonicity = 1`, `forcePositive = false`, which QuantLib documents as the basic Hagan-West method. Discrete forwards `y_i = (ln S_{i-1} - ln S_i)/(t_i - t_{i-1})`, node forwards weighted by the other interval's length, and five branch rules (a) to (e) per section, each integrating to `y_i`. Ruling F-19: with `forcePositive = true`, the quadratic is shrunk and shifted whenever it has real roots, even outside the section, so the average over the section is no longer `y_i`. On the stage F SOFR pillars `ln S` is then off by up to 0.06 at a node, and QuantLib's own bootstrap fails to bracket the 30Y pillar. A negative forward is returned as computed.

What a validator checks: the outside check is against `ConvexMonotoneInterpolation(0, 1, false)`, forwards within 1e-12, and full SOFR, SONIA and ESTR builds within 1e-10 of QuantLib's piecewise curves.

### Q3.18 What does the tension in `TENSION_SPLINE` control, and what are its limits?

*Level: advanced. Evidence: spec; literature. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Interpolation methods](../curves/interpolation-methods.md)*

Tension pulls a spline towards straight lines between nodes. Low tension gives a smooth cubic spline; very high tension gives piecewise linear `ln D`, the log-linear curve.

The spline is in `ln S`, with `(ln S)'' - sigma^2 ln S` linear in `t` on each interval and natural ends `M_0 = M_n = 0`. `tension` is `sigma` per year. Limits: `sigma -> 0` gives the natural cubic spline in `ln S` (QuantLib `NaturalLogCubicDiscountCurve`), with error `O(sigma^2)`; `sigma -> infinity` gives `LOG_LINEAR_DF`. Checks: `tension` missing is `E_INPUT`; `tension <= 0` or above 1000 is `E_DOMAIN`; other methods ignore it. For `z = sigma h < 1` the spec prescribes series forms based on `shm(x) = sinh x - x` and `chm(x) = cosh x - 1`, so nothing cancels in floating point (ruling F-35, amended; measured agreement 1.2e-14 against 40 digits). The method rests on Schweikert (1966) and Andersen (2007).

The pitfall: implementing `sinh(sigma u)/sinh(sigma h) - u/h` directly. At small `z` it loses about `epsilon / z^2` to cancellation, 4e-8 relative at `z = 1e-3`. There is no outside library for this method; acceptance rests on the two limit cases.

### Q3.19 What is the `HYBRID` interpolation for?

*Level: practitioner. Evidence: computed; spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Meeting steps](../../specifications/02-curves/meeting-steps.md)*

The front of an overnight curve moves in steps on central-bank meeting dates; the back is better smooth. `HYBRID` is flat forwards up to a chosen date and monotone convex after it.

Input `step_end` must equal a pillar date (else `E_INPUT`; missing for `HYBRID` is `E_INPUT`). Segments ending on or before `step_end` use `LOG_LINEAR_DF`; from `step_end` on, `MONOTONE_CONVEX` on the nodes from `step_end` to `t_n`, with `step_end` as its node 0 and its own `f_0` rule, so the forward may jump at `step_end`. If `step_end` is the last pillar the whole curve is `LOG_LINEAR_DF`. Locality: moving a pillar after `step_end` leaves every step segment unchanged.

**Worked example.** With `step_end` at the 2Y pillar, the forward at 2027-06-01 0.034871 is the flat forward of the first segment, the same as plain `LOG_LINEAR_DF` there.

What the desk cares about: with pillars on meeting dates, the step section is a meeting-step curve, and changing the long end does not disturb front-end risk.

### Q3.20 What does locality mean for a curve, and which methods have it?

*Level: advanced. Evidence: spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

Locality asks how far along the curve a change to one pillar spreads. A local method keeps hedges on nearby instruments; a global one spreads risk to distant tenors.

Ruling F-22 states locality on pillar inputs, not quotes, because a bootstrap spreads a quote move over later pillars whatever the method. `LOG_LINEAR_DF`: a pillar affects only its two adjacent segments. `MONOTONE_CONVEX`: changing `S_j` changes `f` only on sections `j - 1` to `j + 2`, elsewhere unchanged to 1e-15. `HYBRID`: a pillar after `step_end` leaves every step segment unchanged; one before changes only its two adjacent step segments. Smoothness: `MONOTONE_CONVEX` and `MONOTONIC_LOG_CUBIC` have continuous `f` (jump at most 1e-12); `TENSION_SPLINE` has continuous `f` and `f'`.

The trade-off: smoother forwards cost locality. In the joint solve, a non-local method gives the Jacobian entries above its diagonal (ruling R6-1.1), so a long quote moves short pillars.

## Turns, meeting steps and futures

### Q3.21 How does QuantForge represent a turn-of-year jump?

*Level: practitioner. Evidence: computed; spec. Source: [Curve framework](../../specifications/02-curves/curve-framework.md), [Meeting steps](../../specifications/02-curves/meeting-steps.md)*

Year-end funding pressure lifts overnight rates for a few days. The curve models it as a one-off multiplicative jump in discount factors, so interpolation never smears it across the year.

`D(d) = S(d) * J(d)`, with `J(d)` the product of jump factors whose date is strictly before `d`. Pillars hold the full `D`; interpolation and extrapolation act on `S = D/J`. A turn is a jump on the last business day of the year with `factor = exp(-s n/365)` for a spread `s` over `n` days, QuantLib's jump rule.

**Worked example.** A 25 bp turn over the three days from 2026-12-31: factor = 0.9999794523. Bootstrapping the Tutorial 1 quotes with this jump, D(2027-01-04) with the jump 0.9943620463, without 0.9943791759. The bootstrap still reprices every quote, so the jump changes how discount is spread between dates rather than the swaps' values.

The pitfall is applying the factor on the jump date itself. The rule is "strictly before": the factor dated 2026-12-31 first applies to 2027-01-01.

### Q3.22 How does a meeting-step curve give its discount factors?

*Level: practitioner. Evidence: computed; spec. Source: [Meeting steps](../../specifications/02-curves/meeting-steps.md)*

The instantaneous overnight forward is flat between central-bank meetings and changes on each meeting date, so the discount factor is the exponential of minus the area under a step function.

`D(d) = exp(-integral_0^t(d) f) * J(d)`, with `f` equal to `base_rate` from `as_of` and each step's `rate` from its date on (a step takes effect on its date), `t = (date - as_of)/365`. `rates.ois.step_curve` also reports the overnight forward in force on each date. Step dates not strictly increasing or not after `as_of` are `E_INPUT`; an empty step list is a flat curve.

**Worked example.** `as_of` 2026-11-06, base 4.30%, steps to 4.05% on 2026-12-10 and 3.80% on 2027-01-28, no jumps: D(2026-12-10) = 0.9960025318, D(2027-02-15) = 0.9887473517. By hand, 34 days at 4.30%, 49 at 4.05% and 18 at 3.80% give `exp(-(0.0430*34 + 0.0405*49 + 0.0380*18)/365)`, hand 0.9887473517.

What a validator checks: QuantLib `ForwardCurve` (backward flat, with jumps) agrees within 2e-15.

### Q3.23 Why does `rates.ois.fit_steps` require one quote between consecutive step dates?

*Level: advanced. Evidence: spec. Source: [Meeting steps](../../specifications/02-curves/meeting-steps.md)*

The rule makes each quote see exactly one new step rate, so the step rates can be solved one at a time and the answer is unique.

With `p_j` the last payment date of quote `j`, `b_0 = as_of`, `b_j` step `j`'s date and `b_{m+1}` infinite, the rule is `b_j < p_j <= b_{j+1}` for every `j`. Quote `j` then depends only on `base_rate` and the first `j` step rates, so the system is triangular. The number of quotes must be `m + 1` for `m` step dates, else `E_INPUT`; breaking the pillar rule is `E_INPUT`; a solve that fails is `E_NO_CONVERGENCE`. Every quote must reprice below 1e-13.

The pitfall: two quotes ending in one inter-meeting window over-determine one rate and leave another free. The joint solve's `OIS_STEPS` curve applies the same counting rule (instruments must number `1 + len(step_dates)` plus its turns).

### Q3.24 What is the futures convexity adjustment, and how big is it?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Futures convexity](../../specifications/02-curves/futures-convexity.md)*

A futures contract settles daily, a forward does not. Daily margining makes a short futures position slightly favourable to its holder, so the futures rate sits above the forward rate, and the gap grows with maturity.

`rates.futures.convexity` uses Hull-White (QuantLib's `HullWhite::convexityBias`): with `d = T - t`, `Bd = (1 - e^{-a d})/a`, `L = (1 - e^{-2 a t})/a`, `Bt = (1 - e^{-a t})/a`, `z = sigma^2/2 * (L Bd^2 + Bd Bt^2)`, `convexity = (1 - e^{-z}) (futures_rate + 1/d)` with `1 - e^{-z}` computed as `-expm1(-z)`; `forward_rate = futures_rate - convexity`. `T <= t` is `E_INPUT`; negative `t`, `sigma` or `a` is `E_DOMAIN`.

**Worked example.** Price 96.25, `t` = 1, `T` = 1.25, `sigma` = 0.01, `a` = 0.03: futures_rate 0.037500, convexity 0.00007311, forward_rate 0.03742689, so 0.731 bp. The same contract starting in five years has an adjustment at 5 years 11.920 bp.

What the desk cares about: the adjustment depends on the model's `sigma` and `a`, so futures-fitted front ends carry model risk. The joint solve uses this exact formula for its `FUTURE` instruments.

## Projection curves and multi-curve

### Q3.25 Why does a term-rate swap need a separate projection curve, and how is it built?

*Level: foundation. Evidence: computed; spec. Source: [Projection and FRA](../../specifications/02-curves/projection-and-fra.md), [Tutorial 8](../getting-started/tutorial-8-multicurve.md), [USD term 3M](../curves/usd-term-3m.md)*

A three-month term rate carries more risk than three months of overnight rates, so its forwards are higher. Multi-curve means forecasting the term rate on one curve and discounting the cash flows on the OIS curve.

`rates.projection.bootstrap` takes a `discount` curve, the index `USD-TERM-3M` (synthetic, kept to test multi-curve code; no market index is implied) and quotes of type `DEPOSIT` (spot to spot + 3M), `FRA` (start `spot + start_months`, end 3M later) and `SWAP` (annual `THIRTY_360_BOND` fixed against quarterly floating, no payment lag). Pillars are at instrument end dates, in order, else `E_INPUT`; solve below 1e-13.

**Worked example.** Discounting on the Tutorial 1 SOFR curve, quotes deposit 3.72%, FRAs 3M and 6M at 3.68% and 3.62%, swaps 2Y 3.58%, 3Y 3.52%, 5Y 3.56%: the first projection pillar 2027-02-10 has P = 0.9901754358, and the projection max error 8.2e-16.

The pitfall: bootstrapping the term curve as if it also discounted. The par rate depends on both curves, so the projection pillars change when the OIS curve changes.

### Q3.26 How is a term swap valued on two curves?

*Level: practitioner. Evidence: computed; spec. Source: [Projection and FRA](../../specifications/02-curves/projection-and-fra.md), [Tutorial 8](../getting-started/tutorial-8-multicurve.md)*

Forward term rates come from the projection curve `P`; every cash flow is discounted on the OIS curve `D`.

Fixed leg annual on `THIRTY_360_BOND`, floating leg quarterly on the same dates, no payment lag. `A = sum alpha_i D(e_i)` over fixed periods; `F = sum (P(s_j)/P(e_j) - 1) D(e_j)` over floating periods; par is `F/A`, and the floating forward runs on accrual dates. `rates.swap.pv` returns `pv = sign * notional * (F - fixed_rate * A)`, +1 for `PAY`.

**Worked example.** On the curves of Q3.25, the 5Y swap has par_rate 0.0356000000 (its quote). Paying 3.66% on 10 million: PV -45269.8463 USD, about 10 bp times the annuity times notional.

What a validator checks: QuantLib's `SwapRateHelper` with exogenous discounting and `MakeVanillaSwap` agree on pillars within 1e-10 and on PVs to about 1e-8 on 1e6.

### Q3.27 How is a FRA valued, and why is it discounted at the forward rate?

*Level: practitioner. Evidence: computed; spec. Source: [Projection and FRA](../../specifications/02-curves/projection-and-fra.md)*

A FRA settles at the start of its period, not the end, so the payment is the interest difference discounted back over the period at the FRA's own forward rate, then discounted to today on the OIS curve.

`rates.fra.pv`: `e = start + 3M`, `F = (P(start)/P(e) - 1)/alpha` (ACT/360), `pv = sign * notional * alpha (F - K) / (1 + alpha F) * D(start)`, +1 for `PAY`.

**Worked example.** A FRA starting 2027-05-10 on the curves of Q3.25 (that is the 6M FRA's start date) has forward_rate 0.03620000, the 6M FRA quote. Paying 3.50% on 10 million: FRA PV 2985.3240 USD.

The pitfall: dropping the `1 + alpha F` divisor. That treats the payment as made at the period end and overstates the PV by about `alpha F`, roughly 0.9% here.

### Q3.28 What is the tenor basis spread, and how does QuantForge compute it?

*Level: practitioner. Evidence: computed; spec. Source: [Projection and FRA](../../specifications/02-curves/projection-and-fra.md)*

The tenor basis is the spread you add to an overnight leg so that it is worth the same as a term-rate leg on the same schedule. It measures how much the market prices term risk above overnight.

`rates.basis.spread` on the quarterly schedule: `sum (P(s)/P(e) - D(s)/D(e)) D(e) / sum alpha D(e)`. The overnight leg here is projected on the discount curve itself.

**Worked example.** On the curves of Q3.25, the 5Y basis: spread = 0.00157256, or 15.73 bp.

What a validator checks: the basis spread has only hand replay as its oracle, no outside library. On a non-business `as_of`, QuantLib's own helpers disagree with each other, so those dates have no outside check either.

### Q3.29 What does `rates.basis.ois_spread` measure?

*Level: practitioner. Evidence: computed; spec. Source: [CSA and basis](../../specifications/02-curves/csa-and-basis.md)*

Two overnight indices in one currency can trade at a spread to each other. This operation gives the spread on leg B that makes it worth leg A, both discounted on one curve.

With OIS periods from the convention, `spread = (F_a - F_b) / A`, `F_x = sum (P_x(s_i)/P_x(e_i) - 1) D(p_i)`, `A = sum alpha_i D(p_i)`. The three curves must share one `as_of`, else `E_INPUT`.

**Worked example.** Projection A bootstrapped from the Tutorial 1 quotes plus 5 bp, projection B and the discount curve the Tutorial 1 curve, 5Y SOFR periods: ois spread 5.0007 bp. It is close to 5 bp but not equal, because the shifted curve's forwards are discounted on the unshifted curve.

What a validator checks: the result equals the difference of QuantLib `MakeOIS` fair rates on the two projection curves within 1e-12.

## CSA, joint solve and funding

### Q3.30 How does CSA discounting work, including collateral in another currency?

*Level: practitioner. Evidence: computed; spec; literature. Source: [CSA and basis](../../specifications/02-curves/csa-and-basis.md), [Stage C rulings](../../specifications/stage-c-rulings.md)*

A collateralised trade earns or pays the collateral rate on its value, so it discounts at that rate. Collateral in a foreign currency brings that currency's OIS rate and the FX forward into the discount factor.

`rates.csa.discount` with `t = (d - as_of)/365`: with no FX, `D(d) = Dc(d) exp(-s t)`, `s` a continuous collateral spread. For a trade in currency X with cash collateral in Y: `D(d) = Dc(d) * spot / F(d) * exp(-s t)`, with `Dc` the OIS curve of Y and `spot`, `F(d)` in units of X per unit of Y. The `fx` key must be present, `null` or an object (ruling C9). Non-positive spot or forward is `E_DOMAIN`; a date with no forward is `E_INPUT`. The approach follows Piterbarg (2010).

**Worked example.** At 2031-11-06 on the Tutorial 1 curve, Dc = 0.8460877400; with a 10 bp collateral spread, D = 0.8418655533. Treating the SOFR curve as Y's collateral curve with spot 1.28 and a forward 1.3150 on that date gives D_X = 0.8235682944.

The pitfall: discounting a USD trade collateralised in another currency on the USD OIS curve. The collateral currency, not the trade currency, sets the discount rate.

### Q3.31 Why do `SEQUENTIAL` and `GLOBAL` give the same answer in `rates.curve.joint_bootstrap`?

*Level: practitioner. Evidence: computed; spec. Source: [CSA and basis](../../specifications/02-curves/csa-and-basis.md), [Joint solve and funding](../../specifications/02-curves/joint-solve-and-funding.md)*

The OIS quotes do not depend on the projection curve, so the system is block triangular: you can solve the discount curve first and then the projection curve on it, or solve everything at once, and land on the same point.

`rates.curve.joint_bootstrap` takes `ois_quotes` and `term_quotes`; every quote must reprice below 1e-13. "The system is block triangular (OIS quotes do not see the projection curve), so `GLOBAL` ... and `SEQUENTIAL` ... give one answer." Either list empty is `E_INPUT`.

**Worked example.** The joint `GLOBAL` build on the Tutorial 1 OIS quotes and the term quotes of Q3.25, compared with the separate bootstrap of Q3.25: largest pillar gap 3.3e-16 in projection discount factors.

What a validator checks: QuantLib's two-step build agrees within 1e-10. The equality fails only if some instrument makes the OIS block depend on the projection curve, which the spec's dependency order forbids.

### Q3.32 How does `rates.curve.joint_solve` produce its Jacobian, and what structure must it have?

*Level: advanced. Evidence: computed; spec; literature. Source: [Joint solve and funding](../../specifications/02-curves/joint-solve-and-funding.md), [Stage F rulings](../../specifications/stage-f-rulings.md), [R6 rulings](../../specifications/r6-rulings.md)*

Risk needs the sensitivity of every curve unknown to every quote. Since the solved curve sets all residuals to zero, the implicit function theorem gives those sensitivities directly, without re-solving for every bumped quote.

`J = -(dR/dx)^{-1} (dR/dq)`, `matrix[i][j] = d unknown_i / d quote_j`, unknowns `ln D` at pillars (or base and step rates, and `ln factor` for turns). `dR/dq` is diagonal: -1 for rate quotes, the spread annuity for `XCCY`, `0.01 e^{-z}` for a `FUTURE` quoted by price. Curves are in dependency order, so `dR/dx` is block lower triangular, and entries for an unknown of one curve against a quote of a later curve are exactly 0 (ruling F-25). Newton stops at `max |R| < 1e-13`; a singular `dR/dx` or 50 iterations is `E_NO_CONVERGENCE` (ruling F-40). Henrard (2014) is the cited source.

**Worked example.** One SOFR curve with 1Y, 2Y and 3Y quotes, log-linear: d ln D(1Y) / d q1 = -1.003286, d ln D(3Y) / d q3 = -3.066479, and d ln D(1Y) / d q3 = 0.0 (a later quote cannot move an earlier log-linear pillar). Per basis point, divide by 10,000.

The acceptance check is bump-and-rebuild with Richardson extrapolation to `|J - ref| <= 1e-9 + 1e-6 |ref|`, with the structural zeros exact. With a non-local method the upper triangle fills in (ruling R6-1.1).

### Q3.33 How are turn-of-year factors solved in the joint solve, and what does `turn_sensitivity` show?

*Level: advanced. Evidence: spec; design. Source: [Joint solve and funding](../../specifications/02-curves/joint-solve-and-funding.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

Instead of typing in a turn size, the desk marks one quote that spans the year end as the turn instrument, and the solve finds the jump factor that reprices it.

A curve may list `turns` (`[{date}]`); each adds an unknown `ln factor` for a jump at that date. A curve with `k` turns must have exactly `k` instruments with `"turn": true`, else `E_INPUT`, and a turn instrument gives no pillar. Labels follow `<name>:turn:<date>`. `turn_sensitivity` is one row per turn: `d model_j / d ln factor` for every instrument, other unknowns held. On an `OIS_STEPS` curve, an instrument whose dates all lie on one side of the turn has exactly 0; on a pillar curve it may not, because pillar unknowns are full `ln D` (ruling F-26, amended). The limit case: the turn factor is 1 when the turn instrument is quoted at the no-turn par rate.

The pitfall: reading a nonzero sensitivity on a pillar curve as a bug. The goldens hold the honest column, and the zero pattern is guaranteed only on step curves.

### Q3.34 How is the funding curve built, and what is it for?

*Level: practitioner. Evidence: computed; spec. Source: [Joint solve and funding](../../specifications/02-curves/joint-solve-and-funding.md), [Funding](../curves/funding.md)*

A bank borrows unsecured at a spread over OIS. The funding curve is the OIS curve times a spread factor; it discounts uncollateralised cash flows and feeds FVA.

`rates.funding.curve`: `D_f(t) = D_ois(t) exp(-integral_0^t s(u) du)` with `s` piecewise flat between quote dates. Quotes are simple ACT/360 rates from `as_of`, `P_f(end) = 1/(1 + rate (end - as_of)/360)`. With `t_i = (end_i - as_of)/365`: `s_i = [ln(D_ois(end_i)/P_f(end_i)) - ln(D_ois(end_{i-1})/P_f(end_{i-1}))] / (t_i - t_{i-1})`; `s` stays at `s_n` beyond the last quote. Spreads may be negative. No quotes or dates out of order: `E_INPUT`; `1 + rate (end - as_of)/360 <= 0`: `E_DOMAIN`.

**Worked example.** On the Tutorial 1 SOFR curve, funding quotes 4.00% to 2027-05-06 and 4.05% to 2027-11-08: s_1 = 0.00528214, s_2 = 0.00544851 (continuous). The 6M SOFR rate is near 3.5%, so about 50 bp of the spread is credit.

The limit case the spec asserts: funding rates equal to the OIS simple rates give spreads of 0.

## Curve fits and stability

### Q3.35 What does the roughness penalty in `calib.curve.smooth` do?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Curve fits](../../specifications/03-calibration/curve-fits.md), [Least squares](../../specifications/03-calibration/least-squares.md)*

An exact fit to noisy zero rates gives jagged forwards. Penalising differences between neighbouring forwards trades a small fitting error for a smoother curve.

Piecewise-flat forwards `f_k` on `(t_{k-1}, t_k]`; model zero `z = B f` (linear). Objective `sum w_j (z(m_j) - y_j)^2 + lambda sum (f_{k+1} - f_k)^2`, solved from the normal equations `(B^T W B + lambda D^T D) f = B^T W y`. `lambda < 0` is `E_DOMAIN`, a maturity past the last knot is `E_INPUT`, a singular system is `E_SINGULAR`. The penalty follows Fisher, Nychka and Zervos (1995).

**Worked example.** Knots and maturities 1, 2, 3, 5, 7, 10 years, zero rates 3.50%, 3.40%, 3.60%, 3.38%, 3.50%, 3.62%:

- lambda 0: 0.03500, 0.03300, 0.04000, 0.03050, 0.03800, 0.03900
- lambda 0.01: 0.03493, 0.03370, 0.03797, 0.03206, 0.03695, 0.03891

With `lambda = 0` the fit is exact, and the 3Y zero rate sitting 20 bp above its neighbours makes the forwards swing by up to 95 bp between adjacent sections. With `lambda = 0.01` the largest swing falls to 59 bp.

What a validator checks: goldens are exact-rational, within 1e-10 plus 1e-8 relative.

### Q3.36 How does `calib.curve.robust` handle an outlier quote?

*Level: advanced. Evidence: computed; spec; literature. Source: [Curve fits](../../specifications/03-calibration/curve-fits.md)*

A single bad quote pulls a least-squares fit towards it. Huber loss is quadratic for small residuals and linear for large ones, so an outlier keeps a bounded influence and is flagged rather than chased.

Nelson-Siegel with fixed `tau`: `z(m) = b0 + b1 e + b2 (e - exp(-m/tau))`, `e = (1 - exp(-m/tau))/(m/tau)`. Residual `r_j = z(m_j) - y_j`; objective `sum rho(r_j)`, `rho(r) = r^2/2` for `|r| <= delta`, else `delta |r| - delta^2/2`. The problem is convex in `b`. Outputs `betas`, `residuals`, `outliers` (0-based indices with `|r_j| > delta`), `objective`. Fewer than 3 points is `E_INPUT`; `tau <= 0` or `delta <= 0` is `E_DOMAIN`. Sources: Nelson and Siegel (1987), Huber (1964).

**Worked example.** Maturities 0.5, 1, 2, 3, 5, 7, 10, 20 years, zero rates 3.60%, 3.52%, 3.41%, 3.36%, 3.37%, 4.00%, 3.52%, 3.65%, `tau` 2.5, `delta` 5 bp: betas 0.038583, -0.001661, -0.013446, outliers [5], and the 7Y point has a residual -56.66 bp (model below the bad quote).

What a validator checks: `outliers` must match exactly, which is why the spec keeps every golden residual at least 1e-6 away from `delta`. SciPy's Huber least squares from three starts agrees within 1e-8.

### Q3.37 What does the calibration stability report measure, and what are its pass thresholds for curves?

*Level: advanced. Evidence: spec; design. Source: [Calibration stability](../../specifications/03-calibration/stability.md), [Calibration stability results](../curves/calib-stability.md), [R2 rulings](../../specifications/r2-rulings.md)*

A calibration can fit its inputs perfectly and still be unstable: tiny input noise can swing its outputs. The report perturbs inputs with seeded noise and measures how much the outputs move.

Seven metrics on seven calibrations, all drawing from `core.rng` (xoshiro256**, seed 20261107, stream = calibration id). S1 refit determinism (bit-identical within a language); S2 cross-language agreement; S3 noise amplification `A = max sample std(output)/a` over 200 draws, with `a` = 0.1 bp for rates; S4 single-input response; S5 parameter stability (reported, never judged); S6 outlier-set stability for the robust fit; S7 repricing under noise. Thresholds: OIS bootstraps C1, C2 need `A <= 3` on zero rates and S7 `<= 1e-12`; Nelson-Siegel bond fit C3 needs `A <= 2` on model prices; smooth fit C4 `A <= 5` on forwards; robust fit C5 `A <= 5` and S6 `>= 0.95`. Least-squares fits are judged on RMS `<= rms_0 + 1.5 a` because noise of size `a` cannot be fitted (ruling R2-A2).

The thresholds are provisional, derived from what each method should do; changing one needs a ruling. A failure is a finding to report, not hide. The report is labelled as a stability check of the method on synthetic inputs, not of any market.
