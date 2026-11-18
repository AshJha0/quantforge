# Transaction cost analysis: pre-trade estimates and cost attribution

Spec version 0.1.0 (stage H wave 2; spec lane 2026-11-18). Status: Specified, not implemented. Rulings: `stage-h-rulings-w2-exec.md` HR-64, HR-65, with HR-2, HR-8, HR-56 from earlier stage H files. Plan item STAGE_H_START.md H-17 (acceptance: attribution sums to the total within 1e-10). Extends `tca.md` (`exec.tca.shortfall`), which is unchanged.

**Plain idea.** Before trading, estimate what the order will cost: half the spread, plus market impact that grows with the order's share of daily volume and with volatility, and say separately how much the price may wander while the order works (timing risk). After trading, split what it did cost into three parts that add up exactly: delay (the mid moved between the decision and arrival), impact (the mid moved while we traded) and spread (what we paid against the mid at each fill).

Sources:
- [Kis13] R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2013: the "I-star" impact model `I* = a1 (Q/ADV)^a2 sigma^a3` and its split into a participation-dependent temporary part `b1 I* POV^a4` and a permanent part `(1 - b1) I*`. Not free; chapter, page and the exact parameterisation **NOT verified** (recalled). The parameters a1..a4, b1 are inputs here; no default value is claimed from the book. Evidence class: textbook, recalled, UNVERIFIED.
- [AC00] eq. (10), p. 12 (preprint pages, see `almgren-chriss.md`): the linear trajectory's price variance `1/3 sigma^2 X^2 T (1 - 1/N)(1 - 1/(2N))`, which tends to `1/3 sigma^2 X^2 T` as N grows; the timing-risk line below is its square root over X. Evidence class: paper, read.
- [Per88] as in `tca.md` for the paper-portfolio total that the attribution splits.
- Hand calculation for every golden below by this spec lane, 2026-11-18. Exact decimal arithmetic except the square roots, which were taken to 20 digits and printed to 12 significant digits. Blind re-derivation (DR-H2, 2026-11-18): 11/11 agree (6 MATCH, 5 error cases SHAPE-ONLY), 0 VALUE MISMATCH; program/STAGE_H_BLIND_EXEC.md. Generator: `oracle/python/gen_stage_h_w2_exec.py`.

## `exec.tca.pretrade`
Inputs `quantity` X (> 0), `adv` (average daily volume, > 0), `daily_vol` sigma (decimal, >= 0), `participation` p in (0, 1) (of total market volume including our own, HR-4), `half_spread_bps` (>= 0), `params` {a1 > 0, a2, a3, a4, b1 in [0, 1]}, optional `price` P (> 0).
- `istar_bps` = `a1 (X / adv)^a2 sigma^a3`
- `impact_bps` = `b1 istar_bps p^a4 + (1 - b1) istar_bps`
- `spread_bps` = `half_spread_bps`
- `expected_cost_bps` = `spread_bps + impact_bps`
- `duration_days` T = `X / (p adv)` (HR-64)
- `timing_risk_bps` = `1e4 sigma sqrt(T / 3)` (one standard deviation; NOT added to the expected cost, HR-64)
- with `price`: `expected_cost` = `expected_cost_bps X P / 1e4`, `timing_risk` = `timing_risk_bps X P / 1e4`.
Errors: X <= 0: `E_INPUT`; adv <= 0, sigma < 0, p outside (0, 1), half spread < 0, a1 <= 0, b1 outside [0, 1], P <= 0: `E_DOMAIN`. sigma = 0 with a3 <= 0 is `E_DOMAIN` (0 to a non-positive power).

## `exec.tca.attribution`
Inputs `side` (s), `decision_price` P_d, `arrival_mid` m_0, `end_price` P_c, `order_quantity` X, `fills` list of {`quantity` q_i, `price` p_i, `mid` m_i} (the mid at the fill time), `fees`. Q = sum q_i (HR-65).
- delay = `s Q (m_0 - P_d)`
- impact = `s sum q_i (m_i - m_0)`
- spread = `s sum q_i (p_i - m_i)` (negative when filled inside the mid: price improvement)
- execution = impact + spread (equals `exec.tca.shortfall` execution with `arrival_price` = m_0)
- opportunity = `s (X - Q)(P_c - P_d)`
- total = delay + impact + spread + opportunity + fees; `total_bps` = total / (X P_d) x 1e4
Errors: Q > X, X <= 0, a fill quantity <= 0: `E_INPUT`; any price or mid <= 0: `E_DOMAIN`. No fills is allowed (delay, impact, spread 0).
Identity (acceptance H-17): `|delay + impact + spread - s sum q_i (p_i - P_d)| <= 1e-10 max(1, |total|)`, and the same input to `exec.tca.shortfall` (with `arrival_price` = m_0) gives the same total to 1e-10.

## Golden cases

| Case | Input | Expected | Derivation |
|---|---|---|---|
| tcx_h-0001 | pretrade X = 40,000, adv = 1,000,000, sigma = 0.02, p = 0.25, half spread 1.5 bp, a1 = 700, a2 = 0.5, a3 = 1, a4 = 0.5, b1 = 0.9, price 50 | istar_bps 2.8, impact_bps 1.54, spread_bps 1.5, expected_cost_bps 3.04, duration_days 0.16, timing_risk_bps 46.1880215352, expected_cost 608, timing_risk 9237.60430703 | 700 x 0.2 x 0.02; 0.9 x 2.8 x 0.5 + 0.28; 40000 / 250000; 200 sqrt(0.16/3); notional 2e6 |
| tcx_h-0002 | pretrade X = 100,000, adv = 1,000,000, sigma = 0.02, p = 0.04, half spread 0, a1 = 700, a2 = 1, a3 = 1, a4 = 0.5, b1 = 1, no price | istar_bps 1.4, impact_bps 0.28, spread_bps 0, expected_cost_bps 0.28, duration_days 2.5, timing_risk_bps 182.574185835 | 700 x 0.1 x 0.02; 1.4 x 0.2; 1e5 / 4e4; 200 sqrt(2.5/3) |
| tcx_h-0003 | pretrade as 0002 with p = 1 | `E_DOMAIN` | p outside (0, 1) |
| tcx_h-0004 | pretrade as 0002 with b1 = 1.2 | `E_DOMAIN` | b1 outside [0, 1] |
| tcx_h-0005 | pretrade as 0002 with X = 0 | `E_INPUT` | non-positive quantity |
| tcx_h-0006 | attribution BUY X = 1,000, P_d = 100, m_0 = 100.10, P_c = 101, fills (600 @ 100.20, mid 100.15), (200 @ 100.30, mid 100.25), fees 5 | delay 80, impact 60, spread 40, execution 100, opportunity 200, fees 5, total 385, total_bps 38.5 | 800 x 0.10; 600 x 0.05 + 200 x 0.15; 600 x 0.05 + 200 x 0.05; matches tca_h-0001 |
| tcx_h-0007 | attribution SELL X = 1,000, P_d = 100, m_0 = 100, P_c = 99, fills (500 @ 99.90, mid 99.95), (500 @ 99.70, mid 99.80), fees 2 | delay 0, impact 125, spread 75, execution 200, opportunity 0, fees 2, total 202, total_bps 20.2 | -(500 x -0.05 + 500 x -0.20); -(500 x -0.05 + 500 x -0.10); 202 / 1e5 x 1e4 |
| tcx_h-0008 | attribution BUY X = 100, P_d = 99.5, m_0 = 100, P_c = 100, fills (100 @ 100.00, mid 100.05), fees 0 | delay 50, impact 5, spread -5, execution 0, opportunity 0, fees 0, total 50, total_bps 50.2512562814 | price improvement 0.05 below the mid; 50 / 9950 x 1e4 |
| tcx_h-0009 | attribution BUY X = 100, P_d = 100, m_0 = 100.5, P_c = 101, no fills, fees 0 | delay 0, impact 0, spread 0, execution 0, opportunity 100, fees 0, total 100, total_bps 100 | delay on executed quantity only (HR-8) |
| tcx_h-0010 | attribution as 0006 with fills summing to 1,200 (600 @ 100.20 mid 100.15, 600 @ 100.30 mid 100.25) | `E_INPUT` | Q > X |
| tcx_h-0011 | attribution as 0006 with the first fill's mid 0 | `E_DOMAIN` | mid <= 0 |

Canonical JSON for every case: `datasets/golden/stage_h/tcx_h.json`.

## Acceptance tests (fixed 2026-11-18, before any build)
1. Attribution identity above on every golden and on 1,000 random inputs (seed 20261118, 1 to 50 fills, prices in [1, 1000]): delay + impact + spread equals `s sum q_i (p_i - P_d)` within 1e-10 max(1, |total|); total equals `exec.tca.shortfall` total within the same bound.
2. Pre-trade monotonicity (property): `impact_bps` non-decreasing in X when a2 >= 0, in p when a4 >= 0; `timing_risk_bps` non-increasing in p.
3. Goldens tcx_h-0001..0011 in all four languages to the `simple_analytic` tolerance.

## Post-blind shape changes (2026-11-18, after the blind lane froze; no value changed)
Output field names are fixed as one name each. Pretrade: `istar_bps`, `impact_bps`, `spread_bps`, `expected_cost_bps`, `duration_days`, `timing_risk_bps`, and only with `price`: `expected_cost`, `timing_risk`. Attribution: `delay`, `impact`, `spread`, `execution`, `opportunity`, `fees` (the input echoed, so the output alone sums to `total`), `total`, `total_bps`. Errors as `{"status": "error", "error_code": CODE}`. Record: program/STAGE_H_BLIND_EXEC.md.

## Limitations
The pre-trade model is a parameterised form; its parameters are inputs and nothing here says they fit any venue (calibration is the research lane, H-1). Timing risk assumes a straight-line schedule and no drift. Attribution needs the mid at each fill; with a stale or missing mid the impact/spread split is wrong even though the sum stays right.
