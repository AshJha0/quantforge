#!/usr/bin/env python3
"""Calibration stability report (specifications/03-calibration/stability.md, R2). Standard library only.

  python tools/workflows/calib_stability.py [--impls python java cpp rust] [--draws 200] [--out reports/workflows]

Runs seven calibrations (C1..C7) through `quantforge --batch` and judges metrics S1..S7 against the spec's
provisional thresholds. Noise comes from the library's own seeded generator: `core.rng.normals`, seed 20261107,
stream = calibration number, drawn once through the first implementation listed, so every language sees the same
draws. The tool perturbs inputs, sends cases and measures differences in what comes back. Model curves are
evaluated by CLI operations (vol.svi.evaluate, vol.sabr.hagan), with one exception: C3's zero grid evaluates the
Nelson-Siegel form stated in specifications/03-calibration/curve-fits.md, because no operation evaluates a
Nelson-Siegel curve from betas (raised with the spec session). Synthetic inputs: stability of the method, not of any market.
Exit status: 0 every judged metric passed; 1 otherwise.
"""
import argparse
import copy
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

sys.path.insert(0, str(c.ROOT / "conformance" / "runner"))
import runner  # noqa: E402

SEED = "20261107"
LABEL = "Synthetic inputs; stability of the method, not of any market."
POLICY = runner.load_policy(c.ROOT / "conformance" / "tolerances" / "policy.yaml")
RATE_A, VOL_A, PRICE_A = 1e-5, 1e-4, 1e-3  # 0.1 bp, 0.01 vol points, 0.001 per 100
TV_A = 1e-4  # C6 total variance: the spec states vol points; one vol point squared-per-year scale is taken as 1e-4 (raised with spec)


def golden_case(case_id):
    for f in sorted((c.ROOT / "datasets" / "golden").rglob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        for x in doc.get("cases", []) if isinstance(doc, dict) else []:
            if x.get("case_id") == case_id:
                return x
    raise SystemExit(f"golden case {case_id} not found")


def ns_zero(betas, tau, m):
    """Nelson-Siegel zero rate, the form in curve-fits.md (see module docstring)."""
    x = m / tau
    e = (1 - math.exp(-x)) / x
    return betas[0] + betas[1] * e + betas[2] * (e - math.exp(-x))


def zeros_from_pillars(pillars, as_of):
    return [c.zero_rate(p["discount_factor"], c.years(p["date"], as_of)) for p in pillars]


# Each calibration: base case id, the perturbed input as (get, set), amplitude, output extractor, S7 extractor,
# thresholds, optional evaluation step (extra CLI cases built from a result), parameter extractor (S5).
def cal_specs():
    def quotes_get(i):
        return [q["rate"] for q in i["quotes"]]

    def quotes_set(i, v):
        for q, x in zip(i["quotes"], v):
            q["rate"] = x

    def key_get(k):
        return lambda i: list(i[k])

    def key_set(k):
        def f(i, v):
            i[k] = list(v)
        return f

    def bonds_get(i):
        return [b["dirty_price"] for b in i["bonds"]]

    def bonds_set(i, v):
        for b, x in zip(i["bonds"], v):
            b["dirty_price"] = x

    def c3_out(inputs, outs, ev):
        mats = [c.years(b["maturity"], inputs["settlement"]) for b in inputs["bonds"]]
        grid = [min(mats) + k * (max(mats) - min(mats)) / 20 for k in range(21)]
        return [ns_zero(outs["betas"], inputs["tau"], m) for m in grid]

    return {
        "C1": dict(case="ois-0009", get=quotes_get, set=quotes_set, a=RATE_A,
                   out=lambda i, o, ev: zeros_from_pillars(o["pillars"], i["as_of"]),
                   s7=lambda i, o, ev, d: d.get("max_repricing_error"), th=dict(S3=3, S7=1e-12)),
        "C2": dict(case="ois-0011", get=quotes_get, set=quotes_set, a=RATE_A,
                   out=lambda i, o, ev: zeros_from_pillars(o["pillars"], i["as_of"]),
                   s7=lambda i, o, ev, d: d.get("max_repricing_error"), th=dict(S3=3, S7=1e-12)),
        "C3": dict(case="bondfit_d-0001", get=bonds_get, set=bonds_set, a=PRICE_A, out=c3_out,
                   s7=lambda i, o, ev, d: max(abs(r) for r in o["residuals"]), s7_relative=True,
                   params=lambda o: o["betas"], th=dict(S3=20, S7=1e-6)),
        "C4": dict(case="fits_d-0001", get=key_get("zero_rates"), set=key_set("zero_rates"), a=RATE_A,
                   out=lambda i, o, ev: o["forwards"], th=dict(S3=5)),
        "C5": dict(case="fits_d-0009", get=key_get("zero_rates"), set=key_set("zero_rates"), a=RATE_A,
                   out=lambda i, o, ev: [y + r for y, r in zip(i["zero_rates"], o["residuals"])],
                   discrete=lambda o: sorted(o["outliers"]), th=dict(S3=5, S6=0.95)),
        "C6": dict(case="smile-0034", get=key_get("total_variance"), set=key_set("total_variance"), a=TV_A,
                   evaluate=lambda i, o: ("vol.svi.evaluate", {"svi": o["svi"], "log_moneyness": i["log_moneyness"], "expiry_years": 1.0}),
                   out=lambda i, o, ev: ev["total_variance"],
                   s7=lambda i, o, ev, d: max(abs(w - y) for w, y in zip(ev["total_variance"], i["total_variance"])), th=dict(S3=10, S7=1e-8)),
        "C7": dict(case="sabr-0019", get=key_get("vols"), set=key_set("vols"), a=VOL_A,
                   evaluate=lambda i, o: ("vol.sabr.hagan", {"forward": i["forward"], "strikes": i["strikes"], "expiry_years": i["expiry_years"],
                                                            "alpha": o["alpha"], "beta": i["beta"], "rho": o["rho"], "nu": o["nu"]}),
                   out=lambda i, o, ev: ev["vols"],
                   s7=lambda i, o, ev, d: max(abs(v - y) for v, y in zip(ev["vols"], i["vols"])),
                   params=lambda o: [o["alpha"], o["rho"], o["nu"]], th=dict(S3=10, S7=1e-6)),
    }


def draws(impl, stream, count):
    r = c.batch([c.case("rng", "core.rng.normals", {"seed": SEED, "stream": stream, "count": count})], impl)["rng"]
    if r["status"] != "ok":
        raise SystemExit(f"core.rng.normals failed on {impl}: {r}")
    return r["outputs"]["values"]


def run_impl(impl, specs, noise, n_draws):
    """Returns per calibration: base outputs, S1, S3, S4, S5, S6, S7 numbers for one implementation."""
    out = {}
    for cid, s in specs.items():
        g = golden_case(s["case"])
        base_in = g["inputs"]
        n = len(s["get"](base_in))
        variants = []  # (tag, inputs)
        for k in range(n_draws):
            v = [x + s["a"] * z for x, z in zip(s["get"](base_in), noise[cid][k * n:(k + 1) * n])]
            inp = copy.deepcopy(base_in)
            s["set"](inp, v)
            variants.append((f"d{k}", inp))
        for j in range(n):
            v = s["get"](base_in)
            v[j] += s["a"]
            inp = copy.deepcopy(base_in)
            s["set"](inp, v)
            variants.append((f"b{j}", inp))
        op = g["operation"]
        cases = [c.case("base", op, base_in), c.case("base2", op, base_in)] + [c.case(t, op, i) for t, i in variants]
        res = c.batch(cases, impl)
        again = c.batch([c.case("base", op, base_in)], impl)["base"]
        inputs = {"base": base_in, **{t: i for t, i in variants}}
        evals = {}
        if "evaluate" in s:
            ecases = []
            for t in inputs:
                if res[t]["status"] == "ok":
                    eop, ein = s["evaluate"](inputs[t], res[t]["outputs"])
                    ecases.append(c.case(t, eop, ein))
            evals = {k: v.get("outputs") for k, v in c.batch(ecases, impl).items()}
        failed = [t for t in inputs if res[t]["status"] != "ok"]
        row = {"case": s["case"], "operation": op, "inputs": n, "failed_cases": len(failed)}
        row["S1"] = (json.dumps(res["base"]["outputs"], sort_keys=True) == json.dumps(res["base2"]["outputs"], sort_keys=True)
                     == json.dumps(again.get("outputs"), sort_keys=True))
        if res["base"]["status"] != "ok":
            out[cid] = {**row, "error": res["base"].get("error")}
            continue
        row["base_outputs"] = res["base"]["outputs"]
        base_vec = s["out"](base_in, res["base"]["outputs"], evals.get("base"))
        dvecs = [s["out"](inputs[f"d{k}"], res[f"d{k}"]["outputs"], evals.get(f"d{k}")) for k in range(n_draws) if res[f"d{k}"]["status"] == "ok"]
        stds = [statistics.pstdev(col) for col in zip(*dvecs)] if len(dvecs) > 1 else []
        row["S3"] = max(stds) / s["a"] if stds else None
        resp = []
        for j in range(n):
            t = f"b{j}"
            if res[t]["status"] == "ok":
                v = s["out"](inputs[t], res[t]["outputs"], evals.get(t))
                resp.append(max(abs(x - y) for x, y in zip(v, base_vec)) / s["a"])
            else:
                resp.append(None)
        ok_resp = [(r_, j) for j, r_ in enumerate(resp) if r_ is not None]
        row["S4"] = {"largest": max(ok_resp)[0] if ok_resp else None, "input_index": max(ok_resp)[1] if ok_resp else None, "per_input": resp}
        if "params" in s:
            ps = [s["params"](res[f"d{k}"]["outputs"]) for k in range(n_draws) if res[f"d{k}"]["status"] == "ok"]
            basep = s["params"](res["base"]["outputs"])
            row["S5"] = [statistics.pstdev(col) / abs(b) if b else None for col, b in zip(zip(*ps), basep)]
        if "discrete" in s:
            bset = s["discrete"](res["base"]["outputs"])
            same = sum(s["discrete"](res[f"d{k}"]["outputs"]) == bset for k in range(n_draws) if res[f"d{k}"]["status"] == "ok")
            row["S6"] = same / max(1, n_draws - len([k for k in range(n_draws) if res[f"d{k}"]["status"] != "ok"]))
        if "s7" in s:
            vals = [s["s7"](inputs[f"d{k}"], res[f"d{k}"]["outputs"], evals.get(f"d{k}"), res[f"d{k}"].get("diagnostics") or {})
                    for k in range(n_draws) if res[f"d{k}"]["status"] == "ok"]
            if any(v is None for v in vals):
                row["S7"] = None
                row["S7_note"] = "diagnostic max_repricing_error not returned by this CLI"
            else:
                worst = max(vals) if vals else None
                if s.get("s7_relative") and worst is not None:
                    worst -= s["s7"](base_in, res["base"]["outputs"], evals.get("base"), res["base"].get("diagnostics") or {})
                row["S7"] = worst
        out[cid] = row
    return out


def judge(specs, results):
    """Adds S2 and pass/fail flags. S2 compares each language's base outputs with the first language's."""
    langs = list(results)
    ref = langs[0]
    verdicts = []
    for cid, s in specs.items():
        g = golden_case(s["case"])
        cls = POLICY[g["tolerance_class"]]
        for lang in langs:
            row = results[lang][cid]
            th = s["th"]
            v = {"S1": row.get("S1") is True}
            if "base_outputs" in row and "base_outputs" in results[ref][cid]:
                per = g.get("output_classes", {})
                mism = []
                for k, e in results[ref][cid]["base_outputs"].items():
                    if k in row["base_outputs"]:
                        try:
                            mism += runner.compare(row["base_outputs"][k], e, POLICY[per[k]] if k in per else cls, None, k)
                        except ValueError:
                            pass  # class with no numeric tolerance for this output (e.g. NS betas, judged on objective only)
                row["S2"] = not mism
                row["S2_detail"] = mism[:3]
                v["S2"] = row["S2"]
            else:
                v["S2"] = False
            if "S3" in th:
                v["S3"] = row.get("S3") is not None and row["S3"] <= th["S3"]
            if "S6" in th:
                v["S6"] = row.get("S6") is not None and row["S6"] >= th["S6"]
            if "S7" in th:
                v["S7"] = row.get("S7") is not None and row["S7"] <= th["S7"]
            row["verdict"] = v
            verdicts.append((cid, lang, all(v.values())))
    return verdicts


def fmt(x, spec="{:.3g}"):
    return "—" if x is None else spec.format(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impls", nargs="+", default=["python"])
    ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--out", default=str(c.ROOT / "reports" / "workflows"))
    a = ap.parse_args()
    import datetime as dt
    specs = cal_specs()
    noise = {}
    for k, (cid, s) in enumerate(specs.items(), 1):
        n = len(s["get"](golden_case(s["case"])["inputs"]))
        noise[cid] = draws(a.impls[0], k, n * a.draws)
    results = {lang: run_impl(lang, specs, noise, a.draws) for lang in a.impls}
    verdicts = judge(specs, results)
    r = c.Report("Calibration stability", dt.date.today().isoformat(), a.out)
    r.p(f"{LABEL} Seed {SEED}, stream = calibration number (`core.rng.normals` via {a.impls[0]}), {a.draws} draws. "
        f"Amplitudes: rates {RATE_A}, vols {VOL_A}, prices {PRICE_A} per 100, SVI total variance {TV_A}. "
        "Thresholds are the spec's provisional ones (`specifications/03-calibration/stability.md`); this is a first-run report.")
    head = ["Cal", "Language", "Base case", "S1", "S2", "S3 (A)", "S4 largest (input)", "S5 (std/base)", "S6", "S7", "Pass"]
    rows = []
    for cid, s in specs.items():
        for lang in a.impls:
            row = results[lang][cid]
            v = row.get("verdict", {})
            th = s["th"]

            def mark(key, text):
                return f"{text} {'✓' if v.get(key) else '✗'}" if key in v else text
            rows.append([cid, lang, f"`{row['case']}`", mark("S1", "same" if row.get("S1") else "differs"), mark("S2", "agree" if row.get("S2") else "differ"),
                         mark("S3", f"{fmt(row.get('S3'))} ≤ {th['S3']}" if "S3" in th else fmt(row.get("S3"))),
                         f"{fmt(row.get('S4', {}).get('largest'))} (#{row.get('S4', {}).get('input_index')})",
                         ", ".join(fmt(x, "{:.2g}") for x in row["S5"]) if row.get("S5") else "",
                         mark("S6", f"{fmt(row.get('S6'), '{:.2f}')} ≥ {th['S6']}") if "S6" in th else "",
                         mark("S7", f"{fmt(row.get('S7'), '{:.2e}')} ≤ {th['S7']:g}" if row.get("S7") is not None else row.get("S7_note", "—")) if "S7" in th else "",
                         "PASS" if all(v.values()) else "FAIL"])
            r.check(f"{cid} {lang}", "fail", all(v.values()), ", ".join(k for k, ok in v.items() if not ok) or "all judged metrics pass")
    r.h("Results")
    r.table(head, rows)
    r.data.update({"seed": SEED, "draws": a.draws, "impls": a.impls,
                   "results": {lang: {cid: {k: v for k, v in row.items() if k != "base_outputs"} for cid, row in res.items()} for lang, res in results.items()}})
    return r.write([])


if __name__ == "__main__":
    sys.exit(main())
