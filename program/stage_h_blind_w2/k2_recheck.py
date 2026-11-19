"""Packet builder's arithmetic check of the 58 wave 2 hand cases (hidden side; never in the packet).

Recomputes every expected value of k2_expected.json from the inputs in k2_cases.py, written from the spec
rules, and prints per field the spec value, the recomputed value and OK / DIFF (1e-12 relative, 1e-15 absolute
at 0, the KR-67 tolerance). This is our own second computation: it is not an outside check and counts as none.
    python -I program/stage_h_blind_w2/k2_recheck.py
Exit 1 on any DIFF.
"""
import datetime as dt
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from k2_cases import CASES  # noqa: E402

RW_DRC = {"AAA": 0.005, "AA": 0.02, "A": 0.03, "BBB": 0.06, "BB": 0.15, "B": 0.30, "CCC": 0.50, "UNRATED": 0.15, "DEFAULTED": 1.0}
LGD = {"EQUITY": 1.0, "NON_SENIOR": 1.0, "SENIOR": 0.75, "COVERED": 0.25}
RANK = {"COVERED": 4, "SENIOR": 3, "NON_SENIOR": 2, "EQUITY": 1}


def offset(longs, shorts):
    """KR-53 greedy. longs/shorts: lists of (rank, amount) with amount >0 / <0. Returns (net_long, net_short)."""
    L = [[r, a] for r, a in longs]
    ns = 0.0
    for r, a in sorted(shorts, key=lambda x: -x[0]):
        need = -a
        for item in sorted(L, key=lambda x: x[0]):
            if item[0] >= r and need > 0:
                use = min(item[1], need)
                item[1] -= use
                need -= use
        ns -= need
    return sum(a for _, a in L), ns


def drc_nonsec(inp):
    pos = {}
    ob = {}
    for p in inp["positions"]:
        lgd = LGD[p["seniority"]] if p.get("lgd_applies", True) else 1.0
        pnl = p["market_value"] - p["notional"]
        if p.get("cash_equity"):
            j = p["market_value"]
        elif p["notional"] > 0:
            j = max(lgd * p["notional"] + pnl, 0.0)
        else:
            j = min(lgd * p["notional"] + pnl, 0.0)
        m = p["maturity_years"]
        w = 1.0 if m >= 1 else max(m, 0.25)
        pos[p["id"]] = {"gross_jtd": j, "weight": w, "scaled_jtd": w * j}
        ob.setdefault(p["obligor"], {"bucket": p["bucket"], "l": [], "s": []})
        (ob[p["obligor"]]["l"] if w * j > 0 else ob[p["obligor"]]["s"]).append((RANK[p["seniority"]], w * j))
    obl, bk = {}, {}
    for o, d in ob.items():
        nl, ns = offset(d["l"], d["s"])
        rw = RW_DRC[inp["ratings"][o]]
        obl[o] = {"net_long": nl, "net_short": ns, "rw": rw}
        b = bk.setdefault(d["bucket"], {"L": 0.0, "S": 0.0, "wl": 0.0, "ws": 0.0})
        b["L"] += nl
        b["S"] += -ns
        b["wl"] += rw * nl
        b["ws"] += rw * -ns
    buckets = {}
    for b, d in bk.items():
        if d["L"] + d["S"] == 0:
            buckets[b] = {"hbr": None, "drc": 0.0}
            continue
        hbr = d["L"] / (d["L"] + d["S"])
        buckets[b] = {"hbr": hbr, "wtd_long": d["wl"], "wtd_short": d["ws"], "drc": max(d["wl"] - hbr * d["ws"], 0.0)}
    return {"positions": pos, "obligors": obl, "buckets": buckets, "drc": sum(v["drc"] for v in buckets.values())}


def drc_ctp(inp):
    if "bucket_drc" in inp:
        bd = inp["bucket_drc"]
        return {"drc": max(sum(max(x, 0) + 0.5 * min(x, 0) for x in bd), 0.0)}
    net = {}
    for p in inp["positions"]:
        w = 1.0 if p["maturity_years"] >= 1 else max(p["maturity_years"], 0.25)
        k = (p["index"], p["series"], p["tranche"])
        net.setdefault(k, [0.0, p["rw"]])[0] += w * p["market_value"]
    L = sum(v for v, _ in net.values() if v > 0)
    S = sum(-v for v, _ in net.values() if v < 0)
    hbr = L / (L + S)
    b = {}
    for (idx, _, _), (v, rw) in net.items():
        b[idx] = b.get(idx, 0.0) + (rw * v if v > 0 else -hbr * rw * -v)
    return {"hbr_ctp": hbr, "buckets": {k: {"drc": v} for k, v in b.items()},
            "drc": max(sum(max(x, 0) + 0.5 * min(x, 0) for x in b.values()), 0.0)}


def drc_sec(inp):
    net = {}
    for p in inp["positions"]:
        w = 1.0 if p["maturity_years"] >= 1 else max(p["maturity_years"], 0.25)
        net.setdefault((p["bucket"], p["pool"], p["tranche"]), [0.0, p["rw"]])[0] += w * p["market_value"]
    out = {}
    for b in {k[0] for k in net}:
        L = sum(v for k, (v, _) in net.items() if k[0] == b and v > 0)
        S = sum(-v for k, (v, _) in net.items() if k[0] == b and v < 0)
        wl = sum(rw * v for k, (v, rw) in net.items() if k[0] == b and v > 0)
        ws = sum(rw * -v for k, (v, rw) in net.items() if k[0] == b and v < 0)
        hbr = L / (L + S)
        out[b] = {"hbr": hbr, "drc": max(wl - hbr * ws, 0.0)}
    return {"buckets": out, "drc": sum(v["drc"] for v in out.values())}


def rrao(inp):
    t = 0.0
    for i in inp["instruments"]:
        if i["back_to_back"] or (i["kind"] == "OTHER" and i["listed_or_clearable"]):
            continue
        t += i["gross_notional"] * (0.01 if i["kind"] == "EXOTIC" else 0.001)
    return {"rrao": t}


def hist_es(pnl, c=0.975):
    if not pnl:
        return 0.0
    L = sorted(-x for x in pnl)
    n = len(L)
    w = n - n * c
    m = math.floor(w)
    if w == 0:
        return L[-1]
    return (sum(L[n - m:]) + (w - m) * L[n - m - 1]) / w


def es_lh(inp):
    if "es_t" in inp:
        e = list(map(float, inp["es_t"]))
    else:
        e = [hist_es(p) for p in inp["pnl"]]
    lh = [10, 20, 40, 60, 120]
    s = e[0] ** 2 + sum((e[j] * math.sqrt((lh[j] - lh[j - 1]) / 10)) ** 2 for j in range(1, 5))
    return {"es_by_horizon": e, "es": math.sqrt(s)}


def es_stressed(t):
    r = t["es_fc"] / t["es_rc"]
    return {"ratio": r, "ratio_floored": r < 1, "es": t["es_rs"] * max(1.0, r)}


def imcc(inp):
    p = es_stressed(inp["portfolio"])["es"]
    cl = {k: es_stressed(v)["es"] for k, v in inp["classes"].items()}
    return {"imcc_c": p, "classes": cl, "imcc": 0.5 * p + 0.5 * sum(cl.values())}


def ses(inp):
    a = math.sqrt(sum(x * x for x in inp["idio_credit"]))
    b = math.sqrt(sum(x * x for x in inp["idio_equity"]))
    o = inp["other"]
    c = math.sqrt((0.6 * sum(o)) ** 2 + (1 - 0.36) * sum(x * x for x in o))
    return {"ses": a + b + c}


MULT = {0: 1.5, 1: 1.5, 2: 1.5, 3: 1.5, 4: 1.5, 5: 1.7, 6: 1.76, 7: 1.83, 8: 1.88, 9: 1.92}


def capital(i):
    mc = MULT.get(i["exceptions"], 2.0) + i["qualitative_addon"]
    ca = max(i["imcc_prev"] + i["ses_prev"], mc * i["imcc_avg"] + i["ses_avg"])
    ima = ca + i["drc"]
    sa = sum(d["sa"] for d in i["desks"])
    amb = sum(d["sa"] for d in i["desks"] if d["zone"] == "AMBER")
    k = 0.5 * amb / sa if amb else 0.0
    sur = k * max(0.0, sa - ima)
    acr = min(ima + sur + i["c_u"], i["sa_all"]) + max(0.0, ima - sa)
    return {"m_c": mc, "c_a": ca, "ima_ga": ima, "sa_ga": sa, "k": k, "surcharge": sur, "acr_total": acr}


def months_back(d, n):
    y, m = d.year, d.month - n
    while m <= 0:
        m += 12
        y -= 1
    import calendar
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def rfet(inp):
    asof = dt.date.fromisoformat(inp["as_of"])
    start = months_back(asof, 12) + dt.timedelta(days=1)
    obs = sorted({dt.date.fromisoformat(x) for x in inp["observations"]})
    inwin = [d for d in obs if start <= d <= asof]
    mins, first, firstc = None, None, None
    s = start
    while s + dt.timedelta(days=89) <= asof:
        c = sum(1 for d in inwin if s <= d <= s + dt.timedelta(days=89))
        if mins is None or c < mins:
            mins = c
        if c < 4 and first is None:
            first, firstc = s.isoformat(), c
        s += dt.timedelta(days=1)
    crit1 = len(inwin) >= 24 and mins >= 4
    crit2 = len(inwin) >= 100
    return {"distinct_days": len(inwin), "crit1": crit1, "min_window_count": mins, "first_failing_window_start": first,
            "first_failing_window_count": firstc, "crit2": crit2, "pass": crit1 or crit2, "_last_window_count": c}


BA_RW = {("financials", "IG"): 0.05, ("sovereign", "HY_NR"): 0.02, ("basic_materials_energy_industrials", "IG"): 0.03}
R_HC = {"DIRECT": 1.0, "LEGAL": 0.8, "SECTOR_REGION": 0.5}


def df(m, imm=False):
    return 1.0 if imm else -math.expm1(-0.05 * m) / (0.05 * m)


def cva_ba(inp):
    sc, snh, hma = {}, {}, {}
    for c in inp["counterparties"]:
        sc[c["id"]] = (1 / 1.4) * BA_RW[(c["sector"], c["quality"])] * sum(n["m"] * n["ead"] * df(n["m"], n["imm"]) for n in c["netting_sets"])
        snh[c["id"]] = 0.0
        hma[c["id"]] = 0.0
    kred = math.sqrt((0.5 * sum(sc.values())) ** 2 + 0.75 * sum(v * v for v in sc.values()))
    out = {"counterparties": {k: {"scva": sc[k]} for k in sc}, "k_reduced": kred}
    if inp["version"] == "REDUCED":
        out["capital"] = 0.65 * kred
        return out
    for h in inp["single_name_hedges"]:
        r = R_HC[h["relation"]]
        x = BA_RW[(h["sector"], h["quality"])] * h["m"] * h["notional"] * df(h["m"])
        snh[h["counterparty"]] += r * x
        hma[h["counterparty"]] += (1 - r * r) * x * x
    ih = 0.0
    for h in inp["index_hedges"]:
        rw = 0.7 * sum(c["weight"] * BA_RW[(c["sector"], c["quality"])] for c in h["constituents"])
        ih += rw * h["m"] * h["notional"] * df(h["m"])
    kh = math.sqrt((0.5 * sum(sc[k] - snh[k] for k in sc) - ih) ** 2 + 0.75 * sum((sc[k] - snh[k]) ** 2 for k in sc) + sum(hma.values()))
    kf = 0.25 * kred + 0.75 * kh
    for k in sc:
        out["counterparties"][k].update(snh=snh[k], hma=hma[k])
    out.update(ih=ih, k_hedged=kh, k_full=kf, capital=0.65 * kf)
    return out


IR_RW = {"1Y": 0.0111, "2Y": 0.0093, "5Y": 0.0074, "10Y": 0.0074, "30Y": 0.0074}
IR_RHO = {("1Y", "5Y"): 0.72, ("1Y", "30Y"): 0.31}


def rho(cls, a, b):
    if cls == "IR.DELTA":
        return IR_RHO[tuple(sorted((a["factor"], b["factor"]), key=list(IR_RW).index))]
    if cls == "CCS.DELTA":
        fa, fb = a["factor"], b["factor"]
        t = 1.0 if fa["tenor"] == fb["tenor"] else 0.9
        n = 1.0 if fa["name"] == fb["name"] else (0.9 if fa["legal_group"] == fb["legal_group"] else 0.5)
        q = 1.0 if fa["quality"] == fb["quality"] else 0.8
        return t * n * q
    raise KeyError(cls)


def rw_of(cls, s):
    if cls == "IR.DELTA":
        return IR_RW[s["factor"]]
    if cls == "FX.DELTA":
        return 0.11
    if cls == "IR.VEGA":
        return 1.0
    if cls == "CCS.DELTA":
        return 0.05
    raise KeyError(cls)


GAMMA = {"IR.DELTA": 0.5, "FX.DELTA": 0.6, "IR.VEGA": 0.5}


def cva_sa(inp):
    out = {"classes": {}}
    tot = 0.0
    for cls, sens in inp["classes"].items():
        bks = {}
        for s in sens:
            bks.setdefault(s["bucket"], []).append(s)
        res = {}
        for b, ss in bks.items():
            ws = [rw_of(cls, s) * s["s_cva"] - rw_of(cls, s) * s["s_hdg"] for s in ss]
            wh = [rw_of(cls, s) * s["s_hdg"] for s in ss]
            q = sum(x * x for x in ws) + 0.01 * sum(x * x for x in wh)
            for i in range(len(ss)):
                for j in range(len(ss)):
                    if i != j:
                        q += rho(cls, ss[i], ss[j]) * ws[i] * ws[j]
            kb = math.sqrt(max(0.0, q))
            res[b] = {"k_b": kb, "sum_ws": sum(ws), "s_b": max(-kb, min(sum(ws), kb))}
        g = GAMMA.get(cls, None)
        q = sum(v["k_b"] ** 2 for v in res.values())
        names = list(res)
        for i in range(len(names)):
            for j in range(len(names)):
                if i != j:
                    q += g * res[names[i]]["s_b"] * res[names[j]]["s_b"]
        k = inp["m_cva"] * math.sqrt(max(0.0, q))
        out["classes"][cls] = {"buckets": res, "k": k}
        tot += k
    out["total"] = tot
    return out


CCF = {"COMMITMENT": 0.4, "UNCONDITIONALLY_CANCELLABLE": 0.1, "NIF_RUF": 0.5}


def leverage(i):
    der = sum(1.4 * (max(d["v"] - d["cvm_received"] + d["cvm_provided"], 0) + d["pfe"]) for d in i["derivatives"])
    sft = 0.0
    for s in i["sfts"]:
        if s["mna"]:
            sft += s["gross_assets"] + max(0, sum(s["exposures"]) - sum(s["collateral"]))
        else:
            sft += s["gross_assets"] + sum(max(0, e - c) for e, c in zip(s["exposures"], s["collateral"]))
    obs = sum(o["notional"] * CCF[o["ccf_category"]] for o in i["off_balance"])
    on = sum(i["on_balance"])
    wcd = sum(max(w["notional"] - max(0, -w["fair_value"]) - w["purchased_offset"], 0) for w in i["written_credit_derivatives"])
    exp = on + der + sft + obs + wcd
    return {"on_balance": on, "derivatives": der, "sfts": sft, "off_balance": obs, "exposure": exp,
            "ratio": i["tier1"] / exp, "meets_minimum": i["tier1"] >= 0.03 * exp}


def lex(i):
    e = {c["id"]: 0.0 for c in i["counterparties"]}
    for b in i["banking_book"]:
        e[b["counterparty"]] += b["value"]
    for o in i["off_balance"]:
        e[o["counterparty"]] += o["notional"] * max(o["ccf"], 0.1)
    tb = {}
    for p in i["trading_book"]:
        pnl = p["market_value"] - p["notional"]
        j = p["market_value"] if p.get("cash_equity") else (max(p["notional"] + pnl, 0) if p["notional"] > 0 else min(p["notional"] + pnl, 0))
        d = tb.setdefault(p["counterparty"], {"l": [], "s": []})
        (d["l"] if j > 0 else d["s"]).append((RANK[p["seniority"]], j))
    for c, d in tb.items():
        nl, _ = offset(d["l"], d["s"])
        e[c] += nl
    for m in i["crm"]:
        e[m["counterparty"]] -= m["protected"]
        e[m["provider"]] += m["protected"]
    grp = {}
    gs = {}
    for c in i["counterparties"]:
        g = c.get("group", c["id"])
        grp[g] = grp.get(g, 0.0) + e[c["id"]]
        gs[g] = gs.get(g, False) or c.get("gsib", False)
    out = {}
    for g, x in grp.items():
        lim = (0.15 if (i["bank_gsib"] and gs[g]) else 0.25) * i["tier1"]
        out[g] = {"exposure": x, "share": x / i["tier1"], "large": x >= 0.10 * i["tier1"], "limit": lim, "breach": x > lim}
    return {"groups": out}


OPS = {"risk.frtb.drc_nonsec": drc_nonsec, "risk.frtb.drc_ctp": drc_ctp, "risk.frtb.drc_sec_nonctp": drc_sec,
       "risk.frtb.rrao": rrao, "risk.frtb.ima.es_lh": es_lh, "risk.frtb.ima.es_stressed": es_stressed,
       "risk.frtb.ima.imcc": imcc, "risk.frtb.ima.ses": ses, "risk.frtb.ima.capital": capital, "risk.frtb.rfet": rfet,
       "risk.cva.ba": cva_ba, "risk.cva.sa": cva_sa, "risk.capital.leverage": leverage,
       "risk.capital.large_exposures": lex}


def get(o, path):
    """path like 'positions[id=p1].gross_jtd' or 'classes[IR.DELTA].buckets[USD].k_b'; lists keyed by a field."""
    import re
    for part in re.findall(r"[^.\[\]]+(?:\[[^\]]+\])?", path):
        m = re.fullmatch(r"([^\[]+)(?:\[(?:([^=\]]+)=)?([^\]]+)\])?", part)
        key, _, sel = m.groups()
        o = o[key]
        if sel is not None:
            o = o[sel] if isinstance(o, dict) else o[int(sel)]
    return o


def main():
    exp = json.loads((HERE / "k2_expected.json").read_text(encoding="utf-8"))["cases"]
    bad = 0
    for cid, item, op, inp in CASES:
        got = OPS[op](inp)
        for f in exp[cid]["fields"]:
            want = f["value"]
            try:
                g = get(got, f["path"])
            except (KeyError, IndexError, TypeError) as e:
                print(f"{cid}\t{f['path']}\tspec {want}\trecheck MISSING ({e})")
                bad += 1
                continue
            if isinstance(want, bool) or isinstance(want, str) or want is None:
                ok = g == want
            else:
                ok = abs(g - want) <= max(1e-12 * abs(want), 1e-15)
            bad += not ok
            print(f"{cid}\t{f['path']}\tspec {want!r}\trecheck {g!r}\t{'OK' if ok else 'DIFF'}")
        if op == "risk.frtb.rfet":
            print(f"{cid}\t(info) last 90-day window count {got['_last_window_count']}")
    print(f"# DIFF: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
