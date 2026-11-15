# Tutorial 31: leakage and how purging removes it

The plain idea: when a label looks ahead in time, such as "the return over the next 20 days", ordinary k-fold cross-validation cheats. A training observation from just before the test block has a label that ends inside the test block, so the model is trained on part of the answer. Purging removes every training observation whose label window overlaps the test labels; the embargo removes a few more just after the test block. The price is a smaller training set, and that price grows with the label horizon. This tutorial measures both: how much leakage plain k-fold lets through, and how much data purging costs.

You will split 100 labelled observations into five folds for label horizons of 0, 5 and 20 bars, with and without a 2 % embargo, count the training labels that overlap each test span (always zero after purging), count them for plain k-fold (160), and print the split and path counts of combinatorial purged cross-validation for three group counts. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 10 minutes. The data is only index arithmetic; no prices are involved.

Terms, defined here. Observation `i` has a **label window** `[t0_i, t1_i]`: the label is decided at `t0_i` and known only at `t1_i`. The **horizon** is `t1 - t0`. A training label **leaks** when its window overlaps the span from the first test label's `t0` to the last test label's `t1`. The **embargo** drops the `floor(embargo_pct x n)` observations right after the test block. **CPCV** (combinatorial purged cross-validation) splits the data into `N` groups and tests on every choice of `k` of them.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 23](tutorial-23-backtest-honestly.md) shows the spec's ten-observation hand example and is useful first.

## Step 1: Python

The script `examples/tutorials/t31_purging.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t31_purging.py -->
```python
"""Tutorial 31: leakage and how purging removes it. Training-set sizes as the label horizon and
the embargo grow, a check that no training label overlaps the test span, and a table of CPCV counts.

  uv run --project python python examples/tutorials/t31_purging.py         # Python
  python examples/tutorials/t31_purging.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-31-leakage-and-purging.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import sys

from qf import connect


def leaks(t0, t1, fold):
    # A training label leaks when its window [t0, t1] overlaps the span of the test labels.
    lo = min(t0[i] for i in fold["test"])
    hi = max(t1[i] for i in fold["test"])
    return sum(1 for i in fold["train"] if t0[i] <= hi and t1[i] >= lo)


def main(cli):
    call = connect(cli)
    n, k = 100, 5
    t0 = list(range(n))

    # 1. Labels that look h bars ahead, 5 folds, no embargo then a 2 % embargo.
    for h in (0, 5, 20):
        t1 = [t + h for t in t0]
        for embargo in (0.0, 0.02):
            r = call("research.cv.purged_kfold", {"t0": t0, "t1": t1, "n_splits": k, "embargo_pct": embargo})
            sizes = [len(f["train"]) for f in r["folds"]]
            leaked = sum(leaks(t0, t1, f) for f in r["folds"])
            print(f"horizon {h:>2} embargo {embargo:.2f}: train sizes {sizes}  embargo_count"
                  f" {r['embargo_count']}  leaking labels {leaked}")

    # 2. What plain k-fold would have kept: the same split with the purge undone (t1 = t0).
    t1 = [t + 20 for t in t0]
    plain = call("research.cv.purged_kfold", {"t0": t0, "t1": t0, "n_splits": k})
    print(f"plain 5-fold with 20-bar labels: leaking labels {sum(leaks(t0, t1, f) for f in plain['folds'])}")

    # 3. Combinatorial purged CV: C(N, k) splits and k/N C(N, k) backtest paths.
    for groups in (6, 8, 10):
        row = []
        for test_groups in (1, 2, 3):
            r = call("research.cv.cpcv_paths", {"n_groups": groups, "n_test_groups": test_groups})
            assert r["n_splits"] == math.comb(groups, test_groups)
            assert r["n_paths"] * groups == test_groups * r["n_splits"]
            row.append(f"k={test_groups}: {r['n_splits']:>3} splits {r['n_paths']:>2} paths")
        print(f"N={groups:>2}  " + "   ".join(row))


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t31_purging.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
horizon  0 embargo 0.00: train sizes [80, 80, 80, 80, 80]  embargo_count 0  leaking labels 0
horizon  0 embargo 0.02: train sizes [78, 78, 78, 78, 80]  embargo_count 2  leaking labels 0
horizon  5 embargo 0.00: train sizes [75, 70, 70, 70, 75]  embargo_count 0  leaking labels 0
horizon  5 embargo 0.02: train sizes [75, 70, 70, 70, 75]  embargo_count 2  leaking labels 0
horizon 20 embargo 0.00: train sizes [60, 40, 40, 40, 60]  embargo_count 0  leaking labels 0
horizon 20 embargo 0.02: train sizes [60, 40, 40, 40, 60]  embargo_count 2  leaking labels 0
plain 5-fold with 20-bar labels: leaking labels 160
N= 6  k=1:   6 splits  1 paths   k=2:  15 splits  5 paths   k=3:  20 splits 10 paths
N= 8  k=1:   8 splits  1 paths   k=2:  28 splits  7 paths   k=3:  56 splits 21 paths
N=10  k=1:  10 splits  1 paths   k=2:  45 splits  9 paths   k=3: 120 splits 36 paths
```

### Reading the numbers

- **Horizon 0 is plain k-fold.** Each fold tests 20 observations and trains on the other 80. A 2 % embargo of 100 observations is `floor(0.02 x 100) = 2`, removed after the test block, so the first four folds train on 78; the last fold has nothing after it and keeps 80.
- **Horizon 5.** The first and last folds lose 5 observations, the ones whose label windows reach into the test span from one side; the middle folds lose 10, five on each side: fold 1 tests 20 to 39, whose labels span bars 20 to 44, so indices 15 to 19 (windows ending at 20 to 24) and 40 to 44 (starting before 44) are purged. The 2 % embargo changes nothing here, because the two indices it would drop are already purged.
- **Horizon 20.** Purging removes 20 observations on each side of a middle test block: those folds train on 40 of 100. Fold 0 (test 0 to 19, labels spanning 0 to 39) keeps indices 40 to 99, so 60. With long labels and five folds, purging costs up to 60 % of the training data. That is the honest price of overlapping labels, not a defect.
- **Leakage after purging is zero** in all six runs: the script checks every training label of every fold against its test span.
- **Plain k-fold leaks 160 labels** with 20-bar labels: 20 in each end fold and 40 in each of the three middle folds (20 before the block, 20 after). Every one of them gives the model part of a test label.
- **CPCV counts.** Testing on `k` of `N` groups gives `C(N, k)` splits, and each group is tested in `C(N - 1, k - 1)` of them, which is `k/N C(N, k)` backtest paths. `N = 6, k = 2`: 15 splits and 5 paths; `N = 10, k = 3`: 120 splits and 36 paths. The script asserts both identities for every entry.

### The formal statement, checked against the spec

From [`11-research/purged-cv.md`](../../specifications/11-research/purged-cv.md) (rulings J-7 to J-9 in [`stage-j-rulings-w1.md`](../../specifications/stage-j-rulings-w1.md)). The `n` observations are split into `k` contiguous test blocks (the first `n mod k` blocks one longer, no shuffling, ruling J-7). For a test block `[a, b)` with label span `[lo, hi] = [t0_a, max t1_i over the block]`, a training index `i` is purged when `t0_i <= hi` and `t1_i >= lo`. The embargo `h = floor(embargo_pct x n)` (ruling J-8) also drops indices `b .. b + h - 1`, the indices just after the block; observations before the block are not embargoed. With `t1 = t0` and `embargo_pct = 0` the result equals plain contiguous k-fold. `research.cv.cpcv_paths` returns `n_splits = C(N, k)` and `n_paths = k/N C(N, k)` [LdP18, section 12.4].

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t31_purging.py` sends the same cases (seven `research.cv.purged_kfold`, nine `research.cv.cpcv_paths`) to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t31_purging.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t31_purging.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t31_purging.py cpp26/build/quantforge
```

Each is to print the ten lines of step 1, digit for digit. The full check is `python conformance/runner/runner.py --impl rust --suite purgedcv_j`.

## For practitioners

- **Set `t1` from how the label is really built.** A 20-day forward return known at the close of day 20 has `t1 = t0 + 20`; using `t0 + 19` lets one day leak.
- **Size the folds with the horizon in mind.** With a horizon of `h` bars, each middle fold loses about `2h` training observations; with few observations and long labels, use fewer, larger folds.
- **The embargo is for serial correlation beyond the label.** If features are built from long moving windows, the embargo should cover that window too.
- **CPCV gives many paths from one data set.** That is what makes a distribution of out-of-sample Sharpe ratios possible, and the input to PBO in [Tutorial 24](tutorial-24-is-the-sharpe-real.md).

## Common mistakes

- **Shuffling before splitting.** Purging assumes time order; a shuffled split makes every fold overlap every other.
- **Purging only one side.** Labels before the test block leak into it just as test labels leak into training data after it.
- **Comparing models trained on different fold sizes.** Longer horizons shrink the training set; compare models at the same horizon or say what changed.
- **Expecting the embargo to add to the purge.** When the horizon already covers the embargo, it removes nothing more, as the horizon-5 and horizon-20 lines show.

## What you just did

You measured the training data purging costs at three label horizons, up to 60 % for 20-bar labels and five folds, confirmed that no purged split leaks, counted the 160 leaking labels of plain k-fold, saw the embargo absorbed by the purge for longer labels, and tabulated CPCV splits and paths.

## Try next

- Change the horizon to 10 and predict the training sizes before running it.
- Use three folds instead of five with 20-bar labels and compare the share of data kept.
- Find the smallest `N` for which CPCV with `k = 2` gives at least 10 paths.

## References and further reading

- M. Lopez de Prado, *Advances in Financial Machine Learning*, Wiley, 2018, section 7.4 (purging and embargo) and section 12.4 (combinatorial purged cross-validation). Not opened per the spec; formulas re-derived by hand there.
- This project: [`11-research/purged-cv.md`](../../specifications/11-research/purged-cv.md), [Tutorial 23](tutorial-23-backtest-honestly.md), all sources in [References](../references.md).
