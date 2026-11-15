# Market impact: square-root and Obizhaeva-Wang (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1). Status: Specified, not implemented. Rulings H-2, H-10. Plan item 15.1 "Market impact"; calibration on the crypto book is the research lane (14.7 H-1), not this spec.

Sources:
- [TLD11] B. Toth, Y. Lemperiere, C. Deremble, J. de Lataillade, J. Kockelkoren, J.-P. Bouchaud, "Anomalous price impact and the critical nature of liquidity in financial markets", *Physical Review X* 1 (2011) 021006 (open access). Form `I = Y sigma sqrt(Q / V)`, Y of order one; Y is an input here. Evidence class: paper, recalled.
- [OW13] A. Obizhaeva, J. Wang, "Optimal trading strategy and supply/demand dynamics", *J. Financial Markets* 16(1) (2013) 1-32 (free SSRN preprint). Result used: block-shaped book, exponential resilience rate rho; the optimal schedule trades `X / (rho T + 2)` at t = 0 and at T and continuously at rate `rho X / (rho T + 2)` between. Recalled; proposition and page NOT verified. Evidence class: paper, recalled.

## `exec.impact.sqrt`
Inputs `quantity` Q, `daily_volume` V (> 0), `daily_vol` sigma, `coefficient` Y (default 1, labelled assumed per H-10). Output `impact` (fraction of price) = `Y sigma sqrt(Q / V)`. Q < 0 or V <= 0: `E_DOMAIN`.

## `exec.impact.ow_optimal`
Inputs `quantity` X, `horizon` T, `resilience` rho (> 0). Outputs `initial_block`, `rate`, `final_block`; `2X/(rho T + 2) + rho T X/(rho T + 2) = X`.

## Golden cases
| Case | Input | Expected | Derivation |
|---|---|---|---|
| imp_h-0001 | Q = 1e5, V = 1e7, sigma = 0.02, Y = 1 | 0.002 | 0.02 x sqrt(0.01) |
| imp_h-0002 | Q = 4e5, rest as 0001 | 0.004 | four times Q, twice the impact |
| imp_h-0003 | X = 1,000, T = 1, rho = 8 | blocks 100 and 100, rate 800 | 1000/10; 8 x 1000/10 |

Property test (not a golden until checked against [OW13]): as rho -> 0 each block tends to X/2.

## Limitations
Static formulas with assumed parameters; no claim about any real venue until the calibration lane reports with standard errors.
