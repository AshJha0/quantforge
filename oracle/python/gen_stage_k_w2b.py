"""Stage K wave 2b goldens: CVA capital (K-8g: BA-CVA reduced and full, SA-CVA) and the simplified leverage ratio
and large exposures (K-8i).

Specs: specifications/06-risk/cva-capital.md and specifications/06-risk/leverage-large-exposures.md (PROPOSED);
rulings specifications/stage-k-rulings-w2.md KR-50 to KR-69 and the wave 2b section KR-311 to KR-326 (PROPOSED).
Parameters are read from specifications/tables/stage_k/{mar50_cva,lev_leverage,lex_large_exposures}.json, the
single copy (KR-50).

This oracle is written from the specs in mpmath at 50 digits on the binary64 inputs (`mp.mpf(float)` is exact),
with the quadratic forms written as double sums over index pairs; it does not import quantforge_core. Every case
of the specs' golden tables is written here in table order, so case ids match the tables (suites cva_k, df_k,
sacva_k, lev_k, lex_k for values; cva_ke, sacva_ke, lev_ke, lex_ke for errors). Cases after the tables' last row
are added by this lane (hand, not blind).

Acceptance targets asserted before anything is written (the run stops on a miss):
- every field of program/stage_h_blind_w2/k2_expected.json for the 27 K-8g and K-8i cases, to the compare tolerance
  max(1e-12 |expected|, 1e-15) (KR-67); these 27 cases matched the DR-H2 blind lane (program/STAGE_K_BLIND_W2.md,
  27 of 27) and carry that record in verified_by;
- df_k-0001 and df_k-0002 against SciPy `integrate.quad` (the time average of exp(-0.05 t), footnote 357) and the
  printed spec values;
- lev_k-0001 to 0003 within 1.0 of the printed CRE99 EADs 569, 5,406 and 936 (tolerance fixed in the spec before
  any run), lev_k-0004 and 0005 equal to the footnote 384 figures 90 and 100.

    cd oracle/python && uv run python -W ignore gen_stage_k_w2b.py
"""
import json
import math
import re
import sys
from pathlib import Path

import mpmath as mp
from scipy.integrate import quad

from qf_oracle import common
from qf_oracle.common import Suite, f

mp.mp.dps = 50
G = "oracle/python/gen_stage_k_w2b.py"
ROOT = Path(__file__).resolve().parents[2]
SPEC_C = "specifications/06-risk/cva-capital.md"
SPEC_L = "specifications/06-risk/leverage-large-exposures.md"
TABLES = ROOT / "specifications" / "tables" / "stage_k"


def entries(name):
    doc = json.loads((TABLES / name).read_text("utf-8"))
    return {e["key"]: e["value"] for e in doc["entries"]}


T = entries("mar50_cva.json")
LV = entries("lev_leverage.json")
LX = entries("lex_large_exposures.json")
EXPECTED = json.loads((ROOT / "program/stage_h_blind_w2/k2_expected.json").read_text("utf-8"))["cases"]
sys.path.insert(0, str(ROOT / "program" / "stage_h_blind_w2"))
import k2_cases  # noqa: E402  (the inputs the blind lane received, written out by the packet builder)

CASES = {cid: inp for cid, _, _, inp in k2_cases.CASES}

ORACLE = "mpmath 50 digits (independent oracle, gen_stage_k_w2b.py)"
BLIND = "blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_W2.md): MATCH"
SCIPY = "scipy.integrate.quad 1.x (independent library)"
ADDED = "added by the wave 2b Python lane 2026-11-19: hand, not blind re-derived"
# K-8i blind lane of 2026-11-20 (program/STAGE_K_BLIND_K8I.md): 9 of 9 MATCH, all counted.
BLIND_K8I = "blind re-derivation DR-H2 2026-11-20 (K-8i lane, stage_k_blind/k8i/compare_output.txt, program/STAGE_K_BLIND_K8I.md): MATCH"
LABEL_C = "regulatory formula on caller inputs; not a regulatory return"
LABEL_LEV = "simplified leverage ratio (LEV30 subset); not a regulatory return"
LABEL_LEX = "simplified large exposures (LEX subset); not a regulatory return"
TAGS_C = ["stage_k", "cva_capital"]
TAGS_L = ["stage_k", "leverage_large_exposures"]
E = "date_and_convention"
LIM = {"absolute": 1e-15, "relative": 1e-12}  # KR-67, A1 of both specs


def M(x):
    return mp.mpf(x) if isinstance(x, float) else mp.mpf(str(x))


def D(text):
    return mp.mpf(str(text).split()[0])


def to_float(x):
    if isinstance(x, dict):
        return {k: to_float(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_float(v) for v in x]
    if isinstance(x, mp.mpf):
        return f(x)
    return x


def stop(what):
    raise SystemExit(f"acceptance check FAILED: {what}")


def note_ok(what):
    common.note(f"  check MATCH: {what}")


# ---- BA-CVA ------------------------------------------------------------------------------------------------------

QI = {"IG": 0, "HY_NR": 1}


def rw(sector, quality):
    return D(T["ba.rw"][sector][QI[quality]])


def df(m, imm=False):
    if imm:
        return mp.mpf(1)
    x = D(T["ba.df_rate"]) * M(m)
    return (1 - mp.e ** (-x)) / x


R_HC = {"DIRECT": D(T["ba.r_hc"]["direct"]), "LEGAL": D(T["ba.r_hc"]["legally_related"]),
        "SECTOR_REGION": D(T["ba.r_hc"]["same_sector_region"])}


def ba(inp):
    rho, alpha, beta, ds = D(T["ba.rho"]), D(T["ba.alpha"]), D(T["ba.beta"]), D(T["ba.ds"])
    rows, scva = [], []
    for c in inp["counterparties"]:
        dfs = [df(n["m"], n.get("imm", False)) for n in c["netting_sets"]]
        s = rw(c["sector"], c["quality"]) * mp.fsum(M(n["m"]) * M(n["ead"]) * d for n, d in zip(c["netting_sets"], dfs)) / alpha
        scva.append(s)
        rows.append({"id": c["id"], "scva": s, "snh": None, "hma": None, "netting_sets": [{"df": d} for d in dfs]})
    k_red = mp.sqrt((rho * mp.fsum(scva)) ** 2 + (1 - rho ** 2) * mp.fsum(s ** 2 for s in scva))
    out = {"version": inp["version"], "counterparties": rows, "ih": None, "k_reduced": k_red, "k_hedged": None,
           "k_full": None}
    if inp["version"] == "FULL":
        snh = {c["id"]: [] for c in inp["counterparties"]}
        hma = {c["id"]: [] for c in inp["counterparties"]}
        for h in inp.get("single_name_hedges", []):
            x = rw(h["sector"], h["quality"]) * M(h["m"]) * M(h["notional"]) * df(h["m"])
            r = R_HC[h["relation"]]
            snh[h["counterparty"]].append(r * x)
            hma[h["counterparty"]].append((1 - r ** 2) * x ** 2)
        ih = mp.fsum(D(T["ba.index_rw_scalar"]) * mp.fsum(M(k["weight"]) * rw(k["sector"], k["quality"]) for k in i["constituents"])
                     * M(i["m"]) * M(i["notional"]) * df(i["m"]) for i in inp.get("index_hedges", []))
        net = []
        for row in rows:
            row["snh"], row["hma"] = mp.fsum(snh[row["id"]]), mp.fsum(hma[row["id"]])
            net.append(row["scva"] - row["snh"])
        k_h = mp.sqrt((rho * mp.fsum(net) - ih) ** 2 + (1 - rho ** 2) * mp.fsum(x ** 2 for x in net) + mp.fsum(r["hma"] for r in rows))
        k_full = beta * k_red + (1 - beta) * k_h
        out.update(ih=ih, k_hedged=k_h, k_full=k_full)
        cap = ds * k_full
    else:
        cap = ds * k_red
    out.update(capital=cap, rwa=D(T["rwa_multiplier"]) * cap, label=LABEL_C)
    return out


# ---- SA-CVA ------------------------------------------------------------------------------------------------------

TENORS = T["ir.tenors_specified"]


def upper(table, a, b):
    i, j = min(a, b), max(a, b)
    return D(table[i][j])


def ir_rho_spec(a, b):
    if a == b:
        return mp.mpf(1)
    i, j = sorted((TENORS.index(a), TENORS.index(b)))
    return D(T["ir.rho_specified"][TENORS[i]][TENORS[j]])


def ccs_rho(bucket, fa, fb):
    if bucket == "8":
        p = T["ccs.rho"]["bucket_8"]
        name = D(p["name"][0] if (fa["index"], fa["series"]) == (fb["index"], fb["series"])
                 else p["name"][1] if fa["index"] == fb["index"] else p["name"][2])
    else:
        p = T["ccs.rho"]["buckets_1_7"]
        lg_a, lg_b = fa.get("legal_group"), fb.get("legal_group")
        name = D(p["name"][0] if fa["name"] == fb["name"] else p["name"][1] if lg_a is not None and lg_a == lg_b else p["name"][2])
    return D(p["tenor"][0 if fa["tenor"] == fb["tenor"] else 1]) * name * D(p["quality"][0 if fa["quality"] == fb["quality"] else 1])


def rcs_gamma(b, c):
    x, y = int(b), int(c)
    row = lambda n: n - 1 if n <= 7 else n - 8  # noqa: E731 (Table 9: 1/8..7/14, then 15, 16, 17)
    g = upper(T["rcs.gamma_same_quality"], row(x), row(y))
    if x <= 14 and y <= 14 and (x <= 7) != (y <= 7):
        g = g / D(T["rcs.gamma_cross_quality_divisor"])
    return g


def eq_gamma(b, c):
    x, y, g = int(b), int(c), T["eq.gamma"]
    if 11 in (x, y):
        return D(g["with_11"])
    if x <= 10 and y <= 10:
        return D(g["within_1_10"])
    if {x, y} == {12, 13}:
        return D(g["12_13"])
    return D(g["12_or_13_with_1_10"])


def gamma(cls, b, c):
    if cls == "IR":
        return D(T["ir.gamma"])
    if cls == "FX":
        return D(T["fx.gamma"])
    if cls == "CCS":
        return upper(T["ccs.gamma"], int(b) - 1, int(c) - 1)
    if cls == "RCS":
        return rcs_gamma(b, c)
    if cls == "EQ":
        return eq_gamma(b, c)
    return D(T["com.gamma"]["with_11" if 11 in (int(b), int(c)) else "within_1_10"])


def sa_weight(cls, kind, s, rep):
    """(aggregation bucket, factor, risk weight)."""
    b, fac = s["bucket"], s["factor"]
    specified = {rep if c == "reporting" else c for c in T["ir.specified_currencies"]}
    if cls == "IR":
        if kind == "VEGA":
            return b, fac, D(T["ir.vega_rw"])
        return b, fac, D(T["ir.rw_specified"][fac]) if b in specified else D(T["ir.rw_other_ccy"])
    if cls == "FX":
        return b, b, D(T["fx.delta_rw" if kind == "DELTA" else "fx.vega_rw"])
    if cls == "CCS":
        return ("1" if b in ("1a", "1b") else b), fac, D(T["ccs.rw"][b][QI[fac["quality"]]])
    if kind == "DELTA":
        return b, b, D(T[f"{cls.lower()}.rw"][b])
    if cls == "EQ":
        large = int(b) <= 8 or int(b) == 12  # KR-315
        return b, b, D(T["eq.vega_rw"]["large_cap" if large else "other"])
    return b, b, D(T[f"{cls.lower()}.vega_rw"])


def sa_rho(cls, kind, bucket, fa, fb):
    if cls == "IR" and kind == "VEGA":
        return D(T["ir.vega_rho"])
    if cls == "IR":
        if "CURVE" in (fa, fb):
            return D(T["ir.rho_other_ccy_curve_inflation"])
        return ir_rho_spec(fa, fb)
    if cls == "CCS":
        return ccs_rho(bucket, fa, fb)
    raise AssertionError("one factor per bucket")


def sa(inp):
    m_cva = M(inp.get("m_cva", 1))
    R = D(T["sa.R"])
    order_keys = [f"{c}.{k}" for c in ("IR", "FX", "CCS", "RCS", "EQ", "COM") for k in ("DELTA", "VEGA")]
    classes, total = {}, []
    for key in order_keys:
        if key not in inp["classes"]:
            continue
        cls, kind = key.split(".")
        buckets = {}
        for s in inp["classes"][key]:
            b, fac, w = sa_weight(cls, kind, s, inp["reporting_currency"])
            buckets.setdefault(b, []).append((fac, w * M(s["s_cva"]) - w * M(s["s_hdg"]), w * M(s["s_hdg"])))
        order = sorted(buckets, key=lambda x: (len(x), x))
        rows, ks, sbs = [], [], []
        for b in order:
            it = buckets[b]
            q = mp.fsum(it[k][1] * it[l][1] * (1 if k == l else sa_rho(cls, kind, b, it[k][0], it[l][0]))
                        for k in range(len(it)) for l in range(len(it)))
            q += R * mp.fsum(x[2] ** 2 for x in it)
            kb = mp.sqrt(max(q, 0))
            sw = mp.fsum(x[1] for x in it)
            sb = max(-kb, min(sw, kb))
            rows.append({"bucket": b, "k_b": kb, "s_b": sb, "sum_ws": sw, "floored": bool(q < 0)})
            ks.append(kb)
            sbs.append(sb)
        q = mp.fsum(ks[i] ** 2 for i in range(len(ks))) + mp.fsum(
            gamma(cls, order[i], order[j]) * sbs[i] * sbs[j] for i in range(len(ks)) for j in range(len(ks)) if i != j)
        k = m_cva * mp.sqrt(max(q, 0))
        classes[key] = {"buckets": rows, "k": k}
        total.append(k)
    tot = mp.fsum(total)
    return {"classes": classes, "m_cva": m_cva, "total": tot, "rwa": D(T["rwa_multiplier"]) * tot, "label": LABEL_C}


# ---- leverage ----------------------------------------------------------------------------------------------------

CCF = {"DIRECT_CREDIT_SUBSTITUTE": "direct_credit_substitutes_and_other_100pct_items",
       "FORWARD_PURCHASE": "direct_credit_substitutes_and_other_100pct_items",
       "OTHER_CREDIT_SUBSTITUTE": "direct_credit_substitutes_and_other_100pct_items",
       "NIF_RUF": "nif_ruf", "TRANSACTION_CONTINGENT": "transaction_related_contingent", "COMMITMENT": "commitments",
       "TRADE_LC": "short_term_trade_lc", "UNCONDITIONALLY_CANCELLABLE": "unconditionally_cancellable"}


def lev(inp):
    alpha = D(LV["deriv.alpha"])
    on = mp.fsum(M(x) for x in inp.get("on_balance", []))
    ns = mp.fsum(alpha * (max(M(d["v"]) - M(d.get("cvm_received", 0)) + M(d.get("cvm_provided", 0)), 0) + M(d["pfe"]))
                 for d in inp.get("derivatives", []))
    wcd = mp.fsum(max(M(w["notional"]) - max(0, -M(w["fair_value"])) - M(w.get("purchased_offset", 0)), 0)
                  for w in inp.get("written_credit_derivatives", []))
    sft = mp.mpf(0)
    for s in inp.get("sfts", []):
        e, c = [M(x) for x in s["exposures"]], [M(x) for x in s["collateral"]]
        add = max(0, mp.fsum(e) - mp.fsum(c)) if s["mna"] else mp.fsum(max(0, a - b) for a, b in zip(e, c))
        sft += M(s["gross_assets"]) + add
    obs = mp.fsum(M(o["notional"]) * D(LV["ccf"][CCF[o["ccf_category"]]]) for o in inp.get("off_balance", []))
    exp_ = on + ns + wcd + sft + obs
    t1 = M(inp["tier1"])
    ratio = t1 / exp_
    margin = abs(ratio - D(LV["min_leverage_ratio"]))
    if margin <= mp.mpf("1e-12"):
        stop("a leverage golden lies within 1e-12 of the 3% boundary (spec: avoid)")
    return {"on_balance": on, "derivatives": ns + wcd, "derivative_netting_sets": ns, "written_credit_derivatives": wcd,
            "sfts": sft, "off_balance": obs, "exposure": exp_, "ratio": ratio,
            "meets_minimum": bool(ratio >= D(LV["min_leverage_ratio"])), "label": LABEL_LEV}


# ---- large exposures ---------------------------------------------------------------------------------------------

RANK = {"COVERED": 4, "SENIOR": 3, "NON_SENIOR": 2, "EQUITY": 1}


def offset(pos):
    """KR-53 written out: shorts by descending rank (stable), each against eligible longs by ascending rank."""
    longs = [[r, j] for r, j in pos if j > 0]
    idx = sorted(range(len(longs)), key=lambda i: (longs[i][0], i))
    rest = []
    for r, a in sorted([(r, -j) for r, j in pos if j < 0], key=lambda t: -t[0]):
        for i in idx:
            if a > 0 and longs[i][0] >= r and longs[i][1] > 0:
                u = min(a, longs[i][1])
                longs[i][1] -= u
                a -= u
        rest.append(a)
    return mp.fsum(x[1] for x in longs), -mp.fsum(rest)


def lex(inp):
    t1 = M(inp["tier1"])
    cps = inp["counterparties"]
    ids = [c["id"] for c in cps]
    z = lambda: {i: [] for i in ids}  # noqa: E731
    bb, obs, prot, recv, tb = z(), z(), z(), z(), z()
    for b in inp.get("banking_book", []):
        bb[b["counterparty"]].append(M(b["value"]))
    for o in inp.get("off_balance", []):
        obs[o["counterparty"]].append(M(o["notional"]) * max(M(o["ccf"]), D(LX["exposure.obs_ccf_floor"])))
    for p in inp.get("crm", []):
        prot[p["counterparty"]].append(M(p["protected"]))
        recv[p["provider"]].append(M(p["protected"]))
    for t in inp.get("trading_book", []):
        mv = M(t["market_value"])
        j = max(mv, 0) if M(t["notional"]) >= 0 else min(mv, 0)  # LGD 1: notional + (mv - notional)
        tb[t["counterparty"]].append((RANK[t["seniority"]], j))
    rows, expo = [], {}
    for i in ids:
        nl, nsh = offset(tb[i])
        e = mp.fsum(bb[i]) + mp.fsum(obs[i]) + nl - mp.fsum(prot[i]) + mp.fsum(recv[i])
        expo[i] = e
        rows.append({"id": i, "banking_book": mp.fsum(bb[i]), "off_balance": mp.fsum(obs[i]), "trading_book_net_long": nl,
                     "trading_book_net_short": nsh, "protected": mp.fsum(prot[i]), "received": mp.fsum(recv[i]),
                     "exposure": e})
    groups = {}
    for c in cps:
        groups.setdefault(c.get("group") or c["id"], []).append(c)
    out, ranked = [], []
    for g in sorted(groups):
        ms = groups[g]
        tot = mp.fsum(expo[c["id"]] for c in ms)
        counted = mp.fsum(expo[c["id"]] for c in ms if not c.get("exempt", False))
        gs = inp.get("bank_gsib", False) and any(c.get("gsib", False) for c in ms)
        lim = D(LX["limit.gsib_to_gsib"] if gs else LX["limit"]) * t1
        large = tot >= D(LX["large_exposure_threshold"]) * t1
        out.append({"group": g, "members": [c["id"] for c in ms], "exposure": tot, "share": tot / t1, "large": bool(large),
                    "limit": lim, "breach": bool(counted > lim), "exempt": all(c.get("exempt", False) for c in ms)})
        ranked.append((tot, g, large))
    ranked.sort(key=lambda r: (-r[0], r[1]))
    report = [g for n, (_, g, large) in enumerate(ranked) if large or n < int(LX["report.top_n"])]
    return {"counterparties": rows, "groups": out, "report": report, "label": LABEL_LEX}


# ---- acceptance against the blind expected values ----------------------------------------------------------------

def get(out, path):
    for name, key in re.findall(r"([^.\[\]]+)(?:\[([^\]]+)\])?", path):
        out = out[name]
        if key:
            if isinstance(out, list):
                out = next(x for x in out if str(x.get("id", x.get("bucket", x.get("group")))) == key)
            else:
                out = out[key]
    return out


def accept(cid, hi):
    """Every expected field of the case, to max(1e-12 |e|, 1e-15) on the binary64 output (KR-67)."""
    lo = to_float(hi)
    for fld in EXPECTED[cid]["fields"]:
        got, want = get(lo, fld["path"]), fld["value"]
        if isinstance(want, bool) or isinstance(got, bool):
            ok = got is want
        else:
            ok = abs(got - want) <= max(1e-12 * abs(want), 1e-15)
        if not ok:
            stop(f"{cid} {fld['path']}: {got!r} vs expected {want!r}")
    note_ok(f"{cid}: {len(EXPECTED[cid]['fields'])} field(s) of k2_expected.json")
    return lo


OC_BA = {"version": E, "label": E}
OC_SA = {"label": E}
OC_LEV = {"meets_minimum": E, "label": E}
OC_LEX = {"label": E, "report": E}


def blind(s, cid, op, fn, oc, tags, desc):
    inp = CASES[cid]
    lo = accept(cid, fn(inp))
    s.add(op, inp, lo, limit=LIM, output_classes=oc, verified=["hand", ORACLE, BLIND], tags=tags + ["hand", "outside_checked", "blind"],
          description=desc)


def hand(s, op, inp, fn, oc, tags, desc, rederived=True):
    # the four K-8i hand cases of 2026-11-19 were re-derived blind on 2026-11-20; later cases pass rederived=False
    k8i = op.startswith("risk.capital.") and rederived
    s.add(op, inp, to_float(fn(inp)), limit=LIM, output_classes=oc, verified=["hand", ORACLE, BLIND_K8I if k8i else ADDED],
          tags=tags + (["hand", "outside_checked", "blind"] if k8i else ["hand"]),
          description="hand: " + desc)


# ---- suites ------------------------------------------------------------------------------------------------------

def cp(id_, sector, quality, *ns):
    return {"id": id_, "sector": sector, "quality": quality,
            "netting_sets": [{"ead": e, "m": m, "imm": imm} for e, m, imm in ns]}


def gen_cva():
    s = Suite("cva_k", SPEC_C, G)
    descs = ["one counterparty, reduced (worked example)", "two counterparties, reduced", "IMM netting set: DF 1",
             "direct hedge, full (worked example)", "index hedge, full", "sector/region hedge, full: HMA"]
    for n, d in enumerate(descs, 1):
        blind(s, f"cva_k-{n:04d}", "risk.cva.ba", ba, OC_BA, TAGS_C, d)
    hand(s, "risk.cva.ba", {"version": "FULL", "counterparties": [
        cp("A", "technology_telecom", "HY_NR", (300000, 3, False), (150000, 0.5, True)),
        cp("B", "health_utilities_professional", "IG", (800000, 7, False))],
        "single_name_hedges": [{"counterparty": "A", "relation": "LEGAL", "sector": "technology_telecom", "quality": "HY_NR", "m": 3, "notional": 100000},
                               {"counterparty": "B", "relation": "DIRECT", "sector": "health_utilities_professional", "quality": "IG", "m": 5, "notional": 900000}],
        "index_hedges": [{"m": 5, "notional": 400000, "constituents": [
            {"sector": "financials", "quality": "IG", "weight": 0.25}, {"sector": "other", "quality": "HY_NR", "weight": 0.75}]}]},
        ba, OC_BA, TAGS_C, "LEGAL and DIRECT hedges on two names plus a mixed index (name-weighted RW, MAR50.24(4)); B over-hedged")
    hand(s, "risk.cva.ba", {"version": "REDUCED", "counterparties": [
        cp("L", "local_gov", "IG", (250000, 12, False)), cp("K", "consumer_transport_admin", "HY_NR", (0, 2, False)),
        cp("E", "other", "IG")]}, ba, OC_BA, TAGS_C, "no five-year cap on M (12y); a zero EAD and a counterparty with no netting set")
    s.write()

    d = Suite("df_k", SPEC_C, G)
    for m, printed in ((5, "0.8847968677143805"), (0.1, "0.9975041614635374")):
        inp = {"version": "REDUCED", "counterparties": [cp("C1", "financials", "IG", (1000000, m, False))]}
        lo = to_float(ba(inp))
        got = lo["counterparties"][0]["netting_sets"][0]["df"]
        lib = quad(lambda t: math.exp(-0.05 * t), 0, m)[0] / m
        if got != float(printed) or abs(lib - got) > 2e-16 * 4:
            stop(f"DF({m}): {got!r}, printed {printed}, quad {lib!r}")
        note_ok(f"DF({m}) = {got!r}: printed {printed}, quad {lib!r}")
        d.add("risk.cva.ba", inp, lo, limit=LIM, output_classes=OC_BA,
              verified=["hand", ORACLE, f"{SCIPY}: quad average of exp(-0.05 t) over [0, {m}] = {lib!r}: MATCH 1e-15"],
              tags=TAGS_C + ["outside_checked", "library"], description=f"DF({m}) of footnote 357 in the expm1 form (KR-64)")
    d.write()

    s = Suite("sacva_k", SPEC_C, G)
    descs = ["IR delta USD 1Y and 5Y", "IR delta with a hedge (worked example): the R term", "IR delta USD and EUR",
             "clipping S_b at K_b (worked example)", "CCS bucket 2, legally related names", "m_cva 1.25", "FX delta EUR and JPY",
             "IR delta + FX delta + IR vega: total"]
    for n, dsc in enumerate(descs, 1):
        blind(s, f"sacva_k-{n:04d}", "risk.cva.sa", sa, OC_SA, TAGS_C, dsc)

    def sv(b, fac, c, h=0):
        return {"bucket": b, "factor": fac, "s_cva": c, "s_hdg": h}

    def cf(name, tenor, q, **kw):
        return {"name": name, "tenor": tenor, "quality": q, **kw}

    hand(s, "risk.cva.sa", {"reporting_currency": "EUR", "classes": {
        "IR.DELTA": [sv("EUR", "2Y", 4e5), sv("EUR", "inflation", -1e5), sv("NOK", "CURVE", 2e5, 5e4), sv("NOK", "inflation", 3e4)],
        "IR.VEGA": [sv("EUR", "IR_VOL", 2e4), sv("EUR", "INFLATION_VOL", -5e3)]}},
        sa, OC_SA, TAGS_C, "reporting currency EUR specified; NOK unspecified: CURVE and inflation at 1.58%, rho 40%; IR vega rho 40%")
    hand(s, "risk.cva.sa", {"reporting_currency": "USD", "classes": {"CCS.DELTA": [
        sv("1a", cf("S1", "1Y", "IG"), 2e5), sv("1b", cf("M1", "1Y", "HY_NR"), 1e5, 2e4),
        sv("3", cf("N1", "0.5Y", "IG"), -5e4), sv("3", cf("N2", "10Y", "HY_NR", legal_group="G"), 8e4),
        sv("8", cf("IDX", "5Y", "IG", index="CDX.IG", series="S45"), 3e5),
        sv("8", cf("IDX2", "5Y", "IG", index="CDX.IG", series="S44"), 0, 2.5e5),
        sv("8", cf("IDX3", "3Y", "HY_NR", index="CDX.HY", series="S45"), 1e5)]}},
        sa, OC_SA, TAGS_C, "CCS: 1a and 1b share bucket 1 (KR-312); bucket 8 index and series correlations; gamma Table 6")
    hand(s, "risk.cva.sa", {"reporting_currency": "USD", "classes": {
        "RCS.DELTA": [sv("3", "RCS3", 1e5), sv("10", "RCS10", 4e4), sv("15", "RCS15", 1e4), sv("16", "RCS16", -2e4, 1e4)],
        "RCS.VEGA": [sv("1", "V1", 1e3), sv("17", "V17", 2e3)],
        "EQ.DELTA": [sv("5", "EQ5", 1e5), sv("12", "EQ12", -6e4), sv("11", "EQ11", 2e4)],
        "EQ.VEGA": [sv("2", "V2", 1e3), sv("10", "V10", 1e3), sv("12", "V12", 1e3)],
        "COM.DELTA": [sv("2", "C2", 5e4), sv("7", "C7", -3e4), sv("11", "C11", 1e4)],
        "COM.VEGA": [sv("3", "CV3", 500)], "FX.VEGA": [sv("GBP", "GBP", 4e3), sv("JPY", "JPY", -1e3)]}},
        sa, OC_SA, TAGS_C, "RCS across quality (halved gamma), 15, 16; EQ large-cap vega 78% (KR-315); COM with bucket 11; FX vega")
    s.write()


def gen_cva_errors():
    s = Suite("cva_ke", SPEC_C, G)

    def err(op, inp, code, desc, tags=()):
        s.add(op, inp, error=code, cls=E, verified=["hand"], tags=TAGS_C + ["error", *tags], description="hand: " + desc)

    one = [cp("C1", "financials", "IG", (1000000, 5, False))]
    hdg = {"counterparty": "C1", "relation": "DIRECT", "sector": "financials", "quality": "IG", "m": 5, "notional": 500000}
    b = "risk.cva.ba"
    err(b, {"version": "REDUCED", "counterparties": [cp("C1", "financials", "IG", (1000000, 0, False))]}, "E_DOMAIN", "m 0 (spec cva_ke-0001)")
    err(b, {"version": "REDUCED", "counterparties": one, "single_name_hedges": [hdg]}, "E_INPUT", "hedge with REDUCED (spec cva_ke-0002)")
    err(b, {"version": "REDUCED", "counterparties": [cp("C1", "SPACE", "IG", (1000000, 0, False))]}, "E_SCHEMA",
        "two errors: sector SPACE and m 0 (spec cva_ke-0003) [schema] [domain]")
    err(b, {"version": "FULL", "counterparties": one, "single_name_hedges": [{**hdg, "counterparty": "C9"}]}, "E_INPUT", "hedge on an unknown counterparty")
    err(b, {"version": "REDUCED", "counterparties": one + one}, "E_INPUT", "duplicate counterparty id (KR-312)")
    err(b, {"version": "REDUCED", "counterparties": [cp("C1", "financials", "IG", (-1, 5, False))]}, "E_DOMAIN", "negative ead")
    err(b, {"version": "FULL", "counterparties": one, "single_name_hedges": [{**hdg, "notional": -1}]}, "E_DOMAIN", "negative hedge notional")
    err(b, {"version": "FULL", "counterparties": one, "single_name_hedges": [{**hdg, "m": 0}]}, "E_DOMAIN", "hedge m 0")
    idx = {"m": 5, "notional": 1000, "constituents": [{"sector": "financials", "quality": "IG", "weight": 0.9}]}
    err(b, {"version": "FULL", "counterparties": one, "index_hedges": [idx]}, "E_DOMAIN", "index weights sum to 0.9")
    err(b, {"version": "FULL", "counterparties": one, "index_hedges": [{**idx, "constituents": [
        {"sector": "financials", "quality": "IG", "weight": 1.5}, {"sector": "other", "quality": "IG", "weight": -0.5}]}]},
        "E_DOMAIN", "a negative index weight, weights summing to 1 (KR-313)")
    err(b, {"version": "FULL", "counterparties": one, "index_hedges": [{**idx, "m": -1, "constituents": [{"sector": "financials", "quality": "IG", "weight": 1}]}]},
        "E_DOMAIN", "index hedge m negative")
    err(b, {"version": "FULL", "counterparties": one, "index_hedges": [{**idx, "notional": -5, "constituents": [{"sector": "financials", "quality": "IG", "weight": 1}]}]},
        "E_DOMAIN", "index hedge notional negative")
    err(b, {"version": "BASIC", "counterparties": one}, "E_SCHEMA", "version not listed")
    err(b, {"version": "FULL", "counterparties": one, "single_name_hedges": [{**hdg, "relation": "COUSIN"}]}, "E_SCHEMA", "relation not listed")
    err(b, {"version": "REDUCED", "counterparties": [{"id": "C1", "sector": "financials", "quality": "IG"}]}, "E_SCHEMA", "netting_sets missing")
    err(b, {"version": "REDUCED", "counterparties": [cp("C1", "financials", "AA", (1, 1, False))]}, "E_SCHEMA", "quality not listed")
    err(b, {"version": "FULL", "counterparties": [cp("C1", "financials", "IG", (-1, 5, False))], "single_name_hedges": [{**hdg, "counterparty": "X"}]},
        "E_INPUT", "two errors: unknown hedge counterparty and negative ead (structural first) [structural] [domain]")
    err(b, {"version": "REDUCED", "counterparties": [cp("C1", "financials", "IG", ("NaN", 5, False))]}, "E_DOMAIN", "E1: ead NaN", ("e1",))
    err(b, {"version": "REDUCED", "counterparties": [cp("C1", "financials", "IG", (1, "Infinity", False))], "single_name_hedges": [hdg]},
        "E_DOMAIN", "E1, two errors: m Infinity and a hedge with REDUCED (the finite rule first) [finite] [structural]", ("e1",))
    s.write()

    s = Suite("sacva_ke", SPEC_C, G)
    ir = [{"bucket": "USD", "factor": "1Y", "s_cva": 1e6, "s_hdg": 0}]

    def sa_in(classes, **kw):
        return {"reporting_currency": "USD", "classes": classes, **kw}

    def ccs(b="2", **fac):
        return {"bucket": b, "factor": {"name": "X", "tenor": "1Y", "quality": "IG", **fac}, "s_cva": 1e5, "s_hdg": 0}

    o = "risk.cva.sa"
    s_err = lambda inp, code, desc, tags=(): s.add(o, inp, error=code, cls=E, verified=["hand"],  # noqa: E731
                                                   tags=TAGS_C + ["error", *tags], description="hand: " + desc)
    s_err(sa_in({"CCS.VEGA": [ccs()]}), "E_INPUT", "CCS vega (spec sacva_ke-0001)")
    s_err(sa_in({"IR.DELTA": ir}, m_cva=0.9), "E_DOMAIN", "m_cva 0.9 (spec sacva_ke-0002)")
    s_err(sa_in({"IR.GAMMA": ir}), "E_SCHEMA", "kind not listed")
    s_err(sa_in({"XX.DELTA": ir}), "E_SCHEMA", "class not listed")
    s_err(sa_in({"IR.DELTA": [{**ir[0], "factor": "7Y"}]}), "E_SCHEMA", "IR tenor not listed")
    s_err(sa_in({"IR.VEGA": [{**ir[0], "factor": "1Y"}]}), "E_SCHEMA", "IR vega factor not listed (KR-311)")
    s_err(sa_in({"CCS.DELTA": [ccs(tenor="2Y")]}), "E_SCHEMA", "CCS tenor not listed")
    s_err(sa_in({"CCS.DELTA": [ccs(quality="AAA")]}), "E_SCHEMA", "CCS quality not listed")
    s_err(sa_in({"CCS.DELTA": [{**ccs(), "factor": "X"}]}), "E_SCHEMA", "CCS factor given as a string")
    s_err(sa_in({"IR.DELTA": [{"bucket": "USD", "factor": "1Y", "s_cva": 1}]}), "E_SCHEMA", "s_hdg missing")
    s_err(sa_in({"IR.DELTA": ir + ir}), "E_INPUT", "duplicate (bucket, factor)")
    s_err(sa_in({"EQ.DELTA": [{"bucket": "1", "factor": "A", "s_cva": 1, "s_hdg": 0}, {"bucket": "1", "factor": "B", "s_cva": 1, "s_hdg": 0}]}),
          "E_INPUT", "two entries in a one-factor bucket (KR-311)")
    s_err(sa_in({"CCS.DELTA": [ccs("1a"), ccs("1b")]}), "E_INPUT", "one name and tenor in 1a and 1b: the same factor of bucket 1 (KR-312)")
    s_err(sa_in({"IR.DELTA": [{**ir[0], "bucket": "5"}]}), "E_INPUT", "IR bucket that is not a currency (wrong class)")
    s_err(sa_in({"CCS.DELTA": [ccs("9")]}), "E_INPUT", "CCS bucket 9 (wrong class)")
    s_err(sa_in({"RCS.DELTA": [{"bucket": "18", "factor": "R", "s_cva": 1, "s_hdg": 0}]}), "E_INPUT", "RCS bucket 18")
    s_err(sa_in({"COM.VEGA": [{"bucket": "USD", "factor": "R", "s_cva": 1, "s_hdg": 0}]}), "E_INPUT", "commodity bucket USD")
    s_err(sa_in({"FX.DELTA": [{"bucket": "USD", "factor": "USD", "s_cva": 1, "s_hdg": 0}]}), "E_INPUT", "reporting currency as an FX bucket")
    s_err(sa_in({"IR.DELTA": [{**ir[0], "factor": "CURVE"}]}), "E_INPUT", "CURVE in a specified currency (KR-311)")
    s_err(sa_in({"IR.DELTA": [{**ir[0], "bucket": "NOK", "factor": "5Y"}]}), "E_INPUT", "a tenor in an unspecified currency (KR-311)")
    s_err(sa_in({"CCS.DELTA": [ccs("8")]}), "E_INPUT", "bucket 8 factor without index and series")
    s_err(sa_in({"CCS.DELTA": [ccs(), ccs(tenor="5Y", quality="HY_NR")]}), "E_INPUT", "one name with two qualities (KR-314)")
    s_err(sa_in({"IR.DELTA": ir}) | {"reporting_currency": "usd"}, "E_INPUT", "reporting currency not a currency code")
    s_err(sa_in({"CCS.VEGA": [ccs()]}, m_cva=0.9), "E_INPUT", "two errors: CCS vega and m_cva 0.9 (structural first) [structural] [domain]")
    s_err(sa_in({"IR.DELTA": [{**ir[0], "factor": "7Y"}], "CCS.VEGA": [ccs()]}), "E_SCHEMA", "two errors: tenor not listed and CCS vega [schema] [structural]")
    s_err(sa_in({"IR.DELTA": [{**ir[0], "s_cva": "NaN"}]}), "E_DOMAIN", "E1: s_cva NaN", ("e1",))
    s_err(sa_in({"IR.DELTA": [{**ir[0], "s_hdg": "-Infinity"}] + ir}), "E_DOMAIN", "E1, two errors: s_hdg -Infinity and a duplicate factor (the finite rule first) [finite] [structural]", ("e1",))
    s_err(sa_in({"IR.DELTA": ir}, m_cva="NaN"), "E_DOMAIN", "E1: m_cva NaN", ("e1",))
    s.write()


def gen_lev():
    s = Suite("lev_k", SPEC_L, G)

    def base(**parts):
        d = {"tier1": 100, "on_balance": [], "derivatives": [], "written_credit_derivatives": [], "sfts": [], "off_balance": []}
        d.update(parts)
        return d

    printed = [(60, 347, 569, "CRE99.40, p.528", "Example 1"), (20, 3841, 5406, "CRE99.76, p.536", "Example 3"),
               (40, 629, 936, "CRE99.79, p.537", "Example 4")]
    for v, pfe, ead, cre, ex in printed:
        inp = base(derivatives=[{"v": v, "cvm_received": 0, "cvm_provided": 0, "pfe": pfe}])
        hi = lev(inp)
        if not abs(hi["derivatives"] - ead) <= 1:
            stop(f"{cre}: {hi['derivatives']} not within 1.0 of the printed EAD {ead}")
        note_ok(f"{cre} printed EAD {ead}: derivatives {mp.nstr(hi['derivatives'], 8)} within 1.0")
        s.add("risk.capital.leverage", inp, to_float(hi), limit=LIM, output_classes=OC_LEV,
              verified=["hand", ORACLE, f"published: Basel Framework {cre} printed EAD {ead} ({ex}, multiplier 1, unmargined, V >= 0): "
                                        "within 1.0 (spec A1 tolerance, fixed before the run): MATCH", BLIND_K8I],
              tags=TAGS_L + ["outside_checked", "published", "blind"], description=f"derivative netting set of CRE99 {ex} (LEV30.16)")
    for fv, want in ((-10, 90), (5, 100)):
        inp = base(written_credit_derivatives=[{"notional": 100, "fair_value": fv, "purchased_offset": 0}])
        hi = lev(inp)
        if hi["written_credit_derivatives"] != want:
            stop(f"LEV30.31 footnote 384: fair value {fv} gives {hi['written_credit_derivatives']}, printed {want}")
        note_ok(f"LEV30.31 footnote 384, fair value {fv}: effective notional {want}")
        s.add("risk.capital.leverage", inp, to_float(hi), limit=LIM, output_classes=OC_LEV,
              verified=["hand", ORACLE, f"published: LEV30.31 footnote 384 (Basel Framework PDF p.801): effective notional {want}: MATCH", BLIND_K8I],
              tags=TAGS_L + ["outside_checked", "published", "blind"], description=f"written credit derivative, notional 100, fair value {fv}")
    descs = ["off balance sheet CCFs", "SFT with an MNA", "SFT without an MNA", "derivative with CVM received",
             "worked example: ratio above 3%", "worked example with Tier 1 30: ratio below 3%"]
    for n, dsc in enumerate(descs, 6):
        blind(s, f"lev_k-{n:04d}", "risk.capital.leverage", lev, OC_LEV, TAGS_L, dsc)
    hand(s, "risk.capital.leverage", base(tier1=5, on_balance=[40, 0], derivatives=[{"v": -20, "pfe": 10, "cvm_provided": 5}],
         written_credit_derivatives=[{"notional": 50, "fair_value": -4, "purchased_offset": 30}, {"notional": 10, "fair_value": -12}],
         off_balance=[{"notional": 10, "ccf_category": "DIRECT_CREDIT_SUBSTITUTE"}, {"notional": 10, "ccf_category": "FORWARD_PURCHASE"},
                      {"notional": 10, "ccf_category": "OTHER_CREDIT_SUBSTITUTE"}, {"notional": 10, "ccf_category": "TRANSACTION_CONTINGENT"},
                      {"notional": 10, "ccf_category": "TRADE_LC"}]),
         lev, OC_LEV, TAGS_L, "negative V floored at 0 with CVM provided; purchased offset; a written CD reduced to 0; remaining CCFs")
    hand(s, "risk.capital.leverage", {"tier1": 2, "sfts": [{"gross_assets": 0, "mna": False, "exposures": [], "collateral": []},
                                                         {"gross_assets": 30, "mna": True, "exposures": [10], "collateral": [4]}]},
         lev, OC_LEV, TAGS_L, "absent lists are empty (KR-319); an SFT with no transactions")
    s.write()

    s = Suite("lex_k", SPEC_L, G)
    descs = ["10% is large, 25% is not a breach", "a group of two", "CRM substitution to the provider", "trading book (worked example)",
             "net short counts 0", "CCF floor 10%", "G-SIB to G-SIB limit 15%"]
    for n, dsc in enumerate(descs, 1):
        blind(s, f"lex_k-{n:04d}", "risk.capital.large_exposures", lex, OC_LEX, TAGS_L, dsc)
    many = [{"id": f"N{n:02d}"} for n in range(23)]
    hand(s, "risk.capital.large_exposures", {"tier1": 1000, "counterparties": many + [
        {"id": "X", "group": "GX", "exempt": True}, {"id": "Y", "group": "GX"}, {"id": "Z", "exempt": True}],
        "banking_book": [{"counterparty": f"N{n:02d}", "value": 10 + n} for n in range(23)] + [
            {"counterparty": "X", "value": 200}, {"counterparty": "Y", "value": 100}, {"counterparty": "Z", "value": 400}]},
        lex, OC_LEX, TAGS_L, "report: large groups plus the 20 largest, ties by name; exempt members never breach (KR-325)")
    hand(s, "risk.capital.large_exposures", {"tier1": 400, "bank_gsib": True, "counterparties": [
        {"id": "P", "group": "GP", "gsib": True}, {"id": "Q", "group": "GP"}, {"id": "R"}],
        "off_balance": [{"counterparty": "R", "notional": 100, "ccf": 0.5}],
        "trading_book": [
            {"id": "b1", "counterparty": "P", "seniority": "COVERED", "notional": 20, "market_value": 21},
            {"id": "b2", "counterparty": "P", "seniority": "NON_SENIOR", "notional": 30, "market_value": 25},
            {"id": "s1", "counterparty": "P", "seniority": "SENIOR", "notional": -15, "market_value": -14},
            {"id": "s2", "counterparty": "P", "seniority": "EQUITY", "notional": -40, "market_value": -40, "cash_equity": True},
            {"id": "c1", "counterparty": "Q", "seniority": "SENIOR", "notional": 0, "market_value": 3}],
        "crm": [{"counterparty": "R", "provider": "Q", "protected": 20}]},
        lex, OC_LEX, TAGS_L, "KR-53 offsets across ranks; a G-SIB member makes the group G-SIB (KR-324); notional 0 is long (KR-323)")
    # KR-324 confirmed 2026-11-20: a mixed group (one member G-SIB, one not) between 15% and 25% of Tier 1 breaches
    # under "any member" (limit 150) and would not under "every member" (limit 250); GN is the all-non-G-SIB contrast.
    hand(s, "risk.capital.large_exposures", {"tier1": 1000, "bank_gsib": True, "counterparties": [
        {"id": "M1", "group": "GM", "gsib": True}, {"id": "M2", "group": "GM"},
        {"id": "N1", "group": "GN"}, {"id": "N2", "group": "GN"}],
        "banking_book": [{"counterparty": c, "value": 100} for c in ("M1", "M2", "N1", "N2")]},
        lex, OC_LEX, TAGS_L, "mixed group: one G-SIB member and one not, exposure 20% of Tier 1, breaches the 15% limit (KR-324 any member)",
        rederived=False)
    # KR-326 (confirmed 2026-11-21): group labels in code-point order. U+FFFF sorts before U+1F600 by code point
    # (and by UTF-8 bytes), but after it in UTF-16 order (the surrogate 0xD83D is below 0xFFFF). Equal exposures, so
    # the report's tie-break by label shows the order too.
    hand(s, "risk.capital.large_exposures", {"tier1": 1000, "counterparties": [
        {"id": "A", "group": "😀"}, {"id": "B", "group": "￿"}, {"id": "C", "group": "￿"}],
        "banking_book": [{"counterparty": "A", "value": 50}, {"counterparty": "B", "value": 20},
                         {"counterparty": "C", "value": 30}]},
        lex, OC_LEX, TAGS_L, "group labels U+FFFF and U+1F600 with equal exposures: code-point order, not UTF-16 order (KR-326)",
        rederived=False)
    s.write()


def gen_lev_errors():
    s = Suite("lev_ke", SPEC_L, G)
    L, X = "risk.capital.leverage", "risk.capital.large_exposures"

    def err(op, inp, code, desc, tags=()):
        s.add(op, inp, error=code, cls=E, verified=["hand"], tags=TAGS_L + ["error", *tags], description="hand: " + desc)

    ok = {"tier1": 10, "on_balance": [100]}
    sft = {"gross_assets": 1, "mna": True, "exposures": [1, 2], "collateral": [1]}
    err(L, {**ok, "tier1": 0}, "E_DOMAIN", "tier1 0 (spec lev_ke-0001)")
    err(L, {**ok, "sfts": [sft]}, "E_INPUT", "exposures and collateral of lengths 2 and 1 (spec lev_ke-0002)")
    err(L, {**ok, "off_balance": [{"notional": -1, "ccf_category": "GUARANTEE"}]}, "E_SCHEMA",
        "two errors: unlisted CCF category and a negative notional (spec lev_ke-0003) [schema] [domain]")
    for field, item, key in (("on_balance", None, None), ("derivatives", {"v": 1, "pfe": 1}, "pfe"),
                             ("derivatives", {"v": 1, "pfe": 1, "cvm_received": 1}, "cvm_received"),
                             ("derivatives", {"v": 1, "pfe": 1, "cvm_provided": 1}, "cvm_provided"),
                             ("written_credit_derivatives", {"notional": 1, "fair_value": 0}, "notional"),
                             ("written_credit_derivatives", {"notional": 1, "fair_value": 0, "purchased_offset": 1}, "purchased_offset"),
                             ("sfts", {"gross_assets": 1, "mna": False, "exposures": [1], "collateral": [1]}, "gross_assets"),
                             ("sfts", {"gross_assets": 1, "mna": False, "exposures": [1], "collateral": [1]}, "exposures"),
                             ("sfts", {"gross_assets": 1, "mna": False, "exposures": [1], "collateral": [1]}, "collateral"),
                             ("off_balance", {"notional": 1, "ccf_category": "COMMITMENT"}, "notional")):
        if item is None:
            err(L, {**ok, "on_balance": [100, -1]}, "E_DOMAIN", "negative on-balance value")
            continue
        bad = dict(item)
        bad[key] = [-1] if key in ("exposures", "collateral") else -1
        err(L, {**ok, field: [bad]}, "E_DOMAIN", f"negative {key} in {field}")
    err(L, {"tier1": 1}, "E_DOMAIN", "exposure measure zero: no ratio (KR-321)")
    err(L, {**ok, "sfts": [{"gross_assets": 1, "exposures": [], "collateral": []}]}, "E_SCHEMA", "mna missing")
    err(L, {**ok, "tier1": 0, "sfts": [sft]}, "E_INPUT", "two errors: lengths differ and tier1 0 (structural first) [structural] [domain]")
    err(L, {**ok, "derivatives": [{"v": "NaN", "pfe": 1}]}, "E_DOMAIN", "E1: v NaN", ("e1",))
    err(L, {**ok, "tier1": "Infinity", "sfts": [sft]}, "E_DOMAIN", "E1, two errors: tier1 Infinity and lengths differ (the finite rule first) [finite] [structural]", ("e1",))
    s.write()

    s = Suite("lex_ke", SPEC_L, G)

    def err(op, inp, code, desc, tags=()):  # noqa: F811
        s.add(op, inp, error=code, cls=E, verified=["hand"], tags=TAGS_L + ["error", *tags], description="hand: " + desc)

    cps = [{"id": "A"}, {"id": "B"}]
    base = {"tier1": 1000, "counterparties": cps, "banking_book": [{"counterparty": "A", "value": 10}]}
    pos = {"id": "p", "counterparty": "A", "seniority": "SENIOR", "notional": 10, "market_value": 9}
    err(X, {**base, "counterparties": [{"id": "A", "group": "G1"}, {"id": "A", "group": "G2"}]}, "E_INPUT", "counterparty in two groups (spec lex_ke-0001)")
    err(X, {**base, "off_balance": [{"counterparty": "A", "notional": 10, "ccf": 1.5}]}, "E_DOMAIN", "ccf 1.5 (spec lex_ke-0002)")
    err(X, {**base, "banking_book": [{"counterparty": "Q", "value": 1}]}, "E_INPUT", "banking book on an unknown counterparty")
    err(X, {**base, "crm": [{"counterparty": "A", "provider": "Q", "protected": 1}]}, "E_INPUT", "unknown protection provider")
    err(X, {**base, "crm": [{"counterparty": "A", "provider": "A", "protected": 1}]}, "E_INPUT", "a counterparty protecting itself")
    err(X, {**base, "trading_book": [pos, pos]}, "E_INPUT", "duplicate position id")
    err(X, {**base, "trading_book": [{**pos, "counterparty": "Q"}]}, "E_INPUT", "trading position on an unknown counterparty")
    err(X, {**base, "counterparties": [{"id": "A", "group": "B"}, {"id": "B"}]}, "E_INPUT", "group named like a counterparty outside it (KR-324)")
    err(X, {**base, "tier1": 0}, "E_DOMAIN", "tier1 0")
    err(X, {**base, "banking_book": [{"counterparty": "A", "value": -1}]}, "E_DOMAIN", "negative banking book value")
    err(X, {**base, "off_balance": [{"counterparty": "A", "notional": -1, "ccf": 0.5}]}, "E_DOMAIN", "negative off-balance notional")
    err(X, {**base, "off_balance": [{"counterparty": "A", "notional": 1, "ccf": -0.1}]}, "E_DOMAIN", "ccf below 0")
    err(X, {**base, "crm": [{"counterparty": "A", "provider": "B", "protected": -1}]}, "E_DOMAIN", "negative protected amount")
    err(X, {**base, "crm": [{"counterparty": "A", "provider": "B", "protected": 11}]}, "E_DOMAIN", "protection above the exposure (KR-325)")
    err(X, {**base, "trading_book": [{**pos, "seniority": "SUPER"}]}, "E_SCHEMA", "seniority not listed")
    err(X, {"tier1": 1000}, "E_SCHEMA", "counterparties missing")
    err(X, {**base, "tier1": 0, "banking_book": [{"counterparty": "Q", "value": 1}]}, "E_INPUT", "two errors: unknown counterparty and tier1 0 [structural] [domain]")
    err(X, {**base, "trading_book": [{**pos, "seniority": "SUPER"}], "off_balance": [{"counterparty": "A", "notional": 1, "ccf": 1.5}]},
        "E_SCHEMA", "two errors: seniority not listed and ccf 1.5 [schema] [domain]")
    err(X, {**base, "trading_book": [{**pos, "market_value": "NaN"}]}, "E_DOMAIN", "E1: market value NaN", ("e1",))
    err(X, {**base, "banking_book": [{"counterparty": "Q", "value": "-Infinity"}]}, "E_DOMAIN",
        "E1, two errors: value -Infinity and an unknown counterparty (the finite rule first) [finite] [structural]", ("e1",))
    s.write()


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    try:
        gen_cva()
        gen_cva_errors()
        gen_lev()
        gen_lev_errors()
    finally:
        common.GOLDEN = keep
    blind_ids = [c for c in EXPECTED if EXPECTED[c]["item"] in ("K-8g", "K-8i")]
    common.note(f"blind expected values asserted: {len(blind_ids)} cases")


if __name__ == "__main__":
    main()
