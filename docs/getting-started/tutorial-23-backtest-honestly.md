# Tutorial 23: backtest honestly: lag, look-ahead, costs, purged cross-validation

The plain idea: a backtest replays a rule on past prices and reports what it would have made. Three things make that number lie. The rule may trade on a price it could not yet have seen (look-ahead). It may trade for free, when every trade pays a spread, a commission and a ticket fee. And when the rule was chosen or fitted on the same data it is scored on, the score measures memory, not skill. This tutorial shows each of the three on twelve bars of data you can check by hand, and the tools QuantForge has against them: an execution lag, a cost attribution that closes exactly, and cross-validation that purges overlapping labels.

You will run one strategy through both backtest engines, split its result into gross P&L and three costs, build a look-ahead canary and watch the lag catch it, split ten labelled observations into folds three ways (plain, purged, purged with an embargo), and count the splits and paths of combinatorial purged cross-validation. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All data is synthetic: the prices and targets are those of golden case `backtest_j-0001`, and the label times those of `purgedcv_j-0001`. It is a teaching example, not a trading claim.

Terms, defined here. A **target** is the position, in units, a rule wants after the close of a bar, computed only from information up to that close. The **lag** is the number of bars between that decision and the trade. **Look-ahead** is any use of information from after the decision. A **label** is what a model is trained to predict, for example the return over the next three bars; its **label window** is the time span it covers. **Purging** removes training observations whose label windows overlap the test period; an **embargo** also removes a few observations just after it.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1.

## Step 1: Python

The script `examples/tutorials/t23_backtest.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t23_backtest.py -->
```python
"""Tutorial 23: a backtest run by both engines, the look-ahead canary, costs and their
attribution, purged k-fold with an embargo, and the combinatorial purged CV counts.

  uv run --project python python examples/tutorials/t23_backtest.py         # Python
  python examples/tutorials/t23_backtest.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-23-backtest-honestly.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command
    prices = [100.0, 101.0, 99.5, 102.0, 103.0, 101.5, 100.0, 104.0, 105.5, 103.0, 106.0, 107.0]
    targets = [1.0, 2.0, -1.0, 0.0, 3.0, 3.0, -2.0, 1.0, 0.0, 2.0, 0.0, 0.0]
    costs = {"half_spread_bps": 5.0, "commission_per_unit": 0.01, "fixed_per_trade": 1.0}

    # 1. One strategy, both engines, lag 1: the same numbers.
    for engine in ("EVENT", "VECTOR"):
        r = call("research.backtest.run", {"prices": prices, "targets": targets, "lag": 1,
                                           "engine": engine, **costs})
        print(f"{engine:<6} positions {' '.join(num(q, 0) for q in r['positions'])}"
              f"  equity end {num(r['equity'][-1], 5)}")

    # 2. The attribution: gross minus the three costs is net, exactly.
    print(f"gross {num(r['total_gross'], 5)} - spread {num(r['total_spread_cost'], 5)}"
          f" - commission {num(r['total_commission'], 5)} - fixed {num(r['total_fixed_cost'], 5)}"
          f" = net {num(r['total_net'], 5)}")
    print(f"trades {r['trade_count']}  turnover {num(r['turnover'], 2)}"
          f"  max drawdown {num(r['max_drawdown'], 5)}")

    # 3. The look-ahead canary: a target that knows the next move.
    peek = [(1.0 if prices[t + 1] > prices[t] else -1.0) for t in range(len(prices) - 1)] + [0.0]
    for lag in (0, 1):
        r = call("research.backtest.run", {"prices": prices, "targets": peek, "lag": lag})
        print(f"canary lag {lag}: gross {num(r['total_gross'], 2)}")

    # 4. Ten observations in three folds: plain k-fold (labels one bar long), then labels spanning
    #    three bars (purged), then the same with a 30 % embargo.
    t0 = list(range(10))
    for label, span, pct in (("plain ", 0, 0.0), ("purged", 2, 0.0), ("+embargo", 2, 0.3)):
        r = call("research.cv.purged_kfold", {"t0": t0, "t1": [t + span for t in t0],
                                              "n_splits": 3, "embargo_pct": pct})
        folds = "  ".join(f"test {f['test'][0]}-{f['test'][-1]} train {','.join(map(str, f['train']))}"
                          for f in r["folds"])
        print(f"{label:<8} {folds}")

    # 5. Combinatorial purged CV: how many splits and backtest paths.
    for n, k in ((6, 2), (10, 2), (10, 3)):
        r = call("research.cv.cpcv_paths", {"n_groups": n, "n_test_groups": k})
        print(f"CPCV N {n} k {k}: splits {r['n_splits']} paths {r['n_paths']}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t23_backtest.py
```

Real output, 2026-11-14, Windows 11:

<!-- tutorial:expect -->
```text
EVENT  positions 0 1 2 -1 0 3 3 -2 1 0 2 0  equity end -4.85975
VECTOR positions 0 1 2 -1 0 3 3 -2 1 0 2 0  equity end -4.85975
gross 6.50000 - spread 1.13975 - commission 0.22000 - fixed 10.00000 = net -4.85975
trades 10  turnover 2279.50  max drawdown 8.87575
canary lag 0: gross 21.00
canary lag 1: gross -10.00
plain    test 0-3 train 4,5,6,7,8,9  test 4-6 train 0,1,2,3,7,8,9  test 7-9 train 0,1,2,3,4,5,6
purged   test 0-3 train 6,7,8,9  test 4-6 train 0,1,9  test 7-9 train 0,1,2,3,4
+embargo test 0-3 train 7,8,9  test 4-6 train 0,1  test 7-9 train 0,1,2,3,4
CPCV N 6 k 2: splits 15 paths 5
CPCV N 10 k 2: splits 45 paths 9
CPCV N 10 k 3: splits 120 paths 36
```

### Reading the numbers

- **Two engines, one answer.** The `EVENT` engine walks the bars one at a time; `VECTOR` shifts and differences whole arrays. Both hold the target of bar `t - 1` after bar `t` (lag 1), so the positions are the targets moved one bar right, with a 0 in front: 0, 1, 2, -1, and so on. Both end at equity -4.85975, the figure the spec computes line by line for this case.
- **The attribution closes.** 6.5 - 1.13975 - 0.22 - 10 = -4.85975. Check two pieces by hand. Ten trades at a fixed fee of 1 cost 10. The commission is 0.01 per unit on 22 units traded (1 + 1 + 3 + 1 + 3 + 0 + 5 + 3 + 1 + 2 + 2), which is 0.22. A rule that made 6.5 before costs lost 4.86 after them, mostly to the ticket fee: on a strategy this small, the fixed cost decides the sign.
- **Turnover and drawdown.** Turnover is the money value traded, `sum |d_t| p_t`, 2,279.50. The worst fall from a peak of equity is 8.87575, from 3.143 after bar 7 to -5.73275 after bar 10.
- **The canary.** The rule "+1 if the next close is higher, else -1" uses tomorrow's price today. At lag 0 it holds the right sign over every bar and its gross P&L is the sum of the absolute moves: 1 + 1.5 + 2.5 + 1 + 1.5 + 1.5 + 4 + 1.5 + 2.5 + 3 + 1 = 21. At lag 1 the same signal arrives one bar late and loses 10. A real signal does not collapse like that when delayed by a bar; a leaked one does. That is why the spec allows `lag = 0` only so that this canary can be built, and why a study runner refuses it otherwise (ruling J-2).
- **Plain k-fold.** With labels one bar long (`t1 = t0`) the folds are contiguous blocks, 0-3, 4-6 and 7-9 (four, three, three, the numpy `array_split` order), and each fold trains on everything else.
- **Purged.** Now each label spans three bars, `t1 = t0 + 2`. The first test block covers time 0 to 5 (observation 3's label ends at 5), so observations 4 and 5, whose labels start inside that span, are dropped from training. The middle block covers 4 to 8, so 2 and 3 (labels ending at 4 and 5) and 7 and 8 are dropped, leaving 0, 1 and 9. Without the purge, a model would train on labels that share bars with the test labels and score well for that reason alone.
- **Embargo.** A 30 % embargo on ten observations is `floor(0.3 x 10) = 3` indices after each test block. After the first block that removes 4, 5 (already purged) and 6, leaving 7, 8, 9; after the middle block, 7, 8 and 9, leaving 0 and 1. Nothing follows the last block. Observations before a test block are never embargoed, only purged. The embargo stands in for serial correlation that leaks forward past the label window.
- **CPCV counts.** Combinatorial purged CV cuts the data into `N` groups and tests on every choice of `k` of them: `C(6, 2) = 15` splits. Each group is tested in `k C(N, k) / N` splits, so the test pieces join into that many complete backtest paths: 2 x 15 / 6 = 5. With `N = 10`, `k = 3`: `C(10, 3) = 120` splits and 3 x 120 / 10 = 36 paths. One walk-forward test gives one path; CPCV gives a distribution of them.

### The formal statement, checked against the spec

From [`11-research/backtester.md`](../../specifications/11-research/backtester.md) (rulings J-1 to J-6) and [`11-research/purged-cv.md`](../../specifications/11-research/purged-cv.md) (J-7 to J-9).

Backtest, for `t = 0 .. T-1` with `q_{-1} = 0` and multiplier `m`: position `q_t = targets[t - lag]` for `t >= lag`, else 0; trade `d_t = q_t - q_{t-1}`; holding P&L `g_t = q_{t-1} (p_t - p_{t-1}) m` for `t >= 1`, `g_0 = 0`, so the position that earns a bar's move is the one held before that bar's trade; costs `k_t = |d_t| p_t (half_spread_bps / 10^4) m + |d_t| commission_per_unit + fixed_per_trade 1[d_t != 0]`; net `n_t = g_t - k_t` and equity `E_t = sum_{u <= t} n_u`. The totals satisfy `total_gross - total_spread_cost - total_commission - total_fixed_cost = total_net` as an identity, and `VECTOR` must equal `EVENT` to 1e-10 relative (J-3).

Purged k-fold, observations `i = 0 .. n-1` with label windows `[t0_i, t1_i]`: folds are contiguous, the first `n mod k` of them one longer. For a test block `[a, b)` the span is `[lo, hi] = [t0_a, max t1_i]` over the block; a training observation `j` is purged when `t0_j <= hi` and `t1_j >= lo` (touching counts); the embargo drops indices `b .. b + h - 1` with `h = floor(embargo_pct n)` (J-8). CPCV: `n_splits = C(N, k)`, `n_paths = k C(N, k) / N`, always an integer because `k C(N, k) = N C(N-1, k-1)` [LdP18, section 12.4].

The checks behind the goldens: the ten-trade example and the purged-CV example are hand calculations in the spec; outside libraries reproduce all 14 value-checked `backtest_j` cases (vectorbt 1.2.1; the other 9 of the 23 are error cases) and 12 of the 15 value-checked `purgedcv_j` cases (timeseriescv, scikit-learn, skfolio), ruling J-19a.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t23_backtest.py` sends the same cases (four `research.backtest.run`, three `research.cv.purged_kfold`, three `research.cv.cpcv_paths`) to whichever CLI you name and prints the same lines. Given a command line, the script sends each case to that build's `batch` command (`specifications/cli-contract.md`) instead of the Python package.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t23_backtest.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t23_backtest.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t23_backtest.py cpp26/build/quantforge
```

Each prints the twelve lines of step 1, digit for digit. The full checks are `python conformance/runner/runner.py --impl rust --suite backtest_j` and `--suite purgedcv_j`.

## For practitioners

- **Lag 1 is a floor, not a safe default.** It assumes you can trade at the close after the one you decided on. A daily rule computed after the close usually trades the next open, which this backtester does not model; on bar closes, use the lag your real order timing allows.
- **Costs are inputs.** Nothing here estimates spread or commission from data. Use the costs you actually pay, and rerun with them doubled: a result that changes sign is not a result.
- **One instrument per call.** A portfolio is the sum of calls; there is no borrow cost, financing, dividend or partial fill (stage H adds impact and queue fills).
- **Purge by the label, not the feature.** The window that matters is the one the target covers. A 20-day forward return needs 20 days of purge whatever the feature's look-back.
- **Survivorship sits outside.** The backtester sees only the prices you give it; a study must say which universe it drew them from and whether delisted names are in it.

## Common mistakes

- **Computing the target with the bar's close and trading at the same close.** That is `lag = 0`, the canary.
- **Reading `total_gross` as the result.** Read `total_net`, and the attribution beside it.
- **Shuffling before k-fold.** Shuffled folds put neighbouring, overlapping labels on both sides of the split; QuantForge's folds are contiguous on purpose (ruling J-7).
- **Embargoing before the test block.** Information leaks forward in time, so the embargo is after the block; the purge handles overlap on both sides.
- **Counting CPCV splits as independent tests.** The 15 splits of `N = 6, k = 2` reuse the same data; they give 5 paths, and the paths share training data too.

## What you just did

You ran one strategy through both engines and got the spec's -4.85975, split it into 6.5 of gross P&L and 11.35975 of costs, caught a look-ahead signal that made 21 at lag 0 and lost 10 at lag 1, watched purging and an embargo shrink the training sets, and counted 15 splits and 5 paths for `N = 6, k = 2`. Four implementations printed the same lines. [Tutorial 24](tutorial-24-is-the-sharpe-real.md) asks the next question: is the Sharpe ratio of what is left real?

## Try next

- Double each cost input and confirm each `total_*_cost` doubles exactly (a property test in every language).
- Set `lag` to 2 in the first backtest and see which trades move.
- Give the purged k-fold `n_splits` 5 and an embargo of 0.1, and predict the training sets before running.
- Read [LEARN, stage J](../../LEARN.md#stage-j-backtest-overfitting-and-research-statistics) and the [research workflow page](../curves/research-workflow.md).

## References and further reading

The specs list these as sources; "not opened" there means the spec authors cited them from memory.

- M. Lopez de Prado, *Advances in Financial Machine Learning*, Wiley, 2018, section 7.4 (purging and embargo), chapter 11 (the dangers of backtesting) and section 12.4 (combinatorial purged CV). Not opened per the spec; no link given.
- R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2013, chapter 3: spread, commission and fixed-fee cost components. Not opened per the spec; no link given.
- This project: [`11-research/backtester.md`](../../specifications/11-research/backtester.md), [`11-research/purged-cv.md`](../../specifications/11-research/purged-cv.md), rulings in [`stage-j-rulings-w1.md`](../../specifications/stage-j-rulings-w1.md), all sources in [References](../references.md).
