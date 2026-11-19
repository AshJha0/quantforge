"""K-8 acceptance (specifications/06-risk/bermudan-ladder-k8.md, rulings KR-8, KR-15, KR-16).

Two steps, two interpreters:

  reference   needs the QuantLib wheel (any Python with `pip install QuantLib`; run 2026-11-19 with
              QuantLib 1.44 in a local venv outside the repo). Central bump-and-revalue with
              FdHullWhiteSwaptionEngine on the three aadladder_g cases, eleven relative bumps per
              input, on the KR-16 grid (tGrid 8,000, xGrid 3,201) and on the grid first proposed
              (2,000 / 801). Writes oracle/K8_REFERENCE_QL.json.
  judge       needs the project Python. Runs CN_RANNACHER_SMOOTHED on 201/100, 401/200, 801/400 and
              1601/800, applies acceptance 1 to 3 as written in the spec and writes
              oracle/K8_ACCEPTANCE_W2.json. Nothing here chooses an entry, a bump or a grid from the
              result: the rules are the spec's.

Usage: python oracle/python/k8_acceptance.py reference | judge
"""

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CASES = ("aadladder_g-0001", "aadladder_g-0002", "aadladder_g-0003")
BUMPS = [1e-5, 2e-5, 5e-5, 1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 4e-3, 8e-3, 1.6e-2]
QL_GRIDS = {"kr16": (8000, 3201), "proposed": (2000, 801)}
GRIDS = ((201, 100), (401, 200), (801, 400), (1601, 800))
REF_FILE = ROOT / "oracle/K8_REFERENCE_QL.json"
OUT_FILE = ROOT / "oracle/K8_ACCEPTANCE_W2.json"


def inputs(index: int) -> dict[str, Any]:
    doc = json.loads((ROOT / "datasets/golden/stage_g/aadladder_g.json").read_text("utf-8"))
    out: dict[str, Any] = doc["cases"][index]["inputs"]
    return out


# --- reference (QuantLib) ---------------------------------------------------------------------------


def ql_price(i: dict[str, Any], dfs: list[float], a: float, sigma: float, tgrid: int, xgrid: int) -> float:
    """Curve times are whole days over 365 (Actual/365 Fixed), log-linear discount factors; the swap
    has accruals of exactly one 365-day year on both legs and a 365-day index on the same curve, so
    its exercise value is the spec's `phi (1 - P(t, Tn) - K sum tau P)`."""
    import QuantLib as ql

    ref = ql.Date(1, 1, 2025)
    dc = ql.Actual365Fixed()

    def day(t: float) -> Any:
        d = t * 365.0
        assert abs(d - round(d)) < 1e-9, t
        return ref + round(d)

    ql.Settings.instance().evaluationDate = ref
    curve = ql.DiscountCurve([ref] + [day(t) for t in i["curve"]["times"]], [1.0, *dfs], dc)
    handle = ql.YieldTermStructureHandle(curve)
    model = ql.HullWhite(handle, a, sigma)
    index = ql.IborIndex(
        "k8", ql.Period(365, ql.Days), 0, ql.EURCurrency(), ql.NullCalendar(), ql.Unadjusted, False, dc, handle
    )
    sched = ql.Schedule([day(i["start_years"])] + [day(t) for t in i["payment_times"]])
    kind = ql.VanillaSwap.Payer if i["swaption_type"] == "PAYER" else ql.VanillaSwap.Receiver
    swap = ql.VanillaSwap(kind, i["notional"], sched, i["fixed_rate"], dc, sched, index, 0.0, dc)
    swaption = ql.Swaption(swap, ql.BermudanExercise([day(t) for t in i["exercise_times"]]))
    swaption.setPricingEngine(ql.FdHullWhiteSwaptionEngine(model, tgrid, xgrid, 0, 1e-10))
    return float(swaption.NPV())


def reference() -> None:
    import QuantLib as ql

    doc: dict[str, Any] = {
        "what": "K-8 acceptance 1 reference: QuantLib FdHullWhiteSwaptionEngine, central bump-and-revalue, "
        "relative bumps on each discount factor (rows 0..9), mean_reversion (row 10) and sigma (row 11). "
        "d[k][b] = (P(x(1+h_b)) - P(x(1-h_b))) / (2 h_b x).",
        "quantlib": ql.__version__,
        "engine": "FdHullWhiteSwaptionEngine(model, tGrid, xGrid, dampingSteps=0, invEps=1e-10), Douglas scheme",
        "bumps": BUMPS,
        "grids": {k: {"tGrid": v[0], "xGrid": v[1]} for k, v in QL_GRIDS.items()},
        "cases": {},
    }
    for c, name in enumerate(CASES):
        i = inputs(c)
        dfs, a, s = list(i["curve"]["discount_factors"]), i["mean_reversion"], i["sigma"]
        doc["cases"][name] = {}
        for label, (tg, xg) in QL_GRIDS.items():

            def f(k: int, x: float, tg: int = tg, xg: int = xg) -> float:
                d, aa, ss = list(dfs), a, s
                if k < len(dfs):
                    d[k] = x
                elif k == len(dfs):
                    aa = x
                else:
                    ss = x
                return ql_price(i, d, aa, ss, tg, xg)

            rows = []
            for k in range(len(dfs) + 2):
                x0 = dfs[k] if k < len(dfs) else (a if k == len(dfs) else s)
                rows.append([(f(k, x0 * (1 + h)) - f(k, x0 * (1 - h))) / (2 * h * x0) for h in BUMPS])
            doc["cases"][name][label] = {"price": ql_price(i, dfs, a, s, tg, xg), "d": rows}
            REF_FILE.write_text(json.dumps(doc, indent=1) + "\n", "utf-8")


# --- judge ------------------------------------------------------------------------------------------


def method_rows(index: int) -> dict[str, list[float]]:
    sys.path.insert(0, str(ROOT / "python"))
    from quantforge_core import bermudan_k8 as k8

    i = inputs(index)
    c = i["curve"]
    out = {}
    for nx, spy in GRIDS:
        r = k8.bermudan_ladder(
            c["times"], c["discount_factors"], i["mean_reversion"], i["sigma"], False, i["start_years"],
            i["payment_times"], i["fixed_rate"], i["swaption_type"], i["notional"], i["exercise_times"],
            nx, spy, i["grid"]["width"],
        )  # fmt: skip
        out[f"{nx}/{spy}"] = [
            r["price"], *r["d_price_d_discount_factors"], r["d_price_d_mean_reversion"], r["d_price_d_sigma"]
        ]  # fmt: skip
    return out


def rel(x: float, y: float) -> float:
    return abs(x - y) / abs(y)


def judge(cache: Path | None) -> None:
    sys.path.insert(0, str(ROOT / "python"))
    from quantforge_core import stage_k as sk

    ref_doc = json.loads(REF_FILE.read_text("utf-8"))
    b1, b2 = BUMPS.index(1e-4), BUMPS.index(5e-5)
    doc: dict[str, Any] = {
        "what": "K-8 acceptance 1 to 3 (specifications/06-risk/bermudan-ladder-k8.md 0.2.0), second run: "
        "CN_RANNACHER_SMOOTHED as revised by KR-15, reference grid by KR-16. Rows: [price, d/dDF x10, d/da, "
        "d/dsigma]. The first run (method 0.1.0) is oracle/K8_ACCEPTANCE_W1.json and stays a recorded miss.",
        "date": "2026-11-19",
        "build": "python (quantforge_core.bermudan_k8, tangent-mode ladder)",
        "reference": "oracle/K8_REFERENCE_QL.json, grid kr16, bump 1e-4 (checked against 5e-5)",
        "rules": {
            "acceptance_1": "QuantLib bumps 1e-4 and 5e-5 agree within 0.1% (else the entry is unresolved); "
            "method 801/400 and 1601/800 agree within 0.2%",
            "acceptance_2": "at 201/100 every judged entry within 1% of the QuantLib reference and of the method "
            "at 1601/800; judged = discount-factor entries with |reference| >= 1e-3 max |reference|, d/da, d/dsigma",
            "acceptance_3": "num.richardson.check on 201/401/801, assumed order 2: status OK and observed order in "
            "[1.5, 2.5] on the price and every entry not exactly zero on all three grids",
        },
        "values": {},
        "entries": {},
        "failures": {"acceptance_1": [], "acceptance_2": [], "acceptance_3": []},
    }
    fails = doc["failures"]
    for c, name in enumerate(CASES):
        rows = json.loads((cache / f"rows_{c}.json").read_text("utf-8")) if cache else method_rows(c)
        doc["values"][name] = rows
        d = ref_doc["cases"][name]["kr16"]["d"]
        n = len(d) - 2
        top = max(abs(d[k][b1]) for k in range(n))
        coarse, fine, finest = rows["201/100"], rows["801/400"], rows["1601/800"]
        ent = []
        for k in range(n + 2):
            e: dict[str, Any] = {"row": k + 1, "reference": d[k][b1], "reference_5e-5": d[k][b2]}
            judged = k >= n or abs(d[k][b1]) >= 1e-3 * top
            e["judged_by_acceptance_2"] = judged
            if judged:
                e["reference_bumps_gap"] = rel(d[k][b2], d[k][b1])
                e["method_801_vs_1601"] = rel(fine[k + 1], finest[k + 1])
                e["method_1601_vs_reference"] = rel(finest[k + 1], d[k][b1])
                e["default_vs_reference"] = rel(coarse[k + 1], d[k][b1])
                e["default_vs_method_1601"] = rel(coarse[k + 1], finest[k + 1])
                if e["reference_bumps_gap"] > 1e-3 or e["method_801_vs_1601"] > 2e-3:
                    fails["acceptance_1"].append([c, k + 1])
                if e["default_vs_reference"] > 1e-2 or e["default_vs_method_1601"] > 1e-2:
                    fails["acceptance_2"].append([c, k + 1])
            ent.append(e)
        doc["entries"][name] = ent
        orders: list[Any] = []
        for k in range(n + 3):
            vals = [rows[g][k] for g in ("201/100", "401/200", "801/400")]
            if vals == [0.0, 0.0, 0.0]:
                orders.append(None)
                continue
            rc = sk.richardson_check(vals, 2.0, 2.0)
            obs = rc["observed_order"]
            orders.append({"status": rc["status"], "observed_order": obs})
            if rc["status"] != "OK" or obs is None or not 1.5 <= obs <= 2.5:
                fails["acceptance_3"].append([c, k, rc["status"], obs])
        doc["entries"][name + " observed order (row 0 = price; null = exactly zero on all grids)"] = orders
        ref_price = ref_doc["cases"][name]["kr16"]["price"]
        doc["entries"][name + " price"] = {
            "reference": ref_price,
            "default_vs_reference": rel(coarse[0], ref_price),
            "method_1601_vs_reference": rel(finest[0], ref_price),
        }
    worst = lambda key: max(e[key] for nm in CASES for e in doc["entries"][nm] if e["judged_by_acceptance_2"])  # noqa: E731
    doc["summary"] = {
        "max_reference_bumps_gap": worst("reference_bumps_gap"),
        "max_method_801_vs_1601": worst("method_801_vs_1601"),
        "max_method_1601_vs_reference": worst("method_1601_vs_reference"),
        "max_default_vs_reference": worst("default_vs_reference"),
        "max_default_vs_method_1601": worst("default_vs_method_1601"),
    }
    doc["result"] = {k: ("PASS" if not v else f"FAIL on {len(v)} entries") for k, v in fails.items()}
    assert all(math.isfinite(x) for x in doc["summary"].values())
    OUT_FILE.write_text(json.dumps(doc, indent=1) + "\n", "utf-8")
    print(json.dumps({"result": doc["result"], "summary": doc["summary"]}, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "reference":
        reference()
    else:
        judge(Path(sys.argv[2]) if len(sys.argv) > 2 else None)
