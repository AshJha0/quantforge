# Notes (blind K-8 derivation)

Model: Sonnet 5.5. numpy 2.4.6 used. MANIFEST.sha256 checked: all 8 files matched. Nothing outside the packet and this folder was read.
Implementation: `blind_ref.py` (forward-mode dual numbers, 12 directions: 10 DFs, a, sigma; branch decisions on binary64 values). Run `python blind_ref.py`. Results from a clean run of that script.

## Self-checks (selfcheck.py / selfcheck.log)
- Q(s) formula vs textbook Hull-White bond times D(t), forward rate free: agree exactly (rel diff 0).
- k8_k-0006 (single exercise = European) vs my own Gaussian quadrature (tilted OU law, E[exp(-Y)] = exp(c2 I)): grid errors -3.05e-3, -7.6e-4, -1.91e-4, -1.87e-4 (nx/spy 101/50, 201/100, 401/200, 401/400): second order, converges to the closed-form-style value 7039.32.
- Case 1 price under refinement (41/20, 101/50, 201/100): 22287.5, 22678.3, 22737.4; ladder entries move similarly, converging.
- Ladder vs my own central bump (rel 1e-6) on case 5: relative differences <= 5e-9 for all 12 entries; zero entries are exactly 0.
- Zero ladder entries (nodes 0, 6..9) follow the step-7 weight rule: nodes at 0.4986, 10.005, 15.011, 20.014, 30.019 are 0.

## Ambiguities / choices
1. Step 5 end correction: "rho (1 - rho)(2 rho - 1)/12 x (d_j + d_(j+1))/2": I read "x" as a multiplication sign (units: h is in f units), NOT the node coordinate x_j. If the node coordinate was meant, price changes about 1e-5 (case 5) and 5e-5 (case 7) relative, i.e. far above tolerance. Affects all cases with a crossing (all). Please state it unambiguously.
2. Step 4 CN explicit side: "(I - (dt/2) A) U_old on interior nodes" does not say whether A is applied with the boundary-substituted rows or with the stored boundary values of U_old. I used the substituted rows (same operator on both sides). I also ran the literal version: prices and d_a identical to all printed digits on cases 5 and 7, so the choice appears immaterial here.
3. Half steps: each of the four implicit half steps has size dt/2 (matrix I + (dt/2)A, RHS = U_old), so the CN and half-step LHS matrices coincide. "First two steps" of every interval, including [0, t_1], and all steps if n < 2.
4. Smoothing is applied at t_m with U = 0 and at each earlier exercise date, not at 0. f_i uses all nodes including the boundary values as stored (after the linear-extrapolation set); after smoothing U's two end nodes are Ehat + h (not linearly extrapolated) but only interior values enter the next solve.
5. Payments after t: strictly greater than t; tau_1 = T_first_after - t, then successive differences.
6. ln P interpolation: at a node time return the node value; inside a segment lerp with weight (s - t_k)/(t_(k+1) - t_k); beyond last pillar use last segment line. Form of the weight is rounding-level only.
7. M(p,q): branch order as written (first case p>=0 and q>=0), so p=0,q<0 gives 0.
8. Grid: x_i = -h + i*dx exactly as written (centre node not exactly 0 in binary64); the derivative goes through it. The case's `price` is notional x U; ladder entries are scaled by notional too.
9. Smoothing end-correction loop uses the original f (and original second differences d), with h updated sequentially; d at end nodes is 0.
10. Case ids k8_k-0004/6/7 are swaption cases: price only.
No field was "not derivable".
