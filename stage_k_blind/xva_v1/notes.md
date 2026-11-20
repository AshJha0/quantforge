# Blind derivation notes (xva_v1)
Method: blind_ref.py, mpmath at 60 digits, rounded to binary64 at the end. MANIFEST verified OK.
Phi^-1 via erfinv. REGRESSION: normal equations in 60-digit arithmetic (equivalent to QR); IM_p = z * sqrt(max(fit_p - mean(X)^2, 0)); expected_im = path mean.

## Null outputs
- aadx_k-0001 (all five): needs the xvaadj_g-0001 inputs and the xva.adjustments.value formulas (stage G), which are not in the packet.
- fva_k-0003 fca/fba: inputs are xvaadj_g-0001 (not in packet).
- fva_k-0006 fca: the rule says FCA = 0 because ee is all zero, but the buckets/curves come from fva_k-0004 and xvaadj_g-0001, which are not in the packet. Under any inputs FCA = 0 exactly (ee = 0), so 0.0 is arguably derivable; I left null rather than assume the case is well formed.

## Ambiguities and resolutions
- fva: FCA/FBA survival uses t_(i-1) (formal statement), D_i at bucket end. fva_k-0001 at t_0 = 0 has S = 1 in bucket 1.
- Curve interpolation: linear in s*T between pillars; beyond last pillar "flat forward" was implemented as extending the last segment's slope of s*T (for a single pillar, slope = s*T/T). Not used by any computed case (cases 0001/0002 stay within pillars).
- fva_k-0002: overlap rule f_l' = max(f_l - h_B(1-R_B),0) with R_B=0.6 (R_C stays 0.4, unused). Bucket 1 binds (0.004-0.004=0).
- mva: formula has f_b,i - s_I with flat borrow_spread 0.008; S_C(t_i)S_B(t_i) at bucket END t_i (differs from fva), delta_i = t_i - t_(i-1) with t_0=0. NORMAL_MPOR uses sqrt(10/250), q=0.99.
- colva_k-0003: collateral_floor is negative (= -sum C max(-r,0)...), as the formula reads; colva equals 0001 (floor not added). Case implicitly uses NONE.
- str: sum over k>=1 with t_k <= T*; alpha 1.4 default; ties go to current. str_k-0004: maturity 0.5 is a grid point, T*=0.5, eee=(10,12,12) -> 12 and 15.
- mpor_k-0006: F=10 -> 20 (illiquid) -> 40 (3 disputes > 2); floor 42; binding true (42 > 15).
