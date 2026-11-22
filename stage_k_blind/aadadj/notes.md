# Notes
MANIFEST.sha256: all five files matched.
Method: G-41 formulas in mpmath at 60 digits with per-bucket hazard vectors. Each gradient entry is the KR-265 Richardson
bump (4D(d/2)-D(d))/3, d=1e-12 max(1,|x|), applied to the binary64 inputs read as exact. The flat hazard entry shifts every bucket
together (floor included). Bucket entries shift one bucket's hazard (own bucket also moves that bucket's floor).
Overlap branch is decided once in binary64 (x = s_l - h_b(1-R_b) >= 0 is linear) and held fixed during bumps.
No closed-form adjoint was written, so there is no cross-check against one. Sanity check: the flat entry equals the sum of the bucket entries.
Outputs are rounded once to binary64.
Ambiguities: (1) Template lists mva/kva gradient keys with all keys, so every key was computed for every output. (2) wrt cases (k-0011) follow the
template's reduced keys. (3) With exclude_dva_overlap false, s_l' = s_l, no hazard dependence. (4) h=0 and ee=ene=0 handled by the
analytic formula's central bump (negative hazards allowed in the bump).
