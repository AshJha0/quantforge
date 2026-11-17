# Review request: Liquidity curves (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage J). Evidence line from the project's status table: 7 golden cases for `liq.curve.cost`, 0 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. The square-root impact law has no library implementation with the same conventions.

## Spec

### `specifications/10-execution/liquidity-curve.md`

# Liquidity cost curve: spread, square-root impact and timing risk by size and horizon

Spec version 1.0.0. Status: Specified and implemented in all four builds (stage J curves lane, v0.9.0). Rulings: `stage-j-rulings-curves.md` J-C-1 and J-C-6 to J-C-9. Suite `stage_j/liqcurve_j`. Built so that stage H reuses it: at a one-day horizon with exponent 1/2 the impact term is the draft `exec.impact.sqrt` of stage H (`10-execution/impact.md` on branch `h-spec`, golden `imp_h-0001`), and the timing-risk term is the variance of the linear Almgren-Chriss schedule that H-3b builds (J-C-8).

**Plain idea.** Selling a position costs more than the screen price. You cross half the bid-ask spread, and the selling itself pushes the price away; the push is larger when you sell more and when you sell faster. Selling slowly cuts the push but leaves you exposed to the market for longer. A liquidity curve puts numbers on that trade-off: for each order size and each liquidation horizon, the expected cost per unit, the risk from waiting, and the horizon where their sum is smallest.

**Formal statement.** For an order of `Q` units traded evenly over `h` trading days in a stock with daily volume `V`, daily volatility `sigma` (a fraction of price), half spread `s` (fraction of price; input in basis points), impact coefficient `Y`, exponent `delta` in `(0, 1]` and a risk multiplier `z >= 0`, the cost per unit as a fraction of the arrival price is

`c(Q, h) = s + I(Q, h) + R(h)`, with `I(Q, h) = Y sigma (Q / (V h))^delta` and `R(h) = z sigma sqrt(h / 3)`.

`I` is the square-root law of [TLD11] (`delta = 1/2`) written with the daily participation `Q/(V h)`, which is the form [AFTHL05] fit (they report `delta` near 3/5). `R` is `z` standard deviations of the average execution price against arrival for a linear liquidation over `h` days: the continuous-time variance of the Almgren-Chriss linear trajectory is `sigma^2 X^2 T / 3` [AC00], so per unit the standard deviation is `sigma sqrt(h/3)` (J-C-7).

With `a = Y sigma (Q/V)^delta` and `b = z sigma / sqrt 3`, `c = s + a h^{-delta} + b h^{1/2}` is strictly convex in `h > 0` when `a, b > 0`, and setting the derivative to zero gives the cost-minimising horizon in closed form:

`h* = (2 delta a / b)^{1 / (delta + 1/2)}`, `c* = s + a h*^{-delta} + b sqrt(h*)`.

## `liq.curve.cost`

Inputs: `half_spread_bps` (`>= 0`), `daily_volume` (`> 0`), `daily_vol` (`>= 0`), optional `coefficient` `Y` (default 1, `>= 0`; labelled assumed, as stage H ruling H-10), optional `exponent` `delta` (default 0.5, in `(0, 1]`), optional `risk_multiplier` `z` (default 0, `>= 0`), `sizes` (non-empty, each `>= 0`), `horizons_days` (non-empty, each `> 0`; any order).

Outputs: `spread_cost` (`s`), `impact` (matrix, row per size, column per horizon), `timing_risk` (per horizon), `total_cost` (matrix), `optimal_horizon` and `min_cost` (per size). When `b = 0` (no risk term) or `Y = 0` there is no interior optimum and both are `null` (J-C-8). A zero size gives `h* = 0` and `c* = s`.

Checks, in order (after `E_PARSE`, `E_SCHEMA`, `E_LIMIT` and F-2): empty `sizes` or `horizons_days`: `E_INPUT`; any value outside its domain above: `E_DOMAIN`.

## Worked example (golden `liqcurve_j-0001`, hand)

`sigma = 0.02`, `V = 10^7`, `Y = 1`, `delta = 1/2`, half spread 5 bp, `z = 0`.

1. `Q = 10^5`, `h = 1`: `I = 0.02 sqrt(10^5 / 10^7) = 0.02 x 0.1 = 0.002` (20 bp), the stage H value `imp_h-0001`. Total `0.0005 + 0.002 = 0.0025`.
2. `Q = 4 x 10^5`, `h = 1`: four times the size, twice the impact, `0.004`.
3. `Q = 10^5`, `h = 4`: a quarter of the daily participation, half the impact, `0.001`.

Optimal horizon (golden `liqcurve_j-0002`, hand): set `z = sqrt 3`, so `b = sigma = 0.02`; `a = 0.002`; `h* = (2 x 0.5 x 0.002 / 0.02)^1 = 0.1` day, and `c* = 0.0005 + 0.002/sqrt(0.1) + 0.02 sqrt(0.1) = 0.0131491106`.

## Acceptance

Class `simple_analytic`. Evidence (J-C-9): `liqcurve_j-0001` and `-0002` are hand derivations; the rest are reference-computed by `oracle/python/gen_stage_j_curves.py` (mpmath, 50 digits). No outside library implements this curve and the sources print no fully specified example with these inputs, so it is self-assessed. Property tests in each language: the one-day square-root value, impact increasing in size, `h*` a minimum (cost at `0.9 h*` and `1.1 h*` not lower).

## Limitations

- A formula curve with assumed parameters (`Y`, `delta`, `z`), not a calibration: no claim about any real stock or venue. Calibration is stage H item H-1 (crypto book, research lane).
- Even trading only; the optimal schedule under risk aversion (Almgren-Chriss `sinh` trajectory) is stage H item H-3b. Permanent impact, decay and resilience (Obizhaeva-Wang) are not in the curve.
- FRTB liquidity horizons (MAR33.12, the 10/20/40/60/120-day cascade for expected shortfall) are a regulatory scaling of market risk, not a cost curve; they are not built here.

## Sources

- [TLD11] B. Toth, Y. Lemperiere, C. Deremble, J. de Lataillade, J. Kockelkoren, J.-P. Bouchaud, "Anomalous price impact and the critical nature of liquidity in financial markets", *Physical Review X* 1 (2011) 021006, open access. `I = Y sigma sqrt(Q/V)`, `Y` of order one. Evidence class: paper, recalled (the stage H draft records the same form; equation number not verified).
- [AFTHL05] R. Almgren, C. Thum, E. Hauptmann, H. Li, "Direct estimation of equity market impact", *Risk* July 2005, 57-62 (free preprint). Temporary impact a power of the trading rate, exponent near 3/5. Evidence class: paper, recalled.
- [AC00] R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2) 2000, 5-39 (free preprint). Variance of the linear trajectory, continuous limit `sigma^2 X^2 T / 3`. Evidence class: paper, recalled; checked here by integrating `sigma^2 x(t)^2` with `x(t) = X (1 - t/T)` over `[0, T]`, which gives `sigma^2 X^2 T / 3`.


## Golden cases (7 of 7 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"liqcurve_j-0001","operation":"liq.curve.cost","inputs":{"half_spread_bps":5.0,"daily_volume":10000000.0,"daily_vol":0.02,"sizes":[100000.0,400000.0],"horizons_days":[1.0,4.0]},"expected":{"status":"ok","outputs":{"spread_cost":0.0005,"impact":[[0.002,0.001],[0.004,0.002]],"timing_risk":[0.0,0.0],"total_cost":[[0.0025,0.0015],[0.0045,0.0025]],"optimal_horizon":null,"min_cost":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed"]}
{"case_id":"liqcurve_j-0002","operation":"liq.curve.cost","inputs":{"half_spread_bps":5.0,"daily_volume":10000000.0,"daily_vol":0.02,"sizes":[100000.0],"horizons_days":[0.1,1.0],"risk_multiplier":1.7320508075688772},"expected":{"status":"ok","outputs":{"spread_cost":0.0005,"impact":[[0.006324555320336759,0.002]],"timing_risk":[0.006324555320336759,0.02],"total_cost":[[0.013149110640673518,0.0225]],"optimal_horizon":[0.1],"min_cost":[0.013149110640673518]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["hand","reference-computed"]}
{"case_id":"liqcurve_j-0003","operation":"liq.curve.cost","inputs":{"half_spread_bps":5.0,"daily_volume":10000000.0,"daily_vol":0.02,"sizes":[0.0,10000.0,100000.0,1000000.0,5000000.0],"horizons_days":[0.25,0.5,1,2,5,10,20],"risk_multiplier":1.645},"expected":{"status":"ok","outputs":{"spread_cost":0.0005,"impact":[[0.0,0.0,0.0,0.0,0.0,0.0,0.0],[0.0012649110640673518,0.0008944271909999159,0.0006324555320336759,0.00044721359549995795,0.000282842712474619,0.0002,0.0001414213562373095],[0.004,0.00282842712474619,0.002,0.001414213562373095,0.0008944271909999159,0.0006324555320336759,0.00044721359549995795],[0.012649110640673518,0.00894427190999916,0.006324555320336759,0.00447213595499958,0.00282842712474619,0.002,0.001414213562373095],[0.0282842712474619,0.02,0.01414213562373095,0.01,0.006324555320336759,0.00447213595499958,0.0031622776601683794]],"timing_risk":[0.009497411928169344,0.013431368756261094,0.01899482385633869,0.02686273751252219,0.042473717363408006,0.06006690713973322,0.08494743472681601],"total_cost":[[0.009997411928169345,0.013931368756261093,0.01949482385633869,0.027362737512522186,0.04297371736340801,0.06056690713973322,0.08544743472681601],[0.011262322992236696,0.01482579594726101,0.020127279388372363,0.027809951108022146,0.043256560075882626,0.06076690713973322,0.08558885608305332],[0.013997411928169345,0.016759795881007285,0.021494823856338687,0.028776951074895283,0.04386814455440792,0.06119936267176689,0.08589464832231597],[0.02264652256884286,0.02287564066626025,0.02581937917667545,0.031834873467521764,0.045802144488154194,0.06256690713973322,0.0868616482891891],[0.03828168317563124,0.03393136875626109,0.03363695948006964,0.037362737512522184,0.049298272683744766,0.0650390430947328,0.0886097123869844]],"optimal_horizon":[0.0,0.033296204103657516,0.10529184240540287,0.3329620410365751,0.7445257576848565],"min_cost":[0.0005,0.007432065039494839,0.012827148528784324,0.022421114413228763,0.03327971172083256]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"liqcurve_j-0004","operation":"liq.curve.cost","inputs":{"half_spread_bps":5.0,"daily_volume":10000000.0,"daily_vol":0.02,"sizes":[200000.0,800000.0],"horizons_days":[1,3,10],"exponent":0.6,"coefficient":0.7,"risk_multiplier":2.0},"expected":{"status":"ok","outputs":{"spread_cost":0.0005,"impact":[[0.0013388934997060518,0.0006925853171542942,0.00033631484151480076],[0.00307596952125713,0.0015911432290204748,0.0007726486104182804]],"timing_risk":[0.023094010767585032,0.04,0.07302967433402215],"total_cost":[[0.024932904267291084,0.04119258531715429,0.07386598917553695],[0.02666998028884216,0.042091143229020474,0.07430232294444043]],"optimal_horizon":[0.08864653018445377,0.18882439416544636],"min_cost":[0.013105836480285135,0.01889796755844958]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"liqcurve_j-0005","operation":"liq.curve.cost","inputs":{"half_spread_bps":5.0,"daily_volume":10000000.0,"daily_vol":0.02,"sizes":[100000.0],"horizons_days":[1,2],"exponent":1.0,"risk_multiplier":1.0},"expected":{"status":"ok","outputs":{"spread_cost":0.0005,"impact":[[0.0002,0.0001]],"timing_risk":[0.011547005383792516,0.016329931618554522],"total_cost":[[0.012247005383792515,0.016929931618554522]],"optimal_horizon":[0.10626585691826111],"min_cost":[0.006146216173286171]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"liqcurve_j-0006","operation":"liq.curve.cost","inputs":{"half_spread_bps":5.0,"daily_volume":10000000.0,"daily_vol":0.0,"sizes":[100000.0,400000.0],"horizons_days":[1.0,4.0],"risk_multiplier":1.0},"expected":{"status":"ok","outputs":{"spread_cost":0.0005,"impact":[[0.0,0.0],[0.0,0.0]],"timing_risk":[0.0,0.0],"total_cost":[[0.0005,0.0005],[0.0005,0.0005]],"optimal_horizon":null,"min_cost":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
{"case_id":"liqcurve_j-0007","operation":"liq.curve.cost","inputs":{"half_spread_bps":5.0,"daily_volume":10000000.0,"daily_vol":0.02,"sizes":[100000.0,400000.0],"horizons_days":[1.0,4.0],"coefficient":0.0,"risk_multiplier":1.0},"expected":{"status":"ok","outputs":{"spread_cost":0.0005,"impact":[[0.0,0.0],[0.0,0.0]],"timing_risk":[0.011547005383792516,0.023094010767585032],"total_cost":[[0.012047005383792516,0.023594010767585032],[0.012047005383792516,0.023594010767585032]],"optimal_horizon":null,"min_cost":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["reference-computed"]}
```

## Outside-library evidence and limits (from the project's own page)

7 golden cases with status ok in `datasets/golden/stage_j` for `liq.curve.cost`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| liq.curve.cost: hand, reference-computed | 2 |
| liq.curve.cost: reference-computed | 5 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No official liquidity curve exists to reconcile against. The recorder keeps free crypto order-book snapshots (tools/recorder), which could feed a method test but not a reconciliation.

## Rulings that name this curve's operations

- (stage-j-rulings-curves.md) | J-C-1 | Operations and contract | Adds `repo.term.curve`, `eq.forward.term_financed` (`02-curves/financing-term-structure.md`) and `liq.curve.cost` (`10-execution/liquidity-curve.md`). No new error code; the general per-array limit applies. Contract 1.15.0 (new operations are a minor version), reported by all four builds and expected by the runner. **Coordinator:** the stage J wave 3 lane may also take 1.15.0; at merge keep one number for the union (1.15.0 if only one lane bumped by then, else 1.16.0 for the later merge) and update `conformance/runner/runner.py`, `stub_cli.py`, the four `version` writers and the version tests in one commit |
- (stage-j-rulings-curves.md) | J-C-8 | Optimal horizon and stage H reuse | `h* = (2 delta a / b)^{1/(delta + 1/2)}` with `a = Y sigma (Q/V)^delta`, `b = z sigma / sqrt 3`; `null` outputs when `b = 0` or `Y = 0`; `h* = 0`, `c* = s` for `Q = 0`. Stage H must keep `exec.impact.sqrt(Q, V, sigma, Y)` equal to this curve's impact at `h = 1`, `delta = 1/2`, and should build its pre-trade cost estimate (H-17) on `liq.curve.cost` rather than a second formula |
