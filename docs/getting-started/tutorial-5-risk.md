# Tutorial 5: risk

The plain idea: risk management asks three questions. How does the price move when an input moves? How much could the book lose on a bad day? And how much capital does a regulator require against it? The first is answered by **sensitivities**: you can bump each input and reprice, or get them all at once by **adjoint algorithmic differentiation** (AAD). The second is answered by **value at risk** (VaR) and **expected shortfall** (ES) on a history of daily profit and loss, and a **backtest** checks whether VaR was broken as often as it should be. The third, for interest-rate risk, is the Basel **FRTB** standardised delta charge.

This tutorial does all three: AAD against bump-and-revalue on a Bermudan swaption, historical VaR and ES with a backtest, and the FRTB GIRR delta charge of Tutorial 1's swap. It uses eight operations from stages C to G. Budget about 15 minutes after [Tutorial 1](tutorial-1-swap.md). Every number shown is a real output; CI runs the code in all four languages and fails if a printed line differs.

## What you need

The setup and the three builds of [Tutorial 1](tutorial-1-swap.md#what-you-need). The P&L history is the synthetic golden case `risk_f4-0003` in `datasets/golden/stage_f/risk_f4.json`, which the script reads.

## Step 1: Python

The script `examples/tutorials/t5_risk.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t5_risk.py -->
```python
"""Tutorial 5: AAD against bump-and-revalue, historical VaR and ES with a backtest, an FRTB delta charge.

  uv run --project python python examples/tutorials/t5_risk.py               # Python
  python examples/tutorials/t5_risk.py rust/target/release/quantforge        # or any other build
"""
import json
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. A Bermudan payer swaption under Hull-White (a = 5%, sigma = 1%), exercisable yearly from year 1
#    into a swap ending in year 6. Price and full sensitivity ladder in one reverse (AAD) sweep.
curve = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
deal = {"mean_reversion": 0.05, "sigma": 0.01, "curve": curve, "notional": 1_000_000.0, "start_years": 1.0,
        "payment_times": [2.0, 3.0, 4.0, 5.0, 6.0], "fixed_rate": 0.039462, "swaption_type": "PAYER",
        "exercise_times": [1.0, 2.0, 3.0, 4.0, 5.0], "grid": {"nx": 101, "steps_per_year": 50, "width": 6.0}}
aad = call("rates.shortrate.bermudan_ladder", deal)
print(f"Bermudan price {aad['price']:.4f}")
print(f"AAD   dV/dsigma {aad['d_price_d_sigma']:.2f}  dV/da {aad['d_price_d_mean_reversion']:.2f}")

# 2. The same two numbers by bump-and-revalue: reprice with the input 0.01% up and down (central difference).
def bumped(key):
    h = deal[key] * 1e-4
    up = call("rates.shortrate.bermudan_swaption", {**deal, key: deal[key] + h})["price"]
    down = call("rates.shortrate.bermudan_swaption", {**deal, key: deal[key] - h})["price"]
    return (up - down) / (2 * h)

print(f"bump  dV/dsigma {bumped('sigma'):.2f}  dV/da {bumped('mean_reversion'):.2f}")

# 3. Historical VaR and ES at 99% from 250 days of daily P&L (synthetic; golden case risk_f4-0003).
with open("datasets/golden/stage_f/risk_f4.json", encoding="utf-8") as f:
    [case] = [c for c in json.load(f)["cases"] if c["case_id"] == "risk_f4-0003"]
pnl = case["inputs"]["pnl"]
first, second = pnl[:250], pnl[250:]
v = call("risk.var.historical", {"pnl": first, "confidence": 0.99})
print(f"VaR 99% {v['var']:.2f}  ES 99% {v['es']:.2f}  tail days {v['tail_count']}")

# 4. Backtest: on the next 250 days, count the losses larger than that VaR, then test the count.
exceptions = sum(1 for x in second if -x > v["var"])
k = call("risk.backtest.kupiec", {"observations": 250, "exceptions": exceptions, "confidence": 0.99})
t = call("risk.backtest.traffic_light", {"observations": 250, "exceptions": exceptions, "confidence": 0.99})
print(f"exceptions {exceptions} of 250  Kupiec LR {k['lr_uc']:.4f}  p-value {k['p_value']:.4f}")
print(f"traffic light {t['zone']}  cumulative probability {t['cumulative_probability']:.4f}  plus factor {t['plus_factor']:.2f}")

# 5. FRTB GIRR delta: tutorial 1's swap key-rate DV01s, as MAR21 sensitivities (DV01 / 0.0001).
quotes = [{"tenor": n, "rate": r} for n, r in
          [("1Y", 0.035), ("2Y", 0.0335), ("3Y", 0.033), ("5Y", 0.0335), ("7Y", 0.0345), ("10Y", 0.036)]]
swap = {"convention": "SOFR", "tenor": "5Y", "fixed_rate": 0.034, "notional": 10_000_000.0, "side": "PAY"}
kr = call("risk.ois.dv01", {"as_of": "2026-11-06", "quotes": quotes, "interpolation": "LOG_LINEAR_DF",
                            "trade": swap})["key_rate"]
rows = [{"currency": "USD", "curve": "SOFR", "risk_factor": q["tenor"], "sensitivity": d / 0.0001}
        for q, d in zip(quotes, kr) if d != 0.0]
frtb = call("risk.frtb.girr_delta", {"sensitivities": rows, "specified_currency_reduction": False})
print("GIRR sensitivities " + " ".join(f"{r['risk_factor']}:{r['sensitivity']:.0f}" for r in rows))
print(f"GIRR delta capital {frtb['capital']:.2f}  binding scenario {frtb['binding_scenario']}")
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t5_risk.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
Bermudan price 22697.8097
AAD   dV/dsigma 2269594.61  dV/da -52528.10
bump  dV/dsigma 2269594.61  dV/da -52528.10
VaR 99% 4715737.90  ES 99% 5143820.74  tail days 3
exceptions 4 of 250  Kupiec LR 0.7691  p-value 0.3805
traffic light GREEN  cumulative probability 0.8922  plus factor 0.00
GIRR sensitivities 1Y:4454 2Y:8616 3Y:19862 5Y:45944422
GIRR delta capital 505810.25  binding scenario high
```

### Reading the numbers

**The trade.** A Bermudan payer swaption gives the right to enter, on any of the dates 1, 2, 3, 4 or 5 years from now, a swap paying 3.9462% fixed until year 6 on 1 million. It is priced under the Hull-White model on a finite-difference grid; [Tutorial 6](tutorial-6-hull-white.md) explains both. Here it is just a price with three kinds of input: the ten discount factors of the curve, the mean reversion `a` and the volatility `sigma`.

**AAD against bump-and-revalue.** Plain idea: bumping finds each sensitivity by repricing twice with that input moved up and down, so twelve inputs cost 24 pricings. AAD records one pricing and runs it backwards, applying the chain rule from the price to every input at once, so the whole **ladder** of sensitivities costs a small fixed multiple of one pricing, however many inputs there are (Giles and Glasserman 2006). Formally (spec `06-risk/aad-core.md`): `rates.shortrate.bermudan_ladder` returns `dV/dθ` for `θ` = the discount factors, `a` and `sigma`, the derivative of the discrete grid scheme exactly as computed, including the exercise `max` on its active branch. The bump estimate is the central difference `(V(x + h) − V(x − h))/(2h)` with `h = 1e-4 × x`. Worked example: both print 2,269,594.61 for `dV/dsigma`, to the cent. That is per 1.00 of `sigma`; a 1 bp rise in `sigma`, from 1.00% to 1.01%, adds about 2,269,594.61 × 0.0001 = 227 to the price. Higher mean reversion damps rate moves far ahead, so the option is worth less: `dV/da` is −52,528 per 1.00, about −525 for `a` up by 0.01.

The agreement is not exact in principle. A central difference has an error of order `h²`, and a bump that moves an exercise decision across a grid node would break it; the golden reference therefore uses Richardson-extrapolated differences at two bump sizes, and the builds must match it within `1e-10 + 1e-8 × |ref|` per unit notional (spec `aad-core.md`, tolerance G-9).

**Historical VaR and ES.** Plain idea: line up the last 250 days of P&L as if each could happen tomorrow. The 99% VaR is the loss exceeded on only 1% of those days; ES is the average loss on those worst days. Formally (spec `06-risk/var-es-and-backtests.md`): losses `L = −pnl` are sorted ascending, `k = ceil(n c)`, VaR is `L_(k)`. ES is the Acerbi-Tasche estimator (ruling R6-3.1): with `w = n - n c` and `m = floor(w)`, the `m` largest losses get weight 1, the next gets weight `w - m`, and the sum is divided by `w`. Worked example: `n = 250`, `c = 0.99`, so `k = ceil(247.5) = 248`. VaR is the third-largest loss, 4,715,737.90, and with `w = 2.5`, `m = 2`, ES is (largest + second-largest + 0.5 x third-largest) / 2.5 = 5,143,820.74 (`tail days 3`). Before v0.8.1 ES was the plain mean of the three largest, 5,072,473.60. ES is never below VaR, as it averages losses at least as large.

**Backtest.** The script applies that VaR to the next 250 days and counts the days whose loss was larger: 4. At 99% you expect 2.5.

- **Kupiec's test** asks whether 4 out of 250 is consistent with a 1% rate. With `p = 0.01` and `p̂ = 4/250`, `LR_uc = −2[(n − x) ln(1 − p) + x ln p] + 2[(n − x) ln(1 − p̂) + x ln p̂] = 0.7691`, compared with a chi-square with one degree of freedom: p-value 0.38, so no evidence that the model is wrong (Kupiec 1995).
- **The Basel traffic light** puts 0 to 4 exceptions in 250 days at 99% in the green zone (Basel Committee 1996, Table 2). `cumulative probability` is `P(X ≤ 4)` for `X ~ Binomial(250, 0.01)`, 0.8922, below the 0.95 that would start the yellow zone; the plus factor on the capital multiplier is 0.

**FRTB GIRR delta.** Plain idea: the regulator's standardised approach does not use your VaR. It weights each interest-rate sensitivity by a fixed risk weight and adds the results with fixed correlations. Formally (spec `06-risk/frtb-sa-girr.md`, from BIS MAR21): the sensitivity `s_k` is the value change for a 1 bp rise, divided by 0.0001; `WS_k = RW_k s_k`, with `RW` 1.6% at 1Y, 1.3% at 2Y, 1.2% at 3Y and 1.1% from 5Y (MAR21.42); within a currency `K = sqrt(Σ WS_k² + Σ_{k≠l} ρ_kl WS_k WS_l)` with `ρ = max(exp(−3% |T_k − T_l|/min(T_k, T_l)), 40%)` (MAR21.46); and the whole is computed under medium, high and low correlation scenarios, the largest being the capital (MAR21.6, MAR21.7). Worked example: Tutorial 1's swap has its risk almost all at 5Y, 4,594.44 per bp, which is 45,944,422 as an `s_k`. Alone, that gives 1.1% × 45,944,422 = 505,389. The three small short-tenor sensitivities have the same sign and are highly correlated with it, which lifts the charge to 505,810.25. With all sensitivities the same sign, higher correlation means more capital, so the `high` scenario binds.

## Step 2: the same in Rust, Java and C++

Build once as in [Tutorial 1, step 2](tutorial-1-swap.md#step-2-the-same-in-rust-java-and-c), then:

<!-- tutorial:run rust -->
```bash
python examples/tutorials/t5_risk.py rust/target/release/quantforge
```

<!-- tutorial:run java -->
```bash
python examples/tutorials/t5_risk.py java -jar java25/target/quantforge-cli.jar
```

<!-- tutorial:run cpp -->
```bash
python examples/tutorials/t5_risk.py cpp26/build/quantforge
```

Each prints the eight lines of step 1. Each build has its own AAD implementation of the same scheme; they agree to the digits shown.

## For practitioners

- **AAD of the scheme, not the model.** The ladder differentiates the pinned grid scheme. As the grid is refined it converges to the model's sensitivity, but at this grid (101 nodes, 50 steps a year) it is the derivative of this grid's price. That is what a desk wants for hedging that price.
- **VaR quantile rule.** VaR is the inverted empirical distribution (Hyndman and Fan type 1), with no interpolation between order statistics. Systems that interpolate, or that take `k = floor(n c)`, will report a different loss at the same confidence.
- **Static backtest.** This page holds one VaR fixed for 250 days to keep the arithmetic visible. A real backtest recomputes VaR every day on a rolling window.
- **GIRR inputs.** The FRTB sensitivities here are central-difference par-rate DV01s, bumped quote by quote. MAR21 defines `s_k` as a one-sided 1 bp shift of the risk-free curve at that tenor; the two agree to first order. Tutorial 1's 7Y and 10Y key rates are exactly 0 for a 5Y swap, so they are left out, which matters because 7Y is not a GIRR vertex.

## Common mistakes

- Reading VaR as the worst loss. At 99% on 250 days it is the third-worst; the worst two are beyond it, which is what ES measures.
- Counting a day as an exception when the P&L is a gain larger than VaR. Exceptions are losses: `−pnl > VaR`.
- Passing DV01 directly as `sensitivity` to `risk.frtb.girr_delta`. MAR21's `s_k` is DV01 divided by 0.0001, which is 10,000 times larger.

## What you just did

You computed the full sensitivity ladder of a Bermudan swaption by AAD and confirmed two of its entries by bumping, measured 99% VaR and ES on 250 days of P&L, backtested that VaR on the next 250 days with Kupiec's test and the traffic light, and turned a swap's key-rate risk into an FRTB GIRR delta charge. All four languages printed the same digits.

- Maths in context: [LEARN, VaR, expected shortfall and backtests](../../LEARN.md#var-expected-shortfall-and-backtests), [FRTB standardised capital for rates](../../LEARN.md#frtb-standardised-capital-for-rates), [risk of a whole book in one pass](../../LEARN.md#risk-of-a-whole-book-in-one-pass).
- Commands: [COOKBOOK, stage F recipes](../../COOKBOOK.md#stage-f-recipes) and [stage G recipes](../../COOKBOOK.md#stage-g-recipes).
- The rules: `specifications/06-risk/aad-core.md`, `var-es-and-backtests.md`, `frtb-sa-girr.md`, `rates-sensitivities.md`. Golden cases: `datasets/golden/stage_g/aadladder_g.json`, `stage_f/risk_f4.json`, `stage_f/frtb_f.json`.
- Terms: [GLOSSARY, stage F](../../GLOSSARY.md#stage-f-terms) (VaR, ES, FRTB-SA) and [tutorial terms](../../GLOSSARY.md#tutorial-terms) (AAD, bump and revalue, backtest).

## Try next

- Set `"confidence": 0.975` in the VaR call. With 250 days, `k = ceil(243.75) = 244`, so VaR becomes the seventh-largest loss.
- Pass `"specified_currency_reduction": true` to the GIRR call. USD is a specified currency, so the risk weights fall by `sqrt(2)` and so does the capital.
- Print `aad["d_price_d_discount_factors"]`: the sensitivity to each of the ten curve pillars. The last payment, at year 6, is interpolated between the 5-year and 7-year pillars, so the four pillars from 10 years on have no effect and their entries are 0.

## References and further reading

Links checked 2026-11-11. "Not opened" means the spec cites the source from memory.

- M. Giles and P. Glasserman, "Smoking adjoints: fast Monte Carlo Greeks", *Risk*, January 2006; A. Griewank and A. Walther, *Evaluating Derivatives*, 2nd ed., SIAM, 2008, chapter 3 (cited in `aad-core.md`, not opened; no stable free link).
- P. Kupiec, "Techniques for verifying the accuracy of risk measurement models", *Journal of Derivatives* 3(2), 1995, 73-84. <https://doi.org/10.3905/jod.1995.407942> (paywalled; cited in `var-es-and-backtests.md` [S6], not opened).
- C. Acerbi and D. Tasche, "On the coherence of expected shortfall", *Journal of Banking and Finance* 26(7), 2002, 1487-1503. <https://doi.org/10.1016/S0378-4266(02)00283-2> (paywalled; [S4], not opened).
- Basel Committee on Banking Supervision, *Supervisory framework for the use of "backtesting" in conjunction with the internal models approach to market risk capital requirements*, January 1996, Table 2: <https://www.bis.org/publ/bcbs22.htm> (free; [S8], not opened by the spec).
- Basel Committee, *Basel Framework*, MAR21 "Standardised approach: sensitivities-based method" (MAR21.4 to MAR21.7 and MAR21.42 to MAR21.50 read by the spec author): <https://www.bis.org/basel_framework/chapter/MAR/21.htm> (free; on 2026-11-11 this address redirected to the BIS page for the MAR standard).
- P. Jorion, *Value at Risk*, 3rd ed., McGraw-Hill, 2007 (book; [S1], not opened).
- This project: [LEARN](../../LEARN.md#stage-f-curves-portfolio-risk-and-the-book), [COOKBOOK](../../COOKBOOK.md#stage-f-recipes), [GLOSSARY](../../GLOSSARY.md#tutorial-terms).
