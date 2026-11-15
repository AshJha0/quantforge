# Avellaneda-Stoikov inventory-aware quotes (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1). Status: Specified, not implemented. Rulings H-2, H-7. Plan items 14.7 H-4 (quotes match the closed form to 1e-10), 15.1 "Research" (reused by the market-making prereg study).

**Plain idea.** A market maker long inventory shades both quotes down to sell more readily; the spread widens with risk aversion, volatility and time left, plus a term from how fast fill probability falls with distance from the mid.

Sources:
- [AS08] M. Avellaneda, S. Stoikov, "High-frequency trading in a limit order book", *Quantitative Finance* 8(3) (2008) 217-224; free preprint (URL not re-checked). Formulas: reservation price `r = s - q gamma sigma^2 (T - t)`; total spread `gamma sigma^2 (T - t) + (2 / gamma) ln(1 + gamma / k)`. Recalled; equation and page numbers NOT verified. Evidence class: paper, recalled.
- Hand calculation for goldens.

## `micro.mm.as_quotes`
Inputs `mid` s, `inventory` q (signed), `risk_aversion` gamma (> 0), `sigma` (>= 0), `time_left` (>= 0), `k` (> 0). Outputs `reservation`, `spread`, `bid = r - spread/2`, `ask = r + spread/2`. gamma <= 0 or k <= 0: `E_DOMAIN`.

## Golden cases
| Case | Input | Expected | Derivation |
|---|---|---|---|
| as_h-0001 | s = 100, q = 2, gamma = 0.1, sigma = 2, time_left = 1, k = 1.5 | r = 99.2; spread = 1.6907704228; bid 98.3546147886; ask 100.0453852114 | 100 - 2 x 0.1 x 4; 0.4 + 20 ln(16/15) |
| as_h-0002 | q = 0, rest as 0001 | r = 100; bid 99.1546147886; ask 100.8453852114 | symmetric |
| as_h-0003 | time_left = 0, rest as 0001 | r = 100; spread = 1.2907704228 | terminal: only (2/gamma) ln(1 + gamma/k) |
| as_h-0004 | gamma = 0 | `E_DOMAIN` | the limit 2/k is a property test |

## Property tests
As gamma -> 0 the spread tends to 2/k; r is linear and decreasing in q.

## Limitations
Exponential intensity, no inventory bound, Brownian mid; no tick rounding (the simulator rounds).
