# Tutorial 20: one hedge for equity and rates

The plain idea: an equity book is not only an equity risk. An option's value depends on the discount rate, a forward is worth `S e^{-qT} - K P(T)`, and a book that also holds a bond has rate risk at whatever maturities the bond pays. Treat the equity move and the key rates as one list of risks and you can solve one hedge for all of them; hedge only the equity and the rates are left behind. The second question is practical: if a desk will only trade two instruments, which two? The obvious method, take the best single instrument and then its best partner, can miss the best pair.

You will hedge a book of index options and a 7-year bond with the index and zero-coupon bonds, see which key rate the hedge instruments cannot reach, add the bond that reaches it, compare with an equity-only hedge, and then pick the best one and the best two instruments out of three by exhaustive search. Python first, then Rust, Java and C++. All data is synthetic: `examples/hedge_crossasset_i.json` and `examples/hedge_select_i.json`, with variants built in the code. Budget 15 minutes. Every number shown is a real output.

Terms: key rates and DV01 are in the [glossary, tutorial terms](../../GLOSSARY.md#tutorial-terms). Defined here: **EQ01** is the value change for a 1% move in the equity price; **KR01** at a pillar is the value change for a 1bp move in that pillar's zero rate alone; a **zero-coupon bond** (ZCB) pays its notional once, at maturity.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.
- For step 2, the three builds made in [Tutorial 1](tutorial-1-swap.md).

## Step 1: Python

Save the next block as `hedge20.py` and run it from the repository root (or paste it into `uv run --project python python -`). It calls `quantforge_core.cross_asset_hedge` and `quantforge_core.hedge_solvers` directly.

<!-- tutorial:run python -->
```python
import json

from quantforge_core import cross_asset_hedge, hedge_solvers


def inputs(name):
    with open(f"examples/{name}.json", encoding="utf-8") as f:
        return json.load(f)["inputs"]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(v, places) for v in values)


def positions(items):
    return [(p["instrument"], {key: v for key, v in p.items() if key != "instrument"}) for p in items]


# 1. One hedge for equity and rates: an equity option book with a 7-year bond, hedged with
#    the index and 2-year and 10-year zero-coupon bonds. Risks: EQ01, then KR01 at 1, 2, 5, 10 years.
xa = inputs("hedge_crossasset_i")


def crossasset(hedges, weights):
    return cross_asset_hedge.crossasset_solve(xa["spot"], xa["dividend_yield"], xa["volatility"],
                                              xa["curve"]["times"], xa["curve"]["zero_rates"],
                                              positions(xa["book"]), positions(hedges), weights)


r = crossasset(xa["hedges"], xa["weights"])
print(f"book risk     {nums(r['book_risk'], 2)}")
print(f"hedge         {nums(r['positions'], 4)}")
print(f"residual risk {nums(r['residual_risk'], 2)}")
five = {"instrument": "ZCB", "expiry_years": 5.0, "notional": 1000000.0}
r = crossasset(xa["hedges"] + [five], xa["weights"])
print(f"add 5y bond   {nums(r['positions'], 4)}  residual {nums(r['residual_risk'], 2)}")
eq = crossasset(xa["hedges"][:1], xa["weights"])
print(f"equity only   {nums(eq['positions'], 4)}  residual {nums(eq['residual_risk'], 2)}")

# 2. Choose the best two of three instruments; greedy selection picks the wrong first one.
s = inputs("hedge_select_i")
for k in (1, 2):
    r = hedge_solvers.select_solve(s["a"], s["b"], s["weights"], k)
    print(f"best {k}: instruments {r['selected']}  x {nums(r['x'], 4)}  objective {num(r['objective'], 4)}")
```

```bash
uv run --project python python hedge20.py
```

Real output, 2026-11-12, Windows 11:

<!-- tutorial:expect -->
```text
book risk     -1265.39 -6.20 -13.24 -655.51 -434.65
hedge         31.6348 -0.0706 -0.6356
residual risk 0.00 -6.20 0.00 -655.51 0.00
add 5y bond   31.6348 -0.0706 -0.6356 -1.5617  residual 0.00 -6.20 0.00 0.00 0.00
equity only   31.6348  residual 0.00 -6.20 -13.24 -655.51 -434.65
best 1: instruments [0]  x 0.6667 0.0000 0.0000  objective 0.6667
best 2: instruments [1, 2]  x 0.0000 1.0000 1.0000  objective 0.0000
```

### Reading the numbers

- **The book.** Index at 4,000, dividend yield 1.5%, volatility 18%, zero rates 3% to 3.8% at 1, 2, 5 and 10 years. The book is short 50 eighteen-month 4,200 calls, long 30 three-year 3,600 puts and long a 7-year zero-coupon bond of 2 million. Its risks are EQ01 -1,265.39 and KR01s -6.20, -13.24, -655.51 and -434.65 at the four pillars.
- **Where the rate risk sits.** Most of it is the 7-year bond. The 7-year zero rate is 3.5% + 2/5 x 0.3% = 3.62%, so `P(7)` = `e^{-0.2534}` = 0.776, and the bond's rate risk is about `-N T P(7) x 1bp` = -2,000,000 x 7 x 0.776 x 0.0001 = -1,087. Seven years lies between the 5- and 10-year pillars, and with rates linear in time a bump at 5 years moves the 7-year rate by 3/5 of a basis point and a bump at 10 years by 2/5. So about -652 lands on 5 years and -435 on 10 years; the options add the small rest.
- **The hedge.** 31.63 units of the index cancel the EQ01: one unit has EQ01 of 1% of 4,000 = 40, and 31.63 x 40 = 1,265. Selling 0.0706 of the 2-year bond (notional 1 million) and 0.6356 of the 10-year bond cancels their pillars exactly. The 1-year and 5-year risks stay, because no hedge instrument has any risk at those pillars: a 2-year and a 10-year zero-coupon bond move only with their own pillar's rate.
- **Add a 5-year bond.** Selling 1.5617 of it removes the 5-year risk. The 1-year residual of -6.20 is now the only one left: four instruments, five risks.
- **Equity only.** With just the index, the EQ01 is gone and every rate risk remains. Here the index position is the same as in the joint hedge because each hedge instrument carries one kind of risk only: the index has no rate risk and the bonds no equity risk, so the joint problem splits in two. With a hedge that carries both, such as an index forward, the two parts interact, and the joint solve accounts for the rate risk the forward brings (see "Try next").
- **Selection: the best single instrument is not in the best pair.** The three instruments have risks `(1, 1, 1)`, `(1, 0, 0)` and `(0, 1, 0)` on three factors, against a book of `(-1, -1, 0)`. Alone, instrument 0 is best: hold 2/3 and the residual is `(-1/3, -1/3, 2/3)`, objective 6/9 = 0.6667; instrument 1 alone leaves 1. A greedy method keeps instrument 0 and adds its best partner: with instrument 1, the residual is `(x0 + x1 - 1, x0 - 1, x0)`, best at `x0 = 0.5`, objective 0.5. The exhaustive search finds the pair `[1, 2]` with objective 0: the book is exactly one unit of each, with the sign changed.

### Formal statement, checked against the spec

From [`08-hedging/cross-asset-hedge.md`](../../specifications/08-hedging/cross-asset-hedge.md) and [`08-hedging/instrument-selection.md`](../../specifications/08-hedging/instrument-selection.md) (rulings I-20 to I-23, I-33 to I-35, I-53).

Cross-asset (I-21): per unit of each instrument, `EQ01 = (V(1.01 S) - V(0.99 S))/2` and `KR01_k = (V(z_k + 1bp) - V(z_k - 1bp))/2`, with only pillar `k` moved and the curve linear in zero rates between pillars, flat before the first and undefined after the last (a maturity beyond it is `E_INPUT`, I-20). `P(T) = exp(-z(T) T)`. The risk matrix `A` has rows `EQ01, KR01_1..KR01_P` and a column per hedge; the hedge is `hedge.qp.solve` with `a = A`, the book's risk as `b`, and `weights`. `residual_risk = book_risk + A positions`.

Selection (I-34): for every subset of `1..K` instruments, solve `hedge.qp.solve` on those columns with the others at 0, and return the subset with the least objective; ties within `1e-12` relative go to the smaller subset, then the lexicographically smaller indices. At most 20 instruments, and at most 100,000 candidate subsets (I-53), else `E_LIMIT`.

The outside checks (I-2): QuantLib 1.44's `ZeroCurve` and `AnalyticEuropeanEngine` with the same half-differences, then numpy `lstsq`, for the cross-asset cases; scipy's `lstsq` and `lsq_linear` on every subset for selection. The mutant the selection suite catches is greedy forward selection, which misses `hedgeselect_i-0009` by 0.5, the pair computed above.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_hedge_20.py` sends `hedge.crossasset.solve` three times and `hedge.select.solve` twice, with the same variants, to the CLI you name and prints the same seven lines. It uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_hedge_20.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_hedge_20.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_hedge_20.py cpp26/build/quantforge
```

Each prints the seven lines of step 1, digit for digit. The full checks are the conformance suites `hedgexa_i` and `hedgeselect_i`.

## For practitioners

- **Units matter for the singularity test.** The rank test is relative but not scale-free (I-22), so give zero-coupon bonds a `notional` that puts their risk on the same scale as the other instruments. That is why the example uses 1 million.
- **One curve.** The equity options are discounted and forwarded on one curve with a flat dividend yield. A desk would separate the projection of the equity forward (repo, borrow, dividends) from discounting.
- **Weights.** Equal weights treat an index-point EQ01 and a basis-point KR01 as the same unit of risk. Scale them to what you can tolerate, or to the variance of each factor's moves; a heavy equity weight drives the equity residual to zero at the cost of the rates (golden `hedgexa_i-0004`).
- **Selection is a search, not a formula.** Exhaustive search is exact and cheap at 20 instruments. Larger universes need a mixed-integer QP solver, which this project does not have.
- **The risk matrix is not an output.** To add bounds or whole contracts, pass the book's risk and your own matrix to `hedge.qp.solve` or `hedge.integer.solve` (spec question Q-I8).

## Common mistakes

- **Expecting a bond to hedge a pillar it does not touch.** A zero-coupon bond at a pillar moves only with that pillar; between two pillars it splits linearly.
- **A maturity past the last pillar.** It is `E_INPUT`; the curve is not extrapolated (I-20).
- **Trusting greedy selection.** It keeps the first instrument it picks, and the best pair need not contain it.
- **Asking for exactly `K` instruments.** `max_instruments` is at most `K`: adding an instrument never makes the objective worse, so the best `K` may use fewer.

## What you just did

You measured an equity book's equity and key-rate risks together, hedged them in one solve, found the pillars the hedge instruments could not reach, closed one with another bond, compared with an equity-only hedge, and saw exhaustive selection find a pair that greedy selection misses. Python, Rust, Java and C++ gave the same digits.

## Try next

- Replace the `UNDERLYING` hedge with a one-year index forward, `{"instrument": "FORWARD", "strike": 4000.0, "expiry_years": 1.0}`: you need 32.11 forwards instead of 31.63 units of the index (a forward's EQ01 is `e^{-qT}` times the index's), and the 1-year residual turns from -6.20 to +6.26, because the forward brings 1-year rate risk that no hedge instrument can offset.
- With the forward hedge above, give the 1-year KR01 a weight of 100 and watch the solver trade equity residual for rate residual.
- Raise `max_instruments` to 3 in the selection example: the answer stays `[1, 2]`, because the search returns the smallest best subset.
- Read [LEARN, stage I: hedging](../../LEARN.md#stage-i-hedging), then go on to [Tutorial 21](tutorial-21-hedge-costs.md).

## References and further reading

The specs list these as sources; "not opened" there means the spec authors cited them from memory.

- B. Tuckman, A. Serrat, *Fixed Income Securities*, 3rd ed., Wiley, 2011, chapter 5: key-rate exposures and hedging with key-rate bonds. Not opened per the spec; no link given.
- J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 5 (forward prices) and chapter 19 (rho). Not opened per the spec; no link given.
- A. Miller, *Subset Selection in Regression*, 2nd ed., Chapman and Hall/CRC, 2002, [doi:10.1201/9781420035933](https://doi.org/10.1201/9781420035933) (paywalled), chapter 3: exhaustive search, and forward selection missing the best subset.
- scipy, [`lsq_linear`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.lsq_linear.html), the outside check for each subset with bounds.
- This project: [`08-hedging/cross-asset-hedge.md`](../../specifications/08-hedging/cross-asset-hedge.md), [`08-hedging/instrument-selection.md`](../../specifications/08-hedging/instrument-selection.md), rulings in [`stage-i-rulings.md`](../../specifications/stage-i-rulings.md).

Links checked 2026-11-12: the Taylor and Francis DOI for Miller and the scipy page returned HTTP 200, and Crossref confirms the DOI's title.
