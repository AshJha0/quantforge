"""Audit response re-measure: QuantLib reference for two edge cases, built with ql_price of
oracle/python/k8_acceptance.py (imported, not re-typed), central relative bumps 1e-4 and 5e-5."""
import importlib.util, json, sys, time
from pathlib import Path
ROOT = Path(sys.argv[1]); tg, xg = int(sys.argv[3]), int(sys.argv[4])
spec = importlib.util.spec_from_file_location("k8acc", ROOT / "oracle/python/k8_acceptance.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
base = m.inputs(0)
CASES = {"receiver_deepITM_K0.08": ({"fixed_rate": 0.08, "swaption_type": "RECEIVER"}, [10, 11]),
         "payer_deepOTM_K0.08": ({"fixed_rate": 0.08, "swaption_type": "PAYER"}, [1, 2, 3, 4, 5, 10, 11])}
out = {"quantlib": "1.44", "tGrid": tg, "xGrid": xg, "cases": {}}
for name, (kw, rows) in CASES.items():
    if len(sys.argv) > 5 and sys.argv[5] != name: continue
    i = {**base, **kw}; dfs, a, s = list(i["curve"]["discount_factors"]), i["mean_reversion"], i["sigma"]
    def f(k, x):
        d, aa, ss = list(dfs), a, s
        if k < len(dfs): d[k] = x
        elif k == len(dfs): aa = x
        else: ss = x
        return m.ql_price(i, d, aa, ss, tg, xg)
    t = time.time(); res = {"price": f(0, dfs[0]), "d": {}}; print(name, "one price", time.time() - t, flush=True)
    for k in rows:
        x0 = dfs[k] if k < len(dfs) else (a if k == len(dfs) else s)
        res["d"][k] = {str(h): (f(k, x0 * (1 + h)) - f(k, x0 * (1 - h))) / (2 * h * x0) for h in (1e-4, 5e-5)}
        print(name, k, res["d"][k], flush=True)
    out["cases"][name] = res
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1), "utf-8")
