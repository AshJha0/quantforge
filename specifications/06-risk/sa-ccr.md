# SA-CCR: exposure at default for a derivatives netting set

Spec version 0.1.0 (stage K round 1, wave 1b, plan item K-8d; written 2026-11-19). Status: implemented in all four builds (Python `python/quantforge_core/saccr.py`; ports per `program/STAGE_K_W1B_PORTS_HANDOVER.md`), registered at integration on `k-r1` 2026-11-19. Rulings KR-30 to KR-39 (`specifications/stage-k-rulings-w1b.md`). Operation `risk.saccr.ead`. In `cli-contract.md` under stage K wave 1b (contract 1.17.0).

**Plain idea.** If a counterparty defaults today, a bank loses what its derivatives with that counterparty are worth now, less the collateral it holds (the replacement cost), plus whatever they could grow to be worth before it can replace them (the potential future exposure). SA-CCR is the regulator's fixed recipe for both: no model, only the trades' sizes, maturities, directions and option deltas, a table of supervisory factors, and simple netting rules that let opposite trades offset fully, partly or not at all. The answer, exposure at default (EAD), is 1.4 times the sum.

## Sources

- [CRE52] Basel Committee on Banking Supervision, *The Basel Framework*, chapter CRE52 "Standardised approach to counterparty credit risk", version effective 1 January 2023, in the consolidated PDF generated 11/11/2026 (1,429 pages, `institutional-quant-engine-plan/basel-framework-full.pdf`, 8.2 MB; chapters SCO to BCP; text extracted with pypdf, formula images rendered with PyMuPDF and read by eye), pages 434 to 462. Regulator text, **read** 2026-11-19. Verified on the page: EAD = alpha x (RC + PFE), alpha 1.4 (52.1, p.435); margined EAD capped at the unmargined EAD (52.2, p.435); RC unmargined max(V - C; 0) (52.10, p.437-438); RC margined max(V - C; TH + MTA - NICA; 0) (52.18, p.440); multiplier min{1; Floor + (1 - Floor) exp((V - C) / (2 (1 - Floor) AddOn))}, Floor 5% (52.23, p.441, formula image read); AddOn = sum over asset classes (52.25); SD = (exp(-0.05 S) - exp(-0.05 E)) / 0.05 floored at 10 business days (52.34, p.445, image read); delta table for options (52.40, p.447, image read) and CDO tranches 15 / ((1 + 14 A)(1 + 14 D)) (52.41, p.448, image read); nth-to-default A = (n - 1)/m, D = n/m (footnote 230); hedging sets (52.45 to 52.47); MF unmargined sqrt(min(M; 1 year) / 1 year), M floored at 10 business days (52.48, 52.49, p.450-451, image read); MPOR floors (52.50, 52.51); MF margined 3/2 sqrt(MPOR / 1 year) (52.52, p.452; the 3/2 also in the 52.2 FAQ text); IR steps and the offset formula with 1.4, 1.4, 0.6 (52.57; formula image read on CRE99 p.528); FX steps (52.59); credit and equity single-factor aggregation (52.61, 52.66); commodity steps (52.70); Table 2 parameters (52.72, p.459-460, text); basis x 1/2, volatility x 5 (52.73).
- [CRE99] same PDF, chapter CRE99 "Application guidance", paragraphs 99.20 to 99.97, pages 524 to 540. Regulator text, **read** 2026-11-19 (text and every printed formula image on pages 528, 532, 536, 537, 538, 539, 540 read by eye). These are the five sample portfolios of BCBS 279 Annex 4a. CRE99.20 (p.524): "intermediate values are not rounded ... for ease of presentation, these intermediate values as well as the final EAD are rounded" (paraphrase of the paragraph).
- [BCBS279] Basel Committee, *The standardised approach for measuring counterparty credit risk exposures*, March 2014 (rev. April 2014), Annex 4a, PDF pages 26 to 34; **read** 2026-11-15 in a browser by an earlier lane (not on disk; recorded in `institutional-quant-engine-plan/STAGE_K_SOURCES.md`, section "SA-CCR worked examples"): the five printed EADs 569, 381, 5,406, 936, 1,879 and the intermediates listed there. BCBS 279 itself is not on disk; the same figures were read again in [CRE99].

## Formal statement

Netting set of trades i with notional N_i (domestic currency), market value v_i, maturity M_i (years), and for IR and credit start S_i and end E_i (years from today). V = sum v_i; C = haircut value of net collateral held (caller's figure, signed).

1. Adjusted notional d_i: IR and credit N_i x SD_i with SD_i = max((e^{-0.05 S_i} - e^{-0.05 E_i}) / 0.05, 10/250); FX, equity, commodity N_i (the caller supplies the converted foreign leg, or price x units, KR-38).
2. Maturity factor: unmargined MF_i = sqrt(min(max(M_i, 10/250), 1)); margined MF = 1.5 sqrt(MPOR / 250) for every trade, MPOR in business days (KR-35).
3. Delta: linear +1 long, -1 short. Options with supervisory volatility sigma (Table 2), d1 = (ln((P + lambda)/(K + lambda)) + sigma^2 T / 2) / (sigma sqrt T): bought call Phi(d1), sold call -Phi(d1), bought put -Phi(-d1), sold put Phi(-d1); lambda is the optional shift (CRE52.40 FAQ2, KR-38). CDO tranche: +-15 / ((1 + 14 A)(1 + 14 D)), plus when protection is bought.
4. Effective notional D_i = d_i x MF_i x delta_i.
5. Supervisory factor SF_i from Table 2 by asset class and subclass, x 0.5 for basis hedging sets, x 5 for volatility hedging sets.
6. Hedging sets and add-ons:
   - IR, per currency: buckets by E (E < 1, 1 <= E <= 5, E > 5; KR-32), D_Bk = sum of D in bucket k; EN = sqrt(D_B1^2 + D_B2^2 + D_B3^2 + 1.4 D_B1 D_B2 + 1.4 D_B2 D_B3 + 0.6 D_B1 D_B3) (or |D_B1| + |D_B2| + |D_B3| when `ir_offset` is false); AddOn = SF x EN.
   - FX, per currency pair: AddOn = SF x |sum D|.
   - Credit and equity (one hedging set each): per entity a_e = SF_e x sum D; AddOn = sqrt((sum rho_e a_e)^2 + sum (1 - rho_e^2) a_e^2).
   - Commodity, four hedging sets (energy, metals, agricultural, other; KR-33): per commodity type a_t = SF_t x sum D; per hedging set the same single-factor formula with rho = 0.4; AddOn = sum over hedging sets.
   - Basis and volatility transactions: own hedging sets named by the caller's `hedging_set`, same aggregation as their class (KR-34).
7. AddOn_aggregate = sum over the five classes; multiplier m = 1 if V - C >= 0, else min{1; 0.05 + 0.95 exp((V - C) / (2 x 0.95 x AddOn))} (0.05 when AddOn = 0, KR-36); PFE = m x AddOn.
8. RC = max(V - C, 0) unmargined; max(V - C, TH + MTA - NICA, 0) margined. EAD = 1.4 (RC + PFE). Margined: EAD = min(EAD_margined, EAD_unmargined) with the unmargined figure computed from the same trades, V and C (KR-37).

## Worked example (CRE99 Example 1, PDF pages 524 to 528)

Trades (USD thousands): 10y payer-of-fixed swap 10,000, MV 30; 4y receiver-of-fixed swap 10,000, MV -20; bought 1y-into-10y EUR swaption 5,000, MV 50, forward 6%, strike 5%. SD = 7.8694, 3.6254, 7.4856, so d = 78,694, 36,254, 37,428; the swaption is short the floating rate, a bought put: delta = -Phi(-(ln(1.2) + 0.125)/0.5) = -0.2694; MF = 1 (all beyond one year); D = 78,694, -36,254, -10,083. USD: D_B2 = -36,254, D_B3 = 78,694, EN = 59,270, add-on 296.35; EUR: EN = 10,083, add-on 50.415. AddOn = 346.76; V = 60 >= 0 so multiplier 1, RC 60; EAD = 1.4 x 406.76 = 569.47, printed 569. The paper's "1.4 x (60 + 347) = 569" carries 569.47 and prints the rounded inputs; truncation is not involved (1.4 x 407 = 569.8 would print 570).

## Operation `risk.saccr.ead`

Inputs:

| Key | Type | Meaning |
|---|---|---|
| `trades` | array of objects, 1 to 100,000 | the netting set |
| `trades[].id` | string, unique | trade identifier |
| `trades[].asset_class` | `IR` `FX` `CREDIT` `EQUITY` `COMMODITY` | primary risk driver (CRE52.26) |
| `trades[].notional` | Real > 0 | domestic currency; IR and credit before SD; FX the converted foreign leg; equity and commodity price x units |
| `trades[].market_value` | Real | contributes to V |
| `trades[].maturity` | Real > 0, years | M |
| `trades[].position` | `LONG` `SHORT` for `LINEAR`; `BOUGHT` `SOLD` for `OPTION` and `CDO` (bought = protection bought) | direction |
| `trades[].kind` | `LINEAR` (default) `OPTION` `CDO` | |
| `trades[].treatment` | `NORMAL` (default) `BASIS` `VOLATILITY` | CRE52.46, CRE52.47 |
| `trades[].start`, `end` | Real, 0 <= start <= end; required for IR and CREDIT | S, E |
| `trades[].hedging_set` | string; required for IR (currency), FX (pair), and every BASIS or VOLATILITY trade (label) | |
| `trades[].entity` | string; required for CREDIT, EQUITY, COMMODITY | reference entity, index or commodity type |
| `trades[].subclass` | credit `AAA` `AA` `A` `BBB` `BB` `B` `CCC` `IG` `SG`; equity `SINGLE` `INDEX`; commodity `ELECTRICITY` `OIL_GAS` `METALS` `AGRICULTURAL` `OTHER`; required for those classes, absent for IR and FX | Table 2 row |
| `trades[].option_type`, `underlying_price`, `strike`, `exercise` | `CALL` `PUT`, Real, Real, Real > 0 years; required for OPTION | P, K, T |
| `trades[].shift` | Real, default 0 | lambda of CRE52.40 FAQ2 |
| `trades[].attachment`, `detachment` | Real, 0 <= A < D <= 1; required for CDO | |
| `collateral` | Real, default 0 | C |
| `margin` | object, optional (absent = unmargined) | `threshold` >= 0, `mta` >= 0, `nica` (Real), `remargin_days` (Integer >= 1), `mpor_days` (Integer >= 1, optional estimate), `illiquid` (bool, default false), `disputes` (bool, default false) |
| `ir_offset` | bool, default true | offset or no-offset IR formula |

Outputs: `ead`, `rc`, `pfe`, `multiplier`, `addon_aggregate`, `addon` (object with all five classes), `v`, `c`, `margined` (bool), `mpor_days` (Integer or null), `ead_unmargined` (Real or null), `capped` (bool), `hedging_sets` (array of `asset_class`, `treatment`, `key`, `addon`, sorted by class in the order IR, FX, CREDIT, EQUITY, COMMODITY, then NORMAL, BASIS, VOLATILITY, then key; credit and equity NORMAL key is ""), `trades` (input order: `id`, `supervisory_duration` (null outside IR and credit), `adjusted_notional`, `maturity_factor`, `delta`, `effective_notional`, `supervisory_factor`, the margined figures when margined). Reals are binary64; tolerance class `simple_analytic`.

## Errors

Order (HR-122): `E_SCHEMA` (missing or mistyped key, value not in an enum list), `E_LIMIT` (an array above 100,000), the finite rule (`E_DOMAIN`), structural `E_INPUT`, then `E_DOMAIN`.
- `E_INPUT`: no trades; duplicate `id`; a field required by the trade's class, kind or treatment is missing; a subclass of another class, or a subclass on IR or FX; a position that does not fit the kind; a CDO outside CREDIT; one entity with two subclasses in one hedging set.
- `E_DOMAIN`: notional <= 0; maturity <= 0; not 0 <= start <= end; shifted price or strike <= 0; exercise <= 0; not 0 <= attachment < detachment <= 1; threshold or MTA < 0; `remargin_days` or `mpor_days` < 1.

## Goldens (`datasets/golden/stage_k/saccr_k.json`, generator `oracle/python/gen_stage_k_w1b.py`)

| Cases | Content | Check |
|---|---|---|
| saccr_k-0001 to 0005 | CRE99 Examples 1 to 5 | OUTSIDE (published): printed EAD 569, 381, 5,406, 936, 1,879 ([CRE99] p.528, 532, 536, 537, 540; [BCBS279] pp.26-34); the printed intermediates are asserted by the generator |
| saccr_k-0006 | Example 1, no-offset IR formula | hand |
| saccr_k-0007 to 0016 | FX pairs with a sold call; equity netting and an index put; CDO and second-to-default; electricity, gas, agriculture and a basis set; volatility and IR basis sets; shifted IR option, three buckets; daily margin illiquid and disputed (MPOR 40); own MPOR estimate 15; capped margined EAD; exactly offsetting FX (multiplier 0.05) | hand, mpmath oracle |
| saccr_k-0017 to 0037 | 21 error cases, four with two errors at once | hand |
| saccr_k-0038, 0039 | E1 goldens (ruling F-2): a NaN notional; a -Infinity market value with no currency pair (two errors, the finite rule first), both `E_DOMAIN`; added at integration 2026-11-19 | hand |

## Acceptance (fixed before the goldens were generated)

- Rule KR-30: every figure is computed at full precision and compared with the printed figure after rounding half away from zero to the printed number of digits (CRE99.20). The five EADs and the printed intermediates of CRE99.29, 99.31, 99.32, 99.37 to 99.40, 99.47, 99.52, 99.54 to 99.58, 99.66, 99.68 to 99.79, 99.82 to 99.97 reproduce under this rule, with one recorded exception: CRE99.90 prints -7,100 for the Brent forward, which is twice the rounded 3,550, while full precision gives -7,099.30 (KR-31). That figure is accepted within 1 unit as a source rounding; it was found by the first test run, after the nearest-integer rule had been taken from CRE99.20, and is stated here rather than hidden.
- All 37 cases pass in the Python build (local registration, 2026-11-19). Properties tested (`python/tests/test_stage_k_w1b.py`, Hypothesis, 150 examples): multiplier in [0.05, 1] (in (0.05, 1] in exact arithmetic; exp underflow reaches 0.05); aggregate add-on never above the sum of the trades' stand-alone add-ons; EAD non-decreasing when every notional is scaled up; EAD non-increasing in collateral.
- Outside share: 12 of 16 value cases (75%, floor 60%). Five have a published check (CRE99 Examples 1 to 5); seven (saccr_k-0007 to 0012 and 0014) were re-derived blind by a second model and matched (DR-H2, `program/STAGE_K_BLIND_W1B.md`, evidence class measured). The other four hand cases (0006, 0013, 0015, 0016) also matched but are excluded, because the blind lane had read output facts for them in the unstripped spec once (a recorded process failure). The first figure written here, 5 of 16 (31%), counted the published checks only, before the blind lane ran. There is no free independent SA-CCR library in the oracle environment; ORE has an SA-CCR implementation (not attempted).

## Convergence and limit cases

SA-CCR is a closed-form formula: no iteration, grid or solver. The page names "Brent" only as the crude oil underlying of CRE99 Example 3, not Brent's root-finding method. The table records the limit cases the goldens pin instead of a convergence order.

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Closed form (CRE52 steps 1 to 8) | none: exact formula in binary64 | none | V - C >= 0: multiplier exactly 1 before any exponential (KR-36, saccr_k-0001); add-on 0 with V - C < 0: multiplier at its floor 0.05 (saccr_k-0016) | KR-36 |
| Margined cap (CRE52.2) | none | none | margined EAD above the unmargined EAD of the same trades and C is capped at the unmargined figure (saccr_k-0015) | KR-37 |

## Limits and scope

- **Open audit findings (2026-11-19): KA-A3, KA-C18.** Volatility hedging sets follow the caller's label where CRE52.45 to 52.47 fix their construction: two offsetting equity variance swaps give 320 here against 195.96 under the Basel text. The outside-check share of this item is under review (12 of 16 as counted, 7 of 16 by the strict reading). Register: `docs/known-issues.md`.

- Not covered (KR-39): CRE52.74 multiple margin agreements within one netting set; CRE52.75 and 52.76 one margin agreement over several netting sets; collateral haircuts (C is the caller's haircut value); central counterparty MPOR floors (CRE54); variable-notional averaging (CRE52.37) and digital-option collars (CRE52.42(3)), which the caller applies before the call; the sold-option and sold-protection EAD caps in the CRE52.1 FAQs.
- The supervisory parameters are in `specifications/06-risk/sa-ccr-parameters.json`, shared by the four builds; a test checks the Python literals against it.
- E_LIMIT: the generic array cap of 100,000 (`MAX_ARRAY`) bounds `trades`; the CRE52.51(1) "more than 5000 transactions" floor is reachable below it.
