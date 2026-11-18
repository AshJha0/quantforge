# Venue analytics: markouts, fill rates, toxicity

Spec version 0.1.0 (stage H wave 2, H-16; written 2026-11-18). Status: Specified, not implemented. Rulings HR-72, HR-73. VPIN is not specified: the [ELO12] bucket example could not be verified (HR-73).

Sources: the usual desk definitions, written out in full here; no number comes from a paper. Evidence class: definition and hand calculation, checked with mpmath by the spec lane; not yet blind re-derived.

## `exec.venue.analytics`
Inputs: `mids` list of (t, m), t strictly increasing; `fills` list of (venue, side s = +1 BUY or -1 SELL, q, p, t); `orders` list of (venue, sent, filled); `horizons` list of h.

Mid at u: the last m with t <= u (HR-72); none: `E_INPUT`.

Per venue V and horizon h, over V's fills:
- `markout` = `sum s q (m(t+h) - p) / sum q` (price units per share)
- `markout_bps` = `1e4 * sum s q (m(t+h) - p) / sum q p`
- `toxicity` = `sum q [s (m(t+h) - p) < 0] / sum q`

Per venue: `fill_rate` = `sum filled / sum sent` over V's orders.

A venue with no fills has no markout or toxicity rows; one with no orders has no fill rate. Errors: filled > sent or non-increasing mid times `E_INPUT`; a price, mid, q or sent <= 0, filled < 0, or h < 0 `E_DOMAIN`. Outputs binary64, 1e-12 relative (an expected 0 compared absolutely to 1e-15).

## Golden cases
Base input: mids (0, 100.00), (1, 100.02), (5, 100.05), (10, 99.98). Fills F1 (A, BUY, 100, 100.01, t 0), F2 (A, SELL, 200, 100.03, t 1), F3 (B, BUY, 300, 100.00, t 1). Orders (A, 500, 300), (B, 300, 300). For A, sum q p = 30,007; for B, 30,000.

| Case | Input | Expected | Derivation |
|---|---|---|---|
| venue_h-0001 | base, h = 5 | A: markout 0, bps 0, toxicity 0.666666666666667; B: markout 0.05, bps 5, toxicity 0 | mids 100.05 (t 5, 6); F1 +4, F2 -4, F3 +15; 15/30,000 x 1e4 |
| venue_h-0002 | base, h = 10 | A: markout 0.0233333333333333, bps 2.33278901589629, toxicity 0.333333333333333; B: markout -0.02, bps -2, toxicity 1 | mids 99.98 (t 10, 11); F1 -3, F2 +10, F3 -6; 7/300; 7e4/30,007 |
| venue_h-0003 | base, h = 0 | A: markout 0.00333333333333333, bps 0.333255573699470, toxicity 0.333333333333333; B: markout 0.02, bps 2, toxicity 0 | F1 mid 100.00: -1; F2 mid 100.02: +2; F3 mid 100.02: +6 |
| venue_h-0004 | base, fill rates | A 0.6; B 1 | 300/500; 300/300 |
| venue_h-0005 | base with order (A, 500, 600) | `E_INPUT` | filled > sent |
| venue_h-0006 | base with a fill (B, BUY, 10, 100, t -1) | `E_INPUT` | no mid at or before -1 |
| venue_h-0007 | base, h = -1 | `E_DOMAIN` | negative horizon |

## Property tests
For every venue and h, `markout_bps` has the sign of `markout`; toxicity lies in [0, 1]; reversing every side and reflecting every price and mid about a constant c (p -> 2c - p) leaves markout unchanged.

## Limitations
Markouts use the mid only (no microprice, no spread-adjusted variant); the horizon is clock time, not event time; VPIN is omitted (HR-73). Nothing here is measured on real venue data.
