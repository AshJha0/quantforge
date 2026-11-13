# Tutorial 18: a minimum-variance hedge with the QP solver

The plain idea: most hedges are a small least-squares problem. Write the risks of your book as a list of numbers (key-rate DV01s, a beta, a delta) and the same risks of one unit of each hedge instrument as the columns of a matrix. Then choose how many units of each instrument to hold so that book plus hedges is as close to zero risk as possible. Real hedges add conditions: you can only go long some bonds, you can only trade so much of another, futures come in whole contracts, two instruments may carry the same risk. Each of those changes the problem, and this tutorial shows what each one does.

You will compute a minimum-variance hedge ratio from a short history, size Hull's index-futures hedge, solve a key-rate hedge with bounds and without, watch the solver refuse a problem with two interchangeable instruments until you ask for the minimum-norm answer, find the best whole-contract hedge, and report the risk left over. Python first, then Rust, Java and C++. All data is synthetic and comes from the `examples/hedge_*_i.json` files named in the code. Budget 15 minutes. Every number shown is a real output.

Terms: DV01 and key rates are in the [glossary, tutorial terms](../../GLOSSARY.md#tutorial-terms). Defined here: a **minimum-variance hedge ratio** is the number of hedge units per unit of exposure that makes the variance of the hedged position as small as possible; **beta** is the slope of a portfolio's return on the market's return; a **lot** is the smallest tradeable amount of an instrument, one futures contract for example.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.
- For step 2, the three builds made in [Tutorial 1](tutorial-1-swap.md).

## Step 1: Python

Save the next block as `hedge18.py` and run it from the repository root (or paste it into `uv run --project python python -`). It calls `quantforge_core.hedge_solvers` directly.

<!-- tutorial:run python -->
```python
import json

from quantforge_core import hedge_solvers
from quantforge_core.errors import QfError


def inputs(name):
    with open(f"examples/{name}.json", encoding="utf-8") as f:
        return json.load(f)["inputs"]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(v, places) for v in values)


# 1. Minimum-variance hedge ratio from 12 daily value changes of a position and a future.
mv = inputs("hedge_minvar_i")
r = hedge_solvers.minvar_ratio(None, mv["exposure_changes"], mv["hedge_changes"])
print(f"min-variance hedge {num(r['hedge'][0], 4)}  effectiveness {num(r['effectiveness'], 4)}")

# 2. Hull's equity beta hedge: index futures that take a portfolio's beta from 1.5 to 0.
bf = inputs("hedge_beta_i")
r = hedge_solvers.beta_futures(bf["portfolio_value"], bf["portfolio_beta"], bf["target_beta"],
                               bf["futures_price"], bf["multiplier"])
print(f"beta hedge contracts {num(r['contracts_held'], 0)}  beta after {num(r['beta_after'], 4)}")

# 3. A key-rate hedge with three bonds, long only, at most 20 of the second.
kr = inputs("hedge_qp_keyrate_i")
r = hedge_solvers.qp_solve(kr["a"], kr["b"], kr["weights"], lower=kr["lower"], upper=kr["upper"])
print(f"key-rate hedge x {nums(r['x'], 4)}  objective {num(r['objective'], 4)}")
free = hedge_solvers.qp_solve(kr["a"], kr["b"], kr["weights"])
print(f"  without bounds x {nums(free['x'], 4)}  objective {num(free['objective'], 4)}")

# 4. Two identical instruments: no unique answer, unless you ask for the smallest one.
mn = inputs("hedge_qp_minnorm_i")
try:
    hedge_solvers.qp_solve(mn["a"], mn["b"], mn["weights"])
except QfError as e:
    print(f"duplicate instruments, default: {e.code}")
r = hedge_solvers.qp_solve(mn["a"], mn["b"], mn["weights"], singular="MIN_NORM")
print(f"  MIN_NORM x {nums(r['x'], 4)}  rank {r['rank']}")

# 5. Whole contracts: the best integer hedge is not the rounded continuous one.
it = inputs("hedge_integer_i")
r = hedge_solvers.integer_solve(it["a"], it["b"], it["weights"], it["lot_sizes"])
print(f"integer lots {r['lots']}  objective {num(r['objective'], 6)}  rounding cost {num(r['rounding_cost'], 6)}")

# 6. What risk is left after a hedge, and where it sits.
rr = inputs("hedge_residual_i")
r = hedge_solvers.residual_report(rr["a"], rr["b"], rr["x"], rr["covariance"])
print(f"residual vol {num(r['volatility_after'], 6)}  effectiveness {num(r['effectiveness'], 4)}"
      f"  contributions {nums(r['contributions'], 8)}")
```

```bash
uv run --project python python hedge18.py
```

Real output, 2026-11-12, Windows 11:

<!-- tutorial:expect -->
```text
min-variance hedge -1.1123  effectiveness 0.9788
beta hedge contracts -30  beta after 0.0000
key-rate hedge x 21.9048 20.0000 15.3345  objective 55.7356
  without bounds x 16.4590 25.2802 13.4015  objective 38.1245
duplicate instruments, default: E_SINGULAR
  MIN_NORM x 1.0000 1.0000 0.0000  rank 2
integer lots [0, 1]  objective 0.172125  rounding cost 0.172125
residual vol 0.014000  effectiveness 0.5171  contributions 0.00009172 0.00006246 0.00004182
```

### Reading the numbers

- **Minimum variance, -1.1123.** Hold 1.1123 units short of the hedge per unit of the position. Hull writes the ratio as `h* = rho sigma_S / sigma_F`, the size of a short hedge; the spec reports the units held, so the sign is negative (ruling I-8). The effectiveness 0.9788 is the share of the variance removed, which for one instrument is `rho^2`: the correlation of the two series is `sqrt(0.9788)` = 0.989. On 12 observations that estimate is itself uncertain; the ratio is only as good as the history it came from.
- **Beta hedge, -30 contracts.** Hull's example (chapter 3): a 5,050,000 portfolio with beta 1.5, index futures at 1,010 with a multiplier of 250. `contracts = (0 - 1.5) x 5,050,000 / (1,010 x 250)` = -7,575,000 / 252,500 = -30 exactly, so selling 30 contracts takes the beta to 0.
- **Key-rate hedge with bounds.** Five key-rate exposures of a book (`b`, all negative) and three bonds (columns of `a`). Long only, and at most 20 of the second bond. The unbounded solution wants 25.28 of the second bond; the bound holds it at 20, and the other two bonds move (16.46 to 21.90, 13.40 to 15.33) to take up part of its job. The objective, the weighted sum of squared residual risks, rises from 38.12 to 55.74: that is the price of the bound. Five risks and three instruments cannot all be zeroed, so even the unbounded objective is above zero.
- **Two identical instruments.** The first two columns of `a` are the same, `(1, 0.5)`. Any split between them hedges equally well, so the minimiser is not unique and the default answer is `E_SINGULAR` rather than an arbitrary pick. `MIN_NORM` asks for the split of least size: 1 and 1, the even split, with rank 2 for three instruments. A desk would rather know about the duplicate than have a solver choose for it, which is why `ERROR` is the default (ruling I-5).
- **Whole lots.** Two highly correlated instruments, `a = [[1, 0.95], [0.95, 1]]`, `b = (-1.265, -1.27)`. The continuous answer is `(0.6, 0.7)`, with objective 0 (it prints as `continuous_objective` about 3e-31). Rounding gives `(1, 1)`, whose residuals are `(0.685, 0.68)` and objective 0.9317. The best whole-lot answer is `(0, 1)`, objective 0.172125, just ahead of `(1, 0)` at 0.172625. Check either by hand: for `(0, 1)` the residuals are `(0.95 - 1.265, 1 - 1.27)` = `(-0.315, -0.27)`, and `0.315^2 + 0.27^2` = 0.172125.
- **Residual risk.** A given hedge `x` on three factors with covariance `S`. Before it, the book's volatility is `sqrt(0.0004059)` = 0.0201; after it, 0.0140, so 51.7% of the variance is gone. The contributions split the remaining variance by factor and add up to it: 0.00009172 + 0.00006246 + 0.00004182 = 0.00019600. The first factor carries almost half of what is left, so that is where to look for a better hedge.

### Formal statement, checked against the spec

From [`08-hedging/hedge-solvers.md`](../../specifications/08-hedging/hedge-solvers.md) (rulings I-3 to I-12, I-41 to I-49).

`hedge.qp.solve` minimises `f(x) = sum_i w_i (A x + b)_i^2 + ridge sum_j x_j^2` subject to optional equalities `E x = e` and bounds `lower_j <= x_j <= upper_j`, where `null` means no bound. With `H = A^T W A + ridge I` and `Z` a basis of the null space of `E`, an eigenvalue of `Z^T H Z` at most `1e-12` times the largest of `H` means no unique minimiser: `E_SINGULAR`, or under `MIN_NORM` (no bounds allowed) the least-norm minimiser `-(A^T W A + ridge I)^+ A^T W b` [Golub and Van Loan 5.5]. Otherwise the minimiser is unique and satisfies the KKT conditions [Nocedal and Wright, theorem 12.1]. No point satisfying the constraints: `E_INFEASIBLE`.

`hedge.integer.solve` minimises the same `f` over `x_j = lot_sizes_j n_j` with integer `n`; ties within `1e-12` relative go to the smallest `sum |n_j|`, then the lexicographically smallest `n` (I-7). `rounding_cost = objective - continuous_objective >= 0`.

`hedge.minvar.ratio`: `hedge = -S_hh^{-1} S_he`, from a covariance or from series with divisor `T - 1`; `effectiveness = 1 - variance_after / variance_before`.

`hedge.beta.futures`: `contracts = (beta* - beta) V / (F m)`, rounded half away from zero under `NEAREST` (I-10).

`hedge.residual.report`: `r = A x + b`, `variance_after = r^T S r`, `contributions_i = r_i (S r)_i` (Euler allocation, I-11).

The outside check for `hedge.qp.solve` is scipy's `lsq_linear` with the BVLS method (Stark and Parker 1995); integer lots, beta futures and the residual report have no outside library that solves them a different way, which the spec records as a reason stage I's outside share is below its 60% floor.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_hedge_18.py` sends the same eight cases, built from the same example files, to the CLI you name and prints the same eight lines. The case without `singular` comes back as an error result, and the script prints its code. It uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_hedge_18.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_hedge_18.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_hedge_18.py cpp26/build/quantforge
```

Each prints the eight lines of step 1, digit for digit, the error code included. The full checks are the conformance suites, for example `python conformance/runner/runner.py --impl rust --suite hedgeqp_i`.

## For practitioners

- **Weights are a choice.** `weights` say how much each residual risk matters. Equal weights on key-rate DV01s treat a 2-year and a 30-year basis point alike; diagonal weights (one number per key rate) ignore how key rates move together, so the weighted sum of squares is not the hedged position's variance unless the key-rate moves are uncorrelated. The variance itself needs the full covariance, `r^T S r`, which is what `hedge.minvar.ratio` minimises and `hedge.residual.report` reports (review finding 19).
- **Ridge.** A small `ridge` stops the solver from taking large offsetting positions in nearly collinear instruments. It also biases the hedge; report it with the result.
- **Bounds are where the cost of a mandate shows.** The rise in the objective when a bound becomes active is the risk you keep because of the bound. Compare the bounded and unbounded objectives before arguing about a limit.
- **Integer lots matter for small books.** On a book worth thousands of contracts the rounding cost is negligible; on a book worth two it decides the hedge, as here.
- **History length.** A 12-observation hedge ratio has a wide confidence interval. Desks use longer windows, or a factor model's covariance, and re-estimate on a schedule.

## Common mistakes

- **The sign of Hull's `h*`.** Hull quotes the size of a short position; `hedge` here is the signed number of units held.
- **Rounding the continuous answer.** It can be far from the best whole-lot hedge; here it is more than five times worse.
- **Expecting a pick when instruments are duplicates.** The default is `E_SINGULAR`; ask for `MIN_NORM` explicitly, and only without bounds (else `E_INPUT`).
- **Reading contributions as volatilities.** They split the variance, not the volatility, and one can be negative when factors offset.
- **Passing `null` outside the bound lists.** It is `E_SCHEMA` (I-47).

## What you just did

You estimated a minimum-variance hedge ratio, reproduced Hull's 30-contract beta hedge, solved a key-rate hedge with and without bounds and measured what the bound costs, saw the solver refuse a hedge with duplicate instruments and then give the minimum-norm one, found a whole-lot hedge better than rounding, and broke the remaining risk down by factor. Python, Rust, Java and C++ gave the same digits.

## Try next

- Set `target_beta` to 0.75 in the beta hedge: the answer is -15 contracts.
- Add `"ridge": 1.0` to the key-rate hedge and watch the positions shrink and the objective grow.
- Give the integer hedge lot sizes of 0.5 and see whether rounding gets closer.
- Read [LEARN: a hedge is a small least-squares problem](../../LEARN.md#a-hedge-is-a-small-least-squares-problem), then go on to [Tutorial 19](tutorial-19-credit-correlation.md).

## References and further reading

The spec lists these as sources; "not opened" there means the spec authors cited them from memory.

- J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 3, "Hedging strategies using futures": the minimum-variance hedge ratio and the 30-contract stock-index example. Not opened (the spec's [H18]); no link given.
- J. Nocedal, S. J. Wright, *Numerical Optimization*, 2nd ed., Springer, 2006, [doi:10.1007/978-0-387-40065-5](https://doi.org/10.1007/978-0-387-40065-5) (paywalled): chapter 12 (KKT conditions) and chapter 16 (quadratic programming). Not opened per the spec.
- G. H. Golub, C. F. Van Loan, *Matrix Computations*, 4th ed., Johns Hopkins University Press, 2013, section 5.5: rank-deficient least squares and the minimum-norm solution. Not opened per the spec; no link given.
- P. B. Stark, R. L. Parker, "Bounded-variable least-squares: an algorithm and applications", *Computational Statistics* 10, 1995, 129-141, [author's preprint](https://www.stat.berkeley.edu/~stark/Preprints/bvls.pdf); and scipy, [`lsq_linear`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.lsq_linear.html), which implements it and is the outside check.
- U. Fincke, M. Pohst, "Improved methods for calculating vectors of short length in a lattice, including a complexity analysis", *Mathematics of Computation* 44(170), 1985, 463-471, [doi:10.1090/S0025-5718-1985-0777278-8](https://doi.org/10.1090/S0025-5718-1985-0777278-8): enumeration for integer least squares.
- This project: [`08-hedging/hedge-solvers.md`](../../specifications/08-hedging/hedge-solvers.md), rulings in [`stage-i-rulings.md`](../../specifications/stage-i-rulings.md); [LEARN, stage I: hedging](../../LEARN.md#stage-i-hedging).

Links checked 2026-11-12: the Springer DOI, the Berkeley preprint and the scipy page returned HTTP 200; the AMS DOI returned 403 to a scripted request and its title, journal, volume and pages were confirmed through the Crossref API.
