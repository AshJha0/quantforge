# Tutorial 35: price liquidity: a cost curve by order size and horizon

The plain idea: selling a position costs more than the screen price. You cross half the bid-ask spread, and your own selling pushes the price; the push grows with the size of the order and with the speed at which you trade it. Trading slowly cuts the push but leaves you exposed to the market for longer. A liquidity curve puts numbers on both sides of that trade-off for every size and horizon, and finds the horizon where the total is smallest.

You will check square-root impact by hand, read the cost of one order over seven horizons, find the cost-minimising horizon for four sizes, and see what a different impact exponent does. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 10 minutes. All data and parameters are synthetic and assumed.

Terms, defined here. **Participation** is the fraction of a day's volume you trade each day, `Q / (V h)` for `Q` units over `h` days. **Impact** is the price move your trading causes, here `Y sigma (Q/(V h))^delta` as a fraction of price, with `sigma` the daily volatility; `delta = 1/2` is the square-root law. **Timing risk** is `z` standard deviations of the average sale price against the arrival price for an even liquidation, `z sigma sqrt(h/3)`. Costs print in basis points (bp) of the arrival price.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1.

## Step 1: Python

The script `examples/tutorials/t35_liquidity_curve.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t35_liquidity_curve.py -->
```python
"""Tutorial 35: a liquidity cost curve by order size and liquidation horizon: half spread,
square-root impact, timing risk and the cost-minimising horizon.

  uv run --project python python examples/tutorials/t35_liquidity_curve.py         # Python
  python examples/tutorials/t35_liquidity_curve.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-35-liquidity-curve.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def bp(values):
    return " ".join(f"{x * 1e4:.2f}" for x in values)


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command
    stock = {"half_spread_bps": 5.0, "daily_volume": 1.0e7, "daily_vol": 0.02}

    # 1. The hand case: 1 % of a day's volume in one day costs 20 bp of impact.
    r = call("liq.curve.cost", {**stock, "sizes": [1.0e5, 4.0e5], "horizons_days": [1.0, 4.0]})
    print(f"impact (bp), rows 1e5 and 4e5, columns 1 and 4 days: {bp(r['impact'][0])} | {bp(r['impact'][1])}")
    print(f"total (bp): {bp(r['total_cost'][0])} | {bp(r['total_cost'][1])}  optimum {r['optimal_horizon']}")

    # 2. Add timing risk at z = 1.645 and read the curve over horizons for one order of 1e6.
    h = [0.25, 0.5, 1, 2, 5, 10, 20]
    r = call("liq.curve.cost", {**stock, "risk_multiplier": 1.645, "sizes": [1.0e6], "horizons_days": h})
    print(f"horizons (days):  {' '.join(str(x) for x in h)}")
    print(f"impact (bp):      {bp(r['impact'][0])}")
    print(f"timing risk (bp): {bp(r['timing_risk'])}")
    print(f"total (bp):       {bp(r['total_cost'][0])}")
    print(f"optimal horizon {r['optimal_horizon'][0]:.4f} days  minimum {r['min_cost'][0] * 1e4:.2f} bp")

    # 3. The optimum by size: larger orders should be worked for longer.
    r = call("liq.curve.cost", {**stock, "risk_multiplier": 1.645, "sizes": [1e4, 1e5, 1e6, 5e6], "horizons_days": [1]})
    print(f"optimal horizon by size (days): {' '.join(f'{x:.4f}' for x in r['optimal_horizon'])}")
    print(f"minimum cost by size (bp):      {bp(r['min_cost'])}")

    # 4. The 3/5 exponent of Almgren et al.: the optimum moves.
    r = call("liq.curve.cost", {**stock, "risk_multiplier": 1.645, "exponent": 0.6, "sizes": [1.0e6], "horizons_days": [1]})
    print(f"delta 0.6: optimal horizon {r['optimal_horizon'][0]:.4f} days  minimum {r['min_cost'][0] * 1e4:.2f} bp")


if __name__ == "__main__":
    main(sys.argv[1:])
```

Run it:

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t35_liquidity_curve.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
impact (bp), rows 1e5 and 4e5, columns 1 and 4 days: 20.00 10.00 | 40.00 20.00
total (bp): 25.00 15.00 | 45.00 25.00  optimum None
horizons (days):  0.25 0.5 1 2 5 10 20
impact (bp):      126.49 89.44 63.25 44.72 28.28 20.00 14.14
timing risk (bp): 94.97 134.31 189.95 268.63 424.74 600.67 849.47
total (bp):       226.47 228.76 258.19 318.35 458.02 625.67 868.62
optimal horizon 0.3330 days  minimum 224.21 bp
optimal horizon by size (days): 0.0333 0.1053 0.3330 0.7445
minimum cost by size (bp):      74.32 128.27 224.21 332.80
delta 0.6: optimal horizon 0.3523 days  minimum 211.69 bp
```

### Reading the numbers

- **The hand case.** 100,000 shares is 1 % of a 10-million-share day. In one day the impact is `0.02 x sqrt(0.01) = 0.002`, 20 bp; four times the size doubles it to 40 bp, and spreading the order over four days halves it to 10 bp. With the 5 bp half spread the totals are 25, 15, 45 and 25 bp. With no timing risk (`z = 0`) slower is always cheaper, so there is no optimum and `optimal_horizon` is `null`.
- **One order over seven horizons.** For 1,000,000 shares (10 % of a day) impact falls from 126.49 bp at a quarter-day to 14.14 bp over 20 days, while timing risk at `z = 1.645` rises from 94.97 bp to 849.47 bp. The total is lowest near a third of a day: the optimum is `h* = (2 delta a / b)^(1/(delta + 1/2)) = 0.3330` days, with a minimum of 224.21 bp.
- **By size.** The optimal horizon grows with size, from 0.0333 to 0.7445 days between 10,000 and 5,000,000 shares. With `delta = 1/2`, `h*` is proportional to `sqrt(Q)` exactly: 100 times the size, 10 times the horizon (0.0333 to 0.3330).
- **A 3/5 exponent.** With `delta = 0.6`, near the exponent Almgren et al. report, the optimum moves out to 0.3523 days and the minimum falls to 211.69 bp.
- **These are not market numbers.** The volatility of 2 % a day and the coefficient `Y = 1` are assumed. With them waiting is expensive; a calmer stock or a smaller `z` moves the optimum out.

### The formal statement, checked against the spec

From [`10-execution/liquidity-curve.md`](../../specifications/10-execution/liquidity-curve.md) (rulings J-C-6 to J-C-8 in [`stage-j-rulings-curves.md`](../../specifications/stage-j-rulings-curves.md)).

`c(Q, h) = s + Y sigma (Q / (V h))^delta + z sigma sqrt(h / 3)`. The impact term is the square-root law of Toth et al. written in daily participation; the timing-risk term is the standard deviation of the linear Almgren-Chriss liquidation, whose variance is `sigma^2 X^2 T / 3`. With `a = Y sigma (Q/V)^delta` and `b = z sigma / sqrt 3`, `c = s + a h^(-delta) + b sqrt h` is convex and `h* = (2 delta a / b)^(1/(delta + 1/2))`. When `b = 0` or `Y = 0` there is no interior optimum and those outputs are `null`.

Stage H reuses this curve: at one day and `delta = 1/2` the impact equals its draft `exec.impact.sqrt` (ruling J-C-8). The checks behind the goldens (`liqcurve_j`): two hand cases (step 1 above is `liqcurve_j-0001`), the rest reference-computed at 50 digits. No outside library implements it, so it is self-assessed (ruling J-C-9).

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t35_liquidity_curve.py` sends the same cases (three `liq.curve.cost` with timing risk and one without) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t35_liquidity_curve.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t35_liquidity_curve.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t35_liquidity_curve.py cpp26/build/quantforge
```

Each is to print the 10 lines of step 1, digit for digit. The full check is `python conformance/runner/runner.py --impl rust --suite liqcurve_j`.

## For practitioners

- **Calibrate before you trust it.** `Y` and `delta` vary by stock, venue and period. Fit them on your own fills, with standard errors, before quoting a cost to anyone.
- **The risk multiplier is a preference.** `z` says how many standard deviations of timing risk you charge for. A risk-neutral desk sets it to 0 and trades as slowly as the horizon allows.
- **Even trading is a simplification.** The optimal schedule under risk aversion front-loads the trading (Almgren-Chriss); stage H builds it. This curve prices the even schedule only.
- **Liquidity horizons for capital are different.** FRTB scales expected shortfall by regulatory horizons of 10 to 120 days; that is a capital rule, not a cost curve, and it is not built here.

## Common mistakes

- **Volatility in the wrong unit.** `daily_vol` is daily, as a fraction. An annual 30 % is about 1.9 % a day.
- **Volume in money, size in shares.** `sizes` and `daily_volume` must be in the same unit.
- **Reading costs as money.** Outputs are fractions of the arrival price per unit; multiply by price and size for money.
- **Expecting an optimum without risk.** With `risk_multiplier` 0 the cost only falls with horizon, so the optimum is `null`.

## What you just did

You checked square-root impact by hand, read a cost curve over seven horizons for one order, found the cost-minimising horizon for four sizes and saw it scale with the square root of size, and moved it by changing the impact exponent.

## Try next

- Halve `daily_vol` and predict how `h*` changes before you run it (both `a` and `b` scale with `sigma`).
- Set `coefficient` to 0.5 and compare the minimum cost for 1,000,000 shares.
- Read the [liquidity curve page](../curves/liquidity.md).

## References and further reading

- B. Toth et al., "Anomalous price impact and the critical nature of liquidity in financial markets", *Physical Review X* 1, 2011, 021006. Recalled per the spec.
- R. Almgren, C. Thum, E. Hauptmann, H. Li, "Direct estimation of equity market impact", *Risk*, July 2005. Recalled per the spec.
- R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2), 2000. Recalled per the spec; the `T/3` variance is re-derived there.
- This project: [`10-execution/liquidity-curve.md`](../../specifications/10-execution/liquidity-curve.md), rulings in [`stage-j-rulings-curves.md`](../../specifications/stage-j-rulings-curves.md), all sources in [References](../references.md).
