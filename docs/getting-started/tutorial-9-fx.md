# Tutorial 9: cross-currency and FX

The plain idea: today's exchange rate and the rate for a later date are linked by the two currencies' interest rates. If you can borrow in one currency and lend in the other, the forward rate is pinned by what the two deposits grow to. That is covered interest parity. A cross-currency swap exchanges floating interest in two currencies, and its quoted spread (the cross-currency basis) measures how far the market sits from that parity. An FX option is the right to exchange at a fixed rate. It is priced like an equity option, with the foreign interest rate in place of a dividend yield, and the market quotes it by delta and volatility rather than by strike and price.

This tutorial does all three with library operations: an FX forward and its basis, a cross-currency swap curve and a trade on it, and FX options with the smile conventions the market quotes in. First Python, then Rust, Java and C++. Budget 15 minutes. All data is synthetic: the curves are the ones shipped in `examples/fx_forward_outright.json` and `examples/xccy_bootstrap_d.json`, and the option inputs are those of golden cases `fxs_e-0001`, `fxs_e-0118` and `fxs_e-0120` in `datasets/golden/stage_e/fxs_e.json`. Every number shown is a real output, and CI checks that every code block on this page prints it.

Terms are defined where they first appear, and in the glossary: forward points under [stage B](../../GLOSSARY.md#stage-b-fx-and-rates-slices), cross-currency basis and NDF under [stage D](../../GLOSSARY.md#stage-d-curves-and-fixed-income), premium-adjusted delta, DNS, risk reversal and butterfly under [stage E](../../GLOSSARY.md#stage-e-full-volatility-exotics-rates-vol-correlation-and-credit).

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell. The code reads two JSON files from `examples/`, so the working directory matters.
- [uv](https://docs.astral.sh/uv/). It fetches Python 3.15 and NumPy for you.
- [Tutorial 1](tutorial-1-swap.md), for what a discount curve and a bootstrap are.

## Step 1: Python

```bash
uv sync --locked --project python
```

The script `examples/tutorials/t9_fx.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t9_fx.py -->
```python
"""Tutorial 9: FX forwards, a cross-currency swap and FX options.

  uv run --project python python examples/tutorials/t9_fx.py         # Python
  python examples/tutorials/t9_fx.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-9-fx.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
Run it from the repository root: the curves are read from examples/*.json (synthetic data).
"""
import json
import sys

from qf import runner

EURUSD = {"spot": 1.085, "expiry_years": 0.2493150684931507, "domestic_rate": 0.043, "foreign_rate": 0.031}
USDJPY = {"spot": 151.2, "expiry_years": 0.4986301369863014, "domestic_rate": 0.001, "foreign_rate": 0.045}


def example(name):
    with open(f"examples/{name}.json") as f:
        return json.load(f)["inputs"]


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return results


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
    g = example("fx_forward_outright")
    market = {"pair": "GBPUSD", "spot": 1.28, "as_of": "2026-11-06",
              "base_curve": g["base_curve"], "quote_curve": g["quote_curve"]}
    x = example("xccy_bootstrap_d")
    usd, estr = x["domestic"], x["foreign_projection"]
    smile = {"atm_vol": 0.075, "rr": -0.0045, "bf": 0.002, "delta": 0.25, "delta_type": "SPOT", "atm_type": "DNS"}
    jp_smile = {"atm_vol": 0.105, "rr": -0.015, "bf": 0.0035, "delta": 0.25, "delta_type": "SPOT_PA",
                "atm_type": "DNS"}
    option = {**EURUSD, "strike": 1.1209, "vol": 0.075, "option_type": "CALL"}
    first = batch(cli, [
        case("t9-spot", "fx.spot_date", {"pair": "GBPUSD", "trade_date": "2026-11-06"}),
        case("t9-fwd", "fx.forward.outright", {**market, "value_date": "2027-11-10"}),
        case("t9-implied", "fx.curve.implied", {**market, "points": [{"tenor": "1Y", "points": -71.0}]}),
        case("t9-xccy", "fx.xccy.bootstrap", {"domestic": usd, "foreign_projection": estr,
                                              "domestic_convention": "SOFR", "foreign_convention": "ESTR",
                                              "start": "2026-11-10", "quotes": x["quotes"],
                                              "interpolation": "LOG_LINEAR_DF"}),
        case("t9-gk", "fx.option.price", {**option, "notional": 1_000_000.0}),
        case("t9-deltas", "fx.delta.from_strike", option),
        case("t9-eu", "fx.smile.from_quotes", {**EURUSD, **smile}),
        case("t9-jp", "fx.smile.from_quotes", {**USDJPY, **jp_smile}),
    ])
    spot, fwd, implied, boot, gk, deltas, eu, jp = (r["outputs"] for r in first)
    error = first[3]["diagnostics"]["max_repricing_error"]
    eur_disc = {"as_of": usd["as_of"], "interpolation": "LOG_LINEAR_DF", "pillars": boot["pillars"]}
    trade = {"start": "2026-11-10", "months": 24, "foreign_notional": 10_000_000.0, "spread": 0.0015,
             "side": "RECEIVE_FOREIGN"}
    [xpv] = (r["outputs"] for r in batch(cli, [case("t9-xpv", "fx.xccy.pv", {
        "domestic": usd, "foreign_projection": estr, "foreign_discount": eur_disc, "spot": 1.085,
        "trade": trade})]))
    node = implied["nodes"][0]
    print(f"spot date {spot['spot_date']}")
    print(f"1Y forward {fwd['forward']:.8f}  points {fwd['points']:.4f}")
    print(f"1Y node {node['value_date']}  basis {node['basis_bp']:.4f} bp")
    print(f"EUR xccy discount 2Y {boot['pillars'][1]['discount_factor']:.10f}  repriced {error < 1e-13}")
    print(f"xccy PV {xpv['pv']:.2f} USD  EUR leg {xpv['foreign_leg']:.2f} EUR")
    print(f"GK price {gk['price']:.4f} USD  forward {gk['forward']:.8f}")
    print(f"GK delta {gk['delta']:.4f} EUR  vega {gk['vega']:.4f}")
    print("deltas " + "  ".join(f"{k} {deltas['deltas'][k]:.8f}" for k in ("SPOT", "FORWARD", "SPOT_PA", "FORWARD_PA")))
    print(f"EURUSD ATM {eu['atm_strike']:.8f}  25C {eu['call_strike']:.8f}  25P {eu['put_strike']:.8f}")
    print(f"USDJPY ATM {jp['atm_strike']:.6f}  25C {jp['call_strike']:.6f}  25P {jp['put_strike']:.6f}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t9_fx.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
spot date 2026-11-10
1Y forward 1.28254610  points 25.4610
1Y node 2027-11-10  basis 75.4948 bp
EUR xccy discount 2Y 0.9595837619  repriced True
xccy PV 2263.43 USD  EUR leg 2086.11 EUR
GK price 5011.2442 USD  forward 1.08825094
GK delta 218766.1348 EUR  vega 159367.7828
deltas SPOT 0.21876613  FORWARD 0.22046348  SPOT_PA 0.21414748  FORWARD_PA 0.21580899
EURUSD ATM 1.08901429  25C 1.11651859  25P 1.06067522
USDJPY ATM 147.512813  25C 155.025751  25P 140.197392
```

### Reading the numbers

**Spot date.** An FX trade agreed today settles on the spot date, here two business days later. Friday 2026-11-06 plus two business days, skipping the weekend, is Tuesday 2026-11-10, open in both London and New York. The spot rate 1.28 is a price for delivery on that date, so forwards are measured from it, not from today.

**Forward and points.** The forward is the rate agreed today for exchange on 2027-11-10. Forward points are forward minus spot in pips (0.0001 for GBPUSD): (1.28254610 − 1.28) / 0.0001 = 25.4610. The forward is above spot because USD, the quote currency, has the higher rate on these curves: near one year the GBP discount factor is about 0.966 and the USD one about 0.963, and a lower discount factor means a higher rate.

**Basis.** Suppose the market quotes the 1Y points at −71.0, not the +25.46 the two OIS curves give. The quoted forward is then 1.28 − 0.0071 = 1.2729, below the curve forward 1.2825 by (1.2825 − 1.2729)/1.28 ≈ 0.0075, about 75 bp over one year. The library reports 75.4948 bp: the extra GBP rate the FX market implies over the GBP OIS curve. A real GBPUSD basis is much smaller; −71 is a synthetic quote that makes the effect easy to see.

**Cross-currency discount curve.** Each quote in `xccy_bootstrap_d.json` is the spread on a EUR €STR leg that makes the swap worth zero against a USD SOFR leg. Solving for the curve that reprices those spreads gives a EUR discount curve for cash flows collateralised in USD. Its 2Y factor 0.9595837619 is below the €STR projection curve's 0.96211 near that date (2028-11-14), so the basis-adjusted EUR curve carries the higher rate. `repriced True` means every quote reprices within 1e-13, the spec's requirement.

**Cross-currency PV.** The trade receives €STR + 15 bp on 10m EUR for two years and pays SOFR flat on 10.85m USD (10m × spot 1.085). The par spread for two years is the 24-month quote, 13.95 bp, so you receive about 1.05 bp too much and the trade is worth more than zero. Check: 10,000,000 × 0.000105 × an annuity of about 1.98 years ≈ 2,080 EUR, against 2,086.11 reported. The USD leg is worth zero (SOFR projected and discounted on its own curve), so the PV is 2,086.11 × 1.085 = 2,263.43 USD.

**Garman-Kohlhagen price.** A 3-month EURUSD call, strike 1.1209, on 1m EUR. EUR is the foreign currency and USD the domestic one, the currency the price is paid in. The forward is S e^((rd−rf)T) = 1.085 × e^(0.012 × 0.2493) = 1.08825094. The strike is 3% above the forward, so the call is out of the money and cheap: 5,011.24 USD, 0.46% of the 1.085m USD face.

**Delta and vega.** Spot delta is 218,766 EUR: the amount of EUR to buy to hedge. That is 0.22 per EUR, as expected for a strike this far out. Vega is 159,368 USD per unit of vol, so 1,594 USD per vol point (0.01).

**Four deltas for one option.** Forward delta drops the foreign discount factor: 0.21876613 × e^(0.031 × 0.2493) = 0.21876613 × 1.00776 = 0.22046. Premium-adjusted (PA) delta takes the premium, in foreign currency, off the hedge, because whoever paid it in EUR already holds that much less EUR: 0.21876613 − 5011.2442 / 1,000,000 / 1.085 = 0.21876613 − 0.00461866 = 0.21414747, the printed `SPOT_PA` to the last digit. The same option is a "21.9 delta", a "22.0 delta" or a "21.4 delta" depending on the convention.

**EURUSD smile.** Quotes: ATM vol 7.5%, 25-delta risk reversal −0.45% (call vol minus put vol), 25-delta butterfly 0.20% (average of the two wing vols minus ATM). So call vol = 7.5 + 0.2 − 0.225 = 7.475% and put vol = 7.5 + 0.2 + 0.225 = 7.925%. The ATM strike is the delta-neutral straddle (DNS): the strike where a call's and a put's deltas cancel. For spot delta it is F e^(v²T/2) = 1.08825094 × e^(0.075² × 0.2493 / 2) = 1.08825094 × 1.000701 = 1.08901. The 25-delta call strike 1.1165 lies above it and the 25-delta put strike 1.0607 below.

**USDJPY smile, premium-adjusted.** USDJPY is quoted in JPY per USD, so USD is the foreign currency, and the premium is conventionally paid in USD; the delta is premium-adjusted. The DNS strike then uses e^(−v²T/2): F = 151.2 × e^((0.001 − 0.045) × 0.4986) = 147.92, times e^(−0.105² × 0.4986 / 2) = 0.99725, gives 147.51. With +v²T/2 you would get about 148.33, one of the wrong conventions the goldens are built to catch.

### Formal statement, checked against the specs

- **Forward** (`specifications/02-curves/fx.md`). With `sp` the spot date of `as_of`: `A(T) = D_base(T)/D_base(sp)`, `B(T) = D_quote(T)/D_quote(sp)`, `F(T) = S A(T)/B(T)`, points `(F − S)/pip`. The spot date steps `spot_lag` days counting only days open on both calendars of the pair. For quoted points: `F = S + points × pip`, `implied_ratio = (F/S) B(T)`, `basis_bp = 10000 (−ln(implied_ratio)/tau + ln A(T)/tau)` with `tau = (T − sp)/365` (here 365/365 = 1). The node's value date is `sp` plus the tenor, modified following on the pair's first calendar, then moved forward to a day open on both.
- **Cross-currency** (`specifications/02-curves/cross-currency.md`). Quarterly dates from `start`, modified following on the joint SOFR/€STR calendar; accrual days/360 on both legs. Each leg, with notional exchanges, is `L = N [Σ ((P(s_i)/P(e_i) − 1) + m α_i) D(e_i) + D(T) − D(start)]`. The bootstrap solves the EUR discount curve `D` so that `L_foreign = 0` for each quote, since the USD leg is worth 0. PV in USD is `sign (spot × L_foreign − L_domestic)`, +1 for `RECEIVE_FOREIGN`. The notional is constant, and the spec marks this a synthetic instrument: the market EUR/USD basis swap resets the USD notional each period (mark-to-market), so this curve is not the market cross-currency curve and must not be described as one.
- **Options** (`specifications/05-volatility/fx-smile.md`). `spot` is domestic per foreign; `rd`, `rf` are flat continuous rates; `T` is in years (91/365 and 182/365 here). Per unit of foreign notional, `p = φ Dd (F N(φ d1) − K N(φ d2))`, `d1 = ln(F/K)/(v√T) + v√T/2` (Garman and Kohlhagen 1983). Delta types (Reiswich and Wystup, section 1.3): `SPOT = φ Df N(φ d1)`, `FORWARD = φ N(φ d1)`, `SPOT_PA = φ Df (K/F) N(φ d2)`, `FORWARD_PA = φ (K/F) N(φ d2)`. ATM DNS is `F e^(+v²T/2)` for non-PA deltas and `F e^(−v²T/2)` for PA (section 1.4). Smile: `call_vol = atm + bf + rr/2`, `put_vol = atm + bf − rr/2` (Clark 2011, ch. 3); the call strike is solved at `+delta` and `call_vol`, the put strike at `−delta` and `put_vol`. A PA call delta can have two strikes; the spec takes the upper one (ruling E-A10).

The printed values reproduce the goldens: the 2Y pillar of `xccy_d-0001`, and `fxs_e-0001`, `fxs_e-0118` and `fxs_e-0120`.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t9_fx.py` sends the same inputs to the CLI you name (`specifications/cli-contract.md`) as `fx.spot_date`, `fx.forward.outright`, `fx.curve.implied`, `fx.xccy.bootstrap`, `fx.xccy.pv`, `fx.option.price`, `fx.delta.from_strike` and `fx.smile.from_quotes`, and prints the same ten lines. Given a command line, the same script sends each case to that build's `batch` command (`specifications/cli-contract.md`) instead of the Python package.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t9_fx.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t9_fx.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t9_fx.py cpp26/build/quantforge
```

Each prints the ten lines of step 1, digit for digit at the precision shown. The full checks are the conformance suites: `python conformance/runner/runner.py --impl rust --suite fxs_e` and `--suite xccy_d`.

## For practitioners

- **The implied basis is a quote-driven gap, not a curve.** `fx.curve.implied` turns quoted points into a basis per node. A curve from basis swaps is `fx.xccy.bootstrap`, and only in the constant-notional form. Desk curves, and the cross-currency helpers in QuantLib and ORE, usually use mark-to-market resetting swaps; that variant is row E13 of `specifications/edge-case-register.md` and is not implemented.
- **Only USD SOFR against EUR €STR** in the cross-currency operations at this stage.
- **Flat rates and one time in the option operations.** A desk takes `rd` and `rf` from the two curves and separates expiry from delivery (a spot lag later); here there is one `T` and one flat rate per currency.
- **The butterfly is the smile strangle**, not the broker strangle the market quotes. Converting needs a fitted smile and is out of scope (ruling E-A11), so pass an already converted `bf`.
- **No pair table.** Which delta and ATM type a pair uses (for example spot delta short-dated, forward delta long-dated, PA for USD-premium pairs) is the caller's choice (ruling E-A9). QuantLib's `BlackDeltaCalculator` takes the same choice as an argument; LEARN reports it reproduces `fxs_e-0120`.

## Common mistakes

- Swapping domestic and foreign rates. In EURUSD the domestic currency is USD, so `rd` is the USD rate.
- Discounting spot delta at `rd`. Spot delta uses the foreign discount factor `Df`.
- Reading a spot delta as a forward delta, or dropping the premium adjustment. On the call above that is 0.2188 against 0.2205 against 0.2141, and each gives a different strike.
- Using +v²T/2 for a PA DNS strike.
- Reversing the risk reversal's sign. Here it is call vol minus put vol, so a negative RR makes puts dearer.
- Measuring the forward from today instead of from the spot date.
- Running the code outside the repository root: `examples/*.json` is a relative path.

## What you just did

You found an FX spot date and a forward from two discount curves, read a basis off quoted forward points, bootstrapped a EUR discount curve from cross-currency swap quotes and priced a trade on it, priced an FX call with Garman-Kohlhagen, saw one option's four deltas, and turned ATM, risk reversal and butterfly quotes into strikes, with and without premium adjustment. Four implementations agree on every line.

## Try next

- Change the 1Y points to 25.461. The basis goes to about zero, because those are the points the curves imply.
- Price the cross-currency trade at the 24-month quote's spread, `quotes[1][1]`. The PV goes to about zero.
- Call `fx_smile.delta_to_strike(*eurusd, 0.075, "CALL", deltas["SPOT"], "SPOT")` and check that it returns 1.1209.
- Call `fx_smile.atm_strike` with `atm_type` `"FORWARD"` and `"SPOT"`, and compare with DNS.
- Read [LEARN: FX smile conventions](../../LEARN.md#fx-smile-conventions) and the [Cookbook recipe for an FX forward](../../COOKBOOK.md#price-an-fx-forward).

## References and further reading

- Garman, M. B. and Kohlhagen, S. W., "Foreign currency option values", *Journal of International Money and Finance* 2(3), 1983, pp. 231-237, [doi:10.1016/S0261-5606(83)80001-1](https://doi.org/10.1016/S0261-5606(83)80001-1) (paywalled). The price formula.
- Reiswich, D. and Wystup, U., "FX volatility smile construction", CPQF working paper No. 20, 2009, [EconStor](https://www.econstor.eu/handle/10419/40186) (open access); published in *Wilmott*, 2012. Sections 1.3 to 1.5: delta types, ATM types, strike from delta.
- Clark, I. J., *Foreign Exchange Option Pricing: A Practitioner's Guide*, Wiley, 2011. Chapter 1, spot dates and forward points (marked "not opened" in `fx.md`); chapter 3, ATM, risk reversal and strangle quotes.
- ISDA, EMTA and ICOM, [*1998 FX and Currency Option Definitions*](https://www.isda.org/book/1998-fx-and-currency-option-definitions/) (paid publication; marked "not opened" in `fx.md`). Spot date and business days for currency pairs.
- Fujii, M., Shimada, Y. and Takahashi, A., "A note on construction of multiple swap curves with and without collateral", *FSA Research Review* 6, 2010. Collateralised cross-currency discounting (marked "not opened" in `cross-currency.md`; no link verified).
- QuantLib: [`FxForward`](https://www.quantlib.org/reference/class_quant_lib_1_1_fx_forward.html), the cross-check named in `fx.md`, and [`BlackDeltaCalculator`](https://www.quantlib.org/reference/class_quant_lib_1_1_black_delta_calculator.html), the smile cross-check named in LEARN.
- This project: `specifications/02-curves/fx.md`, `specifications/02-curves/cross-currency.md`, `specifications/05-volatility/fx-smile.md`; [LEARN: FX smile conventions](../../LEARN.md#fx-smile-conventions); [Cookbook: price an FX forward](../../COOKBOOK.md#price-an-fx-forward); [Glossary](../../GLOSSARY.md).

Links checked 2026-11-11.
