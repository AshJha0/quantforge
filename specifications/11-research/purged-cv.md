# Purged and embargoed k-fold cross-validation; combinatorial purged CV counts

Spec version 1.0.0. Status: specified, not implemented (wave 1 code lands in v0.9.0; no build implements these operations and their goldens are not in this release). Rulings: `stage-j-rulings-w1.md` J-7 to J-9. Suite: `datasets/golden/stage_j/purgedcv_j`, written by `oracle/python/gen_stage_j_w1.py`. Plan item A1 (plan 12.5).

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
