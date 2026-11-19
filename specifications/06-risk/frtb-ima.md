# FRTB internal models approach: ES with liquidity horizons, NMRF and SES, RFET, PLA test, capital aggregation

Spec version 0.1.0. Status: **PROPOSED** (stage K wave 2, item K-8f; spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-w2.md` KR-50, KR-56 to KR-61, KR-67 to KR-69. Parameters `specifications/tables/stage_k/mar31_rfet.json`, `mar32_pla.json`, `mar33_ima.json`. The bank-wide backtesting traffic light is item K-8e (wave 1b) and is only used here through its multiplier table. Gate status: `program/STAGE_K_W2_GATE.md`.

Every output carries `label`: "regulatory formula on caller inputs; not a regulatory return" (KR-69).

**Plain idea.** A bank allowed to use its own model for market risk capital still has to follow a recipe around that model. It measures expected shortfall (ES) at 97.5% over 10 days, then stretches it for risk factors that take longer to exit (20 to 120 days), using only the factors that are still "stuck" at each longer horizon. It calibrates to the worst 12 months since 2007 through a smaller set of factors and scales up. Factors without enough real prices (they fail the risk factor eligibility test, RFET) leave the model and get a stress-scenario charge (SES) instead. Every desk must show, through the P&L attribution (PLA) test, that the risk model's P&L tracks the front office's: rank correlation above 0.80 and distributions close by Kolmogorov-Smirnov. The pieces are then added with fixed weights and a multiplier that grows with backtesting failures.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [MAR31] | Basel Framework MAR31, effective 1 January 2023, consolidated PDF of 11/11/2026, pp. 646-657 | read 2026-11-19 | RFET (MAR31.12-31.26), bucket table MAR31.16 |
| [MAR32] | MAR32, pp. 658-668 | read 2026-11-19 (Spearman formula from the image on p. 666) | PLA metrics and zones (MAR32.34-32.44), multiplier table (MAR32.9) |
| [MAR33] | MAR33, pp. 669-686 | read 2026-11-19 (formulas from images pp. 671, 672, 676, 678, 685, 686) | ES, LH, stress calibration, IMCC, SES, C_A, surcharge, ACR |
| [MAR99] | MAR99 Table 2, p. 758 | read 2026-11-15 and 2026-11-19 | multiplier table (same values as MAR32.9) |
| [SciPy] | SciPy 1.17.1 `stats.spearmanr`, `stats.ks_2samp`, `stats.kstwobign`, `stats.norm`, `integrate.quad` | measured 2026-11-19 in a scratch folder | independent library check (L) for PLA and normal ES |
| [AT02] | Acerbi and Tasche (2002), through `06-risk/var-es-and-backtests.md` | recalled, as recorded there | ES estimator on a P&L list |

## Formal statement

### `risk.frtb.pla` and `risk.frtb.pla.ks_pvalue`

Inputs: `hpl`, `rtpl` (equal length n, 3 <= n <= 1,000,000). Ranks with average ties (KR-56); `r_S` = Pearson correlation of the rank series (MAR32.36-32.38: `r_S = cov(R_HPL, R_RTPL) / (sigma_R_HPL sigma_R_RTPL)`). ECDFs with step 1/n (0.004 at n = 250; MAR32.39-32.40); `d` = largest absolute difference of the counts of `rtpl` and `hpl` values at or below any pooled value; `ks = d/n` (MAR32.41). Zone (MAR32.42, KR-56): green iff `r_S > 0.80` and `100 d < 9 n`; red iff `r_S < 0.70` or `100 d > 12 n`; amber otherwise. Outputs `spearman`, `ks`, `ks_count`, `zone`, `ks_pvalue_asymptotic = Q_KS(ks sqrt(n/2))` with `Q_KS(x) = 2 sum_{k>=1} (-1)^(k-1) exp(-2 k^2 x^2)`, `regulatory_window` (n = 250).

`risk.frtb.pla.ks_pvalue`: inputs `ks` in [0, 1] and `n`; output `Q_KS(ks sqrt(n/2))`. Exists so the two printed p-values of MAR32.42 can be checked at D = 0.09 and 0.12, which no 250-day data set can produce exactly (22.5/250 is not a count).

### `risk.frtb.ima.lh`

MAR33.12 Table 2 lookup, then FAQ4 (maturity) and FAQ5 (index) rules (KR-60). Output `n` in {10, 20, 40, 60, 120}.

### `risk.frtb.ima.es_lh`

Inputs (KR-57) one of: `es_t` (five numbers ES_T(P,j) >= 0), `sigma` (five standard deviations of 10-day P&L, normal mode), `pnl` (five lists). Each list j is the P&L of the portfolio under 10-day shocks to the factors with LH >= LH_j only (Q(p_i, j), MAR33.4(4)-(6)); the caller builds the lists. ES per list at 97.5% with the `risk.var.historical` estimator. Then (MAR33.4, image p. 671), T = 10, LH = (10, 20, 40, 60, 120):

`ES = sqrt( ES_1^2 + sum_{j=2..5} ( ES_j sqrt((LH_j - LH_{j-1}) / 10) )^2 )`, so the weights on `ES_j^2` are 1, 1, 2, 2, 6.

Outputs: `es_by_horizon` (five), `es`.

### `risk.frtb.ima.es_stressed`

`ES = ES_R,S max(1, ES_F,C / ES_R,C)` (MAR33.6, KR-58). Outputs `es`, `ratio`, `ratio_floored`.

### `risk.frtb.ima.imcc`

`IMCC = 0.5 IMCC(C) + 0.5 sum_i IMCC(C_i)` with each IMCC computed by `es_stressed` from its own triple (MAR33.15, KR-58). Inputs: `portfolio` {es_rs, es_fc, es_rc}, `classes` (one to five of IR, EQ, FX, COM, CS, each a triple).

### `risk.frtb.ima.ses`

`SES = sqrt(sum ISES_i^2) + sqrt(sum ISES_j^2) + sqrt((0.6 sum SES_k)^2 + (1 - 0.36) sum SES_k^2)` (MAR33.17). Inputs: three lists `idio_credit`, `idio_equity`, `other` of non-negative stress-scenario charges (each already at LH max(MAR33.12 LH, 20), MAR33.16(1); the scenarios themselves are the caller's).

### `risk.frtb.rfet` and `risk.frtb.rfet.bucket`

As KR-59. Outputs `distinct_days`, `crit1` (with `min_window_count` and the first failing window start), `crit2`, `pass`. Bucket lookup per MAR31.16 Table 1.

### `risk.frtb.ima.capital`

Inputs: `imcc_prev`, `ses_prev`, `imcc_avg`, `ses_avg`, `exceptions` (integer), `qualitative_addon` (default 0), `drc`, `desks` [{zone GREEN or AMBER, sa}], `c_u`, `sa_all`. Then (MAR33.41-33.45, KR-61): `m_c` from the MAR32.9 table plus the add-on; `C_A = max(imcc_prev + ses_prev, m_c imcc_avg + ses_avg)`; `IMA_G,A = C_A + drc`; `SA_G,A = sum sa`; `k = 0.5 sum_amber sa / sum sa`; `surcharge = k max(0, SA_G,A - IMA_G,A)`; `ACR_total = min(IMA_G,A + surcharge + c_u, sa_all) + max(0, IMA_G,A - SA_G,A)`. Outputs every intermediate.

## Worked examples (written out)

**PLA on five days (pla_k-0001).** HPL = (-3, 1, 4, -1, 2), RTPL = (-2, 0, 5, 1, 3). Ranks of HPL: -3 is lowest (1), -1 (2), 1 (3), 2 (4), 4 (5), so by day (1, 3, 5, 2, 4). Ranks of RTPL by day (1, 2, 5, 3, 4). No ties, so r_S = 1 - 6 sum d^2 / (n(n^2 - 1)) with d = (0, 1, 0, -1, 0): 1 - 6 x 2 / 120 = 0.9. KS: at x = -3 the HPL ECDF is 1/5, the RTPL ECDF 0: difference 0.2; the largest difference over all ten pooled values is 0.2 (also at -1, 2 and 4); d = 1, ks = 0.2. Zone: 0.9 > 0.80 but 0.2 > 0.12, so red. SciPy `spearmanr` gives 0.8999999999999998 and `ks_2samp` 0.2.

**Liquidity horizons (es_k-0003).** ES_T(P,j) = (10, 8, 6, 4, 2): ES^2 = 100 + 64 x 10/10 + 36 x 20/10 + 16 x 20/10 + 4 x 60/10 = 100 + 64 + 72 + 32 + 24 = 292, ES = 17.08800749063506. If instead every factor had LH 120 (es_k-0002, all ES_T(P,j) equal to E), ES = E sqrt(1 + 1 + 2 + 2 + 6) = E sqrt(12) = E sqrt(120/10): the cascade reduces to square-root-of-time scaling, which is how the normal case is checked against SciPy.

**SES (ses_k-0001).** Idiosyncratic credit (3, 4): sqrt(9 + 16) = 5. Idiosyncratic equity (5, 12): 13. Others (1, 2, 2): sum 5, sum of squares 9; sqrt((0.6 x 5)^2 + 0.64 x 9) = sqrt(9 + 5.76) = 3.841874542459709. SES = 21.84187454245971.

**Capital (cap_k-0002).** Six exceptions: m_c = 1.76. C_A = max(100 + 20, 1.76 x 90 + 15) = max(120, 173.4) = 173.4. IMA_G,A = 173.4 + 30 = 203.4. Desks: green SA 150, amber SA 100, SA_G,A = 250, k = 0.5 x 100/250 = 0.2. Surcharge = 0.2 x (250 - 203.4) = 9.32. ACR = min(203.4 + 9.32 + 40, 300) + max(0, 203.4 - 250) = 252.72 + 0 = 252.72.

## Errors (order KR-67 = HR-122)

`E_SCHEMA`: missing field, wrong type, unlisted enum (LH category, zone, bucket row). `E_LIMIT`: lists above the KR-67 sizes. Finite rule: `E_DOMAIN`. Structural `E_INPUT`: `hpl` and `rtpl` of different lengths; not exactly five horizons; more than one of `es_t`, `sigma`, `pnl`; an LH class key repeated. `E_DOMAIN`: n < 3; a constant rank series (zero variance); negative ES, sigma or SES charge; `es_rc <= 0`; `exceptions < 0`; `ks` outside [0, 1]; `delta = 1` or a negative maturity in the bucket lookup; FAQ5 weights not summing to 1 within 1e-12; `sum sa = 0` with an amber desk.

## Golden cases (designed 2026-11-19; values computed by hand and by SciPy in a scratch folder; not yet frozen)

PLA series (inputs reproducible from integers, no floating point in the inputs): for t = 0..249, `h_t = ((7919 t + 13) mod 1009) - 504` (250 distinct integers), and RTPL series
A: `h_t + ((37 t) mod 101) - 50`; B: `h_t + 4 (((53 t) mod 211) - 105)`; C: `2 h_t + 300`; D: `((433 t + 7) mod 1009) - 504`; E: `h_t + 6 (((53 t) mod 211) - 105)`. First values: h = (-491, 365, 212, 59, -94, ...), A = (-541, 352, 236, 19, -97, ...).

| Case | Input | Expected | Arithmetic / tolerance | Outside check |
|---|---|---|---|---|
| pla_k-0001 | five-day example above | spearman 0.9, ks 0.2 (d 1), zone RED | above; 1e-12 | **L** (SciPy spearmanr, ks_2samp) |
| pla_k-0002 | HPL h, RTPL A (RTPL has 103 distinct values: ties, average ranks) | spearman 0.994739210447638, d 9, ks 0.036, GREEN | 1e-12 | **L** |
| pla_k-0003 | h, B | spearman 0.767250804012864, d 30, ks 0.12, AMBER (KS exactly at 0.12 is not "above", KR-56); p 0.0546463301139 | 1e-12 | **L** |
| pla_k-0004 | h, C | spearman 1, d 99, ks 0.396, RED (distributions differ, ranks identical) | 1e-12 | **L** |
| pla_k-0005 | h, D | spearman 0.0098585897374358, d 2, ks 0.008, RED (by correlation only) | 1e-12 | **L** |
| pla_k-0006 | h, E | spearman 0.650419238707819, d 49, ks 0.196, RED (both) | 1e-12 | **L** |
| pla_k-0007 | ks_pvalue ks 0.09, n 250 | 0.263380632422 | printed "p-value = 0.264": agreement within 1e-3 absolute, fixed now (the printed value is 0.0006 above the asymptotic one; recorded, not hidden) | **P** (MAR32.42, p. 667) and **L** (`kstwobign.sf`) |
| pla_k-0008 | ks_pvalue ks 0.12, n 250 | 0.0546463301139 | printed 0.055 within 1e-3 | **P** and **L** |
| es_k-0001 | sigma (1, 0, 0, 0, 0) | 2.337802792201415 | phi(z)/0.025, z = Phi^-1(0.975); 1e-12 | **L** (SciPy `quad` of the normal tail: 2.3378027922014155) |
| es_k-0002 | sigma (1, 1, 1, 1, 1) | 8.098386428338474 | 2.337802792201415 x sqrt(12); 1e-12 | **L** (normal ES with scale sqrt(12) by `quad`: 8.098386428338475) |
| es_k-0003 | es_t (10, 8, 6, 4, 2) | 17.08800749063506 | sqrt(292) | B |
| es_k-0004 | es_t (10, 0, 0, 0, 0) | 10 | | B |
| es_k-0005 | pnl list 1 = h (250 values), lists 2-5 empty | es_by_horizon (493.52, 0, 0, 0, 0); es 493.52 | n alpha = 6.25: (503 + 499 + 495 + 491 + 490 + 486 + 0.25 x 482) / 6.25 = 3084.5/6.25 | B |
| est_k-0001 | ES_R,S 12, ES_F,C 10, ES_R,C 8 | ratio 1.25; es 15 | | B |
| est_k-0002 | 12, 7, 8 | ratio 0.875; floored; es 12 | KR-58 | B |
| imcc_k-0001 | portfolio (12, 10, 8); IR (6, 5, 4); EQ (5, 4, 5) | IMCC(C) 15; IR 7.5; EQ 5 (floored); IMCC 13.75 | 0.5 x 15 + 0.5 x 12.5 | B |
| ses_k-0001 | worked example | 21.84187454245971 | above | B |
| ses_k-0002 | other (10) only | 10 | sqrt(36 + 64) | B |
| cap_k-0001 | 100, 20, 90, 15, exceptions 6 | m_c 1.76; C_A 173.4 | | B (m_c is a T lookup of MAR32.9) |
| cap_k-0002 | worked example | 252.72 and intermediates | above | B |
| cap_k-0003 | as 0001; drc 30; desks GREEN 180; c_u 40; sa_all 220 | IMA_G,A 203.4; k 0; surcharge 0; ACR 243.4 | min(243.4, 220) + (203.4 - 180) | B |
| rfet_k-0001 | as_of 2026-06-30; one observation on each day 2026-03-23 to 2026-06-30 (100 days) | crit1 false (first failing window 2025-07-01 to 2025-09-28, count 0); crit2 true; pass | | B |
| rfet_k-0002 | as_of 2026-06-30; 2025-07-05 + 15k days, k = 0..23 | 24 days; min window count 5; crit1 true; crit2 false; pass | first window 6, last window 5 | B |
| rfet_k-0003 | as_of 2026-06-30; each day 2025-07-01 to 2025-07-30 | 30 days; crit1 false (first failing window starts 2025-07-28, count 3); crit2 false; fail | | B |
| rfet_k-0004 | rfet_k-0002 list with every date twice and k = 23 removed | 23 distinct days; crit1 false (23 < 24; min window count 4); crit2 false; fail | duplicates count once | B |
| rfet_k-0005 | bucket row A, t 0.75 | 2 | lower bound inclusive | T |
| rfet_k-0006 | row C, t 7.5 | 4 | | T |
| rfet_k-0007 | row D, delta 0.95 | 5 | | T |
| rfet_k-0008 | row B, t 30 | 6 | | T |
| lh_k-0001 | IR_volatility, maturity_days 30 | 40 | FAQ4 printed example | **P** (MAR33.12 FAQ4, p. 675) |
| lh_k-0002 | index constituents (0.8, 10), (0.2, 20) | 20 | weighted 12; FAQ5 printed example | **P** (MAR33.12 FAQ5, p. 675) |
| lh_k-0003 | FX pair JPY/USD | 10 | footnote 309, order ignored | T |
| lh_k-0004 | CS_corporate_HY | 60 | Table 2 | T |

Error goldens: pla_ke-0001 lengths 250 and 249 (`E_INPUT`); pla_ke-0002 constant RTPL (`E_DOMAIN`); es_ke-0001 negative ES (`E_DOMAIN`); es_ke-0002 four horizons and a negative ES at once (`E_INPUT` first, HR-122); est_ke-0001 ES_R,C 0 (`E_DOMAIN`); rfet_ke-0001 delta 1 (`E_DOMAIN`); cap_ke-0001 exceptions -1 (`E_DOMAIN`).

Value cases 33. Printed (P) 4 (pla_k-0007, 0008, lh_k-0001, 0002); library (L) 10 (pla_k-0001 to 0008, es_k-0001, 0002; two overlap with P). Strict P or L: 12/33 = 36%. With the six table lookups (T): 18/33 = 55%.

## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 All value goldens in all four builds to 1e-12 relative (1e-15 absolute at 0); pla_k-0007 and 0008 also within 1e-3 of the printed p-values.
- A2 SciPy agreement, run by the oracle lane before any build compares: spearman and ks of every PLA golden equal SciPy to 1e-12; es_k-0001 and 0002 equal the `quad` values to 1e-12.
- A3 Properties (10,000 random cases): `spearman` symmetric in its arguments and invariant under any strictly increasing transform of either series; `ks` invariant under a common strictly increasing transform of both; `es_lh` with a single nonzero horizon j gives ES_j sqrt(sum of weights up to j); `es_stressed` never below ES_R,S; `ses` with a single entry in any list equals that entry.
- A4 Gate (plan 15): 60% of the 33 value cases outside-checked under KR-68. Strict share now 36%; K-8f moves to a point release unless a DR-H2 blind lane re-derives at least 8 of the B cases (12 + 8 = 20 of 33 = 61%) (`program/STAGE_K_W2_GATE.md`).

## Limits

- No ES model: the caller supplies P&L scenario lists or ES values per horizon. Choosing Q(p_i, j), the stress period, the reduced set and the 75% test (MAR33.5(2)(b)) are the caller's.
- The IMA DRC model (MAR33.18-33.39, a two-factor default simulation at 99.9%) is not in K-8f.
- RFET: no vendor audit or representativeness test (MAR31.14-31.15); no lag between RFET and calibration periods (KR-59); the seven data principles of MAR31.26 are qualitative and out of scope.
- NMRF stress scenarios (MAR33.16) are the caller's; the operation only aggregates.
- PLA: the input alignment rules of MAR32.30-32.33 are the caller's; HPL and RTPL are inputs.
- Averages over 60 days and 12 weeks are inputs (`imcc_avg`, `ses_avg`, `drc`), not computed from a history.
