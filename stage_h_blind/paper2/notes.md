# Blind lane notes (paper2)
Manifest verified before reading. Cases: 0030,0031,0032,0050,0051,0054.
- 0054: duplicate key "kind" -> PARSE at line 0 (HR-78); records 0, head null. Output carries label (CLI contract).
- Outputs of 0050/0051 carry `label`; 0051 has no cash -> cash_delta -5; avg_cost 5/3 half-even 18 dp. 0050: exact decimals, result 31 digits, in range.
- 0030/0031 lit replay: assumed taker walk of asks up to the limit; fee = taker_fee*q*p per level; FILL child_id for LIT assumed = order_id (spec gives no value). Venue string "LIT".
- Intraday position/cash included in pre-trade of step 2 (position 3 + 3 > 5 gives MAX_POSITION; 106 vs mid 100 gives PRICE_BAND). Rejected orders count in orders_today.
- REJECT body: order incl. venue (only `mode` removed) + reasons; ORDER body adds decision_price (mid 100).
- CLOSE with no cash_rate/debit_rate: default 0 assumed; session starts flat so market=0; nav = cash + positions*marks (cash opening = session cash); interest on opening cash.
- TCA binary64 order as stated; total_bps repr "76.73333333333333".
- 0032 (SOR + dark): SPEC NOT IN PACKET (exec.sor.allocate, dark sim, tail/theta/lambda semantics, contra). GUESSED: lit child takes top ask level (1@100.5, taker fee 0.1005), dark child gets the remainder at snapshot mid 100, fee 0, capped by FIRM contra; child_ids "P1-LIT"/"P1-DARK" invented; no CANCEL. Treat 0032 as low confidence.
- results step for SUBMIT: {status, filled} only; results output also has records/head/positions/cash/label/ceiling.
