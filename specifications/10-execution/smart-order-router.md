# Smart order router over simulated venues

Spec version 0.1.0 (stage H wave 1b; confirmed 2026-11-18 by the stage H coordinator). Status: implemented in the Python build (2026-11-18); other builds pending. Rulings HR-37 to HR-40. Plan items 15.1 "Smart order router (simulated)", 14.7 H-4. **Labelled "simulated venues; router scored in simulation only".**

**Plain idea.** To buy S units, send some as a market order now and post limit orders at several venues, more in total than needed if fills are uncertain; choose the split that minimises expected cost including fees, rebates, the risk of filling too little or too much, and impact.

## Sources
- [CK] R. Cont, A. Kukanov, "Optimal order placement in limit order markets", arXiv:1210.1625v4 (revised October 2014), HTML and PDF read 2026-11-17 (39 pp.). Paper, read. Published as *Quantitative Finance* 17(1) (2017) 21-39, DOI 10.1080/14697688.2016.1190030 (journal record from Crossref, read 2026-11-17); section and equation numbers below are the arXiv v4 numbering, not checked against the journal version. Verified: section 2, decision X = (M, L_1..L_K) >= 0; queue ahead Q_k; outflow xi_k (cancellations plus marketable orders); filled on venue k = (xi_k - Q_k)_+ - (xi_k - Q_k - L_k)_+; executed A = M + sum of those (eq. 1); cost (Definition 2.1, eq. 5) v(X, xi) = (h + f) M - sum_k (h + r_k)[fill_k] + theta (M + sum_k L_k + (S - A)_+) + lambda_u (S - A)_+ + lambda_o (A - S)_+, with h the half spread, f the taker fee, r_k the effective rebate (exchange rebate plus an adverse-selection term), theta impact, lambda_u, lambda_o the under- and overfill penalties; problem: minimise V(X) = E v(X, xi). Proposition 3 (single venue, under A1-A3): (M, L) = (0, S) if lambda_u <= (2h + f + r)/F(Q + S) - (h + r + theta); (S, 0) if lambda_u >= (2h + f + r)/F(Q) - (h + r + theta); otherwise M* = S - F^{-1}((2h + f + r)/(lambda_u + h + r + theta)) + Q, L* = S - M*. Section 4: stochastic-approximation algorithm for K venues from fill samples.
- [GKNV09] dark allocation (see `dark-pool.md`).

## Operation `exec.sor.allocate`
Inputs: `S` (lots), `h`, `f`, per venue `k`: `kind` LIT | DARK, `Q_k`, `r_k` (exchange rebate; positive is paid to us), `as_k` (adverse-selection charge, subtracted to give the effective rebate, HR-37), outflow distribution of `xi_k` as a sample list (lit) or the [GKNV09] tail `T_k` (dark), `theta`, `lambda_u`, `lambda_o`, `method` `CLOSED_FORM` (K = 1 lit only) | `SAMPLE_AVERAGE` | `STOCHASTIC_APPROX`, `seed`.
Outputs: `M`, `L[k]` (integer lots, HR-38), expected cost and its MC standard error, expected fill, P(underfill).
- `CLOSED_FORM`: Proposition 3 with the empirical left-inverse quantile of the sample.
- `SAMPLE_AVERAGE` (HR-39): minimise the sample mean of eq. 5 over the integer grid by coordinate descent from the [CK] single-venue solution; exact for the stated samples, used for goldens.
- `STOCHASTIC_APPROX`: [CK] section 4 iteration, step size and iteration count as inputs, iterates averaged; property-tested to approach `SAMPLE_AVERAGE` on the same samples.
- Dark venues: a dark allocation `D_k` fills min(D_k, s_k), no queue; it enters eq. 5 as an extra fill term with rebate `r_k - as_k` and the half spread earned (midpoint, so h) (HR-37).

Errors: S <= 0, negative sizes or penalties `E_DOMAIN`; empty sample `E_INPUT`; more than 64 venues or 10^6 samples `E_LIMIT`.

## Scoring against single-venue routing (fixed before any run)
On the simulated multi-venue world (two lit engines from `lit-matching.md` with different fees and queues, one dark pool from `dark-pool.md`, planted flow, seed 20261117, 10,000 parent orders): report the mean cost per unit (bp of arrival mid) and fill rate for (a) the router, (b) each single venue with the same S and the [CK] single-venue rule, (c) market order only. Difference router minus best single venue with a paired standard error. Pass for H-4 is the method test (the router's chosen split recovers the planted optimum computed by `SAMPLE_AVERAGE` on the true distribution within 3 SE of cost); the comparison itself is a result, published whatever it shows, not a gate (HR-40).

## Golden plan
| Case | Content | Expected | Check |
|---|---|---|---|
| sor_h-0001 | K = 1, lambda_u below the lower threshold | (0, S) | hand from Prop. 3 (i) |
| sor_h-0002 | K = 1, lambda_u above the upper threshold | (S, 0) | Prop. 3 (ii) |
| sor_h-0003 | K = 1, interior, discrete xi sample | M*, L* | Prop. 3 (iii) by hand; SAMPLE_AVERAGE must agree |
| sor_h-0004 | K = 2 at [CK] section 4.2 numerical-example parameters | allocation near the paper's Figure 4 | OUTSIDE-CHECKED (figure-read tolerance, stated) if the parameters are fully given in the paper; else hand |
| sor_h-0005 | one lit, one dark with hand tails | integer split | hand, exhaustive enumeration |

Outside checks (HR-31): every value case by blind re-derivation (DR-H2) from the inputs and [CK] alone; 0004 also against the paper's figure where its parameters are fully given.

## Convergence and limit cases
| Limit | Behaviour | Check |
|---|---|---|
| `STOCHASTIC_APPROX` iterations | averaged iterate approaches the `SAMPLE_AVERAGE` optimum; cost gap reported at 10^3, 10^4, 10^5 iterations | property test: gap non-increasing in the reported sequence and below 1 SE of cost at 10^5 |
| K = 1 | `SAMPLE_AVERAGE` equals Prop. 3 of [CK] | sor_h-0001 to 0003 |
| lambda_u large | all market order (Prop. 3 (ii)) | sor_h-0002 |
| lambda_u small, ample outflow | all limit (Prop. 3 (i)) | sor_h-0001 |
| sample size | expected cost SE falls like 1/sqrt(samples) | SE reported with every cost |
| integer rounding | exhaustive floor/ceiling search (HR-38) | sor_h-0005 enumeration |

## Golden value cases (stage H wave 2, DR-H2 blind lane)

Written 2026-11-18 by the spec lane. Method `SAMPLE_AVERAGE` (HR-39), exact over the stated samples. sor_h-0004 ([CK] section 4.2 parameters) is not written here: it needs the paper's figure and stays with the outside check. sor_h-0006 is the hand-checked two-venue expected-cost ordering case. Canonical JSON as in `lit-matching.md` (HR-12, HR-29).

Harness conventions (fixed before the blind lane starts):
- Inputs: `S`, `h`, `f`, `theta`, `lambda_u`, `lambda_o`, `venues` (in order; LIT: `Q`, `r`, `as`; DARK: `r`, `as`, `tail` = [T(1), ..., T(n)] with T(s) = P(s_k >= s) and T(s) = 0 beyond n), `lit_samples` (rows of joint outflow draws, one value per LIT venue in venue order, equally weighted). Dark draws are independent of each other and of the rows.
- Cost per scenario is eq. 5 of [CK]: (h + f) M - sum over venues of (h + r_k - as_k) fill_k + theta (M + sum_k L_k + (S - A)_+) + lambda_u (S - A)_+ + lambda_o (A - S)_+; LIT fill = (xi - Q)_+ - (xi - Q - L)_+; DARK fill = min(L, s) (HR-37; the dark allocation is counted in the theta term as posted size); A = M + sum of fills.
- Search: every integer (M, L_1, ..., L_K) with each coordinate in 0..S (HR-38: exhaustive); lowest expected cost wins; ties go to the lexicographically smallest tuple.
- Output: `M`, `L` (list in venue order), `expected_cost`, `expected_fill` (E min(A, S)), `p_underfill` (P(A < S)), each rounded half-even to 6 decimal places, trailing zeros removed. The MC standard error is not part of the golden (the sample is the population here). sor_h-0006 adds `ranking`: every tuple with its expected cost, ordered by cost then tuple; it is asked for by the input flag `"ranking":true` (shape fixed 2026-11-18 by the H-13 implementation lane, which needs an input that selects the extra output; no value changed).

| Case | Input | Expected |
|---|---|---|
| sor_h-0001 | {"S":"10","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"0.1","lit_samples":[["10"],["12"],["15"]],"theta":"0","venues":[{"Q":"0","as":"0","kind":"LIT","r":"0.2"}]} | {"L":["10"],"M":"0","expected_cost":"-7","expected_fill":"10","p_underfill":"0"} |
| sor_h-0002 | {"S":"10","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"10","lit_samples":[["0"],["0"],["0"],["2"]],"theta":"0","venues":[{"Q":"0","as":"0","kind":"LIT","r":"0.2"}]} | {"L":["0"],"M":"10","expected_cost":"8","expected_fill":"10","p_underfill":"0"} |
| sor_h-0003 | {"S":"10","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"4","lit_samples":[["0"],["2"],["4"],["6"],["8"],["10"],["12"],["14"]],"theta":"0","venues":[{"Q":"2","as":"0","kind":"LIT","r":"0.2"}]} | {"L":["2"],"M":"8","expected_cost":"7.35","expected_fill":"9.5","p_underfill":"0.25"} |
| sor_h-0005 | {"S":"4","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"1","lit_samples":[["0"],["4"]],"theta":"0","venues":[{"Q":"0","as":"0","kind":"LIT","r":"0.2"},{"as":"0.1","kind":"DARK","r":"0","tail":["0.5","0.5","0.5","0"]}]} | {"L":["4","3"],"M":"0","expected_cost":"0","expected_fill":"2.75","p_underfill":"0.5"} |
| sor_h-0006 | {"S":"2","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"1","lit_samples":[["0","1"],["2","3"]],"ranking":true,"theta":"0","venues":[{"Q":"0","as":"0","kind":"LIT","r":"0.3"},{"Q":"1","as":"0","kind":"LIT","r":"0.1"}]} | {"L":["2","0"],"M":"0","expected_cost":"0.2","expected_fill":"1","p_underfill":"0.5","ranking":[{"L":["2","0"],"M":"0","expected_cost":"0.2"},{"L":["1","1"],"M":"0","expected_cost":"0.3"},{"L":["0","2"],"M":"0","expected_cost":"0.4"},{"L":["2","1"],"M":"0","expected_cost":"0.4"},{"L":["1","2"],"M":"0","expected_cost":"0.5"},{"L":["2","2"],"M":"0","expected_cost":"0.6"},{"L":["1","0"],"M":"1","expected_cost":"0.9"},{"L":["0","1"],"M":"1","expected_cost":"1"},{"L":["2","0"],"M":"1","expected_cost":"1"},{"L":["1","0"],"M":"0","expected_cost":"1.1"},{"L":["1","1"],"M":"1","expected_cost":"1.1"},{"L":["0","1"],"M":"0","expected_cost":"1.2"},{"L":["0","2"],"M":"1","expected_cost":"1.2"},{"L":["2","1"],"M":"1","expected_cost":"1.2"},{"L":["1","2"],"M":"1","expected_cost":"1.3"},{"L":["2","2"],"M":"1","expected_cost":"1.4"},{"L":["0","0"],"M":"2","expected_cost":"1.6"},{"L":["1","0"],"M":"2","expected_cost":"1.7"},{"L":["0","0"],"M":"1","expected_cost":"1.8"},{"L":["0","1"],"M":"2","expected_cost":"1.8"},{"L":["2","0"],"M":"2","expected_cost":"1.8"},{"L":["1","1"],"M":"2","expected_cost":"1.9"},{"L":["0","0"],"M":"0","expected_cost":"2"},{"L":["0","2"],"M":"2","expected_cost":"2"},{"L":["2","1"],"M":"2","expected_cost":"2"},{"L":["1","2"],"M":"2","expected_cost":"2.1"},{"L":["2","2"],"M":"2","expected_cost":"2.2"}]} |

## Limitations
One-period model (place at 0, clean up at T) as in [CK]; no re-routing within the period; distributions are inputs, not estimated live. Simulated venues only; crypto venues are lit, single-venue in our data, and are not routed across.
