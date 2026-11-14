"""Tutorial 26: test an expected-shortfall model with the Acerbi-Szekely Z2 statistic, then fit a
two-state regime model by Baum-Welch and label the days with Viterbi.

  uv run --project python python examples/tutorials/t26_es_regimes.py         # Python
  python examples/tutorials/t26_es_regimes.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-26-test-es-and-fit-regimes.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(x, places) for x in values)


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command

    # 1. Twenty daily losses (positive = loss). Two days break a VaR of 2.0; at alpha = 10 % two are expected.
    losses = [0.4, -0.3, 1.1, 0.2, -0.8, 2.5, 0.6, -1.2, 0.9, 1.5,
              -0.5, 0.3, 1.8, -0.2, 0.7, 3.5, -0.9, 0.1, 1.2, -0.4]
    n, alpha = len(losses), 0.10
    r = call("risk.backtest.kupiec", {"observations": n, "exceptions": 2, "confidence": 1 - alpha})
    print(f"Kupiec, 2 exceptions in {n}: LR {num(r['lr_uc'], 4)}  p-value {num(r['p_value'], 4)}")
    # Three models, the same VaR, different ES forecasts.
    for name, es in (("ES 3.0", 3.0), ("ES 2.2", 2.2), ("ES 4.0", 4.0)):
        r = call("risk.backtest.es_z2", {"losses": losses, "var": [2.0] * n, "es": [es] * n, "alpha": alpha})
        print(f"Z2 {name}: z2 {num(r['z2'], 4)}  exceptions {r['exceptions']}"
              f"  expected {num(r['expected_exceptions'], 1)}")
    # A model whose ES moves with its VaR: the forecasts double on the last ten days.
    var = [1.5] * 10 + [3.0] * 10
    es = [2.0] * 10 + [4.0] * 10
    r = call("risk.backtest.es_z2", {"losses": losses, "var": var, "es": es, "alpha": alpha})
    print(f"Z2 moving forecasts: z2 {num(r['z2'], 4)}  exceptions {r['exceptions']}")

    # 2. Baum-Welch. Twenty-four daily returns, in percent, with two turbulent spells.
    returns = [0.3, -0.2, 0.4, 0.1, -2.5, 3.1, -1.8, 2.2, 0.2, -0.3, 0.1, 0.4,
               -0.5, 0.6, 0.2, -0.1, 1.9, -2.8, 2.4, -1.5, 0.3, 0.0, -0.4, 0.5]
    one = call("research.regime.baum_welch", {"observations": returns, "initial": [1.0],
                                              "transition": [[1.0]], "means": [0.0], "sds": [1.0]})
    print(f"one state: mean {num(one['means'][0], 4)}  sd {num(one['sds'][0], 4)}"
          f"  log-likelihood {num(one['log_likelihood'], 4)}  iterations {one['iterations']}")
    start = {"observations": returns, "initial": [0.5, 0.5], "transition": [[0.9, 0.1], [0.2, 0.8]],
             "means": [0.0, 0.0], "sds": [0.5, 2.0], "tolerance": 1e-6}
    short = call("research.regime.baum_welch", {**start, "max_iterations": 3})
    print(f"two states, 3 iterations: log-likelihood {num(short['log_likelihood'], 4)}"
          f"  converged {short['converged']}")
    fit = call("research.regime.baum_welch", start)
    print(f"two states: iterations {fit['iterations']}  converged {fit['converged']}"
          f"  log-likelihood {num(fit['log_likelihood'], 4)}")
    print(f"  means {nums(fit['means'], 4)}  sds {nums(fit['sds'], 4)}")
    print(f"  stay calm {num(fit['transition'][0][0], 4)}  stay turbulent {num(fit['transition'][1][1], 4)}"
          f"  initial {nums(fit['initial'], 4)}")

    # 3. Viterbi with the fitted parameters: the most likely state of each day.
    r = call("research.regime.viterbi", {"initial": fit["initial"], "transition": fit["transition"],
                                         "observations": returns, "means": fit["means"], "sds": fit["sds"]})
    print(f"Viterbi path {''.join(map(str, r['states']))}  log probability {num(r['log_probability'], 4)}")


if __name__ == "__main__":
    main(sys.argv[1:])
