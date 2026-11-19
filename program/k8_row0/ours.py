import json, sys, time
R = str(__import__("pathlib").Path(__file__).resolve().parents[2])
sys.path.insert(0, R + "/python"); sys.path.insert(0, R + "/oracle/python")
from quantforge_core import bermudan_k8 as k8
import k8_acceptance as ka
out = {}
def args(i, nx, spy, dfs=None, times=None):
    c = i["curve"]
    return (times or c["times"], dfs or c["discount_factors"], i["mean_reversion"], i["sigma"], False, i["start_years"],
            i["payment_times"], i["fixed_rate"], i["swaption_type"], i["notional"], i["exercise_times"], nx, spy, i["grid"]["width"])
BUMPS = [1e-6, 1e-4, 1.6e-2, 0.2]
for c in range(3):
    i = ka.inputs(c); dfs = list(i["curve"]["discount_factors"])
    for nx, spy in ((41, 20), (201, 100)) + (((801, 400),) if c == 0 else ()):
        t0 = time.time()
        p0 = k8.bermudan_price(*args(i, nx, spy))["price"]
        rec = {"price": p0, "rows": {}}
        for j in (0, 6, 7, 8, 9) if nx < 801 else (0,):
            r = []
            for h in BUMPS if nx < 801 else BUMPS[1:3]:
                up = list(dfs); up[j] *= 1 + h; dn = list(dfs); dn[j] *= 1 - h
                pu = k8.bermudan_price(*args(i, nx, spy, up))["price"]; pd = k8.bermudan_price(*args(i, nx, spy, dn))["price"]
                r.append({"h": h, "central": (pu - pd) / (2 * h * dfs[j]), "up_minus_base": pu - p0, "dn_minus_base": pd - p0})
            rec["rows"][j + 1] = r
        out[f"case{c+1} {nx}/{spy}"] = rec
        print(c, nx, spy, time.time() - t0, p0, {k: max(abs(x["up_minus_base"]) + abs(x["dn_minus_base"]) for x in v) for k, v in rec["rows"].items()}, flush=True)
# control: remove the 1.0 node so that the 0.4986 node carries weight for t = 1
i = ka.inputs(0); t = list(i["curve"]["times"]); d = list(i["curve"]["discount_factors"])
t2, d2 = t[:1] + t[2:], d[:1] + d[2:]
lad = k8.bermudan_ladder(*args(i, 201, 100, d2, t2))["d_price_d_discount_factors"]
h = 1e-4; up = list(d2); up[0] *= 1 + h; dn = list(d2); dn[0] *= 1 - h
b = (k8.bermudan_price(*args(i, 201, 100, up, t2))["price"] - k8.bermudan_price(*args(i, 201, 100, dn, t2))["price"]) / (2 * h * d2[0])
out["control_node_1y_removed_201/100"] = {"times": t2, "aad_ladder": lad, "bump_row1_h1e-4": b}
print("control", lad, b)
json.dump(out, open(R + "/program/k8_row0/ours.json", "w"), indent=1)
