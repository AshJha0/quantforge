# Simulated Treasury futures venue (H-24)

Spec version 0.1.0 (drafted 2026-11-18; rulings HR-90 to HR-92). Label: "simulated venue; not a real exchange; no real rates data". Contract specs are parameters with [CME-ZN] and [CME-ZB] defaults (unverified this session; see `../09-microstructure/asset-conventions.md`).

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
