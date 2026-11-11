# Tutorial 6: interest rate models

The plain idea: to price an option on rates you need a model of how the whole curve can move. A **short-rate model** describes the random path of the instantaneous interest rate `r(t)`; every bond price then follows from it. The **Hull-White model** is the standard first choice because it fits today's discount curve exactly and still gives closed-form prices for options on zero-coupon bonds. **Jamshidian's decomposition** turns a European swaption into a sum of such bond options. Its one free volatility parameter is **calibrated** to market swaption prices, and the calibrated model then prices what has no closed form, such as a **Bermudan swaption**, which can be exercised on several dates.

This tutorial does those four steps with four stage G operations. Budget about 15 minutes after [Tutorial 1](tutorial-1-swap.md). Every number shown is a real output; CI runs the code in all four languages and fails if a printed line differs.

## What you need

The setup and the three builds of [Tutorial 1](tutorial-1-swap.md#what-you-need). All data is synthetic.

## Step 1: Python

The script `examples/tutorials/t6_hull_white.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t6_hull_white.py -->
```python
"""Tutorial 6: Hull-White bond option, a Jamshidian swaption, sigma calibrated to swaptions, a Bermudan.

  uv run --project python python examples/tutorials/t6_hull_white.py         # Python
  python examples/tutorials/t6_hull_white.py rust/target/release/quantforge  # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. Today's discount curve by time in years (ACT/365F), and Hull-White with a = 5%, sigma = 1%.
curve = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
hw = {"curve": curve, "mean_reversion": 0.05, "sigma": 0.01}

# 2. A one-year call, strike 0.86, on a zero-coupon bond maturing in year 5; notional 1 million.
z = call("rates.shortrate.zcb_option", {"model": "HULL_WHITE", **hw, "option_type": "CALL", "strike": 0.86,
                                        "expiry_years": 1.0, "maturity_years": 5.0, "notional": 1_000_000.0})
print(f"bond option {z['price']:.4f}  P(0,1) {z['bond_price_expiry']:.6f}  P(0,5) {z['bond_price_maturity']:.6f}")

# 3. A European payer swaption, 1 year into a 5-year annual swap, struck at 3.4462%: Jamshidian's method.
swap = {"payment_times": [2.0, 3.0, 4.0, 5.0, 6.0], "fixed_rate": 0.034462, "swaption_type": "PAYER",
        "notional": 1_000_000.0}
e = call("rates.shortrate.swaption", {**hw, "expiry_years": 1.0, **swap})
print(f"European {e['price']:.4f}  forward swap rate {e['forward_swap_rate']:.8f}  annuity {e['annuity']:.2f}")

# 4. Calibrate sigma (a fixed at 5%) to five co-terminal swaption prices per unit notional.
strip = [(1.0, 0.03948, 0.027739189051503528), (2.0, 0.039486, 0.03302750501350072),
         (3.0, 0.039554, 0.035288652993578785), (5.0, 0.039604, 0.030395873006313835),
         (7.0, 0.039345, 0.021061314962415565)]
swaptions = [{"expiry_years": t, "payment_times": [float(y) for y in range(int(t) + 1, 11)], "fixed_rate": k,
              "swaption_type": "PAYER", "target_price": p} for t, k, p in strip]
cal = call("rates.shortrate.hw_calibrate", {"curve": curve, "mean_reversion": 0.05, "swaptions": swaptions})
print(f"calibrated sigma {cal['sigma']:.8f}  rmse {cal['rmse']:.8f}")
for s, fitted in zip(swaptions, cal["fitted_prices"]):
    print(f"  {s['expiry_years']:.0f}Y expiry  target {s['target_price']:.6f}  fitted {fitted:.6f}")

# 5. The Bermudan: the same swap, but exercisable on every reset date from year 1 to year 5.
grid = {"nx": 201, "steps_per_year": 100, "width": 6.0}
b = call("rates.shortrate.bermudan_swaption", {**hw, "start_years": 1.0, **swap,
                                               "exercise_times": [1.0, 2.0, 3.0, 4.0, 5.0], "grid": grid})
print(f"Bermudan {b['price']:.4f}  exercise premium over the European {b['price'] - e['price']:.4f}")
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t6_hull_white.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
bond option 10236.0072  P(0,1) 0.961900  P(0,5) 0.824287
European 28412.5324  forward swap rate 0.03946246  annuity 4289707.36
calibrated sigma 0.01150409  rmse 0.00038546
  1Y expiry  target 0.027739  fitted 0.027205
  2Y expiry  target 0.033028  fitted 0.033373
  3Y expiry  target 0.035289  fitted 0.034952
  5Y expiry  target 0.030396  fitted 0.030870
  7Y expiry  target 0.021061  fitted 0.021069
Bermudan 34186.6115  exercise premium over the European 5774.0791
```

### Reading the numbers

**The model.** Plain idea: the short rate is pulled back toward a level that is chosen so the model reprices today's curve, and it is shaken by a normal shock. Formally (spec `04-pricing/short-rate-models.md`; Hull and White 1990): `dr = (θ(t) − a r) dt + σ dW`, with `θ(t)` fitted to the input curve, `a` the **mean reversion** (5% here: shocks die out with a half-life of about ln 2/0.05 ≈ 14 years) and `σ` the volatility of the short rate (1% a year, in rate units, so about 100 bp a year). The curve is given by time in years, ACT/365F, and is interpolated log-linearly in discount factor.

**Bond option.** Plain idea: a call on a zero-coupon bond is a bet that rates fall before expiry. Formally: with `σ_p = (σ/a)(1 − e^{−a(S−T)}) sqrt((1 − e^{−2aT})/(2a))` and `h = ln(P(0,S)/(K P(0,T)))/σ_p + σ_p/2`, the call is `P(0,S) N(h) − K P(0,T) N(h − σ_p)` (Jamshidian 1989; Brigo and Mercurio, section 3.3). Worked example: `P(0,1) = 0.9619` is a curve pillar, and `P(0,5) = 0.824287` is interpolated between the 3-year and 5.003-year pillars. The bond's forward price for delivery in one year is 0.824287/0.9619 = 0.8569, just under the 0.86 strike, so the call is slightly out of the money. Here `σ_p = 0.0354`, the volatility of that forward bond price, and the call is worth 10,236 on 1 million face.

**Jamshidian swaption.** Plain idea: a payer swaption is the right to pay fixed. That is the same as a put on a coupon bond paying the fixed rate, struck at par. In a one-factor model every bond price falls as `r` rises, so there is one short rate `r*` at which the coupon bond is worth exactly par, and the put on the coupon bond splits into a sum of puts on the zero-coupon bonds, each struck at that bond's price at `r*` (spec, `rates.shortrate.swaption`). Worked example: the forward swap rate is 3.9462%, the strike is 3.4462%, so the option is 50 bp in the money. Its intrinsic value is about annuity × 0.005 = 4,289,707.36 × 0.005 = 21,449, and the price 28,413 adds about 6,964 of time value. The annuity is the notional times `Σ τ_i P(0, T_i)` over the five annual payments.

**Calibration.** Plain idea: `a` is fixed and `σ` is moved until the model's swaption prices are as close as possible to the market's. Formally (spec, `rates.shortrate.hw_calibrate`): `σ` minimises `Σ (model_i(σ) − target_i)²`, unweighted, on prices per unit notional, over `[1e-4, 1]`; `rmse = sqrt(F(σ)/n)`. Worked example: one parameter cannot fit five prices, so the fit is a compromise, 1.1504%, with errors of 3.85 bp of notional on average, too low at 1 and 3 years and too high at 2 and 5 years. A model with a time-dependent `σ(t)` or a second factor would fit more closely.

**Bermudan swaption.** Plain idea: the holder can exercise on any reset date from year 1 to year 5, entering a swap that pays fixed from that date to year 6. The value is found by working backwards on a grid of short rates: at each exercise date, keep the larger of exercising now and waiting. Formally (spec, `rates.shortrate.bermudan_swaption`, ruling G-18): a fully implicit finite-difference scheme in `x = r − α(t)` on a pinned grid (201 nodes, `width` 6 standard deviations, 100 steps a year), with the exercise value `φ(1 − P(t, T_n) − K Σ τ_j P(t, T_j))` per unit notional. Worked example: the Bermudan is worth 34,187, more than the European's 28,413, because the right to wait and exercise later is worth something; it can never be worth less than the most valuable single-date European it contains. Step 5 uses `σ = 1%`, the same as step 3, so the 5,774 premium compares like with like, apart from the grid's discretisation error in the Bermudan price.

## Step 2: the same in Rust, Java and C++

Build once as in [Tutorial 1, step 2](tutorial-1-swap.md#step-2-the-same-in-rust-java-and-c), then:

<!-- tutorial:run rust -->
```bash
python examples/tutorials/t6_hull_white.py rust/target/release/quantforge
```

<!-- tutorial:run java -->
```bash
python examples/tutorials/t6_hull_white.py java -jar java25/target/quantforge-cli.jar
```

<!-- tutorial:run cpp -->
```bash
python examples/tutorials/t6_hull_white.py cpp26/build/quantforge
```

Each prints the ten lines of step 1.

## For practitioners

- **Single curve.** The swap's floating leg is worth `P(T0,T0) − P(T0,Tn)` at expiry, a par floater on the same curve (ruling G-12). There is no separate projection curve and no basis.
- **Accruals are time differences.** Fixed accruals are `T_i − T_(i−1)` in years, so a caller's dates and day count fix them. These swaps pay exactly 1.0 a year.
- **Calibration target.** The objective is on prices, unweighted. Desks often calibrate on normal or Black volatilities, or weight by vega; those give a different `σ`.
- **Jamshidian in QuantLib.** `JamshidianSwaptionEngine` agrees with these prices only to about 3e-7 relative, its internal root accuracy, so the outside check uses QuantLib's `HullWhite` bond and bond-option formulas with `r*` solved to 1e-15 (spec, `rates.shortrate.swaption`, Validation).
- **The Bermudan scheme is pinned.** Every build runs the same grid, so the four languages agree to 1e-9 relative. The grid error against the true model price is separate and is stated in the spec's convergence table, not here.

## Common mistakes

- Reading `σ = 0.01` as a 1% Black volatility. In Hull-White it is a normal volatility of the short rate, about 100 bp a year.
- Passing `short_rate` to a Hull-White operation. The curve fixes the starting point, so it is not allowed (`E_INPUT`).
- Expecting a one-parameter calibration to fit every swaption. Check the residuals, not only `rmse`.

## What you just did

You priced an option on a zero-coupon bond under Hull-White, priced a European swaption by Jamshidian's decomposition, calibrated the model's volatility to five swaptions and read the residuals, then priced a Bermudan swaption on a finite-difference grid and measured its early-exercise premium. All four languages printed the same digits.

- Maths in context: [LEARN, short-rate models](../../LEARN.md#short-rate-models) and [swaptions, Bermudans and the LMM](../../LEARN.md#swaptions-bermudans-and-the-lmm).
- Commands: [COOKBOOK, stage G recipes](../../COOKBOOK.md#stage-g-recipes).
- The rules: `specifications/04-pricing/short-rate-models.md`, `specifications/stage-g-rulings.md`. Golden cases: `datasets/golden/stage_g/shortrate_g.json` (`shortrate_g-0055`), `hwcal_g.json`, `bermudan_g.json` (`bermudan_g-0001`).
- Terms: [GLOSSARY, stage G](../../GLOSSARY.md#stage-g-terms) (short-rate model, Jamshidian decomposition, Bermudan swaption) and [tutorial terms](../../GLOSSARY.md#tutorial-terms) (mean reversion).

## Try next

- Price the receiver swaption (`"swaption_type": "RECEIVER"`). Payer minus receiver equals annuity × (forward − strike), which the spec asserts on every golden pair.
- Re-run step 5 with `cal["sigma"]` in place of 0.01 to price the Bermudan on the calibrated model.
- Halve `steps_per_year` and `nx` in the Bermudan grid and see how much the price moves: that is the grid error.

## References and further reading

Links checked 2026-11-11. "Not opened" means the spec cites the source from memory.

- J. Hull and A. White, "Pricing interest-rate-derivative securities", *Review of Financial Studies* 3(4), 1990, 573-592. <https://doi.org/10.1093/rfs/3.4.573> (paywalled; cited in `short-rate-models.md` [HW90], not opened).
- F. Jamshidian, "An exact bond option formula", *Journal of Finance* 44(1), 1989, 205-209. <https://doi.org/10.1111/j.1540-6261.1989.tb02413.x> (paywalled; [J89], not opened).
- O. Vasicek, "An equilibrium characterization of the term structure", *Journal of Financial Economics* 5, 1977. <https://doi.org/10.1016/0304-405X(77)90016-2> (paywalled; [V77], not opened).
- D. Brigo and F. Mercurio, *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006, section 3.3 (book, paywalled; [BM]; the spec checked its formulas against QuantLib 1.44 rather than the book).
- QuantLib `HullWhite` <https://www.quantlib.org/reference/class_quant_lib_1_1_hull_white.html>, `JamshidianSwaptionEngine` <https://www.quantlib.org/reference/class_quant_lib_1_1_jamshidian_swaption_engine.html> and `TreeSwaptionEngine` <https://www.quantlib.org/reference/class_quant_lib_1_1_tree_swaption_engine.html> (free). The project's Bermudan is checked against its own pinned reference scheme, not against QuantLib.
- This project: [LEARN](../../LEARN.md#stage-g-rates-models-and-xva), [COOKBOOK](../../COOKBOOK.md#stage-g-recipes), [GLOSSARY](../../GLOSSARY.md#stage-g-terms).
