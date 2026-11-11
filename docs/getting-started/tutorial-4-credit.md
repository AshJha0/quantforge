# Tutorial 4: credit

The plain idea: a **credit default swap** (CDS) is insurance against a borrower's default. The protection buyer pays a running premium; if the borrower defaults, the seller pays the loss, one minus the **recovery rate**. The market quotes, for each maturity, the **par spread**: the premium that makes the contract worth zero. From those quotes you can work out the market's **survival probabilities**, the chance the borrower has not defaulted by each date. That set of probabilities is a credit curve, and it is to credit what the discount curve of [Tutorial 1](tutorial-1-swap.md) is to rates.

This tutorial bootstraps a CDS curve with the ISDA standard model, prices a five-year CDS on it, reads the survival probabilities, then builds a sector curve from three names. It uses three operations from stage D. Budget 10 to 15 minutes after Tutorial 1. Every number shown is a real output; CI runs the code in all four languages and fails if a printed line differs.

## What you need

The setup and the three builds of [Tutorial 1](tutorial-1-swap.md#what-you-need). All data is synthetic.

## Step 1: Python

The script `examples/tutorials/t4_credit.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t4_credit.py -->
```python
"""Tutorial 4: bootstrap an ISDA CDS curve, price a CDS, read survival, build a sector curve.

  uv run --project python python examples/tutorials/t4_credit.py             # Python
  python examples/tutorials/t4_credit.py rust/target/release/quantforge      # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. Market data (synthetic): a flat discount curve, 40% recovery, par spreads for six CDS tenors.
trade_date = "2026-11-06"
discount = {"as_of": trade_date, "interpolation": "LOG_LINEAR_DF",
            "pillars": [{"date": "2046-11-06", "discount_factor": 0.458161174870904}]}
spreads = [("6M", 0.0045), ("1Y", 0.006), ("3Y", 0.009), ("5Y", 0.012), ("7Y", 0.0135), ("10Y", 0.015)]
quotes = [{"tenor": t, "spread": s} for t, s in spreads]
market = {"trade_date": trade_date, "discount": discount, "recovery": 0.4}

# 2. Bootstrap: find the survival curve under which every quoted CDS is worth zero at its par spread.
curve = call("credit.cds.bootstrap", {**market, "quotes": quotes})
for p in curve["pillars"]:
    print(f"survival to {p['date']}  {p['survival']:.8f}")

# 3. Price: buy 10 million of 5Y protection (maturity 2031-12-20) with the standard 100bp coupon.
hazard = {"as_of": trade_date, "pillars": curve["pillars"]}
trade = {"maturity": "2031-12-20", "coupon": 0.01, "notional": 10_000_000.0, "side": "BUY_PROTECTION"}
c = call("credit.cds.price", {**market, "hazard": hazard, "trade": trade, "payout": "STANDARD"})
print(f"CDS pv {c['pv']:.2f}  upfront {c['upfront']:.8f}  par spread {c['par_spread']:.8f}  rpv01 {c['rpv01']:.6f}")

# 4. Sector curve: weighted average of three names' spread curves (weights 2, 1, 1), then bootstrapped.
names = [{"quotes": [{"tenor": t, "spread": s * m} for t, s in spreads], "weight": w}
         for m, w in [(1.0, 2.0), (1.3, 1.0), (0.8, 1.0)]]
sector = call("credit.curve.composite", {**market, "constituents": names, "scale": 1.0})
print("sector spreads " + " ".join(f"{s:.7f}" for s in sector["spreads"]))
print(f"sector 5Y survival {sector['pillars'][3]['survival']:.8f}")
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t4_credit.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
survival to 2027-06-20  0.99532787
survival to 2027-12-20  0.98871818
survival to 2029-12-20  0.95331842
survival to 2031-12-20  0.89889612
survival to 2033-12-20  0.84499644
survival to 2036-12-20  0.76356747
CDS pv 89977.43  upfront 0.00900255  par spread 0.01200000  rpv01 4.629357
sector spreads 0.0046125 0.0061500 0.0092250 0.0123000 0.0138375 0.0153750
sector 5Y survival 0.89647613
```

### Reading the numbers

**Inputs in market terms.** Spreads are annual rates on the notional: 0.012 is 120 bp a year for five-year protection. Recovery 40% is the assumed fraction of the notional recovered after a default, the usual assumption for senior unsecured debt. The discount curve has a single pillar, so its forward rate is flat (about 3.9% continuously compounded) at every date.

**Dates.** CDS maturities are not "trade date plus five years". Under the ISDA conventions (spec `04-pricing/credit.md`, "Dates"), the trade date 2026-11-06 is after 20 September, so the roll date is 2026-12-20, and a tenor of `nY` matures `n` years after that, on the 20th: 6M is 2027-06-20 and 5Y is 2031-12-20. Premiums accrue ACT/360 between the quarterly dates 20 March, June, September and December.

**Bootstrap.** Plain idea: take the shortest quote, find the constant default rate that makes that CDS worth zero, then move to the next quote, keeping what you have already fitted and solving only for the new piece. Formally: the **hazard rate** `h(t)`, the default rate per year given survival so far, is flat between pillars, and survival is `Q(t) = exp(−∫h)`. For each quote, in tenor order, the hazard on the new piece is solved so that the CDS's par spread equals the quote, to 1e-13 (spec `credit.cds.bootstrap`). Worked example, the "credit triangle": with a flat hazard, the par spread is close to `h (1 − R)`, so a 120 bp five-year spread at 40% recovery means `h ≈ 0.012/0.6 = 2%` a year. Survival over the 5.12 years to 2031-12-20 at 2% would be `e^{−0.02 × 5.12} = 0.90`; the bootstrap gives 0.8989. The spreads rise with maturity, so the hazard rises too, and survival to ten years is 0.7636.

**Price.** Both legs are valued per unit notional on the survival and discount curves (spec `04-pricing/credit.md`, "Legs"):

- the **protection leg** is `(1 − R)` times the discounted probability of default before maturity;
- the **risky annuity**, `rpv01`, is the discounted value of 1 a year paid while the name survives, including the premium accrued up to a default. It is 4.629 here: a little under five years, because of discounting and default.

The standard contract pays a fixed 100 bp coupon, not the par spread, so the difference is paid up front. `upfront = (protection_leg − coupon × rpv01)/Pcs + accrued`, with `Pcs` the discount factor to cash settlement (three business days after the trade date) and `accrued` the coupon accrued since 2026-09-21, the first accrual date (2026-09-20 is a Sunday). The par spread is the bootstrap quote, 0.012, as it should be: the CDS is the 5Y quote itself. Check in your head: the buyer pays 100 bp instead of 120 bp for about 4.5 years of risky annuity (4.63 less the accrued that the par-spread formula takes off), so the upfront is about 0.002 × 4.5 = 0.009 per unit, or 90,000 on 10 million. The PV, 89,977.43, is that upfront valued on the trade date.

**Sector curve.** Plain idea: when a name has no liquid CDS, desks proxy it with a sector or rating curve built from names that do. `credit.curve.composite` takes the weighted average spread at each tenor, `scale × Σ w s / Σ w`, then bootstraps that spread curve (spec `credit.curve.composite`). Here the three names have spreads 1.0, 1.3 and 0.8 times the curve above, with weights 2, 1 and 1, so the sector spread is `(2 × 1.0 + 1.3 + 0.8)/4 = 1.025` times it: 0.0123 at five years, and the sector's survival to 2031-12-20 is 0.8965, a little below the single name's 0.8989.

## Step 2: the same in Rust, Java and C++

Build once as in [Tutorial 1, step 2](tutorial-1-swap.md#step-2-the-same-in-rust-java-and-c), then:

<!-- tutorial:run rust -->
```bash
python examples/tutorials/t4_credit.py rust/target/release/quantforge
```

<!-- tutorial:run java -->
```bash
python examples/tutorials/t4_credit.py java -jar java25/target/quantforge-cli.jar
```

<!-- tutorial:run cpp -->
```bash
python examples/tutorials/t4_credit.py cpp26/build/quantforge
```

Each prints the nine lines of step 1.

## For practitioners

- **Model.** This is the ISDA CDS standard model as QuantLib's `IsdaCdsEngine` implements it (Taylor fix, no accrual bias, piecewise-flat forwards): accrual paid on default, step-in one day after the trade date, cash settlement three business days after, weekends but no holidays. QuantLib's NPVs agree within 7e-16 per unit on the golden suite `stage_d/credit_d`; the ISDA C library itself was not run.
- **Discount curve.** Only `LOG_LINEAR_DF` (flat forwards) is accepted, as the ISDA model assumes; any other interpolation is `E_INPUT`. The real ISDA convention builds this curve from deposit and swap rates; this page gives the curve directly.
- **Survival pillars** are at each quote's maturity date, not maturity plus one day (ruling D20). Some systems put them a day later.
- **Sector curves** here average spreads, then bootstrap. Averaging survival probabilities or hazard rates gives a different curve; the spec fixes the spread average.

## Common mistakes

- Using `trade date + 5 years` as the maturity. Standard CDS mature on 20 June or 20 December.
- Reading the upfront as the PV. The upfront is per unit notional, paid at cash settlement; the PV is in money, valued on the trade date, signed for the buyer.
- Forgetting that the quote and the coupon differ. A standard CDS is quoted by spread but trades with a fixed coupon and an upfront.

## What you just did

You turned six CDS spreads into survival probabilities with the ISDA bootstrap, priced a five-year standard CDS on that curve and checked it against the credit triangle, then built a sector curve from three names. All four languages printed the same digits.

- Maths in context: [LEARN, credit and correlation](../../LEARN.md#credit-and-correlation).
- Commands: [COOKBOOK, recipes that need curves](../../COOKBOOK.md#recipes-that-need-curves) and [a CDS option](../../COOKBOOK.md#a-cds-option).
- The rules: `specifications/04-pricing/credit.md`. Golden cases: `datasets/golden/stage_d/credit_d.json` (`credit_d-0001`, `-0004`, `-0011` use these inputs).
- Terms: [GLOSSARY, stage D](../../GLOSSARY.md#stage-d-curves-and-fixed-income) (CDS, hazard rate) and [tutorial terms](../../GLOSSARY.md#tutorial-terms) (survival probability, recovery rate, upfront, risky annuity).

## Try next

- Set `"recovery": 0.25`. The bootstrap needs less default probability to explain the same spreads, so survival rises.
- Price with `"payout": "DIGITAL"`, which pays 1 on default instead of 1 − R.
- Pass `"scale": 1.5` to `credit.curve.composite` to build a rating curve 50% wider than the sector.

## References and further reading

Links checked 2026-11-11.

- ISDA CDS Standard Model, documentation and free source code: <https://www.cdsmodel.com/> (free; cited in `credit.md` [S1], opened 2026-11-07). Its 2009 Big Bang conventions (fixed coupons, step-in T+1, cash settlement T+3) and the semi-annual roll from 21 December 2015 [S4] fix the dates above.
- ISDA, *2014 ISDA Credit Derivatives Definitions* (paywalled; [S2], not opened).
- D. O'Kane, *Modelling Single-name and Multi-name Credit Derivatives*, Wiley, 2008 (book; [S3], not opened).
- QuantLib `IsdaCdsEngine`, the outside check: <https://www.quantlib.org/reference/class_quant_lib_1_1_isda_cds_engine.html> (free).
- This project: `specifications/04-pricing/credit.md`, [LEARN](../../LEARN.md#credit-and-correlation), [COOKBOOK](../../COOKBOOK.md#stage-d-recipes), [GLOSSARY](../../GLOSSARY.md#tutorial-terms).
