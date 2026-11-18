# Equity opening and closing auction uncrossing (H-22)

Spec version 0.1.0 (drafted 2026-11-18; rulings HR-84, HR-96). Label: "simulated venue; not a real exchange" (on IEX data: "IEX only; one venue"). Sources: [IEX-AUC] and common published call-auction practice (see `../09-microstructure/asset-conventions.md`); the criteria are fixed by ruling, not copied from one venue.

**Plain idea.** During the call phase orders collect without trading. At the auction time one price is chosen that trades the most shares, and everyone who trades gets that one price.

## Operation `exec.sim.auction.uncross`
Inputs: `orders` (each `id, side, limit or MARKET, qty, seq`), `tick_size`, `ref_price` (last trade or previous close), `phase` (`OPEN` or `CLOSE`). Outputs: `price`, `volume`, `imbalance` (signed, positive = buy surplus at the chosen price), `fills` (per order), residual book.

## Algorithm (normative, HR-84)
1. Candidate prices: every tick from the lowest to the highest limit price present on either side. Market orders count as limit +infinity (buy) or 0 (sell) and add no candidate. No candidate, or one side empty: no auction, `volume = 0`, `price = null`.
2. For each candidate p: B(p) = sum of buy qty with limit >= p; S(p) = sum of sell qty with limit <= p; V(p) = min(B, S); I(p) = B - S.
3. Keep the p with maximum V. Ties: minimum |I|. Ties: if every remaining I > 0 take the highest p; if every remaining I < 0 the lowest p. Remaining ties: the p closest to `ref_price`; still tied: the higher p (HR-96).
4. Allocation: buys by limit descending then `seq`; sells by limit ascending then `seq`; fill in turn until V is used. All fills at the uncrossing price. Unfilled limit orders rest; unfilled MARKET and on-close orders are cancelled (HR-96).

## Golden value cases
| Case | Input | Expected | Derivation |
|---|---|---|---|
| auc_h-0001 | buys 10.02x100 (s1), 10.01x200 (s2), 10.00x300 (s3); sells 9.99x150 (s4), 10.01x250 (s5), 10.03x100 (s6); tick 0.01; ref 10.00 | price 10.01, volume 300, imbalance -100 | V: 9.99:150, 10.00:150, 10.01:min(300,400)=300, 10.02:100, 10.03:0 |
| auc_h-0002 | same orders as auc_h-0001; report fills and residual | fills s1 100, s2 200, s4 150, s5 150; rest s3 300, s5 100, s6 100 | buy priority by limit; s4 before s5 |
| auc_h-0003 | buy 10.02x100; sell 10.00x100; tick 0.01; ref 10.01 | price 10.01, volume 100, imbalance 0 | V=100, I=0 at all three; closest to ref |
| auc_h-0004 | as auc_h-0003 with ref 10.05 | price 10.02 | closest to ref |
| auc_h-0005 | as auc_h-0003 with ref 10.005 | price 10.01 | 10.00 and 10.01 equidistant; higher |
| auc_h-0006 | buy 10.02x200; sells 10.00x100, 10.01x50; tick 0.01; ref 10.00 | price 10.02, volume 150, imbalance +50 | V 100, 150, 150; I +50 at 10.01 and 10.02; all positive, highest |
| auc_h-0007 | buy MARKETx100; sell MARKETx100 | no auction, volume 0 | no candidate |
| auc_h-0008 | buys 10.00x100, 10.01x100; no sells | no auction, volume 0 | one side empty |

Invariants: V maximal over the candidate grid; no fill worse than its limit; quantity conserved. Acceptance A1 to A5 of `asset-conventions.md`.
