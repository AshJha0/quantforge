# Tutorial 27: build a financing term structure: term repo, stock borrow and the forward they imply

The plain idea: a desk pays one rate for its own unsecured money (the funding curve) and another for money secured on the asset it holds (repo). Locking repo in for three months costs a different rate from rolling it overnight, so secured financing has a term structure of its own. So does the fee a stock lender earns. This page builds both from quotes, as a spread over the funding curve, reads term and forward financing rates off them, and prices an equity forward that carries on them. With one flat spread and one flat fee it gives back the stage D formula exactly.

You will check a one-quote curve by hand, build a four-quote curve with a borrow curve, read forward rates between pillars, price a forward with and without borrow and dividends, and confirm the flat case. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 10 minutes. All data is synthetic.

Terms, defined here. A **term repo rate** `R` for `[0, T]` is simple: one unit borrowed returns `1 + R T`. The **financing spread** is how far the secured rate sits above (or below, for a special) the funding curve, measured as a cumulative log amount `S(T) = ln(1 + R T) - Z(T) T`. A **borrow fee** is the annual fee, continuously compounded, that a lender of the stock earns. The **carry factor** `C(t) = exp(-Z(t) t - S(t) + B(t))` turns spot into the forward: `F = (S_0 - PV of dividends) / C(T)`.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1.

## Step 1: Python

The script `examples/tutorials/t27_financing_curve.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t27_financing_curve.py -->
```python
"""Tutorial 27: build a term repo and stock borrow curve over the funding curve, read forward
financing rates from it, and price an equity forward that carries on it.

  uv run --project python python examples/tutorials/t27_financing_curve.py         # Python
  python examples/tutorials/t27_financing_curve.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-27-financing-term-structure.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def bp(values):
    return " ".join(f"{x * 1e4:.2f}" for x in values)


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command

    # 1. One quote, checked by hand: flat 4 % funding, a one-year term repo at 5 % simple.
    hand = {"funding_times": [1.0], "funding_zero_rates": [0.04], "quote_times": [1.0], "repo_rates": [0.05],
            "borrow_times": [], "borrow_fees": []}
    r = call("repo.term.curve", {**hand, "query_times": [0.5, 1.0]})
    print(f"one quote: spread {num(r['pillar_spreads'][0], 10)}  (ln 1.05 - 0.04 = {num(math.log(1.05) - 0.04, 10)})")
    print(f"  term rate at 0.5 {num(r['financing_rate'][0], 6)}  at 1.0 {num(r['financing_rate'][1], 6)}"
          f"  borrow {r['borrow_fee']}")

    # 2. A sloped funding curve, four term repo quotes and two borrow quotes.
    curve = {"funding_times": [0.25, 0.5, 1.0, 2.0], "funding_zero_rates": [0.040, 0.041, 0.0415, 0.042],
             "quote_times": [1 / 12, 0.25, 0.5, 1.0], "repo_rates": [0.0425, 0.0430, 0.0435, 0.0440],
             "borrow_times": [0.25, 1.0], "borrow_fees": [0.0030, 0.0050]}
    q = [0.25, 0.5, 0.75, 1.0]
    r = call("repo.term.curve", {**curve, "query_times": q})
    print(f"pillar spreads (bp): {bp(r['pillar_spreads'])}")
    print(f"term rates (bp):     {bp(r['financing_rate'])}")
    print(f"forward rates (bp):  {bp(r['forward_financing'])}")
    print(f"borrow fee (bp):     {bp(r['borrow_fee'])}")

    # 3. The equity forward on that curve, with and without borrow, then with dividends.
    eq = {**curve, "spot": 50.0, "maturity_years": 0.75, "dividend_times": [], "dividend_amounts": []}
    a = call("eq.forward.term_financed", eq)
    b = call("eq.forward.term_financed", {**eq, "borrow_times": [], "borrow_fees": []})
    c = call("eq.forward.term_financed", {**eq, "dividend_times": [0.1, 0.4, 0.9], "dividend_amounts": [0.3, 0.35, 0.4]})
    print(f"forward with borrow {num(a['forward'], 6)}  without {num(b['forward'], 6)}"
          f"  carry {num(a['carry'], 6)}")
    print(f"with dividends {num(c['forward'], 6)}  pv dividends {num(c['pv_dividends'], 6)}")

    # 4. Flat inputs give the stage D form F = S exp((r + s - b) T).
    rr, s, fee = 0.03, 0.004, 0.002
    flat = {"funding_times": [1.0], "funding_zero_rates": [rr], "quote_times": [1.0],
            "repo_rates": [math.exp(rr + s) - 1], "borrow_times": [1.0], "borrow_fees": [fee],
            "spot": 100.0, "maturity_years": 0.75, "dividend_times": [], "dividend_amounts": []}
    f = call("eq.forward.term_financed", flat)
    print(f"flat: {num(f['forward'], 10)}  S exp((r+s-b)T) {num(100 * math.exp((rr + s - fee) * 0.75), 10)}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

Run it:

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t27_financing_curve.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
one quote: spread 0.0087901642  (ln 1.05 - 0.04 = 0.0087901642)
  term rate at 0.5 0.049390  at 1.0 0.050000  borrow None
pillar spreads (bp): 24.25 27.71 20.34 15.59
term rates (bp):     430.00 435.00 437.53 440.00
forward rates (bp):  430.00 435.32 433.18 433.18
borrow fee (bp):     30.00 43.33 47.78 50.00
forward with borrow 51.456039  without 51.640754  carry 1.456039
with dividends 50.793899  pv dividends 0.643404
flat: 102.4290317891  S exp((r+s-b)T) 102.4290317891
```

### Reading the numbers

- **One quote, by hand.** `S(1) = ln 1.05 - 0.04 = 0.0087901642`, the spread printed. Between 0 and the pillar the cumulative spread is a straight line, so at 0.5 the zero spread is the same 87.9 bp; the term rate there is `(e^(0.02 + 0.00439508) - 1)/0.5 = 4.9390 %`, and at 1.0 the quote, 5 %, comes back. No borrow quotes were given, so `borrow_fee` is `null` (`None` in Python).
- **Four quotes.** The spreads over funding are 24.25, 27.71, 20.34 and 15.59 bp at 1, 3, 6 and 12 months: the repo quotes rise by 15 bp from 1 to 12 months while the funding curve rises by more, so the secured premium shrinks with term. The term rates at 3, 6 and 12 months are the quotes, 430, 435 and 440 bp; 9 months, between pillars, reads 437.53.
- **Forward rates.** Each forward rate covers the period since the previous query: 435.32 bp for 3 to 6 months, 433.18 bp for 6 to 9 and again for 9 to 12 months. The last two are equal because the funding curve and the spread are both linear in their cumulative form on `[0.5, 1]`: flat forwards, by construction (ruling J-C-3).
- **Borrow.** The fee quotes are 30 bp to 3 months and 50 bp to a year, so the cumulative fee is 0.00075 at 0.25 and 0.005 at 1, and the forward fee between them is `(0.005 - 0.00075)/0.75 = 56.67 bp`. The term fee at 0.5 is `(0.00075 + 0.25 x 0.0056667)/0.5 = 43.33 bp`, as printed.
- **The forward.** Spot 50 over nine months: 51.456039 with borrow and 51.640754 without. The fee the holder earns by lending the stock lowers the cost of carry, so the forward is lower. Of the three dividends at 0.1, 0.4 and 0.9 years, only the first two fall inside nine months; they are worth 0.643404 on the carry factor, which lowers the forward to 50.793899.
- **The flat case.** One repo quote `e^(r + s) - 1` and one fee `b` give `F = 100 e^((0.03 + 0.004 - 0.002) x 0.75) = 102.4290317891`, the stage D formula (ruling D22), to every printed digit.

### The formal statement, checked against the spec

From [`02-curves/financing-term-structure.md`](../../specifications/02-curves/financing-term-structure.md) (rulings J-C-2 to J-C-5 in [`stage-j-rulings-curves.md`](../../specifications/stage-j-rulings-curves.md)).

`Z(t) t` is linear between the funding knots `(0, 0), (t_k, z_k t_k)`. Each quote gives `S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i`, linear between `(0, 0)` and the pillars. `P_f(t) = exp(-Z(t) t - S(t))`, term rate `(1/P_f(t) - 1)/t`, forward rate `(P_f(u)/P_f(t) - 1)/(t - u)`. Borrow: `B(T_j) = b_j T_j`, non-decreasing, linear between pillars. Forward: `F = (S_0 - sum_{0 < t_i <= T} A_i C(t_i)) / C(T)`. No extrapolation past the last pillar of any curve in use.

The checks behind the goldens (`termfin_j`): five hand cases (this page's one-quote curve is `termfin_j-0001`, its forward `termfin_j-0022`), the rest reference-computed at 50 digits from the spec text. No outside library builds this curve, so it is self-assessed (ruling J-C-9).

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t27_financing_curve.py` sends the same cases (two `repo.term.curve`, four `eq.forward.term_financed`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t27_financing_curve.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t27_financing_curve.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t27_financing_curve.py cpp26/build/quantforge
```

Each is to print the 9 lines of step 1, digit for digit. The full check is `python conformance/runner/runner.py --impl rust --suite termfin_j`.

## For practitioners

- **Spread over funding, not a separate curve.** Keeping repo as a spread makes the secured-unsecured basis visible and keeps it consistent when the funding curve moves.
- **Specials are negative spreads.** A bond in demand finances below general collateral and often below funding; the curve allows it (only `1 + R T <= 0` is refused).
- **Borrow is a term structure too.** Hard-to-borrow names have fees that change with term and around index events. A flat fee misprices long-dated forwards and dividend swaps.
- **No extrapolation.** Beyond the last quote the curve refuses to answer. Extrapolating secured financing is a judgement a desk should make explicitly.

## Common mistakes

- **Quotes in the wrong compounding.** Term repo is simple; passing a continuously compounded rate as `R` shifts every spread.
- **Mixing day counts.** The page uses year fractions on one axis. Convert ACT/360 repo dates and ACT/365 funding dates to that axis first.
- **Dividends after expiry.** Only dividends with `0 < t <= T` count; the 0.9-year dividend above is ignored for a nine-month forward.
- **Reading `spread` as a forward.** `spread` is a zero spread `S(t)/t`; the forward spread is the slope of `S`.

## What you just did

You built a financing curve from one quote and checked it by hand, built a four-quote curve with a borrow curve, read flat forward rates between pillars, priced an equity forward that carries on both curves, and confirmed that flat inputs give the stage D formula.

## Try next

- Make the 6-month repo quote a special at 3.80 % and predict the sign of the 3-to-6-month forward spread before you run it.
- Add a third borrow quote at 2 years and extend the repo curve so a 1.5-year forward is covered.
- Read the [financing curve page](../curves/financing-term.md) and [`02-curves/equity-curves.md`](../../specifications/02-curves/equity-curves.md) for the flat stage D operations.

## References and further reading

- P. Hagan, G. West, "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2), 2006. Raw (flat-forward) interpolation.
- V. Piterbarg, "Funding beyond discounting", *Risk*, February 2010. Recalled per the spec.
- M. Choudhry, *The Repo Handbook*, 2nd ed., 2010. Recalled per the spec; definitions only.
- This project: [`02-curves/financing-term-structure.md`](../../specifications/02-curves/financing-term-structure.md), rulings in [`stage-j-rulings-curves.md`](../../specifications/stage-j-rulings-curves.md), all sources in [References](../references.md).
