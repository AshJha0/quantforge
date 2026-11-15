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
