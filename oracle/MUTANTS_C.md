# Stage C wrong-convention checks

Written by `gen_stage_c.py`. The run stops if a suite's tolerance lets one through. Gap is the size of the error at the case that shows it.

| Suite | Wrong convention | Gap |
|---|---|---|
| equity_forward | dividends discounted on r, not r-b (97.064) | 4.913e-02 |
| equity_forward | dividend on expiry dropped | 1.000e+00 |
| equity_forward | borrow ignored | 1.014e+00 |
| equity_forward | ACT/360 time | 1.042e+00 |
| equity_forward | parity mean forgets the discount factor | 7.747e-02 |
| black_deep | price not discounted | 5.419e-01 |
| black_deep | CALL and PUT swapped | 3.992e+01 |
| black_deep | time scaled wrongly | 5.702e+00 |
| black_deep | lognormal vol fed to Bachelier | 2.655e+01 |
| equity_forward_deep | dividends discounted on r in the option forward | 4.234e-02 |
| equity_forward_deep | delta against forward, not spot | 1.097e-02 |
| greeks | vega per vol point | 3.833e+01 |
| greeks | theta per day | 4.741e+00 |
| greeks | delta without the yield factor | 5.764e-03 |
| greeks | rho per point | 4.804e+01 |
| greeks | Black-76 delta left undiscounted | 1.500e-02 |
| smile | spot delta read as forward delta | 5.313e-01 |
| smile | ATM forward taken for delta neutral | 2.020e+00 |
| smile | risk reversal sign | 4.000e-02 |
| smile | SVI rho sign flipped | 3.192e-02 |
| smile | SSVI phi without the (1+theta) term | 7.098e-04 |
| surface | vol, not total variance, linear in time | 2.451e-03 |
| surface | k from spot, not forward (F/S 1.03) | 6.355e-04 |
| surface | bucket vega per vol point | 3.448e+02 |
| sabr | rho and nu swapped (QuantLib argument order) | 2.083e-01 |
| sabr | expansion term in T dropped | 3.794e-02 |
| sabr | shift ignored | 3.140e-01 |
| sabr | beta 0.5 fitted as beta 1 misses the quotes | 1.333e-03 |
| sabr_deep | sign of the time term in M flipped | 5.463e-03 |
| sabr_deep | reflecting, not absorbing, floor (no mass absorbed) | 3.360e-01 |
