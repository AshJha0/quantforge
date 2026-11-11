# FRTB standardised approach: FX, equity, CSR and commodity delta (stage F carry-over)

Spec version 1.0.0. Status: Specified (stage F carry-over wave 2b, landed in stage G). Rulings `stage-g-rulings.md` G-48, G-49. Suite `stage_f/frtb_f2b` (25 cases), written by `oracle/python/gen_stage_f_frtb2.py`. Read with `frtb-sa-girr.md`, whose aggregation and scenario rules apply unchanged.

**Plain idea.** The standardised FRTB charge multiplies each sensitivity by a regulator's risk weight, adds the weighted sensitivities within a bucket allowing for their correlation, then adds the buckets, again with a correlation, and takes the worst of three correlation scenarios. GIRR (interest rates) was specified in stage F. This page adds four more delta risk classes, FX, equity, credit spread (CSR, non-securitisation) and commodity, using the paragraph numbers of the BIS text.

Source: Basel Committee, *Basel Framework*, MAR21 (in force 2023-01-01, version published 2026-03-23), read from the free BIS web page on 2026-11-11: MAR21.4 (aggregation), MAR21.6 and 21.7 (scenarios), MAR21.24 (FX sensitivity), MAR21.77 Table 10 (equity weights), MAR21.78 (equity intra-bucket correlation), MAR21.80 (equity cross-bucket correlation), MAR21.86 to 21.89 (FX); MAR21.51, 21.53 Table 4, 21.54 to 21.57 Table 5 (CSR); MAR21.79 (equity bucket 11); MAR21.82 Table 11, 21.83 Table 12, 21.85 (commodity). Values quoted from the page text; correlation formulas that appear only as images are not used.

## `risk.frtb.fx_delta`

Inputs: `sensitivities` (at least one, else `E_INPUT`), each `{pair, sensitivity}` (one bucket per exchange rate, MAR21.86; a pair twice is `E_INPUT`); optional `specified_pairs`, the pairs (and first-order crosses) the bank elects to treat under MAR21.88.

Recipe: `RW = 15%` (MAR21.87), divided by `sqrt(2)` for a listed pair (MAR21.88). One risk factor per bucket, so `K_b = |WS_b|`. Cross-bucket `gamma = 60%` (MAR21.89). Aggregation and scenarios as `frtb-sa-girr.md` (MAR21.4, 21.6).

Worked example (`frtb_f2b-0002`): EURUSD 1,000,000 and USDJPY -400,000 give `WS = 150,000` and `-60,000`. Medium: `sqrt(150,000^2 + 60,000^2 - 2 x 0.6 x 150,000 x 60,000) = 123,693`. Low (`gamma = max(2 x 0.6 - 1, 0.75 x 0.6) = 45%`): 134,164, the binding scenario.

## `risk.frtb.equity_delta`

Inputs: `sensitivities`, each `{issuer, bucket, kind, sensitivity}`, `kind` `SPOT` or `REPO`, `bucket` 1 to 13 (unknown buckets are `E_INPUT`; the same issuer, bucket and kind twice is `E_INPUT`).

Recipe:
- Risk weights (MAR21.77 Table 10), spot / repo: bucket 1: 55% / 0.55%; 2: 60% / 0.60%; 3: 45% / 0.45%; 4: 55% / 0.55%; 5: 30% / 0.30%; 6: 35% / 0.35%; 7: 40% / 0.40%; 8: 50% / 0.50%; 9: 70% / 0.70%; 10: 50% / 0.50%; 11: 70% / 0.70%; 12: 15% / 0.15%; 13: 25% / 0.25%.
- Bucket 11, other sector (MAR21.79, ruling G-49): the correlations do not apply; `K_11` is the simple sum of the absolute values of the net weighted sensitivities, netted per risk factor (issuer and kind). Cross-bucket correlation with bucket 11 is 0% (MAR21.80).
- Within a bucket (MAR21.78): same issuer, spot against repo: 99.90%. Different issuers, same kind: 15% (buckets 1 to 4), 25% (5 to 8), 7.5% (9), 12.5% (10), 80% (12, 13). Different issuers, spot against repo: those values times 99.90%.
- Across buckets (MAR21.80): 15% within buckets 1 to 10; 75% between 12 and 13; 45% otherwise.

Worked example (`frtb_f2b-0008`): issuer A in bucket 5, spot sensitivity 1,000,000 (WS 300,000) and repo 50,000,000 (WS 150,000), correlated 99.9%: medium `K = 449,900`; high caps the correlation at 100%, giving 450,000.

## `risk.frtb.csr_delta` (ruling G-49)

Inputs: `sensitivities`, each `{issuer, bucket (1 to 18), tenor (0.5Y, 1Y, 3Y, 5Y, 10Y), curve (BOND or CDS), sensitivity}`; other buckets or tenors are `E_INPUT`.

Recipe: risk weights (MAR21.53 Table 4, %): 1: 0.5; 2: 1.0; 3: 5.0; 4: 3.0; 5: 3.0; 6: 2.0; 7: 1.5; 8: 2.5; 9: 2.0; 10: 4.0; 11: 12.0; 12: 7.0; 13: 8.5; 14: 5.5; 15: 5.0; 16: 12.0; 17: 1.5; 18: 5.0. Within a bucket, `rho = rho_name x rho_tenor x rho_basis`: name 1 if the same issuer, else 35% (80% in buckets 17 and 18); tenor 1 if the same, else 65%; basis 1 if the same curve, else 99.9% (MAR21.54, 21.55). Bucket 16 (other sector, MAR21.56): simple sum of absolute net weighted sensitivities. Across buckets, `gamma = rating x sector` (MAR21.57): rating 50% when both buckets are in 1 to 15 and one is investment grade (1 to 8) and the other high yield (9 to 15), else 1; sector 1 for the same sector, else Table 5 (sectors 1/9, 2/10, 3/11, 4/12, 5/13, 6/14, 7/15, 8, 16, 17, 18; bucket 16 has 0% with all, 17 against 18 is 75%, the indices against sectors 1 to 8 are 45%).

Worked example (`frtb_f2b-0019`): other-sector names O1 and O2 at +1 and -1 million give `K_16 = 12% x 2,000,000 = 240,000` (no offset), and a bucket-1 position of 20 million gives 100,000; with `gamma = 0`, capital `sqrt(240,000^2 + 100,000^2) = 260,000`.

Caution: Table 5 was read from the BIS page through an automated page reader, which printed one triangle; the matrix is taken as symmetric. A spot check of Table 5 against the PDF is part of the owner item below.

## `risk.frtb.commodity_delta` (ruling G-49)

Inputs: `sensitivities`, each `{commodity, bucket (1 to 11), tenor, location, sensitivity}`.

Recipe: risk weights (MAR21.82 Table 11, %): 1: 30; 2: 35; 3: 60; 4: 80; 5: 40; 6: 45; 7: 20; 8: 35; 9: 25; 10: 35; 11: 50. Within a bucket `rho = rho_cty x rho_tenor x rho_basis` (MAR21.83): commodity 1 if identical, else Table 12 (1: 55; 2: 95; 3: 40; 4: 80; 5: 60; 6: 65; 7: 55; 8: 45; 9: 15; 10: 40; 11: 15, %); tenor 1 or 99%; delivery location 1 or 99.9%. Across buckets (MAR21.85): 20% within 1 to 10, 0% with bucket 11.

Worked example (`frtb_f2b-0023`): Brent +1 million and WTI -1 million in bucket 2 (35%), correlation `0.95 x 0.999`; the low scenario (`max(2 rho - 1, 0.75 rho)`) binds at 158,004.75.

## Owner item: vega and curvature (G-49, as F-33)

Vega and curvature for every class are not specified. The vega weights are readable (MAR21.92 Table 13: liquidity horizons 60, 120, 120, 120, 20, 60, 120, 40 days; weights 100% except 77.78% for large-cap equity and indices), but the vega risk-weight formula, the vega correlations (MAR21.93 to 21.95), the curvature charge `CVR_k` and its bucket aggregation (MAR21.5), the other-sector curvature formulas (MAR21.56(2), 21.69(2), 21.79(2)) and the curvature correlations (MAR21.100, 21.101) appear only as images on the BIS page. The owner confirms them from the PDF (and spot-checks Table 5), then the goldens are written.

## Outside share

None (no outside implementation or worked example of MAR21).

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| MAR21.4 aggregation | exact | `frtb_f2b` | one factor: `capital = RW x |s|` (`-0001`, `-0007`, `-0016`, `-0022`) | MAR21.4 |
| Other-sector simple sum | exact | `-0012`, `-0019` | no offset between names | MAR21.56, 21.79 |
