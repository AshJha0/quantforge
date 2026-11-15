# Market impact: square-root and Obizhaeva-Wang (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1). Status: Specified, not implemented. Rulings HR-2, HR-10. Plan item 15.1 "Market impact"; calibration on the crypto book is the research lane (14.7 H-1), not this spec.

Sources:
- [TLD11] B. Toth, Y. Lemperiere, C. Deremble, J. de Lataillade, J. Kockelkoren, J.-P. Bouchaud, "Anomalous price impact and the critical nature of liquidity in financial markets", *Physical Review X* 1 (2011) 021006 (open access). Form `I = Y sigma sqrt(Q / V)`, Y of order one; Y is an input here. Evidence class: paper, recalled.
- [OW13] A. Obizhaeva, J. Wang, "Optimal trading strategy and supply/demand dynamics", *J. Financial Markets* 16(1) (2013) 1-32; read 2026-11-15 in the published version, free copy on the first author's page (pages.nes.ru/aobizhaeva/OW-2013.pdf). Verified: block-shaped book, resilience rho (the paper's r); risk-neutral optimum `x_0 = x_T = X_0 / (rho T + 2)`, continuous rate `rho X_0 / (rho T + 2)` on (0, T): Proposition 2, eqs. (25a)-(25c), p. 15 (continuous-time limit of the discrete solution) and Proposition 3, eq. (31), p. 17 (continuous-time problem; same strategy). The strategy does not depend on the price impact lambda or the depth q (section 7.1, p. 17). Evidence class: paper, read.
- Fig. 2, p. 14, uses X_0 = 100,000, T = 1 day, q = 5,000, lambda = 1e-4, r = 2.231 and plots discrete solutions for N = 10, 25, 100 (first trades labelled 26,317, 24,697, 23,899). The paper prints no continuous-limit block for these parameters, so imp_h-0004 below is a hand calculation on the paper's parameters, outside-checked only by the DR-H2 blind re-derivation (rel. diff 8e-16), not by a printed figure; the printed discrete first trades decrease towards it, a consistency remark only.
- [TLD11] not re-read in this pass: still recalled, unverified (open access, to be read). Blind re-derivation (DR-H2, 2026-11-15, second lane, mpmath 40 digits, inputs only; STAGE_H_BLIND_REDERIVATION.md): imp_h-0001..0004 MATCH (0001..0003 exact, 0004 rel. 8e-16). The square-root goldens 0001/0002 are arithmetic on the stated form with Y an input, so they check the arithmetic, not the empirical law.

## `exec.impact.sqrt`
Inputs `quantity` Q, `daily_volume` V (> 0), `daily_vol` sigma, `coefficient` Y (default 1, labelled assumed per HR-10). Output `impact` (fraction of price) = `Y sigma sqrt(Q / V)`. Q < 0 or V <= 0: `E_DOMAIN`.

## `exec.impact.ow_optimal`
Inputs `quantity` X, `horizon` T, `resilience` rho (> 0). Outputs `initial_block`, `rate`, `final_block`; `2X/(rho T + 2) + rho T X/(rho T + 2) = X`.

## Golden cases
| Case | Input | Expected | Derivation |
|---|---|---|---|
| imp_h-0001 | Q = 1e5, V = 1e7, sigma = 0.02, Y = 1 | 0.002 | 0.02 x sqrt(0.01) |
| imp_h-0002 | Q = 4e5, rest as 0001 | 0.004 | four times Q, twice the impact |
| imp_h-0003 | X = 1,000, T = 1, rho = 8 | blocks 100 and 100, rate 800 | 1000/10; 8 x 1000/10 ([OW13] eq. (31)) |
| imp_h-0004 | X = 100,000, T = 1, rho = 2.231 | blocks 23,635.0744504845 each, rate 52,729.8510990310 | [OW13] eq. (31) with the Fig. 2 parameters; 1e5 / 4.231; 2.231e5 / 4.231 (mpmath) |

Property test: as rho -> 0 each block tends to X/2 (follows directly from [OW13] eq. (31)).

## Limitations
Static formulas with assumed parameters; no claim about any real venue until the calibration lane reports with standard errors.
