import json, sys
from fractions import Fraction as F

PACKET = "C:/Work/Claude/qf-blind/k8i_packet/"
LEV_LABEL = "simplified leverage ratio (LEV30 subset); not a regulatory return"
LEX_LABEL = "simplified large exposures (LEX subset); not a regulatory return"
CCF = {"DIRECT_CREDIT_SUBSTITUTE": F(1), "FORWARD_PURCHASE": F(1), "OTHER_CREDIT_SUBSTITUTE": F(1),
       "NIF_RUF": F(1, 2), "TRANSACTION_CONTINGENT": F(1, 2), "COMMITMENT": F(2, 5),
       "TRADE_LC": F(1, 5), "UNCONDITIONALLY_CANCELLABLE": F(1, 10)}
RANK = {"COVERED": 4, "SENIOR": 3, "NON_SENIOR": 2, "EQUITY": 1}
fx = lambda v: F(v)  # exact value of binary64 (or int) input

def leverage(i):
    t1 = fx(i["tier1"])
    ob = sum((fx(x) for x in i.get("on_balance", [])), F(0))
    nets = F(0)
    for d in i.get("derivatives", []):
        rc = max(fx(d["v"]) - fx(d.get("cvm_received", 0)) + fx(d.get("cvm_provided", 0)), F(0))
        nets += F(7, 5) * (rc + fx(d["pfe"]))
    wcd = F(0)
    for w in i.get("written_credit_derivatives", []):
        wcd += max(fx(w["notional"]) - max(F(0), -fx(w["fair_value"])) - fx(w.get("purchased_offset", 0)), F(0))
    sft = F(0)
    for s in i.get("sfts", []):
        E = [fx(x) for x in s.get("exposures", [])]; C = [fx(x) for x in s.get("collateral", [])]
        sft += fx(s["gross_assets"])
        if s["mna"]:
            sft += max(F(0), sum(E, F(0)) - sum(C, F(0)))
        else:
            # pairwise by index; unequal lengths: missing collateral treated as 0
            for k, e in enumerate(E):
                sft += max(F(0), e - (C[k] if k < len(C) else F(0)))
    obs = sum((fx(o["notional"]) * CCF[o["ccf_category"]] for o in i.get("off_balance", [])), F(0))
    deriv = nets + wcd
    expo = ob + deriv + sft + obs
    fexpo = float(expo)
    ratio = float(t1 / expo)
    return {"on_balance": float(ob), "derivatives": float(deriv), "derivative_netting_sets": float(nets),
            "written_credit_derivatives": float(wcd), "sfts": float(sft), "off_balance": float(obs),
            "exposure": fexpo, "ratio": ratio,
            "meets_minimum": bool(float(i["tier1"]) >= 0.03 * fexpo), "label": LEV_LABEL}

def offset(pos):
    longs = [[RANK[p["seniority"]], k, max(fx(p["market_value"]), F(0))] for k, p in enumerate(pos) if fx(p["notional"]) >= 0]
    shorts = [[RANK[p["seniority"]], k, max(-fx(p["market_value"]), F(0))] for k, p in enumerate(pos) if fx(p["notional"]) < 0]
    shorts.sort(key=lambda s: (-s[0], s[1]))
    for r, _, amt in [(s[0], s[1], s[2]) for s in shorts]:
        pass
    ls = sorted(longs, key=lambda l: (l[0], l[1]))
    for s in sorted(shorts, key=lambda s: (-s[0], s[1])):
        for l in ls:
            if s[2] == 0: break
            if l[0] >= s[0] and l[2] > 0:
                u = min(l[2], s[2]); l[2] -= u; s[2] -= u
    return sum((l[2] for l in longs), F(0)), -sum((s[2] for s in shorts), F(0))

def lex(i):
    t1 = fx(i["tier1"]); bank_gsib = bool(i.get("bank_gsib", False))
    cps = i["counterparties"]; ids = [c["id"] for c in cps]
    assert len(set(ids)) == len(ids)
    bb = {c: F(0) for c in ids}; ob = {c: F(0) for c in ids}; prot = {c: F(0) for c in ids}; rec = {c: F(0) for c in ids}
    for b in i.get("banking_book", []): bb[b["counterparty"]] += fx(b["value"])
    for o in i.get("off_balance", []): ob[o["counterparty"]] += fx(o["notional"]) * max(fx(o["ccf"]), F(1, 10))
    tl = {}; ts = {}
    for c in ids:
        tl[c], ts[c] = offset([p for p in i.get("trading_book", []) if p["counterparty"] == c])
    for r in i.get("crm", []):
        prot[r["counterparty"]] += fx(r["protected"]); rec[r["provider"]] += fx(r["protected"])
    rows = []; ex = {}
    for c in cps:
        k = c["id"]
        pre = bb[k] + ob[k] + tl[k]
        assert prot[k] <= pre
        ex[k] = pre - prot[k] + rec[k]
        rows.append({"id": k, "banking_book": float(bb[k]), "off_balance": float(ob[k]),
                     "trading_book_net_long": float(tl[k]), "trading_book_net_short": float(ts[k]),
                     "protected": float(prot[k]), "received": float(rec[k]), "exposure": float(ex[k])})
    groups = {}
    for c in cps:
        groups.setdefault(c.get("group", c["id"]), []).append(c)
    grows = []
    for g in sorted(groups):
        ms = groups[g]
        tot = sum((ex[m["id"]] for m in ms), F(0))
        counted = sum((ex[m["id"]] for m in ms if not m.get("exempt", False)), F(0))
        gs = bank_gsib and any(m.get("gsib", False) for m in ms)
        limit = (0.15 if gs else 0.25) * float(t1)
        ft = float(tot)
        grows.append({"group": g, "members": [m["id"] for m in ms], "exposure": ft,
                      "share": float(tot / t1), "large": bool(ft >= 0.10 * float(t1)), "limit": limit,
                      "breach": bool(float(counted) > limit), "exempt": all(m.get("exempt", False) for m in ms)})
    order = sorted(grows, key=lambda r: (-r["exposure"], r["group"]))
    rep = [r["group"] for r in order if r["large"]]
    for r in order[:20]:
        if r["group"] not in rep: rep.append(r["group"])
    rep = [r["group"] for r in order if r["group"] in set(rep)]
    return {"counterparties": rows, "groups": grows, "report": rep, "label": LEX_LABEL}

inp = json.load(open(PACKET + "inputs/k8i.inputs.json"))["cases"]
res = {}
for cid, c in inp.items():
    res[cid] = leverage(c["inputs"]) if c["operation"] == "risk.capital.leverage" else lex(c["inputs"])
json.dump({"cases": res}, open("blind_results.json", "w"), indent=1)
