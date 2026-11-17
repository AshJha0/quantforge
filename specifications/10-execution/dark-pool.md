# Simulated dark pool, fill probability and adverse selection (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1b). Status: Specified, not implemented. Rulings HR-32 to HR-36. Plan items 15.1 "Dark pools (simulated)", 14.7 H-4. **Every output is labelled "simulated venue; not a real dark pool". No real dark-pool data is used; crypto venues are lit only.**

**Plain idea.** Buy and sell orders that nobody can see wait in the pool; when both sides are present and each side's minimum size is met, they trade at the lit market's midpoint. A trader who sends an order to the pool risks not trading, and the trades it does get are more likely to come just before the price moves against it.

## Sources
- [IEX-OT] IEX order types page (see `lit-matching.md`), read 2026-11-17: midpoint peg is non-displayed and pegged to the NBBO midpoint subject to the limit. Venue documentation.
- [GKNV09] K. Ganchev, M. Kearns, Y. Nevmyvaka, J. W. Vaughan, "Censored exploration and the dark pool problem", Proc. UAI 2009, pp. 185-194; arXiv:1205.2646, PDF read 2026-11-17. Paper, read. Verified: section 2, at each step V^t units are split over K venues; venue i consumes r_i = min(s_i, v_i) with s_i drawn from an unknown P_i; r_i = v_i is a censored observation; T_i(s) = sum over s' >= s of P_i(s'); section 3, greedy one-unit-at-a-time allocation on estimated tails maximises expected units filled; estimates are "optimistic tail modifications" of the Kaplan-Meier estimator.
- [CST10] R. Cont, S. Stoikov, R. Talreja, "A stochastic model for order book dynamics", *Operations Research* 58(3) (2010) 549-563, DOI 10.1287/opre.1090.0780 (journal record from Crossref, read 2026-11-17); free copy https://www.columbia.edu/~ww2040/orderbook.pdf read 2026-11-17 (preprint page numbers). Paper, read. Verified: section 2.2, limit orders at distance i arrive at rate lambda(i), market orders at rate mu, each order at level i cancels so the level cancels at rate theta(i) x; section 4.3, Proposition 5 gives the probability an order at the bid executes before the mid moves, via Laplace transforms (eqs. 13-14). Journal pages not checked against the publisher (preprint read).
- H. Zhu, "Do dark pools harm price discovery?", *RFS* 27(3) (2014): **not read** (MIT copy 404, SSRN 403 on 2026-11-17). Cited only as background in the README of this lane; no ruling rests on it.

## Pool model (operation `exec.sim.dark.run`)
- Reference price: the mid of a lit book supplied per event (from `exec.sim.lit.run` or a replayed crypto book, the latter labelled "lit mid from crypto venue; dark pool simulated").
- Orders: `id`, `side`, `qty`, `limit` (optional), `min_qty` (default 1 lot), `kind` `FIRM` | `CONDITIONAL`.
- Crossing (HR-32): at each event, if mid exists and is within both orders' limits, cross at mid (on the half tick if needed: the pool prices in half ticks, HR-32). Priority: `seq` among eligible orders (time priority; no size priority in wave 1b). A contra pairing is eligible only if the fill quantity `min(open_a, open_b)` is at least each order's `min_qty` (HR-33; a minimum applies per fill, not cumulatively). Locked or crossed lit book: no crossing.
- Conditional orders (HR-34): rest without commitment; when a match is found the pool sends an invitation; the owner firms up with probability `p_firm` (input, default 0.8) after a delay of `firm_delay` events; on failure the conditional is suspended for `penalty_events`. The firm-up draw uses `core.rng` with the given seed. This is a stylised version of conditional-order mechanics; no venue's rules are claimed.

## Fill-probability models
1. **Censored tail estimate per venue** ([GKNV09]): from per-step observations `(v_i, r_i)`, the Kaplan-Meier tail `T_i(s)` with the paper's optimistic modification; output `P(fill >= s)` for s = 1..V. Used by the router.
2. **Queue model for lit passive orders** ([CST10]): probability that a bid order with `q` ahead executes before the mid moves, from Proposition 5 with planted `lambda(i)`, `theta(i)`, `mu`; computed by numerical Laplace inversion (Gaver-Stehfest, HR-35) and checked against Monte Carlo of the same birth-death model.

## Adverse selection (markouts)
For each fill, markout at horizons h in {1 s, 10 s, 60 s} (or event counts in pure simulation): `side_sign x (mid(t + h) - fill_price) / fill_price` in bp (positive is good for us). Information leakage in the simulator (HR-36): an informed flow with planted fraction `alpha` sends orders on the side of a planted future mid jump `J`; pool markouts must recover the planted expected adverse move `alpha x J` within 3 SE (H-4 known-truth test).

## Errors
Non-positive qty or min_qty > qty `E_DOMAIN`; `p_firm` outside [0, 1] `E_DOMAIN`; event count over 10,000,000 `E_LIMIT`.

## Golden plan
| Case | Content | Expected | Check |
|---|---|---|---|
| dark_h-0001 | buy 100, sell 60, mid 100.05 | fill 60 at 100.05 | hand |
| dark_h-0002 | as 0001 with buy min_qty 80 | no fill | HR-33 |
| dark_h-0003 | limit below mid | no fill | hand |
| dark_h-0004 | conditional, p_firm 1 then 0 | fill; then no fill and suspension | HR-34 |
| dark_h-0005 | Kaplan-Meier on a hand table of censored and direct observations | tail values | OUTSIDE-CHECKED: `lifelines` KaplanMeierFitter on the same data (plain KM before the optimistic modification) |
| dark_h-0006 | [CST10] Prop. 5 at the paper's section 5 parameters | probability | OUTSIDE-CHECKED: the paper's printed table if one exists for Prop. 5; else Monte Carlo 10^6 paths within 3 SE |
| dark_h-0007 | markout of a single fill against a given mid path | bp values | hand |

Outside checks (HR-31): 0005 and 0006 by outside tools; 0001 to 0004 and 0007 by blind re-derivation (DR-H2). Rule citations do not count.

## Convergence and limit cases
| Limit | Behaviour | Check |
|---|---|---|
| Gaver-Stehfest terms (HR-35) | inversion error falls with terms until double-precision cancellation; 14 terms fixed | Prop. 5 value at 10, 12, 14, 16 terms published; 14-term value within 3 SE of 10^6-path Monte Carlo |
| Monte Carlo paths | SE falls like 1/sqrt(paths) | SE reported with every MC value |
| Kaplan-Meier with no censoring | equals the empirical tail | property test |
| Kaplan-Meier with all observations censored above s | tail at s stays 1 (no evidence of a cap); optimistic modification as [GKNV09] | dark_h-0005 and a property test |
| p_firm = 1 | conditionals behave as firm orders | dark_h-0004 |
| min_qty = qty on both sides | crossing only on exact size match | property test |

## Limitations
No real dark-pool data anywhere; the pool, its participants and leakage are simulated with planted parameters; no claim about any real venue. Midpoint taken from one lit book (no consolidated NBBO).
