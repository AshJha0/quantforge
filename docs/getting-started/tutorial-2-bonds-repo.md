# Tutorial 2: bonds and repo

The plain idea: a fixed-rate bond is a list of known cash flows, so its fair price is the sum of those cash flows, each multiplied by today's value of a dollar paid on its date. That is exactly what the discount curve of [Tutorial 1](tutorial-1-swap.md) gives. Traders do not quote bonds by price alone, though. They quote a **yield**, a single rate that reproduces the price, and they measure rate risk with **duration** and **convexity**. A bond is also something you can lend out for cash. That is a **repo**: you sell the bond today and agree to buy it back later at a price fixed now. The buy-back price is the bond's **forward price**, and the rate built into it is the **repo rate**.

This tutorial goes from the curve to a bond price, to its yield, duration and convexity, then to a 30-day repo and back to the rate implied by its forward price. It uses six operations from stage D. Budget 10 to 15 minutes if you have done Tutorial 1, which builds the four command-line programs this page uses. Every number shown is a real output. CI runs the code on this page in all four languages (`.github/workflows/tutorial.yml`) and fails if any printed line differs from the text.

## What you need

- The setup of [Tutorial 1](tutorial-1-swap.md#what-you-need): a clone, Git Bash or a Unix shell at its root, and [uv](https://docs.astral.sh/uv/).
- For step 2, the three builds from [Tutorial 1, step 2](tutorial-1-swap.md#step-2-the-same-in-rust-java-and-c).

All the data is synthetic and chosen to be easy to follow. None of it is market data.

## Step 1: Python

The script is `examples/tutorials/t2_bonds.py`. Each step sends one operation, by its name in `specifications/name-map.json`, to an implementation and prints a few of its outputs. With no argument it uses the Python package in this process; with a command line it uses that build's CLI instead (see `examples/tutorials/qf.py`). The script is shown in full; CI checks that this listing equals the file.

<!-- tutorial:source examples/tutorials/t2_bonds.py -->
```python
"""Tutorial 2: a fixed-rate bond off a curve, its yield, duration and convexity, then a repo forward.

  uv run --project python python examples/tutorials/t2_bonds.py              # Python
  python examples/tutorials/t2_bonds.py rust/target/release/quantforge       # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. The discount curve of tutorial 1: SOFR swap quotes, bootstrapped (synthetic, not market data).
quotes = [{"tenor": t, "rate": r} for t, r in
          [("1Y", 0.035), ("2Y", 0.0335), ("3Y", 0.033), ("5Y", 0.0335), ("7Y", 0.0345), ("10Y", 0.036)]]
built = call("rates.ois.bootstrap", {"convention": "SOFR", "as_of": "2026-11-06", "quotes": quotes,
                                     "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"})
curve = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF", "pillars": built["pillars"]}

# 2. The bond: 4.25% coupon paid twice a year, maturing 2029-11-15; trade settles 2026-11-09.
bond = {"maturity": "2029-11-15", "coupon": 0.0425, "frequency": 2}
settle = "2026-11-09"
p = call("bond.price.from_curve", {"bond": bond, "settlement": settle, "curve": curve})
print(f"curve price  dirty {p['dirty']:.6f}  accrued {p['accrued']:.6f}  clean {p['clean']:.6f}")

# 3. The yield that gives the same clean price, then duration and convexity at that yield.
y = call("bond.yield.from_price", {"bond": bond, "settlement": settle, "clean_price": p["clean"]})
r = call("bond.price.from_yield", {"bond": bond, "settlement": settle, "yield": y["yield"]})
print(f"yield        {y['yield']:.10f}")
print(f"duration     Macaulay {r['macaulay_duration']:.6f}  modified {r['modified_duration']:.6f}")
print(f"convexity    {r['convexity']:.6f}")

# 4. Repo: finance the bond for 30 days at 3.85%, then recover the rate from the forward price.
term = {"bond": bond, "start": settle, "end": "2026-12-09", "clean_price": p["clean"]}
f = call("repo.forward", {**term, "repo_rate": 0.0385, "gc_rate": None})
back = call("repo.implied_rate", {**term, "forward_clean": f["forward_clean"]})
print(f"repo forward dirty {f['forward_dirty']:.6f}  clean {f['forward_clean']:.6f}  interest {f['interest']:.6f}")
print(f"implied repo {back['repo_rate']:.10f}")
```

Run it:

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t2_bonds.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
curve price  dirty 104.697813  accrued 2.055707  clean 102.642107
yield        0.0332199717
duration     Macaulay 2.809012  modified 2.763116
convexity    9.390443
repo forward dirty 102.903264  clean 102.621496  interest 0.335905
implied repo 0.0385000000
```

### Reading the numbers

**The bond and its dates.** Face value is 100. A 4.25% coupon paid twice a year is 2.125 every 15 May and 15 November until 2029-11-15, when the last coupon and the 100 are paid. Coupon dates step back from maturity by six months and are not moved for weekends (spec `04-pricing/bonds.md`, "Bond object").

**Dirty, clean and accrued.** Plain idea: on 2026-11-09 the buyer pays for the whole next coupon, but the seller has held the bond for most of that coupon period. The **accrued interest** is the seller's share, and the **clean price** is the price without it. Markets quote clean; cash changes hands at dirty (clean plus accrued). Formally, with `prev` and `next` the coupon dates around settlement, `accrued = c (settlement - prev)/(next - prev)`, counting actual days (ACT/ACT ICMA). Worked example: 2026-05-15 to 2026-11-09 is 178 days of a 184-day period, so accrued = 2.125 × 178/184 = 2.055707, the number printed.

**Price off the curve.** The dirty price is the sum of each cash flow times the curve's discount factor, valued at the curve date (2026-11-06) and carried forward to settlement: `dirty = sum CF_k D(d_k) / D(settlement)`, with curve time `t = (date - as_of)/365` (spec `04-pricing/bonds.md`, `bond.price.from_curve`; `02-curves/curve-framework.md`). The clean price, 102.642107, is above 100 because the bond pays 4.25% while the curve's rates over three years are near 3.3%.

**Yield.** Plain idea: the yield is the one rate that, used to discount every cash flow, gives back the price. Formally, with `f = 2` payments a year, `v = 1/(1 + y/f)`, and `w` the fraction of the current coupon period still to run, `dirty = sum CF_k v^(k+w)`, with `k = 0, 1, ...` counting the remaining cash flows. That is semi-annual compounding with ACT/ACT ICMA accrual, which is QuantLib's `BondFunctions` with `Compounded` (spec `04-pricing/bonds.md`, `bond.price.from_yield`). The price falls as the yield rises, so exactly one yield fits: 3.3220%. A check in your head: the bond pays 4.25 − 3.32 = 0.93% a year more than its yield for about 2.8 years, so it should sit about 0.93 × 2.8 ≈ 2.6 above 100, and the clean price is 102.64.

**Duration and convexity.** Plain idea: duration says how far the price moves when the yield moves; convexity says how that sensitivity itself changes. Formally:

- `macaulay_duration = sum ((k+w)/f) CF_k v^(k+w) / dirty`, the present-value-weighted average time to the cash flows, in years;
- `modified_duration = macaulay_duration × v`, which equals `-(1/dirty) d(dirty)/dy`;
- `convexity = sum ((k+w)(k+w+1)/f^2) CF_k v^(k+w+2) / dirty`, which equals `(1/dirty) d²(dirty)/dy²`.

Worked example: Macaulay duration 2.81 years is a little under the 3 years to maturity, because the coupons pull the average forward. For a 1 bp (0.01%) rise in yield, the price falls by about dirty × modified duration × 0.0001 = 104.697813 × 2.763116 × 0.0001 = 0.0289 per 100 face. The convexity term, ½ × 9.39 × 0.0001² × 104.70 = 0.0000049, is negligible for 1 bp and matters only for large moves.

**Repo forward.** Plain idea: in a repo you hand over the bond and receive its dirty price in cash; at the end you repay the cash plus interest and get the bond back. If the bond pays a coupon in between, the coupon goes to you, its economic owner, so the buy-back price is lowered by it. Formally, with repo rate `r` quoted ACT/360 simple:

`forward_dirty = dirty (1 + r (end - start)/360) - sum c (1 + r (end - d)/360)`, over coupons with dates `d` in `(start, end]`, and `forward_clean = forward_dirty - accrued(end)` (spec `04-pricing/bonds.md`, `repo.forward`).

Worked example, 30 days from 2026-11-09 to 2026-12-09 at 3.85%:

- interest = 104.697813 × 0.0385 × 30/360 = 0.335905;
- the coupon of 2.125 on 2026-11-15 is reinvested for the remaining 24 days: 2.125 × (1 + 0.0385 × 24/360) = 2.130454;
- forward dirty = 104.697813 + 0.335905 − 2.130454 = 102.903264;
- accrued at 2026-12-09 is 2.125 × 24/181 = 0.281768 (the period 2026-11-15 to 2027-05-15 has 181 days), so forward clean = 102.621496.

The forward clean price is below today's 102.642107: you earn a 4.25% coupon on the bond and pay 3.85% to finance it, so holding the bond has positive **carry** and the forward is lower.

**Implied repo.** `repo.implied_rate` runs the same formula backwards: given today's price and the forward clean price, which repo rate links them? The forward is linear in `r`, so there is a closed form, and it returns 3.85% exactly. In practice the forward comes from a futures price or a forward trade, and the implied repo rate is how traders compare it with the cash repo market.

## Step 2: the same in Rust, Java and C++

The same script talks to any of the other three builds through its command-line interface (`specifications/cli-contract.md`). Build them once as in [Tutorial 1, step 2](tutorial-1-swap.md#step-2-the-same-in-rust-java-and-c), then:

Rust:

<!-- tutorial:run rust -->
```bash
python examples/tutorials/t2_bonds.py rust/target/release/quantforge
```

Java:

<!-- tutorial:run java -->
```bash
python examples/tutorials/t2_bonds.py java -jar java25/target/quantforge-cli.jar
```

C++:

<!-- tutorial:run cpp -->
```bash
python examples/tutorials/t2_bonds.py cpp26/build/quantforge
```

Each prints the six lines shown in step 1, digit for digit.

## For practitioners

- **Yield convention.** The yield here is street convention for a US Treasury: semi-annual compounding, ACT/ACT ICMA accrual, regular coupon periods only (there is no odd first coupon). It is not a true (business-day adjusted) yield. QuantLib's `BondFunctions` with ACT/ACT ICMA and `Compounded` agree within 1e-10 on the golden suite `stage_d/bonds_d`.
- **Curve price.** The curve carries cash flows by `t = (date - as_of)/365` and values them at the curve date, then divides by `D(settlement)`. Payment dates are not adjusted for holidays.
- **Repo day count.** Repo interest here is ACT/360 simple, the USD convention. GBP gilt repo is ACT/365; use the right one for your market before comparing numbers.
- **Special repo.** `repo.forward` also takes a general collateral rate `gc_rate`. When it is given, the outputs include the special spread and its value; this page passes `null`.

## Common mistakes

- **Mixing clean and dirty.** Discounting gives a dirty price; screens quote clean. Comparing one with the other is an error of the whole accrued amount, here 2.06 per 100.
- **Forgetting the coupon inside the repo term.** Dropping the 2026-11-15 coupon gives a forward dirty price of 105.03 instead of 102.90.
- **Reading modified duration as a time.** Macaulay duration is in years; modified duration is a sensitivity (price change per unit change in yield, as a fraction of price). They differ by the factor `v = 1/(1 + y/2)`.

## What you just did

You took the curve from Tutorial 1, priced a bond from it, turned the price into a yield, measured the bond's rate risk with duration and convexity, then priced a 30-day repo and recovered the repo rate from its forward price. Python, Rust, Java and C++ gave the same digits.

- Maths in context: [LEARN, curves and fixed income](../../LEARN.md#curves-and-fixed-income).
- Commands for other bonds: [COOKBOOK, price a bond from its yield](../../COOKBOOK.md#price-a-bond-from-its-yield) and [recipes that need curves](../../COOKBOOK.md#recipes-that-need-curves).
- The rules: `specifications/04-pricing/bonds.md`; the golden cases `datasets/golden/stage_d/bonds_d.json` and `repo_d.json`.
- Terms: [GLOSSARY, tutorial terms](../../GLOSSARY.md#tutorial-terms) (accrued interest, yield, duration, convexity) and [stage D terms](../../GLOSSARY.md#stage-d-curves-and-fixed-income) (repo).

## Try next

- Change the coupon to 0.033. The clean price moves close to 100 because the coupon is close to the yield.
- Raise the repo rate to 0.045, above the coupon. The forward clean price rises above the spot clean price: the carry is now negative.
- Call `bond.spread.z` with the curve and a clean price of 102.0 to get the Z-spread, the parallel shift of the curve that reprices the bond.

## References and further reading

The spec lists these as sources; "not opened" there means the project's spec authors cited them from memory and did not re-read them. Links were checked on 2026-11-11.

- ICMA rule for ACT/ACT ICMA accrued interest, and the UK Debt Management Office's gilt price-yield formulae: cited in `04-pricing/bonds.md` [S1, S2] (not opened there). No stable free link is given.
- F. J. Fabozzi (ed.), *The Handbook of Fixed Income Securities*, 8th ed., McGraw-Hill, 2012: yield, duration, convexity and repo (book, paywalled; cited as [S4], not opened).
- G. Burghardt, T. Belton, M. Lane and J. Papa, *The Treasury Bond Basis*, 3rd ed., McGraw-Hill, 2005: implied repo and the futures basis (book, paywalled; [S5], not opened).
- QuantLib `BondFunctions`, the outside check for price, yield and durations: <https://www.quantlib.org/reference/struct_quant_lib_1_1_bond_functions.html> (free).
- This project: `specifications/04-pricing/bonds.md`, `specifications/02-curves/curve-framework.md`, [LEARN](../../LEARN.md#curves-and-fixed-income), [COOKBOOK](../../COOKBOOK.md#stage-d-recipes), [GLOSSARY](../../GLOSSARY.md#tutorial-terms).
