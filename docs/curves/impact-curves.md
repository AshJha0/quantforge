# Market impact curves: square-root and Obizhaeva-Wang

<p class="note">Planned for v0.10.0 (stage H). The operations are specified (spec version 0.1.0, confirmed 2026-11-18) but not merged, so this page is written by hand from the spec's golden cases and is not generated from CLI runs. The coefficient <code>Y</code> is assumed, not estimated; no number here describes a real venue.</p>

## What it is

The plain idea: the more you trade, the more the price moves against you, but less than in proportion. The square-root law says the average move over an order grows with the square root of its size relative to daily volume. A separate question is how fast that move fades once you stop; Obizhaeva and Wang model the order book refilling at a rate `rho`, which changes the cheapest way to trade.

Formally (spec [`10-execution/impact.md`](../../specifications/10-execution/impact.md), rulings HR-2 and HR-10):

- Square-root impact, [TLD11] eq. (1): `I(Q) = Y sigma sqrt(Q / V)`, with `I` the average relative price change over a metaorder of `Q` units, `V` the daily volume, `sigma` the daily volatility and `Y` a coefficient the paper calls "of order unity". Here `Y` is an input, default 1, labelled assumed.
- Obizhaeva-Wang risk-neutral optimum, [OW13] Proposition 3, eq. (31), p. 17: a block of `X / (rho T + 2)` at the start, a constant rate `rho X / (rho T + 2)` over `(0, T)`, and an equal block at the end. The strategy does not depend on the impact size or the book depth ([OW13] section 7.1).

## The square-root curve, from the goldens

`V = 1e7`, `sigma = 0.02`, `Y = 1`.

| Size `Q` | Share of daily volume | Impact | Case |
|---|---|---|---|
| 100,000 | 1 % | 0.002 (20 bp) | `imp_h-0001` |
| 400,000 | 4 % | 0.004 (40 bp) | `imp_h-0002` |

Four times the size, twice the impact. These cases check the arithmetic of the stated form, not the empirical law; whether a market follows it, and with what `Y` and exponent, is the job of the crypto study (plan item H-1(a), a venue-level proxy with a standard error).

The stage J [liquidity cost curve](liquidity.md) uses the same form with daily participation `Q/(V h)`; at `h = 1` and exponent 1/2 it equals `imp_h-0001`.

## The Obizhaeva-Wang schedule, from the goldens

| `X` | `T` | `rho` | Each block | Rate | Case |
|---|---|---|---|---|---|
| 1,000 | 1 | 8 | 100 | 800 | `imp_h-0003` |
| 100,000 | 1 day | 2.231 | 23,635.0744504845 | 52,729.8510990310 | `imp_h-0004`, the parameters of [OW13] Fig. 2, p. 14 |

As `rho` falls to 0 each block tends to `X/2`: with no refill there is no point trading in between (property test). The paper's Fig. 2 labels the first trade of its discrete solutions for 10, 25 and 100 steps as 26,317, 24,697 and 23,899; they fall towards 23,635, a consistency remark, not a printed check.

## Evidence

All four cases were re-derived blind from the inputs only by a second lane (DR-H2, 2026-11-15): 0001 to 0003 exact, 0004 within 8e-16 relative. [TLD11] eq. (1) read 2026-11-18 in the arXiv v3 HTML; [OW13] read 2026-11-15 in the published version.

## What it does not show

Static formulas with assumed parameters. No permanent-impact estimate, no decay fitted to data, and no claim about any venue until the calibration lane reports with standard errors. Results from the crypto study, when they come, are labelled "crypto venue; not equities or rates".

## Related

[Tutorial 39](../getting-started/tutorial-39-market-impact.md); [glossary: market impact](../../GLOSSARY.md#market-impact).
