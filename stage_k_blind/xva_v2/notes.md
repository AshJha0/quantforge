# Blind lane notes (ambiguities and resolutions)

1. t_0 = 0 for xva.adjustments.value, funding, MVA, WWR, portfolio CVA buckets (times given start above 0; spec says "from t_0 = 0").
2. Survival weights: bucket START for FCA/FBA/MVA/ColVA (KR-296/297, spec text), start for DVA/CVA first-to-default weight per G-41.
3. Overlap (G-41, aadx_k-0002): s_l -> max(s_l - h_b(1-R_b), 0); gradient taken on the active branch (0.002 > 0). Own hazard/recovery enter through it as well as DVA/survival.
4. Curves (KR-164): s*T linear in T, origin (0,0) before first pillar, so the forward before the first pillar equals the first spread. Beyond the last pillar I continued the last segment's slope (flat forward); no case uses it (all times <= last pillar, or single pillar 5.0 with times <= 2).
5. xva.mva.value with borrow_curve: f_b from curve (mva_k-0005). NORMAL_MPOR days_per_year default 250, z = Phi^-1(0.99) at 60 digits.
6. REGRESSION IM: LS by QR on 1,x,..,x^n; IM_p = z sqrt(max(fit - mean(X)^2, 0)); expected_im = path mean. Order 0 = population variance.
7. ColVA path form: G-40 on summed trade values (paths x dates), IA absent = 0, MTA test |T-K_prev| >= MTA, C_i = K_max(i-l,0); profile = path mean for i=0..n-1.
8. xva.exposure.closeout (clp_k-0001): IM lagged as IM(t_max(i-l,0)); ene = min(V - C, 0) (no im_posted; IM received never offsets ENE); pfe = ceil(qP)-th smallest E (idx 3 of 4); epe = sum_{i>=1} ee_i dt / (t_n - t_0); effective_epe divides by (last grid point within 1y - t_0) = 1.
9. aadx_k-0008: CVA = (1-R) sum dee_i (e^{-h t_{i-1}} - e^{-h t_i}), t_0=0, t_i = exposure_times, discounted EE from fixed_inputs.json.
10. Stressed EEPE: T* = min(1, maturity) when maturity < 1; sum over grid points t_k <= T*, k >= 1, divided by T*; eee lists are full length. Tie -> current. alpha default 1.4. ead_used follows the portfolio calibration.
11. WWR: P(Z>a, U<=beta) and E[Z 1{...}] computed by 1-D quadrature of phi(z)Phi((beta-cz)/r) (and z times it) from a to max(a,0)+26, mp.quad at 60 digits (not the Phi_2 / closed-form identity). beta_i = Phi^-1(PD(t_i)) via erfinv; beta_0 = -inf (G = 0). cva_independent = same code with rho = 0.
12. shocked curve: applied_bp linear interpolation on scenario tenors, flat outside, scale 1; DF = exp(-z' T); inputs used as given binary64. The template has no cva/ee outputs for shk cases (curve outputs only), so none computed.
13. mpor_days: integers written (floor_days, mpor_days); binding = true when model days <= floor (tie treated as floor used; no tie in the case).
14. Gradients: 4th-order central difference at 60 digits, step 1e-11 * max(1,|x|) (error well below 1e-30). Inputs equal to 0 (none that matter) use absolute step. aadx_k-0007 d/dv0 = 0 exactly (v0 > H so VM absorbs v0; m = H - im).
15. Unspecified: no leaves left null. Script runtime about 4.5 minutes (WWR quadrature dominates).
