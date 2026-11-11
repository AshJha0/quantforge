# Tutorial 8: build several curves at once

The plain idea: since 2008 a desk no longer uses one curve for everything. One curve, built from overnight indexed swaps, discounts cash flows. A second curve forecasts a term rate such as a 3-month rate, and the swaps that calibrate it are discounted on the first. The two curves are coupled, so they can be solved together, and the same solve tells you how every point on either curve moves when any quote moves. On top of that, money is dearer over year end than the smooth curve suggests, and between quoted dates the curve depends on how you choose to draw it.

This tutorial builds an OIS discount curve, a projection curve on it, solves both together with their Jacobian, adds a year-end turn solved from a quote, and compares three interpolation methods on the same quotes. First in Python, then the same in Rust, Java and C++. Budget 15 minutes if the builds from [tutorial 1](tutorial-1-swap.md) are done. All inputs are synthetic (they are the inputs of golden case `joint_f-0003` in `datasets/golden/stage_f/joint_f.json`, plus one 2M quote from `joint_f-0001`); none is market data. CI runs every code block on this page and fails if any printed line differs.

Terms used below, all in the [glossary](../../GLOSSARY.md#stage-b-fx-and-rates-slices): an [OIS](../../GLOSSARY.md#stage-b-fx-and-rates-slices) is a swap of a fixed rate against a compounded overnight rate (here SOFR); a [discount factor](../../GLOSSARY.md#stage-a-foundation) `D(t)` is today's value of one dollar paid at `t`; a [pillar](../../GLOSSARY.md#stage-b-fx-and-rates-slices) is a dated node of a curve holding a solved discount factor; to [bootstrap](../../GLOSSARY.md#stage-b-fx-and-rates-slices) is to solve the pillars so that every quote reprices; a [projection curve](../../GLOSSARY.md#stage-b-fx-and-rates-slices) forecasts a floating rate while another curve discounts; a [zero rate](../../GLOSSARY.md#stage-b-fx-and-rates-slices) is `-ln(D)/t`; the [Jacobian](../../GLOSSARY.md#stage-a-foundation) is the matrix of sensitivities of curve points to quotes; the [turn of year](../../GLOSSARY.md#stage-d-curves-and-fixed-income) is a one-off jump in discount factors over year end. A [basis point](../../GLOSSARY.md#stage-b-fx-and-rates-slices) (bp) is 0.0001.

## What you need

- Tutorial 1 done: a clone, [uv](https://docs.astral.sh/uv/), and `uv sync --locked --project python` run once.
- For step 2, the three CLIs built as in tutorial 1.

## Step 1: Python

The script `examples/tutorials/t8_multicurve.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t8_multicurve.py -->
```python
"""Tutorial 8: SOFR and term curves, the joint solve, the turn, interpolation.

  uv run --project python python examples/tutorials/t8_multicurve.py         # Python
  python examples/tutorials/t8_multicurve.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-8-multicurve.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys
from datetime import date

from qf import runner

AS_OF = "2026-11-09"
SOFR = [("1M", 0.043), ("3M", 0.0425), ("6M", 0.0412), ("1Y", 0.039),
        ("2Y", 0.0365), ("3Y", 0.0355), ("5Y", 0.0352), ("10Y", 0.0364)]
TERM = [("DEPOSIT", 3, 0.0445), ("FRA", 3, 0.0432), ("FRA", 6, 0.0418),
        ("SWAP", 24, 0.0388), ("SWAP", 60, 0.0376), ("SWAP", 120, 0.0389)]
OIS_QUOTES = [{"tenor": t, "rate": r} for t, r in SOFR]
START, END = "2027-11-16", "2028-02-16"
PROBE = ["2028-05-15", "2033-11-15"]
METHODS = ("LOG_LINEAR_DF", "LINEAR_ZERO", "MONOTONE_CONVEX")


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return results


def curve(pillars, interpolation="LOG_LINEAR_DF"):
    return {"as_of": AS_OF, "interpolation": interpolation, "pillars": pillars}


def term_quote(kind, months, rate):
    key = "start_months" if kind == "FRA" else "months"
    return {"type": kind, key: months, "rate": rate}


def ois_bootstrap(case_id, method):
    return case(case_id, "rates.ois.bootstrap", {"convention": "SOFR", "as_of": AS_OF, "quotes": OIS_QUOTES,
                                                 "interpolation": method, "method": "SEQUENTIAL"})


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
    [disc] = batch(cli, [ois_bootstrap("t8-sofr", "LOG_LINEAR_DF")])
    disc_curve = curve(disc["outputs"]["pillars"])
    [proj] = batch(cli, [case("t8-term", "rates.projection.bootstrap", {
        "discount": disc_curve, "index": "USD-TERM-3M", "as_of": AS_OF,
        "quotes": [term_quote(*q) for q in TERM], "interpolation": "LOG_LINEAR_DF"})])
    proj_curve = curve(proj["outputs"]["pillars"])

    sofr_inst = [{"id": f"SOFR-{t}", "curve": "USD-SOFR", "type": "OIS", "tenor": t, "rate": r} for t, r in SOFR]
    term_inst = [{"id": f"T-{k}{m}", "curve": "USD-TERM-3M", **term_quote(k, m, r)} for k, m, r in TERM]
    turn_inst = [sofr_inst[0], {"id": "SOFR-2M", "curve": "USD-SOFR", "type": "OIS", "tenor": "2M",
                                "rate": 0.0428, "turn": True}, *sofr_inst[1:]]
    cases = [
        case("t8-fwd-ois", "rates.curve.forward", {"curve": disc_curve, "start": START, "end": END, "day_count": "ACT_360"}),
        case("t8-fwd-term", "rates.curve.forward", {"curve": proj_curve, "start": START, "end": END, "day_count": "ACT_360"}),
        case("t8-joint", "rates.curve.joint_solve", {"as_of": AS_OF, "curves": [
            {"name": "USD-SOFR", "type": "OIS", "convention": "SOFR", "interpolation": "LOG_LINEAR_DF"},
            {"name": "USD-TERM-3M", "type": "PROJECTION", "index": "USD-TERM-3M", "discount": "USD-SOFR",
             "interpolation": "LOG_LINEAR_DF"}], "instruments": sofr_inst + term_inst}),
        case("t8-zero-jac", "risk.curve.jacobian", {"as_of": AS_OF, "convention": "SOFR", "quotes": OIS_QUOTES,
                                                    "interpolation": "LOG_LINEAR_DF", "bump_bp": 1.0}),
        case("t8-turn", "rates.curve.joint_solve", {"as_of": AS_OF, "curves": [
            {"name": "USD-SOFR", "type": "OIS", "convention": "SOFR", "interpolation": "LOG_LINEAR_DF",
             "turns": [{"date": "2026-12-31"}]}], "instruments": turn_inst}),
        *[ois_bootstrap(f"t8-{m}", m) for m in METHODS],
    ]
    fwd_ois, fwd_term, joint, zero_jac, turned, *by_method = batch(cli, cases)
    f_ois, f_term = fwd_ois["outputs"]["forward"], fwd_term["outputs"]["forward"]
    err = max(disc["diagnostics"]["max_repricing_error"], proj["diagnostics"]["max_repricing_error"])
    print(f"SOFR curve {len(disc_curve['pillars'])} pillars, term curve {len(proj_curve['pillars'])}, "
          f"both reprice below 1e-13: {err < 1e-13}")
    print(f"SOFR 10Y discount factor {disc_curve['pillars'][-1]['discount_factor']:.12f}")
    print(f"TERM 10Y discount factor {proj_curve['pillars'][-1]['discount_factor']:.12f}")
    print(f"3M forward from {START}: SOFR {f_ois:.4%}  TERM {f_term:.4%}  basis {(f_term - f_ois) * 1e4:.2f} bp")

    solved = joint["outputs"]
    jac = solved["jacobian"]
    row = {u: k for k, u in enumerate(jac["unknowns"])}
    col = {q: k for k, q in enumerate(jac["quotes"])}

    def J(unknown, quote):
        return jac["matrix"][row[unknown]][col[quote]]

    term10, sofr10 = "USD-TERM-3M:pillar:2036-11-12", "USD-SOFR:pillar:2036-11-14"
    print(f"joint TERM 10Y discount factor {solved['curves'][1]['pillars'][-1]['discount_factor']:.12f}")
    print(f"J[TERM 10Y, T-SWAP120] {J(term10, 'T-SWAP120'):.4f}  J[TERM 10Y, SOFR-10Y] {J(term10, 'SOFR-10Y'):.4f}")
    print(f"J[SOFR 10Y, T-SWAP120] is exactly zero: {J(sofr10, 'T-SWAP120') == 0.0}")

    t10 = (date(2036, 11, 14) - date.fromisoformat(AS_OF)).days / 365
    print(f"dz(SOFR 10Y)/dq(SOFR-10Y): bump {zero_jac['outputs']['jacobian'][-1][-1]:.4f}  "
          f"joint -J/t {-J(sofr10, 'SOFR-10Y') / t10:.4f}")

    sens = turned["outputs"]["turn_sensitivity"][0]
    print(f"turn factor {turned['outputs']['turn_factors'][0]['factor']:.8f}")
    print(f"turn sensitivity: SOFR-1M zero {abs(sens[0]) < 1e-12}  SOFR-2M {sens[1]:.4f}  SOFR-3M {sens[2]:.4f}")

    batch_inspect = [case(f"t8-inspect-{m}", "rates.curve.inspect",
                          {"curve": curve(r["outputs"]["pillars"], m), "dates": PROBE})
                     for m, r in zip(METHODS, by_method)]
    for m, r, ins in zip(METHODS, by_method, batch(cli, batch_inspect)):
        fwd = ins["outputs"]["instantaneous_forwards"]
        print(f"{m:<16}10Y DF {r['outputs']['pillars'][-1]['discount_factor']:.6f}  "
              f"fwd {PROBE[0]} {fwd[0]:.4%}  fwd {PROBE[1]} {fwd[1]:.4%}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t8_multicurve.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
SOFR curve 8 pillars, term curve 6, both reprice below 1e-13: True
SOFR 10Y discount factor 0.694786099655
TERM 10Y discount factor 0.681699830969
3M forward from 2027-11-16: SOFR 3.3471%  TERM 3.4345%  basis 8.75 bp
joint TERM 10Y discount factor 0.681699830969
J[TERM 10Y, T-SWAP120] -10.7320  J[TERM 10Y, SOFR-10Y] 0.1133
J[SOFR 10Y, T-SWAP120] is exactly zero: True
dz(SOFR 10Y)/dq(SOFR-10Y): bump 1.0777  joint -J/t 1.0777
turn factor 0.99994234
turn sensitivity: SOFR-1M zero True  SOFR-2M -3.3968  SOFR-3M -0.3139
LOG_LINEAR_DF   10Y DF 0.694786  fwd 2028-05-15 3.3791%  fwd 2033-11-15 3.7649%
LINEAR_ZERO     10Y DF 0.694650  fwd 2028-05-15 3.3826%  fwd 2033-11-15 3.7425%
MONOTONE_CONVEX 10Y DF 0.694601  fwd 2028-05-15 3.3547%  fwd 2033-11-15 3.7611%
```

### Reading the numbers

- **Two curves, each exact.** Eight SOFR quotes give eight pillars and six term quotes give six. Both bootstraps reprice every quote to below 1e-13, the spec's stopping rule.
- **SOFR 10Y discount factor 0.6948.** The 10Y pillar is 2036-11-14, 3,658 days or 10.02 years out. At a flat 3.64% continuously compounded, `exp(-0.0364 × 10.02) = 0.694`, close to the solved value.
- **TERM 10Y discount factor 0.6817.** Lower, because the term swap rate (3.89%) is above the SOFR rate (3.64%): `exp(-0.0389 × 10.02) = 0.677`. A term-curve "discount factor" is only a device for storing forward rates; nothing is discounted with it.
- **The basis, 8.75 bp.** The same 3-month window, 2027-11-16 to 2028-02-16, gives a simple ACT/360 forward of 3.4345% on the term curve and 3.3471% on SOFR: 3.4345 − 3.3471 = 0.0874%, 8.74 bp from the rounded figures, 8.75 bp unrounded. That gap is the tenor basis: lending for three months at a term rate costs more than rolling overnight.
- **The joint solve gives the same curve.** `joint TERM 10Y discount factor` matches the sequential one to all 12 printed digits. The spec requires this: with log-linear curves the joint solve's limit case is the sequential build.
- **J[TERM 10Y, T-SWAP120] = −10.73.** The unknown is `ln D`, so a rise of `dq` in the 10Y term swap rate moves `ln D` at the 10Y term pillar by about −10.73 `dq`. Head check: if `ln D ≈ −z t` with `t ≈ 10`, a rate move of `dq` moves `ln D` by about −10 `dq`; the extra 0.73 is from the swap's coupon structure.
- **J[TERM 10Y, SOFR-10Y] = +0.1133.** The term curve also moves when a *discount* quote moves, because the term swaps are valued on the SOFR curve. The effect is about 1% of the own-quote effect (0.1133 / 10.73 = 0.011): small, but a hedge that ignores it carries basis risk.
- **J[SOFR 10Y, T-SWAP120] is exactly zero.** The SOFR curve does not depend on term quotes. The Jacobian is block lower triangular, and the spec requires these zeros to be exactly 0, not merely small.
- **1.0777 both ways.** `risk.curve.jacobian` bumps each quote by 1bp, rebuilds, and reports `dz/dq` in zero rates. The joint Jacobian is in `ln D`, and `z = −ln D / t`, so `dz/dq = −J / t = 10.80 / 10.02 = 1.078`. Two methods (bump and rebuild; implicit function theorem) agree to four decimals.
- **Turn factor 0.99994234.** Discount factors for dates after 2026-12-31 are multiplied by this. As a rate: `−ln(0.99994234) = 5.766e-5`. If all of it sits on the SOFR fixing of Thursday 31 December 2026, which runs to Monday 4 January because 1 January is a holiday (`n = 4` days), then by the spec's rule `factor = exp(−s n/365)` the year-end spread is `s = 5.766e-5 × 365/4 = 0.0053`, about 53 bp for those four days. The `n = 4` is our reading of the calendar; the operation itself returns only the factor.
- **Turn sensitivity.** The row is `d(model par rate)/d(ln factor)`, one entry per instrument. The 1M swap ends before year end and is exactly unaffected. The 2M swap spans the turn and is the most exposed: −3.3968. Linearised, the solved turn adds `−3.3968 × −5.766e-5 = 1.96e-4`, about 2 bp, to the 2M par rate, which is what the 2M quote demanded over a curve without a turn. The 3M entry (−0.3139) is small but nonzero: on a pillar curve the unknowns are full `ln D`, so the turn moves interpolated dates inside the 3M swap (spec ruling F-26, amended).
- **Three interpolations.** All three reprice the same eight quotes, yet the 10Y pillar differs in the fourth decimal (0.694786, 0.694650, 0.694601). The 10Y OIS pays annual coupons in years 6 to 9, which fall between the 5Y and 10Y pillars, so the interpolation between pillars feeds back into the pillar itself. The instantaneous forward on 2028-05-15 ranges from 3.3547% (monotone convex) to 3.3826% (linear zero), a spread of 2.79 bp; on 2033-11-15 from 3.7425% to 3.7649%, 2.24 bp. Log-linear check: between the 1Y pillar (2027-11-16) and the 2Y pillar (2028-11-15, exactly 365 days later) the forward is constant at `ln(D_1Y/D_2Y)` per year, and `ln(0.961237/0.929298) = 0.03379`, the printed 3.3791%.

## Formal statement, checked against the spec

- **OIS curve** (`specifications/02-curves/ois-curves.md`). Par rate of each SOFR swap from spot (as_of plus 2 business days, `USGS` calendar), annual periods, compounded SOFR leg, ACT/360 accrual, payment lag as specified; one pillar per quote at its last payment date. Stop when every repricing error is at most 1e-13.
- **Projection curve** (`specifications/02-curves/projection-and-fra.md`). `USD-TERM-3M` is a synthetic index. Deposit and FRA model rates are `(P(s)/P(e) − 1)/α` with `P` the projection curve and `α` ACT/360. A term swap's par rate is `F/A` with `A = Σ αᵢ D(eᵢ)` over the annual `THIRTY_360_BOND` fixed leg and `F = Σ (P(sⱼ)/P(eⱼ) − 1) D(eⱼ)` over the quarterly floating leg, `D` the SOFR curve. This is where the curves couple.
- **Forward** (`rates.curve.forward`, `curve-framework.md`): `(D(start)/D(end) − 1)/α`, with `α` from the day count you pass (here `ACT_360`).
- **Joint solve** (`specifications/02-curves/joint-solve-and-funding.md`, `rates.curve.joint_solve`). Unknowns `x`: `ln D` at each pillar, curves in input order, then turns as `ln factor`. Residuals `R = model − quote`, solved by Newton until every `|R| ≤ 1e-13`. Jacobian by the implicit function theorem: `J = −(∂R/∂x)⁻¹ (∂R/∂q)`, with `∂R/∂q = −1` for rate quotes. Because a curve's residuals depend only on its own unknowns and those of earlier curves, `∂R/∂x` is block lower triangular and the entries for an earlier curve's unknowns against a later curve's quotes are exactly 0 (ruling F-25). Rows are labelled `<name>:pillar:<date>`.
- **Zero-rate Jacobian** (`risk.curve.jacobian`, `specifications/06-risk/par-and-key-rate.md`, ruling R2-A8): `dzᵢ/dqⱼ` by central difference with a `bump_bp` bump, `z = −ln D / t`, `t` in ACT/365F years from `as_of`, lower triangular by construction.
- **Turn** (`curve-framework.md`, jumps; `joint-solve-and-funding.md`, turns). `D(d) = S(d) × J(d)`, `J(d)` the product of jump factors dated strictly before `d`; interpolation acts on `S = D/J`. In `joint_solve`, a curve's `turns: [{date}]` adds one unknown each, and exactly one instrument per turn must carry `"turn": true`; that instrument gives no pillar and pins the factor. `turn_sensitivity` is `d model_j / d ln factor` with all other unknowns held. A fixed, typed-in turn is the `jumps` input of the curve object and of `rates.ois.bootstrap`.
- **Interpolation** (`curve-framework.md`). `LOG_LINEAR_DF`: `ln D` linear in time between pillars, so forwards are flat. `LINEAR_ZERO`: zero rate linear in time. `MONOTONE_CONVEX`: Hagan and West's forward-rate method, implemented with `forcePositive = false` (ruling F-19). `rates.curve.inspect` returns discount factors, zero rates and instantaneous forwards `−d ln D/dt` at given dates.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t8_multicurve.py` sends the same operations, `rates.ois.bootstrap`, `rates.projection.bootstrap`, `rates.curve.forward`, `rates.curve.joint_solve` (twice, the second with a turn), `risk.curve.jacobian` and `rates.curve.inspect`, to whichever CLI you name and prints the same lines. Given a command line, the same script sends each case to that build's `batch` command (`specifications/cli-contract.md`) instead of the Python package.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t8_multicurve.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t8_multicurve.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t8_multicurve.py cpp26/build/quantforge
```

Each prints the lines shown in step 1, digit for digit at the printed precision. The Jacobian entries are printed to four decimals because the spec's `jacobian` tolerance class allows `1e-9 + 1e-6 |ref|` between builds (a build may form `∂R/∂x` by central differences); on this run all four languages agreed at that precision. The full check is `python conformance/runner/runner.py --impl rust --suite joint_f`.

## For practitioners

- **QuantLib.** The OIS and projection curves here correspond to `PiecewiseYieldCurve` with `OISRateHelper`, `DepositRateHelper`, `FraRateHelper` and `SwapRateHelper` with an exogenous discounting handle; the spec's outside check rebuilds the log-linear and stage F curves that way with QuantLib 1.44. In that check the curves are built one after the other, and the joint Jacobian is compared with bump-and-rebuild through QuantLib rather than with a QuantLib Jacobian.
- **Turns.** QuantLib and many desks type the turn in as a jump (`jumps`, a spread over `n` days). Here a solved turn is also available: the factor is calibrated from a quote that spans year end, and it then has its own risk. Turns on step curves (`OIS_STEPS`) are local by construction; on pillar curves a turn moves interpolated dates on both sides of nearby pillars, which is why the 3M entry above is not zero.
- **Units of the Jacobian.** The joint Jacobian is in `ln D` per unit of quote, `risk.curve.jacobian` in zero rate per unit of quote. Convert with `−J/t` as above before comparing with a risk system that reports zero-rate deltas.
- **Monotone convex.** QuantLib's default `forcePositive = true` changes the method so that it no longer returns its own pillars on these inputs (ruling F-19). Pillars from QuantLib with the default flag will not match these.
- **Projection-curve "discount factors"** are a storage convention. Some systems store forwards or pseudo-zero rates instead; compare forwards, not stored values.

## Common mistakes

- Building the projection curve on a different discount curve than the one used to price. The term pillars depend on the discount curve through the swaps; the Jacobian entry 0.1133 says by how much.
- Comparing Jacobians across systems without matching the unknown (`ln D`, zero rate, par rate) and the scaling (per unit or per bp).
- Expecting a turn to touch only the instrument that spans it on a pillar curve. That holds on step curves, not on pillar curves.
- Choosing an interpolation by how smooth the zero curve looks. The forwards between pillars differ by a few bp across methods here, and forwards are what a FRA or a forward-starting swap is priced from.
- Marking the turn instrument as a pillar. A curve with `k` turns must have exactly `k` instruments with `"turn": true`, else `E_INPUT`.

## What you just did

You built a SOFR discount curve and a 3M term curve on it, measured the tenor basis between them, solved both as one system and read the cross-curve Jacobian, including its exact zeros, checked the joint Jacobian against a bump-and-rebuild one, solved a year-end turn from a quote, and saw three interpolation methods agree on the quotes and disagree between them.

## Try next

- Set the 2M quote in step 5 to 0.0426. The turn factor crosses 1 and comes out slightly above it: that quote sits a little below the 2M rate of a curve without a turn.
- Replace `"LOG_LINEAR_DF"` with `"MONOTONE_CONVEX"` in the joint solve (`CurveSpec(..., interpolation="MONOTONE_CONVEX")`) and look above the diagonal of the SOFR block: a non-local method puts small nonzero entries there, where log-linear has exact zeros.
- Run the four-curve golden case `joint_f-0001` (SOFR with a turn, term, ESTR and EUR cross-currency) from the [Cookbook](../../COOKBOOK.md) table, and `joint_f-0002` for meeting-date steps fitted to SOFR futures.
- Read [Solving several curves at once](../../LEARN.md#solving-several-curves-at-once), [Five more ways to draw a curve](../../LEARN.md#five-more-ways-to-draw-a-curve) and [The Jacobian, and why the chain rule holds only for pillars](../../LEARN.md#the-jacobian-and-why-the-chain-rule-holds-only-for-pillars).

## References and further reading

- Ametrano, F. M. and Bianchetti, M., "Everything you always wanted to know about multiple interest rate curve bootstrapping but were afraid to ask", SSRN working paper, 2013, [doi:10.2139/ssrn.2219548](https://doi.org/10.2139/ssrn.2219548). Multi-curve bootstrapping and tenor basis. The spec lists it as not opened; SSRN and doi.org return 403 to scripts, so the DOI and title were confirmed through Crossref.
- Henrard, M., *Interest Rate Modelling in the Multi-curve Framework*, Palgrave Macmillan, 2014, [doi:10.1057/9781137374660](https://doi.org/10.1057/9781137374660) (paywalled). Curve calibration with the Jacobian from the implicit function theorem; turn-of-year treatment. Not opened by the spec.
- Hagan, P. S. and West, G., "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2), 2006, 89-129, [doi:10.1080/13504860500396032](https://doi.org/10.1080/13504860500396032) (paywalled; the publisher returns 403 to scripts, the DOI and title were confirmed through Crossref). Monotone convex and the other methods compared in step 6.
- Andersen, L. B. G. and Piterbarg, V. V., *Interest Rate Modeling*, 2010, vol. 1, curve construction chapter: turn-of-year effects (not opened by the spec; no link).
- Federal Reserve Bank of New York, [SOFR](https://www.newyorkfed.org/markets/reference-rates/sofr), the rate behind the OIS curve.
- [QuantLib](https://www.quantlib.org/) 1.44, the outside check for the OIS and projection curves.
- Specs: `specifications/02-curves/ois-curves.md`, `projection-and-fra.md`, `curve-framework.md`, `joint-solve-and-funding.md`, `meeting-steps.md`. Golden cases: `datasets/golden/stage_f/joint_f.json`.
- [LEARN: curves and fixed income](../../LEARN.md#curves-and-fixed-income), [Cookbook](../../COOKBOOK.md), [Glossary](../../GLOSSARY.md).

Links checked 2026-11-11.
