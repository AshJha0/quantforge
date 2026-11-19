# Notes (btk blind derivation)

MANIFEST.sha256: all 6 files matched.
Method: exact Fraction arithmetic for the binomial cdf (p = 1/100, 1/40); thresholds 95/100 and 9999/10000 compared exactly; float() only at the end.

Ambiguities / assumptions
- btk_k-0013..0018 (spec Formal statement, KR-42): multiplier table indexed by exceptions 0..9 at n=250, 2.00 for >=10; null for n != 250 (0014, 0015, 0016, 0017, 0018).
- btk_k-0017 (KR-42): n=1, cdf(0)=0.99 >= 0.95 so amber_from=0, zone AMBER with 0 exceptions, red_from=1 (0.99 < 0.9999). Applied literally as ruled.
- btk_k-0019, 0023 (KR-44): "more than" for both limits; 0019 has 12 and 30 exactly, so no breach, eligible. 0023: 13>12 and 31>30 both breach.
- btk_k-0021: 975-limit breach from hypothetical count only (max rule).
- Desk probabilities (KR-47): information only, computed at given n (300 for 0023), p=0.01 and p=0.025.
- btk_k-0024 (KR-45): -P&L > VaR strict; null VaR or null P&L is an exception. Day 2 var null -> exception for both series. Boundary days 0.5 vs 0.5 (hyp, day 4) and 1.0 vs 1.0 (actual, day 0) are not exceptions. "exceptions" = max of the two counts.
- No field was non-derivable. Hash file written under two names (blind_results.sha256 per README, results.sha256 per task text).
