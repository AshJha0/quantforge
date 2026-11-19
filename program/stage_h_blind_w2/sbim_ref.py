"""Spec lane's own reference for specifications/06-risk/sbim-placeholder.md (K-8h). HIDDEN side of the blind packet.

Used only to recheck the hand arithmetic of the spec's hand cases and to write sbim_expected.json; it is our own
second computation and counts as no outside check (KR-68). Standard library only; reads the placeholder table.

    python -I program/stage_h_blind_w2/sbim_ref.py <checkout>     # prints every case's outputs
"""
import json
import math
import sys
from pathlib import Path

RISK_TYPES = {"IR_DELTA": ("IR", "delta"), "IR_VEGA": ("IR", "vega"), "FX_DELTA": ("FX", "delta"),
              "EQ_DELTA": ("EQ", "delta"), "EQ_VEGA": ("EQ", "vega")}
RC_ORDER = ("IR", "FX", "EQ")


def load_table(root):
    t = json.loads((Path(root) / "specifications/tables/stage_k/sbim-placeholder.json").read_text(encoding="utf-8"))
    f = float
    days = {x["label"]: x["days"] for x in t["tenors"]}
    order = t["IR"]["delta"]["rho"]["order"]
    ir_rho = {(a, b): f(t["IR"]["delta"]["rho"]["matrix"][i][j]) for i, a in enumerate(order) for j, b in enumerate(order)}
    return {
        "days": days,
        "IR": {"rw": {k: f(v) for k, v in t["IR"]["delta"]["rw"].items()}, "rho": ir_rho,
               "gamma": f(t["IR"]["delta"]["gamma"]), "T": f(t["IR"]["delta"]["threshold"]),
               "vrw": f(t["IR"]["vega"]["rw"]), "VT": f(t["IR"]["vega"]["threshold"])},
        "FX": {"rw": f(t["FX"]["delta"]["rw"]), "rho": f(t["FX"]["delta"]["rho"]), "T": f(t["FX"]["delta"]["threshold"])},
        "EQ": {"rw": {k: f(v) for k, v in t["EQ"]["delta"]["rw"].items()},
               "rho": {k: f(v) for k, v in t["EQ"]["delta"]["rho"].items()},
               "gamma": f(t["EQ"]["delta"]["gamma"]), "T": f(t["EQ"]["delta"]["threshold"]),
               "vrw": f(t["EQ"]["vega"]["rw"]), "VT": f(t["EQ"]["vega"]["threshold"])},
        "sf_scale": f(t["curvature"]["sf_scale"]), "sf_days": f(t["curvature"]["sf_days"]), "z": f(t["curvature"]["z"]),
        "rho_class": f(t["rho_class"]["value"]),
    }


def clip(x, k):
    return max(min(x, k), -k)


def ratio(a, b):
    return min(a, b) / max(a, b)


def factor_key(rc, rec):
    if rc == "IR":
        return rec["name"] + "|" + rec["tenor"]
    return rec["name"]


def bucket_of(rc, rec):
    if rc == "IR":
        return rec["name"]
    if rc == "FX":
        return "FX"
    return rec["bucket"]


def group_of(rc, rec):
    """Concentration group: the currency for IR (the bucket), the currency for FX, the issuer for EQ."""
    return rec["name"]


def rho(P, rc, b, fk, fl, label):
    if rc == "IR":
        return P["IR"]["rho"][(label[fk], label[fl])]
    if rc == "FX":
        return P["FX"]["rho"]
    return P["EQ"]["rho"][b]


def weighted(P, rc, kind, recs):
    """Net per risk factor, concentration per group, weighted sensitivities. Returns dicts in first-seen order."""
    net, bucket, group, label = {}, {}, {}, {}
    for r in recs:
        k = factor_key(rc, r)
        net[k] = net.get(k, 0.0) + r["amount"]
        bucket[k], group[k] = bucket_of(rc, r), group_of(rc, r)
        if rc == "IR":
            label[k] = r["tenor"]
    gsum = {}
    for k, v in net.items():
        gsum[group[k]] = gsum.get(group[k], 0.0) + v
    if kind == "delta":
        T = {"IR": P["IR"]["T"], "FX": P["FX"]["T"], "EQ": P["EQ"]["T"]}[rc]
    else:
        T = P[rc]["VT"]
    cr = {g: max(1.0, math.sqrt(abs(s) / T)) for g, s in gsum.items()}
    ws = {}
    for k, v in net.items():
        if kind == "delta":
            rw = {"IR": lambda: P["IR"]["rw"][label[k]], "FX": lambda: P["FX"]["rw"], "EQ": lambda: P["EQ"]["rw"][bucket[k]]}[rc]()
        else:
            rw = P[rc]["vrw"]
        ws[k] = rw * v * cr[group[k]]
    return net, bucket, group, label, cr, ws


def aggregate(P, rc, bucket, group, label, cr, x, curvature):
    """Intra- and inter-bucket aggregation of x (WS or CVR). Returns (buckets, inner, residual_k)."""
    byb = {}
    for k in x:
        byb.setdefault(bucket[k], []).append(k)
    buckets, res_k = {}, None
    for b, ks in byb.items():
        s2 = 0.0
        for k in ks:
            for l in ks:
                if k == l:
                    s2 += x[k] * x[k]
                else:
                    r = rho(P, rc, b, k, l, label)
                    if curvature:
                        s2 += r * r * x[k] * x[l]
                    else:
                        s2 += r * ratio(cr[group[k]], cr[group[l]]) * x[k] * x[l]
        kb = math.sqrt(max(0.0, s2))
        if b == "RESIDUAL":
            res_k = kb
            continue
        sx = sum(x[k] for k in ks)
        buckets[b] = {"k_b": kb, "s_b": clip(sx, kb), ("sum_cvr" if curvature else "sum_ws"): sx}
    inner = 0.0
    for b, vb in buckets.items():
        for c, vc in buckets.items():
            if b == c:
                inner += vb["k_b"] ** 2
            else:
                g = P[rc]["gamma"] if rc != "FX" else 0.0  # FX has one bucket
                if curvature:
                    inner += g * g * vb["s_b"] * vc["s_b"]
                else:
                    gbc = ratio(cr[b], cr[c]) if rc == "IR" else 1.0
                    inner += g * gbc * vb["s_b"] * vc["s_b"]
    return buckets, math.sqrt(max(0.0, inner)), res_k


def theta_lambda(P, cvrs):
    s, a = sum(cvrs), sum(abs(v) for v in cvrs)
    theta = min(s / a, 0.0) if a > 0 else 0.0
    z = P["z"]
    return s, theta, (z * z - 1) * (1 + theta) - theta


def risk_class(P, rc, recs):
    out = {}
    for kind in ("delta", "vega"):
        rs = [r for r in recs if RISK_TYPES[r["risk_type"]][1] == kind]
        if not rs:
            continue
        net, bucket, group, label, cr, ws = weighted(P, rc, kind, rs)
        buckets, inner, res_k = aggregate(P, rc, bucket, group, label, cr, ws, False)
        d = {"margin": inner + (res_k or 0.0), "buckets": buckets, "cr": cr, "ws": ws}
        if res_k is not None:
            d["residual_k"] = res_k
        out[kind] = d
        if kind == "vega":
            cvr, cb, cl = {}, {}, {}
            for r in rs:
                k = factor_key(rc, r)
                t = P["days"][r["tenor"]]
                sf = P["sf_scale"] * min(1.0, P["sf_days"] / t)
                cvr[k] = cvr.get(k, 0.0) + sf * r["amount"]
                cb[k] = bucket_of(rc, r)
                if rc == "IR":
                    cl[k] = r["tenor"]
            buckets, inner, res_k = aggregate(P, rc, cb, {}, cl, {}, cvr, True)
            c = {"cvr": cvr, "buckets": buckets}
            margin = 0.0
            non = [v for k, v in cvr.items() if cb[k] != "RESIDUAL"]
            if non:
                s, th, lam = theta_lambda(P, non)
                c.update(sum_cvr=s, theta=th, **{"lambda": lam})
                margin += max(s + lam * inner, 0.0)
            if res_k is not None:
                s, th, lam = theta_lambda(P, [v for k, v in cvr.items() if cb[k] == "RESIDUAL"])
                rm = max(s + lam * res_k, 0.0)
                c["residual"] = {"k": res_k, "sum_cvr": s, "theta": th, "lambda": lam, "margin": rm}
                margin += rm
            c["margin"] = margin
            out["curvature"] = c
    out["im"] = sum(out[k]["margin"] for k in ("delta", "vega", "curvature") if k in out)
    return out


def sbim(P, inp):
    pcs = {}
    for r in inp["records"]:
        pcs.setdefault(r["group"], []).append(r)
    res = {"groups": {}}
    total = 0.0
    for pc, recs in pcs.items():
        rcs = {}
        for rc in RC_ORDER:
            rr = [r for r in recs if RISK_TYPES[r["risk_type"]][0] == rc]
            if rr:
                rcs[rc] = risk_class(P, rc, rr)
        ims = [v["im"] for v in rcs.values()]
        s2 = sum(a * b * (1.0 if i == j else P["rho_class"]) for i, a in enumerate(ims) for j, b in enumerate(ims))
        im = math.sqrt(max(0.0, s2))
        res["groups"][pc] = {"im": im, "risk_classes": rcs}
        total += im
    res["total"] = total
    return res


def flatten(o, prefix=""):
    """Leaves of the output object as (path, value); keyed members written name[key], as the compare script reads."""
    out = []
    for k, v in o.items():
        if isinstance(v, dict):
            keyed = k in ("groups", "risk_classes", "buckets", "cr", "ws", "cvr")
            if keyed:
                for kk, vv in v.items():
                    p = f"{prefix}{k}[{kk}]"
                    if isinstance(vv, dict):
                        out += flatten(vv, p + ".")
                    else:
                        out.append((p, vv))
            else:
                out += flatten(v, f"{prefix}{k}.")
        else:
            out.append((prefix + k, v))
    return out


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sbim_cases import CASES, ADDED_CASES
    P = load_table(sys.argv[1])
    if "--write-expected" in sys.argv:
        exp = {"note": "K-8h hand cases; values from sbim_ref.py (the spec lane's own computation), each headline value "
                       "also printed in the spec section 'Hand cases'; HIDDEN from the blind lane",
               "cases": {cid: {"item": "K-8h", "fields": [{"path": p, "value": v} for p, v in flatten(sbim(P, inp))]}
                         for cid, inp in CASES}}
        out = Path(__file__).resolve().parent / "sbim_expected.json"
        out.write_text(json.dumps(exp, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {out}: {sum(len(c['fields']) for c in exp['cases'].values())} fields")
        add = {"note": "K-8h cases added AFTER the blind run of 2026-11-19; values from sbim_ref.py; NOT blind-checked "
                       "and never counted as outside-checked",
               "cases": {cid: {"item": "K-8h", "fields": [{"path": p, "value": v} for p, v in flatten(sbim(P, inp))]}
                         for cid, inp in ADDED_CASES}}
        out = Path(__file__).resolve().parent / "sbim_added_expected.json"
        out.write_text(json.dumps(add, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {out}: {sum(len(c['fields']) for c in add['cases'].values())} fields")
        return
    for cid, inp in CASES + ADDED_CASES:
        print(cid, json.dumps(sbim(P, inp)))


if __name__ == "__main__":
    main()
