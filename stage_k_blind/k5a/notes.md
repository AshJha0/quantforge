# Notes (K-5a blind)
MANIFEST.sha256: all 5 files matched.
Rules read: specs sec. risk.intraday.delta_gamma_bound; rulings KR-7/10/15/17; template.
Formulas: V=N e^{-yT}; estimate per position = V(-T h) + V T^2 h^2/2; bound per position = |h|^3 T^3 |N| e^{-T min(y,y+h)}/6.
Assumptions (all cases):
1. Estimate summed with math.fsum (exactly rounded) -- spec only mandates this for bound (KR-17); same choice for estimate is mine. Affects idr_k-0005 only (2 positions); single-position cases unaffected.
2. Per-position terms computed in plain binary64 (V first, then V*(-T*h) + V*T^2*h^2/2); KR-17 says "evaluated in binary64" without fixing operation order, so last-bit differences (~1e-16 rel) are possible. All cases.
3. Label: KR-10 text "latency-aware analytics on simulated data" used verbatim; inputs are treated as simulated (no data provenance in packet). All cases.
4. Short position (case 5, N=-5e5): KR-15 abs(N) used; estimate keeps sign of N.
5. No field was non-derivable. Sanity check (not output): |estimate - exact revaluation| <= bound in all 5 cases. Hand-checked cases 1 and 2.
Hash file: written as results.sha256 (task) and blind_results.sha256 (README) with identical content.
