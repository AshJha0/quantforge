# Tutorial 16: the LIBOR market model

The plain idea: the LIBOR market model (LMM) does not model a short rate. It models the forward rates the market quotes, one per period of a tenor grid, and makes each one lognormal under the measure that pays at the end of its own period. Two things follow. A caplet, an option on one forward rate, is then priced exactly by Black's formula, with a variance equal to the integral of that forward's volatility up to its fixing date. A swaption depends on many forwards at once, so it has no exact formula, but Rebonato's approximation turns the forward volatilities and their correlations into one Black volatility for the swap rate.

This tutorial prices a 5-year semi-annual cap and floor from an "abcd" volatility, prices a 5-year into 5-year payer swaption with two correlation settings, and then, in Python only, checks the closed-form caplets against a Monte Carlo simulation of the forwards. All data is synthetic: the curve and volatility are those of golden cases `lmmcap_g-0001`, `lmmcap_g-0003`, `lmmswn_g-0003` and `lmmswn_g-0015`. Budget 15 minutes, plus two minutes for the optional simulation. Every number shown is a real output.

Terms used here are in the [glossary, stage G section](../../GLOSSARY.md#stage-g-terms) (LIBOR market model) and the [stage C section](../../GLOSSARY.md#stage-c-equity-vol-slice) (Black-76, implied vol). Two more, defined here: a **caplet** pays `notional x tau x max(F - K, 0)` at the end of a period of length `tau` whose rate `F` fixed at the start; a **cap** is a strip of caplets, a **floor** the same with `max(K - F, 0)`. The **abcd volatility** gives each forward with fixing time `T` the instantaneous volatility `sigma_T(t) = (a + b (T - t)) e^{-c (T - t)} + d`: it depends only on the time left to fixing, and with `b > 0` it has a hump.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.

## Step 1: Python

<!-- tutorial:run python -->
```python
from quantforge_core import lmm

# Synthetic discount curve: times in years (ACT/365F) and discount factors, log-linear between.
TIMES = [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
         10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782]
DFS = [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]
HUMP = (-0.06, 0.17, 0.54, 0.17)       # abcd: a, b, c, d
SEMI = [0.5 * k for k in range(1, 11)]  # period ends 0.5 .. 5.0: nine caplets fixing 0.5 .. 4.5

# 1. A 5-year semi-annual cap and floor at 3% on 1 million.
cap = lmm.capfloor(TIMES, DFS, HUMP, SEMI, 0.03, "CAP", 1_000_000.0)
floor = lmm.capfloor(TIMES, DFS, HUMP, SEMI, 0.03, "FLOOR", 1_000_000.0)

# 2. A 5y into 5y payer swaption at 3.5%, annual payments, forward correlation exp(-beta |Ti - Tj|).
pay = [6.0, 7.0, 8.0, 9.0, 10.0]
s0 = lmm.swaption_rebonato(TIMES, DFS, HUMP, 0.0, 5.0, pay, 0.035, "PAY", 1_000_000.0)
s5 = lmm.swaption_rebonato(TIMES, DFS, HUMP, 0.5, 5.0, pay, 0.035, "PAY", 1_000_000.0)

print(f"cap price   {cap['price']:.2f}")
print(f"floor price {floor['price']:.2f}")
print("caplet Black vols " + " ".join(f"{v:.4f}" for v in cap["black_vols"][:3]))
print(f"first caplet forward {cap['forward_rates'][0]:.6f}  price {cap['caplet_prices'][0]:.2f}")
print(f"5y5y swap rate {s0['swap_rate']:.6f}  annuity {s0['annuity']:.6f}")
print(f"5y5y payer, beta 0.0: vol {s0['black_vol']:.4f}  price {s0['price']:.2f}")
print(f"5y5y payer, beta 0.5: vol {s5['black_vol']:.4f}  price {s5['price']:.2f}")
```

```bash
uv run --project python python lmm.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
cap price   42638.43
floor price 6491.40
caplet Black vols 0.1547 0.1869 0.2088
first caplet forward 0.039292  price 4473.22
5y5y swap rate 0.039604  annuity 3.672487
5y5y payer, beta 0.0: vol 0.2283  price 36842.11
5y5y payer, beta 0.5: vol 0.1670  price 29834.20
```

### Reading the numbers

- **Cap 42,638.43 and floor 6,491.40.** Both match the goldens `lmmcap_g-0001` and `-0003`. Cap minus floor is 36,147.03, which must equal a forward-starting swap: `notional sum (P(t_(i-1)) - (1 + K tau) P(t_i))`, the spec's asserted parity. Head check: forwards near 3.9%, strike 3%, so about 0.009 a year on 1 million over 4.5 years of discounted accrual (roughly 4.5 x 0.9 = 4.1): 0.009 x 4.1 x 1,000,000 = 36,900, near 36,147.
- **Caplet Black vols 0.1547, 0.1869, 0.2088.** These are the flat vols the market would quote for the first three caplets, `v_i / sqrt(t_(i-1))`. The abcd volatility at zero time to fixing is `a + d` = 0.11, and at half a year `(-0.06 + 0.17 x 0.5) e^{-0.27} + 0.17` = 0.025 x 0.763 + 0.17 = 0.189; the first caplet's vol, a root-mean-square over that half year, sits between at 0.155. Later caplets see more of the hump, so their vols rise.
- **First caplet, forward 0.039292, price 4,473.22.** It is deep in the money. Intrinsic value is `1,000,000 x 0.5 x P(1.0) x (0.039292 - 0.03)` = 500,000 x 0.9619 x 0.009292 = 4,469.0, so the option value on top is about 4.
- **Swap rate 0.039604, annuity 3.672487.** The swaption is 0.0046 in the money. Intrinsic value per unit of annuity: 1,000,000 x 3.672487 x 0.004604 = 16,908; the rest of 36,842.11 is time value.
- **Correlation matters: 0.2283 against 0.1670.** With `beta = 0` the five forwards move together, and the swap-rate vol is their weighted average. With `beta = 0.5`, forwards one year apart have correlation `e^{-0.5}` = 0.61, part of their moves cancel in the swap rate, and its vol falls. The price falls by 36,842.11 - 29,834.20 = 7,007.91, the gap the spec quotes for "correlation ignored". The caps above do not depend on `beta` at all: each caplet sees one forward. That is why caps alone cannot calibrate the correlation.

### Formal statement, checked against the spec

From [`04-pricing/lmm.md`](../../specifications/04-pricing/lmm.md) (ruling G-22; Brigo and Mercurio 2006, sections 6.3.2, 6.4, 6.9, 6.13). Times are year fractions ACT/365F; the curve is log-linear in discount factors; the forward over `[s, t]` is `F = (P(s)/P(t) - 1)/(t - s)`, a single curve. Every forward and strike must be above 0 (lognormal model), else `E_DOMAIN`.

Cap: with `C(T_i, T_j; u) = integral_0^u sigma_(T_i)(t) sigma_(T_j)(t) dt` and `v_i^2 = C(t_(i-1), t_(i-1); t_(i-1))`, `caplet_i = notional tau_i P(t_i) Black(F_i, K, v_i)` [Black 1976]. The variance runs to the fixing date, not the payment date; integrating to the payment date is a wrong-convention case the goldens catch (gap 595 on 1 million).

Swaption (Rebonato's frozen weights, Brigo and Mercurio eq. 6.67): annuity `A = sum tau_i P(T_i)`, weights `w_i = tau_i P(T_i)/A`, swap rate `S = sum w_i F_i`, correlation `rho_ij = exp(-beta |T_(i-1) - T_(j-1)|)`, and `v^2 = (1/S^2) sum_ij w_i w_j F_i F_j rho_ij C(T_(i-1), T_(j-1); T_0)`; `price = notional A Black(S, K, v)`, a call for a payer. `black_vol` is `v / sqrt(T_0)`.

Tolerances: prices 1e-6 absolute plus 1e-9 relative on 1 million (1e-12 per unit notional), other outputs 1e-12 absolute plus 1e-10 relative. Every value case matches QuantLib 1.44's `AbcdFunction.covariance` and `blackFormula`.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_lmm.py` sends `rates.lmm.capfloor` (twice) and `rates.lmm.swaption_rebonato` (twice) to the CLI you name and prints the same seven lines. Standard library only.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_lmm.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_lmm.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_lmm.py cpp26/build/quantforge
```

Each prints the seven lines of step 1, digit for digit, well inside the tolerances above.

## Step 3 (optional, Python only): does a simulated LMM reproduce the caplets?

No CLI operation simulates the LMM: `name-map.json` lists only the two closed forms. The simulation is a library function in the Python implementation, `quantforge_core.lmm.simulate_caplets`, and the spec judges it by one acceptance test rather than goldens, because its numbers depend on the random stream (`lmm.md`, "Simulated LMM", ruling G-26). Each language runs that test with its own stream; there is nothing to compare digit for digit, so this block is not run by CI and is not part of the four-language check.

The scheme simulates every forward under the measure of the last grid date (the terminal measure): log-Euler steps with a predictor-corrector drift `mu_k = -sigma_k sum_(j > k) rho_kj tau_j sigma_j F_j / (1 + tau_j F_j)`, the volatility frozen at each step's midpoint, correlated normals by Cholesky. The settings are the spec's: humped abcd, `beta = 0.1`, annual grid to 7 years, strike 4.5%, 100,000 paths, 20 steps a year, seed 20261111.

```python
from quantforge_core import lmm, shortrate

TIMES = [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
         10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782]
DFS = [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]
HUMP = (-0.06, 0.17, 0.54, 0.17)
grid = [float(k) for k in range(8)]  # annual fixings 1..6, last payment 7
sim = lmm.simulate_caplets(shortrate.make_curve(TIMES, DFS), lmm.make_abcd(*HUMP), 0.1, grid,
                           0.045, 100_000, 20, 20261111)
exact = lmm.capfloor(TIMES, DFS, HUMP, grid[1:], 0.045, "CAP", 1.0)["caplet_prices"]
for k, ((mean, se), x) in enumerate(zip(sim, exact), start=1):
    print(f"fix {k}y  closed {x:.6f}  simulated {mean:.6f}  SE {se:.6f}  z {(mean - x) / se:+.2f}")
```

Real output, 2026-11-11, Windows 11 (1 minute 49 seconds):

```text
fix 1y  closed 0.001029  simulated 0.001023  SE 0.000009  z -0.60
fix 2y  closed 0.002515  simulated 0.002485  SE 0.000021  z -1.49
fix 3y  closed 0.003812  simulated 0.003805  SE 0.000031  z -0.24
fix 4y  closed 0.004578  simulated 0.004600  SE 0.000037  z +0.61
fix 5y  closed 0.005271  simulated 0.005295  SE 0.000042  z +0.58
fix 6y  closed 0.005573  simulated 0.005543  SE 0.000043  z -0.70
```

Prices are per unit notional. All six caplets lie within 3 standard errors of the closed form, the acceptance rule; `z` runs from -1.49 to +0.61, the range the spec records. This is evidence that the simulation and the closed form describe the same model, not a proof: six `z` values say little about a small bias. The spec also discloses that an earlier left-point scheme put the 1-year caplet at `z = 2.97`, which is why the midpoint rule is used.

## For practitioners

- **Single curve, lognormal.** Forwards are projected and discounted on one curve, and every forward must be positive. Desks price caps on a projection curve with OIS discounting, and in low-rate regimes with a shifted lognormal or normal (Bachelier) model. Both are new inputs in this spec, not options (G-22): a negative forward returns `E_DOMAIN`.
- **Caplet vols.** `black_vols` are what a caplet stripper would recover; see the [caplet stripping](../../GLOSSARY.md#stage-e-full-volatility-exotics-rates-vol-correlation-and-credit) entry and [LEARN: stripping caplet vols](../../LEARN.md#stripping-caplet-vols-and-when-it-must-fail). Calibrating `a, b, c, d` to a stripped curve is not an operation here.
- **QuantLib.** `AbcdFunction` uses the same parameterisation; the goldens agree with its closed-form covariance to the 1e-10 relative tolerance on all 53 value cases.
- **Rebonato's accuracy.** It is an approximation. For the 5y into 5y payer at 3.5%, the spec records that Rebonato exceeds a simulated LMM by 0.41% at `beta = 0` and 0.47% at `beta = 0.5`, with simulation standard errors about 0.6% and 0.5%: not distinguishable from zero in that run.
- **Correlation form.** One-parameter exponential correlation by fixing time. Desks often use a two- or three-parameter form with a long-run correlation floor; with it, long-dated swaption vols fall less than here.

## Common mistakes

- Integrating the caplet variance to the payment date. It runs to the fixing date.
- Quoting `black_vols` as the abcd value at the fixing. It is the root-mean-square of the path up to the fixing.
- Expecting `beta` to change cap prices. It cannot; only swaptions (and path-dependent products) see correlation.
- Putting the expiry into `payment_times`. The first payment is after `expiry_years`; the first period runs from the expiry, and both fixed and floating accruals come from the payment times (G-12).
- Comparing a single Monte Carlo price to a closed form without its standard error.

## What you just did

You priced a cap and a floor from a humped abcd volatility, checked cap-floor parity and an intrinsic-value bound by hand, priced a swaption with Rebonato's formula and watched decorrelation lower its vol from 0.2283 to 0.1670, ran the same four calls in four languages, and checked the closed-form caplets against a simulated LMM.

## Try next

- Set `HUMP = (0.0, 0.0, 1.0, 0.2)`: a flat 20% vol. Every `black_vols` entry becomes 0.20, and with `beta = 0` so does the swaption vol (both asserted to 1e-14 in the spec).
- Price the 1y into 5y swaption (`expiry_years` 1.0, payments 2.0 to 6.0) at both `beta` values and compare with goldens `lmmswn_g-0001` and `-0013`.
- Raise the strike until the floor is worth more than the cap; parity tells you where.
- Read [LEARN: swaptions, Bermudans and the LMM](../../LEARN.md#swaptions-bermudans-and-the-lmm).

## References and further reading

- D. Brigo, F. Mercurio, *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006, [doi:10.1007/978-3-540-34604-3](https://doi.org/10.1007/978-3-540-34604-3) (paywalled): sections 6.3.2 (abcd), 6.4 (caplets), 6.9 (correlation), 6.13 (Rebonato's formula, eq. 6.67). The spec marks it "not opened" and checks the formulas against QuantLib.
- A. Brace, D. Gatarek, M. Musiela, "The market model of interest rate dynamics", *Mathematical Finance* 7, 1997, 127-155, [doi:10.1111/1467-9965.00028](https://doi.org/10.1111/1467-9965.00028) (paywalled). The publisher returns HTTP 403 to scripted requests; the DOI's title was confirmed through the Crossref API.
- F. Black, "The pricing of commodity contracts", *Journal of Financial Economics* 3, 1976, 167-179, [doi:10.1016/0304-405X(76)90024-6](https://doi.org/10.1016/0304-405X(76)90024-6) (paywalled).
- R. Rebonato, *Volatility and Correlation*, 2nd ed., Wiley, 2004, chapter 6: the abcd form (not opened per the spec; no link given).
- P. Glasserman, *Monte Carlo Methods in Financial Engineering*, Springer, 2003, section 3.7, [doi:10.1007/978-0-387-21617-1](https://doi.org/10.1007/978-0-387-21617-1) (paywalled): simulating the LMM (not opened per the spec).
- [QuantLib](https://www.quantlib.org/) 1.44: `AbcdFunction`, `blackFormula`, the outside oracle for both operations.
- QuantForge: spec [`04-pricing/lmm.md`](../../specifications/04-pricing/lmm.md); the [Cookbook](../../COOKBOOK.md) row "LMM caplets and Rebonato swaptions"; the [glossary](../../GLOSSARY.md#stage-g-terms).

Links checked 2026-11-11: doi.org links for Brigo-Mercurio, Black and Glasserman and quantlib.org returned HTTP 200; the Brace-Gatarek-Musiela DOI returned 403 (bot block) and was verified through Crossref.
