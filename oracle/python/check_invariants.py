"""Checks every golden file against the invariants the specs state, and sweeps day counts by brute force."""
import json
from datetime import date, timedelta

from qf_oracle.common import GOLDEN, note
from qf_oracle.dates import is_business, yf

CONVS = ["ACT_360", "ACT_365F", "ACT_364", "ACT_365_25", "NL_365", "ONE_ONE", "ACT_ACT_ISDA", "ACT_ACT_AFB", "THIRTY_360_BOND",
         "THIRTY_360_US", "THIRTY_E_360", "THIRTY_E_360_ISDA", "THIRTY_E_PLUS_360"]


def sweep():
    n = 0
    ds = [date(2023, 1, 25) + timedelta(i) for i in range(70)] + [date(2024, 1, 25) + timedelta(i) for i in range(70)]
    for c in CONVS:
        for a in ds:
            for b in ds:
                if a > b:
                    continue
                for term in (b, date(2099, 12, 31)):
                    v = yf(c, a, b, termination=term)
                    assert v >= 0 and (a != b or v == 0), (c, a, b, v)
                    n += 1
    note(f"invariants: {n} day-count evaluations, none negative, all equal-date results 0")


def nondecreasing(v):
    return all(a <= b for a, b in zip(v, v[1:]))


def check(c):
    op, i, e = c["operation"], c["inputs"], c["expected"]
    if e["status"] != "ok":
        return
    o = e["outputs"]
    if op == "core.daycount.year_fraction":
        assert o["year_fraction"] >= 0
        assert i["start"] != i["end"] or o["year_fraction"] == 0
    elif op == "core.compounding.discount_factor":
        assert o["discount_factor"] > 0
    elif op == "core.rng.uniforms":
        assert all(0 < u < 1 for u in o["values"])
    elif op == "core.sobol.points":
        assert all(0 < u < 1 for p in o["points"] for u in p) or i["dimensions"] > 0 and all(0 <= u < 1 for p in o["points"] for u in p)
    elif op == "core.calendar.holidays":
        ds = [date.fromisoformat(x) for x in o["dates"]]
        assert ds == sorted(set(ds)) and all(d.year == i["year"] and d.weekday() < 5 for d in ds)
    elif op in ("core.calendar.adjust", "core.calendar.add_tenor", "core.calendar.add_business_days"):
        if i.get("convention") != "UNADJUSTED":
            assert is_business(i["calendar"], date.fromisoformat(o["date"])), c["case_id"]
    elif op == "core.stats.summary":
        assert o["variance"] >= 0 and o["min"] <= o["mean"] <= o["max"]
    elif op == "core.stats.quantile":
        assert nondecreasing(o["values"])
    elif op == "core.stats.covariance":
        assert o["correlation"] is None or abs(o["correlation"]) <= 1
    elif op == "core.stats.ols":
        assert o["r_squared"] is None or 0 <= o["r_squared"] <= 1
    elif op == "core.ts.ewma_variance":
        assert all(v >= 0 for v in o["variance"])
    elif op in ("core.pde.bs_european", "core.cos.european", "core.mc.gbm_european"):
        assert o["price"] >= 0
        assert "stderr" not in o or o["stderr"] > 0
    elif op == "core.interp.evaluate":
        for x, y in zip(i["x"], i["y"]):
            if x in i["at"]:
                assert abs(o["values"][i["at"].index(x)] - y) < 1e-11, c["case_id"]
        if i["method"] == "monotone_pchip":
            for k in range(len(i["x"]) - 1):
                lo, hi = sorted(i["y"][k:k + 2])
                for t, v in zip(i["at"], o["values"]):
                    if i["x"][k] <= t <= i["x"][k + 1]:
                        assert lo - 1e-12 <= v <= hi + 1e-12, c["case_id"]
    elif op == "core.interp.monotone_convex":
        for t, r in zip(i["t"], i["r"]):
            if t in i["at"]:
                assert abs(o["zero_rates"][i["at"].index(t)] - r) < 1e-12, c["case_id"]


def main():
    sweep()
    n = 0
    for p in sorted(GOLDEN.glob("*.json")):
        for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            check(c)
            n += 1
    note(f"invariants: {n} golden cases checked, none breaks a stated invariant")


if __name__ == "__main__":
    main()
