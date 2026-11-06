# Stage B mutants

Written by `oracle/python/gen_stage_b_deep.py`. Each row is one deliberate mistake; the gap is how far it lands from the golden, and the run stops if a gap is inside tolerance. Date mutants count differing cases.

| Suite | Mutant | Gap |
|---|---|---|
| `schedule_deep` | generate forward, stub last | 36 |
| `schedule_deep` | FOLLOWING in place of MODIFIED_FOLLOWING | 12 |
| `curve_deep` | ACT/360 curve time | 0.000631 |
| `curve_deep` | linear in discount factor | 0.0613 |
| `curve_deep` | flat zero rate beyond the last pillar | 0.0132 |
| `ois_deep` | payment lag ignored | 2.84e-05 |
| `ois_deep` | spot lag ignored | 6.16e-05 |
| `ois_deep` | ACT_365F on the fixed leg | 0.00494 |
| `ois_deep` | FOLLOWING before counting the spot lag | 2 |
| `ois_deep` | telescoped floating leg under a payment lag | 113 |
| `projection_deep` | discounting on the projection curve | 5.15 |
| `projection_deep` | ACT_360 on the fixed leg | 0.00378 |
| `projection_deep` | FRA without the settlement discount | 19.8 |
| `risk_deep` | one-sided bump | 0.964 |
| `risk_deep` | bump of 1 bp reported per 100 bp | 1.04e+05 |
| `risk_deep` | sign flipped | 2.09e+03 |
| `fx_deep` | spot date on one calendar | 3 |
| `fx_deep` | curves not measured from spot | 27.6 |
| `fx_deep` | ratio inverted | 0.00512 |
| `fx_deep` | delta left undiscounted | 3.62e+04 |
| `hedge_deep` | weights ignored | 6.03 |
| `hedge_deep` | cost ignored | 45.8 |
| `hedge_deep` | sign of b reversed | 63.3 |
