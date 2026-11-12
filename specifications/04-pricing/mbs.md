# MBS prepayment and pass-through pricing

Spec version 1.0.0. Status: Specified (stage D, D9).

## Pool

`pool`: `{balance, wac, net_coupon, wam, age, prepayment}`. `wam` is the remaining term in months (`>= 1`), `age` the loan age in months at the start (`>= 0`). `prepayment`: `{model: "CPR", rate}` or `{model: "PSA", speed}`.

For month `k = 1 .. wam`, with beginning balance `B_k` (`B_1 = balance`), `r = wac/12`, `n = wam - k + 1`:

- `CPR_k = rate`, or for PSA `min((age + k)/30, 1) * 0.06 * speed/100`
- `SMM_k = 1 - (1 - CPR_k)^(1/12)`
- scheduled payment `B_k r / (1 - (1 + r)^(-n))`; `scheduled_principal_k` = that less `B_k r`
- `prepayment_k = SMM_k (B_k - scheduled_principal_k)`
- `interest_k = B_k net_coupon / 12` (to the investor)
- `B_{k+1} = B_k - scheduled_principal_k - prepayment_k`

The last month's scheduled principal is the whole balance.

## `mbs.cashflows`

Input: `pool`. Outputs: `balance` (`B_k`), `interest`, `scheduled_principal`, `prepayment` (each `wam` long), `wal = sum (k/12)(scheduled_principal_k + prepayment_k) / balance`.

Checks, in order (ruling D44): `wam` outside 1 to 1200, or `age < 0`: `E_INPUT`. `wac <= 0`: `E_DOMAIN`. `net_coupon > wac`: `E_INPUT`. `balance <= 0`, `rate` outside `[0, 1)`, `speed < 0`: `E_DOMAIN`. For PSA, a monthly `CPR_k >= 1` in any month `k = 1 .. wam` is `E_DOMAIN` (ruling R6-7.1): `1 - CPR` would be zero or negative and its twelfth root undefined (until v0.8.0 Python returned complex numbers and Rust NaN above about PSA 1667). Checked after the checks above, before any cash flow. In `mbs.price`, `1 + y/12 <= 0`: `E_DOMAIN`.

## `mbs.price`

Inputs: `pool`, `yield` `y` (monthly compounding), `delay_days` (integer `>= 0`, else `E_INPUT`). Month `k`'s cash flow `CF_k = interest_k + scheduled_principal_k + prepayment_k` is discounted at `v^(t_k)`, `v = 1/(1 + y/12)`, `t_k = k + delay_days/30`. **`delay_days`** (ruling R6-7.6) is the number of days from the end of month `k`'s accrual period to its payment, on a 30-day month: the agency "stated delay" less 30. For example a stated delay of 55 days (the usual Fannie Mae pass-through figure, from memory, not opened) is `delay_days = 25`; `0` pays at the end of the accrual month. It moves only the discounting time, never the cash flow. Outputs: `price = 100 sum CF_k v^(t_k) / balance`, `modified_duration = sum (t_k/12) CF_k v^(t_k + 1) / sum CF_k v^(t_k)`, `wal`.

## Acceptance

`simple_analytic`, widened for long pools to 1e-9 per unit balance plus 1e-10 relative. Analytic, by the standard PSA and level-pay formulas; no outside library is run. Suite `stage_d/mbs_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] SIFMA, *Uniform Practices for the Clearance and Settlement of Mortgage-Backed Securities and Other Related Securities*, Chapter SF, *Standard Formulas* (PSA prepayment benchmark, SMM from CPR, level-pay amortisation) (not opened)
- [S2] Fabozzi, F. J. (ed.), *The Handbook of Mortgage-Backed Securities*, 7th ed., Oxford University Press, 2016 (not opened)
