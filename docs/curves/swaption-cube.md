# Swaption volatility cube

<p class="note">Status: Planned, stage E (in progress, target v0.5). No CLI operation exists yet, so this page has no numbers or charts. Nothing here is a result.</p>

## What it is

Swaption volatilities by option expiry, underlying swap tenor and strike: the at-the-money matrix as a heat grid, and smiles for the shortest and longest tenor at a middle expiry.

## Inputs

A synthetic at-the-money matrix and SABR smile parameters per expiry and tenor, copied from a golden case. Synthetic inputs, not market data.

## Command

Not yet. When the operation lands, the page shows the command for `examples/swaption_cube_e.json`.

## Charts

None yet. Charts are drawn only from real CLI output when the gallery is built.

## Numbers

None yet.

## Four-language agreement

None yet. The page fills in when all four CLIs answer the operation.

## Oracle evidence and limits

Compared with QuantLib `SabrSwaptionVolatilityCube` where the conventions match, and with hand cases at the at-the-money strike. Golden cases with an `ok` result in `datasets/golden/stage_e/` so far: 0.

## Output contract

The renderer reads `expiries`, `tenors` (years), `strikes` (offsets from ATM in bp, with 0 present), `vols` as [expiry][tenor][strike] from the operation's outputs. Operation name `rates.swaption.cube` is a placeholder until the stage E spec fixes it. See [the gallery index](README.md).
