# Local volatility (Dupire)

<p class="note">Status: Planned, stage E (in progress, target v0.5). No CLI operation exists yet, so this page has no numbers or charts. Nothing here is a result.</p>

## What it is

Dupire local volatility derived from an arbitrage-free implied surface, as a heat grid by time and spot level, with slices at three times. Local volatility is the diffusion coefficient that reprices every vanilla on the surface.

## Inputs

A synthetic implied surface, the same parameters as a golden case, evaluated on a time and strike grid. Synthetic inputs, not market data.

## Command

Not yet. When the operation lands, the page shows the command for `examples/vol_local_grid_e.json`.

## Charts

None yet. Charts are drawn only from real CLI output when the gallery is built.

## Numbers

None yet.

## Four-language agreement

None yet. The page fills in when all four CLIs answer the operation.

## Oracle evidence and limits

Compared with QuantLib `LocalVolSurface` on the same implied surface, and with the flat-surface hand case, where local and implied volatility are equal. Golden cases with an `ok` result in `datasets/golden/stage_e/` so far: 0.

## Output contract

The renderer reads `expiries` (years, ascending), `strikes` (ascending), `vols` as a list per expiry of one value per strike from the operation's outputs. Operation name `vol.local.grid` is a placeholder until the stage E spec fixes it. See [the gallery index](README.md).
