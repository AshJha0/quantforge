# Tutorial 12: exotic options, American exercise, and three models for one call

The plain idea: a vanilla option pays on the spot at expiry and nothing else. Change one thing and the price changes. Let the holder exercise early (an American option) and the price can only go up. Kill the option if spot touches a lower level (a knock-out barrier) and it goes down, by an amount that depends on how often anyone looks at spot. Change the model instead of the payoff, from Black-Scholes to stochastic variance (Heston) or to a vol that depends on spot and time (local vol), and the same call gets a different price.

This tutorial prices one synthetic option set (spot 100, strike 100, one year, rate 5%, dividend yield 2%, vol 25%) all of those ways, first in Python, then the same in Rust, Java and C++. Budget 15 minutes. Every number shown is a real output, and CI runs every code block on this page and fails if any printed line differs. All inputs are synthetic and match golden cases in `datasets/golden/stage_e/` and `datasets/golden/stage_g/barrier_g.json`.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [tutorial 1](tutorial-1-swap.md).
- The Black-Scholes model and implied vol (see the [Glossary, stage C](../../GLOSSARY.md#stage-c-equity-vol-slice)).

Terms used below, all in the [Glossary, stage E](../../GLOSSARY.md#stage-e-full-volatility-exotics-rates-vol-correlation-and-credit) unless noted:

- **American option**: may be exercised at any time up to expiry; a **European option** only at expiry. The price difference is the **early-exercise premium**.
- **BAW**: Barone-Adesi-Whaley, a closed-form (quadratic) approximation to the American price.
- **CRR tree**: the Cox-Ross-Rubinstein binomial tree; at each step spot moves up by `u = e^{v sqrt(dt)}` or down by `1/u`.
- **Barrier option**: dies (knock-out) or comes alive (knock-in) when spot touches a level. A **down-and-out call** dies if spot falls to the barrier.
- **BGK correction** ([Glossary, stage G](../../GLOSSARY.md#stage-g-terms)): Broadie, Glasserman and Kou's shift of the barrier that turns the continuous-monitoring formula into an approximation for monitoring at discrete dates.
- **Heston**: a model in which the variance is itself random and mean-reverting.
- **Local vol**: the vol, as a function of time and spot, that reprices every vanilla on a given implied-vol surface (Dupire 1994). **SVI** is the smile shape the surface here is built from.

## Step 1: Python

```bash
uv sync --locked --project python
```

The script `examples/tutorials/t12_exotics.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t12_exotics.py -->
```python
"""Tutorial 12: American puts, a barrier call, Heston and local-vol calls.

  uv run --project python python examples/tutorials/t12_exotics.py         # Python
  python examples/tutorials/t12_exotics.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-12-exotics.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import math
import sys

from qf import runner

S, K, T, R, Q, VOL = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
COMMON = {"spot": S, "strike": K, "expiry_years": T, "rate": R, "dividend_yield": Q, "vol": VOL}
BS = {"model": "BLACK_SCHOLES", "strike": K, "expiry_years": T, "spot": S, "rate": R, "yield": Q}
BARRIER = {**COMMON, "option_type": "CALL", "barrier": 90.0, "rebate": 0.0, "barrier_type": "DOWN_OUT"}
HESTON = {"v0": 0.0625, "kappa": 1.5, "theta": 0.0625, "xi": 0.5, "rho": -0.7}
SURFACE = [{"expiry_years": 1.0, "svi": {"a": 0.035, "b": 0.11, "rho": -0.35, "m": 0.03, "sigma": 0.25}}]


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
    k = math.log(K / (S * math.exp((R - Q) * T)))  # forward log-moneyness of the strike
    put = {**COMMON, "option_type": "PUT"}
    euro, baw, crr, fd, call, cont, daily, weekly, hes, lv = batch(cli, [
        case("t12-euro", "vol.option.price", {**BS, "option_type": "PUT", "vol": VOL}),
        case("t12-baw", "exotic.american.baw", put),
        case("t12-crr", "exotic.american.crr", {**put, "steps": 200}),
        case("t12-fd", "exotic.american.fd",
             {**put, "exercise": "AMERICAN", "grid": {"nx": 201, "nt": 200, "width": 5.0}}),
        case("t12-call", "vol.option.price", {**BS, "option_type": "CALL", "vol": VOL}),
        case("t12-cont", "exotic.barrier.price", BARRIER),
        case("t12-daily", "exotic.barrier.price",
             {**BARRIER, "monitoring": "DISCRETE", "monitoring_per_year": 252}),
        case("t12-weekly", "exotic.barrier.price",
             {**BARRIER, "monitoring": "DISCRETE", "monitoring_per_year": 52}),
        case("t12-heston", "vol.heston.price",
             {"spot": S, "strikes": [K], "expiry_years": T, "rate": R, "dividend_yield": Q,
              "heston": HESTON, "option_type": "CALL"}),
        case("t12-dupire", "vol.local.dupire",
             {"slices": SURFACE, "points": [{"expiry_years": T, "log_moneyness": k}]}),
    ])
    iv = lv["implied_vol"][0]
    [lv_call] = batch(cli, [case("t12-lvcall", "vol.option.price", {**BS, "option_type": "CALL", "vol": iv})])
    print(f"European put (BS)   {euro['price']:.6f}")
    print(f"American put BAW    {baw['price']:.6f}")
    print(f"American put CRR200 {crr['american']:.6f}")
    print(f"American put FD     {fd['price']:.6f}")
    print(f"Vanilla call (BS)   {call['price']:.6f}")
    print(f"Down-out continuous {cont['price']:.6f}")
    print(f"Down-out daily      {daily['price']:.6f}")
    print(f"Down-out weekly     {weekly['price']:.6f}")
    print(f"Heston call         {hes['prices'][0]:.6f}")
    print(f"Surface vol {iv:.6f} local vol {lv['local_vol'][0]:.6f}")
    print(f"Local-vol call      {lv_call['price']:.6f}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t12_exotics.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
European put (BS)   8.226837
American put BAW    8.580054
American put CRR200 8.558810
American put FD     8.549269
Vanilla call (BS)   11.123762
Down-out continuous 8.138811
Down-out daily      8.519040
Down-out weekly     8.923283
Heston call         10.521639
Surface vol 0.256107 local vol 0.238079
Local-vol call      11.355515
```

### Reading the numbers

- **European put, 8.2268.** Check it against the call by put-call parity: `C - P = S e^{-qT} - K e^{-rT} = 98.0199 - 95.1229 = 2.8969`, and 11.123762 - 8.226837 = 2.896925.
- **American put, three methods.** All three sit above the European put, as they must: the American holder has every right the European holder has, plus one. Early-exercise premium: BAW 8.580054 - 8.226837 = 0.3532, CRR 0.3320, FD 0.3224. The three disagree by 8.580054 - 8.549269 = 0.031, about 0.4% of the price. That spread is the methods, not a bug: BAW is an approximation, and the tree and the grid carry discretisation error at 200 steps. The CRR value equals golden `american_e-0002` and the FD value equals `american_e-0035`. A put can be worth exercising early because the strike received early earns 5% while the stock given up yields only 2%.
- **Barrier, continuous, 8.1388.** Below the vanilla call (11.1238) by 2.98: that is what the paths that touch 90 and then finish above 100 were worth.
- **Barrier, daily 8.5190 and weekly 8.9233.** Looking at spot less often lets some paths dip below 90 between looks without being caught, so the discretely watched option is worth more than the continuous one (by 0.380 daily, 0.784 weekly) and still less than the vanilla. BGK moves the barrier away from spot, `90 exp(-0.5826 × 0.25 × sqrt(1/252)) = 89.178` for daily and `90 exp(-0.5826 × 0.25 × sqrt(1/52)) = 88.200` for weekly, then prices continuously. Both prices match `barrier_g-0001` and `barrier_g-0002`.
- **Heston call, 10.5216.** The starting and long-run variance are both 0.0625 (vol 25%), yet the call is 11.123762 - 10.521639 = 0.602 cheaper than Black-Scholes at 25%. With `rho = -0.7` the smile slopes down: low strikes get higher implied vol, and this strike, a little below the forward of `100 e^{0.03} = 103.05`, gets lower. In vol terms, 0.602 divided by the Black-Scholes vega (about `S e^{-qT} phi(d1) sqrt(T) = 98.02 × 0.387 = 37.9` per unit of vol, with `d1 = (0.03 + 0.03125)/0.25 = 0.245`) is about 1.6 vol points, so Heston's implied vol here is near 23.4%.
- **Local vol.** A local-vol model calibrated to a surface reprices every vanilla on it by construction, so its price for this call is the Black-Scholes price at the surface's implied vol, 25.61%: 11.3555. The difference from the 25% price, 0.2318, matches vega × vol difference = 37.9 × 0.006107 = 0.231. The local vol at that point, 23.81%, is below the implied vol because the surface has negative skew (`rho = -0.35` in SVI): roughly, implied vol averages local vol along the paths, and paths that wander to lower spot see higher local vol. Local vol matters for path-dependent payoffs such as the barrier above, where it and Heston give different prices even when both fit the same vanillas. This repository has no local-vol barrier pricer, so the tutorial stops at the vanilla.

## Formal statement, checked against the specs

- **Conventions.** Rates, dividend yields and vols are continuously compounded and annual; `expiry_years` is already a year fraction, so no day count, calendar or settlement lag is applied. Prices are per unit of underlying.
- **American** (`specifications/04-pricing/exotics.md`). BAW [BAW87] adds a quadratic early-exercise term to the European price, with a critical price found by iteration; it needs `r > 0`. CRR [CRR79] uses `u = e^{v sqrt(dt)}`, `d = 1/u`, `p = (e^{(r-q)dt} - d)/(u - d)`, and backward induction with exercise allowed at every node including today; it also returns the same tree's European value and the difference. The FD reference scheme (ruling E-A23) is backward Euler in `x = ln S` on `nx` points spanning `ln S ± width × v sqrt(T)`, with `nt` time steps and `V = max(V, payoff)` after each step. It reports `price`, `delta` and `gamma` at the centre node.
- **Barrier** (`exotics.md`). Continuous monitoring uses the Reiner-Rubinstein closed form [RR91] as tabulated by Haug (2007, ch. 4). With `DISCRETE` and `monitoring_per_year = m`, `dt = 1/m` and the barrier is replaced by `H exp(∓0.5826 v sqrt(dt))` (minus for down barriers, plus for up), with `0.5826 ≈ -zeta(1/2)/sqrt(2 pi)` [BGK97] (ruling G-7). The domain check uses the unshifted barrier (ruling G-8). The spec's acceptance test compares the daily down-and-out call against a 40,000-path Monte Carlo on the 252 dates: 8.51904 against 8.45109 ± 0.08496.
- **Heston** (`specifications/05-volatility/heston-family.md`). `dv = kappa (theta - v) dt + xi sqrt(v) dW_2`, the log spot driven by `dW_1`, with `d<W_1, W_2> = rho dt` [Hes93]. Prices come from Lewis's single integral of the characteristic function [Lew01], in the "little trap" form [Alb07]. The golden suite is checked against QuantLib 1.44's analytic engine.
- **Local vol** (`specifications/05-volatility/local-and-forward-vol.md`). Local variance is `w_T / g(k)`, Gatheral's total-variance form [Gat06, eq. 1.10] of Dupire's formula [Dup94], with `k = ln(K / (S e^{(r-q)T}))` the forward log-moneyness, `w` the SVI total variance and `g` the butterfly function. With one slice, `w_T = w/T`. The operation returns `total_variance`, `implied_vol = sqrt(w/T)` and `local_vol`; it does not price.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t12_exotics.py` sends the same cases (`vol.option.price`, `exotic.american.baw`, `exotic.american.crr`, `exotic.american.fd`, `exotic.barrier.price`, `vol.heston.price`, `vol.local.dupire`) to whichever CLI you name and prints the same lines. Given a command line, the same script sends each case to that build's `batch` command (`specifications/cli-contract.md`) instead of the Python package.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t12_exotics.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t12_exotics.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t12_exotics.py cpp26/build/quantforge
```

Each prints the eleven lines of step 1, digit for digit at six decimals. The golden suites behind these operations are `stage_e/american_e`, `stage_e/exotic_e`, `stage_g/barrier_g`, `stage_e/heston_e` and `stage_e/lv_e`.

## For practitioners

- **Where BGK is used (ruling R6-2.1).** The 2026-11-12 review found BGK prices badly wrong away from daily monitoring: on `barrier_g-0006` (a monthly down-and-out put) BGK gives 0.2962 against an exact-date Monte Carlo of 0.2478 ± 0.0012 (+19.6%). Since contract 1.12.0, `exotic.barrier.price` with `DISCRETE` monitoring returns the BGK price only for a regular knock-out away from the barrier: a down-and-out call with the barrier at or below the strike, or an up-and-out put with the barrier at or above it, no rebate, and `|ln(spot/barrier)| >= 1.25 vol sqrt(T/n)`. Everything else (knock-ins, reverse barriers, rebates, barriers too close to spot) is `E_DOMAIN`. The call above is inside: `ln(100/90) = 0.105` against `1.25 × 0.25 × sqrt(1/52) = 0.043` weekly and 0.020 daily. Inside the envelope the oracle checked every value golden against a 4-million-path exact-date Monte Carlo, all within `max(3 SE, 0.5%)` (`oracle/R6_BARRIER_ACCEPTANCE.json`). - **BGK is an approximation with a known weak spot.** It works well when the barrier is not too close to spot relative to `v sqrt(dt)`. For daily-fixed barriers near spot, or with few fixings left, desks check against a Monte Carlo on the actual fixing dates or a PDE with monitoring steps. The constant is fixed at 0.5826 by ruling G-7, and the rebate is not corrected (`exotics.md`).
- **Monitoring frequency is per year, not a schedule.** `monitoring_per_year = 252` assumes evenly spaced looks. A real term sheet lists fixing dates and may skip holidays or watch only closing prices; that is a different contract.
- **American prices.** QuantLib's `BaroneAdesiWhaleyApproximationEngine` implements the same BAW paper. American equity options with discrete cash dividends are usually priced on a tree or grid with the dividend dates explicit; the continuous yield here is a simplification. The FD scheme is a fixed reference grid for cross-language agreement (ruling E-A23), not a converged answer: compare it with CRR at more steps before trusting the third digit.
- **Model choice is not a detail.** Heston and local vol can be calibrated to the same vanilla surface and still disagree on barriers, because they imply different forward smiles. That gap is model risk, and one reason desks use stochastic-local vol (see [LEARN: Heston family](../../LEARN.md#heston-bates-merton-and-slv)).

## Common mistakes

- Passing log-moneyness relative to spot, `ln(K/S)`, to `vol.local.dupire`. The surface is in forward log-moneyness; with `r ≠ q` the two differ (here by `(r - q)T = 0.03`).
- Expecting BAW, CRR and FD to agree to many digits. They are three methods; at these settings they differ by 0.03.
- Using BAW with `r <= 0`. The spec returns `E_DOMAIN`; use CRR or FD.
- Reading Heston's `v0` as a vol. It is a variance: 0.0625 is a 25% vol.
- Pricing a daily-fixed barrier with the continuous formula. Here that undervalues the knock-out call by 0.380, about 4.5% of 8.519.

## What you just did

You priced an American put three ways and saw the early-exercise premium (0.32 to 0.35) and the spread between methods (0.03). You priced a down-and-out call watched continuously, daily and weekly, and saw the BGK shift raise the price as monitoring gets sparser. You priced one vanilla call under Black-Scholes, Heston and local vol and got three prices, 11.12, 10.52 and 11.36, for one contract. The same eleven lines came out of four independent implementations.

## Try next

- Raise CRR `steps` to 2000 and the FD grid to `nx = 801, nt = 800`: CRR and FD should move toward each other.
- Make the American a `CALL`. Per the spec, BAW returns the European price for a call when `q <= 0`; with `q = 0.02` there is a small premium.
- Try `DOWN_IN` and check that in plus out equals the vanilla for the continuous barrier.
- Set `xi` close to 0 in the Heston case and compare with Black-Scholes at 25%.
- Read [LEARN: exotics and American options](../../LEARN.md#exotics-and-american-options), [LEARN: local vol and forward vol](../../LEARN.md#local-vol-and-forward-vol) and the [Cookbook](../../COOKBOOK.md).

## References and further reading

- [BAW87] G. Barone-Adesi, R. E. Whaley, "Efficient analytic approximation of American option values", *Journal of Finance* 42(2), 1987, pp. 301-320, [doi:10.1111/j.1540-6261.1987.tb02569.x](https://doi.org/10.1111/j.1540-6261.1987.tb02569.x) (paywalled; the spec marks it not opened).
- [CRR79] J. Cox, S. Ross, M. Rubinstein, "Option pricing: a simplified approach", *Journal of Financial Economics* 7(3), 1979, [doi:10.1016/0304-405X(79)90015-1](https://doi.org/10.1016/0304-405X(79)90015-1) (paywalled; the spec marks it not opened).
- [RR91] E. Reiner, M. Rubinstein, "Breaking down the barriers", *Risk* 4(8), 1991 (not opened; no stable link).
- [BGK97] M. Broadie, P. Glasserman, S. Kou, "A continuity correction for discrete barrier options", *Mathematical Finance* 7(4), 1997, [doi:10.1111/1467-9965.00035](https://doi.org/10.1111/1467-9965.00035) (paywalled; the spec marks it not opened).
- [Hes93] S. L. Heston, "A closed-form solution for options with stochastic volatility with applications to bond and currency options", *Review of Financial Studies* 6(2), 1993, pp. 327-343, [doi:10.1093/rfs/6.2.327](https://doi.org/10.1093/rfs/6.2.327) (paywalled).
- [Alb07] H. Albrecher, P. Mayer, W. Schoutens, J. Tistaert, "The little Heston trap", *Wilmott* 2007(1), pp. 83-92 (not opened).
- [Lew01] A. Lewis, "A simple option formula for general jump-diffusion and other exponential Levy processes", 2001 (not opened).
- [Dup94] B. Dupire, "Pricing with a smile", *Risk* 7(1), 1994, pp. 18-20 (not opened).
- [Gat06] J. Gatheral, *The Volatility Surface*, Wiley, 2006, ch. 1 (not opened).
- E. G. Haug, *The Complete Guide to Option Pricing Formulas*, 2nd ed., McGraw-Hill, 2007, chapters 3 and 4 (not opened).
- QuantLib reference: [AnalyticBarrierEngine](https://www.quantlib.org/reference/class_quant_lib_1_1_analytic_barrier_engine.html), [BaroneAdesiWhaleyApproximationEngine](https://www.quantlib.org/reference/class_quant_lib_1_1_barone_adesi_whaley_approximation_engine.html), [AnalyticHestonEngine](https://www.quantlib.org/reference/class_quant_lib_1_1_analytic_heston_engine.html).
- In this repository: `specifications/04-pricing/exotics.md`, `specifications/05-volatility/heston-family.md`, `specifications/05-volatility/local-and-forward-vol.md`; [LEARN: Heston family](../../LEARN.md#heston-bates-merton-and-slv); [Glossary](../../GLOSSARY.md#stage-e-full-volatility-exotics-rates-vol-correlation-and-credit).

Three publisher DOI links (BAW87, BGK97, Hes93) return 403 to automated requests; each DOI was checked against its Crossref record (title, volume, issue). The CRR79 DOI and the three QuantLib pages returned 200. Links checked 2026-11-11.
