# Tutorial 3: options and volatility

The plain idea: an option's price depends on one number nobody can observe directly, the **volatility** of the underlying. The Black-Scholes model turns a volatility into a price, and its slopes, the **Greeks**, say how that price moves with the stock, time, rates and volatility. Markets run it the other way round: they quote prices, and you solve for the volatility that matches, the **implied volatility**. Doing that at many strikes gives a curve, the **smile**, which no single volatility explains. A model such as SABR fits the smile with a few parameters, and a **vol surface** stores implied volatility by expiry and strike so that any option can be read off it.

This tutorial prices an option and its Greeks, solves an implied volatility, fits a SABR smile, then reads three points off a surface. It uses five operations from stages C and E. Budget 10 to 15 minutes after [Tutorial 1](tutorial-1-swap.md). Every number shown is a real output; CI runs the code in all four languages and fails if a printed line differs.

## What you need

The setup and the three builds of [Tutorial 1](tutorial-1-swap.md#what-you-need). All data is synthetic.

## Step 1: Python

The script `examples/tutorials/t3_options.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t3_options.py -->
```python
"""Tutorial 3: Black-Scholes price and Greeks, implied volatility, a SABR smile and a vol surface.

  uv run --project python python examples/tutorials/t3_options.py            # Python
  python examples/tutorials/t3_options.py rust/target/release/quantforge     # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. A one-year at-the-money call on a stock at 100: 3% rate, 1% dividend yield, 20% volatility.
option = {"model": "BLACK_SCHOLES", "option_type": "CALL", "strike": 100.0, "expiry_years": 1.0,
          "spot": 100.0, "rate": 0.03, "yield": 0.01}
g = call("risk.vol.greeks", {**option, "vol": 0.2})
print(f"price {g['price']:.6f}  delta {g['delta']:.6f}  gamma {g['gamma']:.6f}")
print(f"vega  {g['vega']:.6f}  theta {g['theta']:.6f}  rho {g['rho']:.6f}")

# 2. Implied volatility: the market quotes the same call at 9.50. Which volatility gives that price?
iv = call("vol.option.implied", {**option, "price": 9.5})
print(f"implied vol at 9.50  {iv['vol']:.8f}")

# 3. A SABR smile (beta = 0.5) fitted to seven quoted vols, one-year expiry, forward 100.
strikes = [60.0, 75.0, 90.0, 100.0, 110.0, 125.0, 150.0]
vols = [0.4277311493595516, 0.3703805829578223, 0.32676467971358686, 0.30442125000000003,
        0.28724831699910025, 0.27059495038968, 0.26158130822689635]
fit = call("vol.sabr.calibrate", {"forward": 100.0, "expiry_years": 1.0, "beta": 0.5,
                                  "strikes": strikes, "vols": vols})
print(f"SABR  alpha {fit['alpha']:.4f}  rho {fit['rho']:.4f}  nu {fit['nu']:.4f}")
smile = call("vol.sabr.hagan", {"forward": 100.0, "expiry_years": 1.0, "beta": 0.5, "alpha": fit["alpha"],
                                "rho": fit["rho"], "nu": fit["nu"], "strikes": [80.0, 100.0, 120.0]})
print("smile at 80, 100, 120  " + "  ".join(f"{v:.5f}" for v in smile["vols"]))

# 4. A vol surface: a grid of vols by expiry (years) and log-moneyness ln(K/F); read three points.
surface = {"expiry_years": [0.2, 0.4, 1.0, 2.0], "log_moneyness": [-0.4, -0.2, 0.0, 0.2, 0.4],
           "vols": [[0.32, 0.27, 0.23, 0.22, 0.23], [0.3, 0.26, 0.225, 0.215, 0.22],
                    [0.285, 0.25, 0.22, 0.21, 0.215], [0.27, 0.24, 0.215, 0.205, 0.21]]}
points = [{"expiry_years": 1.0, "log_moneyness": 0.0}, {"expiry_years": 0.7, "log_moneyness": 0.0},
          {"expiry_years": 0.7, "log_moneyness": -0.1}]
q = call("vol.surface.query", {"surface": surface, "points": points})
for pt, v, w in zip(points, q["vols"], q["total_variance"]):
    print(f"surface T={pt['expiry_years']} k={pt['log_moneyness']:+.1f}  vol {v:.6f}  total variance {w:.6f}")
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t3_options.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
price 8.827321  delta 0.573496  gamma 0.019358
vega  38.715175  theta -4.753690  rho 48.522277
implied vol at 9.50  0.21737589
SABR  alpha 3.0000  rho -0.4000  nu 0.6000
smile at 80, 100, 120  0.35444  0.30442  0.27501
surface T=1.0 k=+0.0  vol 0.220000  total variance 0.048400
surface T=0.7 k=+0.0  vol 0.221440  total variance 0.034325
surface T=0.7 k=-0.1  vol 0.237690  total variance 0.039547
```

### Reading the numbers

**Inputs in market terms.** A call gives the right, not the obligation, to buy the stock at the **strike** (100) at **expiry** (one year). The stock is at 100, so the option is **at the money**. The rate (3%) and dividend yield (1%) are continuously compounded. Volatility, 20%, is the annualised standard deviation of the stock's log return.

**Price.** Plain idea: the price is the discounted average payoff, `max(S_T − K, 0)`, if the log return is normal with that volatility. Formally (spec `05-volatility/black-models.md`): with forward `F = S e^{(r−q)T}`, discount factor `D = e^{−rT}`, `d1 = (ln(F/K) + v²T/2)/(v√T)` and `d2 = d1 − v√T`, the call is `V = D (F N(d1) − K N(d2))`, `N` the standard normal distribution function (Black and Scholes 1973). Worked example: an at-the-money call is worth roughly 0.4 × S × v × √T = 8; the 2% carry (r − q) lifts the forward to 102.02, which adds a little more, giving 8.827321.

**Greeks.** All are per unit of the option (spec `06-risk/vol-greeks.md`), with volatility per 1.00, not per percentage point, and time in years.

- **Delta** 0.5735: the price moves 0.57 for a 1.00 move in the stock. For Black-Scholes it is `e^{−qT} N(d1)`. Here `d1 = 0.2`, `N(0.2) = 0.5793`, times `e^{−0.01} = 0.990`.
- **Gamma** 0.0194: how fast delta changes per 1.00 move in the stock.
- **Vega** 38.715: price change per 1.00 (100 percentage points) of volatility. Per volatility point it is 0.387.
- **Theta** −4.754: `theta = −dV/dT`, per year. Per calendar day that is about −4.754/365 = −0.013.
- **Rho** 48.52: per 1.00 of interest rate, so 0.485 per 1% rise in rates.

**Implied volatility.** The market price, 9.50, is 0.673 above the 20% model price. Dividing by vega gives a first guess: 0.20 + 0.673/38.715 = 0.2174. The solver's answer is 0.21737589. A solver stops when the price matches to `1e-13 × max(1, price)` (spec `05-volatility/black-models.md`), so the answer does not depend on the method.

**SABR smile.** Plain idea: in SABR the forward's volatility is itself random, and correlated with the forward. That bends the flat Black volatility into a smile. Formally (spec `05-volatility/sabr.md`): `dF = a F^β dW`, `da = ν a dZ`, `dW dZ = ρ dt`, `a(0) = α`. Hagan's formula (Hagan, Kumar, Lesniewski and Woodward 2002) gives the implied Black volatility for each strike. `vol.sabr.calibrate` fixes β (0.5 here) and finds α, ρ, ν that minimise the squared volatility errors. The seven quotes on this page were generated from α = 3, ρ = −0.4, ν = 0.6 (the golden case `sabr-0019` in `datasets/golden/stage_c/sabr.json`), so the fit recovers them, which is a check on the calibrator, not a claim about real markets. The parameters read as:

- α sets the level: with β = 0.5 and F = 100, the at-the-money volatility is close to α F^{β−1} = 3/10 = 0.30, and the smile prints 0.30442 at 100;
- ρ = −0.4 tilts the smile: low strikes get higher volatility (0.354 at 80) than high strikes (0.275 at 120);
- ν, the volatility of volatility, curves it.

**Vol surface.** A surface stores volatility by expiry `T` and log-moneyness `k = ln(K/F)`. The rule (spec `05-volatility/smile-and-surface.md`, `vol.surface.query`) interpolates **total variance** `w = v²T`, not volatility: linear in `k` on each expiry, then linear in `T` between expiries, flat volatility outside the grid. Worked example at T = 0.7, k = 0: the grid gives `w = 0.225² × 0.4 = 0.02025` at T = 0.4 and `0.22² × 1.0 = 0.0484` at T = 1.0. Halfway between them, `w = 0.034325`, and `v = √(0.034325/0.7) = 0.221440`. The first point sits on a node, so it returns the node's 0.22.

## Step 2: the same in Rust, Java and C++

Build once as in [Tutorial 1, step 2](tutorial-1-swap.md#step-2-the-same-in-rust-java-and-c), then:

<!-- tutorial:run rust -->
```bash
python examples/tutorials/t3_options.py rust/target/release/quantforge
```

<!-- tutorial:run java -->
```bash
python examples/tutorials/t3_options.py java -jar java25/target/quantforge-cli.jar
```

<!-- tutorial:run cpp -->
```bash
python examples/tutorials/t3_options.py cpp26/build/quantforge
```

Each prints the eight lines of step 1. The SABR fit is printed to four decimals on purpose: the languages use different optimisers, and the golden tolerance for this calibration is 1e-6.

## For practitioners

- **Units.** Vega and volga are per 1.00 of volatility and theta is per year. Many desk systems quote vega per volatility point and theta per day; divide by 100 and by 365 (or 252) to compare.
- **Theta.** Here theta is `−dV/dT` with spot, rates and volatility held fixed, the textbook definition. It is not the one-day P&L including carry.
- **Hagan's formula** is an expansion and is not arbitrage-free: at low strikes and long expiries its implied density can go negative. The spec says so in bold; use `vol.sabr.density` to check, or `vol.sabr.arbfree` (Hagan et al. 2014).
- **Surface interpolation** is linear in total variance on a fixed grid. That rules out calendar arbitrage between nodes when the nodes have none, but it can create butterfly arbitrage between strikes; `vol.surface.check` checks the nodes only. Stage E adds SVI and SSVI for arbitrage-free surfaces.

## Common mistakes

- Feeding a volatility in percent (20) instead of a fraction (0.2).
- Reading vega 38.7 as "38.7 per point". It is per 1.00 of volatility; per point it is 0.387.
- Interpolating volatility rather than total variance across expiries.
- Asking for an implied volatility below the option's intrinsic value. There is none, and the operation returns `E_DOMAIN`.

## What you just did

You priced a call with Black-Scholes and read its Greeks, solved the volatility implied by a market price, fitted a SABR smile and read volatilities off a surface. Python, Rust, Java and C++ printed the same digits.

- Maths in context: [LEARN, options and volatility](../../LEARN.md#options-and-volatility).
- Commands: [COOKBOOK, price then solve the vol back](../../COOKBOOK.md#price-then-solve-the-vol-back), [Greeks](../../COOKBOOK.md#greeks), [see Hagan SABR go negative](../../COOKBOOK.md#see-hagan-sabr-go-negative).
- The rules: `specifications/05-volatility/black-models.md`, `06-risk/vol-greeks.md`, `05-volatility/sabr.md`, `05-volatility/smile-and-surface.md`. Golden cases: `datasets/golden/stage_c/greeks.json`, `sabr.json`, `surface.json`.
- Terms: [GLOSSARY, stage C](../../GLOSSARY.md#stage-c-equity-vol-slice) (Greeks, implied vol, SABR, total variance).

## Try next

- Set `"option_type": "PUT"` in step 1. Put-call parity says call − put = D (F − K) = 0.970446 × 2.020134 = 1.960.
- Ask for the implied volatility of a call struck at 80 priced at 18. The discounted intrinsic value is D (F − K) = 0.970446 × 22.020134 = 21.37, more than 18, so no volatility fits and the operation returns `E_DOMAIN`.
- Change ρ to 0 in the `vol.sabr.hagan` call (α 3, ν 0.6). The vols at 80, 100, 120 become 0.336, 0.309, 0.302: a smile that curves up on both sides of its low point, with only the downward tilt that β = 0.5 builds in.

## References and further reading

Specs cite these; "not opened" means the spec author cited from memory. Links checked 2026-11-11 (DOIs resolve through doi.org; publisher pages are paywalled).

- F. Black and M. Scholes, "The pricing of options and corporate liabilities", *Journal of Political Economy* 81(3), 1973, 637-654. <https://doi.org/10.1086/260062> (paywalled).
- F. Black, "The pricing of commodity contracts", *Journal of Financial Economics* 3, 1976, 167-179 (Black-76). <https://doi.org/10.1016/0304-405X(76)90024-6> (paywalled).
- J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "The Greek Letters" (book; cited in `vol-greeks.md`, not opened).
- P. S. Hagan, D. Kumar, A. S. Lesniewski and D. E. Woodward, "Managing smile risk", *Wilmott Magazine*, September 2002, 84-108; and "Arbitrage-free SABR", *Wilmott Magazine*, January 2014 (cited in `sabr.md`, not opened; no stable link).
- J. Gatheral, *The Volatility Surface: A Practitioner's Guide*, Wiley, 2006 (book; cited in `smile-and-surface.md`, not opened).
- QuantLib cross-checks: `AnalyticEuropeanEngine` <https://www.quantlib.org/reference/class_quant_lib_1_1_analytic_european_engine.html> and `SABRInterpolation` <https://www.quantlib.org/reference/class_quant_lib_1_1_s_a_b_r_interpolation.html> (free).
- This project: [LEARN](../../LEARN.md#options-and-volatility), [COOKBOOK, stage C](../../COOKBOOK.md#stage-c-recipes), [GLOSSARY](../../GLOSSARY.md#stage-c-equity-vol-slice).
