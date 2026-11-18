# Stage H rulings, item H-21 paper trading: PROPOSED 2026-11-18

Drafted 2026-11-18 on branch `h21-paper`. Not normative until the stage H coordinator confirms them. Separate file so branches merge without conflict; numbering continues from HR-41. Covers `10-execution/paper-trading.md`. Append-only once confirmed.

| # | Point | Proposed ruling |
|---|---|---|
| HR-42 | Live orders | Never. No network or order-entry code in the paper modules; `mode` other than `"simulated"` is `E_UNSUPPORTED_OPERATION`; a static test enforces it |
| HR-43 | Label | Every ledger record and report carries `"crypto venue; simulated"` and the 11.6 honest-ceiling sentence; a record without the label fails `verify` |
| HR-44 | Numbers | Decimal strings everywhere; exact decimal arithmetic; only financing postings are rounded (half-even, cash precision) |
| HR-45 | Canonical bytes | Sorted keys, `,`/`:` separators, ASCII with `\uXXXX`, only `seq` as an integer; SHA-256 lowercase hex; a stated subset, not RFC 8785 |
| HR-46 | Ledger home | JSON Lines appended in `forward-log`; the head hash is published daily in the commit message so truncation of the tail is detectable; never rewritten |
| HR-47 | Fill source | Lit, dark and SOR simulators of this folder seeded with the recorded form B snapshot at the order time; no permanent impact on recorded data (stated limitation) |
| HR-48 | Resting orders | Cancelled at the daily close (00:00 UTC); no GTC carry-over in paper |
| HR-49 | Risk limits | KILL_SWITCH, MAX_ORDERS, MAX_QTY, PRICE_BAND, MAX_NOTIONAL, MAX_POSITION, NO_SHORT, INSUFFICIENT_CASH; all evaluated, reported in that order; MARKET checked at P_ref (1 + s band); a rejection is a ledger record, not an error |
| HR-50 | Cost method | Average cost; fees outside cost and realised; crossing zero opens the remainder at the fill price |
| HR-51 | Close | Mid of the recorded snapshot at 00:00:00 UTC |
| HR-52 | Financing | ACT/365 on opening balances: cash at `cash_rate` or `debit_rate`, shorts at `borrow_rate` on opening market value; posted end of day |
| HR-53 | Explain | market + trading + fees + financing equals the NAV change exactly; no residual term |
| HR-54 | Dashboard | Out of H-21; stays in stage K |
| HR-55 | Acceptance | A1 to A8 and goldens pt_h-0001..0023 fixed in this commit before any paper run; goldens go to a blind lane (DR-H2) before they count as outside-checked; pt_h-0020's hash is checked by `sha256sum` |
