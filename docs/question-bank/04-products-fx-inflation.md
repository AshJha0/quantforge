# Question bank 4: Fixed income, FX, inflation and financing products

This set checks your understanding of the linear products QuantForge prices off its curves: OIS swaps, fixed-rate bonds and FRNs, repo and Treasury futures, the Nelson-Siegel bond fit behind the rich/cheap screen, FX forwards, swaps, non-deliverable forwards and the cross-currency basis, inflation swaps and linkers, equity forwards with dividends and borrow, commodity forwards with storage, and agency pass-through MBS. It is written for a newcomer who wants to check the ideas and for a practitioner who wants to check QuantForge's exact conventions (day counts, compounding, signs and units). Each answer gives the plain idea, the rule as the specification states it, a worked example where the topic is quantitative, and the pitfall a desk or validator watches for. Levels are marked foundation, practitioner or advanced. Every number in a worked example was produced by running `quantforge_core`; the script [v04_products_fx_inflation.py](verify/v04_products_fx_inflation.py) recomputes each one and checks it is printed here. All data is synthetic. Unless stated otherwise the USD curve is the SOFR curve of [Tutorial 1](../getting-started/tutorial-1-swap.md): quotes 1Y 3.50%, 2Y 3.35%, 3Y 3.30%, 5Y 3.35%, 7Y 3.45%, 10Y 3.60%, `as_of` 2026-11-06, `LOG_LINEAR_DF`.

## Swaps

### Q4.1 How does QuantForge value an OIS swap, and which side has a positive PV when rates rise?

*Level: foundation. Evidence: computed; spec. Source: [OIS curves](../../specifications/02-curves/ois-curves.md), [Tutorial 1](../getting-started/tutorial-1-swap.md)*

A swap's value to the fixed-rate payer is the floating leg it receives minus the fixed leg it pays. When the fixed rate is above the par rate, the payer overpays and the PV is negative.

`rates.ois.pv`: `pv = sign * notional * (F - fixed_rate * A)`, with `sign` +1 for `side` `PAY` (pay fixed, receive the overnight rate) and -1 for `RECEIVE`. `A = sum alpha_i D(p_i)` is the annuity, `F = sum (D(s_i)/D(e_i) - 1) D(p_i)` the floating leg, and the par rate is `F/A`. Outputs are `valuation` (model `OIS_DISCOUNTING`), `par_rate` and `annuity`.

**Worked example.** Paying 3.40% on 10 million USD for 5 years: PV -22955.4220 USD, par 0.0335000000, annuity 4.591084. The check is `-10,000,000 x 0.0005 x 4.591084`. The same trade with `side` `RECEIVE` gives RECEIVE PV 22955.4220.

The pitfall: `side` refers to the fixed leg. Reading `PAY` as "pay floating" flips every sign in a risk report.

### Q4.2 What is DV01 in QuantForge, and how is it computed?

*Level: foundation. Evidence: computed; spec. Source: [Tutorial 1](../getting-started/tutorial-1-swap.md), [Rates sensitivities](../../specifications/06-risk/rates-sensitivities.md)*

DV01 is the change in value for a one basis point move in rates. QuantForge moves the market quotes, not the curve, and rebuilds the curve each time, so the number is what a trader sees when the quotes move.

The DV01 is a central difference: rebuild the curve with every quote 1 bp up and 1 bp down, reprice, and take half the PV difference. `key_rates` gives the same split per quote. For a payer swap DV01 is positive: paying fixed gains when rates rise.

**Worked example.** The 5Y payer swap of Q4.1: DV01 4597.7356 USD per bp, of which the 5Y key rate 4594.4422. The rule of thumb `notional x annuity x 1bp` gives 4591.08; it is a first-order shortcut that ignores how the bump also changes the annuity and the floating leg.

What the desk cares about: a parallel DV01 hides curve risk. A 5Y swap's risk sits almost entirely on the 5Y quote here, but a trade between pillars spreads across two.

## Bonds

### Q4.3 How does QuantForge price a fixed-rate bond off a curve, and how is accrued interest computed?

*Level: foundation. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md), [Tutorial 2](../getting-started/tutorial-2-bonds-repo.md)*

A bond is a list of known cash flows, so its fair dirty price is each flow times the discount factor for its date. The quoted clean price takes out the coupon interest already earned since the last coupon.

`bond.price.from_curve`: `dirty = sum CF_k D(d_k) / D(settlement)`, valued at the curve's `as_of` and carried to settlement. Face is 100, coupon `c = 100 coupon / frequency`, `accrued = c (settlement - prev)/(next - prev)` in actual days (ACT/ACT ICMA), `clean = dirty - accrued`. Settlement before the curve's `as_of` is `E_OUT_OF_RANGE`.

**Worked example.** A 4.25% semi-annual bond maturing 2029-11-15, settling 2026-11-09: dirty 104.697813, accrued 2.055707, clean 102.642107. The bond pays 4.25% on a curve near 3.4%, so it trades above par.

The pitfall: comparing a clean price to a curve value. The curve gives dirty prices; the accrued must come off first.

### Q4.4 What yield does `bond.yield.from_price` return, and with what compounding?

*Level: foundation. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md), [Tutorial 2](../getting-started/tutorial-2-bonds-repo.md)*

The yield is the single rate that, used to discount every cash flow, gives the market price. It summarises the price in rate terms, compounded at the bond's own coupon frequency.

With `v = 1/(1 + y/f)` and cash flow `k` at exponent `k + w`, `w = (next - settlement)/(next - prev)`: `dirty = sum CF_k v^(k+w)`. The yield is the `y` whose clean price equals `clean_price`; price falls strictly in `y`, so the yield is unique. `clean_price <= 0` or a non-positive dirty price is `E_DOMAIN` (ruling D43). This is QuantLib's `BondFunctions` with ACT/ACT ICMA and `Compounded`.

**Worked example.** At the curve clean price of Q4.3: yield 0.0332199717, semi-annually compounded.

The pitfall: comparing this yield directly with the curve's continuous zero rates. They differ in compounding as well as in being an average over all cash flows.

### Q4.5 How are Macaulay duration, modified duration and convexity defined, and how good is the second-order price approximation?

*Level: practitioner. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md), [Tutorial 2](../getting-started/tutorial-2-bonds-repo.md)*

Duration is the price sensitivity to the bond's yield; convexity is the curvature that duration misses. Together they predict the price after a yield move.

`macaulay_duration = sum ((k+w)/f) CF_k v^(k+w) / dirty`, `modified_duration = macaulay_duration * v`, `convexity = sum ((k+w)(k+w+1)/f^2) CF_k v^(k+w+2) / dirty`. All are per unit price, in years and years squared.

**Worked example.** For the bond of Q4.3 at its yield: Macaulay 2.809012, modified 2.763116, convexity 9.390443. For a 10 bp rise in yield, repricing gives exact 104.40901171, and `dirty (1 - D_mod dy + C dy^2 / 2)` gives approximation 104.40901235 (computed with a scratch formula, not the library).

What the desk cares about: modified duration is a yield sensitivity, not a curve DV01. A curve move that is not parallel changes the price differently from a yield move.

### Q4.6 What simplifications does the QuantForge bond object make?

*Level: foundation. Evidence: spec; design. Source: [Bonds](../../specifications/04-pricing/bonds.md), [Stage D rulings](../../specifications/stage-d-rulings.md), [Edge-case register](../../specifications/edge-case-register.md)*

The bond object is deliberately plain so that every implementation agrees exactly. Real bonds have features it leaves out, and you should know which.

`bond` is `{maturity, coupon, frequency}` with `frequency` 1, 2 or 4 (else `E_SCHEMA`), face 100 redeemed at 100. Coupon dates step back from maturity by `12/frequency` months, unadjusted, with no business-day rule (ruling D13); a month-end maturity keeps every coupon on month end. Every period is regular: no odd first coupon. `settlement >= maturity` is `E_DATE_ORDER`. Not modelled: ex-dividend periods (gilts trade ex-dividend for 7 business days, edge register E9), settlement lags beyond the date you pass, and call features. The rich/cheap workflow drops gilts inside their ex-dividend period for this reason.

The pitfall: pricing a bond with a long or short first coupon through this object gives a wrong accrued and a wrong price without any error.

### Q4.7 What is the Z-spread, and how is it computed?

*Level: practitioner. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md)*

The Z-spread is the constant spread added to the curve's zero rates that makes the curve price equal the market price. A bond that is cheap to the curve has a positive Z-spread.

`Ds(d) = D(d) exp(-z t(d))`, `t(d) = (d - as_of)/365`, and `dirty = sum CF_k Ds(d_k) / Ds(settlement)`. `bond.spread.z` solves for `z` with dirty equal to `clean_price + accrued`; it is unique because dirty falls in `z`. It equals QuantLib's `BondFunctions.zSpread` with `Continuous` and ACT/365F.

**Worked example.** The bond of Q4.3 priced 1.00 below its curve clean price: z_spread 0.00341421, or 34.14 bp continuous. As a rough check, one point on a dirty price near 104.7 with modified duration near 2.76 is about `1 / (104.7 x 2.76)`, roughly 35 bp of yield.

The pitfall: the spread is continuous and ACT/365F. Comparing it with a semi-annual yield spread mixes conventions.

### Q4.8 How does QuantForge compute a par-par asset swap spread?

*Level: practitioner. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md)*

In a par-par asset swap, an investor buys the bond at par and swaps its fixed coupons for floating plus a spread. The spread pays back the gap between the bond's curve value and its market price, spread over the floating leg's annuity.

`bond.spread.asset_swap`: floating dates step back quarterly from maturity, unadjusted, the first period from settlement. `annuity = sum ((e_j - s_j)/360) D(e_j) / D(settlement)`; `spread = (P_curve - dirty_price) / (100 annuity)`, with `P_curve` the `from_curve` dirty price. With an OIS curve the result is the bond-OIS spread. The annuity is the floating leg's, not the bond's fixed leg.

**Worked example.** The bond of Q4.3 at a dirty price 1.00 below its curve value: annuity 2.899243, spread 0.00344918, about 34.5 bp.

The pitfall: using the fixed-leg annuity (ACT/ACT, semi-annual) instead of the floating annuity (ACT/360, quarterly). The spec names this explicitly.

### Q4.9 Why does a floating-rate note price at par, and what does the discount margin do?

*Level: practitioner. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md)*

A floater resets its coupon to the market rate each period, so on a reset date, with no margin and the same curve projecting and discounting, it is worth exactly par. The discount margin is the extra spread a buyer demands, which pulls the price below par.

`bond.frn.price`: later periods pay `(P(s)/P(e) - 1)/alpha + margin` with `alpha = days/360`; with `Dm(d) = D(d) exp(-dm t(d))`, `dirty = [sum 100 (r_i + margin) alpha_i Dm(e_i) + 100 Dm(T)] / Dm(settlement)`. The spec states the identity: on a coupon date, at `margin = dm = 0`, with one curve and `current_rate` its forward, `dirty = 100`.

**Worked example.** A quarterly FRN maturing 2029-11-09, settling on its coupon date 2026-11-09, projected and discounted on the SOFR curve, current rate the curve forward: FRN dirty 100.000000. A discount margin of 50 bp gives dm 50 bp dirty 98.576455.

What a validator checks: the par identity is the FRN's acceptance test. A build that fails it has a date or accrual mismatch between the coupon and the discount factors.

## Repo and bond futures

### Q4.10 How is a repo forward price computed?

*Level: foundation. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md), [Tutorial 2](../getting-started/tutorial-2-bonds-repo.md), [Repo](../curves/repo.md)*

A repo is a sale today with an agreed buy-back. The buy-back (forward) price is today's dirty price grown at the repo rate, less any coupons paid in between, which go to the seller and are also reinvested at repo.

`repo.forward`: `forward_dirty = dirty (1 + r (end-start)/360) - sum c (1 + r (end-d)/360)` over coupons in `(start, end]`, with `r` simple ACT/360; `forward_clean = forward_dirty - accrued(end)`; `interest = dirty r (end-start)/360`. `end <= start` is `E_DATE_ORDER`; `end >= maturity` is `E_INPUT`.

**Worked example.** The bond of Q4.3 financed for 30 days from 2026-11-09 at 3.85%: forward dirty 102.903264, forward clean 102.621496, interest 0.335905. No coupon falls in the window, so the forward dirty is just the dirty price plus interest.

The pitfall: growing the clean price. Repo cash is lent against the dirty price, and the accrued at the end date is different from the start.

### Q4.11 How is the implied repo rate recovered from a forward price?

*Level: practitioner. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md), [Tutorial 2](../getting-started/tutorial-2-bonds-repo.md)*

The forward price formula is linear in the repo rate, so given a forward price you can solve for the rate in closed form, with no root finder.

`repo.implied_rate` inverts `repo.forward`: `r = (forward_dirty + sum c - dirty) / (dirty (end-start)/360 - sum c (end-d)/360)`. The futures basis uses the same expression with the invoice price in place of the forward dirty price.

**Worked example.** Feeding the forward clean of Q4.10 back in returns implied repo 0.0385000000, the rate that produced it.

What a validator checks: round trip `forward` then `implied_rate` must return the input rate; the denominator can be zero only in a degenerate case, which is `E_DOMAIN`.

### Q4.12 What is special repo, and how does QuantForge value specialness?

*Level: practitioner. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md)*

A bond in high demand can be borrowed only by lending cash at a rate below general collateral (GC). The gap is the special spread, and its value is the cheaper financing earned on the bond's dirty price.

`repo.forward` takes `gc_rate` (a number or `null`; the key is required). `special_spread = gc_rate - r`, `specialness_value = dirty (gc_rate - r)(end-start)/360`; both are `null` when `gc_rate` is `null`.

**Worked example.** The bond of Q4.3 for 30 days at a special rate of 3.60% against GC 3.85%: special_spread 0.0025, specialness_value 0.021812 per 100 face.

What the desk cares about: specialness is why an on-the-run issue looks rich in a fitted-curve screen. The rich/cheap workflow excludes on-the-run Treasuries from its fit for this reason.

### Q4.13 How is a Treasury futures conversion factor computed?

*Level: practitioner. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md), [R1 rulings](../../specifications/r1-rulings.md)*

The conversion factor puts deliverable bonds on a common footing: it is roughly the price per unit face of the bond at a 6% yield on the first day of the delivery month.

`bond.futures.conversion_factor`, the CME formula: coupon rounded to the nearest 1/8 of 1%, ties up; `n` whole years and `z` whole months from the first day of `delivery_month` to maturity, with `z` rounded down to a multiple of 3 for `TEN_YEAR`, `ULTRA_TEN_YEAR`, `BOND`, `ULTRA_BOND` (whole months for the 2Y, 3Y and 5Y contracts, ruling R1-3). `v = z` if `z < 7` else `z - 6`; `a = 1.03^(-v/6)`; `b = (c/2)(6-v)/6`; `C = 1.03^(-2n)` or `1.03^(-2n-1)`; `CF = a (c/2 + (c/0.06)(1 - C) + C) - b`, rounded to 4 decimals. `notional_coupon` must be 0.06 and the bond semi-annual, else `E_INPUT`. Basket eligibility is not checked.

**Worked example.** For March 2027 delivery on the `TEN_YEAR` contract: 4.25% of 2034-11-15 CF 0.8955; 4% of 2035-08-15 CF 0.8713; 4.5% of 2036-02-15 CF 0.8990.

The pitfall: forgetting the 3-month rounding of `z` for the long contracts, which changes the factor in the third or fourth decimal.

### Q4.14 How does QuantForge pick the cheapest-to-deliver bond?

*Level: advanced. Evidence: computed; spec. Source: [Bonds](../../specifications/04-pricing/bonds.md), [R6 rulings](../../specifications/r6-rulings.md)*

The short futures holder delivers whichever bond is cheapest. The standard test is the implied repo rate: the return from buying the bond, delivering it into the futures, and earning the invoice price. The highest implied repo marks the cheapest to deliver.

`bond.futures.basis`, with `T = (delivery - settlement)/360`: `invoice = F CF + accrued(delivery)`, `gross_basis = clean - F CF`, `net_basis = forward_dirty - invoice` (repo forward at `r`), `implied_repo = (invoice + sum c - dirty) / (dirty T - sum c (delivery - d)/360)`. `ctd` is the 0-based index of the highest implied repo.

**Worked example.** The three bonds of Q4.13, priced off the SOFR curve on 2026-11-09, delivery 2027-03-31, repo 3.85%. The futures price is set at the lowest `forward_clean / CF` less 2/32, as ruling R6-7.2 does for its golden: futures price 117.096709. Then, bond by bond:

- implied repo 0.037149, net basis 0.055968
- implied repo 0.008599, net basis 1.221183
- implied repo -0.002792, net basis 1.750719

so ctd 0. The CTD has the smallest net basis and the highest implied repo, just under the 3.85% market repo.

What a validator checks: the spec keeps every golden's implied repos at least 1e-6 apart so the CTD index is unambiguous. Delivery options (timing, quality, wild card) are not modelled.

## Bond curve fits and rich/cheap

### Q4.15 How does `bond.fit.nelson_siegel` fit a government curve, and why weight by `1/D_mod^2`?

*Level: advanced. Evidence: computed; spec; literature. Source: [Bonds](../../specifications/04-pricing/bonds.md), [Workflow (b) rich/cheap](../../specifications/04-pricing/workflow-b-rich-cheap.md), [Bond fit](../curves/bond-fit.md)*

A Nelson-Siegel curve has three parameters, so it cannot pass through every bond. The fit finds the smooth curve closest to all prices, and the leftover residuals are the relative-value signal.

Zero rate `z(t) = b0 + b1 e + b2 (e - exp(-t/tau))`, `e = (1 - exp(-t/tau))/(t/tau)`, `t = (d - settlement)/365`; model dirty `sum CF exp(-z(t) t)`; minimise `sum w (model - dirty_price)^2` with fixed `tau`. Outputs `betas` and `residuals` (model minus market, for every bond, including those with weight 0). Fewer than 3 positive weights is `E_INPUT`, `tau <= 0` is `E_DOMAIN`. The rich/cheap workflow uses `tau` 2.5 years and `w = 1/D_mod^2`: a price error divided by duration is about a yield error, so the fit is in yields, as Gurkaynak, Sack and Wright (2007) and the Bank of England method do (ruling R2-A5).

**Worked example.** Six bonds maturing 2028 to 2035 priced off the SOFR curve, with the 3.5% of 2031-11-15 marked 0.30 below its curve price; weights `1/D_mod^2`, `tau` 2.5: betas 0.042347, -0.005687, -0.021013, and the 2031 bond's residual 0.192104.

The pitfall: equal weights. Long bonds have large price errors for small yield errors and would dominate an unweighted price fit.

### Q4.16 How do you read a fit residual as rich or cheap?

*Level: practitioner. Evidence: computed; spec. Source: [Workflow (b) rich/cheap](../../specifications/04-pricing/workflow-b-rich-cheap.md), [Rich/cheap](../curves/rich-cheap.md)*

If the curve says a bond should cost more than the market price, the bond is cheap; if less, it is rich. Converting the price gap to a yield gap makes bonds of different maturity comparable.

The workflow: `price_residual = residual` per 100, model minus market dirty; positive means cheap. `model_clean = market_clean + residual`; `yield_residual_bp = (market yield - model yield) x 10,000`, both yields from `bond.yield.from_price`. Rank by yield residual within maturity buckets 1-3, 3-7, 7-15 and 15+ years.

**Worked example.** For the 2031 bond of Q4.15: residual 0.192104 per 100, so cheap, and yield_residual_bp 4.19. The fit absorbs part of the 0.30 shock into its parameters, which is why the residual is below 0.30, and spreads a little error onto the other bonds: largest other residual 0.080316.

The pitfall: reading a residual as a trade. The report label says it plainly: fitted-curve residuals from end-of-day reference prices, not executable prices, tradability not established.

### Q4.17 Which bonds does the rich/cheap workflow exclude, and why can it not run daily?

*Level: practitioner. Evidence: spec; design. Source: [Workflow (b) rich/cheap](../../specifications/04-pricing/workflow-b-rich-cheap.md), [R2 rulings](../../specifications/r2-rulings.md)*

A curve fit is only as good as the bonds in it. Bonds with features or premia the model does not capture are dropped or given weight 0, and the job is honest about missing data.

Kept: fixed-coupon nominal bonds with at least 1 year to maturity. Dropped and listed: bills, FRNs, TIPS and index-linked gilts, STRIPS, callable or rump issues, any bond whose `bond.yield.from_price` errors, and gilts inside their ex-dividend period. Treasury on-the-run and first off-the-run issues in each auction tenor are fitted with weight 0 but still reported, because their liquidity premium biases the fit (ruling R2-A6). Data: TreasuryDirect's `robots.txt` disallows automated clients and the DMO gilt page sits behind an anti-bot challenge; neither may be scraped. Without a manual `--data` directory the job writes a report marked "BLOCKED: no price data" and exits 0, a known state rather than a failure. Checks: fit RMS below 0.25 per 100 (warn), at least 20 bonds per market (fail).

What a validator checks: that the daily acceptance is listed as open in the README known issues, as the spec requires.

## FX

### Q4.18 What does a `GBPUSD` rate mean, and how is the FX spot date found?

*Level: foundation. Evidence: computed; spec. Source: [FX](../../specifications/02-curves/fx.md), [Conventions](../../specifications/01-core/conventions.md), [GBPUSD FX forward](../curves/gbpusd-fx-forward.md)*

A rate of 1.28 for `GBPUSD` means 1 GBP (base) costs 1.28 USD (quote). Spot trades settle two business days later, counting only days open in both centres.

`fx.spot_date` steps forward `spot_lag` days, counting only days that are business days on both calendars of the pair. `GBPUSD`: `spot_lag` 2, calendars `GBLO` and `USGS`, `pip` 0.0001. An unknown pair is `E_SCHEMA`.

**Worked example.** Traded on Friday 2026-11-06: spot date 2026-11-10.

The pitfall: counting on one calendar. A UK holiday that is a US business day still delays GBPUSD spot.

### Q4.19 How does QuantForge compute an FX forward from two discount curves?

*Level: foundation. Evidence: computed; spec. Source: [FX](../../specifications/02-curves/fx.md), [Tutorial 9](../getting-started/tutorial-9-fx.md)*

By no-arbitrage, converting today and investing in the quote currency must equal investing in the base currency and converting forward. The currency with the higher rate trades at a forward discount.

With `sp` the spot date: `A(T) = D_base(T)/D_base(sp)`, `B(T) = D_quote(T)/D_quote(sp)`, `F(T) = S A(T)/B(T)`. Both are measured from spot because quoted spot settles on `sp`. `points = (F - S)/pip`. A value date before `sp` is `E_DATE_ORDER`; curves with a different `as_of` are `E_INPUT`.

**Worked example.** Spot 1.2800; GBP curve bootstrapped from SONIA quotes 1Y 4.00%, 2Y 3.85%, 5Y 3.75%; USD the SOFR curve. For value date 2027-11-10: forward 1.274470, points -55.30. GBP rates are higher, so GBP trades at a forward discount.

The pitfall: measuring discount factors from `as_of` instead of spot. That adds two days of rate differential to every forward.

### Q4.20 How are an FX forward's PV and FX delta defined?

*Level: foundation. Evidence: computed; spec. Source: [FX](../../specifications/02-curves/fx.md)*

A forward to buy base currency at strike K gains if the market forward is above K. The gain is paid on the value date, so it is discounted on the quote currency's curve.

`fx.forward.pv`: `pv = sign * N * (F - K) * D_quote(T)` in quote currency, +1 for `BUY` of base. `fx_delta = dPV/dS = sign * N * (F/S) * D_quote(T)`, in base units, with curves held fixed.

**Worked example.** Buying 1 million GBP for 2027-11-10 at 1.2700 on the market of Q4.19: FX PV 4315.49 USD, fx_delta 961190.61 GBP. The delta is below the notional because it is `N (F/S) D_quote(T)`, the present value of 1 million GBP delivered a year from now.

What the desk cares about: the delta is in base units and assumes rates fixed. Rate risk on the two curves is separate.

### Q4.21 How is an FX swap valued, and what risk does an at-market swap carry?

*Level: practitioner. Evidence: computed; spec. Source: [FX](../../specifications/02-curves/fx.md)*

An FX swap is two forwards in opposite directions. When both legs are struck at market, the PV is zero and the spot risk almost cancels, leaving mostly the interest-rate differential.

`fx.swap.pv`: trade `{notional_base, near_date, near_rate, far_date, far_rate, far_side}`, the near leg the opposite side to the far leg. `valuation` and `fx_delta` are the sums of the two legs. `near_date >= far_date` is `E_DATE_ORDER`.

**Worked example.** Sell 1 million GBP spot at 1.2800 on 2026-11-10 and buy it back on 2027-11-10 at the forward 1.274470 of Q4.19: swap PV 0.00, swap fx_delta -38427.32 GBP. The residual delta exists because the far leg's GBP is worth less today than the near leg's.

The pitfall: treating an FX swap as risk-free. Its main risk is the rate differential between the two currencies.

### Q4.22 How does `fx.curve.implied` turn forward points into a basis?

*Level: advanced. Evidence: computed; spec. Source: [FX](../../specifications/02-curves/fx.md)*

If the market's forward points disagree with the two OIS curves, the difference is the cross-currency basis. This operation reads it straight from the quotes.

Value date `sp` plus tenor (months, day clipped), modified following on the pair's first calendar, then moved forward until a business day on both. `F = S + points * pip`. `implied_ratio = (F/S) B(T)`, the base growth the quotes imply. With `tau = (T - sp)/365`: `basis_bp = 10000 (-ln(implied_ratio)/tau + ln(A(T))/tau)`. Tenors must be in `M` or `Y` (else `E_SCHEMA`) and in order (else `E_INPUT`).

**Worked example.** On the market of Q4.19, 12M points of -60.0 instead of the curve-implied -55.30: implied_ratio 0.96120314, basis_bp 3.69. The quoted points imply a GBP rate about 3.7 bp above GBP OIS.

The limit: this gives the basis at each quoted tenor, not a curve. A curve from basis swaps is `fx.xccy.bootstrap`, with the caveat in Q4.23.

### Q4.23 What is the cross-currency basis curve in QuantForge, and what must it never be called?

*Level: advanced. Evidence: spec; design. Source: [Cross-currency](../../specifications/02-curves/cross-currency.md), [R1 rulings](../../specifications/r1-rulings.md), [Cross-currency curve](../curves/cross-currency.md)*

Foreign cash flows collateralised in USD discount on a basis-adjusted foreign curve, not on the foreign OIS curve. Basis swap quotes pin that curve down. QuantForge builds it from a simplified swap, and says so.

A leg on notional `N`: `L = N [sum ((P(s_i)/P(e_i) - 1) + m alpha_i) D(e_i) + D(T) - D(start)]`, quarterly on the joint calendar, `alpha = days/360`. `fx.xccy.bootstrap` solves the foreign (EUR) discount curve so that `L_foreign = 0` at each quoted spread, with the USD SOFR-flat leg worth 0 on its own curve; quotes reprice below 1e-13. `fx.xccy.pv`: `pv = sign (spot foreign_leg - domestic_leg)` in USD, +1 for `RECEIVE_FOREIGN`. Ruling R1-1: this is a constant-notional swap, a synthetic instrument. The market EUR/USD basis swap resets the USD notional each period (mark-to-market), so the curve solved here is not the market xccy-implied curve and must never be described as one. The reset variant is row E13 of the edge-case register.

What a validator checks: the label. A report that calls this curve "the market EUR basis curve" is wrong, whatever the numbers.

### Q4.24 How is a non-deliverable forward valued?

*Level: advanced. Evidence: computed; spec. Source: [Cross-currency](../../specifications/02-curves/cross-currency.md)*

An NDF on a restricted currency settles the difference in USD, so the payoff is nonlinear in the rate: buying USD forward at strike K against a currency quoted per USD pays `N (1 - K/X)` USD. Its value is still closed form, because `1/X` is a USD-priced asset.

`fx.ndf.pv`: `F = fixing` if given, else `spot D_usd(p) / D_off(p)`; `pv = sign N (1 - K/F) D_usd(p)`, +1 for `BUY` (buy USD forward). `payment_date < fixing_date` is `E_DATE_ORDER`; `fixing_date <= as_of` with no fixing is `E_INPUT`; non-positive spot, fixing or strike is `E_DOMAIN`.

**Worked example.** Spot 83.50 per USD, offshore curve bootstrapped from quotes 6.50% and 6.40% (SOFR conventions, synthetic), fixing 2027-05-06, payment 2027-05-10, buying 1 million USD at 85.00: NDF forward 84.734301, NDF PV -3080.74 USD. The strike is above the forward, so buying USD there loses.

The pitfall: valuing `N (F - K)/K` or `N (F - K)/F` with the wrong denominator. The spec's form `N (1 - K/F)` is exact.

## Inflation

### Q4.25 How is a CPI curve built from zero-coupon inflation swaps, and how does seasonality enter?

*Level: foundation. Evidence: computed; spec. Source: [Inflation](../../specifications/02-curves/inflation.md), [Tutorial 10](../getting-started/tutorial-10-inflation-commodities.md), [Inflation curve](../curves/inflation.md)*

A zero-coupon inflation swap of `n` years at rate `K` fixes the expected index `n` years out: `I_0 (1 + K)^n`. Between pillars the log index is linear; seasonal factors then add the within-year pattern without disturbing the pillars.

The curve is `{base_month, base_cpi, quotes: [{years, rate}], seasonality}`; `base_month` already carries the index lag. Pillar `I(b + 12n) = I_0 (1 + K)^n`, whatever the discount curve. `ln I` is linear in the month index between pillars, and the last slope carries on. With 12 seasonal factors, `I(k) = I_smooth(k) s(k)/s(b)`; pillar months fall in the base month's calendar month, so the factors cancel there. Years not strictly increasing positive integers: `E_INPUT`; `rate <= -1`: `E_DOMAIN`; a month before base: `E_OUT_OF_RANGE`.

**Worked example.** Base August 2026 at 320.0, quotes 1Y 2.5%, 2Y 2.6%, 5Y 2.55%: I(2028-08) = 336.856320 (`320 x 1.026^2`) and I(2027-02) = 323.975308. With seasonal factors (February 0.999, August 1.000): seasonal I(2028-08) = 336.856320, unchanged, and seasonal I(2027-02) = 323.651332.

What a validator checks: every quote reprices with and without seasonality. No outside library is run, because QuantLib's inflation curves use other lag and interpolation conventions.

### Q4.26 How is a zero-coupon inflation swap valued?

*Level: practitioner. Evidence: computed; spec. Source: [Inflation](../../specifications/02-curves/inflation.md)*

At maturity one side pays the realised index growth minus 1, the other `(1 + K)^n - 1`. The notional exchange of 1 cancels, so the PV is the gap between the two growth factors, discounted.

`infl.zcis.pv`: `index_ratio = I(b + 12 years)/I_0`; `pv = sign N (index_ratio - (1 + K)^years) D(payment_date)`, +1 for `RECEIVE_INFLATION`.

**Worked example.** On the curve of Q4.25, receiving inflation on a 5-year swap at 2.50% on 10 million, paid 2031-11-10, discounted on the SOFR curve: index_ratio 1.13417044, ZCIS PV 23362.09 USD. The curve's 5Y rate is 2.55%, so receiving inflation against 2.50% is worth a little.

The pitfall: discounting from the index month rather than the payment date. The index month is lagged; the cash moves on `payment_date`.

### Q4.27 How does QuantForge price an inflation-linked bond from a real yield?

*Level: advanced. Evidence: computed; spec. Source: [Inflation](../../specifications/02-curves/inflation.md), [R6 rulings](../../specifications/r6-rulings.md), [Real USD Treasury](../curves/real-usd-treasury.md)*

A linker pays real coupons scaled by the index ratio, the reference CPI on the settlement date divided by the reference CPI at issue. Price the real bond at its real yield, then scale by the index ratio.

Reference CPI for a date `d` in month `m`: `ref(d) = I(m-3) + (day(d) - 1)/days_in_month(m) (I(m-2) - I(m-3))`, the US TIPS rule. `infl.linker.price` rounds as Treasury does (ruling R6-7.5, 31 CFR Part 356 Appendix B): truncate to six decimals, then round half up to five; the index ratio is formed from the rounded reference CPI. `real_clean` and `real_accrued` come from `bond.price.from_yield` at the real yield; nominal values are the real ones times `index_ratio`. A missing fixing is `E_INPUT`. No deflation floor in this stage.

**Worked example.** A 1.25% linker maturing 2034-07-15, settling 2026-11-10 at a 1.80% real yield, base reference CPI 300.0, CPI fixings August 321.123456789 and September 321.987654321: ref_cpi 321.38272, index_ratio 1.07128, real_clean 96.071089, nominal_clean 102.919036.

The pitfall: rounding the index ratio from the unrounded reference CPI. The order is prescribed, and getting it wrong moves the fifth decimal of the ratio.

## Equity forwards, dividends and borrow

### Q4.28 How does QuantForge compute an equity forward with cash dividends and a borrow fee?

*Level: foundation. Evidence: computed; spec. Source: [Equity forward](../../specifications/02-curves/equity-forward.md), [Stage C rulings](../../specifications/stage-c-rulings.md), [Equity forward page](../curves/equity-forward.md)*

Holding the stock costs funding and earns the stock-loan fee, so the stock grows at `r - b`. Each dividend is cash that leaves the forward, carried on the same factor.

Carry factor `C(t) = D(t)/B(t)`; `F(T) = S/C(T) - sum_i A_i C(t_i)/C(T)` over dividends with `as_of < ex_date_i <= expiry`. With flat rates, `F = S e^{(r-b)T} - sum A_i e^{(r-b)(T-t_i)}`. The spec's rule, in bold there: dividends are carried on `C`, never discounted on `D` (ruling C2). A dividend on expiry counts. Option PVs discount on the funding curve `D` only.

**Worked example.** The spec's check case through `eq.forward.flat`: spot 100, `r` 4%, `b` 5%, a dividend of 2 at 0.5 years, `T` 1: F = 97.0149584. The wrong form `(S - PV_r(div)) e^{(r-b)T}` gives wrong form 97.0640923 (computed with a scratch formula, not the library).

The pitfall the spec names: the wrong pair of curves gives a plausible number. The two forms agree only when `b = 0`.

### Q4.29 How is a forward implied from option prices by put-call parity?

*Level: practitioner. Evidence: computed; spec. Source: [Equity forward](../../specifications/02-curves/equity-forward.md)*

Call minus put at the same strike is a forward contract: `C - P = D (F - K)`. Across several strikes, a line through those differences gives both the forward and the discount factor.

`eq.forward.parity`: mids `c_i`, `p_i`, `y_i = c_i - p_i`. With a given discount factor, `F = mean(K_i + y_i/D)`. With `null`, regress `y = a + s K` by ordinary least squares: `D = -s`, `F = a/D`. Also reported: `max_residual` and `outside_spread`, the strikes where `D (F - K)` lies outside `[call_bid - put_ask, call_ask - put_bid]`. One quote with `null` discount factor is `E_INPUT`; a fitted `D <= 0` or `F <= 0` is `E_DOMAIN`.

**Worked example.** Strikes 90, 100, 110 with call mids 12.20, 5.70, 1.90 and put mids 2.00, 5.25, 11.30, discount factor left free: parity forward 100.425170, parity discount factor 0.980000.

What a validator checks: `outside_spread` flags strikes whose quotes contradict the fitted parity line, the first sign of a stale quote. American options are out of scope (ruling C1), so no de-Americanisation is applied.

### Q4.30 How are dividends implied from index futures, and a borrow rate from a forward?

*Level: advanced. Evidence: computed; spec. Source: [Equity curves](../../specifications/02-curves/equity-curves.md), [Dividend and borrow](../curves/dividend-borrow.md)*

A futures price below the carried spot means dividends are expected before expiry; the gap, carried, is their value. Given known dividends, a forward instead pins down the stock-loan fee.

`F(T) = [S - sum div_i C(t_i)] / C(T)`, `C = D/B`, `B(t) = exp(-b t)`. `eq.dividend.implied`: `pv_dividends X(T) = S - F(T) C(T)`, period values by differencing, `dividend_yields q(T) = -ln(F(T) C(T)/S)/T`. `eq.borrow.implied`: the `b` with `F(expiry) = forward`; `F` falls as `b` rises, so `b` is unique, solved below 1e-14; no root in `[-0.5, 0.5]` is `E_NOT_BRACKETED`.

**Worked example.** A flat funding curve (one pillar, D = 0.70 at 2036-11-06, about 3.56% continuous), zero borrow, index at 4500 with futures 4560 for 2027-06-18 and 4600 for 2027-12-17: pv_dividends 38.6496, 78.7834, dividend_yields 0.014056, 0.015879. A stock at 50 with a 0.50 dividend on 2027-03-15 and a forward 51.00 for 2027-11-05: borrow_rate 0.00580944.

The pitfall: implying dividends with `B = 1` when the stock is hard to borrow. The borrow fee and the dividends both lower the forward, and one can be mistaken for the other.

## Commodities

### Q4.31 How does QuantForge interpolate a commodity forward curve with seasonality?

*Level: practitioner. Evidence: computed; spec. Source: [Commodity](../../specifications/02-curves/commodity.md), [Tutorial 10](../getting-started/tutorial-10-inflation-commodities.md), [Commodities](../curves/commodities.md)*

Many commodities have a strong calendar pattern, such as natural gas peaking in winter. Removing a seasonal term before interpolating, and adding it back after, keeps the pattern in months between quotes.

`cmdty.curve.forward`: with `sigma(k)` the additive log term for month `k`'s calendar month (0 when `null`), `L_j = ln(price_j) - sigma(k_j)` at the quotes, `L` linear in `k` between quotes, `F(k) = exp(L(k) + sigma(k))`. Every quote reprices. A month outside the quoted range is `E_OUT_OF_RANGE`: no extrapolation (ruling D29). Quote months must increase (`E_INPUT`); a price `<= 0` is `E_DOMAIN`.

**Worked example.** Quotes January 2027 3.80, July 2027 3.20, January 2028 3.90. April 2027 without seasonality: flat 3.487119 (geometric interpolation). With log terms January +0.10, April -0.04, July -0.04: seasonal 3.251368.

The pitfall: extrapolating past the last quote. QuantForge refuses, because a commodity curve's shape beyond the last contract is not implied by the quotes.

### Q4.32 What do the convenience yield and carry value in `cmdty.storage.carry` tell you?

*Level: practitioner. Evidence: computed; spec. Source: [Commodity](../../specifications/02-curves/commodity.md)*

Buying forward, storing and selling forward later costs funding and storage. If the later forward is high enough to pay for both, cash-and-carry earns money; the convenience yield is what holding the physical good is worth beyond that.

For consecutive forwards, `dt = (d1 - d0)/365`, `r = ln(D(d0)/D(d1))/dt`: `convenience_yields y = r + u - ln(F1/F0)/dt`; `carry_values = D(d1) F1 - D(d0) F0 exp(u dt)`; `arbitrage` is `carry_values > 0` (cash and carry earns; `y < 0`). Storage cost `u` is continuous, a fraction of value per year, `>= 0`.

**Worked example.** On the SOFR curve, forwards 75.0 for 2027-01-15 and 78.0 for 2027-07-15, storage 2%: convenience_yield -0.024221, carry_value 0.909167, arbitrage True.

What the desk cares about: a negative convenience yield in a real market usually means storage is full or the quoted cost is wrong. QuantForge flags the arbitrage; whether it can be traded depends on access to storage, which the model does not know.

## Mortgage-backed securities

### Q4.33 How does the PSA prepayment model shape an MBS pool's cash flows and WAL?

*Level: foundation. Evidence: computed; spec. Source: [MBS](../../specifications/04-pricing/mbs.md), [Tutorial 11](../getting-started/tutorial-11-mbs.md), [MBS page](../curves/mbs.md)*

Mortgage borrowers repay early. The PSA convention assumes prepayments ramp up over the first 30 months of a loan's life and then stay flat; faster prepayment returns principal sooner and shortens the weighted-average life.

For month `k`: `CPR_k = min((age + k)/30, 1) * 0.06 * speed/100` (or a constant `rate` for `CPR`), `SMM_k = 1 - (1 - CPR_k)^(1/12)`, level scheduled payment on the remaining term, `prepayment_k = SMM_k (B_k - scheduled_principal_k)`, interest at the net coupon. `wal = sum (k/12)(scheduled_principal_k + prepayment_k) / balance`. A PSA speed that gives `CPR_k >= 1` in any month is `E_DOMAIN` (ruling R6-7.1).

**Worked example.** A new pool of 1 million, WAC 6.5%, net coupon 6%, 360 months, PSA 150: month 1 prepayment 250.1181, month 30 prepayment 6792.7154, wal 9.285005 years. At PSA 100: PSA 100 wal 11.493976.

The pitfall: forgetting that `age` shifts the ramp. A seasoned pool is already at full speed in month 1.

### Q4.34 How is a pass-through priced, and what does `delay_days` change?

*Level: advanced. Evidence: computed; spec. Source: [MBS](../../specifications/04-pricing/mbs.md), [R6 rulings](../../specifications/r6-rulings.md)*

Each month's cash flow is discounted at a monthly-compounded yield. Agency pass-throughs pay some days after the accrual month ends, and that delay lowers the price even though the cash flows are unchanged.

`mbs.price`: `CF_k = interest_k + scheduled_principal_k + prepayment_k`, discounted at `v^(t_k)`, `v = 1/(1 + y/12)`, `t_k = k + delay_days/30`. `price = 100 sum CF_k v^(t_k) / balance`; `modified_duration = sum (t_k/12) CF_k v^(t_k + 1) / sum CF_k v^(t_k)`. `delay_days` (ruling R6-7.6) is the days from the end of the accrual month to payment on a 30-day month: the agency stated delay less 30, so a stated 55 days is `delay_days = 25` (the spec marks that figure as from memory). It moves only the discounting time.

**Worked example.** The PSA 150 pool of Q4.33 at a 6% yield: with no delay, price 100.000000, exactly par because the yield equals the net coupon. With `delay_days` 25: delay 25 price 99.585234, modified_duration 6.446745.

The limit: prepayment speed here is an input, not a function of rates. Without a rate-dependent prepayment model there is no option-adjusted spread or negative convexity in this stage.
