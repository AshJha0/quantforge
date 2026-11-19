# Simulators

<p class="note">Stage H, v0.10.0. The simulators below are implemented in all four languages (spec version 0.1.0, confirmed 2026-11-18). Every output they produce carries the label its spec fixes, for example "simulated venue; not a real exchange". No simulator places a real order; trading in this project is simulated only.</p>

## Why a page for simulators

A simulator answers "what would happen under these rules and this order flow", and nothing else. It cannot tell you how a real venue behaves, because the rules and the flow are ours. It is still useful in two ways: it lets a method be tested against a truth we planted (does the estimator recover the arrival rate we put in?), and it lets two strategies be compared on the same replay. This page lists each simulator, what it assumes, and what it cannot show, so that no simulated number is read as a market fact.

Simulators are kept out of the numerical core: they consume the library's operations but are not models of prices (ARCHITECTURE, "Simulated venues").

## The simulators

| Simulator | Operation | What it assumes | Label on every output | Spec |
|---|---|---|---|---|
| Lit matching engine | `exec.sim.lit.run` | One instrument, integer ticks and lots, price-time priority with a FIFO queue per level (MBO). Order types LIMIT, MARKET, IOC, FOK, ICEBERG, POST_ONLY, PEG_MID, PEG_PRIMARY. Event order is given; no latency, halts or self-trade prevention. With an optional `session` and `PHASE` events it also runs an opening and a closing auction (HR-112); the continuous book does not join the closing cross | "simulated venue; not a real exchange" | [`lit-matching.md`](../../specifications/10-execution/lit-matching.md) |
| Dark pool | `exec.sim.dark.run` | Crosses at the lit mid (half ticks allowed), time priority among eligible orders, a minimum quantity per fill, conditional orders that firm up with a given probability | "simulated venue; not a real dark pool" | [`dark-pool.md`](../../specifications/10-execution/dark-pool.md) |
| Smart order router | `exec.sor.allocate` | The one-period model of Cont and Kukanov: place market and limit orders at time 0, clean up at the end; fill distributions are inputs | "simulated venues; router scored in simulation only" | [`smart-order-router.md`](../../specifications/10-execution/smart-order-router.md) |
| Equity auction | `exec.sim.auction.uncross` | One call auction, OPEN or CLOSE: the price with the largest matched volume, ties by smallest imbalance and then by `tie_break` (`CBOE` default, or `IEX`); the imbalance-side and final higher-price steps of the default are the simulator's own (HR-119) | "simulated venue; not a real exchange" | [`auction.md`](../../specifications/10-execution/auction.md) |
| FX dealer venue with last look | `exec.sim.fx.stream`, `exec.sim.fx.request` | One dealer quoting around a given mid path; a request is rejected if the mid moved past `threshold_pips`, or at random with probability `p_random_reject`, else filled at the quote. The thresholds and the random reject are the spec's own toy model (HR-119) | "simulated venue; not a real exchange; no real FX data" | [`fx-rfq-venue.md`](../../specifications/10-execution/fx-rfq-venue.md) |
| Treasury futures venue | `exec.sim.fut.run`, `.to_ticks`, `.to_text`, `.pnl`, `.variation` | The lit engine in integer ticks with prices in 32nds; ZN and ZB contract defaults; fees per contract per side; open positions marked at the last trade. No delivery or conversion factors; eighth-tick contracts not supported (HR-118) | "simulated venue; not a real exchange; no real rates data" | [`rates-futures-venue.md`](../../specifications/10-execution/rates-futures-venue.md) |
| Order flow for method tests | inside the H-4 tests | Poisson arrivals, cancels and market orders at planted rates (the Cont-Stoikov-Talreja queue model), seeded from `core.rng` | as the venue it drives | `lit-matching.md`, "Known-truth method tests" |

## What each can and cannot show

**Lit engine.** It can show that an order type does what its rule says (one golden per type, `lit_h-0001` to `0009`), that quantity is conserved and the book never crosses (property tests), and that an estimator recovers planted rates within 3 standard errors. It cannot show queue position on a real venue, latency races, or how other traders react to your orders. Its rules borrow from venue documentation (CME's FIFO steps, Kraken's order types, IEX's midpoint peg) for definitions only; no venue's rule book is reproduced.

**Dark pool.** It can show the mechanics of midpoint crossing, minimum quantity and conditional orders, and whether a markout estimator recovers a planted adverse move `alpha x J` within 3 standard errors. It cannot show real dark-pool fill rates or leakage: QuantForge uses no real dark-pool data, and crypto venues are lit only. When it runs against a replayed crypto book, the reference mid is labelled "lit mid from crypto venue; dark pool simulated".

**Router.** It can show whether the chosen split recovers the optimum computed on the true (planted) fill distributions. The comparison of router against single-venue routing on 10,000 simulated parent orders (seed 20261117) is published whatever it shows, but it is a result inside the simulation, not evidence that routing pays on any real market (ruling HR-40). The recorded crypto data is a single venue and is not routed across.

**Auction.** It can show that the uncrossing price maximises matched volume and that the tie-break steps are applied in order (`auc_h-0001`: 300 shares at 10.01, imbalance -100; `rule_h-0009`: no cross, no auction, HR-127). It cannot show how a real opening or closing auction prices: real auctions have order types, collars and published imbalance feeds that are not modelled, and no exchange's rule book is reproduced.

**FX dealer venue.** It can show the mechanics of last look: which requests fill and which are rejected for a given move and draw, repeatably from a seed (`fxv_h-0003`, `0004`, `0010`). It cannot show any dealer's reject rate, hold time or pricing. No real FX data is used anywhere in the project.

**Futures venue.** It can show tick arithmetic, price-time matching in ticks and that trading P&L sums to minus the fees across traders (`fut_h-0011`: 134.625, -143.625 and -3, fees 12). It cannot show real futures liquidity, settlement prices or margin rules. No real rates data is used.

## Goldens and paper trading

The simulators' goldens are generated and checked in every build: `ob_h` 17, `lit_h` 20, `dark_h` 8, `sor_h` 9, `sorx_h` 2, `auc_h` 12, `ses_h` 3, `fxv_h` 20, `fut_h` 16 and `acls_h` 5 (`datasets/golden/stage_h/`; for example `lit_h-0006`, an iceberg refresh; `dark_h-0002`, a minimum-quantity block; `sor_h-0001`, a corner solution). Paper trading with simulated fills (plan item H-21, moved into stage H on 2026-11-18) runs on these simulators through `python/quantforge_core/paper_fills.py`: simulated fills, positions, cash, daily P&L explain, risk limits, pre-trade checks and a hashed append-only ledger ([Tutorial 44](../getting-started/tutorial-44-paper-trading.md)). The `paper.*` CLI operations (`pt_h`, 34 cases) are in all four languages. The paper path drives the lit engine, the dark pool and the router; the auction, FX and futures venues are not on it. It never sends a live order.

## Related

[Recorded feeds](../data/recorded-feeds.md); diagrams H-D2 and H-D3 in [Diagrams](../diagrams/README.md#matching-engine-state) and the [multi-asset venues](../diagrams/README.md#multi-asset-venues) diagram; [Tutorial 50](../getting-started/tutorial-50-auction-fx-and-futures-venues.md).
