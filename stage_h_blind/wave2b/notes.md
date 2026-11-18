# Blind lane w2b notes (ambiguities and chosen interpretation)

Output shapes are mine where the spec gives none; decimals are normalised (no exponent, no trailing zeros, "0" for zero) everywhere, including paper cash.

dark
- Declined conditional (0004 scenario 2): the suspension blocks the conditional immediately in the same event (scan repeats), recorded as from_event = event+1 .. event+penalty. It re-invites at event 6 (suspension 4-5 over), declined again, suspended 7-8.
- Invitation `id` = the conditional order; `contra_id` = its counterparty. Firm S1 gets no invitation.
- dark_h-0007 output shape: {"fills":[{"markouts_bp":{h:value}}]}, same order as input.
- Locked book (bid == ask, 0003 last event) = no mid, no crossing.

sor
- All numbers (M, L entries) are decimal strings; ranking entries {M, L, expected_cost}, full 6dp-rounded cost, ordered by exact cost then tuple.
- Dark draw distribution from tail: P(s=k) = T(k) - T(k+1), T(0) = 1.
- Expectation over lit rows x dark outcomes (product, independent).

paper (output shapes invented)
- Rates absent in 0002: financing taken as 0 (no cash_rate given).
- 0005 has no starting cash: output cash_delta (+270) instead of cash.
- 0010..0017: P_ref 100, cash 10000, n 0, today 0 unless stated; 0015/0016 use the 0010 order (BUY LIMIT 3 @ 101).
- 0011 reasons: MAX_QTY, MAX_NOTIONAL (1100 > 1000), MAX_POSITION (11 > 5).
- 0018 output {"error":"E_UNSUPPORTED_OPERATION"}.
- Ledger: record field `hash` excluded from canonical bytes; 0021 verify records = 1; 0022 second record invented (seq 1, ts ...:02Z, body order O2) with prev zeros, so only LINK fails; 0023 verify check order SEQ, HASH, LINK, LABEL (hash recomputed so LABEL fires).
