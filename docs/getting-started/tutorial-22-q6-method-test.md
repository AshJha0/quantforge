# Tutorial 22: a calibration method test on synthetic noisy quotes

<!-- tutorial:only python -->

The plain idea: before fitting a volatility surface to real option quotes, test the whole procedure on quotes where the answer is known. Draw quotes from a surface you chose, spoil them the way real quotes are spoiled (a bid-ask spread, stale quotes, the odd bad print), run the preregistered fit, and check three things: the fit has no arbitrage, it does not jump around from day to day more than the market does, and it stays inside the quoted spreads. This is plan item Q6 built as a **method test**. Real quotes are **not done**: no free source with terms that allow it was found (`research/preregs/Q6-01-churn-bound.md`, section "Data source").

*Label:* synthetic quotes from a known SSVI surface; a method test, not a calibration to real option quotes.

Terms, defined here. **SSVI** is a parametric total-variance surface (Gatheral and Jacquier 2014, "Arbitrage-free SVI volatility surfaces", *Quantitative Finance* 14(1)); its parameters can be constrained so that it has no **calendar arbitrage** (total variance rises with expiry at each moneyness) and no **butterfly arbitrage** (Durrleman's condition `g(k) >= 0`, which keeps the implied density non-negative). **Churn** `C_t` is the root-mean-square day-on-day change of the fitted surface on a fixed grid; the **churn ratio** `R_t` divides it by the move of the at-the-money volatility, so a pure level shift scores about 1. All three, and the bounds, are fixed in the prereg `Q6-01` before any fit was run.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python` (the tool uses numpy and scipy).
- About two minutes: 60 synthetic days are fitted six times on the selection sample and once on the test sample.

The tool is `research/q6/q6_method_test.py`, in Python only: it is research tooling, not a library operation, so this page has no Rust, Java or C++ step.

## Step 1: run the preregistered procedure

<!-- tutorial:run python -->
```python
import sys

sys.path.insert(0, "research/q6")
import q6_method_test as q

out = q.main(days=60, seed=20261112)
for t in out["trials"]:
    print(f"selection lambda {t['lambda']:>4}: inside spread {t['inside_share']:.2f}, median R {t['median_R']:.2f}, p95 R {t['p95_R']:.2f}")
print(f"chosen lambda {out['chosen_lambda']}")
print(f"test: median R {out['test_median_R']:.2f} (bound 1.5), p95 R {out['test_p95_R']:.2f} (bound 3.0)")
print(f"test: inside spread {out['test_inside_share']:.3f} (bound 0.800)")
print(f"test: calendar-free days {out['calendar_free_days']}/{out['test_days']}, butterfly-free days {out['butterfly_free_days']}/{out['test_days']}")
print(f"rms error to the true surface on the grid: {out['rms_error_to_truth_on_grid_vol'] * 100:.2f} vol points")
print(f"result: {out['result']}")
```

It prints:

<!-- tutorial:expect -->
```text
selection lambda    0: inside spread 0.85, median R 0.99, p95 R 1.54
selection lambda  0.1: inside spread 0.62, median R 0.95, p95 R 1.67
selection lambda  0.3: inside spread 0.47, median R 0.93, p95 R 1.50
selection lambda    1: inside spread 0.35, median R 0.78, p95 R 1.05
selection lambda    3: inside spread 0.31, median R 0.45, p95 R 0.82
selection lambda   10: inside spread 0.27, median R 0.17, p95 R 0.29
chosen lambda 0
test: median R 0.99 (bound 1.5), p95 R 1.64 (bound 3.0)
test: inside spread 0.784 (bound 0.800)
test: calendar-free days 48/48, butterfly-free days 48/48
rms error to the true surface on the grid: 0.20 vol points
result: FAIL
```

## Step 2: read the result

- **Arbitrage: passes.** Every one of the 48 test days is free of calendar and butterfly arbitrage on the prereg grid, to 1e-10. That is by construction: the fit uses SSVI with the no-arbitrage constraints built into its parameters (theta increments are squares; `eta (1 + |rho|) < 2`), so "arbitrage repair" is a property of the model rather than a step after the fit. The check itself is shown failing on planted calendar and butterfly faults in `research/q6/test_q6_method_test.py`.
- **Churn: passes.** Median `R_t` 0.99 and 95th percentile 1.64, against bounds of 1.5 and 3.0. With no penalty (`lambda = 0`) the fitted surface already moves about as much as the true one.
- **Fit quality: fails, narrowly.** 78.4% of test quotes are inside their spread, against a bound of 80%. The noise was drawn with standard deviation `h/2`, so about 95% of honest quotes fall inside `h`; 10% stale quotes and 2% outliers take that down to the low 80s before any model error. The bound is close to what this noise model allows, and the run lands just below it. Under the prereg rule (all of rules 3, 4 and 5), the method test **fails**, and that is reported here with the same prominence as a pass would be. The bound was not changed and the seed was not rerun. Owner decision, 2026-11-12: Q6-01 stays published as a failed method test and is not re-run or tuned; a redesigned test, with a new preregistration and fresh synthetic data, is scheduled for stage J (plan row J-11).
- **The penalty scale.** Every non-zero `lambda` in the prereg grid costs fit quality fast: at `lambda = 0.1` only 62% of selection quotes are inside the spread. The prereg's penalty divides churn by 0.001 (0.1 vol point), which makes it large next to the quote term. A future prereg could use a smaller grid; this one cannot be changed.
- **Against the truth.** The fit is 0.20 vol points from the true surface on average over the grid: close, because the model family contains the truth. Real quotes give no such check.

## Limits

- One noise model, one seed, one model family that contains the truth: a method test shows the procedure works where it should; it says nothing about real quotes.
- Quotes are in volatility, so the prereg's price error over half-spread is taken in volatility; the two agree to first order through vega.
- Real option quotes stay **not done** until a source with suitable terms, or written consent, is approved by the owner.

Next: back to the [tutorial list](README.md).
