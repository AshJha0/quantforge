# R1 rulings

Rulings by the spec session in phase R1, from the R5 stage D audit (`R5_STAGE_D_AUDIT.md` section 1, outside the repo). Normative. Goldens: suite `stage_d/rulings_r1`, written by `oracle/python/gen_r1_rulings.py`.

| # | Point | Ruling |
|---|---|---|
| R1-1 | Cross-currency swap (D17) | `fx.xccy.*` is a synthetic constant-notional basis swap, not the market MTM-reset EUR/USD instrument. The text says so; no value changes. The MTM-reset variant is edge-case register row E13, out of scope until stage F |
| R1-2 | ESTR payment lag (D1) | Lag 2 stays, and is labelled a library choice (Strata 2.12.78), not a market standard. TP ICAP terms use 1. Changing it would move every ESTR golden for no confirmed gain; revisit if the ECB working group or LCH publish a definitive convention. No value changes |
| R1-3 | Conversion factor | Optional input `contract`; `null` keeps the stage D behaviour (`TEN_YEAR`). 2Y, 3Y and 5Y contracts count whole months; the others round down to a multiple of 3. The coupon is rounded to the nearest 1/8 of 1%, ties up, first. `v = z - 6` for `z >= 7`, which equals the old `v = 3` whenever `z` is a multiple of 3. CME states 4 decimals and no tie rule, so the "half-even" claim is withdrawn; no golden sits near a boundary. Every existing golden keeps its value (all its coupons are on the 1/8 grid) |
| R1-4 | CDS discount curve | Every `credit.*` operation requires `discount.interpolation` `LOG_LINEAR_DF` (ISDA flat forwards); anything else is `E_INPUT`, checked before every other rule check. Every existing golden already uses `LOG_LINEAR_DF` |
| R1-5 | Caps and swaptions | The conventions are labelled stylised: synthetic term index, no fixing lag, annual 30/360 fixed leg. No value changes |
