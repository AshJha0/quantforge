# Simulated FX dealer-to-client venue with last look (H-23)

Spec version 0.1.0 (drafted 2026-11-18; rulings HR-87 to HR-89, HR-97). Label always: "simulated venue; not a real exchange; no real FX data". Last-look concept from [FXGC] Principle 17 (unverified this session). The model is a stated toy, not any dealer's practice.

**Plain idea.** A dealer streams a bid and an ask. A client hits one. The dealer holds the request for a short window; if the market has moved too far it rejects, otherwise it fills at the quoted price (a small random reject rate is also allowed).

## Operations
`exec.sim.fx.stream`: inputs `mid_path` (time, mid), `half_spread_pips`, `pair`, `tick`; output quotes, bid rounded down and ask rounded up to the tick.

`exec.sim.fx.request`: inputs `quote` (bid, ask, quote_mid), `side` (client BUY takes the ask, SELL hits the bid), `qty`, `mid_after` (mid at the end of `hold_ms`), `threshold_pips`, `symmetric` (default true), `p_random_reject`, `u` in [0,1). In simulations `u` comes from `core.rng`: when `u` is absent, `seed` (integer, 0 to 2^64 - 1) and `request_index` (integer >= 0) are required and u is the first `uniform` of stream `request_index` of the generator seeded by `seed` (rng.md: stream k is the seeded generator jumped k times); the output then also carries `u` (binary64, HR-97). Goldens fxv_h-0001..0009 give `u` directly; fxv_h-0010..0012 draw it (hand, oracle generator, not blind).

Rule (HR-97): move = (mid_after - quote_mid)/pip. Adverse to the dealer: move > 0 when the client buys, move < 0 when the client sells. If `symmetric`, reject `LL_PRICE` when |move| > threshold; otherwise reject `LL_PRICE` only when the adverse move exceeds the threshold. If not rejected on price, reject `LL_RANDOM` when u < p_random_reject. Otherwise `FILL` at the quoted price. Comparisons are strict; exact decimals.

Outputs: `outcome`, `price` (null on reject), `move_pips`. Reports: reject rate by reason; mean move on fills (TCA hook).

Plugs into: SOR as a venue of class FX (request for quote, not a book); paper trading posts per-currency cash on the spot date (`../09-microstructure/asset-conventions.md` 2.3).

## Golden value cases (EURUSD, pip 0.0001)
| Case | Input | Expected | Derivation |
|---|---|---|---|
| fxv_h-0001 | stream mid 1.08512, half-spread 1 pip, tick 0.00001 | bid 1.08502, ask 1.08522 | plus and minus 0.0001, on grid |
| fxv_h-0002 | stream mid 1.085125, half-spread 1 pip, tick 0.00001 | bid 1.08502, ask 1.08523 | 1.085025 down, 1.085225 up |
| fxv_h-0003 | quote 1.0850/1.0852, quote_mid 1.0851; client BUY; mid_after 1.0855; threshold 2; symmetric; p 0.05; u 0.50 | LL_PRICE | move +4 > 2 |
| fxv_h-0004 | as fxv_h-0003 with mid_after 1.0852 | FILL 1.0852 | move +1; u not below p |
| fxv_h-0005 | as fxv_h-0004 with u 0.03 | LL_RANDOM | u < 0.05 |
| fxv_h-0006 | as fxv_h-0003 with mid_after 1.0847 | LL_PRICE | move -4, abs 4 > 2 |
| fxv_h-0007 | as fxv_h-0006 with symmetric false | FILL 1.0852 | -4 is not adverse for a client buy |
| fxv_h-0008 | client SELL; quote as fxv_h-0003; mid_after 1.0848; symmetric false; p 0.05; u 0.50 | LL_PRICE | move -3 adverse for a sell, > 2 |
| fxv_h-0009 | as fxv_h-0004 with mid_after 1.0853 | FILL 1.0852 | move +2, not strictly above 2 |

## Output shapes (pre-comparison spec fix, 2026-11-18, HR-100)
Decimal inputs (mids, pips, `u`, `p_random_reject`) are HR-12 decimal strings; `pair` names the pip. `exec.sim.fx.stream`: `{status, label, quotes: [{time, mid, bid, ask}]}`; a golden with one mid is a one-point path at time 0. `exec.sim.fx.request`: `{status, label, outcome ("FILL"|"LL_PRICE"|"LL_RANDOM"), price (decimal or null), move_pips (decimal)}`.
