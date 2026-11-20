# Leverage ratio and large exposures (simplified)

Spec version 0.1.0. Status: **PROPOSED** (stage K wave 2, item K-8i; spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-w2.md` KR-50 to KR-53, KR-65 to KR-69. Parameters `specifications/tables/stage_k/lev_leverage.json` and `lex_large_exposures.json`. Gate status: `program/STAGE_K_W2_GATE.md`.

Every output carries `label`: "simplified leverage ratio (LEV30 subset); not a regulatory return" or "simplified large exposures (LEX subset); not a regulatory return" (KR-65, KR-66).

**Plain idea.** Two backstops sit beside the risk-weighted capital rules. The leverage ratio ignores risk weights altogether: Tier 1 capital divided by a gross measure of everything the bank has on and off its balance sheet must stay at or above 3%, so a bank cannot hold very little capital simply because its models call its assets safe. The large exposures rule caps what a bank can lose if one counterparty, or one group of connected counterparties, fails: the total exposure must stay at or below 25% of Tier 1. Both are simple ratios; the work is in measuring the denominator and the exposures consistently.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [LEV] | Basel Framework LEV20, LEV30 (effective 1 January 2023), LEV40, consolidated PDF of 11/11/2026, pp. 787-813 | read 2026-11-19 (formulas from images pp. 788, 795, 805) | ratio, minimum, exposure measure, CCFs |
| [LEX] | LEX10, LEX20 (effective 15 December 2019), LEX30 (1 January 2023), pp. 937-956 | read 2026-11-19 | thresholds, limit, exposure values, trading book, CRM |
| [MAR22] | MAR22.9-22.14, pp. 621-624 | read 2026-11-19 | gross JTD reused by LEX30.17 |
| [CRE99] | SA-CCR Examples 1, 3, 4 (CRE99.40, 99.76, 99.79), pp. 528, 536-537 | read 2026-11-19 (images) | published values for the derivative exposure (see below) |

Why the CRE99 numbers are a fair outside check here: for an unmargined netting set without collateral whose value is not negative, the SA-CCR multiplier is 1 (CRE99.79: "Because V-C is positive, the multiplier is equal to 1"), and the leverage ratio fixes the multiplier at 1 and uses RC = max(V, 0) (LEV30.16). The two formulas then coincide, so the printed EAD is the leverage exposure of that netting set. It does not hold for Example 2 (multiplier 0.965) or Example 5 (margined, collateral), which are therefore not used.

## Formal statement

### `risk.capital.leverage`

Inputs (KR-65): `tier1`; `on_balance` (list of non-negative values); `derivatives` [{v, cvm_received >= 0, cvm_provided >= 0, pfe >= 0}]; `written_credit_derivatives` [{notional >= 0, fair_value, purchased_offset >= 0}]; `sfts` [{gross_assets >= 0, mna, exposures [E_i >= 0], collateral [C_i >= 0]}]; `off_balance` [{notional >= 0, ccf_category}].

- Derivatives (LEV30.14-30.16): `RC = max(v - cvm_received + cvm_provided, 0)`, exposure `1.4 (RC + pfe)` per netting set.
- Written credit derivatives (LEV30.31, footnote 384): effective notional `max(notional - max(0, -fair_value) - purchased_offset, 0)`.
- SFTs (LEV30.37): `gross_assets` plus, with `mna`, `max(0, sum E_i - sum C_i)`, without, `sum_i max(0, E_i - C_i)`.
- Off-balance sheet (LEV30.47-30.54): `notional x CCF`, CCF 1 (`DIRECT_CREDIT_SUBSTITUTE`, `FORWARD_PURCHASE`, `OTHER_CREDIT_SUBSTITUTE`), 0.5 (`NIF_RUF`, `TRANSACTION_CONTINGENT`), 0.4 (`COMMITMENT`), 0.2 (`TRADE_LC`), 0.1 (`UNCONDITIONALLY_CANCELLABLE`).
- Exposure measure = sum of the four parts (LEV20.5); ratio = `tier1 / exposure` (LEV20.3); `meets_minimum` = ratio >= 0.03 (LEV20.7), compared exactly as `tier1 >= 0.03 x exposure` in binary64 with the golden avoiding values within 1e-12 of the boundary.

Outputs: each part, `exposure`, `ratio`, `meets_minimum`, `label`.

### `risk.capital.large_exposures`

Inputs (KR-66): `tier1 > 0`; `bank_gsib` (optional Boolean, default false: whether the reporting bank is itself a G-SIB, KR-324; the text requires the fact, the field name and the default are ours, evidence class inferred, KR-319); `counterparties` [{id, group?, gsib?, exempt?}]; `banking_book` [{counterparty, value >= 0}]; `off_balance` [{counterparty, notional >= 0, ccf}] (the caller's standardised CCF, floored at 0.10 by the operation, LEX30.6); `crm` [{counterparty, provider, protected >= 0}] (LEX30.13-30.14); `trading_book` positions as KR-51 with a `counterparty` field.

- Trading book (LEX30.17-30.19, 30.22-30.23, 30.30): gross JTD of MAR22.11 with LGD 1 and no maturity weight; offsets per counterparty by the KR-53 rule; a net short counts 0.
- Exposure per counterparty = banking book + converted off-balance sheet + trading book net long - protected amounts + amounts received as provider (LEX30.14, LEX30.15).
- Exposure per group = sum over members (LEX10.9); a counterparty without a group is its own group.
- `large` = exposure >= 0.10 tier1 (LEX10.8); `limit` = 0.15 tier1 if `bank_gsib` is true and at least one member of the group is flagged `gsib` (LEX20.1; KR-324 "any member", an inferred reading), else 0.25 tier1; `breach` = exposure > limit; exempt counterparties are reported, never breach.
- Report list: every group with `large` true, plus the 20 largest (LEX20.4(1), (4)).

Outputs: per group `exposure`, `share` (exposure / tier1), `large`, `limit`, `breach`; `report`; `label`.

## Worked examples (written out)

**Written credit derivative (lev_k-0004, lev_k-0005), from LEV30.31 footnote 384.** Protection sold, notional 100. Its fair value was +20 and is now -10, and the loss has gone through Tier 1. The effective notional may be reduced by the negative fair value now recorded, 10, giving 90; not by the 30 change from +20. If the fair value is instead +5, there is no negative fair value and the effective notional stays 100.

**Leverage ratio (lev_k-0010).** Tier 1 60. On balance sheet 500. One derivative netting set as CRE99 Example 1 (V = 60, PFE add-on 347): 1.4 x (60 + 347) = 569.8. SFTs: gross assets 150 with an MNA, lent 100 + 50, received 80 + 90, so the counterparty add-on is max(0, 150 - 170) = 0. Off balance sheet: commitment 1,000 x 40% = 400, unconditionally cancellable 500 x 10% = 50, NIF 200 x 50% = 100, total 550. Exposure 500 + 569.8 + 150 + 550 = 1,769.8. Ratio 60 / 1,769.8 = 3.39%, above 3%. With Tier 1 of 30 (lev_k-0011) the ratio is 1.70% and fails.

**Trading book large exposure (lex_k-0004).** Tier 1 1,000. Issuer G: long senior bond, face 100, market value 90; short G stock, market value -30; banking book loan 200. LEX30.17 uses LGD 100%: bond JTD = 100 + (90 - 100) = 90; stock JTD = -30. The stock is junior to the bond, so the short may offset (LEX30.23): 60. Total 200 + 60 = 260, 26% of Tier 1: large and in breach of 25%. Under MAR22 the same bond would have had LGD 75% and JTD 65; the large exposures rule deliberately assumes nothing is recovered.

## Errors (order KR-67 = HR-122)

`E_SCHEMA`: missing field, wrong type, unlisted `ccf_category`. `E_LIMIT`: more than 100,000 items in any list. Finite rule: `E_DOMAIN`. Structural `E_INPUT`: `exposures` and `collateral` of different lengths; a reference to an unknown counterparty; a counterparty in two groups. `E_DOMAIN`: negative amounts where marked `>= 0`; `tier1 <= 0`; `ccf` outside [0, 1].

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Input | Expected | Arithmetic / tolerance | Outside check |
|---|---|---|---|---|
| lev_k-0001 | derivative v 60, pfe 347 | 569.8 | 1.4 x 407; printed EAD 569 (CRE99.40): agreement within 1.0, fixed now, because the printed figures are rounded from unrounded add-ons | **P** |
| lev_k-0002 | v 20, pfe 3841 | 5405.4 | printed 5,406 (CRE99.76), within 1.0 | **P** |
| lev_k-0003 | v 40, pfe 629 | 936.6 | printed 936 (CRE99.79), within 1.0 | **P** |
| lev_k-0004 | written CD notional 100, fair_value -10 | effective notional 90 | footnote 384: "reduced by 10", "cannot be reduced by 30" | **P** (LEV30.31 fn 384, p. 801) |
| lev_k-0005 | written CD notional 100, fair_value 5 | 100 | footnote 384: "cannot be reduced at all" | **P** |
| lev_k-0006 | off balance: COMMITMENT 1000, UNCONDITIONALLY_CANCELLABLE 500, NIF_RUF 200 | 550 | 400 + 50 + 100 | B |
| lev_k-0007 | SFT gross 150, mna, E (100, 50), C (80, 90) | 150 | 150 + max(0, -20) | B |
| lev_k-0008 | as 0007 without mna | 170 | 150 + 20 + 0 | B |
| lev_k-0009 | derivative v 100, cvm_received 30, pfe 50 | 168 | 1.4 x (70 + 50) | B |
| lev_k-0010 | worked example, tier1 60 | exposure 1769.8; ratio 0.033902135834557576; meets true | above | B |
| lev_k-0011 | as 0010, tier1 30 | ratio 0.016951067917278788; meets false | | B |
| lex_k-0001 | tier1 1000; A 260, B 100, C 250, D 99.99 | A large breach; B large, no breach (10% is "equal to or above"); C large, no breach (25% is "not higher than"); D not large | | B |
| lex_k-0002 | group G: A1 150, A2 120 | G 270, breach | | B |
| lex_k-0003 | E 300 guaranteed 100 by F; F 200 | E 200 (large), F 300 (breach) | substitution LEX30.13-30.14 | B |
| lex_k-0004 | worked example | 260; breach | above | B |
| lex_k-0005 | H: long bond 50/50; short same issue -80/-80 | 0 (net short) | LEX30.22, 30.30 | B |
| lex_k-0006 | off balance notional 1000, ccf 0 | 100 | floor 10% (LEX30.6) | B |
| lex_k-0007 | bank and counterparty G-SIB; exposure 160, tier1 1000 | limit 150; breach | LEX20.1 | B |
| lex_k-0010 | `bank_gsib`; group GM of M1 (`gsib`) and M2 (not), 100 each; group GN of N1 and N2 (neither `gsib`), 100 each; tier1 1000 | GM limit 150, breach (200 > 150); GN limit 250, no breach | KR-324 "any member": under "every member" GM would take 250 and not breach. Added 2026-11-20 when KR-324 was confirmed; hand case, not counted as outside-checked (KR-68) | none |

Error goldens: lev_ke-0001 `tier1` 0 (`E_DOMAIN`); lev_ke-0002 `exposures` and `collateral` lengths 2 and 1 (`E_INPUT`); lev_ke-0003 unlisted CCF category and a negative notional at once (`E_SCHEMA`); lex_ke-0001 counterparty in two groups (`E_INPUT`); lex_ke-0002 `ccf` 1.5 (`E_DOMAIN`).

Value cases 18; printed (P) 5; library (L) 0. Strict share 5/18 = 28%.

## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 All value goldens in all four builds to 1e-12 relative, except lev_k-0001 to 0003 which must also lie within 1.0 of the printed CRE99 EADs (tolerance fixed here, before any run).
- A2 Properties (10,000 random cases): exposure measure is monotone in every non-negative input; non-cash collateral has no input and so cannot lower the exposure (LEV30.22); a group's exposure equals the sum of its members'; moving protection from counterparty to provider leaves the total over all counterparties unchanged.
- A3 Gate (plan 15): 60% of the 18 value cases outside-checked under KR-68. Strict share 28%; K-8i moves to a point release unless a DR-H2 blind lane re-derives at least 6 B cases (5 + 6 = 11 of 18 = 61%) (`program/STAGE_K_W2_GATE.md`).

## Limits (what is left out, exactly)

Leverage ratio (KR-65): Tier 1 and its deductions (LEV30.3) are inputs; PFE is an input or comes from the SA-CCR operation (K-8d) with the multiplier forced to 1; CCP client clearing (LEV30.26-30.29); cash pooling (LEV30.12); trade-date accounting offsets (LEV30.10-30.11); securitisation derecognition (LEV30.5); central bank reserves exemption (LEV30.7); agent SFTs (LEV30.41-30.44); eligibility tests for purchased protection (LEV30.31(1)-(5), 30.32-30.34: the caller asserts `purchased_offset`); exclusion of written CD PFE (LEV30.35); provisions against off-balance sheet items (LEV30.48); the G-SIB leverage buffer (LEV40); quarter-end or averaging rules (LEV20.6).

Large exposures, the G-SIB rule for groups (KR-324, inferred): the Basel text (LEX20.1, LEX40.1, LEX40.3) gives a G-SIB a 15% limit for its exposure to another G-SIB but does not say what happens when a group of connected counterparties has some members that are G-SIBs and some that are not. We apply 15% to the whole group when any one member is flagged `gsib`, so that adding a non-G-SIB member to a group can never loosen the limit the G-SIB member would have on its own. This is our reading, not text; golden lex_k-0010 pins it.

Written credit derivatives (KR-320): the input is the signed `fair_value`, and the operation reduces the notional by `max(0, -fair_value)`. This assumes the full negative fair value has been incorporated in Tier 1 (LEV30.31); a partial incorporation is not modelled.

Large exposures (KR-66): connectedness (LEX10.9-10.18) is the caller's group map; exemptions are a flag (LEX30.31-30.59 not modelled: sovereigns, covered bonds, interbank, CCPs); look-through for funds and securitisations (LEX30.41-30.53); the LEX30.28 rule for CDS with a non-financial provider or reference; SFT haircuts (LEX30.5) and the standardised CCFs themselves (LEX30.6, only the 10% floor is applied); maturity mismatch of CRM (LEX30.10-30.11, the caller passes the recognised amount); reporting before and after CRM (LEX20.4(1)-(2)) is reduced to one list after CRM.
