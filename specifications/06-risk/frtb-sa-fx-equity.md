# FRTB standardised approach: FX delta and equity delta (stage F carry-over)

Spec version 1.0.0. Status: Specified (stage F carry-over wave 2b, landed in stage G). Ruling `stage-g-rulings.md` G-48. Suite `stage_f/frtb_f2b` (15 cases), written by `oracle/python/gen_stage_f_frtb2.py`. Read with `frtb-sa-girr.md`, whose aggregation and scenario rules apply unchanged.

**Plain idea.** The standardised FRTB charge multiplies each sensitivity by a regulator's risk weight, adds the weighted sensitivities within a bucket allowing for their correlation, then adds the buckets, again with a correlation, and takes the worst of three correlation scenarios. GIRR (interest rates) was specified in stage F. This page adds two more risk classes, FX and equity, using the paragraph numbers of the BIS text.

Source: Basel Committee, *Basel Framework*, MAR21 (in force 2023-01-01, version published 2026-03-23), read from the free BIS web page on 2026-11-11: MAR21.4 (aggregation), MAR21.6 and 21.7 (scenarios), MAR21.24 (FX sensitivity), MAR21.77 Table 10 (equity weights), MAR21.78 (equity intra-bucket correlation), MAR21.80 (equity cross-bucket correlation), MAR21.86 to 21.89 (FX). Values quoted from the page text; correlation formulas that appear only as images are not used.

## `risk.frtb.fx_delta`

Inputs: `sensitivities` (at least one, else `E_INPUT`), each `{pair, sensitivity}` (one bucket per exchange rate, MAR21.86; a pair twice is `E_INPUT`); optional `specified_pairs`, the pairs (and first-order crosses) the bank elects to treat under MAR21.88.

Recipe: `RW = 15%` (MAR21.87), divided by `sqrt(2)` for a listed pair (MAR21.88). One risk factor per bucket, so `K_b = |WS_b|`. Cross-bucket `gamma = 60%` (MAR21.89). Aggregation and scenarios as `frtb-sa-girr.md` (MAR21.4, 21.6).

Worked example (`frtb_f2b-0002`): EURUSD 1,000,000 and USDJPY -400,000 give `WS = 150,000` and `-60,000`. Medium: `sqrt(150,000^2 + 60,000^2 - 2 x 0.6 x 150,000 x 60,000) = 123,693`. Low (`gamma = max(2 x 0.6 - 1, 0.75 x 0.6) = 45%`): 134,164, the binding scenario.

## `risk.frtb.equity_delta`

Inputs: `sensitivities`, each `{issuer, bucket, kind, sensitivity}`, `kind` `SPOT` or `REPO`, `bucket` 1 to 10, 12 or 13 (bucket 11 is outside this slice, since MAR21.79 treats it by a separate rule; it and unknown buckets are `E_INPUT`; the same issuer, bucket and kind twice is `E_INPUT`).

Recipe:
- Risk weights (MAR21.77 Table 10), spot / repo: bucket 1: 55% / 0.55%; 2: 60% / 0.60%; 3: 45% / 0.45%; 4: 55% / 0.55%; 5: 30% / 0.30%; 6: 35% / 0.35%; 7: 40% / 0.40%; 8: 50% / 0.50%; 9: 70% / 0.70%; 10: 50% / 0.50%; 12: 15% / 0.15%; 13: 25% / 0.25%.
- Within a bucket (MAR21.78): same issuer, spot against repo: 99.90%. Different issuers, same kind: 15% (buckets 1 to 4), 25% (5 to 8), 7.5% (9), 12.5% (10), 80% (12, 13). Different issuers, spot against repo: those values times 99.90%.
- Across buckets (MAR21.80): 15% within buckets 1 to 10; 75% between 12 and 13; 45% otherwise.

Worked example (`frtb_f2b-0008`): issuer A in bucket 5, spot sensitivity 1,000,000 (WS 300,000) and repo 50,000,000 (WS 150,000), correlated 99.9%: medium `K = 449,900`; high caps the correlation at 100%, giving 450,000.

## Not specified here (G-48)

Vega and curvature for every class, CSR and commodity delta. The vega weights are in MAR21.92 Table 13 (for example 77.78% for large-cap equity, 100% elsewhere), but the vega and curvature correlation formulas (MAR21.93 to 21.95, 21.100, 21.101) and the curvature charge `CVR_k` (MAR21.5) appear only as images on the BIS page. As with F-33, they need the owner to confirm the formulas from the PDF before goldens are written.

## Outside share

None (no outside implementation or worked example of MAR21).

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| MAR21.4 aggregation | exact | `frtb_f2b` | one factor: `capital = RW x |s|` (`-0001`, `-0007`, asserted) | MAR21.4 |
