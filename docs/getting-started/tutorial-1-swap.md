# Tutorial 1: price your first swap

The plain idea: a swap swaps a fixed rate for a floating one. To value it you need today's price of a dollar paid on each future date, and that set of prices is a discount curve. You build the curve from the swap rates the market quotes, then use it to price your own swap and to ask how much the price moves when rates move by one basis point (0.01%). That move is the DV01.

This tutorial does all four steps (quotes, curve, swap PV, DV01) with library calls, first in Python, then the same in Rust, Java and C++. Budget 10 minutes, most of it the first build. Every number shown is a real output; CI runs every code block on this page on a fresh runner (`.github/workflows/tutorial.yml`) and fails if any printed line differs.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/). It fetches Python 3.15 and the one runtime dependency, NumPy, for you.

## Step 1: Python

```bash
uv sync --locked --project python
```

Save the next block as `swap.py` (or paste it into `uv run --project python python -`):

<!-- tutorial:run python -->
```python
from datetime import date

from quantforge_core import ois, sensitivities
from quantforge_core.ois import OisTrade, Quote

# 1. Quotes: par rates of SOFR overnight index swaps (synthetic, not market data).
as_of = date(2026, 11, 6)
quotes = [Quote("1Y", 0.035), Quote("2Y", 0.0335), Quote("3Y", 0.033),
          Quote("5Y", 0.0335), Quote("7Y", 0.0345), Quote("10Y", 0.036)]

# 2. Curve: find the discount factors that reprice every quote exactly.
curve, max_error = ois.bootstrap("SOFR", as_of, quotes, "LOG_LINEAR_DF")

# 3. Swap: pay 3.40% fixed on 10 million USD for 5 years, receive compounded SOFR.
trade = OisTrade("SOFR", "5Y", 0.034, 10_000_000.0, "PAY")
valuation, par_rate, annuity = ois.pv(curve, trade)

# 4. DV01: rebuild the curve with every quote 1bp up and 1bp down; half the PV difference.
dv01, key_rates = sensitivities.dv01(as_of, quotes, "LOG_LINEAR_DF", trade)

print(f"1Y discount factor {curve.discount_factors[0]:.12f}")
print(f"PV   {valuation['pv']:.4f} {valuation['currency']}")
print(f"par  {par_rate:.10f}")
print(f"DV01 {dv01:.4f}")
```

```bash
uv run --project python python swap.py
```

Real output, 2026-11-09, Windows 11:

<!-- tutorial:expect -->
```text
1Y discount factor 0.964899988733
PV   -22955.4220 USD
par  0.0335000000
DV01 4597.7356
```

### Reading the numbers

- **Discount factor.** 0.9649 means a dollar paid on the first pillar date (2027-11-15, one year after spot) is worth 96.5 cents today. The bootstrap is exact to rounding: `max_error` came back near 1e-16.
- **PV.** The fair fixed rate for a 5Y swap on this curve is 3.35%, which is just the 5Y quote. You pay 3.40%, 5bp too much, so the swap is worth less than zero to you. As a check, PV is close to minus notional times 0.0005 times the annuity: 10,000,000 × 0.0005 × 4.591 = 22,955.
- **DV01.** Positive: you pay fixed, so you gain when rates rise. About 4,598 USD per basis point, close to notional × annuity × 1bp = 4,591. Nearly all of it sits on the 5Y quote; `key_rates` shows the split.

Formally: the curve and PV follow `specifications/02-curves/ois-curves.md`, and the DV01 is the central difference in `specifications/06-risk/rates-sensitivities.md`. The swap's PV for the payer is N × (Σ αᵢ Fᵢ Pᵢ − K × Σ αᵢ Pᵢ), with αᵢ the accrual fractions, Fᵢ the compounded overnight forwards and Pᵢ the discount factors; the second sum is the annuity.

## Step 2: the same in Rust, Java and C++

Each language ships a CLI that takes the same operations as JSON (`specifications/cli-contract.md`). `examples/tutorial_swap.py` sends the three steps above, `rates.ois.bootstrap`, `rates.ois.pv` and `risk.ois.dv01`, to whichever CLI you name and prints the same four lines. It uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_swap.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_swap.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_swap.py cpp26/build/quantforge
```

Each prints the four lines shown in step 1, digit for digit. That is the project's claim in small: four independent implementations of one specification agree. The full check is the conformance suite: `python conformance/runner/runner.py --impl rust --suite ois`.

## Try next

- Change the fixed rate to 0.0335. The PV goes to about zero, because that is the par rate.
- Change `"LOG_LINEAR_DF"` to `"LINEAR_ZERO"`. The curve still reprices every quote, but discount factors between pillars change.
- Print `key_rates`: the DV01 split by quote.
- Read [LEARN](../../LEARN.md#curves-and-fixed-income) for why bootstrapping works, and the [Cookbook](../../COOKBOOK.md) for the other operations.
