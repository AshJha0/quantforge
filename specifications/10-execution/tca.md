# Transaction cost analysis: implementation shortfall

Spec version 0.1.0 (stage H wave 1; confirmed 2026-11-18 by the stage H coordinator). Status: implemented in all four builds (Python, Java, C++, Rust; 2026-11-18). Rulings HR-2, HR-8, HR-9. Plan items 14.7 H-3 (decomposition sums to 1e-10), 15.1 "TCA".

Sources:
- [Per88] A. Perold, "The implementation shortfall: paper versus reality", *J. Portfolio Management* 14(3) (1988) 4-9. Paper-portfolio definition. Not free; recalled. Evidence class: paper, recalled.
- [Kis13] as in `schedules.md` (delay, trading and opportunity split). Pages NOT verified.
- Hand calculation for goldens, then Blind re-derivation (DR-H2, 2026-11-15, second lane, mpmath 40 digits, inputs only; STAGE_H_BLIND_REDERIVATION.md): tca_h-0001..0003 MATCH (outside-checked per DR-H2). Perold [Per88] and Kissell [Kis13] are not free and were not read.

## `exec.tca.shortfall`
Inputs `side` (s = +1 BUY, -1 SELL), `decision_price` P_d, `arrival_price` P_0, `end_price` P_c, `order_quantity` X, `fills` list of (q_i, p_i), `fees`; optional `benchmark_vwap`. Q = sum q_i.
- delay = `s Q (P_0 - P_d)` (executed quantity, HR-8)
- execution = `s sum q_i (p_i - P_0)`
- opportunity = `s (X - Q)(P_c - P_d)`
- total = delay + execution + opportunity + fees; `total_bps` = total / (X P_d) x 1e4
- with `benchmark_vwap`: `vwap_slippage` = `s Q (avg_fill - VWAP)`
Errors: Q > X: `E_INPUT`; a price <= 0: `E_DOMAIN`.

## Golden cases
| Case | Input | Expected | Derivation |
|---|---|---|---|
| tca_h-0001 | BUY X = 1,000, P_d = 100, P_0 = 100.10, P_c = 101, fills (600 @ 100.20), (200 @ 100.30), fees 5 | delay 80; execution 100; opportunity 200; total 385; 38.5 bp | 800 x 0.10; 600 x 0.10 + 200 x 0.20; 200 x 1 |
| tca_h-0002 | SELL, same prices and fills, fees 0 | delay -80, execution -100, opportunity -200, total -380 | a seller gains when prices rise |
| tca_h-0003 | fills sum to 1,200 with X = 1,000 | `E_INPUT` | overfill |
| tca_h-0004 | as 0001 with benchmark_vwap = 100.15 | vwap_slippage 60, rest as 0001 | average fill 100.225; 800 x 0.075; added by the oracle lane 2026-11-18; hand calculation and oracle only, not blind re-derived |
| tca_h-0005 | as 0001 with P_0 = 0 | `E_DOMAIN` | a price <= 0; added by the oracle lane 2026-11-18; hand calculation and oracle only, not blind re-derived |
| tca_h-0006 | as 0001 with X = 0, no fills | `E_INPUT` | non-positive order quantity (HR-56); added by the integration lane 2026-11-18 for HR-56; hand calculation and oracle only, not blind re-derived |

## Property tests
Components sum to total to 1e-10 relative; a full fill has opportunity 0.

## Limitations
Delay is charged on the executed quantity and the unexecuted part is reported separately as opportunity cost (HR-8, confirmed by DR-H3, Perold decomposition); a full-order delay (Kissell variant) is not offered. Attribution of execution cost into impact and spread needs the mid path and is wave 2.
