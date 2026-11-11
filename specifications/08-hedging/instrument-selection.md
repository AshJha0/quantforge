# Instrument selection: the best hedge with at most K instruments

Spec version 1.0.0. Status: Specified (stage I, wave 4c). Rulings: `stage-i-rulings.md` I-33 to I-35 (and I-1 to I-5). Suite `datasets/golden/stage_i/hedgeselect_i`, written by `oracle/python/gen_stage_i_w4c.py`.

**Plain idea.** A desk often wants a hedge that uses only a few of the instruments it could trade: fewer tickets, fewer lines to manage. Choosing the best `K` out of `n` is a cardinality-constrained least-squares problem. It is not convex, and simple greedy rules can miss the answer. `hedgeselect_i-0009` is built so that the best single instrument is not in the best pair. With `n` at most 20 this operation defines the answer as the best over every subset of at most `K` instruments, each solved by `hedge.qp.solve`.

Sources:
- [M02] A. Miller, *Subset Selection in Regression*, 2nd ed., Chapman and Hall/CRC, 2002, chapter 3 (exhaustive search, and forward selection missing the best subset) (not opened in this session; the counterexample here is checked numerically).
- `08-hedging/hedge-solvers.md` (`hedge.qp.solve`), normative here.

## `hedge.select.solve`

### Inputs

`a`, `b`, `weights`, `ridge`, `lower`, `upper` as `hedge.qp.solve`; `max_instruments` `K` (Integer). No `eq_matrix`, `eq_rhs` or `singular` (I-33).

### Checks, in order

1. `E_LIMIT`: more than 20 instruments (I-35).
2. Finite rule; then `hedge.qp.solve` checks 1 to 3 (shapes `E_INPUT`, domain `E_DOMAIN`).
3. `K` outside `1..n`; any of `eq_matrix`, `eq_rhs`, `singular` present: `E_INPUT`.
4. A bound that excludes 0 (`lower_j > 0` or `upper_j < 0`): `E_DOMAIN`. An instrument left out sits at 0, which must be feasible.
5. The full problem's `H = A^T W A + ridge I` singular by I-3: `E_SINGULAR`. Every subset of a regular problem is then regular.

### Solution and ties (I-34)

For every subset `S` of `1..K` instruments, solve `hedge.qp.solve` on the columns in `S` with their bounds; the others are 0. The answer is the subset with the least objective. Ties are objectives within `1e-12` relative of the best. Among tied subsets the smallest one wins, then the lexicographically smallest list of indices. The goldens hold either an exact tie (`-0008`: two symmetric instruments, so index 0 wins; `-0010`: one instrument against two, so one wins) or a runner-up more than `1e-9` relative worse, which the generator asserts.

Builds may prune (branch and bound on the objective, which can only fall as instruments are added). They must return the same subset.

### Outputs

`selected` (the chosen 0-based indices, ascending), `x` (length `n`, 0 outside `selected`), `residual`, `objective`.

## Validation cases and oracle

`hedgeselect_i`: 10 value cases and 7 error cases. The value cases are a five-bond key-rate book with `K = 1, 2, 3, 5`, long-only, a ridge, and weights that change the single best bond; plus two exact ties and the greedy counterexample. Every subset is solved at 50 digits by the wave 1 reference.

Outside (I-2): 10 of 17. The same enumeration is run with every subset solved by scipy 1.18 (`lstsq`, or `lsq_linear` BVLS with bounds). The case counts when the library's best subset is the same and every output agrees within `root_finding`. Stage I so far: 108 of 251 = 43.0%.

Mutant caught: greedy forward selection. It takes the best single instrument, then that instrument's best partner, and misses the best pair by 0.5 in objective (`-0009`).

## Convergence and limit cases

| Method | Asserted behaviour | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Exhaustive subset search | Finite: `sum_{k<=K} C(n, k)` solves (at most 31 in the goldens) | Every value case | `K = n` is the full `hedge.qp.solve` answer (`-0004`) | scipy per subset |

## Limitations

- At most 20 instruments: with exhaustive search the cost grows as `C(n, K)`. Larger universes need a mixed-integer QP solver, which no free library in the toolchain offers for an outside check.
- No fixed cost per selected instrument, and no equalities. Both are natural extensions for a later wave.

## Spec questions and rulings

| # | Question | Ruling |
|---|---|---|
| Q-I17 | Exactly `K` instruments, or at most `K`? | At most `K` (I-34). Adding an instrument never raises the least objective, so "exactly `K`" would only add ties with zero positions |
| Q-I18 | Equalities in selection? | Refused (I-33). A budget equality can make a small subset infeasible, which would need a rule for which infeasible subsets to skip |

## Amendment after the builds

Ruling I-53 adds a size limit: `E_LIMIT` when `sum_{k=1..min(K,n)} C(n, k)` exceeds 100,000 candidate subsets (`hedgeselect_i-0018`).
