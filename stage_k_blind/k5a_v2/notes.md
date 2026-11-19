# Notes (K-5a v2 blind)
Manifest check: all 5 files OK.
Read only the packet folder and this folder.

Arithmetic follows KR-234 / spec 1.1.0 exactly, no contraction; sums via math.fsum (exactly rounded); bound = fsum of all L_i and rho_i together.
- A1 (all cases): `-T*h` is read as `(-T)*h` (identical value to -(T*h)). `1 + T*abs(y) + T*ah` read left to right. `abs(v)*(T*ah + (T*T)*(h*h) + g) + L` left to right; 2^-49 multiplied first (exact power of two, order irrelevant). KR-234 text.
- A2 (all): label from KR-10: "latency-aware analytics on simulated data" (data is simulated per packet; no flag in inputs).
- A3 (all): L's `((T*T)*T)*abs(N)*e` read as (((T*T)*T)*abs(N))*e, then multiplied by (ah^3) and divided by 6. Spec 1.1.0.
- A4 idr_k-0013: |h|=0.4000000001 inside domain D; estimate is near cancellation (T*h~2), result is order-sensitive; used the specified order.
- A5 idr_k-0014: both positions in D boundary values; exp(100) ~ 2.7e43 finite, no overflow. Values huge (1e41, 1e86) but computed as specified.
- A6 idr_k-0010: h=1e-30 at the domain edge; results tiny but normal (no subnormals).
- Exact check: for every case, bound >= |estimate - exact revaluation| (80-digit Decimal exp) holds (True for all 11); cases 0001 and 0012 hand-checked in this way (e.g. 0001: diff 16.8458 <= bound 17.0569).
No fields not derivable.
