# Simulators

<p class="note">Planned for v0.10.0 (stage H). The simulators below are specified (spec version 0.1.0, confirmed 2026-11-18) but not merged. Every output they produce will carry the label its spec fixes, for example "simulated venue; not a real exchange". No simulator places a real order; trading in this project is simulated only.</p>

## Why a page for simulators

A simulator answers "what would happen under these rules and this order flow", and nothing else. It cannot tell you how a real venue behaves, because the rules and the flow are ours. It is still useful in two ways: it lets a method be tested against a truth we planted (does the estimator recover the arrival rate we put in?), and it lets two strategies be compared on the same replay. This page lists each simulator, what it assumes, and what it cannot show, so that no simulated number is read as a market fact.

Simulators are kept out of the numerical core: they consume the library's operations but are not models of prices (ARCHITECTURE, "Simulated venues").

## The simulators

| Simulator | Operation | What it assumes | Label on every output | Spec |
|---|---|---|---|---|
| Lit matching engine | `exec.sim.lit.run` | One instrument, integer ticks and lots, price-time priority with a FIFO queue per level (MBO). Order types LIMIT, MARKET, IOC, FOK, ICEBERG, POST_ONLY, PEG_MID, PEG_PRIMARY. Event order is given; no latency, auctions, halts or self-trade prevention | "simulated venue; not a real exchange" | [`lit-matching.md`](../../specifications/10-execution/lit-matching.md) |
| Dark pool | `exec.sim.dark.run` | Crosses at the lit mid (half ticks allowed), time priority among eligible orders, a minimum quantity per fill, conditional orders that firm up with a given probability | "simulated venue; not a real dark pool" | [`dark-pool.md`](../../specifications/10-execution/dark-pool.md) |
| Smart order router | `exec.sor.allocate` | The one-period model of Cont and Kukanov: place market and limit orders at time 0, clean up at the end; fill distributions are inputs | "simulated venues; router scored in simulation only" | [`smart-order-router.md`](../../specifications/10-execution/smart-order-router.md) |
| Order flow for method tests | inside the H-4 tests | Poisson arrivals, cancels and market orders at planted rates (the Cont-Stoikov-Talreja queue model), seeded from `core.rng` | as the venue it drives | `lit-matching.md`, "Known-truth method tests" |

## What each can and cannot show

**Lit engine.** It can show that an order type does what its rule says (one golden per type, `lit_h-0001` to `0009`, planned), that quantity is conserved and the book never crosses (property tests), and that an estimator recovers planted rates within 3 standard errors. It cannot show queue position on a real venue, latency races, or how other traders react to your orders. Its rules borrow from venue documentation (CME's FIFO steps, Kraken's order types, IEX's midpoint peg) for definitions only; no venue's rule book is reproduced.

**Dark pool.** It can show the mechanics of midpoint crossing, minimum quantity and conditional orders, and whether a markout estimator recovers a planted adverse move `alpha x J` within 3 standard errors. It cannot show real dark-pool fill rates or leakage: QuantForge uses no real dark-pool data, and crypto venues are lit only. When it runs against a replayed crypto book, the reference mid is labelled "lit mid from crypto venue; dark pool simulated".

**Router.** It can show whether the chosen split recovers the optimum computed on the true (planted) fill distributions. The comparison of router against single-venue routing on 10,000 simulated parent orders (seed 20261117) is published whatever it shows, but it is a result inside the simulation, not evidence that routing pays on any real market (ruling HR-40). The recorded crypto data is a single venue and is not routed across.

## What waits for merged code

Goldens for these three simulators are planned in their specs (for example `lit_h-0006`, an iceberg refresh; `dark_h-0002`, a minimum-quantity block; `sor_h-0001`, a corner solution) but carry no values on this page until they are generated and checked. Paper trading with simulated fills (plan item H-21, moved into stage H on 2026-11-18) will run on these simulators and add its own section here: simulated fills, positions, cash, daily P&L explain, risk limits, pre-trade checks and a hashed append-only ledger. It never sends a live order.

## Related

[Recorded feeds](../data/recorded-feeds.md); diagrams H-D2 and H-D3 in [Diagrams](../diagrams/README.md#matching-engine-state).
