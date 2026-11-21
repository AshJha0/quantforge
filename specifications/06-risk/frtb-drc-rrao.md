# FRTB standardised approach: default risk capital (DRC) and residual risk add-on (RRAO)

Spec version 0.1.0. Status: implemented in all four builds (Python `python/quantforge_core/frtb_drc.py`; Java, C++ and Rust ports per `program/STAGE_K_W2A_HANDOVER.md` and `program/STAGE_K_W2B_HANDOVER.md`) on the wave 2 integration branch `k-r3-w2` (2026-11-20), merge into `k-v1` pending; goldens in `datasets/golden/stage_k/` (spec lane 2026-11-19). The rulings stay PROPOSED except those confirmed in `stage-k-rulings-w2.md` (KR-312, KR-315, KR-319, KR-320, KR-324, KR-327, confirmed 2026-11-20). Rulings `stage-k-rulings-w2.md` KR-50 to KR-55, KR-67 to KR-69. Parameters `specifications/tables/stage_k/mar22_drc.json` and `mar23_rrao.json`. Gate status: `program/STAGE_K_W2_GATE.md`.

Every output carries `label`: "regulatory formula on caller inputs; not a regulatory return" (KR-69).

**Plain idea.** The sensitivities-based charge (stage F, `frtb-sa-girr.md` and neighbours) prices small moves in credit spreads. It does not price the jump when an issuer defaults. The DRC does: for each position it asks "what would we lose if this issuer defaulted tomorrow with the standard recovery", lets longs and shorts on the same issuer cancel, lets shorts on other issuers in the same bucket partly hedge longs, and weights the result by a rating-based default probability. The RRAO is a blunt add-on for what neither charge sees: exotic underlyings (weather, longevity, realised volatility) at 1% of notional and other hard-to-replicate payoffs (barriers, baskets, Bermudans) at 0.1%.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [MAR22] | Basel Framework MAR22, version effective 1 January 2023, in the consolidated PDF generated 11/11/2026, PDF pp. 619-633 | read 2026-11-19 (text; formulas from images pp. 622, 627, 628, 633) | every DRC rule and parameter |
| [MAR23] | Basel Framework MAR23, same PDF, pp. 634-637 | read 2026-11-19 | RRAO scope, exclusions, weights |
| [LEX30] | Basel Framework LEX30.17-30.19, pp. 948 | read 2026-11-19 | reuse of the gross JTD in `leverage-large-exposures.md` |

No library computes the standardised DRC, so there is no independent-library check; outside checks are the two printed examples (P) and, if run, a DR-H2 blind lane (B).

## Formal statement

### `risk.frtb.drc_nonsec`

Inputs (KR-51): `positions` (1 to 100,000), each `{id, obligor, bucket, seniority, notional, market_value, maturity_years, cash_equity?, lgd_applies?}`; `ratings` map obligor to one of `AAA, AA, A, BBB, BB, B, CCC, UNRATED, DEFAULTED`.

1. **Gross JTD** (MAR22.11, MAR22.12): `LGD` = 1 for `EQUITY` and `NON_SENIOR`, 0.75 for `SENIOR`, 0.25 for `COVERED`; with `lgd_applies: false` the notional is not multiplied (MAR22.12(4)). `PnL = market_value - notional`. If `notional > 0` (long): `JTD = max(LGD notional + PnL, 0)`; if `notional < 0` (short): `JTD = min(LGD notional + PnL, 0)`. For cash equity, notional equals market value (KR-51), so `JTD = market_value`.
2. **Maturity weight** (MAR22.15, MAR22.18, KR-52): `w = 1` if `maturity_years >= 1`, else `max(maturity_years, 0.25)`; scaled `JTD' = w JTD`.
3. **Offset per obligor** (MAR22.19-22.21, KR-53): shorts offset longs of the same or higher seniority, greedy rule of KR-53. Result per obligor: `net_long >= 0`, `net_short <= 0`. The direction is by rank (`COVERED` 4, `SENIOR` 3, `NON_SENIOR` 2, `EQUITY` 1): a short of rank r offsets only longs of rank r or above, so a short equity offsets a long senior bond but a short senior bond does not offset a long equity (drc_k-0007, drc_k-0008; inferred from the expected values; blind lane note, stage_k_blind/w2/notes.md). Offsetting uses the maturity-weighted `JTD'` of step 2 (drc_k-0004).
4. **Bucket** (MAR22.22, MAR22.23, MAR22.24, MAR22.25): with `RW` from the obligor's rating (0.005, 0.02, 0.03, 0.06, 0.15, 0.30, 0.50, 0.15 unrated, 1 defaulted),
   `HBR = sum net_long / (sum net_long + sum |net_short|)`,
   `DRC_b = max(sum RW net_long - HBR sum RW |net_short|, 0)`.
5. **Total** (MAR22.26): `DRC = sum_b DRC_b`.

Outputs: `positions` (`id`, `gross_jtd`, `weight`, `scaled_jtd`), `obligors` (`obligor`, `net_long`, `net_short`, `rw`), `buckets` (`bucket`, `hbr` or null, `wtd_long`, `wtd_short`, `drc`), `drc`, `label`.

### `risk.frtb.drc_sec_nonctp`

Inputs: `positions` `{id, bucket, pool, tranche, market_value, maturity_years, rw}`; JTD = market value, no LGD (MAR22.27); maturity weight as above (MAR22.30), applied to each position's JTD before offsetting, as in `drc_nonsec`; offsetting only between positions with the same `pool` and `tranche` (MAR22.29); then HBR and `DRC_b` as MAR22.25 with the caller's `rw` (MAR22.33, KR-55); total = sum (MAR22.35).

### `risk.frtb.drc_ctp`

Inputs: either `positions` `{id, index, series, tranche, market_value, maturity_years, rw}` or `bucket_drc` (list of numbers). JTD = market value, scaled by the maturity weight of `drc_nonsec` step 2 before netting (no golden case has a maturity under one year, so no expected value pins this; it matches the securitisation rule above). Netting within identical `index`, `series`, `tranche` across maturities (MAR22.39(1)); `HBR_ctp` from all CTP net longs and shorts together, across every index bucket, on the net amounts before risk weighting: `HBR_ctp = sum net_long / (sum net_long + sum |net_short|)` as in `drc_nonsec` step 4 (ctp_k-0002: hbr_ctp 0.5 = 1000 / 2000 over both indices; inferred from the expected values; blind lane note, stage_k_blind/w2/notes.md); `DRC_b = sum RW net_long - HBR_ctp sum RW |net_short|` with **no floor** (MAR22.44); `DRC_CTP = max(sum_b (max(DRC_b, 0) + 0.5 min(DRC_b, 0)), 0)` (MAR22.45). Decomposition and replication offsets of MAR22.39(2)-(3) are the caller's (they need a valuation model).

### `risk.frtb.rrao`

Inputs: `instruments` `{id, gross_notional >= 0, kind (EXOTIC, OTHER), listed_or_clearable, back_to_back}`. Excluded: `back_to_back` (MAR23.7), and `OTHER` with `listed_or_clearable` (MAR23.7). `RRAO = sum gross_notional x (0.01 for EXOTIC, 0.001 for OTHER)` (MAR23.8(2)). Empty list gives 0.

## Worked example (drc_k-0007, written out)

Obligor Z, rated BB (RW 15%), corporate bucket. A long stock worth 50 (cash equity, maturity two years) and a short senior bond, notional -40, market value -40, two years.
- Stock: LGD 1, notional = market value = 50, PnL 0: JTD = max(50, 0) = 50; weight 1.
- Bond: LGD 0.75, PnL = -40 - (-40) = 0: JTD = min(0.75 x (-40) + 0, 0) = -30; weight 1.
- Offset: the short is senior (rank 3), the long is equity (rank 1). A short may only offset a long of the same or higher seniority, so nothing offsets: net long 50, net short -30.
- HBR = 50 / (50 + 30) = 0.625.
- DRC = max(0.15 x 50 - 0.625 x 0.15 x 30, 0) = max(7.5 - 2.8125, 0) = 4.6875.

Turn the positions round (drc_k-0008: long senior bond 40, short stock 50): the stock short is junior to the bond, so it may offset: 30 - 50 = -20 net short, HBR = 0, DRC = 0. The asymmetry is the point of MAR22.19(1): being short the equity is a better hedge of a bond than being short a bond is of the equity.

Table 1 mapping (drc_k-0010): a sold put on a bond with notional 100, strike amount 95 and option value -3 has bond-equivalent market value 95 - |-3| = 92 and P&L 92 - 100 = -8. Senior: JTD = 0.75 x 100 - 8 = 67, a long credit exposure even though the bank sold an option (MAR22.10(2)).

## Errors (order KR-67 = HR-122)

`E_SCHEMA`: missing field, unlisted enum (`bucket`, `seniority`, `kind`, rating string), wrong JSON type. `E_LIMIT`: more than 100,000 positions. Finite rule: non-finite number is `E_DOMAIN`. Structural `E_INPUT`: obligor without a rating entry; duplicate `id`; both or neither of `positions` and `bucket_drc` in `drc_ctp`. `E_DOMAIN`: `maturity_years <= 0`; cash equity maturity not 0.25 and below 1; `notional = 0` with nonzero market value in `drc_nonsec` (long or short is undefined); `gross_notional < 0`; `rw < 0` or `rw > 12.5`.

## Golden cases (designed; values computed by hand on 2026-11-19 and not yet frozen in a file)

Common: amounts in currency units; all maturities in years. Outside-check column: P printed in a read source; T printed-table lookup (not counted, KR-68); B blind re-derivation (DR-H2) if a blind lane is run; none.

| Case | Input | Expected | Arithmetic | Outside check |
|---|---|---|---|---|
| drc_k-0001 | X BBB, long SENIOR notional 100, mv 100, m 5 | jtd 75; hbr 1; drc 4.5 | 0.75 x 100; 0.06 x 75 | B |
| drc_k-0002 | as 0001 with m 0.5 | scaled 37.5; drc 2.25 | 75 x 0.5; 0.06 x 37.5 | B (weight one-half is printed in MAR22.15; the drc is not) |
| drc_k-0003 | obligor IDX: short equity future mv -10,000,000, m 1/12 (derivative); long cash equity mv 10,000,000, m 0.25 | scaled -2,500,000 and 2,500,000; net 0; drc 0 | MAR22.16 FAQ: "1/4*10 - 1/4*10 = 0" | **P** (MAR22.16 FAQ, p. 625) |
| drc_k-0004 | X BBB: long SENIOR 100/100 m 5; short SENIOR -100/-100 m 0.25 | net long 56.25; drc 3.375 | 75 - 0.25 x 75; 0.06 x 56.25 | B (one quarter is printed in MAR22.19(3)(b); the drc is not) |
| drc_k-0005 | X A long SENIOR 100, mv 80, m 5; Y BB short SENIOR -100, mv -80, m 5 | jtd 55 and -55; hbr 0.5; drc 0 | 75 - 20; -75 + 20; max(1.65 - 0.5 x 8.25, 0) | B |
| drc_k-0006 | as 0005 with Y AAA | drc 1.5125 | 1.65 - 0.5 x 0.005 x 55 | B |
| drc_k-0007 | worked example above | net long 50, net short -30; hbr 0.625; drc 4.6875 | above | B |
| drc_k-0008 | Z BB: long SENIOR 40/40 m 2; short cash equity -50 m 2 | net short -20; hbr 0; drc 0 | 30 - 50 | B |
| drc_k-0009 | X A long SENIOR 100/100 m 5 (CORPORATE); S AA long SENIOR 200/200 m 5 (SOVEREIGN) | drc 2.25 + 3 = 5.25 | 0.03 x 75; 0.02 x 150 | B |
| drc_k-0010 | X BBB sold put: notional 100, mv 92 (bond-equivalent), m 5 | jtd 67; drc 4.02 | 0.75 x 100 + (92 - 100); 0.06 x 67 | B |
| drc_k-0011 | U UNRATED long SENIOR 100/100 m 5; D DEFAULTED long cash equity 5, m 2 | drc 11.25 + 5 = 16.25 | 0.15 x 75; 1 x 5 | B |
| ctp_k-0001 | bucket_drc [100, -100] | 50 | 100 + 0.5 x (-100) | **P** (MAR22.45, p. 633, image "100 - 0.5 x 100 = 50") |
| ctp_k-0002 | index A long mv 1000 rw 0.1 m 5; index B short mv -1000 rw 0.1 m 5 | hbr_ctp 0.5; DRC_A 100, DRC_B -50; total 75 | 0.1 x 1000; -0.5 x 100; max(100 - 25, 0) | B |
| ctp_k-0003 | bucket_drc [-10] | 0 | max(0.5 x (-10), 0) | B |
| sec_k-0001 | bucket RMBS-EU: pool P1 tranche T1 long mv 50 rw 0.2; pool P1 tranche T2 short mv -20 rw 0.2; m 5 | no offset; hbr 0.714285714285714; drc 7.142857142857142 | 50/70; 10 - (50/70) x 4 | B |
| rrao_k-0001 | EXOTIC 1,000,000; OTHER 2,000,000 | 12,000 | 10,000 + 2,000 | B |
| rrao_k-0002 | OTHER listed 5,000,000; EXOTIC listed 1,000,000; EXOTIC back-to-back 3,000,000 | 10,000 | only the listed exotic counts (MAR23.7) | B |
| rrao_k-0003 | empty list | 0 | | B |

Error goldens (not value cases): drc_ke-0001 missing `notional` (`E_SCHEMA`); drc_ke-0002 seniority `JUNIOR` (`E_SCHEMA`); drc_ke-0003 obligor without rating (`E_INPUT`); drc_ke-0004 `maturity_years` 0 (`E_DOMAIN`); drc_ke-0005 cash equity m 0.5 (`E_DOMAIN`); drc_ke-0006 missing `notional` and `maturity_years` 0 in the same request (`E_SCHEMA`, two errors at once); rrao_ke-0001 `gross_notional` -1 (`E_DOMAIN`).

Value cases 18; printed (P) 2; library (L) 0. Strict outside share 2/18 = 11% without a blind lane.

## Acceptance (fixed before any run; proposed here, frozen when the coordinator confirms this spec)

- A1 Every value golden above reproduced in all four builds to 1e-12 relative (1e-15 absolute at 0).
- A2 Error goldens give the stated code in all four builds.
- A3 Property (10,000 random portfolios): DRC is 0 or positive; a long added to an obligor with no net short, with risk weight at least that of every obligor with a net short in the bucket, never lowers DRC_b (KR-327: a long added without that premise can lower DRC_b, for example by offsetting the same obligor's short); permuting the input order leaves every output unchanged (KR-53 greedy is order-independent in its totals); scaling every notional and market value by c > 0 scales DRC by c.
- A4 Gate (plan section 15): at least 60% of the 18 value cases outside-checked under KR-68. Without a DR-H2 blind lane the share is 11% and K-8a moves to a point release (`program/STAGE_K_W2_GATE.md`). Measured 2026-11-20 after the DR-H2 blind lane (`program/STAGE_K_BLIND_W2.md`): 15 of 18 value cases of `drc_k` (83.3%), so the 60% gate is met (`oracle/OUTSIDE_SHARES.md`, generated by `tools/outside_shares.py`; evidence class measured).

## Limits

- Securitisation risk weights (CRE40-CRE44) are not implemented; the caller supplies them (KR-55). Decomposition and replication offsets for securitisations and CTP (MAR22.28, MAR22.30, MAR22.39(2)-(3)) need a valuation model and are the caller's.
- Look-through of index and multi-name products to constituents (MAR22.5 and its FAQ) is the caller's: the operation takes single-obligor positions.
- National discretion of a zero sovereign risk weight (MAR22.7), guarantee substitution (MAR22.19(2), CRE22) and fund mandates (MAR22.8, MAR23.6(5)) are not modelled.
- Ratings are the caller's mapping of external ratings (MAR22.24 FAQ: two or three ratings rule not applied).
- RRAO classification (is this instrument exotic, does it bear other residual risk) is the caller's; the operation applies weights and exclusions only.
