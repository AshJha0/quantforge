# Question bank 13: Execution and microstructure

A learning set and knowledge check for stage H (v0.10.0). It is for two readers: someone meeting order execution and order books for the first time, and a practitioner who wants to check how QuantForge pins down the details (participation base, remainder rules, which quantity carries delay cost, priority rules). Each answer starts with the plain idea, then gives the rule as the spec states it, then a worked example where numbers help. Levels: foundation, practitioner, advanced. Try to answer before reading the answer.

The operations here are implemented in all four languages from v0.10.0 (spec version 0.1.0, confirmed 2026-11-18; the `paper.*` operations included). The numbers below are spec goldens, which the builds reproduce in conformance; apart from the paper-trading book in Q13.19 to Q13.21, none was printed by `quantforge_core` for this page. Every worked-example number is a spec golden or arithmetic on one, and `docs/question-bank/verify/v13_execution_microstructure.py` recomputes each with the standard library and fails if the page differs. Inputs are synthetic or a paper's own test parameters. Crypto data is labelled "crypto venue; not equities or rates"; simulated venues are labelled simulated. The specs are in [`specifications/10-execution`](../../specifications/10-execution/README.md) and [`specifications/09-microstructure`](../../specifications/09-microstructure/README.md).

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

*Level: foundation. Evidence: spec; golden. Source: [Lit matching](../../specifications/10-execution/lit-matching.md), golden `lit_h-0001`, ruling HR-25*

Price-time priority: best price first, then arrival order within a price. At one price, the first two bids by arrival sequence `seq` fill, the first in full and the second in part; the third is untouched. A quantity decrease keeps an order's place; a price change or a quantity increase sends it to the back (CME's FIFO steps).

The engine is a simulated venue; every output says so. The pitfall is assuming a real venue uses the same rules: QuantForge borrows definitions from venue documentation but reproduces no venue's rule book.

### Q13.17 The recorded Kraken book is a once-a-second snapshot of the recorder's own book. What can the book check claim, and what can it not?

*Level: advanced. Evidence: spec; design. Source: [Order book](../../specifications/09-microstructure/order-book.md), rulings HR-11, HR-13*

Each snapshot row carries an `ok` flag: whether the recorder's top 10 levels matched Kraken's CRC32 checksum at the last update before the row. So the check can claim "the recorder's book agreed with the venue checksum on X % of seconds", with X stated. It cannot claim that the book equals the venue below level 10, because the checksum covers the top 10 only, and it cannot see changes within a second.

Raw message-by-message data exists for one 14-minute sample (2026-11-17 20:29 to 20:43 UTC), where the full check runs as a demonstration, and for the one H-9 R2 timing window being recorded from 2026-11-19 11:41:24 UTC (HR-130). Results are labelled "crypto venue; not equities or rates", and only aggregates are published.

### Q13.18 Why does QuantForge have no market-by-order data from a real venue?

*Level: foundation. Evidence: design. Source: [Order book](../../specifications/09-microstructure/order-book.md), [KR-L3]; plan 11.4*

Kraken's order-by-order (level 3) channel needs an API token, and the project takes no accounts, keys or cards. So the only real book is market by price (quantity per level, 100 levels per side from 2026-11-17 20:15 UTC). Market by order, with each order in its queue, exists only inside the simulated venues.

The pitfall is reading queue position or fill probability off market-by-price data: it does not show who is ahead of you.

## Stage H wave 2: paper trading, estimators, venue analytics, adaptive algorithms, latency

Every operation here, paper trading (Q13.19 to Q13.21) included, is available in all four builds from v0.10.0. Numbers are spec goldens, checked by the verify script.

### Q13.19 A paper book buys 2 at 100 (fee 0.20) and sells 1 at 110 (fee 0.11), then closes the day at 105. Explain the day's P&L.

*Level: foundation. Evidence: golden. Source: [Paper trading](../../specifications/10-execution/paper-trading.md), [Tutorial 44](../getting-started/tutorial-44-paper-trading.md)*

The plain idea: split the change in the book's value into what the opening position did, what the day's trades did against the close, fees and financing, and make the parts add up exactly.

The rule (HR-53): `market = sum n_open (P_t - P_{t-1})`, `trading = sum s q (P_t - p)`, `fees = -sum f`, financing on opening balances; `total = NAV_t - NAV_{t-1}` with no residual. Here there is no opening position, so market is 0; trading is `2 x (105 - 100) + (-1) x (105 - 110) = 15`; fees -0.31; total 14.69, and NAV is `9909.69 + 105 = 10014.69` (`pt_h-0002`).

The pitfall is keeping a "residual" line. In this design a residual other than zero is a defect, and the code raises.

### Q13.20 How does the paper ledger show that a record was edited after it was written, and what can it not show?

*Level: practitioner. Evidence: spec; golden. Source: [Paper trading](../../specifications/10-execution/paper-trading.md), rulings HR-45, HR-46*

The plain idea: each record carries a fingerprint of itself and of the record before it, so changing any record changes its fingerprint and breaks the link to the next one.

The rule: `hash` is the SHA-256 of the record's canonical bytes (keys sorted, no whitespace, ASCII, numbers as strings except `seq`), and `prev` is the previous record's hash (64 zeros for the first). `verify` reports the first bad record and a reason: `HASH`, `LINK`, `SEQ`, `LABEL` or `PARSE`. Changing a limit price from 101 to 102 after writing gives `ok` false at record 0 with reason `HASH` (`pt_h-0021`).

What it cannot show: that the data was right when written, or that the last lines were not cut off. A truncated file is still a valid shorter chain; only comparing its head hash with the published one catches that (HR-46).

### Q13.21 An order to buy 11 at 100 meets limits of 10 per order, notional 1,000 and position 5. Which checks fail, and in what order are they reported?

*Level: foundation. Evidence: golden. Source: [Paper trading](../../specifications/10-execution/paper-trading.md), ruling HR-49*

All checks run, and every failure is reported in a fixed order: kill switch, orders per day, size, price band, notional, position, short sale, cash. Here size (11 > 10), notional (1,100 > 1,000) and position (11 > 5) fail, reported as `MAX_QTY`, `MAX_NOTIONAL`, `MAX_POSITION` (`pt_h-0011`). The rejection is a ledger record, not an error.

The pitfall is stopping at the first failure: the desk then fixes one limit, resubmits and fails again on the next.

### Q13.22 Twelve orders arrive in four seconds. What is the arrival rate, and how sure are you?

*Level: foundation. Evidence: golden. Source: `specifications/09-microstructure/micro-estimators.md` (available from v0.10.0), [Tutorial 45](../getting-started/tutorial-45-microstructure-estimators.md)*

For a Poisson count the rate is `N / T = 3` a second and its standard error `sqrt(lambda / T) = sqrt(0.75) = 0.866025403784439` (`mest_h-0001`). Three standard errors either side is roughly 0.4 to 5.6, so four seconds says little.

The estimator is trusted because it recovers a planted rate: 2.5 a second over 3,600 seconds must come back within 3 SE on a fixed seed, with at most 4 misses in 200 seeds (HR-70). The pitfall is quoting a rate without its SE.

### Q13.23 Venue A's fills have a markout of 0 at 5 seconds, yet a toxicity of two thirds. How can both be true?

*Level: practitioner. Evidence: golden. Source: `specifications/10-execution/venue-analytics.md` (available from v0.10.0), [Tutorial 46](../getting-started/tutorial-46-venue-analytics.md)*

Markout averages the signed move over all quantity; toxicity counts the quantity whose own move was against us. In `venue_h-0001`, a buy of 100 at 100.01 gains 0.04 a share (+4) and a sell of 200 at 100.03 loses 0.02 a share (-4) against the mid 100.05: they net to 0, but the 200 that lost is two thirds of the 300 traded.

At 10 seconds the same venue shows 2.33 bp and toxicity one third, while venue B goes from 5 bp to -2 bp (`venue_h-0002`). The pitfall is ranking venues on one horizon.

### Q13.24 Why does the arrival-price golden use an urgency of exactly ln 2?

*Level: practitioner. Evidence: spec; golden. Source: `specifications/10-execution/adaptive-algos.md` (available from v0.10.0)*

Because then every `sinh` in the holdings formula is rational: `sinh(ln 2) = 3/4`, `sinh(2 ln 2) = 15/8`, `sinh(3 ln 2) = 63/16`. The holdings `x_j = X sinh(kappa (N - j)) / sinh(kappa N)` ([AC00] eq. (17)) then come out exact: 1,000 over two buckets is 600 and 400 (`alg_h-0002`); 2,100 over three is 1,100, 600 and 400 (`alg_h-0004`). A golden that is exact by construction can be checked by hand and by a blind lane without arguing about the last digit.

The pitfall is choosing test inputs for realism alone; inputs chosen for checkability catch more bugs per case.

### Q13.25 A pre-trade estimate says 3.04 bp expected cost and 46.2 bp timing risk. Should you add them?

*Level: practitioner. Evidence: golden; spec. Source: `specifications/10-execution/tca-pretrade.md` (available from v0.10.0), ruling HR-64*

No. Expected cost is a mean; timing risk is one standard deviation of the price move while the order works, `1e4 sigma sqrt(T/3)` for a straight-line schedule ([AC00] eq. (10) as N grows). In `tcx_h-0001` (4 % of ADV, 2 % daily volatility, 25 % participation, 0.16 days) the risk is fifteen times the cost: the order's outcome is dominated by where the price goes, not by what trading costs on average. Trading faster lowers the risk and raises the impact; that trade-off is the Almgren-Chriss frontier.

The pitfall is reporting a single "cost" that mixes a mean with a standard deviation.

### Q13.26 The first H-9 run shows Rust `best_bid` p99 at 105 ns against a 50 ns target. What can you conclude?

*Level: advanced. Evidence: design; measured (laptop). Source: `specifications/09-microstructure/low-latency-targets.md`, [Tutorial 48](../getting-started/tutorial-48-low-latency-book.md)*

That it missed on that machine, and that the figure needs a better measurement before anyone optimises against it. The run was a laptop under WSL, not the acceptance machine; each query was timed singly, and a clock read alone costs about 17 ns at p50 in Rust, so a 50 ns target is close to the clock. Batch timing for queries (HR-21) was not run. The miss is published as a miss and the target is not moved (HR-23).

What it does show: updates met every target in both languages (C++ p50 39 ns, Rust 47 ns, against 150) with zero allocations and zero mismatches against the spec at 10,000 checkpoints. The pitfall is either hiding the miss or "fixing" it by moving the target.

## Stage H venues, book rebuild, conventions, checks and latency

Every venue in this part is simulated, and every venue output carries its label ("simulated venue; not a real dark pool", "simulated venue; not a real exchange", "simulated venues; router scored in simulation only"). The book rebuild runs on one crypto venue's public feed: "crypto venue; not equities or rates". Numbers are spec goldens in `datasets/golden/stage_h/`, rechecked by the verify script.

### Q13.27 A buy of 100 and a sell of 60 sit in the simulated dark pool while the lit book is 100.00 bid, 100.10 offered. What trades?

*Level: foundation. Evidence: golden; spec. Source: [Dark pool](../../specifications/10-execution/dark-pool.md), golden `dark_h-0001`, ruling HR-32*

The plain idea: a dark pool shows nobody its orders and trades only at a price it borrows from the lit market, usually the midpoint, so neither side pays the spread.

The rule (HR-32): after every event, if the lit book has a mid and the mid is within both orders' limits, the pool crosses at the mid. Buys are scanned in `seq` order and, for each, sells in `seq` order (time priority, no size priority); the fill is `min(open_buy, open_sell)`.

**Worked example.** The mid is `(100.00 + 100.10) / 2 = 100.05`. The pair fills 60 at 100.05; the buy rests with 40 open (`dark_h-0001`). The output is labelled "simulated venue; not a real dark pool".

The pitfall is reading "midpoint, no spread" as "no cost". The cost of a dark pool is the trade that does not happen and the trade that happens just before the price moves against you; the markouts in `dark_h-0007` measure the second.

### Q13.28 Repeat Q13.27 with a minimum quantity of 80 on the buy, then with a buy limit of 100.04. What changes?

*Level: practitioner. Evidence: golden; spec. Source: [Dark pool](../../specifications/10-execution/dark-pool.md), goldens `dark_h-0002`, `dark_h-0003`, rulings HR-32, HR-33*

The plain idea: a minimum quantity protects a large order from being found out by small fills; a limit protects it from a bad midpoint.

The rule: a pairing is eligible only if the fill `min(open_a, open_b)` is at least each order's `min_qty`, applied per fill and not cumulatively (HR-33). An order with a limit is eligible only while the mid is within it. The pool prices in half ticks, and a locked or crossed lit book has no mid, so nothing crosses.

**Worked example.** With `min_qty` 80 the only possible fill is 60, below 80, so nothing trades and both orders rest (`dark_h-0002`). With a buy limit of 100.04 the mid 100.05 is above the limit: no cross. When the book moves to 100.00 / 100.01 the mid is 100.005, half a tick, and 60 fill at 100.005; a later locked book 100.02 / 100.02 has no mid (`dark_h-0003`).

The pitfall is treating `min_qty` as a total: two fills of 50 do not satisfy a minimum of 80.

### Q13.29 A conditional buy of 50 meets a firm sell of 30. What happens when the owner firms up, and when it declines?

*Level: practitioner. Evidence: golden; spec. Source: [Dark pool](../../specifications/10-execution/dark-pool.md), golden `dark_h-0004`, ruling HR-34*

The plain idea: a conditional order sits in the pool without commitment. When a match appears the pool invites its owner, who may firm up and trade or decline; a decline costs the owner a spell out of the pool.

The rule (HR-34, a stylised model; no venue's rules are claimed): an invitation is recorded; the owner firms up with probability `p_firm` after `firm_delay` events, drawn from `core.rng`; on a decline the conditional is suspended for `penalty_events` events and nothing fills. The goldens use `p_firm` 1 and 0 so that no random draw is consumed.

**Worked example.** With `p_firm` 1 the invitation at event 3 is `FIRMED` and 30 fill at 100.05, leaving 20 open. With `p_firm` 0 the invitation at event 3 is `DECLINED`, the conditional is suspended, and when the suspension ends the next invitation, at event 6, is declined too; both orders rest in full (`dark_h-0004`).

The pitfall is modelling conditionals as free options. Each decline is information the contra side may have seen, which is why real pools penalise them; here the penalty is a parameter, not a measured cost.

### Q13.30 To buy 10 lots with 2 lots queued ahead at one lit venue, what split between a market order and a limit order does the router choose?

*Level: advanced. Evidence: golden; literature. Source: [Smart order router](../../specifications/10-execution/smart-order-router.md), [CK] Proposition 3 and eq. (5), golden `sor_h-0003`, rulings HR-38, HR-39*

The plain idea: a market order fills for sure but pays the half spread and the taker fee; a limit order earns them back but may not fill, and an underfill has a penalty. The router balances the two.

The rule ([CK] eq. (5), the per-scenario cost): `(h + f) M - (h + r) fill + theta (M + L + (S - A)_+) + lambda_u (S - A)_+ + lambda_o (A - S)_+`, where the limit order fills `(xi - Q)_+ - (xi - Q - L)_+` from the outflow `xi` and `A = M + fill`. `SAMPLE_AVERAGE` (HR-39) minimises the mean over the given outflow samples by exhaustive search on the integer grid, ties to the lexicographically smallest tuple. For one venue this agrees with Proposition 3 of [CK].

**Worked example.** `S = 10`, `h = 0.5`, `f = 0.3`, `r = 0.2`, `Q = 2`, `theta = 0`, `lambda_u = 4`, `lambda_o = 1`, outflow samples 0, 2, 4, ..., 14 equally weighted: the router sends `M = 8` and posts `L = 2`, expected cost 7.35, expected fill 9.5, probability of underfill 0.25 (`sor_h-0003`). The two lots posted fill only in the samples where the outflow passes the queue of 2.

The pitfall is reading the output as a forecast for a real venue. The outflow distribution is an input, and the comparison against single-venue routing on 10,000 simulated parent orders is published whatever it shows, not used as a gate (HR-40): "simulated venues; router scored in simulation only".

### Q13.31 With one lit venue and one dark venue, the router posts 4 lots lit and 3 dark for an order of 4. Why post 7 for 4?

*Level: practitioner. Evidence: golden; spec. Source: [Smart order router](../../specifications/10-execution/smart-order-router.md), golden `sor_h-0005`, ruling HR-37*

The plain idea: when each venue fills only part of what it is sent, sending more than you need in total raises the chance of getting enough. The overfill penalty stops it going too far.

The rule (HR-37): a dark allocation `D` fills `min(D, s)` with `s` drawn from the venue's tail `T(s) = P(s_k >= s)`, earns the half spread (midpoint) and the effective rebate `r - as`, and counts in the impact term as posted size.

**Worked example.** `S = 4`, lit queue 0 with outflow samples 0 and 4, dark tail 0.5, 0.5, 0.5, 0 and adverse-selection charge 0.1, `lambda_u = lambda_o = 1`: the exhaustive search picks `M = 0`, `L = [4, 3]`, expected cost 0, expected fill 2.75 and probability of underfill 0.5 (`sor_h-0005`). Half the time the lit order fills all 4; the dark order fills 3 only half the time.

The pitfall is ignoring the overfill side: with `lambda_o` at zero the search would post as much as the grid allows.

### Q13.32 An iceberg buy of 100 showing 10 rests first, then a plain buy of 20 at the same price. A sell of 15 arrives. Who fills?

*Level: practitioner. Evidence: golden; spec. Source: [Lit matching](../../specifications/10-execution/lit-matching.md), golden `lit_h-0006`, ruling HR-27*

The plain idea: an iceberg shows a small slice and hides the rest. It keeps its place for the slice it shows, but each new slice joins the back of the queue.

The rule (HR-27, after the CME FIFO refresh rule): the shown part trades by its `seq`; when it is filled, a new slice `min(display_qty, hidden)` joins the back with a new `seq`; hidden quantity trades only after all displayed quantity at that price.

**Worked example.** The sell takes the iceberg's 10 shown units first, then 5 from the plain buy. The iceberg refreshes at the back with `seq` 3, showing 10 with 80 hidden; the plain buy keeps `seq` 2 with 15 left (`lit_h-0006`). Simulated venue; not a real exchange.

The pitfall is assuming the hidden part keeps the iceberg's original place. Here it never does, and venue rule books differ on this point; [KR-ADD] does not state its refresh priority.

### Q13.33 Two bids rest at 100. The first is cut from 10 to 5, a sell of 3 arrives, then the first is raised to 8, and another sell of 3 arrives. Which bid fills each sell?

*Level: practitioner. Evidence: golden; spec. Source: [Lit matching](../../specifications/10-execution/lit-matching.md), golden `lit_h-0007`, ruling HR-25*

The plain idea: cutting an order costs others nothing, so it keeps its place; raising it would jump the queue, so it goes to the back.

The rule (HR-25): a quantity decrease keeps `seq`; a quantity increase or a price change takes a new `seq`.

**Worked example.** After the cut, bid A (5) is still first, so the first sell fills 3 from A. Raising A to 8 gives it `seq` 3, behind B, so the second sell fills 3 from B. At the end B rests with 7 and A with 8; A's conservation record shows 16 submitted, 3 filled, 5 cancelled and 8 resting (`lit_h-0007`).

The pitfall is "topping up" a resting order on a desk and expecting to keep priority.

### Q13.34 A buy of 12 at 102 meets 5 offered at 101 and 5 at 102. What happens to it as a fill-or-kill, and what would an immediate-or-cancel buy of 8 at 102 do against 5 at 101 and 5 at 103?

*Level: foundation. Evidence: golden; spec. Source: [Lit matching](../../specifications/10-execution/lit-matching.md), goldens `lit_h-0003`, `lit_h-0004`*

The plain idea: both order types refuse to rest. Fill-or-kill trades all or nothing; immediate-or-cancel trades what it can and cancels the rest.

The rule: `FOK` first checks that the marketable quantity within its limit, hidden iceberg quantity included, covers the whole order; if not, it is rejected with nothing traded. `IOC` matches what it can and cancels the remainder.

**Worked example.** Only 10 are offered at or below 102, less than 12, so the FOK is rejected in full: 12 rejected, no fill, the book unchanged (`lit_h-0003`). The IOC buys 5 at 101; the offer at 103 is above its limit, so 3 are cancelled (`lit_h-0004`). Simulated venue; not a real exchange.

The pitfall is reporting a rejected FOK as an error. It is a normal outcome in the output's `rejects`, and the conservation record still balances.

### Q13.35 The book is 100 bid, 103 offered. Where does a mid-peg buy with a cap of 105 rest, and what fills when a market sell of 2 arrives?

*Level: foundation. Evidence: golden; spec. Source: [Lit matching](../../specifications/10-execution/lit-matching.md), golden `lit_h-0008`, ruling HR-28*

The plain idea: a mid-peg follows the midpoint, hidden. If the midpoint falls between ticks it must round, and it rounds so that it never crosses.

The rule (HR-28): the price is the mid of the engine's own best bid and ask, rounded away from crossing (a buy down, a sell up to the tick), capped by its limit; it is not displayed.

**Worked example.** The mid is 101.5; the buy peg rounds down to 101, under its cap of 105, and rests hidden ahead of the bid at 100. The market sell of 2 trades at the best bid, the peg's 101, so the peg fills 2 and keeps 3 hidden (`lit_h-0008`).

The pitfall is rounding the peg to the nearest tick: 102 would sit nearer the offer than the venue's rule allows, and on a one-tick spread it would cross.

### Q13.36 How is the Kraken book checksum computed, and what does `ob_h-0001` check?

*Level: practitioner. Evidence: golden; venue documentation. Source: [Order book](../../specifications/09-microstructure/order-book.md), [KR-CRC], goldens `ob_h-0001`, `ob_h-0010`, ruling HR-13*

The plain idea: the venue sends a short fingerprint of its top 10 levels with each update. If your rebuilt book gives the same fingerprint, your top 10 almost surely match.

The rule ([KR-CRC], read 2026-11-17): take the top 10 asks ascending, then the top 10 bids descending; write each price and quantity with the decimal point and leading zeros removed; concatenate; the checksum is the CRC32 of that string as an unsigned 32-bit integer. It covers the top 10 whatever the subscribed depth.

**Worked example.** On the venue's own printed example levels the checksum is 3310070434 (`ob_h-0001`, outside-checked against the venue's printed value). A bid at price "0.00012300" and quantity "1.00000000" becomes the string `12300100000000`, whose CRC32 is 1057566538 (`ob_h-0010`). Both are recomputed with `zlib.crc32` by the verify script.

The pitfall is formatting prices as numbers: "45283.5" and "45283.50" give different strings, which is why prices stay as the decimal strings received (HR-12). Recorded rows stay local; only counts are published ("crypto venue; not equities or rates").

### Q13.37 During a rebuild, an update deletes a level that is not in the book, a later update makes the book locked and then crossed, and a reconnect row arrives. Which of these are errors?

*Level: advanced. Evidence: golden; spec. Source: [Order book](../../specifications/09-microstructure/order-book.md), goldens `ob_h-0004`, `ob_h-0006`, `ob_h-0007`, `ob_h-0008`, rulings HR-14, HR-15*

The plain idea: a replay of a whole day must count problems and keep going, not stop at the first one. So none of these is an error; each is counted.

The rule: an update sets a level's quantity (replace, not add) and quantity 0 removes it; deleting a missing level counts in `deletes_of_absent_level` (the venue's truncation makes it legitimate). After each message the book is truncated to the depth and checked: best bid equal to best ask is `LOCKED`, above it `CROSSED` (HR-14). A `gap` row clears the book and counts in `gaps`; updates before the next snapshot are ignored and reported as `UPDATE_BEFORE_SNAPSHOT`. Errors are reserved for bad input: a malformed message or a price written as a number is `E_SCHEMA`, a negative quantity or a depth not in the venue's list `E_DOMAIN`.

**Worked example.** Two updates at 100.0 with 5 then 7 leave 7, not 12 (`ob_h-0004`). Deleting the absent level 98.0 counts once and changes nothing (`ob_h-0007`). A bid at 101.0 against an offer at 101.0 is `LOCKED`, then a bid at 101.5 is `CROSSED`, one count each (`ob_h-0006`). After a `gap`, an update to 100.0 is ignored and the next snapshot rebuilds the book from scratch: `gaps` 1, `snapshots` 2 (`ob_h-0008`).

The pitfall is "repairing" a gap by carrying the old book across it. The rebuild never invents a recovery the venue does not document (HR-15).

### Q13.38 A buy limit at 10.005 and a sell limit at 10.005 are rounded to the equity tick. What do you get, and when does the half-penny tier apply?

*Level: foundation. Evidence: golden; regulator text read. Source: [Asset conventions](../../specifications/09-microstructure/asset-conventions.md), goldens `eqc_h-0001`, `eqc_h-0002`, `eqc_h-0010`, `eqc_h-0020`, `eqc_h-0022`, rulings HR-81, HR-120*

The plain idea: a limit price must sit on the price grid, and rounding must never make an order more aggressive than its owner asked.

The rule (SEC Rule 612, HR-81, HR-120): the tick is 0.0001 below 1.00 and 0.01 at or above it, or 0.005 for a stock on the half-penny tier; a buy rounds down, a sell up. The half-penny tier is in the amended rule, whose compliance date is 2027-11-01 (deferred by SEC order 34-105656). With no `as_of` the operation applies the amended text; with `as_of` it applies the rule in force on that date.

**Worked example.** 10.005 rounds to 10.00 for a buy and 10.01 for a sell (`eqc_h-0001`, `eqc_h-0002`). On the half-penny tier with no `as_of`, a sell at 10.003 rounds to 10.005 (`eqc_h-0010`); with `as_of` 2026-11-19 the tier is refused with `E_INPUT` (`eqc_h-0020`); with `as_of` 2027-11-01 it gives 10.005 again (`eqc_h-0022`).

The pitfall is calling without `as_of` and quoting the result as today's rule. Until 2027-11-01 the amended tick table is not in force, and the SEC has these rules under review, so the date may move.

### Q13.39 On 2026-11-19, is an access fee of 0.0015 a share at a price of 20 within the cap? What is the round lot for a stock at 500?

*Level: practitioner. Evidence: golden; regulator text read. Source: [Asset conventions](../../specifications/09-microstructure/asset-conventions.md), goldens `eqc_h-0023`, `eqc_h-0024`, `eqc_h-0025` to `eqc_h-0027`, ruling HR-120*

The plain idea: rules change on dates, and different parts of one amendment can start on different dates. A convention function needs the date as an input, not as a constant.

The rule (HR-120): the access-fee cap (Rule 610(c)) is 0.003 a share at or above 1.00 until the amended cap of 0.001 applies from 2027-11-01; the round lot (Rule 600(b)(93)) has applied by price since 2025-11-03: 100 shares up to 250.00, 40 up to 1,000.00, 10 up to 10,000.00, then 1.

**Worked example.** On 2026-11-19 a fee of 0.0015 at 20 passes against the cap 0.003 (`eqc_h-0023`); on 2027-11-01 it is above the cap 0.001 and fails with `E_DOMAIN` (`eqc_h-0024`). At 500 the round lot is 40 on 2026-11-19 and on 2025-11-03, but 100 on 2025-10-31, the business day before (`eqc_h-0025` to `eqc_h-0027`).

The pitfall is one compliance date for the whole amendment. Until the SEC order was read on 2026-11-19 the spec had that error, and all four builds followed it; a blind re-derivation could not catch it, because the blind lane read the same spec.

### Q13.40 What is one pip worth on 1,000,000 EURUSD and on 1,000,000 USDJPY, and when does EURUSD traded on 2026-11-24 settle if the 26th is a USD holiday?

*Level: foundation. Evidence: golden; spec. Source: [Asset conventions](../../specifications/09-microstructure/asset-conventions.md), goldens `fxc_h-0001`, `fxc_h-0002`, `fxc_h-0004`, `fxc_h-0006`, `fxc_h-0008`, ruling HR-119*

The plain idea: a pip is the smallest usual quote step, and its value is in the quote currency. Spot settles two good business days after the trade, with currency holidays deciding which days are good.

The rule: pip value is notional times the pip, 0.0001, or 0.01 when JPY is the quote currency. Spot is T+2 days that are business days in both currencies, T+1 for USDCAD. Two exceptions: a USD-only holiday on the first day after the trade does not stop the count, and the spot date itself must be a USD business day, rolled forward if not (market conventions with no primary source read, HR-119).

**Worked example.** EURUSD: 100 USD a pip (`fxc_h-0001`); USDJPY: 10,000 JPY a pip (`fxc_h-0002`). Traded Tuesday 2026-11-24 with a USD holiday on Thursday the 26th, T+2 falls on the holiday and rolls to Friday 2026-11-27 (`fxc_h-0004`). Traded Wednesday 2026-11-25, the holiday is T+1 and still counts, so spot is again Friday 2026-11-27 (`fxc_h-0008`). USDCAD traded Friday 2026-11-20 settles Monday 2026-11-23 (`fxc_h-0006`).

The pitfall is converting a pip value to a home currency without saying which rate was used: the operation returns the currency with the value for that reason.

### Q13.41 What are 99-16, 99-16+, 99-162 and 99-167 as decimals, and why is 99-163 refused?

*Level: foundation. Evidence: golden; venue documentation. Source: [Asset conventions](../../specifications/09-microstructure/asset-conventions.md), goldens `rtc_h-0001` to `rtc_h-0004`, `rtc_h-0015`, rulings HR-109, HR-118*

The plain idea: Treasury prices are quoted in 32nds of a point, and a third digit gives quarters of a 32nd.

The rule: `H-FF[q]` is `H + (FF + q)/32`, where `+` is a half and the third digit 0, 2, 5 or 7 is 0, 1/4, 1/2 or 3/4 of a 32nd (CME's text form). Any other third digit is `E_SCHEMA` (HR-109). Eighth-tick contracts, the 2-year and 3-year notes, are not supported (HR-118).

**Worked example.** 99-16 is 99.5; 99-16+ is 99.515625; 99-162 is `99 + 16.25/32 = 99.5078125`; 99-167 is `99 + 16.75/32 = 99.5234375` (`rtc_h-0001` to `rtc_h-0004`). A third digit of 3 is not a quarter, so it is refused (`rtc_h-0015`).

The pitfall is reading the third digit as eighths: 99-163 would then be a valid eighth-tick price, which these operations do not support.

### Q13.42 Six orders meet in a simulated opening auction. At what price does it uncross, how much trades, and what is the imbalance?

*Level: practitioner. Evidence: golden; venue documentation. Source: [Auction](../../specifications/10-execution/auction.md), goldens `auc_h-0001`, `auc_h-0006`, `auc_h-0009`, rulings HR-84, HR-127*

The plain idea: an auction collects orders, then picks the one price at which the most shares can trade, and everyone trades at that price.

The rule: for every tick between the lowest and highest limit, matched volume `V(p) = min(buys with limit >= p, sells with limit <= p)`; keep the price with the largest `V`; ties go first to the smallest absolute imbalance, then by the `tie_break` parameter (`CBOE` by default; the imbalance-side step is the simulator's own, not Cboe's).

**Worked example.** Buys 100 at 10.02, 200 at 10.01, 300 at 10.00; sells 150 at 9.99, 250 at 10.01, 100 at 10.03. `V` is 150 at 9.99 and at 10.00, `min(300, 400) = 300` at 10.01, 100 at 10.02 and 0 at 10.03, so the auction uncrosses at 10.01 for 300 shares with an imbalance of -100, a sell surplus; seller s5 fills 150 of its 250 (`auc_h-0001`). Simulated venue; not a real exchange.

The pitfall is ignoring the tie-break: on one buy of 200 at 10.02 against sells of 100 at 10.00 and 50 at 10.01 (reference 10.00), `auc_h-0006` uncrosses at 10.02 with `tie_break` `CBOE` and `auc_h-0009` at 10.01 with `IEX`, both for 150 shares.

### Q13.43 A client buys EURUSD on the simulated dealer's quote 1.0850 / 1.0852 (mid 1.0851). During the hold the mid moves to 1.0855, or only to 1.0852. What does last look do with a 2-pip threshold?

*Level: practitioner. Evidence: golden; spec. Source: [FX dealer venue](../../specifications/10-execution/fx-rfq-venue.md), goldens `fxv_h-0003`, `fxv_h-0004`, ruling HR-97*

The plain idea: on last look the dealer checks the market again before accepting, and may refuse a trade that has become a loss for it.

The rule (HR-97): `move = (mid_after - quote_mid) / pip`. If `symmetric`, reject `LL_PRICE` when `|move| > threshold_pips`; otherwise reject only an adverse move above the threshold. If not rejected on price, reject `LL_RANDOM` when `u < p_random_reject`; else fill at the quoted price.

**Worked example.** A move to 1.0855 is +4 pips against the dealer, above 2: `LL_PRICE`, no price (`fxv_h-0003`). A move to 1.0852 is 1 pip, within the threshold, and `u = 0.50` is above `p_random_reject = 0.05`, so the client buys at 1.0852 (`fxv_h-0004`). Labelled "simulated venue; not a real exchange; no real FX data".

The pitfall is treating the thresholds as market practice. They are the spec's own toy model, not taken from the FX Global Code (HR-119); with `symmetric` on, a move in the client's favour beyond the threshold is rejected too.

### Q13.44 On the simulated ZN futures venue, P buys 3 at 110-16 from M and sells 3 at 110-17+ to N, with fees of 1.00 a contract a side. What is each trader's P&L?

*Level: practitioner. Evidence: golden; venue documentation. Source: [Rates futures venue](../../specifications/10-execution/rates-futures-venue.md), golden `fut_h-0011`, rulings HR-90 to HR-92, HR-117*

The plain idea: futures P&L is ticks moved times quantity times tick value, less fees, with open positions marked at the last trade.

The rule: the venue is the lit engine in integer ticks; ZN's tick is 1/64 of a point and worth 15.625 on 100,000 face (CME, read 2026-11-19, HR-117). `pnl = sum signed ticks x qty x tick_value - fees`.

**Worked example.** 110-16 is 110.5 and 110-17+ is 110.546875, 3 ticks of 1/64 apart. P: `3 x 3 x 15.625 - 6 = 134.625`. M is short 3 from 110.5, marked at the last trade 110.546875: `-3 x 3 x 15.625 - 3 = -143.625`. N bought at the last trade: `0 - 3 = -3`. The three sum to -12, minus the fees (`fut_h-0011`). Labelled "simulated venue; not a real exchange; no real rates data".

The pitfall is a P&L table that does not sum to minus the fees: in a closed simulated venue every tick one trader makes, another loses.

### Q13.45 A request breaks two rules at once. Which error code does each build return?

*Level: advanced. Evidence: golden; spec. Source: `specifications/stage-h-rulings-audit.md` (HR-121, HR-122), suite `rule_h` (goldens `rule_h-0003`, `rule_h-0012`, `rule_h-0016`)*

The plain idea: if each build checked inputs in its own order, the same bad request would get different error codes, and conformance would never notice unless some golden broke two rules at once.

The rule (HR-122): `E_SCHEMA`; then `E_LIMIT` for a size limit on the input itself; then a non-finite Real, `E_DOMAIN`; then structural `E_INPUT` (an empty list, a count below 1, lengths, cross-field consistency); then `E_DOMAIN` for a value outside its domain. A related rule, HR-121: a binary64 value within 1e-12 relative of an integer is taken as that integer before a floor.

**Worked example.** Almgren-Chriss with `n_steps` 0 and `sigma` -1 is `E_INPUT`, the structural fault first (`rule_h-0016`); before 2026-11-19 Python and Rust answered `E_DOMAIN` and Java and C++ `E_INPUT`. TWAP with quantity -5 and 200,000 buckets is `E_LIMIT` (`rule_h-0012`). A cash-balanced pair at leg prices 0.3 and 0.2 gives 2 units of leg B: `0.3 / 0.2` is 1.4999999999999998 in binary64 and gave 1 before HR-121 (`rule_h-0003`). Suite `rule_h` has 40 cases.

The pitfall is testing each validation rule alone. Single-fault goldens passed in all four builds while the builds disagreed on double faults; the different-model audit found it.

### Q13.46 On workload R, the recorded crypto window, the low-latency book passes every correctness check and misses its timing targets. How should that be reported?

*Level: advanced. Evidence: measured (laptop); design. Source: `benchmarks/results/h9/README.md`, `specifications/09-microstructure/low-latency-targets.md`, [v0.10.0 release notes](../releases/v0.10.0.md), ruling HR-23*

As a miss, with the targets unchanged. Correctness: the book after every one of 31,287 book messages per symbol matched `micro.book.rebuild` exactly, 0 failed, for BTC/USD and ETH/USD in C++, Rust and Java. Timing (median of 5 runs, a laptop under WSL for C++ and Rust and native Windows for Java, not the acceptance machine; crypto venue; not equities or rates): p99 and p99.9 miss in every language, for example C++ BTC/USD p99 9,223 ns against a 500 ns target, and ETH/USD p50 misses too.

The reason recorded with it: the targets were set for a message that changes one or a few levels, while a recorded update carries about 58 level changes. About 40 ns per level is descriptive only and has no target. R2 not yet run: on 2026-11-19 four recording sessions were cut short by network drops, the longest 3 h 20 min; targets and rules were fixed before any timing (HR-130 to HR-134); the measurement uses the first 6-hour session that completes; the 2026-11-19 workload R result remains a recorded MISS.

The pitfall is replacing the missed target with the per-level figure after seeing the data. A target judges only a run it was fixed before (HR-23).

### Q13.47 A paper book is long 1 at an average cost of 100 with 9,909.69 cash. The next day closes at 102 after 105, with no trades and cash earning 3.65 %. Explain the day.

*Level: foundation. Evidence: golden. Source: [Paper trading](../../specifications/10-execution/paper-trading.md), golden `pt_h-0003`, rulings HR-52, HR-53*

The plain idea: with no trades, the day's P&L is the move on the position held plus interest on the cash held, and the parts must add up to the change in the book's value.

The rule: financing is posted on opening balances only, ACT/365, rounded half-even to the cent when posted (HR-52); `total = market + trading + fees + financing = NAV_t - NAV_{t-1}` exactly (HR-53).

**Worked example.** Market `1 x (102 - 105) = -3`; interest `9909.69 x 0.0365 / 365 = 0.990969`, posted as 0.99; trading and fees 0; total -2.01. Cash closes at 9,910.68 and NAV goes from 10,014.69 to 10,012.68 (`pt_h-0003`). Fills in a paper book come from the simulated venues only.

The pitfall is rounding the interest after adding it to the explain: the rounded posting is what reaches cash, so the explain uses 0.99 and still sums exactly.

Back to the [question bank index](README.md).
