"""Re-measure (audit response, KA-B1): CN_RANNACHER_SMOOTHED from the repo's Python build at 101/50 and
151/75 against oracle/K8_REFERENCE_QL.json (KR-19 grid, bump 1e-4), judged entries by the acceptance 2 rule."""
import json, sys
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path.insert(0, str(ROOT / "python"))
from quantforge_core import bermudan_k8 as k8
ref = json.loads((ROOT / "oracle/K8_REFERENCE_QL.json").read_text("utf-8"))
cases = json.loads((ROOT / "datasets/golden/stage_g/aadladder_g.json").read_text("utf-8"))["cases"]
b1, b2 = ref["bumps"].index(1e-4), ref["bumps"].index(5e-5)
out = {}
for c, name in enumerate(("aadladder_g-0001", "aadladder_g-0002", "aadladder_g-0003")):
    i = cases[c]["inputs"]; cu = i["curve"]
    d = ref["cases"][name]["kr16"]["d"]
    r1 = [row[b1] for row in d]
    n = len(cu["times"]); mx = max(abs(x) for x in r1[:n])
    for nx, spy in ((101, 50), (151, 75), (201, 100)):
        r = k8.bermudan_ladder(cu["times"], cu["discount_factors"], i["mean_reversion"], i["sigma"], False,
            i["start_years"], i["payment_times"], i["fixed_rate"], i["swaption_type"], i["notional"],
            i["exercise_times"], nx, spy, i["grid"]["width"])
        v = [*r["d_price_d_discount_factors"], r["d_price_d_mean_reversion"], r["d_price_d_sigma"]]
        gaps = {k: 100 * (v[k] - r1[k]) / abs(r1[k]) for k in range(n + 2) if k >= n or abs(r1[k]) >= 1e-3 * mx}
        w = max(gaps, key=lambda k: abs(gaps[k]))
        out[f"{name} {nx}/{spy}"] = {"worst_row": w, "worst_pct": gaps[w], "gaps_pct": gaps, "values": v, "price": r["price"]}
        print(name, nx, spy, "worst row", w, f"{gaps[w]:+.3f}%", {k: round(g, 3) for k, g in gaps.items()}, flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1), "utf-8")
