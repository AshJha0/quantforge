# Simulated Treasury futures venue (H-24)

Spec version 0.1.0 (drafted 2026-11-18; rulings HR-90 to HR-92). Label: "simulated venue; not a real exchange; no real rates data". Contract specs are parameters with [CME-ZN] (face, tick and tick value verified 2026-11-19, HR-117) and [CME-ZB] (read 2026-11-19) defaults (see `../09-microstructure/asset-conventions.md`).

**Plain idea.** The existing lit engine runs unchanged in integer ticks; for futures a tick is 1/64 (ZN) or 1/32 (ZB) of a point. Prices are shown in 32nds and P&L is ticks times tick value.

## Operation `exec.sim.fut.run`
Inputs: `contract` (HR-91), `events` with prices as 32nds strings or decimals, `fee_per_contract` (per side). Prices map to ticks by `asset-conventions.md` 3.1; ticks = price / tick; a price off the contract grid is `E_DOMAIN`. Matching = `exec.sim.lit.run` (FIFO). Outputs: as the lit engine plus `pnl` per participant = sum of signed ticks x qty x tick_value - fees. Daily settlement price = last trade (mid if none); variation margin = (settle - previous mark) in ticks x qty x tick_value (HR-92).

## Golden value cases (ZN: tick 1/64, tick value 15.625 unless stated)
| Case | Input | Expected | Derivation |
|---|---|---|---|
| fut_h-0001 | price 110-16+ to ticks | 7073 | 110 x 64 + 33 |
| fut_h-0002 | ticks 7073 to string | 110-16+ | inverse |
| fut_h-0003 | price 110-162 to ticks | E_DOMAIN | 1/128 not on the 1/64 grid |
| fut_h-0004 | buy 3 at 110-16, sell 3 at 110-17+, fee 0 | pnl +140.625 | 3 ticks x 3 x 15.625 |
| fut_h-0005 | as fut_h-0004, fee 1.00 per contract per side | pnl +134.625 | 140.625 - 6 |
| fut_h-0006 | ZB (tick 1/32, value 31.25): buy 1 at 120-00, settle 119-31 | variation margin -31.25 | -1 tick x 31.25 |
| fut_h-0011 | `exec.sim.fut.run`, ZN: S1 (M) sells 3 at 110-16, B1 (P) buys 3 at 110-16, S2 (P) sells 3 at 110-17+, B2 (N) buys 3 at 110-17+; fee 1.00 | fills at 110.5 and 110.546875; pnl P +134.625, M -143.625, N -3; fees P 6, M 3, N 3 | mark = last trade, 7075 ticks. P: 3 ticks x 3 x 15.625 - 6. M: -3 ticks x 3 x 15.625 - 3. N: 0 - 3. The sum is minus the fees |
| fut_h-0012 | `exec.sim.fut.run`, ZB: X1 (X) sells 2 at 120-00, Y1 (Y) buys 1 at 120-01, Z1 (Z) sells 1 at 119-31, W1 (W) buys 1 at 120-00; fee 0.50 | fills at 120 and 119.96875; X1 rests 1; pnl X +30.75, Y -31.75, Z -0.5, W -0.5 | maker price, then price priority; mark 3839 ticks. X: +1 tick x 31.25 - 0.5. Y: -1 tick x 31.25 - 0.5 |
| fut_h-0013 | `exec.sim.fut.run`, no events | empty book, no fills, empty `pnl` and `fees` | nothing traded |

fut_h-0011 to fut_h-0013 were added on 2026-11-19: until then `exec.sim.fut.run` had unit tests in each language but no shared golden. They are hand cases, not blind; the lit-engine fields follow `exec.sim.lit.run`. Error cases fut_h-0014 to fut_h-0016: a price off the contract grid and a negative fee are `E_DOMAIN`; an event that is not an object is `E_SCHEMA`.

## Output shapes and gap rulings (pre-comparison spec fixes, 2026-11-18, HR-100, HR-102, HR-103)
Operations `exec.sim.fut.to_ticks`, `exec.sim.fut.to_text`, `exec.sim.fut.pnl`, `exec.sim.fut.variation` (`variation_margin` is a list, one per settlement) and `exec.sim.fut.run`; decimals are HR-12 decimal strings; `contract` defaults to `{symbol: ZN}`. Price to ticks `{status, label, ticks}`; ticks to text `{status, label, text}`; trade P&L `{status, label, pnl, fees}`; variation `{status, label, variation_margin}`.
HR-102 (gap found by the blind lane): fut_h-0004 and fut_h-0005 list a buy and a sell at different prices that would not cross in one book; they are **one participant's round trip filled against other resting orders**, pnl = (sell ticks - buy ticks) x qty x tick_value - fees; the fee is per contract per side (3 + 3 = 6 contracts).
HR-103 (gap found by the blind lane): on the trade day the previous mark for variation margin is the **fill price**; on later days it is the previous settlement price.
