# FRTB internal models approach: backtesting zones and desk exception limits

Spec version 0.1.0 (stage K round 1, wave 1b, plan item K-8e; written 2026-11-19). Status: implemented in all four builds (Python `python/quantforge_core/frtb_backtest.py`; ports per `program/STAGE_K_W1B_PORTS_HANDOVER.md`), registered at integration on `k-r1` 2026-11-19. Rulings KR-40 to KR-47 (`specifications/stage-k-rulings-w1b.md`). Operations `risk.frtb.backtest.zone`, `risk.frtb.backtest.desk`, `risk.frtb.backtest.count`. In `cli-contract.md` under stage K wave 1b (contract 1.17.0).

**Plain idea.** A bank that uses its own model for market risk capital must check, every day, whether the loss it made was bigger than the model's one-day 99% value at risk. A correct model should be beaten about 2.5 days in 250. The regulator turns the count into a colour: green (nothing to see), amber (suspicious; capital goes up) and red (the model is almost certainly wrong; capital goes up most or the model is withdrawn). The boundaries come from the binomial distribution: amber starts at the count that a correct model would reach or stay under 95% of the time, red at 99.99%. Separately, each trading desk loses its permission to use the model if it has too many exceptions in a year.

## Sources

- [MAR32] Basel Committee on Banking Supervision, *The Basel Framework*, chapter MAR32 "Internal models approach: backtesting and P&L attribution test requirements", version effective 1 January 2023, consolidated PDF generated 11/11/2026 (`institutional-quant-engine-plan/basel-framework-full.pdf`), pages 658 to 668. Regulator text, **read** 2026-11-19. Verified: 32.3(3) 12 months, ie 250 trading days (p.659); 32.5 bank-wide VaR at the 99th percentile, exception when the actual or hypothetical loss exceeds the VaR, counted separately, overall number the greater (32.5(1)), a missing P&L or VaR counts as an outlier (32.5(2)) (p.659-660); 32.8 to 32.9 three zones and Table 1 multipliers 1.50 (0 to 4), 1.70, 1.76, 1.83, 1.88, 1.92 (5 to 9), 2.00 (10 or more) (p.660-661); 32.18 desk VaR at 97.5th and 99th percentiles with the same exception and outlier rules (p.662); 32.19 "more than 12 exceptions at the 99th percentile or 30 exceptions at the 97.5th percentile in the most recent 12-month period" moves the desk to the standardised approach (p.662).
- [MAR99] same PDF, chapter MAR99 "Guidance on use of the internal models approach", pages 753 to 761. Regulator text, **read** 2026-11-19. Verified: 99.8 overall exceptions the maximum of hypothetical and actual (p.755); 99.11 Table 1, exact and type 1 / type 2 probabilities for 250 observations at coverage 99%, 98%, 97%, 96%, 95% (p.755-756; all 176 printed numbers transcribed into `frtb-ima-backtest-tables.json`); 99.17 Table 2 and its notes (p.758-759): cumulative probabilities 8.11%, 28.58%, 54.32%, 75.81%, 89.22%, 95.88%, 98.63%, 99.60%, 99.89%, 99.97%, 99.99%; "For other sample sizes, the amber zone begins at the point where the cumulative probability equals or exceeds 95%, and the red zone begins at the point where the cumulative probability equals or exceeds 99.99%."
- The same Table 2 was read on the bis.org web page on 2026-11-15 by an earlier lane (`institutional-quant-engine-plan/STAGE_K_SOURCES.md`); the two reads agree.

## Relation to `risk.backtest.traffic_light` (KR-40)

The stage F operation implements the 1996 framework: zones `GREEN` `YELLOW` `RED` from the same binomial rule, and the 1996 plus factor on a multiplier base of 3 (`var-es-and-backtests.md`, vintage note R6-28.1). K-8e is a set of **new operations**, not an extension, because (1) the FRTB output is an absolute backtesting-dependent multiplier (1.50 to 2.00), not a plus factor, and its zone is called amber; changing the stage F output would break a four-build contract and its goldens; (2) FRTB counts the greater of the actual and hypothetical exception counts (MAR99.8) and fixes the coverage at 99%, so the inputs differ; (3) desk eligibility (MAR32.19) has no 1996 counterpart. The binomial core is the same; both operations agree on the zone and the cumulative probability at every count. As an outside check of the **existing** operation, suite `tlk_k` compares `risk.backtest.traffic_light` at 250 observations and 99% with MAR99 Table 2 (zone, `YELLOW` = amber, and cumulative probability; the plus factor is the 1996 table and is not compared).

## Formal statement

X ~ Binomial(n, 0.01). cdf(k) = P(X <= k). amber_from = min{k in 0..n : cdf(k) >= 0.95}; red_from = min{k : cdf(k) >= 0.9999} (both exist since cdf(n) = 1). Exceptions x = max(x_actual, x_hypothetical). Zone RED if x >= red_from, AMBER if x >= amber_from, else GREEN. Multiplier at n = 250: 1.50 for 0 to 4, 1.70, 1.76, 1.83, 1.88, 1.92 for 5 to 9, 2.00 from 10; null for any other n (KR-42).

Desk: x99 = max of the two 99% counts, x975 = max of the two 97.5% counts; `breach_99` = x99 > 12, `breach_975` = x975 > 30 (KR-44); `eligible` = neither. Information outputs P(X <= x99) with p = 0.01 and P(X <= x975) with p = 0.025.

Count: day t is an exception when VaR_t or P&L_t is null, or when -P&L_t > VaR_t (VaR positive for a loss; strict, "exceeds"; KR-45).

## Worked example

250 days, 3 actual exceptions, 5 hypothetical: x = 5. cdf(4) = 0.892188 < 0.95 <= cdf(5) = 0.958817, so amber starts at 5; cdf(9) = 0.999750 < 0.9999 <= cdf(10) = 0.999946, so red starts at 10. Zone AMBER, cumulative probability 95.88% (MAR99 Table 2 row 5), multiplier 1.70. With 500 days the same rule gives amber from 9 and red from 15 (no multiplier is published for 500).

## Operations

| Operation | Inputs | Outputs |
|---|---|---|
| `risk.frtb.backtest.zone` | `observations` (Integer 1 to 1,000,000), `exceptions_actual`, `exceptions_hypothetical` (Integers 0 to n) | `exceptions`, `cumulative_probability`, `zone` (`GREEN` `AMBER` `RED`), `amber_from`, `red_from`, `multiplier` (Real or null) |
| `risk.frtb.backtest.desk` | `observations`, `exceptions_99_actual`, `exceptions_99_hypothetical`, `exceptions_975_actual`, `exceptions_975_hypothetical` | `exceptions_99`, `exceptions_975`, `cumulative_probability_99`, `cumulative_probability_975`, `breach_99`, `breach_975`, `eligible` |
| `risk.frtb.backtest.count` | `var`, `actual`, `hypothetical`: arrays of Real or null, equal length 1 to 100,000 | `observations`, `exceptions_actual`, `exceptions_hypothetical`, `exceptions`, `days_actual`, `days_hypothetical` (0-based indices) |

Probabilities are binary64 (tolerance class `simple_analytic`); counts, zones, flags and the tabulated multiplier compare exactly.

## Errors

Order (HR-122): `E_SCHEMA`, `E_LIMIT` (observations above 1,000,000, checked first in the core, as ruling J-W3-17; an array above 100,000 by the generic cap), the finite rule, structural `E_INPUT`, `E_DOMAIN`.
- `E_DOMAIN`: observations < 1; a count outside 0..observations.
- `E_INPUT` (count): `var` empty; `actual` or `hypothetical` of a different length from `var`.

## Goldens (`datasets/golden/stage_k/btk_k.json` and `tlk_k.json`, generator `oracle/python/gen_stage_k_w1b.py`)

| Cases | Content | Check |
|---|---|---|
| btk_k-0001 to 0012 | zone at 250 for 0 to 10 and 12 exceptions | OUTSIDE (published): MAR99 Table 2 p.758 (cumulative to 2 dp for 0 to 10, zone, multiplier); OUTSIDE (library): `scipy.stats.binom.cdf` within 1e-12 |
| btk_k-0013 to 0018 | max of APL and HPL; n = 500, 100, 1,000, 1, 260 | OUTSIDE (library): SciPy cdf and the 95% / 99.99% boundaries; BLIND: DR-H2 re-derivation MATCH (`program/STAGE_K_BLIND_BTK.md`), counted for every case except btk_k-0017 (n = 1: the rules text states its answer, so it is compared, not counted) |
| btk_k-0019 to 0023 | desk at the limits (12 / 30 eligible, 13, 31), mixed, n = 300 | OUTSIDE (library): SciPy cdf; limits hand (KR-44); BLIND: DR-H2 re-derivation MATCH (`program/STAGE_K_BLIND_BTK.md`), counted |
| btk_k-0024 | exception counting with nulls and a loss equal to VaR | hand; BLIND: DR-H2 re-derivation MATCH (`program/STAGE_K_BLIND_BTK.md`), counted |
| btk_k-0025 to 0038 | 14 error cases, four with two errors | hand |
| btk_k-0039, 0040 | E1 goldens for `risk.frtb.backtest.count` (ruling F-2): a NaN VaR; an Infinity P&L with series of different lengths (two errors, the finite rule first), both `E_DOMAIN`; added at integration 2026-11-19. `zone` and `desk` take Integers only, where a non-finite token is `E_SCHEMA` (not an integer), so they can have no E1 golden: `desk` is listed in `conformance/E1_EXEMPT.json`; `zone` is Integer-only as well (every build rejects even 1.0 there as `E_SCHEMA`, not an integer; checked 2026-11-19), so F-2 ("every Real input is finite") gives it no E1 obligation. It is listed in `conformance/E1_EXEMPT.json` under ruling KR-112 (owner decision 2026-11-19): an exempt operation may carry a Real input only in goldens expecting `E_SCHEMA`, which btk_k-0029 (the JSON float 1.5, refused) does; the gate's planted-fault tests (a) to (d) are in `tools/check_e1_coverage.py --self-test` | hand |
| tlk_k-0001 to 0011 | existing `risk.backtest.traffic_light` at 250, 0.99, 0 to 10 exceptions | OUTSIDE (published): MAR99 Table 2; OUTSIDE (library): SciPy |

## Acceptance (fixed before the goldens were generated)

- KR-41: at 250 observations, for 0 to 10 exceptions the cumulative probability rounded half to even to two decimals in percent equals the MAR99 Table 2 figure, the zone equals the printed zone (amber = `YELLOW` for the stage F operation) and the multiplier equals the printed multiplier; from 10 on the zone is red and the multiplier 2.00. Every value of the new and the existing operation agrees with `scipy.stats.binom.cdf` within 1e-12 relative. Result 2026-11-19: all rows match, for both operations; MAR99 Table 1 (176 printed numbers) also matches SciPy at one decimal.
- Outside share: btk_k 23 of 24 value cases (95.8%, floor 60%; `oracle/OUTSIDE_SHARES.md`, generated by `tools/outside_shares.py`); tlk_k 11 of 11. Counted: the 12 cases checked against the printed MAR99 Table 2 (btk_k-0001 to 0012) and 11 cases re-derived blind by a second model (btk_k-0013 to 0016 and 0018 to 0024; DR-H2, `program/STAGE_K_BLIND_BTK.md`, 12 of 12 MATCH in the first and only compare run, evidence class measured). btk_k-0017 matched too and is not counted, because the rules text states its answer. The SciPy `binom.cdf` checks do not count under D6: stage F's precedent `REIMPL_ROWS = {"SCIPY.BINOM", ...}` classes risk_f4-0082 (`risk.backtest.traffic_light`, the same binomial sum) as `reimplementation`. The 50% (12 of 24) line written before the blind lane ran, and the earlier 96% that counted SciPy, are both superseded (integration 2026-11-19). A blind match shows the rules are unambiguous as written and the arithmetic right; it does not show that KR-44 reads MAR32.19 correctly (KR-44 stays labelled inferred).

## Limits and scope

- Not covered: the PLA test (MAR32.20 to 32.44), the 10% eligibility criterion (MAR32.2), the NMRF exception waiver (MAR32.6), the qualitative add-on (MAR33.44) and capital (MAR33). The desk operation applies MAR32.19 to the counts given; the caller supplies the most recent 12 months (KR-47).
- Literal reading for very small samples (KR-42): for n <= 5, P(X = 0) = 0.99^n >= 0.95, so zero exceptions is amber. The rule is applied as written.
- Tables shared by the four builds: `specifications/06-risk/frtb-ima-backtest-tables.json`.
