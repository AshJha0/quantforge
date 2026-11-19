"""Audit response re-measure: repo Python build, CN_RANNACHER_SMOOTHED, two edge cases of audit finding KA-B2."""
import json, sys, time
from pathlib import Path
ROOT = Path(sys.argv[1]); sys.path.insert(0, str(ROOT / "python"))
from quantforge_core import bermudan_k8 as k8
i0 = json.loads((ROOT / "datasets/golden/stage_g/aadladder_g.json").read_text("utf-8"))["cases"][0]["inputs"]
out = {}
for name, kw in (("receiver_deepITM_K0.08", {"fixed_rate": 0.08, "swaption_type": "RECEIVER"}), ("payer_deepOTM_K0.08", {"fixed_rate": 0.08, "swaption_type": "PAYER"})):
    i = {**i0, **kw}; cu = i["curve"]; out[name] = {}
    for nx, spy in ((101, 50), (201, 100), (401, 200), (801, 400), (1601, 800)):
        t = time.time()
        r = k8.bermudan_ladder(cu["times"], cu["discount_factors"], i["mean_reversion"], i["sigma"], False,
            i["start_years"], i["payment_times"], i["fixed_rate"], i["swaption_type"], i["notional"], i["exercise_times"], nx, spy, 6.0)
        out[name][f"{nx}/{spy}"] = [r["price"], *r["d_price_d_discount_factors"], r["d_price_d_mean_reversion"], r["d_price_d_sigma"]]
        print(name, nx, round(time.time() - t, 1), out[name][f"{nx}/{spy}"], flush=True)
        Path(sys.argv[2]).write_text(json.dumps(out, indent=1), "utf-8")
