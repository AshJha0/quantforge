"""Stage K wave 1b goldens: SA-CCR (K-8d, suite saccr_k), FRTB IMA backtesting (K-8e, suite btk_k) and
the MAR99 Table 2 outside check of the existing stage F operation risk.backtest.traffic_light
(suite tlk_k).

Specs: specifications/06-risk/sa-ccr.md, specifications/06-risk/frtb-ima-backtest.md; rulings
specifications/stage-k-rulings-w1b.md (KR-30 to KR-47). This oracle is written from the specs and the
Basel Framework text, in mpmath at 50 digits, with the quadratic forms written as sums over index pairs;
it does not import quantforge_core. Published checks: the CRE99 worked examples (Basel Framework PDF
generated 11/11/2026, pages 524 to 540, read 2026-11-19) and the BCBS 279 Annex 4a figures recorded in
institutional-quant-engine-plan/STAGE_K_SOURCES.md (read 2026-11-15); MAR99 Tables 1 and 2 (PDF pages
756 and 758). Independent library: scipy.stats.binom (cdf and pmf). The generator stops if any
published figure fails to reproduce under the acceptance rule of the spec.

    cd oracle/python && uv run python -W ignore gen_stage_k_w1b.py
"""
import json
from pathlib import Path

import mpmath as mp
from scipy.stats import binom

from qf_oracle import common
from qf_oracle.common import Suite, f

mp.mp.dps = 50
G = "oracle/python/gen_stage_k_w1b.py"
SPEC_S = "specifications/06-risk/sa-ccr.md"
SPEC_B = "specifications/06-risk/frtb-ima-backtest.md"
ROOT = Path(__file__).resolve().parents[2]
PARAMS = json.loads((ROOT / "specifications/06-risk/sa-ccr-parameters.json").read_text("utf-8"))
TABLES = json.loads((ROOT / "specifications/06-risk/frtb-ima-backtest-tables.json").read_text("utf-8"))
T2 = {(r["asset_class"], r["subclass"]): r for r in PARAMS["table2"]}
ORACLE = "mpmath 50 digits (independent oracle, gen_stage_k_w1b.py)"
SCIPY = "scipy.stats.binom 1.x (independent library)"
CLS_ORDER = ["IR", "FX", "CREDIT", "EQUITY", "COMMODITY"]
TR_ORDER = ["NORMAL", "BASIS", "VOLATILITY"]
SCALE = {"NORMAL": mp.mpf(1), "BASIS": mp.mpf("0.5"), "VOLATILITY": mp.mpf(5)}
TAGS_S = ["stage_k", "saccr"]
TAGS_B = ["stage_k", "frtb_backtest"]


def M(x):
    return mp.mpf(str(x))


def row(t):
    return T2[(t["asset_class"], t.get("subclass"))]


def delta(t):
    kind = t.get("kind", "LINEAR")
    if kind == "LINEAR":
        return mp.mpf(1) if t["position"] == "LONG" else mp.mpf(-1)
    if kind == "CDO":
        v = mp.mpf(15) / ((1 + 14 * M(t["attachment"])) * (1 + 14 * M(t["detachment"])))
        return v if t["position"] == "BOUGHT" else -v
    sig = M(row(t)["option_volatility"])
    T = M(t["exercise"])
    lam = M(t.get("shift", 0))
    d1 = (mp.log((M(t["underlying_price"]) + lam) / (M(t["strike"]) + lam)) + sig ** 2 * T / 2) / (sig * mp.sqrt(T))
    s = 1 if t["position"] == "BOUGHT" else -1
    return s * (mp.ncdf(d1) if t["option_type"] == "CALL" else -mp.ncdf(-d1))


def mpor_of(margin, n):
    rd = margin["remargin_days"]
    fl = 10 if rd == 1 else 9 + rd
    if n > 5000 or margin.get("illiquid", False):
        fl = max(fl, 20)
    if margin.get("disputes", False):
        fl *= 2
    return max(fl, margin.get("mpor_days") or 0)


def sa_ccr(inp):
    """Returns (outputs at 50 digits as mpf, the same rounded to binary64)."""
    trades = inp["trades"]
    C = M(inp.get("collateral", 0))
    V = mp.fsum(M(t["market_value"]) for t in trades)
    floor_y = mp.mpf(10) / 250
    sd, d = [], []
    for t in trades:
        if t["asset_class"] in ("IR", "CREDIT"):
            s = (mp.e ** (-M("0.05") * M(t["start"])) - mp.e ** (-M("0.05") * M(t["end"]))) / M("0.05")
            s = max(s, floor_y)
            sd.append(s)
            d.append(M(t["notional"]) * s)
        else:
            sd.append(None)
            d.append(M(t["notional"]))
    dl = [delta(t) for t in trades]
    mf_un = [mp.sqrt(min(max(M(t["maturity"]), floor_y), 1)) for t in trades]

    def addon(mf):
        D = [d[i] * mf[i] * dl[i] for i in range(len(trades))]
        sets = {}
        for i, t in enumerate(trades):
            tr = t.get("treatment", "NORMAL")
            c = t["asset_class"]
            if tr == "BASIS" or c in ("IR", "FX"):  # KR-236: VOLATILITY sets follow CRE52.45 (CRE52.47)
                key = t["hedging_set"]
            elif c == "COMMODITY":
                key = row(t)["hedging_set"]
            else:
                key = ""
            sets.setdefault((c, tr, key), []).append(i)
        out, per = [], {c: mp.mpf(0) for c in CLS_ORDER}
        for (c, tr, key) in sorted(sets, key=lambda k: (CLS_ORDER.index(k[0]), TR_ORDER.index(k[1]), k[2])):
            idx = sets[(c, tr, key)]
            if c == "IR":
                B = [mp.mpf(0)] * 3
                for i in idx:
                    E = M(trades[i]["end"])
                    b = 0 if E < 1 else (1 if E <= 5 else 2)
                    B[b] += D[i]
                if inp.get("ir_offset", True):
                    rho = [[1, M("0.7"), M("0.3")], [M("0.7"), 1, M("0.7")], [M("0.3"), M("0.7"), 1]]
                    q = mp.fsum(rho[a][b] * B[a] * B[b] for a in range(3) for b in range(3))
                    en = mp.sqrt(max(q, 0))
                else:
                    en = mp.fsum(abs(x) for x in B)
                a_hs = M("0.005") * SCALE[tr] * en
            elif c == "FX":
                a_hs = M("0.04") * SCALE[tr] * abs(mp.fsum(D[i] for i in idx))
            else:
                ent = {}
                for i in idx:
                    ent.setdefault(trades[i]["entity"], []).append(i)
                sysc, idio = mp.mpf(0), mp.mpf(0)
                for name in ent:
                    r = row(trades[ent[name][0]])
                    a = M(r["supervisory_factor"]) * SCALE[tr] * mp.fsum(D[i] for i in ent[name])
                    rho = M(r["correlation"])
                    sysc += rho * a
                    idio += (1 - rho ** 2) * a ** 2
                a_hs = mp.sqrt(sysc ** 2 + idio)
            per[c] += a_hs
            out.append({"asset_class": c, "treatment": tr, "key": key, "addon": a_hs})
        return D, per, out

    def netting(mf, rc):
        D, per, hs = addon(mf)
        agg = mp.fsum(per.values())
        x = V - C
        if x >= 0:
            m = mp.mpf(1)
        elif agg == 0:
            m = M("0.05")
        else:
            m = mp.mpf(min(1, M("0.05") + M("0.95") * mp.e ** (x / (2 * M("0.95") * agg))))
        pfe = m * agg
        return M("1.4") * (rc + pfe), pfe, m, per, hs, D, agg

    rc_un = mp.mpf(max(V - C, 0))
    un = netting(mf_un, rc_un)
    margin = inp.get("margin")
    if margin is None:
        res, mf, rc, mpor, ead_un, capped = un, mf_un, rc_un, None, None, False
    else:
        mpor = mpor_of(margin, len(trades))
        mf = [M("1.5") * mp.sqrt(mp.mpf(mpor) / 250)] * len(trades)
        rc = mp.mpf(max(V - C, M(margin["threshold"]) + M(margin["mta"]) - M(margin["nica"]), 0))
        res = netting(mf, rc)
        ead_un, capped = un[0], un[0] < res[0]
    ead, pfe, m, per, hs, D, agg = res
    out = {
        "ead": min(ead, ead_un) if ead_un is not None else ead, "rc": rc, "pfe": pfe, "multiplier": m,
        "addon_aggregate": agg, "addon": per, "v": V, "c": C, "margined": margin is not None,
        "mpor_days": mpor, "ead_unmargined": ead_un, "capped": capped, "hedging_sets": hs,
        "trades": [{"id": t["id"], "supervisory_duration": sd[i], "adjusted_notional": d[i], "maturity_factor": mf[i],
                    "delta": dl[i], "effective_notional": D[i],
                    "supervisory_factor": M(row(t)["supervisory_factor"]) * SCALE[t.get("treatment", "NORMAL")]}
                   for i, t in enumerate(trades)],
    }
    return out, to_float(out)


def to_float(x):
    if isinstance(x, dict):
        return {k: to_float(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_float(v) for v in x]
    if isinstance(x, mp.mpf):
        return f(x)
    return x


def tr(id_, cls, notional, mv, mat, **kw):
    t = {"id": id_, "asset_class": cls, "notional": notional, "market_value": mv, "maturity": mat, "position": "LONG"}
    t.update(kw)
    return t


EX1 = [tr("1", "IR", 10000, 30, 10, start=0, end=10, hedging_set="USD"),
       tr("2", "IR", 10000, -20, 4, position="SHORT", start=0, end=4, hedging_set="USD"),
       tr("3", "IR", 5000, 50, 11, kind="OPTION", position="BOUGHT", option_type="PUT", underlying_price=0.06,
          strike=0.05, exercise=1, start=1, end=11, hedging_set="EUR")]
EX2 = [tr("4", "CREDIT", 10000, 20, 3, start=0, end=3, entity="Firm A", subclass="AA"),
       tr("5", "CREDIT", 10000, -40, 6, position="SHORT", start=0, end=6, entity="Firm B", subclass="BBB"),
       tr("6", "CREDIT", 10000, 0, 5, start=0, end=5, entity="CDX.IG", subclass="IG")]
EX3 = [tr("7", "COMMODITY", 10000, -50, 0.75, entity="CRUDE_OIL", subclass="OIL_GAS"),
       tr("8", "COMMODITY", 20000, -30, 2, position="SHORT", entity="CRUDE_OIL", subclass="OIL_GAS"),
       tr("9", "COMMODITY", 10000, 100, 5, entity="SILVER", subclass="METALS")]
WEEKLY = {"threshold": 0, "mta": 5, "nica": 150, "remargin_days": 5}


def near(x, printed, digits=0):
    """Acceptance rule KR-30: full precision, rounded half away from zero to the printed digits."""
    q = mp.mpf(10) ** digits
    v = mp.floor(abs(x) * q + mp.mpf("0.5")) / q
    return (v if x >= 0 else -v) == mp.mpf(str(printed))


def check(cond, what):
    if not cond:
        raise SystemExit(f"published check FAILED: {what}")
    common.note(f"  published check MATCH: {what}")


# (inputs, printed EAD, CRE99 paragraph and PDF page, BCBS 279 PDF page)
EXAMPLES = [
    ({"trades": EX1}, 569, "CRE99.40, p.528", "26-28"),
    ({"trades": EX2}, 381, "CRE99.58, p.532", "28-30"),
    ({"trades": EX3}, 5406, "CRE99.76, p.536", "31-32"),
    ({"trades": EX1 + EX2}, 936, "CRE99.79, p.537", "32-33"),
    ({"trades": EX1 + EX3, "collateral": 200, "margin": WEEKLY}, 1879, "CRE99.97, p.540", "33-34"),
]


def published_intermediates(outs):
    o1, o2, o3, o4, o5 = outs
    t1 = o1["trades"]
    check(all(near(t1[i]["adjusted_notional"], v) for i, v in enumerate([78694, 36254, 37428])), "CRE99.29 d = 78,694 / 36,254 / 37,428")
    check(all(near(t1[i]["supervisory_duration"], v, 2) for i, v in enumerate(["7.87", "3.63", "7.49"])), "CRE99.29 SD = 7.87 / 3.63 / 7.49")
    check(near(t1[2]["delta"], "-0.2694", 4), "CRE99.31 swaption delta -0.2694")
    check(all(near(t1[i]["effective_notional"], v) for i, v in enumerate([78694, -36254, -10083])), "CRE99.32 D = 78,694 / -36,254 / -10,083")
    hs = {h["key"]: h["addon"] for h in o1["hedging_sets"]}
    check(near(hs["USD"] / M("0.005"), 59270) and near(hs["EUR"] / M("0.005"), 10083), "CRE99.37 EN_USD 59,270, EN_EUR 10,083")
    check(near(hs["USD"], "296.35", 2) and near(hs["EUR"], "50.415", 3), "CRE99.38 add-ons 296.35 / 50.415")
    check(near(o1["addon_aggregate"], 347) and o1["rc"] == 60, "CRE99.39-40 AddOn_IR 347, RC 60")
    t2 = o2["trades"]
    check(all(near(t2[i]["adjusted_notional"], v) for i, v in enumerate([27858, 51836, 44240])), "CRE99.47 d = 27,858 / 51,836 / 44,240")
    check(all(near(t2[i]["supervisory_duration"], v, 2) for i, v in enumerate(["2.79", "5.18", "4.42"])), "CRE99.47 SD = 2.79 / 5.18 / 4.42")
    a = [M("0.0038") * t2[0]["effective_notional"], M("0.0054") * t2[1]["effective_notional"], M("0.0038") * t2[2]["effective_notional"]]
    check([near(x, v) for x, v in zip(a, [106, -280, 168])] == [True] * 3, "CRE99.52 entity add-ons 106 / -280 / 168")
    rho = [M("0.5"), M("0.5"), M("0.8")]
    s = mp.fsum(r * x for r, x in zip(rho, a))
    i_ = mp.fsum((1 - r * r) * x * x for r, x in zip(rho, a))
    check(near(s, "47.5", 1) and near(s * s, 2253) and near(i_, 77344), "CRE99.54-55 systematic 47.5 (2,253), idiosyncratic 77,344")
    check(near(o2["addon_aggregate"], 282) and near(o2["multiplier"], "0.965", 3) and o2["rc"] == 0, "CRE99.55-57 AddOn 282, multiplier 0.965, RC 0")
    t3 = o3["trades"]
    check(near(t3[0]["effective_notional"], 8660), "CRE99.66 D_1 = 8,660 (MF sqrt(9/12))")
    hs3 = {h["key"]: h["addon"] for h in o3["hedging_sets"]}
    check(near(t3[0]["effective_notional"] + t3[1]["effective_notional"], -11340), "CRE99.68 EN crude oil -11,340")
    check(near(hs3["ENERGY"], 2041) and near(hs3["METALS"], 1800) and near(o3["addon_aggregate"], 3841) and o3["rc"] == 20, "CRE99.69-74 energy 2,041, metals 1,800, total 3,841, RC 20")
    check(near(o4["addon_aggregate"], 629) and o4["rc"] == 40, "CRE99.77-78 RC 40, AddOn 629")
    t5 = o5["trades"]
    check(o5["mpor_days"] == 14 and o5["rc"] == 0 and o5["v"] == 80, "CRE99.82-83 V 80, RC 0, MPOR 14")
    check(all(near(t5[i]["effective_notional"], v) for i, v in [(0, 27934), (1, -12869), (2, -3579), (3, 3550), (5, 3550)]), "CRE99.85/99.90 D = 27,934 / -12,869 / -3,579 / 3,550 / 3,550")
    # CRE99.90 prints -7,100 for the Brent forward: 2 x the rounded 3,550; full precision -7,099.30 (KR-31)
    check(abs(t5[4]["effective_notional"] + 7100) < 1 and near(t5[4]["effective_notional"], -7099), "CRE99.90 D_Brent printed -7,100 vs -7,099.30: within 1 (source rounding, KR-31)")
    hs5 = {(h["asset_class"], h["key"]): h["addon"] for h in o5["hedging_sets"]}
    check(near(hs5[("IR", "USD")] / M("0.005"), 21039) and near(hs5[("IR", "EUR")] / M("0.005"), 3579), "CRE99.87 EN_USD 21,039, EN_EUR 3,579")
    check(near(hs5[("IR", "USD")], 105) and near(hs5[("IR", "EUR")], 18) and near(o5["addon"]["IR"], 123), "CRE99.88-89 105 + 18 = 123")
    check(near(hs5[("COMMODITY", "ENERGY")], 639) and near(hs5[("COMMODITY", "METALS")], 639) and near(o5["addon"]["COMMODITY"], 1278), "CRE99.92-94 639 + 639 = 1,278")
    check(near(o5["addon_aggregate"], 1401) and near(o5["multiplier"], "0.958", 3), "CRE99.95-96 AddOn 1,401, multiplier 0.958")


BLIND_W1B = "blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_W1B.md): MATCH"
# K-8e blind lane (program/STAGE_K_BLIND_BTK.md, packet manifest 03fdc75d, compare fixed at 21392489): 12 of 12 MATCH,
# 11 counted. btk_k-0017 (one observation) matched but is not counted: the rules text states its answer.
BLIND_BTK = "blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_BTK.md): MATCH"


def gen_saccr():
    s = Suite("saccr_k", SPEC_S, G)
    oc = {"margined": "date_and_convention", "capped": "date_and_convention", "mpor_days": "date_and_convention"}
    hp = []
    for inp, printed, cre, bcbs in EXAMPLES:
        hi, lo = sa_ccr(inp)
        hp.append(hi)
        check(near(hi["ead"], printed), f"{cre} printed EAD {printed} (ead {mp.nstr(hi['ead'], 10)})")
        s.add("risk.saccr.ead", inp, lo, verified=[
            ORACLE, f"published: Basel Framework {cre} printed EAD {printed}: MATCH at nearest integer (KR-30)",
            f"published: BCBS 279 Annex 4a, PDF pp.{bcbs} (read 2026-11-15, STAGE_K_SOURCES.md) EAD {printed}: MATCH"],
            tags=TAGS_S + ["outside_checked", "published"], output_classes=oc,
            description=f"CRE99 worked example, printed EAD {printed} ({cre})")
    published_intermediates(hp)

    def hand(inp, desc, blind=False):
        _, lo = sa_ccr(inp)
        # blind: one of the seven cases counted by the DR-H2 blind lane (program/STAGE_K_BLIND_W1B.md); the other four
        # hand cases matched too but are not counted (the lane had read output facts for them, a recorded process failure)
        verified = ["hand", ORACLE] + ([BLIND_W1B] if blind else [])
        s.add("risk.saccr.ead", inp, lo, verified=verified, tags=TAGS_S + ["hand"], output_classes=oc, description="hand: " + desc)

    hand({"trades": EX1, "ir_offset": False}, "Example 1 with the no-offset IR formula (CRE52.57 step 5)")
    hand({"trades": [tr("f1", "FX", 1000, 12, 0.5, hedging_set="EURUSD"),
                     tr("f2", "FX", 600, -5, 2, position="SHORT", hedging_set="EURUSD"),
                     tr("f3", "FX", 800, 3, 1, kind="OPTION", position="SOLD", option_type="CALL", underlying_price=1.1,
                        strike=1.15, exercise=0.75, hedging_set="USDJPY")]},
         "FX forwards netting in one pair, sold call in a second pair", blind=True)
    hand({"trades": [tr("e1", "EQUITY", 500, 20, 1, entity="ACME", subclass="SINGLE"),
                     tr("e2", "EQUITY", 300, -4, 0.5, position="SHORT", entity="ACME", subclass="SINGLE"),
                     tr("e3", "EQUITY", 1000, 7, 2, kind="OPTION", position="BOUGHT", option_type="PUT",
                        underlying_price=4000, strike=3800, exercise=0.5, entity="SPX", subclass="INDEX")],
          "collateral": 10}, "equity single name netting plus an index put; collateral 10", blind=True)
    hand({"trades": [tr("c1", "CREDIT", 1000, 5, 5, kind="CDO", position="BOUGHT", attachment=0.03, detachment=0.07,
                        start=0, end=5, entity="ITRAXX 3-7", subclass="IG"),
                     tr("c2", "CREDIT", 500, -2, 3, kind="CDO", position="SOLD", attachment=0.25, detachment=0.5,
                        start=0, end=3, entity="FTD basket", subclass="SG"),
                     tr("c3", "CREDIT", 800, 1, 0.02, start=0, end=0.02, entity="Firm C", subclass="CCC")]},
         "CDO tranche bought, second-to-default sold (A = 1/4, D = 1/2), floored M and SD", blind=True)
    hand({"trades": [tr("p1", "COMMODITY", 400, 3, 1, entity="POWER", subclass="ELECTRICITY"),
                     tr("p2", "COMMODITY", 400, -1, 1, position="SHORT", entity="GAS", subclass="OIL_GAS"),
                     tr("p3", "COMMODITY", 250, 0, 1, entity="CORN", subclass="AGRICULTURAL"),
                     tr("p4", "COMMODITY", 250, 0, 1, treatment="BASIS", hedging_set="BRENT/HENRY HUB", entity="BRENT/HH",
                        subclass="OIL_GAS")]},
         "electricity and gas offset within energy; agriculture alone; a basis hedging set at half the factor", blind=True)
    hand({"trades": [tr("v1", "EQUITY", 100, 0, 1, treatment="VOLATILITY", hedging_set="EQ VOL", entity="VIX", subclass="INDEX"),
                     tr("i1", "IR", 1000, 0, 3, start=0, end=3, treatment="BASIS", hedging_set="USD SOFR/TBILL")]},
         "a volatility hedging set at five times the factor; an IR basis set at half", blind=True)
    hand({"trades": [tr("n1", "IR", 1000, 2, 2, kind="OPTION", position="BOUGHT", option_type="CALL",
                        underlying_price=-0.002, strike=0.001, exercise=1, shift=0.01, start=1, end=2, hedging_set="EUR"),
                     tr("n2", "IR", 2000, -3, 0.5, start=0, end=0.5, hedging_set="EUR"),
                     tr("n3", "IR", 2000, 1, 7, position="SHORT", start=0, end=7, hedging_set="EUR")]},
         "shifted IR option at negative rates (CRE52.40 FAQ2) and all three maturity buckets", blind=True)
    hand({"trades": EX1 + EX3, "collateral": 200,
          "margin": {"threshold": 0, "mta": 5, "nica": 150, "remargin_days": 1, "illiquid": True, "disputes": True}},
         "Example 5 netting set, daily margin, illiquid and disputed: MPOR floor 40")
    hand({"trades": EX1 + EX3, "collateral": 200, "margin": {"threshold": 0, "mta": 5, "nica": 150, "remargin_days": 1, "mpor_days": 15}},
         "Example 5 netting set, daily margin, own MPOR estimate 15 above the floor 10", blind=True)
    hand({"trades": [tr("s1", "IR", 1000, 1, 0.02, start=0, end=0.02, hedging_set="USD")],
          "margin": {"threshold": 1000000, "mta": 0, "nica": 0, "remargin_days": 1}},
         "margined EAD above the unmargined EAD is capped (CRE52.2)")
    hand({"trades": [tr("z1", "FX", 1000, -10, 1, hedging_set="GBPUSD"), tr("z2", "FX", 1000, 0, 1, position="SHORT", hedging_set="GBPUSD")]},
         "exactly offsetting FX trades: zero add-on, multiplier at its floor 0.05 (KR-36)")
    AUDIT_W1B = ("added by the audit-response lane 2026-11-19 (STAGE_K_R1_AUDIT_A.md; rulings KR-236 to KR-238): hand and "
                 "oracle, not blind re-derived")

    def err(inp, code, desc):
        two = ["two-errors"] if "two errors" in desc else []
        s.add("risk.saccr.ead", inp, error=code, cls="date_and_convention", verified=["hand"], tags=TAGS_S + ["error"] + two,
              description="hand: " + desc)

    ok = tr("a", "FX", 100, 0, 1, hedging_set="EURUSD")
    err({"trades": []}, "E_INPUT", "no trades")
    err({"trades": [ok, ok]}, "E_INPUT", "duplicate trade id")
    err({"trades": [tr("a", "IR", 100, 0, 1, hedging_set="USD")]}, "E_INPUT", "IR trade without start and end")
    err({"trades": [tr("a", "FX", 100, 0, 1)]}, "E_INPUT", "FX trade without a currency pair")
    err({"trades": [tr("a", "EQUITY", 100, 0, 1, entity="X", subclass="IG")]}, "E_INPUT", "credit subclass on an equity trade")
    err({"trades": [tr("a", "EQUITY", 100, 0, 1, entity="X", subclass="SINGLE"), tr("b", "EQUITY", 100, 0, 1, entity="X", subclass="INDEX")]},
        "E_INPUT", "one entity with two subclasses")
    err({"trades": [{**ok, "position": "BOUGHT"}]}, "E_INPUT", "option position on a linear trade")
    err({"trades": [{**ok, "asset_class": "RATES"}]}, "E_SCHEMA", "unknown asset class")
    err({"trades": [{k: v for k, v in ok.items() if k != "position"}]}, "E_SCHEMA", "position missing")
    err({"trades": "x"}, "E_SCHEMA", "trades not an array")
    err({"trades": [{**ok, "notional": 0}]}, "E_DOMAIN", "zero notional")
    err({"trades": [{**ok, "maturity": -1}]}, "E_DOMAIN", "negative maturity")
    err({"trades": [tr("a", "IR", 100, 0, 1, start=2, end=1, hedging_set="USD")]}, "E_DOMAIN", "start after end")
    err({"trades": [tr("a", "FX", 100, 0, 1, kind="OPTION", position="BOUGHT", option_type="CALL", underlying_price=1, strike=0, exercise=1, hedging_set="EURUSD")]},
        "E_DOMAIN", "zero strike without a shift")
    err({"trades": [tr("a", "CREDIT", 100, 0, 1, kind="CDO", position="BOUGHT", attachment=0.3, detachment=0.3, start=0, end=1, entity="T", subclass="IG")]},
        "E_DOMAIN", "attachment not below detachment")
    err({"trades": [ok], "margin": {"threshold": -1, "mta": 0, "nica": 0, "remargin_days": 1}}, "E_DOMAIN", "negative threshold")
    err({"trades": [ok], "margin": {"threshold": 0, "mta": 0, "nica": 0, "remargin_days": 0}}, "E_DOMAIN", "re-margining period of zero days")
    # two errors at once (repo-wide order HR-122: E_SCHEMA, structural E_INPUT, E_DOMAIN)
    err({"trades": [{**ok, "asset_class": "RATES", "notional": 0}]}, "E_SCHEMA", "two errors: unknown asset class [schema] and zero notional [domain]")
    err({"trades": [tr("a", "FX", -5, 0, 1)]}, "E_INPUT", "two errors: no currency pair [structural] and negative notional [domain]")
    err({"trades": [ok, {**ok, "notional": "1"}]}, "E_SCHEMA", "two errors: duplicate id [structural] and notional as a string [schema]")
    err({"trades": [ok, {**ok, "maturity": 0}]}, "E_INPUT", "two errors: duplicate id [structural] and zero maturity [domain]")
    # E1 goldens (ruling F-2, tools/check_e1_coverage.py): a non-finite Real input is E_DOMAIN by the finite rule,
    # which comes before structural E_INPUT (HR-122)
    err({"trades": [{**ok, "notional": "NaN"}]}, "E_DOMAIN", "E1: non-finite notional (NaN)")
    err({"trades": [{k: v for k, v in {**ok, "market_value": "-Infinity"}.items() if k != "hedging_set"}]}, "E_DOMAIN",
        "E1, two errors: market value -Infinity [finite] and no currency pair [structural] (the finite rule first)")
    # Audit A response (2026-11-19), appended so that the case ids above stay as they were.
    va = {"trades": [tr("v1", "EQUITY", 100, 0, 1, treatment="VOLATILITY", hedging_set="V1", entity="X", subclass="SINGLE"),
                     tr("v2", "EQUITY", 100, 0, 1, position="SHORT", treatment="VOLATILITY", hedging_set="V2", entity="Y",
                        subclass="SINGLE")]}
    hi, lo = sa_ccr(va)
    check(len(lo["hedging_sets"]) == 1 and abs(hi["addon"]["EQUITY"] - mp.sqrt(38400)) < mp.mpf(10) ** -40,
          "KR-236 worked example: one equity volatility set, add-on sqrt(38,400) = 195.959...")
    s.add("risk.saccr.ead", va, lo, verified=["hand", ORACLE, AUDIT_W1B], tags=TAGS_S + ["hand"], output_classes=oc,
          description="hand: KR-236 (KA-A3): two equity volatility trades on two names with two labels form one hedging "
                      "set (CRE52.47): add-on sqrt(38,400) = 195.96, not 320")
    vc = {"trades": [tr("w1", "COMMODITY", 100, 0, 1, treatment="VOLATILITY", entity="POWER", subclass="ELECTRICITY"),
                     tr("w2", "COMMODITY", 100, 0, 1, position="SHORT", treatment="VOLATILITY", entity="SILVER",
                        subclass="METALS", hedging_set="SAME LABEL")]}
    _, lo = sa_ccr(vc)
    check([h["key"] for h in lo["hedging_sets"]] == ["ENERGY", "METALS"], "KR-236: commodity volatility sets by category")
    s.add("risk.saccr.ead", vc, lo, verified=["hand", ORACLE, AUDIT_W1B], tags=TAGS_S + ["hand"], output_classes=oc,
          description="hand: KR-236 (KA-A3 b): electricity and silver volatility trades sit in the energy and metals "
                      "volatility sets, a label does not merge them")
    m15 = {"trades": EX1 + EX3, "collateral": 200,
           "margin": {"threshold": 0, "mta": 5, "nica": 150, "remargin_days": 15, "illiquid": True}}
    _, lo = sa_ccr(m15)
    check(lo["mpor_days"] == 24, "KR-238(b): remargin 15 and illiquid give max(9 + 15, 20) = 24")
    s.add("risk.saccr.ead", m15, lo, verified=["hand", ORACLE, AUDIT_W1B], tags=TAGS_S + ["hand"], output_classes=oc,
          description="hand: KR-238(b) (KA-A11): re-margining every 15 days and illiquid: MPOR floor max(9 + 15, 20) = 24 "
                      "(the combination is inferred, not read)")
    s.write()
    return s


def zone_oracle(n, xa, xh):
    x = max(xa, xh)
    p = mp.mpf("0.01")
    def cdf(k):
        return mp.fsum(mp.binomial(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k + 1))
    amber = next(k for k in range(n + 1) if cdf(k) >= M("0.95"))
    red = next(k for k in range(n + 1) if cdf(k) >= M("0.9999"))
    c = cdf(x)
    zone = "RED" if x >= red else "AMBER" if x >= amber else "GREEN"
    mult = None
    if n == 250:
        mult = TABLES["multiplier_250"][x] if x < 10 else TABLES["multiplier_red"]
    sc = float(binom.cdf(x, n, 0.01))
    assert abs(sc - f(c)) <= 1e-12 * max(1.0, abs(sc)), (n, x, sc, c)
    return {"exceptions": x, "cumulative_probability": f(c), "zone": zone, "amber_from": amber, "red_from": red, "multiplier": mult}


def bcdf(n, k, p):
    p = M(p)
    return mp.fsum(mp.binomial(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k + 1))


def zone_exact(n, xa, xh):
    """KR-237 check: the zone outputs from exact rationals at p = 1/100 (integer term recurrence, streamed so that
    only the running term and sum are held; fast enough for n = 1,000,000)."""
    from fractions import Fraction
    x = max(xa, xh)
    a, b = 1, 100
    c = b - a
    den = b ** n
    term = c ** n
    total = term
    amber = red = cum = None
    k = 0
    while amber is None or red is None or cum is None:
        if cum is None and k == x:
            cum = Fraction(total, den)
        if amber is None and 100 * total >= 95 * den:
            amber = k
        if red is None and 10000 * total >= 9999 * den:
            red = k
        if k == n:
            break
        term = term * (n - k) * a // ((k + 1) * c)
        total += term
        k += 1
    zone = "RED" if x >= red else "AMBER" if x >= amber else "GREEN"
    sc = float(binom.cdf(x, n, 0.01))
    assert abs(sc / float(cum) - 1) <= 1e-12, (n, x, sc, float(cum))
    return {"exceptions": x, "cumulative_probability": float(cum), "zone": zone, "amber_from": amber, "red_from": red,
            "multiplier": None}


def gen_backtest():
    s = Suite("btk_k", SPEC_B, G)
    oc = {"exceptions": "date_and_convention", "zone": "date_and_convention", "amber_from": "date_and_convention",
          "red_from": "date_and_convention", "multiplier": "date_and_convention"}
    printed = TABLES["printed_table2_cumulative_percent"]
    for x in list(range(11)) + [12]:
        o = zone_oracle(250, x, 0)
        k = min(x, 10)
        check((x > 10 or round(100 * o["cumulative_probability"], 2) == printed[k]) and o["zone"] == TABLES["printed_table2_zone"][k],
              f"MAR99 Table 2 row {x}: {printed[k]}% {TABLES['printed_table2_zone'][k]}")
        s.add("risk.frtb.backtest.zone", {"observations": 250, "exceptions_actual": x, "exceptions_hypothetical": 0}, o,
              verified=[ORACLE, SCIPY + ": binom.cdf MATCH 1e-12",
                        f"published: MAR99 Table 2 (Basel Framework PDF p.758) row {k}: " + (f"{printed[k]}%, " if x <= 10 else "") + f"{TABLES['printed_table2_zone'][k]}, multiplier: MATCH"],
              tags=TAGS_B + ["outside_checked", "published"], output_classes=oc, description=f"{x} exceptions in 250 at 99% (MAR99 Table 2)")
    for n, xa, xh, why in [(250, 3, 7, "the larger of the APL and HPL counts (MAR99.8)"), (500, 9, 8, "500 observations"),
                           (100, 2, 0, "100 observations"), (1000, 15, 15, "1,000 observations"),
                           (1, 0, 0, "one observation: zero exceptions is amber (KR-42)"), (260, 6, 6, "260 observations: no multiplier")]:
        s.add("risk.frtb.backtest.zone", {"observations": n, "exceptions_actual": xa, "exceptions_hypothetical": xh},
              zone_oracle(n, xa, xh), verified=[ORACLE, SCIPY + ": binom.cdf and the 95% / 99.99% boundaries MATCH"] + ([] if n == 1 else [BLIND_BTK]),
              tags=TAGS_B + ["outside_checked"], output_classes=oc, description="general rule MAR99.17: " + why)
    doc = {"exceptions_99": "date_and_convention", "exceptions_975": "date_and_convention", "breach_99": "date_and_convention",
           "breach_975": "date_and_convention", "eligible": "date_and_convention"}
    for n, a99, h99, a975, h975 in [(250, 12, 10, 30, 28), (250, 13, 0, 0, 0), (250, 0, 0, 0, 31), (250, 4, 6, 11, 9), (300, 12, 13, 31, 30)]:
        x99, x975 = max(a99, h99), max(a975, h975)
        c99, c975 = bcdf(n, x99, "0.01"), bcdf(n, x975, "0.025")
        assert abs(float(binom.cdf(x99, n, 0.01)) - f(c99)) < 1e-12 and abs(float(binom.cdf(x975, n, 0.025)) - f(c975)) < 1e-12
        o = {"exceptions_99": x99, "exceptions_975": x975, "cumulative_probability_99": f(c99), "cumulative_probability_975": f(c975),
             "breach_99": x99 > 12, "breach_975": x975 > 30, "eligible": not (x99 > 12 or x975 > 30)}
        s.add("risk.frtb.backtest.desk", {"observations": n, "exceptions_99_actual": a99, "exceptions_99_hypothetical": h99,
                                          "exceptions_975_actual": a975, "exceptions_975_hypothetical": h975}, o,
              verified=[ORACLE, SCIPY + ": binom.cdf MATCH 1e-12", "hand: MAR32.19 limits 12 / 30 (KR-44)", BLIND_BTK],
              tags=TAGS_B + ["outside_checked"], output_classes=doc, description=f"desk {n}: 99% {x99}, 97.5% {x975}")
    cnt = {"var": [1.0, 1.0, None, 2.0, 0.5], "actual": [-1.0, -1.25, 0.3, None, 0.0], "hypothetical": [-1.5, 0.0, 0.1, -2.5, -0.5]}
    s.add("risk.frtb.backtest.count", cnt,
          {"observations": 5, "exceptions_actual": 3, "exceptions_hypothetical": 3, "exceptions": 3,
           "days_actual": [1, 2, 3], "days_hypothetical": [0, 2, 3]},
          cls="date_and_convention", verified=["hand", BLIND_BTK], tags=TAGS_B + ["hand"],
          description="hand: strict exceedance, a loss equal to VaR is not an exception, a missing VaR or P&L is (MAR32.5(2))")

    def err(op, inp, code, desc):
        two = ["two-errors"] if "two errors" in desc else []
        s.add(op, inp, error=code, cls="date_and_convention", verified=["hand"], tags=TAGS_B + ["error"] + two,
              description="hand: " + desc)

    z = "risk.frtb.backtest.zone"
    err(z, {"observations": 0, "exceptions_actual": 0, "exceptions_hypothetical": 0}, "E_DOMAIN", "no observations")
    err(z, {"observations": 10, "exceptions_actual": 11, "exceptions_hypothetical": 0}, "E_DOMAIN", "more exceptions than observations")
    err(z, {"observations": 10, "exceptions_actual": 0, "exceptions_hypothetical": -1}, "E_DOMAIN", "negative count")
    err(z, {"observations": 1000001, "exceptions_actual": 0, "exceptions_hypothetical": 0}, "E_LIMIT", "observations above 1,000,000")
    err(z, {"observations": 250, "exceptions_actual": 1.5, "exceptions_hypothetical": 0}, "E_SCHEMA", "count not an integer")
    err(z, {"observations": 250, "exceptions_actual": 1}, "E_SCHEMA", "hypothetical count missing")
    err(z, {"observations": 1000001, "exceptions_actual": -1, "exceptions_hypothetical": 0}, "E_LIMIT", "two errors: limit [limit] and negative count [domain]")
    err(z, {"observations": "250", "exceptions_actual": -1, "exceptions_hypothetical": 0}, "E_SCHEMA", "two errors: observations a string [schema] and negative count [domain]")
    d = "risk.frtb.backtest.desk"
    err(d, {"observations": 250, "exceptions_99_actual": 0, "exceptions_99_hypothetical": 0, "exceptions_975_actual": 251, "exceptions_975_hypothetical": 0},
        "E_DOMAIN", "97.5% count above observations")
    err(d, {"observations": 250, "exceptions_99_actual": -1, "exceptions_99_hypothetical": 0, "exceptions_975_actual": 0}, "E_SCHEMA",
        "two errors: a count missing [schema] and a negative count [domain]")
    c = "risk.frtb.backtest.count"
    err(c, {"var": [], "actual": [], "hypothetical": []}, "E_INPUT", "empty series")
    err(c, {"var": [1.0, 1.0], "actual": [0.0], "hypothetical": [0.0, 0.0]}, "E_INPUT", "series of different lengths")
    err(c, {"var": [1.0], "actual": ["x"], "hypothetical": [0.0]}, "E_SCHEMA", "a P&L that is not a number")
    err(c, {"var": [1.0, 1.0], "actual": [0.0], "hypothetical": ["x", 0.0]}, "E_SCHEMA", "two errors: lengths differ [structural] and a string [schema]")
    # E1 goldens (ruling F-2, tools/check_e1_coverage.py): a non-finite Real is E_DOMAIN, before structural E_INPUT
    err(c, {"var": [1.0, "NaN"], "actual": [0.0, 0.0], "hypothetical": [0.0, 0.0]}, "E_DOMAIN", "E1: non-finite VaR (NaN)")
    err(c, {"var": [1.0, 1.0], "actual": ["Infinity"], "hypothetical": [0.0, 0.0]}, "E_DOMAIN",
        "E1, two errors: actual P&L Infinity [finite] and series of different lengths [structural] (the finite rule first)")
    # Audit A response (KR-237: KA-A16, KA-A17), appended so that the case ids above stay as they were.
    import sys
    sys.set_int_max_str_digits(0)
    audit = ("added by the audit-response lane 2026-11-19 (STAGE_K_R1_AUDIT_A.md; ruling KR-237): exact rational "
             "arithmetic at p = 1/100 (Python fractions)")
    o2 = zone_exact(2, 1, 0)
    check((o2["zone"], o2["amber_from"], o2["red_from"], o2["cumulative_probability"]) == ("RED", 0, 1, 0.9999),
          "KR-237: n = 2, one exception: P(X <= 1) = 0.9999 exactly, a tie with the red threshold: RED from 1")
    s.add("risk.frtb.backtest.zone", {"observations": 2, "exceptions_actual": 1, "exceptions_hypothetical": 0}, o2,
          verified=["hand", audit, SCIPY + ": binom.cdf MATCH 1e-12"], tags=TAGS_B + ["outside_checked"], output_classes=oc,
          description="KR-237 (KA-A17): n = 2, one exception: 1 - p^2 = 0.9999 ties the red threshold exactly: RED, "
                      "red_from 1, amber_from 0")
    for n, xa, xh in [(100_000, 1_050, 0), (1_000_000, 10_164, 10_100), (1_000_000, 9_800, 0)]:
        o = zone_exact(n, xa, xh)
        s.add("risk.frtb.backtest.zone", {"observations": n, "exceptions_actual": xa, "exceptions_hypothetical": xh}, o,
              verified=[audit, SCIPY + ": binom.cdf MATCH 1e-12"], tags=TAGS_B + ["outside_checked"], output_classes=oc,
              limit={"absolute": 1e-15, "relative": 1e-12},
              description=f"KR-237 (KA-A16): {n:,} observations, {max(xa, xh):,} exceptions: the binomial sum at large n "
                          "against exact rationals (the lgamma form was 1.3e-10 off at 100,000)")
    s.write()
    return s


def gen_traffic_light():
    """MAR99 Table 2 as an outside check of the existing stage F operation (KR-43)."""
    s = Suite("tlk_k", SPEC_B, G)
    oc = {"zone": "date_and_convention", "plus_factor": "date_and_convention"}
    plus = {5: 0.40, 6: 0.50, 7: 0.65, 8: 0.75, 9: 0.85}  # existing contract: 1996 plus factor (var-es-and-backtests.md)
    printed = TABLES["printed_table2_cumulative_percent"]
    for x in range(11):
        c = bcdf(250, x, "0.01")
        zone = {"GREEN": "GREEN", "AMBER": "YELLOW", "RED": "RED"}[TABLES["printed_table2_zone"][x]]
        check(round(100 * f(c), 2) == printed[x], f"traffic_light row {x} cumulative {printed[x]}%")
        s.add("risk.backtest.traffic_light", {"observations": 250, "exceptions": x, "confidence": 0.99},
              {"cumulative_probability": f(c), "zone": zone, "plus_factor": 0.0 if x <= 4 else plus.get(x, 1.0)},
              verified=[ORACLE, SCIPY + ": binom.cdf MATCH 1e-12",
                        f"published: MAR99 Table 2 (Basel Framework PDF p.758) row {x}: {printed[x]}%, zone {TABLES['printed_table2_zone'][x]} (YELLOW = Amber): MATCH"],
              tags=["stage_k", "traffic_light", "outside_checked", "published"], output_classes=oc,
              description=f"existing operation, {x} of 250 at 0.99, against MAR99 Table 2 (zone and cumulative only; plus_factor is the 1996 table)")
    # KR-253 (KA-A16 applied to stage J), appended so that the case ids above stay as they were. p is 1 - c as the
    # operation computes it in binary64 (0.99 gives 0.010000000000000009), taken exactly; tolerance fixed here.
    import sys
    from fractions import Fraction
    sys.set_int_max_str_digits(0)
    kr253 = "added by lane k-r2-tl 2026-11-20 (ruling KR-253)"
    for n, x, conf in [(100_000, 1_050, 0.99), (100_000, 2_600, 0.975), (1_000_000, 10_164, 0.99), (1_000_000, 9_800, 0.99)]:
        pf = Fraction(1.0 - conf)
        if n <= 100_000:
            a, b = pf.numerator, pf.denominator
            cc = b - a
            term = cc ** n
            total = term
            for k in range(x):
                term = term * (n - k) * a // ((k + 1) * cc)
                total += term
            cum = float(Fraction(total, b ** n))
            how = "exact rational arithmetic at the binary64 p (Python fractions)"
        else:
            with mp.workdps(50):
                pm = mp.mpf(pf.numerator) / pf.denominator
                t = (1 - pm) ** n
                acc = t
                for k in range(x):
                    t = t * (n - k) * pm / ((k + 1) * (1 - pm))
                    acc += t
                cum = float(acc)
            how = "mpmath 50 digits at the binary64 p (term recurrence)"
        sc = float(binom.cdf(x, n, 1.0 - conf))
        assert abs(sc / cum - 1) <= 1e-12, (n, x, sc, cum)
        zone = "GREEN" if cum < 0.95 else "YELLOW" if cum < 0.9999 else "RED"
        s.add("risk.backtest.traffic_light", {"observations": n, "exceptions": x, "confidence": conf},
              {"cumulative_probability": cum, "zone": zone, "plus_factor": None},
              verified=[f"{kr253}: {how}", SCIPY + ": binom.cdf MATCH 1e-12"],
              tags=["stage_k", "traffic_light", "outside_checked"], output_classes=oc,
              limit={"absolute": 1e-15, "relative": 1e-12},
              description=f"KR-253: {n:,} observations, {x:,} exceptions at {conf}: the stage J binomial at large n "
                          "(the lgamma form drifted past 1e-10 here)")
    s.write()
    return s


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    try:
        gen_saccr()
        gen_backtest()
        gen_traffic_light()
    finally:
        common.GOLDEN = keep


if __name__ == "__main__":
    main()
