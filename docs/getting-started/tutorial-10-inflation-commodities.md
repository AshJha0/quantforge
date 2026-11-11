# Tutorial 10: inflation and commodities

The plain idea: an inflation curve and a commodity curve are both forward curves for a price, not for a rate. Inflation swap quotes tell you what the market expects the consumer price index (CPI) to be in one, two, five years; futures quotes tell you what gas or oil will cost in each delivery month. Between quotes you interpolate, and both markets have a pattern by calendar month, [seasonality](../../GLOSSARY.md#stage-d-curves-and-fixed-income), that straight-line interpolation would smear out. With the inflation curve you can price a zero-coupon inflation swap; with commodity forwards and a funding curve you can ask whether buying now, storing and selling later makes money.

This tutorial does four things with library operations: a CPI curve with and without seasonality, a zero-coupon inflation swap (ZCIS: one payment at maturity, inflation over the period against a fixed rate compounded over the period), a seasonal gas forward curve, and storage carry on an oil curve. It runs in Python, then the same cases through the Rust, Java and C++ command-line programs. Budget 10 to 15 minutes. All data is synthetic, taken from the golden cases `inflation_d-0002` and `inflation_d-0007` and the examples `examples/commodity_forward_d.json` and `examples/commodity_carry_d.json`; it is not market data. CI runs every code block on this page (`.github/workflows/tutorial.yml`) and fails if a printed line differs.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [tutorial 1](tutorial-1-swap.md).
- Knowing what a discount factor is (tutorial 1). Months are counted with an index `k = 12 × year + month − 1`, so August 2026 is `index(2026, 8)`.

## Step 1: Python

```bash
uv sync --locked --project python
```

The script `examples/tutorials/t10_inflation_commodities.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t10_inflation_commodities.py -->
```python
"""Tutorial 10: a CPI curve with seasonality, a zero-coupon inflation
swap, a commodity forward curve and storage carry.

  uv run --project python python examples/tutorials/t10_inflation_commodities.py         # Python
  python examples/tutorials/t10_inflation_commodities.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-10-inflation-commodities.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys

from qf import runner

QUOTES = [{"years": y, "rate": r} for y, r in
          [(1, 0.0265), (2, 0.0255), (3, 0.025), (5, 0.0245), (7, 0.0245), (10, 0.025), (20, 0.0255)]]
SEASON = [0.9978, 0.9992, 1.0011, 1.0018, 1.0012, 1.0005,
          0.9989, 0.9994, 1.0006, 1.0003, 0.9995, 0.9997]
DISCOUNT = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF", "pillars": [
    {"date": d, "discount_factor": v} for d, v in
    [("2027-11-15", 0.9634397330592425), ("2028-11-14", 0.9318539967570951),
     ("2029-11-15", 0.9012037662703272), ("2031-11-13", 0.839287128565213)]]}
GAS = [{"month": m, "price": p} for m, p in
       [("2026-12", 3.42), ("2027-03", 3.105), ("2027-06", 2.88),
        ("2027-12", 3.56), ("2028-12", 3.64), ("2030-12", 3.7)]]
GAS_SEASON = [0.06, 0.045, 0.01, -0.03, -0.045, -0.04, -0.02, -0.015, -0.02, 0.0, 0.025, 0.03]
FUNDING = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF", "pillars": [
    {"date": d, "discount_factor": v} for d, v in
    [("2027-05-06", 0.9803598150999601), ("2027-11-08", 0.9615452062959098),
     ("2028-11-06", 0.9267197211276171), ("2031-11-06", 0.8310200391947283)]]}
OIL = [{"date": d, "price": p} for d, p in
       [("2026-12-15", 75.2), ("2027-03-15", 74.1), ("2027-06-15", 75.9),
        ("2027-12-15", 78.4), ("2028-12-15", 76.0)]]


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
    smooth = {"base_month": "2026-08", "base_cpi": 322.15, "quotes": QUOTES, "seasonality": None}
    seasonal = {**smooth, "seasonality": SEASON}
    months = ["2026-12", "2027-01", "2027-08"]
    trade = {"years": 5, "fixed_rate": 0.026, "notional": 10_000_000.0, "side": "RECEIVE_INFLATION",
             "payment_date": "2031-11-10"}
    cpi_s, cpi_x, zcis, gas, carry = batch(cli, [
        case("t10-cpi-smooth", "infl.curve.cpi", {**smooth, "months": months}),
        case("t10-cpi-seasonal", "infl.curve.cpi", {**seasonal, "months": months}),
        case("t10-zcis", "infl.zcis.pv", {"curve": seasonal, "discount": DISCOUNT, "trade": trade}),
        case("t10-gas", "cmdty.curve.forward", {"quotes": GAS, "seasonality": GAS_SEASON,
                                                "months": ["2027-01", "2027-08", "2028-07"]}),
        case("t10-carry", "cmdty.storage.carry", {"funding": FUNDING, "forwards": OIL,
                                                  "storage_cost": 0.02})])
    for label, out in (("smooth  ", cpi_s), ("seasonal", cpi_x)):
        print(label, " ".join(f"{x:.4f}" for x in out["cpi"]))
    print(f"ZCIS index ratio {zcis['index_ratio']:.10f}")
    print(f"ZCIS PV {zcis['pv']:.2f}")
    print("gas forwards", " ".join(f"{x:.6f}" for x in gas["forwards"]))
    for f, y, v, a in zip(OIL[1:], carry["convenience_yields"], carry["carry_values"], carry["arbitrage"]):
        print(f"to {f['date']} convenience yield {y:+.6f} carry {v:+.6f} arbitrage {a}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t10_inflation_commodities.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
smooth   324.9709 325.6800 330.6870
seasonal 325.0684 325.1586 330.6870
ZCIS index ratio 1.1286513716
ZCIS PV -69569.49
gas forwards 3.435279 3.096009 3.430562
to 2027-03-15 convenience yield +0.119761 carry -2.189644 arbitrage False
to 2027-06-15 convenience yield -0.036080 carry +0.670816 arbitrage True
to 2027-12-15 convenience yield -0.006820 carry +0.256357 arbitrage True
to 2028-12-15 convenience yield +0.087927 carry -6.466560 arbitrage False
```

### Reading the numbers

The three CPI columns are December 2026, January 2027 and August 2027.

- **Smooth CPI.** August 2027 is the 1Y pillar: 322.15 × 1.0265 = 330.687, the third column. December 2026 is four months along the first segment, and ln CPI is linear in the month, so it is 322.15 × 1.0265^(4/12) ≈ 322.15 × 1.00875 = 324.97.
- **Seasonal CPI.** Each value is the smooth one times s(month)/s(August). December: 0.9997/0.9994 ≈ 1.0003, so 324.97 becomes 325.07. January: 0.9978/0.9994 ≈ 0.9984, so 325.68 becomes 325.16. August 2027 is unchanged because the factors cancel in the base calendar month; that is why every swap quote still reprices.
- **ZCIS index ratio.** CPI in August 2031 over base CPI: 1.0245^5 = 1.12865, the 5Y quote compounded, as the pillar rule says. This is the [index ratio](../../GLOSSARY.md#stage-d-curves-and-fixed-income) of the swap.
- **ZCIS PV.** You receive 1.12865 − 1 and pay 1.026^5 − 1 = 0.13694. The net is about −0.00829 per unit of notional, −82,900 on 10 million, discounted at about 0.839 to 2031-11-10: about −69,570. You agreed to pay 2.60% where the market's 5Y rate is 2.45%, so the swap is worth less than zero to you.
- **Gas forwards** (January 2027, August 2027, July 2028). January sits a third of the way from December (3.42, seasonal term +0.03) to March (3.105, term +0.01). Deseasonalised logs: ln 3.42 − 0.03 = 1.1996 and ln 3.105 − 0.01 = 1.1230; a third of the way gives 1.1741; add January's +0.06: e^1.2341 = 3.435. The quotes fall from December to March, yet January prints above December, because January is the winter peak.
- **Convenience yield and carry.** The [convenience yield](../../GLOSSARY.md#stage-d-curves-and-fixed-income) is the benefit of holding the physical commodity that the forward curve implies. First leg, December 2026 to March 2027, 90 days, dt = 0.2466: the price falls from 75.2 to 74.1, ln(74.1/75.2)/dt = −0.0598, so y = r + 0.02 + 0.0598, with r about 0.04 from the funding curve (ln(1/0.98036)/0.5 = 0.0397): about 0.12, as printed. The curve is in backwardation (later delivery is cheaper), and the carry trade loses 2.19. Second leg, March to June 2027, 92 days: the price rises from 74.1 to 75.9, faster than funding plus storage, so y is negative and the carry is about 0.98 × (75.9 − 74.1 × e^(0.06 × 0.252)) ≈ 0.98 × (75.90 − 75.23) ≈ 0.66, against the printed 0.670816. `arbitrage` is True exactly when the carry value is positive.

### The formal statement, checked against the spec

From `specifications/02-curves/inflation.md`:

- Month index `k = 12 year + month − 1`. `base_month` b already carries the index lag: it is the last published month the swaps reference. A ZCIS of n whole years quoting K pins `I(b + 12n) = I₀ (1 + K)^n`, whatever the discount curve.
- `ln I` is linear in k between `(b, ln I₀)` and the pillars; after the last pillar the last slope carries on. With 12 positive factors s₁ to s₁₂ (January to December), `I(k) = I_smooth(k) s(k)/s(b)`.
- `infl.zcis.pv`: `index_ratio = I(b + 12 years)/I₀` and `pv = sign × N × (index_ratio − (1 + K)^years) × D(payment_date)`, sign +1 for `RECEIVE_INFLATION`. D comes from an ordinary curve object (log-linear in discount factors here, with times ACT/365F from `as_of`, as for every curve object). The payment date is a trade input; nothing rolls it from the index month.

From `specifications/02-curves/commodity.md`:

- `cmdty.curve.forward`: seasonality is 12 additive log terms σ. `L_j = ln(price_j) − σ(k_j)`, L linear in k between quotes, `F(k) = exp(L(k) + σ(k))`. Every quote reprices. A month outside the quoted range is `E_OUT_OF_RANGE`: no extrapolation (ruling D29).
- `cmdty.storage.carry`: for consecutive forwards, `dt = (d₁ − d₀)/365`, `r = ln(D(d₀)/D(d₁))/dt`, `y = r + u − ln(F₁/F₀)/dt`, carry value `D(d₁)F₁ − D(d₀)F₀ e^(u dt)`, and `arbitrage = carry > 0`. Storage cost u is continuous, a fraction of value per year. This is the cost-of-carry relation `F₁ = F₀ e^((r + u − y) dt)` in Hull's chapter on forward and futures prices.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t10_inflation_commodities.py` sends the five cases above (`infl.curve.cpi` twice, `infl.zcis.pv`, `cmdty.curve.forward`, `cmdty.storage.carry`) to whichever CLI you name and prints the same lines. Given a command line, the same script sends each case to that build's `batch` command (`specifications/cli-contract.md`) instead of the Python package.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t10_inflation_commodities.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t10_inflation_commodities.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t10_inflation_commodities.py cpp26/build/quantforge
```

Each prints the nine lines of step 1, digit for digit at the precision shown. The full checks are `python conformance/runner/runner.py --impl rust --suite inflation_d` and `--suite commodity_d`.

## For practitioners

- **Lag and interpolation.** The spec takes the lag as already applied in `base_month` and puts pillars on whole months. US CPI swaps and TIPS use a three-month lag with daily interpolation of the index (31 CFR 356); euro HICPxT zero-coupon swaps are usually traded on a three-month lag to a whole month, without interpolation (market practice; the confirmation, under the ISDA 2008 Inflation Derivatives Definitions, decides; not opened). Euro inflation-linked bonds, by contrast, do interpolate: the daily reference index is a linear interpolation between the HICPxT of months M−3 and M−2 (Ejsing, García and Werner, ECB Working Paper 830, 2007, appendix A, opened 2026-11-11), so do not carry a swap's lag rule over to OAT€i or BTP€i pricing. QuantLib's zero-inflation curves carry an observation lag and an interpolation choice on the index, so its numbers differ from these unless the conventions are matched. The spec runs no outside library for this suite for that reason.
- **Seasonality.** Here the factors are inputs. Desks usually estimate them from several years of CPI prints and normalise them so the product over a year is one; the spec does not require that, because only the ratio s(k)/s(b) enters.
- **No convexity.** The ZCIS PV is linear in the index ratio. Year-on-year swaps need a convexity adjustment and are not priced here; `infl.cap.yoy_price` takes YoY forwards as inputs.
- **Two seasonality conventions.** Commodity terms are additive in log price (a factor e^σ); CPI factors are multiplicative. Both reprice every quote.
- **Carry is a screen.** "Buying at d₀" means buying the d₀ forward. Real cash and carry also needs storage capacity, financing haircuts and delivery logistics; a positive carry value here is a flag, not a trade.

## Common mistakes

- Putting `base_month` at the trade month. It is the lagged reference month: with a three-month lag, a swap traded in November 2026 references August 2026.
- Seasonality in the wrong order. Position 0 is January for both CPI and commodity terms.
- Asking for a gas forward outside the quoted months. The answer is `E_OUT_OF_RANGE`, by design.
- Reading `arbitrage True` as free money without checking the storage cost you put in.
- Comparing the ZCIS PV with a QuantLib number without matching lag and interpolation.

## What you just did

You built a CPI curve that reprices seven ZCIS quotes, added a monthly pattern that leaves those quotes intact, priced a 5-year receive-inflation swap at −69,569.49, built a gas curve with a winter peak, and found which oil calendar spreads pay for cash and carry. Four implementations printed the same lines.

## Try next

- Set the ZCIS fixed rate to 0.0245. The PV goes to about zero: that is the 5Y quote.
- Ask the curve for a month after the 20Y pillar and check it uses the last slope.
- Raise the storage cost to 0.06 and watch the `arbitrage` flags.
- Price an inflation-linked bond off the same curve with `infl.linker.price_curve`.
- The [Cookbook](../../COOKBOOK.md#stage-d-recipes) lists a golden case for each operation.

## References and further reading

- Our specs: `specifications/02-curves/inflation.md` and `specifications/02-curves/commodity.md`; golden suites `datasets/golden/stage_d/inflation_d.json` and `commodity_d.json`.
- [LEARN: curves and fixed income](../../LEARN.md#curves-and-fixed-income) and [stage D status](../../LEARN.md#stage-d-curves-and-fixed-income); [Glossary, stage D terms](../../GLOSSARY.md#stage-d-curves-and-fixed-income).
- US Treasury, 31 CFR Part 356, Appendix B: reference CPI and index ratio for TIPS (three-month lag, daily interpolation). [Text at Cornell LII](https://www.law.cornell.edu/cfr/text/31/part-356). The spec marks it not opened.
- Ejsing, J., García, J. A. and Werner, T., *The term structure of euro area break-even inflation rates: the impact of seasonality*, ECB Working Paper 830, November 2007, appendix A: the daily, interpolated reference index of euro inflation-linked bonds. [PDF at the ECB](https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp830.pdf). Opened 2026-11-11.
- ISDA, *2008 Inflation Derivatives Definitions*: the lag and interpolation terms of inflation swap confirmations. Not opened; members only, no public link.
- Kerkhof, J., *Inflation Derivatives Explained*, Lehman Brothers Fixed Income Quantitative Research, 2005: zero-coupon inflation swaps and seasonality. The spec marks it not opened; no stable link.
- Brigo, D. and Mercurio, F., *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006, chapter on inflation derivatives. [doi:10.1007/978-3-540-34604-3](https://doi.org/10.1007/978-3-540-34604-3) (paywalled). The spec marks it not opened.
- Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Determination of Forward and Futures Prices": storage costs, convenience yield, cash and carry. The spec marks it not opened; no stable link.
- Geman, H., *Commodities and Commodity Derivatives*, Wiley, 2005: forward-curve seasonality. The spec marks it not opened; no stable link.
- QuantLib, [ZeroInflationIndex reference](https://www.quantlib.org/reference/class_quant_lib_1_1_zero_inflation_index.html), for its lag and interpolation settings (not used as an oracle here).

Links checked 2026-11-11.
