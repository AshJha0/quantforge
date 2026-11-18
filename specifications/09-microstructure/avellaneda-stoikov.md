# Avellaneda-Stoikov inventory-aware quotes

Spec version 0.1.0 (stage H wave 1; confirmed 2026-11-18 by the stage H coordinator). Status: Specified, not implemented. Rulings HR-2, HR-7. Plan items 14.7 H-4 (quotes match the closed form to 1e-10), 15.1 "Research" (reused by the market-making prereg study).

**Plain idea.** A market maker long inventory shades both quotes down to sell more readily; the spread widens with risk aversion, volatility and time left, plus a term from how fast fill probability falls with distance from the mid.

Sources:
- [AS08] M. Avellaneda, S. Stoikov, "High-frequency trading in a limit order book", *Quantitative Finance* 8(3) (2008) 217-224; read 2026-11-15 in the published version, free copy at math.nyu.edu/~avellane/HighFrequencyTrading.pdf (journal page numbers). Verified: reservation price `r(s, t) = s - q gamma sigma^2 (T - t)`, eq. (29), p. 221; total bid-ask spread `delta_a + delta_b = gamma sigma^2 (T - t) + (2 / gamma) ln(1 + gamma / k)`, eq. (30), p. 221. Correction to the draft: these are not exact closed forms of the HJB problem but the paper's approximate solution (section 3.2, "Asymptotic expansion in q", first-order approximation (26) of the arrival term, p. 221); the paper calls them "simple expressions" from that approximation. Evidence class: paper, read.
- Section 3.3, p. 222, uses s = 100, T = 1, sigma = 2, dt = 0.005, q = 0, gamma = 0.1, k = 1.5, A = 140 (the as_h-0001 inputs come from here) and Tables 1-3 (pp. 222-223) print the average spread of the inventory strategy: 1.49 (gamma = 0.1), 1.35 (gamma = 0.01), 3.02 (gamma = 1). The spread (30) is linear in T - t and independent of q, so its time average over [0, T] equals the spread at time_left = T/2; cases as_h-0005 to 0007 check that against the printed values. (In the text extraction the gamma glyph is lost in the table captions; gamma is identified from the text on pp. 222-223.)
- Hand calculation for as_h-0001 to 0004, then Blind re-derivation (DR-H2, 2026-11-15, second lane, mpmath 40 digits, inputs only; STAGE_H_BLIND_REDERIVATION.md): as_h-0001..0004 MATCH (spread 2.9e-11 relative, print rounding; as_h-0004 E_DOMAIN): outside-checked per DR-H2. as_h-0005..0007 are outside-checked against the printed paper tables (blind lane also matched them).

## `micro.mm.as_quotes`
Inputs `mid` s, `inventory` q (signed), `risk_aversion` gamma (> 0), `sigma` (>= 0), `time_left` (>= 0), `k` (> 0). Outputs `reservation`, `spread`, `bid = r - spread/2`, `ask = r + spread/2`. gamma <= 0 or k <= 0: `E_DOMAIN`.

## Golden cases
| Case | Input | Expected | Derivation |
|---|---|---|---|
| as_h-0001 | s = 100, q = 2, gamma = 0.1, sigma = 2, time_left = 1, k = 1.5 | r = 99.2; spread = 1.6907704228; bid 98.3546147886; ask 100.0453852114 | 100 - 2 x 0.1 x 4; 0.4 + 20 ln(16/15) |
| as_h-0002 | q = 0, rest as 0001 | r = 100; bid 99.1546147886; ask 100.8453852114 | symmetric |
| as_h-0003 | time_left = 0, rest as 0001 | r = 100; spread = 1.2907704228 | terminal: only (2/gamma) ln(1 + gamma/k) |
| as_h-0004 | gamma = 0 | `E_DOMAIN` | the limit 2/k is a property test |
| as_h-0005 | q = 0, gamma = 0.1, sigma = 2, time_left = 0.5, k = 1.5, s = 100 | spread = 1.4907704228 | OUTSIDE-CHECKED: [AS08] Table 1, p. 222, prints 1.49; 0.2 + 20 ln(16/15). Tolerance 0.005 (two printed decimals; the paper averages over a simulated dt = 0.005 grid) |
| as_h-0006 | as 0005 with gamma = 0.01 | spread = 1.3489085437 | OUTSIDE-CHECKED: Table 2, p. 222, prints 1.35; 0.02 + 200 ln(1 + 0.01/1.5). Tolerance 0.005 |
| as_h-0007 | as 0005 with gamma = 1 | spread = 3.0216512475 | OUTSIDE-CHECKED: Table 3, p. 223, prints 3.02; 2 + 2 ln(5/3). Tolerance 0.005 |

## Property tests
As gamma -> 0 the spread tends to 2/k; r is linear and decreasing in q.

## Limitations
Exponential intensity, no inventory bound, Brownian mid; no tick rounding (the simulator rounds).
