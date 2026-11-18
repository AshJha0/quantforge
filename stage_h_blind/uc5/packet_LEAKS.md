# Use case 5 blind packet: leak list (2026-11-18, integration lane)

Built from stage-h (spec text stripped of Expected, Derivation and Check columns by program/stage_h_blind_w2/wave2_extract.awk; uc5 inputs from datasets/golden/stage_h/uc5_h.json, value cases only, no expected outputs).

Removed: the use-case-5 sentence listing the value cases ("lots [334, 333, 333]", "opportunity cost is charged"), replaced by a pointer to uc5_cases.blind.md.

Known residual leaks (judge the comparison with these in mind):
- almgren-chriss.blind.md cites [AC00]'s printed kappa "about 0.6/day" and kappa T "about 3" for parameter set P (a paper figure, two digits; uc5_h-0001 uses P with lambda = 1e-6, so kappa is partly visible).
- (see also the variance leak below) - stage-h-rulings-w1.md header prints E = 562,500 for ac_h-0004 (N = 1; not a uc5 parameter set) and the AC ac_h-0001 linear-case sums are derivable by hand from the eqs. (9)-(11) quoted in almgren-chriss.blind.md (uc5_h-0002 is the linear case: lambda = 0). Formulas are not values, but the linear case is easy to check by hand.
- The packet's spec text is the same text the oracle lane used: a blind lane catches arithmetic and convention slips, not a misreading of the use case (DR-H2 caveat).
- almgren-chriss.blind.md lines 18-19 print the linear-case standard deviation 1.0407e6 on P (the ac_h-0001 caveat). uc5_h-0002 is P with lambda = 0, so its `variance` (= 1.0407e6 squared to 5 digits) is NOT blind; count uc5_h-0002's other outputs only, or strip those lines in a rebuilt packet.
