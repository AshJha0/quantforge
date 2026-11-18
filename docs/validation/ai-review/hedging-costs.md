# Review request: Hedging against trading costs (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: I. Evidence line from the project's curve table: 33 golden cases for `hedge.qp.solve` with costs and `hedge.frontier.solve`, 15 reproduced by an outside library.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.

## Spec

### `specifications/08-hedging/hedge-costs-and-frontier.md`

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
| `hedgefrontier_i` | 4 + 6 | The same at each 

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

### `specifications/08-hedging/hedge-solvers.md`

# Hedge solvers: constrained least squares, integer contracts, minimum variance, Greek and beta hedges, residual risk

Spec version 1.0.0. Status: Specified (stage I, wave 1). Rulings: `stage-i-rulings.md` I-1 to I-14. Suites in `datasets/golden/stage_i/`: `hedgeqp_i`, `hedgeint_i`, `hedgemv_i`, `hedgegreeks_i`, `hedgebeta_i`, `hedgeres_i`, all written by `oracle/python/gen_stage_i_w1.py`.

**Plain idea.** A hedge is a set of positions `x` in instruments whose sensitivities `A` (one row per risk factor, one column per instrument) offset the book's existing risk `b`. The residual risk is `A x + b`. Most hedges in this page are one problem, weighted least squares on that residual, with limits on the positions; the rest (minimum variance, Greek neutralisation, beta futures) are closed forms of the same idea. Stage B's `hedge.solve` (`stage-b-hedges.md`) is unchanged; this page adds constraints, integer lots, rank-deficient problems and reporting.

Sources:
- [NW06] J. Nocedal, S. J. Wright, *Numerical Optimization*, 2nd ed., Springer, 2006, chapter 12 (KKT conditions, theorem 12.1) and chapter 16 (equality-constrained and active-set QP) (not opened in this session; the conditions are re-derived and checked numerically by the generator).
- [GV13] G. H. Golub, C. F. Van Loan, *Matrix Computations*, 4th ed., Johns Hopkins, 2013, section 5.5 (rank-deficient least squares, minimum-norm solution by the SVD) (not opened).
- [SP95] P. B. Stark, R. L. Parker, "Bounded-variable least-squares: an algorithm and applications", *Computational Statistics* 10, 1995, 129-141 (the BVLS method that scipy's `lsq_linear(method="bvls")` implements, used as an outside check) (not opened).
- [FP85] U. Fincke, M. Pohst, "Improved methods for calculating vectors of short length in a lattice", *Mathematics of Computation* 44(170), 1985, 463-471 (ellipsoid enumeration for integer least squares) (not opened).
- [H18] J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 3 (minimum-variance hedge ratio `h* = rho sigma_S / sigma_F`; stock-index futures `N* = beta V_A / V_F`, worked example with 30 contracts) and chapter 19 (delta, gamma and vega neutrality) (not opened; the 30-contract example is reproduced by `hedgebeta_i-0001`).

## Common rules

- Check order for every operation: `E_PARSE`, `E_SCHEMA`, `E_LIMIT` (sizes in ruling I-4), the finite rule F-2 (`E_DOMAIN`), then the operation's own checks in the order listed below. F-3 (negative zero) holds.
- Matrices are lists of rows. `null` is legal only inside `lower`, `upper`, `lower_lots`, `upper_lots` (ruling I-12).
- Every rank or singularity decision uses one relative threshold, `1e-12` (ruling I-3), **applied after scaling** (ruling R6-6.2, amending I-3): a symmetric matrix `M` (`H`, a covariance) is tested as `D M D` with `D_jj = 1/sqrt(M_jj)` (a zero or negative diagonal entry is itself singular); an equality matrix `E` is tested with each row scaled to unit Euclidean norm and its columns scaled by the same `D` as `H`; the reduced Hessian is `Z^T (D H D) Z` with `Z` a basis of the null space of `E D`, compared with the largest eigenvalue of `D H D`. Scaling never changes the solution, only the decision, so a regular problem in mixed units (basis points against currency, weights from 1e-3 to 1e3) is no longer refused (`r6/hedgescale_r6`).
- Iteration caps and the kink tolerance (ruling R6-6.1): a position is at its kink when `|x_j| <= 1e-11 max(1, max_k |x_k|)`; any active-set or sign-state loop of `hedge.qp.solve` stops after `10 (n + p) + 100` iterations (`p` constraints of the problem as stated; rows a build adds for its own reformulation, such as `2 n` sign rows, do not count: R6-28.5), and `hedge.integer.solve` after 1,000,000 lattice points or nodes, with `E_NO_CONVERGENCE`. Builds may use any rank-revealing method (SVD, pivoted QR, symmetric eigenvalues, Cholesky pivots); the goldens keep every decision at least a factor 1e3 away from the threshold, so all of them agree.
- New error code `E_INFEASIBLE` (contract 1.11.0, ruling I-1): no point satisfies the constraints.

## `hedge.qp.solve` (HEDGE-05 constrained least squares; HEDGE-04 multi-instrument)

Minimise

`f(x) = sum_i w_i (A x + b)_i^2 + ridge * sum_j x_j^2`

subject to `E x = e` (optional equalities) and `lower_j <= x_j <= upper_j` (optional bounds).

### Inputs

- `a` (`m x n`, `m, n >= 1`), `b` (length `m`), `weights` (length `m`, each `> 0`).
- `ridge` (optional, default 0, `>= 0`).
- `eq_matrix` (`k x n`) and `eq_rhs` (length `k`): optional, both or neither.
- `lower`, `upper` (optional, length `n`, entries a Real or `null` for no bound).
- `singular` (optional, `ERROR` default, or `MIN_NORM`; ruling I-5).

### Checks, in order

1. Shapes: `a` non-empty with rows of one length `n >= 1`; `b`, `weights` of length `m`; `eq_matrix` and `eq_rhs` both present or both absent, rows of length `n`, `len(eq_rhs) = k`; `lower`, `upper` of length `n`: else `E_INPUT`.
2. `singular = MIN_NORM` with any non-null bound: `E_INPUT` (I-5).
3. A weight `<= 0`, `ridge < 0`, or `lower_j > upper_j` (both non-null): `E_DOMAIN`.
4. Equality rank: `k > n`, or the smallest singular value of `E` at most `1e-12` times its largest: `E_SINGULAR`.
5. Reduced Hessian. Let `H = A^T W A + ridge I` and `Z` an orthonormal basis of the null space of `E` (`Z = I` when `k = 0`). If an eigenvalue of `Z^T H Z` is at most `1e-12` times the largest eigenvalue of `H` (in absolute value), the problem has no unique minimiser: `E_SINGULAR` under `ERROR`; under `MIN_NORM` see below. When `k = n` there is no reduced Hessian and this check passes.
6. Feasibility: no `x` with `E x = e` inside the bounds: `E_INFEASIBLE` (I-14).

### Solution

With checks 4 and 5 passed, `f` is strictly convex on the feasible set, so the minimiser is uniq

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

## Golden cases (16 of 48 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"hedgecost_i-0001","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.05,0.05,0.05]},"expected":{"status":"ok","outputs":{"x":[1.2016219490255016,-0.568436977708047,-0.7277727018914835],"residual":[-1.2281510802068187,0.8872531307014007,-2.012559044559503,1.0926147319764568,-1.3492763108944867],"objective":8.844136838981443,"rank":3,"risk":8.719245257550192,"cost":0.12489158143125162}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-trust-constr-split"]}
{"case_id":"hedgecost_i-0002","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.01,5.0,0.01]},"expected":{"status":"ok","outputs":{"x":[0.9593664257212245,0.0,-1.0036965663483512],"residual":[-1.2413728875484458,1.3863313011770269,-2.1096082069504045,0.7641662308634635,-1.0173623996160157],"objective":9.540640917264254,"rank":3,"risk":9.52101028734356,"cost":0.01963062992069576}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-trust-constr-split"]}
{"case_id":"hedgecost_i-0003","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.3,0.3,0.3],"cost_weight":0.0},"expected":{"status":"ok","outputs":{"x":[1.2389484039547414,-0.579151887583752,-0.7518047108371649],"residual":[-1.2009884820045675,0.875980371751054,-2.0513033584105242,1.0987041058935945,-1.35119875049463],"objective":8.717443423206426,"rank":3,"risk":8.717443423206426,"cost":0.7709715007126975}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-slsqp-split"]}
{"case_id":"hedgecost_i-0004","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.05,0.1,0.02],"cost_weight":4.0},"expected":{"status":"ok","outputs":{"x":[1.0941877951928924,-0.4834054404250442,-0.7188354537220323],"residual":[-1.2912820157640361,0.9606356285590018,-1.9588776653187856,1.031717239719476,-1.3130404144219925],"objective":9.222094115305316,"rank":3,"risk":8.752387543798958,"cost":0.11742664287658969}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-trust-constr-split"]}
{"case_id":"hedgecost_i-0005","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"impact":[0.5,0.5,2.0]},"expected":{"status":"ok","outputs":{"x":[0.6733517569287463,-0.5062323373210563,-0.2666016642222619],"residual":[-1.6330847445762342,0.9878860566044515,-1.336306723033152,1.0974934402787502,-1.366248900084131],"objective":9.682024946496282,"rank":3,"risk":9.18503516780984,"cost":0.49698977868644395}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-bvls-or-lstsq"]}
{"case_id":"hedgecost_i-0006","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.05,0.1,0.02],"impact":[0.2,0.2,0.2]},"expected":{"status":"ok","outputs":{"x":[0.9631490130803548,-0.49785439390992775,-0.5957187457917915],"residual":[-1.4049219330329674,0.9532319329154765,-1.7959758537256085,1.034801460469686,-1.3415249730243306],"objective":9.22571928805759,"rank":3,"risk":8.809782854492578,"cost":0.41593643356501203}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-trust-constr-split"]}
{"case_id":"hedgecost_i-0007","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.02,0.02,0.02],"lower":[-0.6,-0.4,-0.4],"upper":[0.6,0.4,0.4]},"expected":{"status":"ok","outputs":{"x":[0.6,-0.4,-0.4],"residual":[-1.68,1.04,-1.48,0.94,-1.34],"objective":9.229800000000001,"rank":3,"risk":9.2018,"cost":0.028}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-slsqp-split"]}
{"case_id":"hedgecost_i-0008","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"margin_rates":[0.1,0.2,0.15],"margin_limit":0.2},"expected":{"status":"ok","outputs":{"x":[0.6753530358866267,-0.3547739004652618,-0.41006610878856653],"residual":[-1.5840471361037176,1.1128507866922472,-1.4604281998733442,1.0002681507065392,-1.272175128700655],"objective":9.171738457835492,"rank":3,"risk":9.171738457835492,"cost":0.0,"margin":0.2}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-slsqp-split"]}
{"case_id":"hedgecost_i-0009","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"margin_rates":[0.1,0.2,0.15],"margin_limit":10.0},"expected":{"status":"ok","outputs":{"x":[1.2389484039547414,-0.579151887583752,-0.7518047108371649],"residual":[-1.2009884820045675,0.875980371751054,-2.0513033584105242,1.0987041058935945,-1.35119875049463],"objective":8.717443423206426,"rank":3,"risk":8.717443423206426,"cost":0.0,"margin":0.3524959245377993}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-slsqp-split"]}
{"case_id":"hedgecost_i-0010","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.02,0.02,0.02],"margin_rates":[0.1,0.1,0.1],"margin_limit":0.15,"eq_matrix":[[1.0,1.0,1.0]],"eq_rhs":[0.0]},"expected":{"status":"ok","outputs":{"x":[0.7499999999999999,-0.40635888501742146,-0.34364111498257843],"residual":[-1.5219076655052266,1.0999128919860628,-1.3842770034843206,1.109451219512195,-1.268815331010453],"objective":9.180146450348433,"rank":2,"risk":9.150146450348432,"cost":0.03,"margin":0.15}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-slsqp-split"]}
{"case_id":"hedgecost_i-0011","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"lower":[0.5,null,null],"margin_rates":[0.2,0.1,0.1],"margin_limit":0.2},"expected":{"status":"ok","outputs":{"x":[0.6007919683283436,-0.4118239730307936,-0.38659209031251934],"residual":[-1.6824384362495572,1.031411986736543,-1.4669033224544208,0.9503358987752487,-1.3463024154901326],"objective":9.201360817957415,"rank":3,"risk":9.201360817957415,"cost":0.0,"margin":0.2}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-slsqp-split"]}
{"case_id":"hedgecost_i-0012","operation":"hedge.qp.solve","inputs":{"a":[[1.0,1.0,0.0],[0.5,0.5,1.0]],"b":[-2.0,-1.0],"weights":[1.0,1.0],"impact":[0.1,0.1,0.1]},"expected":{"status":"ok","outputs":{"x":[0.9533898305084746,0.9533898305084746,0.04237288135593221],"residual":[-0.09322033898305085,-0.004237288135593221],"objective":0.19067796610169493,"rank":3,"risk":0.00870798621085895,"cost":0.18196997989083596}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-bvls-or-lstsq"]}
{"case_id":"hedgecost_i-0013","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.1,0.1,0.1],"lower":[null,-0.3,null],"upper":[null,-0.3,null]},"expected":{"status":"ok","outputs":{"x":[1.0427540852072872,-0.3,-0.8183954323048379],"residual":[-1.2709250012536804,1.125468052640251,-2.003317739936528,0.9376473790914757,-1.1984169956085367],"objective":9.126340175801818,"rank":3,"risk":8.910225224050606,"cost":0.2161149517512125}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration"]}
{"case_id":"hedgecost_i-0023","operation":"hedge.qp.solve","inputs":{"a":[[1.0,0.0],[0.0,1.0]],"b":[-1.0,-2.0],"weights":[1.0,1.0],"half_spreads":[2.0,0.5]},"expected":{"status":"ok","outputs":{"x":[0.0,1.75],"residual":[-1.0,-0.25],"objective":1.9375,"rank":2,"risk":1.0625,"cost":0.875}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","scipy-1.18-slsqp-split"]}
{"case_id":"hedgefrontier_i-0001","operation":"hedge.frontier.solve","inputs":{"a":[[1.0,0.5,0.2],[0.3,1.2,0.4],[0.1,0.6,1.5],[0.8,0.2,0.9],[0.4,0.9,0.3]],"b":[-2.0,1.5,-0.7,0.9,-1.1],"weights":[1.0,2.0,0.5,1.5,1.0],"half_spreads":[0.05,0.1,0.02],"cost_weights":[0.0,0.5,1.0,2.0,5.0,10.0,50.0]},"expected":{"status":"ok","outputs":{"points":[{"cost_weight":0.0,"x":[1.2389484039547414,-0.579151887583752,-0.7518047108371649],"risk":8.717443423206426,"cost":0.13489870317285557},{"cost_weight":0.5,"x":[1.2208533278595104,-0.5671835816889136,-0.7476835536977733],"risk":8.717989425090684,"cost":0.13271469563582233},{"cost_weight":1.0,"x":[1.2027582517642792,-0.555215275794075,-0.7435623965583817],"risk":8.71962743074346,"cost":0.13053068809878912},{"cost_weight":2.0,"x":[1.166568099573817,-0.5312786640043982,-0.7353200822795986],"risk":8.72617945335456,"cost":0.12616267302472264},{"cost_weight":5.0,"x":[1.0579976430024303,-0.4594688286353672,-0.7105931394432492],"risk":8.772043611632258,"cost":0.11305862780252322},{"cost_weight":10.0,"x":[0.8770468820501189,-0.3397857696869824,-0.6693815680493335],"risk":8.93584417690975,"cost":0.09121855243219086},{"cost_weight":50.0,"x":[0.0,0.0,-0.23655913978494628],"risk":10.77731182795699,"cost":0.004731182795698926}]}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-state-enumeration","monotone-frontier"]}
{"case_id":"hedgeqp5_i-0001","operation":"hedge.qp.solve","inputs":{"a":[[0.9165,1.4925,0.5121,1.3447],[0.0942,0.1216,0.7015,-0.6375],[0.7218,-0.6466,-0.7107,0.6811],[0.1732,-0.5201,0.1618,-0.9089]],"b":[0.1406,-2.8892,2.7533,0.7408],"weights":[0.2323,1.9889,1.0815,0.7755]},"expected":{"status":"ok","outputs":{"x":[-4.097964802539608,-6.353269105271629,10.862334259230327,5.603359490587942],"residual":[0.0,0.0,0.0,0.0],"objective":0.0,"rank":4}},"tolerance_class":"root_finding","tolerance_limit":null,"verified_by":["mpmath-50-active-set","kkt-check","scipy-1.18-lstsq"]}
```

## Outside-library evidence and limits (from the project's own page)

The golden cases are 50-digit mpmath solves over the sign states with subgradient checks. Outside checks are scipy 1.18 solvers on the same problem (`oracle/outside_register_i.json`):

| Suite | Cases | Outside-checked |
|---|---|---|
| `hedgecost_i` | 23 | 13 |
| `hedgefrontier_i` | 10 | 2 |
| `hedgeqp5_i` | 30 | 29 |

Stage I as a whole: 278 of 443 cases outside-checked, error cases in the denominator (ruling I-2). Limits: linear spread cost and synthetic risks, so the page shows the method, not a desk's costs; the hedge starts from no position.

## Real-data reconciliation

- Not applicable: an optimisation on given inputs, not a market curve.

## Rulings that name this curve's operations

- (stage-i-rulings.md) | I-1 | Operations and contract | Wave 1 adds `hedge.qp.solve`, `hedge.integer.solve`, `hedge.minvar.ratio`, `hedge.greeks.neutralise`, `hedge.beta.futures`, `hedge.residual.report` (`08-hedging/hedge-solvers.md`) and one error code, `E_INFEASIBLE` (no point satisfies the constraints). Adding a code is a minor version: target contract 1.11.0. Stage B `hedge.solve` and `hedge.spread_cost` are unchanged |
- (stage-i-rulings.md) | I-9 | Greek hedges | Exact neutralisation only: as many hedge instruments as targets. Vega is per unit of volatility, as QuantLib's `vega()`, not per 1%. A least-squares Greek hedge is `hedge.qp.solve` with the Greek matrix as `a` |
- (stage-i-rulings.md) | I-13 | Costs in the QP | Not in wave 1 (spec question Q-I1). The cost wave adds new optional inputs; with them absent, `hedge.qp.solve` keeps the meaning fixed here |
- (stage-i-rulings.md) | I-25 | Order of the new checks in `hedge.qp.solve` | After wave 1 checks 1 to 3: lengths and the `margin_rates`/`margin_limit` pair (`E_INPUT`), `MIN_NORM` with any new input (`E_INPUT`), negative values (`E_DOMAIN`); then wave 1 checks 4 to 6, with the margin constraint part of feasibility |
- (stage-i-rulings.md) | I-33 | Selection inputs | `hedge.select.solve` takes the `hedge.qp.solve` inputs without equalities or a singular policy (`E_INPUT` if present), and every bound must admit 0 (`E_DOMAIN`). The full problem must be regular (I-3) |
- (stage-i-rulings.md) | I-48 | Java J-I4, C++ open note: Java and C++ return `E_LIMIT` above 20 instruments with a sign-open cost or margin term (one QP per sign orthant); Rust and Python do not | The I-4 limit (200 instruments) is the only size limit of `hedge.qp.solve`. A method-dependent `E_LIMIT` below it is not allowed. Java and C++ replace the orthant enumeration with a split-variable or sign-state active-set method before release. No golden reaches 20 such instruments, so no golden is added tonight |
- (stage-i-rulings.md) | I-54 | Rust note: wave 4a is accurate only to about 1e-6 at a hold/not-hold switch point | Not allowed: `hedge.qp.solve` with costs is exact to `root_finding` everywhere, switch points included. At a switch (`|g_j| = cost_weight h_j` with `x_j = 0`) both neighbouring sign states give the same `x`, so solving the smooth problem exactly on either state is exact. A regularised split problem may find the state, but its answer must then be re-solved exactly. Pinned by `hedgecost_i-0023` (instrument 1 exactly at its switch, `x = [0, 1.75]`). Rust changes its 4a final step; the other lanes run the new case |
