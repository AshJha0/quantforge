# Notes (blind derivation, packet simm_packet)

MANIFEST.sha256: all six files matched their hashes.
Nothing outside the packet and this folder was read. No outside knowledge of real margin models was used; all constants from tables/simm-placeholder.json.
All 29 cases derived; no field is "not derivable".

## Ambiguities / assumptions
1. File names: README says blind_results.json / blind_results.sha256; the task brief says results.sha256. Both hash files written (same hash). Results JSON is blind_results.json.
2. `label` (spec Outputs, KR-130) is not in output_template results_skeleton; I followed the skeleton and omitted it (all cases).
3. Skeleton keys are reproduced exactly; shape checked by script (no missing/extra keys). Case 17 `buckets` is `{}`; case 27 (net zero) has ws 0, cr 1, k_b 0 (spec step 2: CR=1 at zero sum).
4. Single-bucket margin: M = sqrt(K_b^2 + 0) = K_b (spec step 5, FX note). All cases.
5. IR/EQ vega concentration: group = currency (IR) / issuer (EQ); EQ vega group sum is over the issuer's net across expiries (spec step 1-2). Case 22.
6. EQ vega within-bucket rho: bucket EQ rho between different issuers (spec step 4, "vega correlations equal delta"); EQ vega factors are issuers, so no tenor rho. Curvature uses rho^2 (and gamma^2) likewise. Case 22 has only one factor per bucket, so rho is untested.
7. CVR for EQ vega: SF(t) x amount summed per issuer over expiries, t from tenor days (1W 7, 1Y 365). Case 22.
8. Product class label only groups: IR_DELTA under Equity (cases 25, 26) treated as ordinary IR; psi 0.2 between present risk classes (case 26: IR, FX, EQ all pairs).
9. Case 25: same IR factor in two product classes does not net (KR-132); each product class computed alone, total = sum.
10. Case 29: calculation currency EUR, FX qualifier USD; not equal to calculation currency, so valid; FX cr group key USD.
11. Curvature present exactly when vega present (spec Outputs); sum_cvr/theta/lambda included only when non-residual factors exist (case 22 has both parts).
12. theta = min(sum/sum abs, 0); lambda = (z^2-1)(1+theta)-theta; z from table. No 0/0 case occurs.
13. Hand checks done: case 1 (60), case 4 (sqrt(12400)), case 22 curvature (C_non 60, C_res 20, curvature 80).
