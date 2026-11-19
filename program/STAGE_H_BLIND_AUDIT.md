# Stage H audit follow-up: probes and blind packets 3 and 4 (2026-11-19)

Record for the rulings in `specifications/stage-h-rulings-audit.md` (HR-121 to HR-129), ruling HR-120 (SEC compliance dates) and the `exec.sim.fut.run` goldens. Validation is self-assessment; there is no second review (owner decision 2026-11-18). The audit itself is the plan's different-model audit (rule 14.10-5), which the owner approved running on 2026-11-19.

## 1. Probes: what the four builds did before any change

Method: each audit finding was turned into one or more inputs and sent in batch mode to the four command-line builds (Python, Java, C++, Rust), and the four answers were compared. 60 probe cases in three files.

| Finding | Probe | Before | After |
|---|---|---|---|
| HA-3 POV | p = 0.03, v = 97, UNITS | 3 in all four (the snap before the floor was already there) | unchanged, pinned by rule_h-0001 |
| HA-3 close | p_c = 0.57, V_c = 100, UNITS | 57 in all four | unchanged, rule_h-0002 |
| HA-3 pair | C = 1, P_A = 0.3, P_B = 0.2, CASH_BALANCED, UNITS | leg B **1** in all four (binary64 1.4999999999999998 + 0.5 floors to 1); the rule gives 2 | **2** in all four (HR-121), rule_h-0003 |
| HA-1 AC, two errors | N = 0 and sigma = -1 | **Python and Rust E_DOMAIN, Java and C++ E_INPUT** | E_INPUT in all four (HR-122), rule_h-0016 |
| HA-1 POV, two errors | empty `market_volume` and p = 1.5 | E_DOMAIN in all four, against HR-66 | E_INPUT in all four (HR-122), rule_h-0015 |
| HA-1 size limit | 200,000 buckets with a negative quantity, or with NaN | E_LIMIT in all four | unchanged, rule_h-0012, 0013 |
| HA-1 finite rule | NaN quantity and 0 buckets | E_DOMAIN in all four | unchanged, rule_h-0014 |
| HA-5 AC sigma = 0, lambda > 0 | sigma = 0 or 1e-170 | linear trajectory, kappa 0, in all four | unchanged, rule_h-0005 |
| HA-6 arrival | kappa N = 800 | finite slices in all four | unchanged, rule_h-0006, 0007 |
| HA-7 domains | AS sigma < 0, time_left < 0; AC lambda < 0; negative VWAP weight; all-zero profile | E_DOMAIN in all four | unchanged, rule_h |
| HA-7 structure | empty `risk_aversions`; 0 buckets; fractional UNITS quantity | E_INPUT in all four | unchanged, rule_h |
| HA-7 shortfall, no fills | `fills` empty with `benchmark_vwap` | all components 0 except opportunity, in all four | unchanged, rule_h-0008 |
| HA-9 auction | buy 10.00, sell 10.01 | price null, volume 0, both residual, in all four | unchanged, rule_h-0009 |
| HA-11 currency | USDMXN | E_INPUT in all four | unchanged, rule_h |
| HA-12 lot grid | qty 15 with lot 10; display 5; MODIFY 15; MODIFY 0 | E_DOMAIN in all four | unchanged, rule_h |
| HA-13 dark min_qty | lot 10, sell 10 against buy 100, no `min_qty` | fills 10 in all four (the default is one lot) | unchanged, rule_h-0011 |

Also seen in the probes, not an error: Rust leaves out the optional `error.field` on the execution-module errors where the other three builds give it. `cli-contract.md` says `error.field` "is optional and is not compared". Listed as a known difference in the release notes.

## 2. SEC compliance dates (HR-120)

SEC order 34-105656 of 2026-06-11 was read on 2026-11-19 from the PDF at sec.gov (8 pages, text extracted with pypdf). It grants temporary exemptive relief from compliance with Rules 600(b)(89)(i)(F), 610(c) and 612 as amended "until the first business day of November 2027", extending an earlier order that had deferred them to November 2026, and recites that the Commission did not stay the round-lot definition. All four builds used 2025-11-03 for every rule. Fixed in all four; goldens eqc_h-0020 to eqc_h-0027 sit at both sides of each date.

## 3. Blind packets (DR-H2)

A second model (Claude Sonnet 5.5), in a separate context, was given the rules and the inputs only, with no file or web access, and returned its values. It never saw the first lane's numbers. Limit, as in every stage H blind check: the packet's rules were written by the first lane, so a blind match catches arithmetic and convention slips, not a wrong rule.

Packet 3 (14 cases): 14 of 14 agree.

| Packet case | Golden | Blind result |
|---|---|---|
| E1, E2 | eqc_h-0020, 0021 | E_INPUT, E_INPUT |
| E3 | eqc_h-0022 | 10.005 |
| E4 | eqc_h-0023 | cap 0.003, taker_fee 0.0015 |
| E5 | eqc_h-0024 | E_DOMAIN |
| E6, E7, E8 | eqc_h-0025, 0026, 0027 | 40, 100, 40 |
| F1 | fut_h-0011 | fills 110.5 and 110.546875; fees M 3, P 6, N 3; pnl M -143.625, P 134.625, N -3 |
| F2 | fut_h-0012 | fills 120 and 119.96875; X1 rests 1; pnl X 30.75, Y -31.75, Z -0.5, W -0.5 |
| R1 | rule_h-0001 | child 3, filled 3, residual 997 |
| R2 | rule_h-0002 | 57 |
| R3 | rule_h-0003 | leg B 2, imbalance -0.1 |
| R4 | rule_h-0004 | leg B 4, imbalance -0.5 |

Note from the blind lane on R3 and R4: both sit exactly on a half, and half-up and half-even give the same answers here, so these two cases do not tell those two rounding modes apart. They do pin the binary64 fault that HR-121 fixes (R3 was 1 before).

Packet 4 (5 cases): 5 of 5 agree.

| Packet case | Golden | Blind result |
|---|---|---|
| D1 | rule_h-0005 | kappa 0; holdings linear; trades 200,000 each; E 662,500; V 0; objective 662,500 |
| E1 | rule_h-0006 | 1000 - 1.38e-84; 1.38389652673674e-84; 1.91516959671401e-171; 2.65039655300431e-258 |
| E2 | rule_h-0007 | 1000, 0, 0, 0 |
| F1 | rule_h-0008 | delay 0, execution 0, opportunity 1000, total 1000, 100 bp, vwap_slippage 0 |
| G1 | rule_h-0009 | V = 0 at both candidates; no auction; price null; both orders residual |

Not in any packet, hand only: fut_h-0013 (no events), rule_h-0010 (MODIFY of an unknown id), rule_h-0011 (dark `min_qty` default), and every error case.

## 4. Shares after these changes

From `oracle/OUTSIDE_SHARES.md`: stage H 160 of 205 value cases (78.0%); H-22 20 of 30 (66.7%); H-24 18 of 19 (94.7%). `rule_h` is not mapped to a plan item (cross-item cases), as `acls_h` is not.
