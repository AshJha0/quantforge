# Simulated lit matching engine (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1b). Status: Specified, not implemented. Rulings HR-25 to HR-31. Plan items 15.1 "Lit book (simulated)", 14.7 H-4 (method tests on a simulated book with known truth). **Every output is labelled "simulated venue; not a real exchange".** No real venue's rule book is reproduced; the rules below are a small, stated subset chosen to match common published practice.

**Plain idea.** Orders rest at their price; at one price, the first to arrive is filled first. An incoming order trades against the best opposite prices while it is marketable, then rests, is cancelled, or is rejected according to its type.

## Sources
- [CME-FIFO] CME Group, "CME Globex Matching Algorithm Steps", client wiki, https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457218521, read 2026-11-17. Evidence class: venue documentation, read. Verified: FIFO matches resting orders in timestamp order only; an order loses time priority when its price changes or its quantity increases; a display-quantity order is refreshed to the lowest priority at its price after a match.
- [KR-ADD] Kraken, "Add Order", REST docs, https://docs.kraken.com/api/docs/rest-api/add-order, read 2026-11-17. Venue documentation, read. Verified: time in force GTC, IOC, GTD, FOK; IOC executes what it can and cancels the rest; FOK executes in full immediately or is cancelled; `post` flag is post-only for limit orders; iceberg orders show `displayvol`, minimum 1/15 of the volume. Not stated: post-only behaviour when it would cross; iceberg refresh priority.
- [IEX-OT] IEX, "Order types", https://www.iex.io/products/equities/order-types, read 2026-11-17. Venue documentation, read. Verified: midpoint peg is non-displayed, pegged to the NBBO midpoint subject to its limit. Used for the peg definition only.

## Model
- Integer ticks and integer lots (HR-20); one instrument; prices `tick_size` apart.
- Book: per side, price levels; per level a FIFO queue of orders (MBO). Each order has `id`, `side`, `price`, `qty_open`, `display_qty`, `hidden_qty`, `seq` (arrival counter; the priority key).
- Time is a logical sequence; the engine is deterministic: same input list, same output, in every language.

## Order types (HR-25)
| Type | Rule |
|---|---|
| `LIMIT` GTC | match while marketable at resting prices (price improvement to the incoming order), rest the remainder |
| `MARKET` | match against the opposite side to exhaustion of the order or the book; never rests; the unfilled rest is cancelled and reported (`E_` none) |
| `IOC` | limit price; match what is marketable, cancel the rest |
| `FOK` | limit price; pre-check that marketable quantity >= order quantity (including hidden iceberg quantity, HR-27); if yes match in full, else reject with nothing traded |
| `ICEBERG` | `display_qty` shown at the back of the queue; when the shown part is filled, a new slice of `min(display_qty, hidden)` joins the **back** of the queue with a new `seq` ([CME-FIFO] refresh rule); hidden quantity is matchable by an incoming order only after all displayed quantity at that price (HR-27) |
| `POST_ONLY` | if it would trade on arrival it is **rejected** (HR-26; reprice-to-passive is not offered in wave 1b) |
| `PEG_MID` | non-displayed; price = mid of the engine's own best bid and ask, rounded away from crossing (bid down, ask up to a tick, HR-28), capped by its limit; repriced after each event that moves the mid, keeping `seq` while its price is unchanged and taking a new `seq` when it moves; no mid when a side is empty: it does not trade |
| `PEG_PRIMARY` | displayed, priced at the same-side best (excluding itself), capped by its limit, repriced like `PEG_MID`; same `seq` rule |

Modify: a quantity decrease keeps `seq`; a price change or increase takes a new `seq` ([CME-FIFO]). Cancel removes the order.

## Matching (normative)
Incoming marketable order against the opposite side: best price first; within a price, displayed orders by `seq`, then pegged non-displayed orders by `seq`, then iceberg hidden quantity by the iceberg's `seq` (HR-27). Trade price = resting order's price. Self-trade: not checked in wave 1b (one trader id per simulation), stated.

## Operation `exec.sim.lit.run`
Inputs: `tick_size`, `lot_size`, `events` (list of `{"op": "NEW"|"CANCEL"|"MODIFY", ...}`), `fee_schedule` `{taker_fee, maker_rebate}` per unit notional (signed, HR-30). Outputs: `fills` (`taker_id`, `maker_id`, `price`, `qty`, `seq`), `rejects` (`id`, `reason`: `POST_ONLY_WOULD_CROSS`, `FOK_UNFILLABLE`, `UNKNOWN_ID`), final MBO book and its MBP projection (must equal `micro.book.rebuild` applied to the engine's own level diffs), fees per participant.
Errors: price not on the tick grid, non-positive quantity, `display_qty` > quantity `E_DOMAIN`; duplicate `id` `E_INPUT`; more than 10,000,000 events `E_LIMIT`.

## Invariants (property tests, every language)
Book never crossed after an event; quantity conserved (sum of fills + resting + cancelled + rejected = submitted); FIFO: for any two fills at one price on displayed quantity, smaller `seq` fills first; FOK fills all or nothing; post-only never takes; replay determinism (byte-identical output).

## Known-truth method tests (H-4)
A Poisson order-flow simulator (`core.rng`, seed fixed per test) in the [CST10] model of `dark-pool.md`'s fill section, with planted arrival, cancel and market-order rates; the estimators of arrival and cancellation rates from the engine's event log recover the planted rates within 3 SE.

## Golden plan
| Case | Content | Expected | Check |
|---|---|---|---|
| lit_h-0001 | three bids at one price, a sell that fills 1.5 of them | first two in `seq` order | hand |
| lit_h-0002 | buy limit crossing two ask levels | trades at each resting price | hand |
| lit_h-0003 | FOK larger than book | rejected, book unchanged | hand, [KR-ADD] definition |
| lit_h-0004 | IOC partially marketable | fill then cancel | hand, [KR-ADD] |
| lit_h-0005 | post-only crossing | rejected | HR-26 |
| lit_h-0006 | iceberg 100 shown 10, another order behind it, a sell of 15 | 10 from iceberg, 5 from the other order, iceberg refresh at back | hand, [CME-FIFO] refresh rule |
| lit_h-0007 | modify down then up | keeps then loses priority | [CME-FIFO] |
| lit_h-0008 | PEG_MID with spread 3 ticks | bid peg rounds down | HR-28 |
| lit_h-0009 | market order on an empty side | no fill, remainder cancelled | hand |

Outside checks (HR-31, decided): no public reference engine publishes outputs, so value cases are outside-checked by blind re-derivation under DR-H2, a second lane given the inputs and the rules of this page only. All nine cases go to that lane, so the plan's 60% rule is met only if at least six match. Venue documentation (0003, 0004, 0006, 0007) backs the rules and is cited, but is not counted as an outside check.

## Limitations
One instrument, one engine, no auctions, no halts, no self-trade prevention, no latency between participants (event order is given). Simulated venue; not a real exchange.
