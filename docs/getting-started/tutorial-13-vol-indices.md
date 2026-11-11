# Tutorial 13: time series and vol indices

The plain idea: there are two ways to say how volatile a market is. One looks back. It reads a series of daily returns and fits a model of how variance moves from day to day; GARCH(1,1) is the standard one, and once fitted it forecasts variance over any horizon. The other looks forward. It reads today's option prices, which already hold the market's price of future variance, and turns a strip of them into one number; the VIX method does that for 30 days. Between two option expiries, the variance the market expects is the difference of the two total variances, and that gives the forward vol.

This tutorial fits a GARCH(1,1) model, reads its standard errors, forecasts a month of volatility, builds a VIX-style index from two option strips and takes the forward vols of a term structure. All data is synthetic: the return series were simulated from known parameters and the option strips are Black prices on a skewed smile rounded to 0.05 ticks. Budget 15 minutes. Every number shown is a real output; CI runs every code block marked for it and fails if a printed line differs.

Terms used here are defined in the [glossary, stage E section](../../GLOSSARY.md#stage-e-full-volatility-exotics-rates-vol-correlation-and-credit) (GARCH(1,1), long-run variance, total variance, forward vol, calendar arbitrage, VIX-style index, K0).

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell (the code reads golden files by relative path).
- [uv](https://docs.astral.sh/uv/). It fetches Python and NumPy for you: `uv sync --locked --project python`.

## Step 1: Python

The inputs come from three golden files: case `garch_e-0028` (250 returns), case `garch_f-0009` (2,000 returns simulated with `omega = 2e-6`, `alpha = 0.08`, `beta = 0.90`, seed 20261109) and case `vix_e-0007` (two strips around 30 days). The term structure is `examples/vol_forward_term_e.json`.

The script `examples/tutorials/t13_vol_indices.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t13_vol_indices.py -->
```python
"""Tutorial 13: fit GARCH(1,1), forecast vol, build a VIX-style index.

  uv run --project python python examples/tutorials/t13_vol_indices.py         # Python
  python examples/tutorials/t13_vol_indices.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-13-vol-indices.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines. Inputs are
synthetic and come from golden cases garch_e-0028, garch_f-0009 and vix_e-0007, and from
examples/vol_forward_term_e.json.
"""
import json
import math
import sys

from qf import runner


def golden(path, case_id):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    cases = data["cases"] if isinstance(data, dict) else data
    return next(c["inputs"] for c in cases if c["case_id"] == case_id)


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
    r250 = golden("datasets/golden/stage_e_b/garch_e.json", "garch_e-0028")["returns"]
    r2000 = golden("datasets/golden/stage_f/garch_f.json", "garch_f-0009")["returns"]
    vix = golden("datasets/golden/stage_e_b/vix_e.json", "vix_e-0007")
    with open("examples/vol_forward_term_e.json", encoding="utf-8") as f:
        term = json.load(f)["inputs"]

    fit, est = batch(cli, [
        case("t13-fit", "vol.garch.fit", {"returns": r250, "initial_variance": "SAMPLE"}),
        case("t13-est", "vol.garch.estimate", {"returns": r2000, "initial_variance": "SAMPLE",
                                               "distribution": "NORMAL", "demean": False})])
    weights = {k: est[k] for k in ("omega", "alpha", "beta")}
    [ll] = batch(cli, [case("t13-ll", "vol.garch.loglik",
                            {"returns": r2000, "initial_variance": "SAMPLE", **weights})])
    nxt = ll["next_variance"]
    fc, near, index, fwd = batch(cli, [
        case("t13-fc", "vol.garch.forecast", {**weights, "next_variance": nxt, "horizon": 21,
                                              "periods_per_year": 252.0}),
        case("t13-near", "vol.vix.term_variance", vix["near"]),
        case("t13-index", "vol.vix.index", vix),
        case("t13-fwd", "vol.forward.vol", term)])
    se = est["std_errors"]

    print(f"fit loglik, 250 returns  {fit['loglik']:.4f}")
    print(f"omega {est['omega']:.4e}  SE {se['omega']:.3e}")
    print(f"alpha {est['alpha']:.6f}  SE {se['alpha']:.6f}")
    print(f"beta  {est['beta']:.6f}  SE {se['beta']:.6f}")
    print(f"persistence {est['persistence']:.6f}")
    print(f"next-day vol, annualised {math.sqrt(nxt * 252):.4f}")
    print(f"21-day forecast vol      {fc['annualized_vol']:.4f}")
    print(f"long-run vol             {math.sqrt(fc['long_run_variance'] * 252):.4f}")
    print(f"near forward {near['forward']:.4f}  K0 {near['k0']:.1f}")
    print(f"near variance {index['near_variance']:.6f}  next variance {index['next_variance']:.6f}")
    print(f"VIX-style index {index['index']:.4f}")
    print("forward vols " + " ".join(f"{v:.4f}" for v in fwd["forward_vols"]))


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t13_vol_indices.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
fit loglik, 250 returns  856.0686
omega 3.5576e-06  SE 1.246e-06
alpha 0.094508  SE 0.018552
beta  0.873172  SE 0.026236
persistence 0.967680
next-day vol, annualised 0.1645
21-day forecast vol      0.1650
long-run vol             0.1666
near forward 4513.3406  K0 4500.0
near variance 0.029447  next variance 0.031235
VIX-style index 17.4886
forward vols 0.2000 0.2164 0.2199 0.2249
```

### Reading the numbers

- **Fit log-likelihood, 856.0686.** The golden for `garch_e-0028` is 856.0685762080798, and the spec judges the fit on this number only, to 1e-6. The fitted parameters are not compared: two optimisers can stop at slightly different points on a flat ridge and still agree on the maximum. A sanity check on the size: 250 daily returns with variance near 6.4e-5 (the sample variance printed in the golden's first `variances` entry for case `garch_e-0006`, same series) give per-day terms of about `-0.5 (ln(2 pi) + ln 6.4e-5 + 1) = -0.5 (1.838 - 9.657 + 1) = 3.41`, and 250 x 3.41 = 852, close to 856.
- **The estimate.** The series was simulated with `alpha = 0.08`, `beta = 0.90`, `omega = 2e-6`. Each true value is inside two standard errors: 0.094508 - 0.08 = 0.0145 < 2 x 0.018552; 0.90 - 0.873172 = 0.0268 < 2 x 0.026236; 3.5576e-6 - 2e-6 = 1.56e-6 < 2 x 1.246e-6. With 2,000 returns, `alpha` and `beta` are still only known to about 0.02 to 0.03 each.
- **Persistence 0.967680.** It is `alpha + beta` = 0.094508 + 0.873172. A shock to variance decays by that factor each day, so its half-life is `ln 0.5 / ln 0.96768` = 0.6931 / 0.03285 = 21 trading days.
- **Long-run vol 0.1666.** `V_L = omega / (1 - alpha - beta)` = 3.5576e-6 / 0.032320 = 1.1007e-4 per day; times 252 is 0.02774, whose square root is 0.1666.
- **Next-day vol 0.1645 and 21-day vol 0.1650.** Tomorrow's variance is below the long-run level (0.1645 < 0.1666), so the forecast rises towards it, and the 21-day average lands in between. Annualising uses 252 periods a year, an input, not a convention built into the model.
- **Near forward 4513.3406, K0 4500.0.** The forward comes from put-call parity at the strike where call and put mids are closest; K0 is the listed strike at or below it, here 4500, not 4525.
- **Index 17.4886.** Interpolate total variance to 30 days and annualise. The near term has 34,560 minutes (24 days), the next 50,400 (35 days); the weights are (50,400 - 43,200)/15,840 = 0.4545 and 0.5455. Then `T1 v1` = 34,560/525,600 x 0.029447 = 0.0019363 and `T2 v2` = 50,400/525,600 x 0.031235 = 0.0029951; the bracket is 0.4545 x 0.0019363 + 0.5455 x 0.0029951 = 0.0025139; times 525,600/43,200 = 12.1667 gives 0.030586, and 100 x sqrt(0.030586) = 17.489.
- **Forward vols.** The first is the first vol. The second: `(0.21^2 x 0.49863 - 0.2^2 x 0.2) / (0.49863 - 0.2)` = (0.021990 - 0.008) / 0.29863 = 0.046846, square root 0.2164. Each forward vol is above the spot vol at its end, which is what a rising term structure implies.

### Formal statement, checked against the specs

GARCH(1,1) ([`garch.md`](../../specifications/05-volatility/garch.md); Bollerslev 1986). Returns are used as given: no mean is removed unless `demean` is true. `sigma2_1` is the initial variance (`"SAMPLE"` is `(1/n) sum r_t^2`, divisor `n`), then `sigma2_{t+1} = omega + alpha r_t^2 + beta sigma2_t`, and the Gaussian log-likelihood is `-1/2 sum_{t=1..n} [ln(2 pi) + ln sigma2_t + r_t^2/sigma2_t]`, with the first term kept. `vol.garch.fit` needs at least 30 returns and returns only `loglik` at the optimum; `vol.garch.estimate` returns the parameters, `std_errors` from the observed information `(-H)^{-1}` (not the sandwich form), and `persistence`. The forecast is `E[sigma2_{n+h}] = V_L + p^(h-1) (sigma2_{n+1} - V_L)` with `p = alpha + beta`, `V_L = omega/(1 - p)`; `annualized_vol = sqrt(total_variance x periods_per_year / H)`. Units: everything per period of the return series (here daily) until you annualise.

VIX-style index ([`vix-index.md`](../../specifications/05-volatility/vix-index.md), targets in [`stage-e-targets-b.md`](../../specifications/05-volatility/stage-e-targets-b.md); Cboe methodology v5.0, section 3). `T = N / 525,600` with `N` in minutes; `variance = (2/T) e^{RT} sum (dK_i / K_i^2) Q(K_i) - (1/T)(F/K0 - 1)^2`; `index = 100 sqrt([T1 v1 (N2 - N30)/(N2 - N1) + T2 v2 (N30 - N1)/(N2 - N1)] x N365 / N30)` with `N30 = 43,200`. The rate `R` is continuously compounded and given by the caller; so are the two strips.

Forward vol ([`local-and-forward-vol.md`](../../specifications/05-volatility/local-and-forward-vol.md); Hull, chapter on volatility smiles). `forward_vols[i] = sqrt((v_i^2 T_i - v_{i-1}^2 T_{i-1}) / (T_i - T_{i-1}))`, `T` in years. A negative radicand is calendar arbitrage and returns `E_ARBITRAGE`.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t13_vol_indices.py` sends the same seven operations, `vol.garch.fit`, `vol.garch.estimate`, `vol.garch.loglik`, `vol.garch.forecast`, `vol.vix.term_variance`, `vol.vix.index` and `vol.forward.vol`, to whichever CLI you name (`specifications/cli-contract.md`) and prints the same lines. Given a command line, the same script sends each case to that build's `batch` command (`specifications/cli-contract.md`) instead of the Python package.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t13_vol_indices.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t13_vol_indices.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t13_vol_indices.py cpp26/build/quantforge
```

Each prints the twelve lines of step 1. The precision printed is chosen to sit inside the cross-language tolerances: the fit is judged to 1e-6 on the log-likelihood, estimated parameters to 1e-6 relative and standard errors to 1e-5 relative (`garch.md`, stage F acceptance), so the page prints six significant digits of parameters and four of standard errors. Every language printed the same digits in this run.

## For practitioners

- **No mean, by default.** The spec's GARCH removes no mean (`demean` is false in `vol.garch.estimate`, and `vol.garch.fit` has no mean at all). The `arch` Python package fits a constant mean by default, so its parameters on the same series differ. For daily index returns the gap is small; for a drifting series it is not.
- **Initial variance.** `"SAMPLE"` is the mean square, divisor `n`. Some libraries start at the sample variance (divisor `n - 1`, demeaned) or back-cast with an exponential weight. The choice moves the log-likelihood in early terms; the goldens catch `r_1^2` as a wrong start.
- **Standard errors.** Observed information, not the robust sandwich of Bollerslev and Wooldridge (1992). On fat-tailed data the sandwich errors are larger; use `distribution: STUDENT_T` or compute the sandwich yourself if that matters.
- **QuantLib.** Its Python wheel has no `Garch11`, so no GARCH case here is outside-checked; the goldens rest on 50-digit mpmath and a separate float replay (`garch.md`, acceptance).
- **The VIX.** This is the published method applied to a strip you give. Cboe also derives the rate from Treasury yields, chooses the expiries and filters series using quote history; those steps are yours. The result is a VIX-style index, not the VIX.
- **Forward vol.** The formula assumes the vols are at one fixed moneyness (for example ATM forward). Forward vol from ATM vols is not the vol of a forward-start option, which also depends on the smile dynamics.

## Common mistakes

- Annualising with the wrong count. `periods_per_year` is an input; 252 for daily trading returns, 52 for weekly. Using 365 for trading-day returns overstates vol by `sqrt(365/252)` = 1.20.
- Reading the fitted `omega` without its units: it is a daily variance, 3.56e-6 here, not an annual one.
- Forecasting with `alpha + beta >= 1`. There is no long-run variance; `vol.garch.forecast` returns `E_DOMAIN` (ruling E-B2).
- Taking K0 as the strike nearest the forward. It is the strike at or below it; 4525 instead of 4500 here would be a wrong-convention case the goldens catch.
- Measuring time to expiry in days of 360. The VIX method counts minutes over 525,600 (a 365-day year).
- Interpolating vols linearly across expiries. Variance times time is additive; vols are not.

## What you just did

You fitted a GARCH(1,1) by maximum likelihood, checked that the true parameters sit inside two standard errors, turned the model into a one-month vol forecast that mean-reverts towards a long-run level, built a 30-day VIX-style index from two option strips, and read forward vols off a term structure, each in four languages that agree.

## Try next

- Change `"NORMAL"` to `"STUDENT_T"` in step 2 and use case `garch_f-0010`'s returns: the estimate gains `degrees_of_freedom` (about 5.8 in the golden).
- Forecast with `horizon` 252 instead of 21: the annualised vol moves closer to the long-run 0.1666.
- Run the five-strike hand case `vix_e-0001` through `vol.vix.term_variance` (the [Cookbook](../../COOKBOOK.md) has it) and check the variance 0.08188 by hand.
- Make the term structure invert (vols 0.25, 0.20, ...) until `vol.forward.vol` returns `E_ARBITRAGE`.
- Read [LEARN: GARCH(1,1)](../../LEARN.md#garch11-volatility-that-remembers), [LEARN: the VIX method](../../LEARN.md#the-vix-method) and [LEARN: local vol and forward vol](../../LEARN.md#local-vol-and-forward-vol).

## References and further reading

- T. Bollerslev, "Generalized autoregressive conditional heteroskedasticity", *Journal of Econometrics* 31(3), 1986, 307-327, [doi:10.1016/0304-4076(86)90063-1](https://doi.org/10.1016/0304-4076(86)90063-1) (paywalled). The recursion and Gaussian likelihood used in step 1. The spec marks it "not opened"; the formulas are stated in full in `garch.md` and checked by the goldens.
- R. F. Engle, "Autoregressive conditional heteroscedasticity with estimates of the variance of United Kingdom inflation", *Econometrica* 50(4), 1982, 987-1007, [doi:10.2307/1912773](https://doi.org/10.2307/1912773) (paywalled; not opened per the spec).
- T. Bollerslev, J. M. Wooldridge, "Quasi-maximum likelihood estimation and inference in dynamic models with time-varying covariances", *Econometric Reviews* 11(2), 1992, 143-172: the sandwich standard errors, named in the spec as the form not used (not opened).
- J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018: GARCH forecasts and the long-run variance, and additive variance across expiries (not opened per the specs).
- Cboe Global Indices, [*Cboe Volatility Index Mathematics Methodology*](https://cdn.cboe.com/resources/indices/Cboe_Volatility_Index_Mathematics_Methodology.pdf), v5.0, revised 26 February 2026, section 3. Read by the spec authors on 2026-11-08 and 2026-11-09.
- K. Demeterfi, E. Derman, M. Kamal, J. Zou, "A guide to volatility and variance swaps", *Journal of Derivatives* 6(4), 1999, 9-32: the strip behind the VIX method (not opened per the spec; no link given).
- QuantForge specs: [`garch.md`](../../specifications/05-volatility/garch.md), [`vix-index.md`](../../specifications/05-volatility/vix-index.md), [`stage-e-targets-b.md`](../../specifications/05-volatility/stage-e-targets-b.md), [`local-and-forward-vol.md`](../../specifications/05-volatility/local-and-forward-vol.md); the [Cookbook](../../COOKBOOK.md) recipes "GARCH likelihood by hand" and "A VIX term from five strikes"; the [glossary](../../GLOSSARY.md#stage-e-full-volatility-exotics-rates-vol-correlation-and-credit).

Links checked 2026-11-11: the two DOIs and the Cboe PDF returned HTTP 200 (DOI titles also confirmed through the Crossref API).
