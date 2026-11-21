# K-8i blind notes
Read: README.md, specs/leverage-large-exposures.blind.md (Formal statement), rulings/k8i.blind.md (KR-51,53,65,66,319,320,322-326), tables/*.json, inputs/k8i.inputs.json.
Method: Fractions of the binary64 inputs, constants as exact decimals (1.4=7/5, CCFs), one rounding via float(); comparisons in binary64.

1. All cases: numbers emitted as floats (e.g. 40.0), not ints; zero as 0.0.
2. All leverage: 1.4 and 0.03 taken as exact decimals (tables give decimal strings); 1.4 is NOT the binary64 1.4 inside the exact sum. Possible 1-ulp difference vs a float-1.4 implementation (lev_k-0001..0003).
3. meets_minimum: `float(tier1) >= 0.03 * float(exposure)` (binary64, spec). None of the cases are near the boundary (lev_k-0002 ratio 0.0185 false; others clearly true).
4. lev_k-0004/0005: written CDS effective notional goes into `derivatives` (KR-320); netting-set part 0. fair_value -10 -> 90; fair_value +5 -> max(0,-5)=0 -> 100.
5. lev_k-0012: missing cvm_received/purchased_offset default 0 (KR-319). RC=max(-20+5,0)=0, set = 1.4*10=14; WCD 16+0 (second: 10-12<0 floored 0). off_balance 10+10+10+5+2=37. Exposure 107.
6. lev_k-0013: omitted on_balance/derivatives/wcd/off_balance are empty (KR-319). First SFT (gross 0, no mna, empty lists) contributes 0. Second 30+max(0,10-4)=36. Non-MNA lists of unequal length unspecified; not exercised (I pair by index, missing collateral = 0).
7. lex_k-0008: no bank_gsib -> false -> 0.25*1000=250 limit for all. Large threshold 0.10*1000=100. GX = X(200, exempt)+Y(100)=300, large, breach compares non-exempt sum 100 <= 250 -> false, exempt false (not all). Z 400 exempt: large true, breach false, exempt true, own group "Z". Groups in code-point order (GX, N00..N22, Z). Report = large groups plus 20 largest (union, KR-326 order exposure desc, ties by label): Z, GX, N22..N05 (20 entries).
   Ambiguity: "large groups plus the 20 largest" read as union (not 20 + large extras counted separately); here both readings coincide.
8. lex_k-0009: KR-323 long if notional>=0: c1 (notional 0) long, JTD = market value 3. JTD = market value (LGD 1; notional + (mv - notional)).
   P offset (KR-53): shorts by descending rank: s1 SENIOR(3) 14 uses longs rank>=3: b1 COVERED(4) 21 -> 7 left. s2 EQUITY(1) 40 uses ascending longs: b2 NON_SENIOR 25 -> 0, b1 7 -> 0; 8 unmatched short. Net long 0, net short -8. Short stored as negative value per README.
   R: off_balance 100*max(0.5,0.1)=50; CRM protected 20 on R, provider Q receives 20: R=50-20=30, Q=3+20=23, P=0. `protected` and `received` reported per counterparty accordingly.
   Group GP limit 0.15*400=60 (bank_gsib true and member P gsib, KR-324 "any member"); R limit 100. Large threshold 40: none large. Report: all groups (<=20) by exposure desc: R, GP.
   Group label "R" equals counterparty id R, which is in that group (allowed, KR-324).
9. `members` lists ids in input order; group `exempt` = all members exempt.
