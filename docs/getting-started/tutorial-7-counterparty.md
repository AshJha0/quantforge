# Tutorial 7: counterparty risk

The plain idea: when you trade a swap with a bank or a fund, you are exposed to it defaulting. If it defaults while the swap is worth something to you, you lose that value, less what you recover. Today the swap may be worth almost nothing, but rates will move, so the question is what it could be worth at each future date. The **exposure profile** answers that: the **expected exposure** (EE), the average positive value at each date, and the **potential future exposure** (PFE), a high quantile of it. Weighting the expected exposure by the chance of default in each period gives the **credit valuation adjustment** (CVA), the price of that risk. A **collateral agreement** (a CSA) makes the counterparty post cash as the swap moves in your favour, which cuts the exposure and so the CVA.

This tutorial computes a swap's exposure profile and CVA under Hull-White, then shows on four hand-written scenarios what a CSA changes. It uses three stage G operations (waves 4a to 4c). Budget about 15 minutes after [Tutorial 1](tutorial-1-swap.md); [Tutorial 6](tutorial-6-hull-white.md) introduces the Hull-White model. Every number shown is a real output; CI runs the code in all four languages and fails if a printed line differs.

## What you need

The setup and the three builds of [Tutorial 1](tutorial-1-swap.md#what-you-need). All data is synthetic.

## Step 1: Python

The script `examples/tutorials/t7_counterparty.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t7_counterparty.py -->
```python
"""Tutorial 7: a swap's exposure profile (EE, PFE), its CVA, then what a collateral agreement changes.

  uv run --project python python examples/tutorials/t7_counterparty.py       # Python
  python examples/tutorials/t7_counterparty.py rust/target/release/quantforge  # or any other build
"""
import math
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. Hull-White (a = 3%, sigma = 0.5%) on tutorial 6's curve. We pay 3.9% fixed on 10 million for 5 years,
#    annual payments; the counterparty has a 2% a year default intensity and 40% recovery.
curve = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
swap = {"notional": 10_000_000.0, "fixed_rate": 0.039, "side": "PAY", "start_years": 0.0,
        "payment_times": [1.0, 2.0, 3.0, 4.0, 5.0]}
dates = [1.0, 2.0, 3.0, 4.0]  # the reset dates: each just after a payment
x = call("xva.exposure.portfolio_hw", {"curve": curve, "mean_reversion": 0.03, "sigma": 0.005, "trades": [swap],
                                       "exposure_times": dates, "pfe_quantiles": [0.95],
                                       "hazard_rate": 0.02, "recovery": 0.4})
print("  t    discounted EE   discounted ENE   PFE 95%")
for t, ee, ene, pfe in zip(dates, x["discounted_ee"], x["discounted_ene"], x["deflated_pfe_95"]):
    print(f"{t:4.1f} {ee:15.2f} {ene:16.2f} {pfe:10.2f}")
print(f"EPE {x['epe']:.2f}  CVA {x['cva']:.2f}")

# 2. Collateral, shown on four hand-written scenarios so every number can be checked by hand:
#    the netting set's value on each path at 0, 3, 6, 9 and 12 months.
times = [0.0, 0.25, 0.5, 0.75, 1.0]
paths = [[0.0, 3.0, 5.0, 2.0, -1.0], [0.0, -2.0, -4.0, -6.0, -3.0],
         [0.0, 1.0, 6.0, 9.0, 4.0], [0.0, 0.5, -1.0, 2.5, 7.0]]
trades = [{"netting_set": "NS1", "values": paths}]
csa = {"NS1": {"threshold_receive": 1.0, "threshold_post": 1.0, "minimum_transfer_amount": 0.5, "mpor_steps": 1}}
bare = call("xva.exposure.collateralised", {"times": times, "trades": trades, "pfe_quantile": 0.75})["netting_sets"]["NS1"]
held = call("xva.exposure.collateralised", {"times": times, "trades": trades, "pfe_quantile": 0.75,
                                            "csa": csa})["netting_sets"]["NS1"]
for name, r in [("no CSA", bare), ("CSA   ", held)]:
    print(f"{name}  EE " + " ".join(f"{v:.3f}" for v in r["ee"]) + f"  EPE {r['epe']:.5f}")

# 3. CVA of each profile: counterparty 2% intensity, 40% recovery, flat 3% continuous discounting.
#    Our own default intensity is set to 0, so this is the unilateral CVA.
dfs = [math.exp(-0.03 * t) for t in times[1:]]
names = {"counterparty": {"hazard_rate": 0.02, "recovery": 0.4}, "own": {"hazard_rate": 0.0, "recovery": 0.4},
         "funding": {"borrow_spread": 0.0, "lend_spread": 0.0, "exclude_dva_overlap": False}}
for name, r in [("no CSA", bare), ("CSA   ", held)]:
    a = call("xva.adjustments.value", {"times": times[1:], "discount_factors": dfs, "ee": r["ee"][1:],
                                       "ene": r["ene"][1:], **names})
    print(f"{name}  CVA {a['cva']:.6f}")
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t7_counterparty.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
  t    discounted EE   discounted ENE   PFE 95%
 1.0        73697.96        -61436.62  285775.34
 2.0        74187.68        -66020.34  289428.97
 3.0        59889.67        -52388.32  230050.32
 4.0        33616.93        -29938.80  128195.70
EPE 60348.06  CVA 2799.32
no CSA  EE 0.000 1.125 2.750 3.375 2.750  EPE 2.50000
CSA     EE 0.000 1.125 2.250 1.625 1.875  EPE 1.71875
no CSA  CVA 0.029052
CSA     CVA 0.020013
```

### Reading the numbers

**The swap and the model.** You pay 3.9% fixed on 10 million and receive a floating rate, with annual payments for five years. On this curve 3.9% is close to the par rate, so the swap is worth little today. Rates follow Hull-White with mean reversion 3% and short-rate volatility 0.5% (about 50 bp a year). Exposure is measured at each reset date, just after a payment, when the remaining floating leg is worth par.

**Exposure profile.** Plain idea: at each date the swap's value is uncertain. Exposure is the part you would lose on default, the positive part; the **expected negative exposure** (ENE) is the average of the negative part, what the counterparty would lose. Formally (spec `06-risk/xva-exposure-portfolio.md`): with `f` the netting set's value at `t` divided by the model's numeraire, `discounted_ee(t) = E[max(f, 0)]` and `discounted_ene(t) = E[min(f, 0)]`, computed by exact one-dimensional integration because a one-factor model makes the value a function of one normal variable. Both are in today's money.

Worked example, a check you can do with the curve alone: `EE + ENE = E[f]`, the value today of the payments after `t`. At year 1 that is 73,697.96 − 61,436.62 = 12,261.34, and pricing the remaining four payments off the curve, `N (P(0,1) − P(0,5) − 0.039 Σ_{j=2..5} P(0,j))`, also gives 12,261.34 (with `P` interpolated log-linearly as in Tutorial 6). The same holds at years 2, 3 and 4 to the cent.

The profile has the classic **hump**: early on, rates have had little time to move; late on, few payments are left. The PFE at 95% is the exposure exceeded with 5% probability, about four times the EE here.

**EPE and CVA.** `epe` is the time-average of the discounted EE over the dates, `Σ EE_i (t_i − t_{i−1}) / t_n` = (73,697.96 + 74,187.68 + 59,889.67 + 33,616.93)/4 = 60,348.06. CVA is the loss given default times the discounted EE times the probability of default in each period: `CVA = (1 − R) Σ EE_i (e^{−h t_{i−1}} − e^{−h t_i})` (spec, G-16 buckets; Gregory 2015). With `h = 2%`, the first year's default probability is `1 − e^{−0.02} = 0.0198`, so a first guess is CVA ≈ 0.6 × 0.0198 × (sum of the four EEs) = 0.6 × 0.0198 × 241,392 ≈ 2,868. The exact sum is a little lower, 2,799.32, because each later year's default probability is that of surviving to it times 0.0198. That is about 2.8 bp of notional.

**Collateral, by hand.** Plain idea: under a CSA, once the value in your favour passes a **threshold**, the counterparty posts collateral for the excess, but only in steps of at least the **minimum transfer amount** (MTA), and after a default it takes a while, the **margin period of risk** (MPoR), to close out, during which the value keeps moving. Formally (spec `06-risk/xva-framework.md`, `xva.exposure.collateralised`, ruling G-40): the target collateral is `T(V) = max(V − H_r, 0) − max(−V − H_p, 0)`; a call is made only when the target has moved by at least the MTA since the last call; the collateral held at date `i` is the call from `mpor_steps` dates earlier; exposure is `max(V − C, 0)`.

The four paths are made up so you can follow every number. Worked example at 6 months, with threshold 1, MTA 0.5 and one-step lag:

- at 3 months the values are 3, −2, 1, 0.5, so the targets are 2, −1, 0, 0, and each move from 0 is at least the MTA, so those are called;
- at 6 months the values are 5, −4, 6, −1 and the collateral held is the 3-month call, 2, −1, 0, 0;
- the exposures `max(V − C, 0)` are 3, 0, 6, 0, whose mean is 2.25, against 2.75 without a CSA.

Over the year the CSA cuts EPE from 2.5 to 1.71875. It does not reach zero, because of the threshold and the lag.

**CVA with and without collateral.** `xva.adjustments.value` applies the same CVA formula to each EE profile with a 2% hazard, 40% recovery and discount factors `e^{−0.03 t}` (spec, ruling G-41). Collateral cuts CVA from 0.029052 to 0.020013, by 31%. Both are in the units of the paths.

## Step 2: the same in Rust, Java and C++

Build once as in [Tutorial 1, step 2](tutorial-1-swap.md#step-2-the-same-in-rust-java-and-c), then:

<!-- tutorial:run rust -->
```bash
python examples/tutorials/t7_counterparty.py rust/target/release/quantforge
```

<!-- tutorial:run java -->
```bash
python examples/tutorials/t7_counterparty.py java -jar java25/target/quantforge-cli.jar
```

<!-- tutorial:run cpp -->
```bash
python examples/tutorials/t7_counterparty.py cpp26/build/quantforge
```

Each prints the eleven lines of step 1.

## For practitioners

- **Discounted PFE.** `deflated_pfe_95` (ruling R6-5.6) is a quantile of the discounted exposure under the model's measure, the quantity ORE's exposure cube holds. Many systems report PFE undiscounted, in future money; the two differ by roughly a discount factor.
- **Exposure dates.** `xva.exposure.portfolio_hw` measures only at reset dates, where the floating leg is at par. Exposure between payments, including the spike just before a payment, is not on this grid.
- **Outside check.** The exposures are checked against ORE 1.8.17 by Monte Carlo: 80 of the 96 value cases fall within the registered statistical rule, and the 16 that do not fail on one ill-conditioned check each (spec, "Outside share").
- **Unilateral CVA.** Setting our own hazard to 0 removes the first-to-default weight `S_b` from the formula. With both hazards positive the operation also returns DVA and the funding terms.
- **Effective EPE** (Basel CRE53) is also returned by `xva.exposure.collateralised` for regulatory exposure; it is not used on this page.

## Common mistakes

- Treating EE as the expected value of the swap. EE is the average of the positive part only; the swap's expected value is EE + ENE.
- Expecting a CSA to remove exposure. Thresholds, the MTA and the margin period of risk all leave some.
- Mixing discounted and undiscounted profiles in a CVA formula. `portfolio_hw` returns discounted EE and applies no further discounting; `xva.adjustments.value` takes undiscounted EE and the discount factors separately.

## What you just did

You computed the exposure profile of a swap under Hull-White, checked it against the curve with `EE + ENE`, turned it into a CVA, then worked through a collateral agreement on four scenarios by hand and measured how much it cuts exposure and CVA. All four languages printed the same digits.

- Maths in context: [LEARN, exposure and xVA](../../LEARN.md#exposure-and-xva).
- Commands: [COOKBOOK, stage G recipes](../../COOKBOOK.md#stage-g-recipes).
- The rules: `specifications/06-risk/xva-exposure-portfolio.md`, `xva-exposure.md`, `xva-framework.md`. Golden cases: `datasets/golden/stage_g/expsim_g.json`, `collexp_g.json` (`collexp_g-0001` and `-0004` are step 2), `xvaadj_g.json`.
- Terms: [GLOSSARY, stage G](../../GLOSSARY.md#stage-g-terms) (EE, ENE, PFE, EPE, MPoR, CVA) and [tutorial terms](../../GLOSSARY.md#tutorial-terms) (CSA, threshold, minimum transfer amount).

## Try next

- Change `"side"` to `"RECEIVE"`. EE and ENE swap roles, with signs reversed.
- Set `"mpor_steps": 0` in the CSA. With no lag the EPE falls further, to 0.59375 (golden case `collexp_g-0005`).
- Set both thresholds and the MTA to 0 with no lag: exposure is 0 on every path (`collexp_g-0007`).

## References and further reading

Links checked 2026-11-11. "Not opened" means the spec cites the source from memory.

- J. Gregory, *The xVA Challenge*, 3rd ed., Wiley, 2015: exposure (EE, PFE, EPE), collateral and CVA (book, paywalled; cited in `xva-exposure.md` and `xva-framework.md`, not opened in the former).
- D. Brigo, M. Morini and A. Pallavicini, *Counterparty Credit Risk, Collateral and Funding*, Wiley, 2013 (book, paywalled; first-to-default weighting).
- R. Lichters, R. Stamm and D. Gallagher, *Modern Derivatives Pricing and Credit Exposure Analysis*, Palgrave Macmillan, 2015, chapter 11 (the LGM form of Hull-White used for exposure; book, paywalled; not opened).
- J. Hull and A. White, "CVA and wrong-way risk", *Financial Analysts Journal* 68(5), 2012. <https://doi.org/10.2469/faj.v68.n5.6> (paywalled; the wrong-way extension `xva.wwr.cva_hw`, not used here).
- Basel Committee, *Basel Framework*, CRE53 (internal model method: EE, effective EE, effective EPE): <https://www.bis.org/basel_framework/chapter/CRE/53.htm> (free; on 2026-11-11 this address redirected to the BIS page for the CRE standard).
- ORE (Open Source Risk Engine) documentation, the outside check for exposures: <https://www.opensourcerisk.org/documentation/> (free).
- This project: [LEARN](../../LEARN.md#stage-g-rates-models-and-xva), [COOKBOOK](../../COOKBOOK.md#stage-g-recipes), [GLOSSARY](../../GLOSSARY.md#stage-g-terms).
