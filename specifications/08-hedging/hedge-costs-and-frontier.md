# Hedge costs, market impact, liquidity and margin; the risk-against-cost frontier

Spec version 1.0.0. Status: Specified (stage I, wave 4a). Rulings: `stage-i-rulings.md` I-24 to I-28 (and I-1 to I-5, I-13, I-14). Suites in `datasets/golden/stage_i/`: `hedgecost_i` (new cases of `hedge.qp.solve`) and `hedgefrontier_i`, written by `oracle/python/gen_stage_i_w4a.py`.

**Plain idea.** A hedge that cuts risk also costs money. Crossing the bid-ask spread costs a fixed amount per unit traded. Trading size moves the price against the trader (market impact). A broker or clearing house asks for margin on each position. This page adds those costs to the wave 1 least-squares hedge as optional inputs, as ruling I-13 set out. With none of the new inputs given, `hedge.qp.solve` is exactly the wave 1 operation; the generator re-solves every `hedgeqp_i` case through the extended reference and asserts byte-equal results. Liquidity limits need no new input: a cap on how much of an instrument can be traded is a bound (`lower`, `upper`). The frontier operation solves the same problem for a list of cost weights, so the risk given up for each saving in cost can be read off.

Sources:
- [AC01] R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2), 2001, 5-39 (linear temporary impact, so the impact cost is quadratic in size) (not opened in this session).
- [NW06] J. Nocedal, S. J. Wright, *Numerical Optimization*, 2nd ed., Springer, 2006, chapter 12 (KKT conditions; here with the subgradient of `|x|`) (not opened).
- [BV04] S. Boyd, L. Vandenberghe, *Convex Optimization*, Cambridge University Press, 2004, section 4.4 and 6.3 (quadratic programs with an l1 term; trade-off curves) (not opened).
- `08-hedging/hedge-solvers.md` (`hedge.qp.solve`), normative here.

## `hedge.qp.solve`: new optional inputs (contract 1.11.0, wave 4a)

Objective, extending the wave 1 one:

`f(x) = sum_i w_i (A x + b)_i^2 + ridge |x|^2 + cost_weight * C(x)`, with `C(x) = sum_j (half_spreads_j |x_j| + impact_j x_j^2)`,

subject to the wave 1 constraints and, when given, `sum_j margin_rates_j |x_j| <= margin_limit`.

New inputs, each optional:
- `half_spreads` (length `n`, each `>= 0`): the cost per unit traded of crossing half the spread, as stage B `hedge.spread_cost`.
- `impact` (length `n`, each `>= 0`): the linear-impact coefficient. A trade of size `x` moves its own price by `impact x`, so it costs `impact x^2` [AC01].
- `cost_weight` (default 1, `>= 0`): how much one unit of cost is worth against one unit of weighted squared residual.
- `margin_rates` (length `n`, each `>= 0`) and `margin_limit` (`>= 0`): both or neither.

The hedge starts from no position, so the traded size is `x` itself (I-24).

### Checks, in order (I-25)

The wave 1 checks 1 to 3 come first. Then, still before the singularity checks:

1. `half_spreads`, `impact` or `margin_rates` not of length `n`; `margin_rates` without `margin_limit`, or the reverse: `E_INPUT`.
2. `singular = MIN_NORM` with any new input: `E_INPUT`.
3. A negative half-spread, impact or margin rate; `cost_weight < 0`; `margin_limit < 0`: `E_DOMAIN`.

The wave 1 singularity checks 4 and 5 use `H = A^T W A + ridge I + cost_weight diag(impact)`. Impact makes a singular problem regular, as a ridge does; a spread cost does not (I-26). Feasibility (wave 1 check 6) also counts the margin constraint, and `E_INFEASIBLE` covers a margin limit that the bounds or equalities cannot meet.

### Solution

The smooth part is strictly convex after the checks, and `C` and the margin are convex, so the minimiser is unique. The `|x|` terms make `f` non-smooth at `x_j = 0`. Optimality uses the subgradient: at `x_j = 0` inside its bounds, `|g_j| <= cost_weight half_spreads_j + mu margin_rates_j`, where `g` is the gradient of the smooth part plus the equality terms and `mu >= 0` is the margin multiplier. So a costly instrument can be left out exactly (`hedgecost_i-0002` returns `x_2 = 0.0`). Builds may use any exact method. Two examples are an active-set method over the sign states, and a QP in split variables `x = p - n`, `p, n >= 0`, where the costs and the margin are linear.

### New outputs (I-27)

Present only when at least one new input is given, so wave 1 cases keep their exact output set:
- `risk`: `sum_i w_i r_i^2 + ridge |x|^2` (the objective without the cost term).
- `cost`: `C(x)`.
- `margin`: `sum_j margin_rates_j |x_j|`, only when `margin_rates` is given.

`objective` is `risk + cost_weight cost`. `x`, `residual` and `rank` are as in wave 1.

## `hedge.frontier.solve` (risk against cost)

### Inputs

Every input of `hedge.qp.solve` except `cost_weight`, plus `cost_weights` (1 to 50 values, strictly increasing, each `>= 0`).

### Checks, in order

`E_LIMIT` (more than 50 weights), the finite rule, then: `cost_weight` given; `cost_weights` empty or not strictly increasing; neither `half_spreads` nor `impact` given: `E_INPUT`. Then the `hedge.qp.solve` checks at each point in turn, in order of the weights; the first error stops the operation.

### Outputs

`points`: one per weight, `{cost_weight, x, risk, cost}`. On a convex problem `risk` is non-decreasing and `cost` non-increasing in the weight [BV04 4.7]; the generator asserts this on every golden.

## Validation cases and oracle

| Suite | Cases (value + error) | Oracle and self-checks | Outside (I-2, I-28) |
|---|---|---|---|
| `hedgecost_i` | 13 + 9 | Every combination of per-instrument states (positive, negative, zero, at a bound) and margin active or not, solved at 50 digits; a state is kept if signs, bounds, margin and the subgradient conditions hold; exactly one `x` must survive. Wave 1 goldens reproduced exactly. `E_INFEASIBLE` confirmed by HiGHS on the split-variable LP | 12 of 22 |
| `hedgefrontier_i` | 4 + 6 | The same at each point; monotone frontier asserted | 2 of 10 |

Outside solvers (I-28), on the same problem: scipy 1.18 `lsq_linear` BVLS or `lstsq` (exact; used only when there is no spread cost, margin or equality, since impact and ridge are then extra least-squares rows), `minimize` trust-constr and `minimize` SLSQP (both on the split form). A case counts when the first of these that agrees with every `x` within `root_finding` does; `verified_by` names it. On the split form both general solvers stop near 1e-8 to 1e-10 on some cases: SLSQP's line search stalls, and trust-constr loses accuracy with general constraints. So the uncounted cases (one cost case, two frontiers) are solver accuracy, not a disagreement in the answer. Stage I so far: 86 of 209 = 41.1%.

Mutants caught: costs ignored; the margin constraint ignored.

## Convergence and limit cases

| Method | Asserted behaviour | Measured on | Limit case | Reference |
|---|---|---|---|---|
| State enumeration | Finite: at most `5^n x 2` KKT systems; exactly one optimum survives | Every value case | `cost_weight = 0` returns the wave 1 answer exactly (`hedgecost_i-0003`); a large spread sets a position to exactly 0 | scipy BVLS, trust-constr, SLSQP |
| Frontier | Risk non-decreasing, cost non-increasing in the weight | Every frontier golden | Weight 0 is the risk-only hedge | Same solvers per point |

## Limitations

- Square-root impact (cost growing as `|x|^{3/2}`), which is common in practice, is not a QP and is not covered. Linear impact is the QP-compatible approximation.
- The hedge starts from no position. Rebalancing from an existing position (cost on `x - x_0`) is a new input for a later wave.
- Margin is linear in `|x|` per instrument, with no netting and no portfolio margin model.

## Spec questions and rulings

| # | Question | Ruling |
|---|---|---|
| Q-I11 | Should cost apply to the trade from an existing position? | Not in wave 4a (I-24). Every stage I hedge so far starts from no hedge position. An `initial_positions` input can come later and changes no current meaning |
| Q-I12 | Should the new outputs always be present? | No (I-27). Adding outputs to wave 1 results would change goldens the language lanes already pass |
| Q-I13 | May the outside check try several library solvers? | Yes, if each is a library solving the same problem and the solver used is recorded per case (I-28). Picking the one that agrees does not change any golden, which comes from the 50-digit reference alone |

## Amendment after the builds

Ruling I-54: answers are exact to `root_finding` at a hold/not-hold switch point too (`hedgecost_i-0023`).
