# Caps, floors and swaptions on flat or quoted vol

Spec version 1.0.0. Status: Specified (stage D, D7).

Index `USD-TERM-3M` on the stage B curves: `discount` (OIS) and `projection`. `spot = add_business_days(as_of, 2)` on `USGS`; schedules by `02-curves/schedules.md` with `MODIFIED_FOLLOWING`, no end-of-month. Option formulas are `black-models.md` (`BLACK_76` or `BACHELIER`, undiscounted, vols as ruling C7); time to expiry `t = (fixing - as_of)/365`.

## `rates.cap.price`

Inputs: `discount`, `projection`, `model`, `vol` (one number, or a list with one vol per caplet: quoted vol), `trade` `{type, start_months, tenor_months, strike, notional}`, `type` `CAP` or `FLOOR`. `start = adjust(spot + start_months)`; quarterly periods `(a_i, e_i)` from `start` to `start + tenor_months`.

Caplet `i`: `alpha = ACT_360(a_i, e_i)`, `F = (P(a_i)/P(e_i) - 1)/alpha`, fixing at `a_i` (no fixing lag, ruling D28), paid at `e_i`: `N alpha D(e_i) option(F, K, vol_i, t(a_i))`, call for caps, put for floors. Outputs: `caplets`, `price` (their sum, in order).

Checks, in order: `start_months < 1`: `E_INPUT`. A vol list of the wrong length: `E_INPUT`. A vol `< 0`: `E_DOMAIN`. `BLACK_76` with `strike <= 0` or a forward `<= 0`: `E_DOMAIN`.

## `rates.swaption.price`

European, physically settled, on the stage B swap (`projection-and-fra.md`): fixed annual `THIRTY_360_BOND`, floating quarterly. Inputs: `discount`, `projection`, `model`, `vol` (a number), `trade` `{type, expiry_months, tenor_months, strike, notional}`, `type` `PAYER` or `RECEIVER`. The swap starts at `s = adjust(spot + expiry_months)` and runs `tenor_months`; exercise is at `s` (ruling D28).

`annuity A = sum alpha_j D(e_j)` over fixed periods, `forward_rate = sum (P(s_k)/P(e_k) - 1) D(e_k) / A` over floating periods, `price = N A option(forward_rate, K, vol, (s - as_of)/365)`, call for payers. Outputs: `price`, `forward_rate`, `annuity`. `expiry_months < 1`: `E_INPUT`; other checks as caps.

## Acceptance

1e-9 per unit notional. Option values agree with QuantLib `blackFormula` and `bachelierBlackFormula`; curves and schedules are checked in stage B. Suite `stage_d/capswaption_d`.
