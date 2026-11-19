# Stage H rulings, item H-21 paper trading: confirmed 2026-11-18 (HR-42 to HR-55)

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

## Confirmation (2026-11-18, stage H integration lane, maintainer under the owner's delegation)

Checked against plan 12.7 Q8k (TCA and the fill simulator wired into paper trading; the ledger carries TCA per order), the owner's 2026-11-18 H-21 scope (simulated fills, positions, cash, daily P&L explain, risk limits, pre-trade checks, hashed append-only ledger; dashboard stays in stage K) and the standing owner rules (never live orders; zero spend and no card; real data is one crypto venue, labelled). None needs the owner.

| # | Status | Amendment |
|---|---|---|
| HR-42 | Confirmed | none; matches "never live orders" |
| HR-43 | Confirmed, amended | Reports (not ledger records, whose hashed bytes stay as specified) also carry the venue label used elsewhere in stage H: "crypto venue; not equities or rates" |
| HR-44 | Confirmed | none |
| HR-45 | Confirmed | none |
| HR-46 | Confirmed | none; publishing the head hash adds no spend and no account |
| HR-47 | Confirmed | Q8k needs the fill simulator wired in before H-21 is called done; until then H-21 ships as ledger, book and checks only and says so (acceptance A7 open) |
| HR-48 | Confirmed | none |
| HR-49 | Confirmed | none |
| HR-50 | Confirmed | none |
| HR-51 | Confirmed | none |
| HR-52 | Confirmed | none; rates are inputs, no market data purchase |
| HR-53 | Confirmed | none |
| HR-54 | Confirmed | none; matches the owner's 2026-11-18 scope |
| HR-55 | Confirmed, amended | Q8k: every order in a final state has one `TCA` record (`paper-trading.md` "TCA per order", acceptance A7); A7 is part of the acceptance fixed here |

E1 note (maintainer decision 2026-11-18, round 3 integration): `paper.ledger.verify` stays E1-exempt under the existing exemption rule (no Real input; `conformance/E1_EXEMPT.json`). It takes only ledger text, has no numeric or decimal-string input, and reports bad lines as a verify result, not an error. Ruling F-2a's "nothing is exempted" refers only to the decimal-string refinement of the gate and does not remove this exemption.
