# Review request: Research workflow: backtest to PBO (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage J). Evidence line from the project's status table: 83 golden cases for the backtest, purged CV and research statistics, 31 reproduced by an outside library; synthetic prices, a teaching example.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.

## Spec

### `specifications/11-research/backtester.md`

# Backtester: event loop, order and fill model, costs, P&L and attribution

Spec version 1.0.0. Status: Implemented (stage J, wave 1) in Python, Rust, Java and C++ (wave 1 contract 1.13.0, now 1.14.0); every build passes all its cases (15,315 of 15,315, 2026-11-14). Rulings: `stage-j-rulings-w1.md` J-1 to J-6. Suite in `datasets/golden/stage_j/`: `backtest_j`, written by `oracle/python/gen_stage_j_w1.py`. Plan items Q7 and J-3 (plan 12.5, 14.6).

**Plain idea.** A strategy says, at the close of each bar, how many units it wants to hold. The backtester holds that target from a later close (the execution lag), pays costs on every change, and books the price move on what it held over each bar. Every number it reports is a sum of per-bar numbers, so the P&L explain closes exactly.

Sources:
- [LdP18] M. Lopez de Prado, *Advances in Financial Machine Learning*, Wiley, 2018, chapter 11 ("The dangers of backtesting") and chapter 12 (backtesting through cross-validation) (not opened in this session; used for the look-ahead and lag discussion only, no number is taken from it). Evidence class: textbook, recalled.
- [Kis93] R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2013, chapter 3 (half-spread, commission and fixed-fee cost components) (not opened). Evidence class: textbook, recalled.
- Hand check: the ten-trade example below, computed line by line, equals `backtest_j-0001` and `-0002` exactly (the generator works in rational arithmetic). Evidence class: hand calculation.

## Common rules

- Check order: `E_PARSE`, `E_SCHEMA` (an `engine` value not listed), `E_LIMIT` (bars, J-5), the finite rule F-2 (`E_DOMAIN`), then the checks below. F-3 (negative zero) holds.
- Time is the bar index `t = 0 .. T-1`. Prices are closes. No calendar is used; bar spacing is the caller's.
- Determinism: the outputs are sums and products of the inputs in a fixed order; there is no randomness and no iteration.

## `research.backtest.run`

### Inputs

- `prices` (length `T >= 2`, each `> 0`): close of each bar.
- `targets` (length `T`): the position, in units, the strategy wants after the close of bar `t`, computed with information up to that close.
- `lag` (Integer, default 1, `0 <= lag < T`): bars between decision and execution. `lag = 0` executes at the same close as the decision; it is allowed only so that a look-ahead canary can be built (ruling J-2).
- `half_spread_bps` (default 0, `>= 0`), `commission_per_unit` (default 0, `>= 0`), `fixed_per_trade` (default 0, `>= 0`).
- `multiplier` (default 1, `> 0`): money per unit per unit of price.
- `engine` (`EVENT` default, or `VECTOR`): both engines must return the same outputs (J-3).

### Checks, in order

1. `len(targets) != T`, `T < 2`, `lag < 0` or `lag >= T`: `E_INPUT`.
2. A price `<= 0`, a negative cost input, or `multiplier <= 0`: `E_DOMAIN`.

### Event loop (normative definition)

With `q_{-1} = 0`, for `t = 0 .. T-1`:
1. Position held after bar `t`'s close: `q_t = targets[t - lag]` for `t >= lag`, else `0`.
2. Trade at the close of bar `t`: `d_t = q_t - q_{t-1}`. It fills in full at `p_t` plus or minus the half spread (no partial fills, no queue; the fill model of stage H replaces this later, ruling J-1).
3. Holding P&L over bar `t`: `g_t = q_{t-1} (p_t - p_{t-1}) m` for `t >= 1`, `g_0 = 0`. The position that earns bar `t`'s move is the one held **before** the bar's trade.
4. Costs: spread `s_t = |d_t| p_t (half_spread_bps / 10^4) m`; commission `c_t = |d_t| commission_per_unit`; fixed `f_t = fixed_per_trade` if `d_t != 0`, else 0. Cost `k_t = s_t + c_t + f_t`.
5. Net `n_t = g_t - k_t`; equity `E_t = sum_{u <= t} n_u`.

The `VECTOR` engine computes the same quantities as whole arrays (shifted targets, differences, element-wise products, cumulative sum). It must equal `EVENT` to 1e-10 relative on every output (J-3), which holds trivially when both follow the definition above.

### Outputs

- Per bar (length `T`): `positions` (`q_t`), `trades` (`d_t`), `pnl_gross` (`g_t`), `cost` (`k_t`), `pnl_net` (`n_t`), `equity` (`E_t`).
- Totals (attribution): `total_gross`, `total_spread_cost`, `total_commission`, `total_fix

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

### `specifications/11-research/purged-cv.md`

# Purged and embargoed k-fold cross-validation; combinatorial purged CV counts

Spec version 1.0.0. Status: Implemented (stage J, wave 1) in Python, Rust, Java and C++ (wave 1 contract 1.13.0, now 1.14.0); every build passes all its cases (15,315 of 15,315, 2026-11-14). Rulings: `stage-j-rulings-w1.md` J-7 to J-9. Suite: `datasets/golden/stage_j/purgedcv_j`, written by `oracle/python/gen_stage_j_w1.py`. Plan item A1 (plan 12.5).

**Plain idea.** In finance a label (for example a 5-day forward return) spans time. Plain k-fold lets a training label overlap the test period, so the model learns the answer. Purging drops every training observation whose label window overlaps the test window; the embargo also drops a few observations right after the test block, because serial correlation leaks information forward.

Sources:
- [LdP18] M. Lopez de Prado, *Advances in Financial Machine Learning*, Wiley, 2018, section 7.4 (purging and embargo, `getTrainTimes`, `getEmbargoTimes`, `PurgedKFold`) and section 12.4 (combinatorial purged CV: `C(N, k)` splits and `phi = k/N C(N, k)` paths) (not opened in this session; formulas recalled and re-derived by hand). Evidence class: textbook, recalled.
- Hand check: the 10-observation example below equals `purgedcv_j-0001`. The CPCV count `N = 6, k = 2` gives 15 splits and 5 paths, the figure used in [LdP18] section 12.4. Evidence class: hand calculation.

## `research.cv.purged_kfold`

### Inputs

- `t0`, `t1` (length `n`): start and end time of each observation's label, Reals or Integers in one unit; `t0` non-decreasing (the observations are in time order).
- `n_splits` (Integer `k`, `2 <= k <= n`).
- `embargo_pct` (default 0, `0 <= embargo_pct < 1`).

### Checks, in order

`E_LIMIT` (`n` above 1,000,000, J-9); F-2; lengths differ, `k` out of range, or `t0` decreasing: `E_INPUT`; a `t1_i < t0_i` or `embargo_pct` outside `[0, 1)`: `E_DOMAIN`.

### Definition

- Folds are contiguous index blocks: fold `f` has `floor(n/k) + 1` observations if `f < n mod k`, else `floor(n/k)` (numpy `array_split` order; no shuffling, ruling J-7).
- For test block `[a, b)`: test span `[lo, hi] = [t0_a, max_{a <= i < b} t1_i]`.
- Purge: training observation `j` (outside the block) is dropped when its label overlaps the span, `t0_j <= hi` and `t1_j >= lo` (closed intervals: touching counts as overlap).
- Embargo: `h = floor(embargo_pct * n)` (ruling J-8); indices `b .. b + h - 1` are also dropped. Observations before the test block are not embargoed.
- Training set: every other index, ascending.

### Outputs

`folds`: list of `k` objects `{test, train}` with ascending integer index lists; `embargo_count`: `h`.

### Worked example (`purgedcv_j-0001`)

`t0 = 0..9`, `t1 = t0 + 2`, `k = 3`, embargo 0.1 so `h = 1`. Fold 0 tests 0..3, span `[0, 5]`: 4 and 5 overlap and are purged; `b = 4`, so the embargo is index 4 (already purged); train = 6, 7, 8, 9. Fold 1 tests 4..6, span `[4, 8]`: 2, 3, 7, 8 overlap; embargo index 7; train = 0, 1, 9. Fold 2 tests 7..9, span `[7, 11]`: 5, 6 overlap; nothing after the block; train = 0..4.

### Property tests

- No training label window overlaps the test span (A1 acceptance).
- With `t1 = t0` and `embargo_pct = 0` the result equals plain contiguous k-fold.
- Planted leak (A1 acceptance, Python research lane): a feature equal to the label shifted inside the label window scores high under plain k-fold and near zero under purged k-fold.

## `research.cv.cpcv_paths`

Inputs `n_groups` (`N`, `2 <= N <= 64`) and `n_test_groups` (`k`, `1 <= k < N`), Integers. Outputs `n_splits = C(N, k)` and `n_paths = k C(N, k) / N` (always an integer, since `k C(N,k) = N C(N-1,k-1)`). Errors: `E_LIMIT` for `N > 64`; `E_INPUT` otherwise out of range. Example: `N = 6, k = 2` gives 15 and 5.

## Limitations

Index purging only; time-based embargo in calendar units is left to the caller (convert to an index count first). Walk-forward splits are the special case of one test block per step and are built in the research package, not as a CLI operation.


### `specifications/11-research/research-statistics.md`

# Research statistics: probabilistic and deflated Sharpe ratio, PBO by CSCV, power

Spec version 1.0.0. Status: Implemented (stage J, wave 1) in Python, Rust, Java and C++ (wave 1 contract 1.13.0, now 1.14.0); every build passes all its cases (15,315 of 15,315, 2026-11-14). Rulings: `stage-j-rulings-w1.md` J-13 to J-18. Suite: `datasets/golden/stage_j/rstats_j`, written by `oracle/python/gen_stage_j_w1.py`. Plan 11.3 (every study reports DSR and PBO), Q7, J-1.

**Plain idea.** A backtest Sharpe ratio is an estimate, and the best of many tried strategies is biased upward. The probabilistic Sharpe ratio (PSR) is the probability that the true Sharpe exceeds a benchmark, allowing for sample length, skew and fat tails. The deflated Sharpe ratio (DSR) is the PSR against the Sharpe the best of `N` useless strategies would show by luck. PBO asks a different question: how often does the in-sample winner rank in the bottom half out of sample? The power calculation says how large a Sharpe a study can detect at all.

Sources:
- [BLdP12] D. H. Bailey, M. Lopez de Prado, "The Sharpe ratio efficient frontier", *Journal of Risk* 15(2), 2012, 3-44 (PSR) (not opened in this session). Evidence class: paper, recalled.
- [BLdP14] D. H. Bailey, M. Lopez de Prado, "The deflated Sharpe ratio: correcting for selection bias, backtest overfitting and non-normality", *Journal of Portfolio Management* 40(5), 2014, 94-107 (DSR formula and the worked example: `SR = 2.5` annualised, `T = 1250` daily returns, skew `-3`, kurtosis `10`, `N = 100` trials, variance of the trials' annualised Sharpe `0.5`; printed `SR0 = 0.1132` per period and `DSR = 0.9004`). Paper read 2026-11-13 (author copy, davidhbailey.com, SSRN 2460551 version), section "A numerical example", pp. 9-10: `N = 100`, `V = 1/2`, `T = 1250`, skew `-3`, kurtosis `10`, `SR = 2.5` annualised over 250 days a year; printed `SR0 ~ 0.1132` (per period), `DSR ~ 0.9004 < 0.95`; also `N = 46` gives `0.9505`, and normal returns (skew 0, kurtosis 3) with `N = 88` give `0.9505`. All four digits reproduced by `rstats_j-0001`, `-0036` and `-0037`; no discrepancy. Evidence class: paper read.
- [BBLdPZ17] D. H. Bailey, J. M. Borwein, M. Lopez de Prado, Q. J. Zhu, "The probability of backtest overfitting", *Journal of Computational Finance* 20(4), 2017, 39-69 (CSCV, logits, PBO). Paper read 2026-11-13 (author copy, davidhbailey.com, 34 pp.): the method in section 2 matches steps 1-6 here; its numerical results (PBO 74 % and 0.04 %, pp. 16-17; seasonal strategy 55 % and 13 %, pp. 25-27) come from seeded simulations and real series whose performance matrices are not printed, so no printed-example golden is possible. The hand example below stays the PBO golden. Evidence class: paper read.
- [Lo02] A. W. Lo, "The statistics of Sharpe ratios", *Financial Analysts Journal* 58(4), 2002, 36-52 (iid standard error `sqrt((1 + SR^2/2)/T)`) (not opened). Used in `research/preregs/README.md`; the MDS table there is reproduced by four goldens. Evidence class: paper, recalled; hand calculation.
- [TS11] B. Tuckman, A. Serrat, *Fixed Income Securities: Tools for Today's Markets*, 3rd ed., Wiley, 2011, chapter 4 ("DV01, Duration, and Convexity": price of a par bond and its yield derivative) and chapter 6 ("Empirical Approaches to Risk Metrics and Hedging": the 50:50 butterfly) (not opened; chapter numbers and titles recalled, confirm against the book). Cited by R3-01 amendments 4 and 5 by chapter name; numbers given in `program/R3_A5_REVIEW.md`. Evidence class: textbook, recalled.
- [Fab13] F. J. Fabozzi, *Bond Markets, Analysis, and Strategies*, 8th ed., Pearson, 2013, chapter 4 ("Bond Price Volatility": duration and convexity as measures of interest-rate risk) (not opened; edition and chapter recalled, confirm against the book). Cited by R3-01 amendment 5 by chapter name. Evidence class: textbook, recalled.

## Common rules

- Sharpe ratios in `research.stats.psr` and `.dsr` are **per period** (not annualised): annualise outside. `kurtosis` is the non-excess fourth standardised moment (3 for a normal).
- Check order: `E_PARSE`, `E_SCHEMA`, `E_LIMIT`, F-2, then the checks listed. Normal qu

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

## Golden cases (14 of 53 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"backtest_j-0001","operation":"research.backtest.run","inputs":{"prices":[100.0,101.0,99.5,102.0,103.0,101.5,100.0,104.0,105.5,103.0,106.0,107.0],"targets":[1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0,0.0],"lag":1,"half_spread_bps":5.0,"commission_per_unit":0.01,"fixed_per_trade":1.0,"engine":"EVENT"},"expected":{"status":"ok","outputs":{"positions":[0.0,1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0],"trades":[0.0,1.0,1.0,-3.0,1.0,3.0,0.0,-5.0,3.0,-1.0,2.0,-2.0],"pnl_gross":[0.0,0.0,-1.5,5.0,-1.0,0.0,-4.5,12.0,-3.0,-2.5,0.0,2.0],"cost":[0.0,1.0605,1.05975,1.183,1.0615,1.18225,0.0,1.31,1.18825,1.0615,1.126,1.127],"pnl_net":[0.0,-1.0605,-2.55975,3.817,-2.0615,-1.18225,-4.5,10.69,-4.18825,-3.5615,-1.126,0.873],"equity":[0.0,-1.0605,-3.62025,0.19675,-1.86475,-3.047,-7.547,3.143,-1.04525,-4.60675,-5.73275,-4.85975],"total_gross":6.5,"total_spread_cost":1.13975,"total_commission":0.22,"total_fixed_cost":10.0,"total_net":-4.85975,"turnover":2279.5,"trade_count":10,"max_drawdown":8.87575}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed"]}
{"case_id":"backtest_j-0002","operation":"research.backtest.run","inputs":{"prices":[100.0,101.0,99.5,102.0,103.0,101.5,100.0,104.0,105.5,103.0,106.0,107.0],"targets":[1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0,0.0],"lag":1,"half_spread_bps":5.0,"commission_per_unit":0.01,"fixed_per_trade":1.0,"engine":"VECTOR"},"expected":{"status":"ok","outputs":{"positions":[0.0,1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0],"trades":[0.0,1.0,1.0,-3.0,1.0,3.0,0.0,-5.0,3.0,-1.0,2.0,-2.0],"pnl_gross":[0.0,0.0,-1.5,5.0,-1.0,0.0,-4.5,12.0,-3.0,-2.5,0.0,2.0],"cost":[0.0,1.0605,1.05975,1.183,1.0615,1.18225,0.0,1.31,1.18825,1.0615,1.126,1.127],"pnl_net":[0.0,-1.0605,-2.55975,3.817,-2.0615,-1.18225,-4.5,10.69,-4.18825,-3.5615,-1.126,0.873],"equity":[0.0,-1.0605,-3.62025,0.19675,-1.86475,-3.047,-7.547,3.143,-1.04525,-4.60675,-5.73275,-4.85975],"total_gross":6.5,"total_spread_cost":1.13975,"total_commission":0.22,"total_fixed_cost":10.0,"total_net":-4.85975,"turnover":2279.5,"trade_count":10,"max_drawdown":8.87575}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed"]}
{"case_id":"backtest_j-0003","operation":"research.backtest.run","inputs":{"prices":[100.0,101.0,99.5,102.0,103.0,101.5,100.0,104.0,105.5,103.0,106.0,107.0],"targets":[1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0,0.0],"lag":0,"half_spread_bps":5.0,"commission_per_unit":0.01,"fixed_per_trade":1.0},"expected":{"status":"ok","outputs":{"positions":[1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0,0.0],"trades":[1.0,1.0,-3.0,1.0,3.0,0.0,-5.0,3.0,-1.0,2.0,-2.0,0.0],"pnl_gross":[0.0,1.0,-3.0,-2.5,0.0,-4.5,-4.5,-8.0,1.5,0.0,6.0,0.0],"cost":[1.06,1.0605,1.17925,1.061,1.1845,0.0,1.3,1.186,1.06275,1.123,1.126,0.0],"pnl_net":[-1.06,-0.0605,-4.17925,-3.561,-1.1845,-4.5,-5.8,-9.186,0.43725,-1.123,4.874,0.0],"equity":[-1.06,-1.1205,-5.29975,-8.86075,-10.04525,-14.54525,-20.34525,-29.53125,-29.094,-30.217,-25.343,-25.343],"total_gross":-14.0,"total_spread_cost":1.123,"total_commission":0.22,"total_fixed_cost":10.0,"total_net":-25.343,"turnover":2246.0,"trade_count":10,"max_drawdown":30.217}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"backtest_j-0004","operation":"research.backtest.run","inputs":{"prices":[100.0,101.0,99.5,102.0,103.0,101.5,100.0,104.0,105.5,103.0,106.0,107.0],"targets":[1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0,0.0],"lag":2,"half_spread_bps":5.0,"commission_per_unit":0.01,"fixed_per_trade":1.0},"expected":{"status":"ok","outputs":{"positions":[0.0,0.0,1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0],"trades":[0.0,0.0,1.0,1.0,-3.0,1.0,3.0,0.0,-5.0,3.0,-1.0,2.0],"pnl_gross":[0.0,0.0,0.0,2.5,2.0,1.5,0.0,12.0,4.5,5.0,3.0,0.0],"cost":[0.0,0.0,1.05975,1.061,1.1845,1.06075,1.18,0.0,1.31375,1.1845,1.063,1.127],"pnl_net":[0.0,0.0,-1.05975,1.439,0.8155,0.43925,-1.18,12.0,3.18625,3.8155,1.937,-1.127],"equity":[0.0,0.0,-1.05975,0.37925,1.19475,1.634,0.454,12.454,15.64025,19.45575,21.39275,20.26575],"total_gross":30.5,"total_spread_cost":1.03425,"total_commission":0.2,"total_fixed_cost":9.0,"total_net":20.26575,"turnover":2068.5,"trade_count":9,"max_drawdown":1.18}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"backtest_j-0005","operation":"research.backtest.run","inputs":{"prices":[100.0,101.0,99.5,102.0,103.0,101.5,100.0,104.0,105.5,103.0,106.0,107.0],"targets":[1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0,0.0],"lag":1,"half_spread_bps":0.0,"commission_per_unit":0.0,"fixed_per_trade":0.0},"expected":{"status":"ok","outputs":{"positions":[0.0,1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0],"trades":[0.0,1.0,1.0,-3.0,1.0,3.0,0.0,-5.0,3.0,-1.0,2.0,-2.0],"pnl_gross":[0.0,0.0,-1.5,5.0,-1.0,0.0,-4.5,12.0,-3.0,-2.5,0.0,2.0],"cost":[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0],"pnl_net":[0.0,0.0,-1.5,5.0,-1.0,0.0,-4.5,12.0,-3.0,-2.5,0.0,2.0],"equity":[0.0,0.0,-1.5,3.5,2.5,2.5,-2.0,10.0,7.0,4.5,4.5,6.5],"total_gross":6.5,"total_spread_cost":0.0,"total_commission":0.0,"total_fixed_cost":0.0,"total_net":6.5,"turnover":2279.5,"trade_count":10,"max_drawdown":5.5}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"backtest_j-0006","operation":"research.backtest.run","inputs":{"prices":[100.0,101.0,99.5,102.0,103.0,101.5,100.0,104.0,105.5,103.0,106.0,107.0],"targets":[1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0,0.0],"lag":1,"half_spread_bps":5.0,"commission_per_unit":0.01,"fixed_per_trade":1.0,"multiplier":50.0},"expected":{"status":"ok","outputs":{"positions":[0.0,1.0,2.0,-1.0,0.0,3.0,3.0,-2.0,1.0,0.0,2.0,0.0],"trades":[0.0,1.0,1.0,-3.0,1.0,3.0,0.0,-5.0,3.0,-1.0,2.0,-2.0],"pnl_gross":[0.0,0.0,-75.0,250.0,-50.0,0.0,-225.0,600.0,-150.0,-125.0,0.0,100.0],"cost":[0.0,3.535,3.4975,8.68,3.585,8.6425,0.0,14.05,8.9425,3.585,6.32,6.37],"pnl_net":[0.0,-3.535,-78.4975,241.32,-53.585,-8.6425,-225.0,585.95,-158.9425,-128.585,-6.32,93.63],"equity":[0.0,-3.535,-82.0325,159.2875,105.7025,97.06,-127.94,458.01,299.0675,170.4825,164.1625,257.7925],"total_gross":325.0,"total_spread_cost":56.9875,"total_commission":0.22,"total_fixed_cost":10.0,"total_net":257.7925,"turnover":113975.0,"trade_count":10,"max_drawdown":293.8475}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"backtest_j-0007","operation":"research.backtest.run","inputs":{"prices":[10.0,10.0],"targets":[0.0,0.0]},"expected":{"status":"ok","outputs":{"positions":[0.0,0.0],"trades":[0.0,0.0],"pnl_gross":[0.0,0.0],"cost":[0.0,0.0],"pnl_net":[0.0,0.0],"equity":[0.0,0.0],"total_gross":0.0,"total_spread_cost":0.0,"total_commission":0.0,"total_fixed_cost":0.0,"total_net":0.0,"turnover":0.0,"trade_count":0,"max_drawdown":0.0}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"backtest_j-0008","operation":"research.backtest.run","inputs":{"prices":[50.0,51.0,49.0],"targets":[-4.0,-4.0,-4.0]},"expected":{"status":"ok","outputs":{"positions":[0.0,-4.0,-4.0],"trades":[0.0,-4.0,0.0],"pnl_gross":[0.0,0.0,8.0],"cost":[0.0,0.0,0.0],"pnl_net":[0.0,0.0,8.0],"equity":[0.0,0.0,8.0],"total_gross":8.0,"total_spread_cost":0.0,"total_commission":0.0,"total_fixed_cost":0.0,"total_net":8.0,"turnover":204.0,"trade_count":1,"max_drawdown":0.0}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"backtest_j-0009","operation":"research.backtest.run","inputs":{"prices":[100.0,101.4929,101.8441,100.1279,98.9237,100.5606,102.1576,101.3492,99.9701,99.6064,100.4713,101.9599,100.9052,99.4285,99.4861,99.6812,98.7725,98.9213,99.1055,99.9775],"targets":[4.0,-2.0,5.0,0.0,5.0,0.0,-5.0,-5.0,0.0,-1.0,5.0,1.0,-2.0,-2.0,-2.0,5.0,1.0,-2.0,1.0,0.0],"lag":1,"half_spread_bps":2.0,"commission_per_unit":0.005,"fixed_per_trade":0.5,"engine":"VECTOR"},"expected":{"status":"ok","outputs":{"positions":[0.0,4.0,-2.0,5.0,0.0,5.0,0.0,-5.0,-5.0,0.0,-1.0,5.0,1.0,-2.0,-2.0,-2.0,5.0,1.0,-2.0,1.0],"trades":[0.0,4.0,-6.0,7.0,-5.0,5.0,-5.0,-5.0,0.0,5.0,-1.0,6.0,-4.0,-3.0,0.0,0.0,7.0,-4.0,-3.0,3.0],"pnl_gross":[0.0,0.0,1.404799999999966,3.4324000000000012,-6.021000000000001,0.0,7.985000000000042,0.0,6.89549999999997,1.8185000000000429,0.0,-1.4886000000000053,-5.273500000000055,-1.476699999999994,-0.11519999999998731,-0.3902000000000214,1.8174000000000206,0.7440000000000424,0.18420000000000414,-1.7439999999999998],"cost":[0.0,0.6011943200000001,0.65221292,0.6751790599999999,0.6239237,0.6255606,0.6271576,0.6263492,0.0,0.6246064,0.52509426,0.65235188,0.60072416,0.5746571,0.0,0.0,0.6732815,0.59913704,0.5744633,0.5749865],"pnl_net":[0.0,-0.6011943200000001,0.7525870799999661,2.757220940000001,-6.6449237000000005,-0.6255606,7.357842400000042,-0.6263492,6.89549999999997,1.1938936000000429,-0.52509426,-2.140951880000005,-5.874224160000056,-2.051357099999994,-0.11519999999998731,-0.3902000000000214,1.1441185000000205,0.1448629600000424,-0.39026329999999587,-2.3189865],"equity":[0.0,-0.6011943200000001,0.15139275999996607,2.908613699999967,-3.7363100000000333,-4.361870600000033,2.9959718000000084,2.3696226000000085,9.265122599999978,10.459016200000022,9.93392194000002,7.792970060000016,1.918745899999961,-0.1326112000000331,-0.2478112000000204,-0.6380112000000419,0.5061072999999787,0.6509702600000211,0.2607069600000253,-2.0582795399999747],"total_gross":7.7726000000000255,"total_spread_cost":1.46587954,"total_commission":0.365,"total_fixed_cost":8.0,"total_net":-2.0582795399999747,"turnover":7329.3976999999995,"trade_count":16,"max_drawdown":12.517295739999996}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"purgedcv_j-0001","operation":"research.cv.purged_kfold","inputs":{"t0":[0,1,2,3,4,5,6,7,8,9],"t1":[2,3,4,5,6,7,8,9,10,11],"n_splits":3,"embargo_pct":0.1},"expected":{"status":"ok","outputs":{"folds":[{"test":[0,1,2,3],"train":[6,7,8,9]},{"test":[4,5,6],"train":[0,1,9]},{"test":[7,8,9],"train":[0,1,2,3,4]}],"embargo_count":1}},"tolerance_class":"date_and_convention","tolerance_limit":null,"verified_by":["hand","reference-computed"]}
{"case_id":"purgedcv_j-0002","operation":"research.cv.purged_kfold","inputs":{"t0":[0,1,2,3,4,5,6,7,8,9],"t1":[2,3,4,5,6,7,8,9,10,11],"n_splits":3,"embargo_pct":0.0},"expected":{"status":"ok","outputs":{"folds":[{"test":[0,1,2,3],"train":[6,7,8,9]},{"test":[4,5,6],"train":[0,1,9]},{"test":[7,8,9],"train":[0,1,2,3,4]}],"embargo_count":0}},"tolerance_class":"date_and_convention","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"purgedcv_j-0003","operation":"research.cv.purged_kfold","inputs":{"t0":[0,1,2,3,4,5,6,7,8,9],"t1":[0,1,2,3,4,5,6,7,8,9],"n_splits":3,"embargo_pct":0.0},"expected":{"status":"ok","outputs":{"folds":[{"test":[0,1,2,3],"train":[4,5,6,7,8,9]},{"test":[4,5,6],"train":[0,1,2,3,7,8,9]},{"test":[7,8,9],"train":[0,1,2,3,4,5,6]}],"embargo_count":0}},"tolerance_class":"date_and_convention","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"purgedcv_j-0004","operation":"research.cv.purged_kfold","inputs":{"t0":[0,1,2,3,4,5,6,7,8,9],"t1":[2,3,4,5,6,7,8,9,10,11],"n_splits":10,"embargo_pct":0.1},"expected":{"status":"ok","outputs":{"folds":[{"test":[0],"train":[3,4,5,6,7,8,9]},{"test":[1],"train":[4,5,6,7,8,9]},{"test":[2],"train":[5,6,7,8,9]},{"test":[3],"train":[0,6,7,8,9]},{"test":[4],"train":[0,1,7,8,9]},{"test":[5],"train":[0,1,2,8,9]},{"test":[6],"train":[0,1,2,3,9]},{"test":[7],"train":[0,1,2,3,4]},{"test":[8],"train":[0,1,2,3,4,5]},{"test":[9],"train":[0,1,2,3,4,5,6]}],"embargo_count":1}},"tolerance_class":"date_and_convention","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"purgedcv_j-0017","operation":"research.cv.cpcv_paths","inputs":{"n_groups":6,"n_test_groups":2},"expected":{"status":"ok","outputs":{"n_splits":15,"n_paths":5}},"tolerance_class":"date_and_convention","tolerance_limit":null,"verified_by":["hand","reference-computed"]}
```

## Outside-library evidence and limits (from the project's own page)

The operations are checked against hand examples, one paper example and outside libraries (`oracle/OUTSIDE_J.json`, ruling J-19a):

| Suite | Cases | Outside-checked |
|---|---|---|
| `backtest_j` | 23 | 14 |
| `purgedcv_j` | 23 | 12 |
| `rstats_j` | 37 | 5 |

Limits: synthetic prices, one instrument, a fixed half-spread and no financing; the iid assumptions of PSR and DSR; daily P&L per unit rather than returns on capital. The page shows the method, not a market.

## Real-data reconciliation

- Not applicable: synthetic prices, a teaching example.

## Rulings that name this curve's operations

- (stage-j-rulings-w1.md) | J-1 | Operations and contract | Wave 1 adds `research.backtest.run` (`11-research/backtester.md`), `research.cv.purged_kfold`, `research.cv.cpcv_paths` (`purged-cv.md`), `research.regime.viterbi` (`regimes.md`), `research.stats.psr`, `research.stats.dsr`, `research.stats.pbo`, `research.stats.power` (`research-statistics.md`). No new error code: target contract 1.13.0 (new operations are a minor version). The fill model is full fill at the close plus or minus the half spread; stage H's queue fill simulator is a separate operation and does not change this one |
- (stage-j-rulings-w1.md) | J-18 | Units | PSR and DSR take per-period Sharpe ratios; `research.stats.power` takes years and returns annualised Sharpe ratios, as `research/preregs/README.md` |
- (stage-j-rulings-w1.md) | J-21 | Power argument range | `research.stats.power` with `alpha` or `power` outside the open interval (0, 1) is `E_DOMAIN`, as `alpha >= power` (`rstats_j-0022`) |
