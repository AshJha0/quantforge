import json, math, os, sys

PK = "C:/Work/Claude/qf-blind/simm_packet/"
OUT = "C:/Work/Claude/qf-blind/simm_blind/"
T = json.load(open(PK + "tables/simm-placeholder.json"))
CASES = json.load(open(PK + "inputs/K-8h.inputs.json"))["cases"]
SKEL = json.load(open(PK + "output_template.json"))["results_skeleton"]

F = float
DAYS = {x["label"]: F(x["days"]) for x in T["tenors"]}
ORD = T["IR"]["delta"]["rho"]["order"]
MAT = [[F(v) for v in r] for r in T["IR"]["delta"]["rho"]["matrix"]]
IR_RW = {k: F(v) for k, v in T["IR"]["delta"]["rw"].items()}
IR_GAMMA = F(T["IR"]["delta"]["gamma"])
IR_T = F(T["IR"]["delta"]["threshold"]); IR_VT = F(T["IR"]["vega"]["threshold"]); IR_VRW = F(T["IR"]["vega"]["rw"])
FX_RW = F(T["FX"]["delta"]["rw"]); FX_RHO = F(T["FX"]["delta"]["rho"]); FX_T = F(T["FX"]["delta"]["threshold"])
EQ_RW = {k: F(v) for k, v in T["EQ"]["delta"]["rw"].items()}
EQ_RHO = {k: F(v) for k, v in T["EQ"]["delta"]["rho"].items()}
EQ_GAMMA = F(T["EQ"]["delta"]["gamma"]); EQ_T = F(T["EQ"]["delta"]["threshold"])
EQ_VT = F(T["EQ"]["vega"]["threshold"]); EQ_VRW = F(T["EQ"]["vega"]["rw"])
SFS = F(T["curvature"]["sf_scale"]); SFD = F(T["curvature"]["sf_days"]); Z = F(T["curvature"]["z"])
PSI = F(T["psi"]["value"])


def sqrtp(x):
    return math.sqrt(max(0.0, x))


def clip(x, k):
    return max(-k, min(x, k))


def ir_rho(a, b):
    return MAT[ORD.index(a)][ORD.index(b)]


def kind_calc(rc, kind, facs):
    """facs: dict key -> dict(bucket, group, net, label1). Returns delta/vega output dict."""
    # concentration groups
    gsum = {}
    for k, f in facs.items():
        gsum[f["group"]] = gsum.get(f["group"], 0.0) + f["net"]
    if rc == "IR":
        th = IR_T if kind == "delta" else IR_VT
    elif rc == "FX":
        th = FX_T
    else:
        th = EQ_T if kind == "delta" else EQ_VT
    cr = {g: max(1.0, math.sqrt(abs(s) / th)) for g, s in gsum.items()}
    ws = {}
    for k, f in facs.items():
        if kind == "vega":
            rw = IR_VRW if rc == "IR" else EQ_VRW
        elif rc == "IR":
            rw = IR_RW[f["label1"]]
        elif rc == "FX":
            rw = FX_RW
        else:
            rw = EQ_RW[f["bucket"]]
        ws[k] = rw * f["net"] * cr[f["group"]]

    def rho(k, l, b):
        if rc == "IR":
            return ir_rho(facs[k]["label1"], facs[l]["label1"])
        if rc == "FX":
            return FX_RHO
        return EQ_RHO[b]

    byb = {}
    for k, f in facs.items():
        byb.setdefault(f["bucket"], []).append(k)
    kb, sb, sumws = {}, {}, {}
    for b, ks in byb.items():
        s = sum(ws[k] * ws[k] for k in ks)
        for k in ks:
            for l in ks:
                if k == l:
                    continue
                ck, cl = cr[facs[k]["group"]], cr[facs[l]["group"]]
                fkl = min(ck, cl) / max(ck, cl)
                s += rho(k, l, b) * fkl * ws[k] * ws[l]
        kb[b] = sqrtp(s)
        sumws[b] = sum(ws[k] for k in ks)
        sb[b] = clip(sumws[b], kb[b])
    nonres = [b for b in byb if b != "RESIDUAL"]
    m = sum(kb[b] ** 2 for b in nonres)
    for b in nonres:
        for c in nonres:
            if b == c:
                continue
            if rc == "IR":
                gam = IR_GAMMA
                crb = cr[b]; crc = cr[c]  # IR group == bucket == currency
                g = min(crb, crc) / max(crb, crc)
            else:
                gam = EQ_GAMMA
                g = 1.0
            m += gam * g * sb[b] * sb[c]
    M = sqrtp(m)
    kres = kb.get("RESIDUAL", 0.0)
    out = {"margin": M + kres,
           "buckets": {b: {"k_b": kb[b], "s_b": sb[b], "sum_ws": sumws[b]} for b in nonres},
           "cr": cr, "ws": ws}
    if "RESIDUAL" in byb:
        out["residual_k"] = kres
    return out, M + kres


def curvature(rc, vrecs):
    """vrecs: list of (factor key, bucket, label1, amount)"""
    cvr = {}
    fb = {}
    for key, b, lab, amt in vrecs:
        sf = SFS * min(1.0, SFD / DAYS[lab])
        cvr[key] = cvr.get(key, 0.0) + sf * amt
        fb[key] = b
    def rho_c(k, l, b):
        if rc == "IR":
            ka = k.split("|")[1]; la = l.split("|")[1]
            return ir_rho(ka, la) ** 2
        return EQ_RHO[b] ** 2
    byb = {}
    for k in cvr:
        byb.setdefault(fb[k], []).append(k)
    kb, sb, sc = {}, {}, {}
    for b, ks in byb.items():
        s = sum(cvr[k] ** 2 for k in ks)
        for k in ks:
            for l in ks:
                if k != l:
                    s += rho_c(k, l, b) * cvr[k] * cvr[l]
        kb[b] = sqrtp(s)
        sc[b] = sum(cvr[k] for k in ks)
        sb[b] = clip(sc[b], kb[b])
    nonres = [b for b in byb if b != "RESIDUAL"]
    out = {"cvr": cvr}
    total = 0.0
    def theta_lam(ks):
        ssum = sum(cvr[k] for k in ks); den = sum(abs(cvr[k]) for k in ks)
        th = 0.0 if den == 0 else min(ssum / den, 0.0)
        return ssum, th, (Z * Z - 1) * (1 + th) - th
    if nonres:
        gam = IR_GAMMA if rc == "IR" else EQ_GAMMA
        m = sum(kb[b] ** 2 for b in nonres)
        for b in nonres:
            for c in nonres:
                if b != c:
                    m += gam ** 2 * sb[b] * sb[c]
        Mc = sqrtp(m)
        ks = [k for k in cvr if fb[k] != "RESIDUAL"]
        ssum, th, lam = theta_lam(ks)
        out["buckets"] = {b: {"k_b": kb[b], "s_b": sb[b], "sum_cvr": sc[b]} for b in nonres}
        out["sum_cvr"] = ssum; out["theta"] = th; out["lambda"] = lam
        total += max(ssum + lam * Mc, 0.0)
    else:
        out["buckets"] = {}
    if "RESIDUAL" in byb:
        ks = byb["RESIDUAL"]
        ssum, th, lam = theta_lam(ks)
        cres = max(ssum + lam * kb["RESIDUAL"], 0.0)
        out["residual"] = {"k": kb["RESIDUAL"], "sum_cvr": ssum, "theta": th, "lambda": lam, "margin": cres}
        total += cres
    out["margin"] = total
    return out, total


def run(inp):
    recs = inp["records"]
    pcs = {}
    for r in recs:
        pcs.setdefault(r["product_class"], []).append(r)
    res = {"product_classes": {}}
    total = 0.0
    for pc, rs in pcs.items():
        rcs = {}
        for r in rs:
            rcs.setdefault(r["risk_type"].split("_")[0], []).append(r)
        pcout = {"risk_classes": {}}
        ims = {}
        for rc, rr in rcs.items():
            o = {}
            im = 0.0
            for kind, rt in (("delta", rc + "_DELTA"), ("vega", rc + "_VEGA")):
                sel = [r for r in rr if r["risk_type"] == rt]
                if not sel:
                    continue
                facs = {}
                vrecs = []
                for r in sel:
                    q = r["qualifier"]
                    if rc == "IR":
                        key = q + "|" + r["label1"]; b = q; g = q
                    elif rc == "FX":
                        key = q; b = "FX"; g = q
                    else:
                        key = q; b = r["bucket"]; g = q
                    f = facs.setdefault(key, {"bucket": b, "group": g, "net": 0.0, "label1": r.get("label1")})
                    f["net"] += r["amount"]
                    if kind == "vega":
                        vrecs.append((key, b, r["label1"], r["amount"]))
                out, mg = kind_calc(rc, kind, facs)
                o[kind] = out; im += mg
                if kind == "vega":
                    co, cm = curvature(rc, vrecs)
                    o["curvature"] = co; im += cm
            o["im"] = im
            ims[rc] = im
            pcout["risk_classes"][rc] = o
        names = list(ims)
        s = sum(v * v for v in ims.values())
        for a in names:
            for b in names:
                if a != b:
                    s += PSI * ims[a] * ims[b]
        pcout["im"] = sqrtp(s)
        total += pcout["im"]
        res["product_classes"][pc] = pcout
    res["total"] = total
    return res


def check_shape(sk, got, path):
    """every skeleton key must exist in got; report extra keys in got."""
    msgs = []
    if isinstance(sk, dict):
        if not isinstance(got, dict):
            return [path + " not dict"]
        for k in sk:
            if k not in got:
                msgs.append(path + "/" + k + " MISSING")
            else:
                msgs += check_shape(sk[k], got[k], path + "/" + k)
        for k in got:
            if k not in sk:
                msgs.append(path + "/" + k + " EXTRA")
    else:
        if got is None:
            msgs.append(path + " None")
    return msgs


def main():
    out = {"cases": {}}
    bad = []
    for c in CASES:
        r = run(c["inputs"])
        out["cases"][c["case_id"]] = r
        bad += check_shape(SKEL["cases"][c["case_id"]], r, c["case_id"])
    s = json.dumps(out, indent=1)
    open(OUT + "blind_results.json", "w").write(s)
    for b in bad:
        print(b)
    print("shape problems:", len(bad))


if __name__ == "__main__":
    main()
