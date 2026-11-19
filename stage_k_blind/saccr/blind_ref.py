"""Blind SA-CCR reference (plain Python, written from the stripped spec, parameters file and rulings only).
    python -I blind_ref.py <packet dir> <out json>
"""
import json
import math
import sys
from pathlib import Path


def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def load_params(pk):
    p = json.loads((Path(pk) / "sa-ccr-parameters.json").read_text(encoding="utf-8"))
    t = {}
    for r in p["table2"]:
        t[(r["asset_class"], r["subclass"])] = r
    return p, t


def single_factor(items):
    """items: list of (a_e, rho_e)."""
    s = sum(rho * a for a, rho in items)
    q = sum((1 - rho * rho) * a * a for a, rho in items)
    return math.sqrt(s * s + q)


def ir_en(db, offset):
    b1, b2, b3 = db
    if not offset:
        return abs(b1) + abs(b2) + abs(b3)
    return math.sqrt(b1 * b1 + b2 * b2 + b3 * b3 + 1.4 * b1 * b2 + 1.4 * b2 * b3 + 0.6 * b1 * b3)


def mpor_of(m, n_trades):
    rd = m["remargin_days"]
    floor = 10 if rd == 1 else 9 + rd
    if m.get("illiquid") or n_trades > 5000:
        floor = max(floor, 20)
    if m.get("disputes"):
        floor *= 2
    est = m.get("mpor_days")
    return max(floor, est) if est is not None else floor


def compute(inp, P, T, margined_mode):
    """margined_mode: None for unmargined factors, else MPOR days."""
    out_tr = []
    groups = {}  # (cls, treat, key) -> list of per-trade records
    for t in inp["trades"]:
        cls = t["asset_class"]
        kind = t.get("kind", "LINEAR")
        treat = t.get("treatment", "NORMAL")
        sub = t.get("subclass")
        row = T[(cls, None if cls in ("IR", "FX") else sub)]
        sd = None
        if cls in ("IR", "CREDIT"):
            S, E = t["start"], t["end"]
            sd = max((math.exp(-0.05 * S) - math.exp(-0.05 * E)) / 0.05, 10 / 250)
            d = t["notional"] * sd
        else:
            d = t["notional"]
        if margined_mode is None:
            mf = math.sqrt(min(max(t["maturity"], 10 / 250), 1.0))
        else:
            mf = 1.5 * math.sqrt(margined_mode / 250)
        if kind == "LINEAR":
            delta = 1.0 if t["position"] == "LONG" else -1.0
        elif kind == "OPTION":
            sg = row["option_volatility"]
            lam = t.get("shift", 0.0)
            T_ = t["exercise"]
            d1 = (math.log((t["underlying_price"] + lam) / (t["strike"] + lam)) + sg * sg * T_ / 2) / (sg * math.sqrt(T_))
            bought, call = t["position"] == "BOUGHT", t["option_type"] == "CALL"
            if call:
                delta = phi(d1) if bought else -phi(d1)
            else:
                delta = -phi(-d1) if bought else phi(-d1)
        else:  # CDO
            A, D = t["attachment"], t["detachment"]
            mag = 15 / ((1 + 14 * A) * (1 + 14 * D))
            delta = mag if t["position"] == "BOUGHT" else -mag
        eff = d * mf * delta
        sf = row["supervisory_factor"] * P["treatment_scale"][treat]
        key = t.get("hedging_set") if treat != "NORMAL" or cls in ("IR", "FX") else None
        if key is None:
            key = row["hedging_set"] if cls == "COMMODITY" else ""
        rec = {"t": t, "row": row, "eff": eff, "sf": sf}
        groups.setdefault((cls, treat, key), []).append(rec)
        out_tr.append({"id": t["id"], "supervisory_duration": sd, "adjusted_notional": d, "maturity_factor": mf,
                       "delta": delta, "effective_notional": eff, "supervisory_factor": sf})
    order_c = ["IR", "FX", "CREDIT", "EQUITY", "COMMODITY"]
    order_t = ["NORMAL", "BASIS", "VOLATILITY"]
    hs = []
    for (cls, treat, key), recs in groups.items():
        if cls == "IR":
            db = [0.0, 0.0, 0.0]
            for r in recs:
                E = r["t"]["end"]
                db[0 if E < 1 else (1 if E <= 5 else 2)] += r["eff"]
            add = recs[0]["sf"] * ir_en(db, inp.get("ir_offset", True))
        elif cls == "FX":
            add = recs[0]["sf"] * abs(sum(r["eff"] for r in recs))
        else:
            ents = {}
            for r in recs:
                e = r["t"]["entity"]
                ents.setdefault(e, [r["sf"], r["row"]["correlation"], 0.0])
                ents[e][2] += r["eff"]
            add = single_factor([(sf * s, rho) for sf, rho, s in ents.values()])
        hs.append({"asset_class": cls, "treatment": treat, "key": key, "addon": add})
    hs.sort(key=lambda h: (order_c.index(h["asset_class"]), order_t.index(h["treatment"]), h["key"]))
    addon = {c: 0.0 for c in order_c}
    for h in hs:
        addon[h["asset_class"]] += h["addon"]
    agg = sum(addon.values())
    return out_tr, hs, addon, agg


def multiplier(v, c, agg):
    if v - c >= 0:
        return 1.0
    if agg == 0:
        return 0.05
    return min(1.0, 0.05 + 0.95 * math.exp((v - c) / (2 * 0.95 * agg)))


def ead_case(inp, P, T):
    v = sum(t["market_value"] for t in inp["trades"])
    c = inp.get("collateral", 0.0)
    mg = inp.get("margin")
    tr, hs, addon, agg = compute(inp, P, T, None)
    m_un = multiplier(v, c, agg)
    rc_un = max(v - c, 0.0)
    ead_un = 1.4 * (rc_un + m_un * agg)
    if mg is None:
        return {"ead": ead_un, "rc": rc_un, "pfe": m_un * agg, "multiplier": m_un, "addon_aggregate": agg, "addon": addon,
                "v": v, "c": c, "margined": False, "mpor_days": None, "ead_unmargined": None, "capped": False,
                "hedging_sets": hs, "trades": tr}
    mp = mpor_of(mg, len(inp["trades"]))
    trm, hsm, addonm, aggm = compute(inp, P, T, mp)
    mm = multiplier(v, c, aggm)
    rcm = max(v - c, mg["threshold"] + mg["mta"] - mg["nica"], 0.0)
    ead_m = 1.4 * (rcm + mm * aggm)
    ead = min(ead_m, ead_un)
    return {"ead": ead, "rc": rcm, "pfe": mm * aggm, "multiplier": mm, "addon_aggregate": aggm, "addon": addonm, "v": v, "c": c,
            "margined": True, "mpor_days": mp, "ead_unmargined": ead_un, "capped": ead_m > ead_un,
            "hedging_sets": hsm, "trades": trm}


def main():
    pk, outp = sys.argv[1], sys.argv[2]
    P, T = load_params(pk)
    cases = json.loads((Path(pk) / "saccr.inputs.json").read_text(encoding="utf-8"))
    res = {c["case_id"]: ead_case(c["inputs"], P, T) for c in cases}
    Path(outp).write_text(json.dumps(res, indent=1, sort_keys=True), encoding="utf-8", newline="\n")


main()
