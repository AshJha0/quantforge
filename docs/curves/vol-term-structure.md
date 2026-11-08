# Volatility term structures

<p class="note">Status: Planned, stage E (in progress, target v0.5). No CLI operation exists yet, so this page has no numbers or charts. Nothing here is a result.</p>

## What it is

At-the-money implied volatility by expiry, and the forward volatility between consecutive expiries that it implies. A negative forward variance would mean calendar arbitrage.

## Inputs

A synthetic surface's at-the-money total variance by expiry, copied from a golden case. Synthetic inputs, not market data.

## Command

Not yet. When the operation lands, the page shows the command for `examples/vol_term_structure_e.json`.

## Charts

None yet. Charts are drawn only from real CLI output when the gallery is built.

## Numbers

None yet.

## Four-language agreement

None yet. The page fills in when all four CLIs answer the operation.

## Oracle evidence and limits

Forward variance is checked against hand cases. The at-the-money volatilities come from the same surface as the implied surface page. Golden cases with an `ok` result in `datasets/golden/stage_e/` so far: 0.

## Output contract

The renderer reads `expiries` (years, ascending) and `atm_vols`; optional `forward_vols`, one per expiry from the operation's outputs. Operation name `vol.surface.term` is a placeholder until the stage E spec fixes it. See [the gallery index](README.md).
