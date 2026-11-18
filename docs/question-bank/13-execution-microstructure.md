# Question bank 13: Execution and microstructure

A learning set and knowledge check for stage H (v0.10.0). It is for two readers: someone meeting order execution and order books for the first time, and a practitioner who wants to check how QuantForge pins down the details (participation base, remainder rules, which quantity carries delay cost, priority rules). Each answer starts with the plain idea, then gives the rule as the spec states it, then a worked example where numbers help. Levels: foundation, practitioner, advanced. Try to answer before reading the answer.

The operations here are specified (spec version 0.1.0, confirmed 2026-11-18) but not merged, so no number below was produced by `quantforge_core`. Every worked-example number is a spec golden or arithmetic on one, and `docs/question-bank/verify/v13_execution_microstructure.py` recomputes each with the standard library and fails if the page differs. Inputs are synthetic or a paper's own test parameters. Crypto data is labelled "crypto venue; not equities or rates"; simulated venues are labelled simulated. The specs are in [`specifications/10-execution`](../../specifications/10-execution/README.md) and [`specifications/09-microstructure`](../../specifications/09-microstructure/README.md).

## Schedules

### Q13.1 Why cut a large order into slices at all?

*Level: foundation. Evidence: spec. Source: [Schedules](../../specifications/10-execution/schedules.md), [Tutorial 36](../getting-started/tutorial-36-slice-an-order.md)*

An order much larger than what trades at the best price moves the price against you if sent at once. Cutting it into child orders spread over time lets the book refill between them. The cost is time: the price can drift while the order is still being worked.

The spec offers three rules for the cut. TWAP spreads the order evenly over `N` time buckets; VWAP spreads it in proportion to an expected volume profile; POV trades a fixed share of the volume that actually prints. None of them decides how fast to trade overall; that is the Almgren-Chriss question (Q13.6).

The pitfall is reading a schedule as a cost estimate. A schedule only says how much to send when.

### Q13.2 You must send 1,000 units in 3 buckets, in whole units. What does `exec.schedule.twap` return, and why?

*Level: foundation. Evidence: golden. Source: [Schedules](../../specifications/10-execution/schedules.md), golden `sched_h-0001`*

`1000 / 3` is 333 with 1 left over. In UNITS mode the spec gives `floor(X/N)` to every slice and the remainder `X mod N` one unit at a time to the earliest slices (ruling HR-3).

**Worked example.** `[334, 333, 333]`, which sums to 1,000.

The pitfall is rounding each slice to the nearest unit: three slices of 333 sum to 999 and lose a unit. The remainder rule exists so the slices always sum to the order.

### Q13.3 How does the VWAP schedule break ties when it rounds to whole units?

*Level: practitioner. Evidence: golden. Source: [Schedules](../../specifications/10-execution/schedules.md), goldens `sched_h-0003`, `sched_h-0004`*

The profile is normalised, so slice `i` is `X w_i / sum w`. In UNITS mode the integer parts are taken first and the spare units go to the largest fractional remainders; equal remainders go to the earliest bucket (HR-3).

**Worked example.** 1,000 on the profile `[1, 2, 3, 4]` in CONTINUOUS mode is `[100, 200, 300, 400]` (`sched_h-0003`). 10 units on `[1, 1, 1]` is 3.333 each; the three remainders tie, so the first bucket gets the spare unit: `[4, 3, 3]` (`sched_h-0004`).

An all-zero profile has no shares to give and is `E_DOMAIN` (`sched_h-0008`). The pitfall is assuming the profile is forecast by the library: it is an input, and wave 1 does not forecast it.

### Q13.4 A POV order is set to 20 % participation. Outside traders print 1,000 units in a bucket. How much does the order trade there?

*Level: practitioner. Evidence: golden; design. Source: [Schedules](../../specifications/10-execution/schedules.md), ruling HR-4 (confirmed by DR-H4), golden `sched_h-0005`*

Participation is your share of all volume, your own fills included. If you trade `s` against outside volume `v`, then `s / (s + v) = p`, so `s = p v / (1 - p)`.

**Worked example.** `p = 0.2`: `0.2 / 0.8 x 1000 = 250`, and `250 / 1250 = 0.2` exactly. In `sched_h-0005` the order is 1,000 against outside volumes `[1000, 2000, 4000]`: the slices are 250 and 500, and the third would be 1,000 but only 250 remain, so it is capped: `[250, 500, 250]`, residual 0.

The pitfall is `p v`, which gives 200 and a realised participation of `200 / 1200 = 16.7 %`, below the target.

### Q13.5 A POV order ends the day unfilled. Is that an error?

*Level: foundation. Evidence: golden. Source: [Schedules](../../specifications/10-execution/schedules.md), goldens `sched_h-0006`, `sched_h-0007`*

No. POV promises a participation rate, not completion. When the market is thin, the order trades its share of what prints and the rest is reported as `residual`.

**Worked example.** 1,000 at `p = 0.1` against `[900, 900]`: each slice is `0.1 / 0.9 x 900 = 100`, filled 200, residual 800 (`sched_h-0006`).

`p = 1` is `E_DOMAIN` (`sched_h-0007`): no finite order can be all of a volume that includes outside trades.

## Almgren-Chriss

### Q13.6 In plain terms, what trade-off does Almgren-Chriss solve?

*Level: foundation. Evidence: literature. Source: [Almgren-Chriss](../../specifications/10-execution/almgren-chriss.md), [AC00] read in the December 2000 preprint*

Trading fast costs impact; trading slowly leaves you exposed to price moves while you still hold the position. Almgren and Chriss write the expected cost `E` and its variance `V` for any schedule and choose the schedule that minimises `E + lambda V`, with `lambda` the trader's risk aversion. With linear impact the answer is a holdings path that decays like a hyperbolic sine: more selling early, less later.

At `lambda = 0` the trader ignores risk and the best schedule is the straight line, the same as TWAP (ruling HR-5).

### Q13.7 Using the paper's test parameters, what are the expected cost and variance of the straight-line schedule?

*Level: practitioner. Evidence: golden. Source: [Almgren-Chriss](../../specifications/10-execution/almgren-chriss.md), golden `ac_h-0001`*

`X = 1e6`, `T = 5`, `N = 5` (so `tau = 1`), `sigma = 0.95`, `epsilon = 0.0625`, `eta = 2.5e-6`, `gamma = 2.5e-7` ([AC00] Table 1, p. 25). `eta_tilde = eta - gamma tau / 2 = 2.375e-6`.

**Worked example.** `E = 1/2 gamma X^2 + epsilon X + eta_tilde X^2 / T = 125,000 + 62,500 + 475,000 = 662,500`. `V = sigma^2 tau X^2 (N - 1)(2N - 1) / (6N) = 0.9025e12 x 1.2 = 1.083e12`.

The pitfall is the continuous-time variance `sigma^2 X^2 T / 3`, which gives 1.504e12 here: the discrete grid matters at `N = 5`.

### Q13.8 At `lambda = 1e-6`, how much of the position is left after the first day, and what does risk aversion cost?

*Level: practitioner. Evidence: golden. Source: [Almgren-Chriss](../../specifications/10-execution/almgren-chriss.md), goldens `ac_h-0002`, `ac_h-0005`*

`kappa` solves `2 (cosh(kappa tau) - 1) = tau^2 lambda sigma^2 / eta_tilde`, so `cosh(kappa) = 1.19`, and holdings are `X sinh(kappa (T - t)) / sinh(kappa T)`.

**Worked example.** `kappa = 0.6070761632`; after day 1, 541,955.5544 shares are left (against 800,000 on the straight line). `E = 911,226.986`, `V = 3.641285721e11`. So about 249,000 dollars of expected cost buys a variance one third as large. The paper prints `kappa` "about 0.6/day, so kappa T about 3" (p. 24); `kappa T = 3.0353808` (`ac_h-0005`).

The pitfall is comparing `lambda` across different position sizes: it has units of one over dollars.

### Q13.9 Why does selling everything in one step at the same parameters give a lower expected cost (562,500) than the five-step straight line (662,500)?

*Level: advanced. Evidence: golden. Source: [Almgren-Chriss](../../specifications/10-execution/almgren-chriss.md), golden `ac_h-0004`*

Because `eta_tilde = eta - gamma tau / 2` depends on the step length. With `N = 1`, `tau = 5` and `eta_tilde = 2.5e-6 - 2.5e-7 x 5 / 2 = 1.875e-6`, so `E = 125,000 + 62,500 + 375,000 = 562,500`.

This is a property of the discrete model's correction for permanent impact within a step, not a claim that one block is cheap in practice. The pitfall is reusing the `tau = 1` value of `eta_tilde`, which gives 662,500 by mistake.

## Shortfall

### Q13.10 What are the four parts of implementation shortfall in QuantForge, and which quantity carries the delay cost?

*Level: foundation. Evidence: spec; design. Source: [TCA](../../specifications/10-execution/tca.md), ruling HR-8 (confirmed by DR-H3)*

Shortfall compares what you got with a paper portfolio that traded the whole order at the decision price. The spec splits it as: delay `s Q (P_0 - P_d)` on the filled quantity `Q`; execution `s sum q_i (p_i - P_0)` against the arrival price; opportunity `s (X - Q)(P_c - P_d)` on the unfilled part; plus fees. `s` is +1 for a buy and -1 for a sell.

Delay is charged on the filled quantity only, and the unfilled part's whole move goes to opportunity cost (Perold's split). A full-order delay, as in some textbook variants, is not offered, so reports built that way will not reconcile line by line.

### Q13.11 A buy of 1,000 is decided at 100, arrives at 100.10, fills 600 at 100.20 and 200 at 100.30, ends at 101, with fees of 5. Decompose the shortfall.

*Level: practitioner. Evidence: golden. Source: [TCA](../../specifications/10-execution/tca.md), golden `tca_h-0001`*

**Worked example.** Delay `800 x 0.10 = 80`; execution `600 x 0.10 + 200 x 0.20 = 100`; opportunity `200 x (101 - 100) = 200`; total `80 + 100 + 200 + 5 = 385`, which is `385 / (1000 x 100) x 1e4 = 38.5` bp.

For a seller with the same prices and fills and no fees, every part flips sign: total -380 (`tca_h-0002`). The pitfall is dividing by the filled value instead of `X P_d`.

## Impact

### Q13.12 What does the square-root law say, and what do QuantForge's square-root goldens prove?

*Level: foundation. Evidence: golden; literature. Source: [Impact](../../specifications/10-execution/impact.md), [TLD11] eq. (1), goldens `imp_h-0001`, `imp_h-0002`*

The average relative price move over an order of `Q` units is `I = Y sigma sqrt(Q / V)`, with `V` the daily volume, `sigma` the daily volatility and `Y` a coefficient the paper calls of order one.

**Worked example.** `Q = 1e5`, `V = 1e7`, `sigma = 0.02`, `Y = 1`: `0.02 x sqrt(0.01) = 0.002`, 20 bp. Four times the size, `4e5`, gives 0.004: twice the impact.

The goldens prove the arithmetic of the stated form with `Y` supplied, nothing more. Whether a market follows the law, with what `Y` and exponent, is an empirical question for the crypto study, which will report a venue-level proxy with a standard error.

### Q13.13 In the Obizhaeva-Wang model, what is the risk-neutral optimal schedule, and what happens as resilience goes to zero?

*Level: advanced. Evidence: golden; literature. Source: [Impact](../../specifications/10-execution/impact.md), [OW13] Proposition 3, eq. (31), p. 17, goldens `imp_h-0003`, `imp_h-0004`*

A block at the start, a constant rate in between, and an equal block at the end: each block is `X / (rho T + 2)` and the rate `rho X / (rho T + 2)`, where `rho` is the rate at which the book refills.

**Worked example.** `X = 1000`, `T = 1`, `rho = 8`: blocks of 100, rate 800 (`imp_h-0003`). On the paper's Fig. 2 parameters, `X = 1e5`, `rho = 2.231`: blocks of 23,635.0744504845 and rate 52,729.8510990310 (`imp_h-0004`).

As `rho` goes to 0 each block tends to `X/2`: with no refill there is no reason to trade in between. The strategy does not depend on the size of impact or the book depth ([OW13] section 7.1).

## Market making and order books

### Q13.14 A market maker is long 2 units. How do the Avellaneda-Stoikov quotes move, and by how much?

*Level: practitioner. Evidence: golden; literature. Source: [Avellaneda-Stoikov](../../specifications/09-microstructure/avellaneda-stoikov.md), [AS08] eqs. (29), (30), p. 221, golden `as_h-0001`*

Long inventory is risk, so both quotes move down to sell more readily. The reservation price is `r = s - q gamma sigma^2 (T - t)` and the total spread `gamma sigma^2 (T - t) + (2/gamma) ln(1 + gamma/k)`.

**Worked example.** `s = 100`, `q = 2`, `gamma = 0.1`, `sigma = 2`, one unit of time left, `k = 1.5`: `r = 100 - 2 x 0.1 x 4 = 99.2`; spread `0.4 + 20 ln(16/15) = 1.6907704228`; bid 98.3546147886, ask 100.0453852114.

These are the paper's approximate solution (an expansion in inventory), not an exact solution. The pitfall is the sign: a short book raises both quotes.

### Q13.15 How were the Avellaneda-Stoikov goldens checked against the paper, when the paper prints only simulated averages?

*Level: advanced. Evidence: golden; literature. Source: [Avellaneda-Stoikov](../../specifications/09-microstructure/avellaneda-stoikov.md), goldens `as_h-0005` to `as_h-0007`*

The spread is linear in time left and does not depend on inventory, so its average over the horizon equals its value half way. The paper's Tables 1 to 3 print the average spread of its simulated strategy for three risk aversions.

**Worked example.** At half the horizon the formula gives 1.4907704228, 1.3489085437 and 3.0216512475 for `gamma` 0.1, 0.01 and 1; the paper prints 1.49, 1.35 and 3.02. The tolerance is 0.005: two printed decimals, and the paper averages a simulation on a grid.

The pitfall is comparing to the spread at the start of the horizon, which is wider.

### Q13.16 In the simulated lit engine, three bids rest at one price and a sell arrives that fills one and a half of them. Which bids fill?

*Level: foundation. Evidence: spec. Source: [Lit matching](../../specifications/10-execution/lit-matching.md), planned golden `lit_h-0001`, ruling HR-25*

Price-time priority: best price first, then arrival order within a price. At one price, the first two bids by arrival sequence `seq` fill, the first in full and the second in part; the third is untouched. A quantity decrease keeps an order's place; a price change or a quantity increase sends it to the back (CME's FIFO steps).

The engine is a simulated venue; every output says so. The pitfall is assuming a real venue uses the same rules: QuantForge borrows definitions from venue documentation but reproduces no venue's rule book.

### Q13.17 The recorded Kraken book is a once-a-second snapshot of the recorder's own book. What can the book check claim, and what can it not?

*Level: advanced. Evidence: spec; design. Source: [Order book](../../specifications/09-microstructure/order-book.md), rulings HR-11, HR-13*

Each snapshot row carries an `ok` flag: whether the recorder's top 10 levels matched Kraken's CRC32 checksum at the last update before the row. So the check can claim "the recorder's book agreed with the venue checksum on X % of seconds", with X stated. It cannot claim that the book equals the venue below level 10, because the checksum covers the top 10 only, and it cannot see changes within a second.

Raw message-by-message data exists for one 14-minute sample (2026-11-17 20:29 to 20:43 UTC), where the full check runs as a demonstration. Results are labelled "crypto venue; not equities or rates", and only aggregates are published.

### Q13.18 Why does QuantForge have no market-by-order data from a real venue?

*Level: foundation. Evidence: design. Source: [Order book](../../specifications/09-microstructure/order-book.md), [KR-L3]; plan 11.4*

Kraken's order-by-order (level 3) channel needs an API token, and the project takes no accounts, keys or cards. So the only real book is market by price (quantity per level, 100 levels per side from 2026-11-17 20:15 UTC). Market by order, with each order in its queue, exists only inside the simulated venues.

The pitfall is reading queue position or fill probability off market-by-price data: it does not show who is ahead of you.

Back to the [question bank index](README.md).
