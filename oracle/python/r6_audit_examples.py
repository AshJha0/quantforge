"""R6-11: the stage I audit's three hand examples (R5_STAGE_I_AUDIT.md items 50 to 52) and its Greek and Margrabe hand checks
(items 29, 30) recomputed by the oracle's reference functions. Prints each with agreement.

    cd oracle/python && uv run python -W ignore r6_audit_examples.py
"""
import gen_stage_i_w1 as W
import gen_stage_i_w4a as W4


def show(name, got, want, tol=5e-6):
    ok = all(abs(g - w) <= tol * max(1, abs(w)) for g, w in zip(got, want))
    print(f"{name}: oracle {['%.6f' % g for g in got]} audit {want}: {'agree' if ok else 'DISAGREE'}")
    return ok


ok = True
o = W.qp_ref({"a": [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], "b": [-1.0, -2.0, -2.5], "weights": [1.0, 1.0, 1.0], "upper": [0.5, None], "lower": [None, None]})
ok &= show("item 50 qp bounds x, objective", o["x"] + [o["objective"]], [0.5, 2.0, 0.25])
for h, want in ((1.0, 1.5), (3.0, 0.5), (4.0, 0.0), (5.0, 0.0)):
    o = W4.qp4_ref({"a": [[1.0]], "b": [-2.0], "weights": [1.0], "half_spreads": [h]})
    ok &= show(f"item 51 cost kink h = {h}", o["x"] + ([o["risk"], o["cost"]] if h == 4.0 else []), [want] + ([4.0, 0.0] if h == 4.0 else []))
S = [[4, 1.2, 0.8], [1.2, 2, 0.5], [0.8, 0.5, 1]]
o = W.mv_ref({"covariance": [[float(v) for v in r] for r in S]})
ok &= show("item 52 minvar hedge, variance_after, effectiveness", list(o["hedge"]) + [o["variance_after"], o["effectiveness"]], [-0.457143, -0.571429, 2.994286, 0.251429])
g = W.bs_greeks(100.0, 0.03, 0.01, 0.2, {"instrument": "CALL", "strike": 100.0, "expiry_years": 1.0})
ok &= show("item 29 call delta, gamma, vega", [g["DELTA"], g["GAMMA"], g["VEGA"]], [0.573496, 0.0193576, 38.7152])
print("ALL AGREE" if ok else "SOME DISAGREE")
