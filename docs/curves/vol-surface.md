# Implied volatility surface, calibrated

<p class="note">Status: Planned, stage E (in progress, target v0.5). No CLI operation exists yet, so this page has no numbers or charts. Nothing here is a result.</p>

## What it is

A full implied volatility surface calibrated to option quotes, as a heat grid by expiry and strike, with smile slices at three expiries. The surface is checked for calendar and butterfly arbitrage on its grid.

## Inputs

Synthetic option quotes on a strike and expiry grid, a spot, and flat funding and dividend curves, copied from a golden case. Synthetic inputs, not market data.

## Command

Not yet. When the operation lands, the page shows the command for `examples/vol_surface_grid_e.json`.

## Charts

None yet. Charts are drawn only from real CLI output when the gallery is built.

## Numbers

None yet.

## Four-language agreement

None yet. The page fills in when all four CLIs answer the operation.

## Oracle evidence and limits

Calibrated surfaces are compared with QuantLib where it has the same parametrisation, and with hand cases for the arbitrage checks. Targets are set in the stage E spec. Golden cases with an `ok` result in `datasets/golden/stage_e/` so far: 0.

## Output contract

The renderer reads `expiries` (years, ascending), `strikes` (ascending), `vols` as a list per expiry of one value per strike from the operation's outputs. Operation name `vol.surface.grid` is a placeholder until the stage E spec fixes it. See [the gallery index](README.md).
