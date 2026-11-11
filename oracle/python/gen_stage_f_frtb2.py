"""Stage F carry-over wave 2b: FRTB-SA delta for FX and equity (ruling G-48), on the MAR21 text read 2026-11-11 from the
BIS page (MAR21 in force 2023-01-01, published 2026-03-23): MAR21.4 aggregation, MAR21.6 scenarios, MAR21.77 to 21.80
(equity), MAR21.86 to 21.89 (FX). Values: 50-digit mpmath. No outside library (MAR21 has no worked example).

    cd oracle/python && uv run python -W ignore gen_stage_f_frtb2.py
"""
import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_f_frtb2.py"
SPEC = "specifications/06-risk/frtb-sa-fx-equity.md"
EQ_RW = {11: "0.70", 1: "0.55", 2: "0.60", 3: "0.45", 4: "0.55", 5: "0.30", 6: "0.35", 7: "0.40", 8: "0.50", 9: "0.70", 10: "0.50", 12: "0.15", 13: "0.25"}
EQ_RHO = {1: "0.15", 2: "0.15", 3: "0.15", 4: "0.15", 5: "0.25", 6: "0.25", 7: "0.25", 8: "0.25", 9: "0.075", 10: "0.125", 12: "0.80", 13: "0.80"}
SCEN = {"medium": lambda r: r, "high": lambda r: min(mp.mpf("1.25") * r, mp.mpf(1)), "low": lambda r: max(2 * r - 1, mp.mpf("0.75") * r)}
MUT = []


def eq_gamma(b, c):
    if 11 in (b, c):
        return mp.mpf(0)
    if b <= 10 and c <= 10:
        return mp.mpf("0.15")
    if {b, c} == {12, 13}:
        return mp.mpf("0.75")
    return mp.mpf("0.45")


def aggregate(buckets, rho_fn, gamma_fn, simple=()):
    """buckets: {name: [(factor, WS)]}. MAR21.4 with the MAR21.6 scenarios and the MAR21.4(5)(b) alternative."""
    out = {}
    for nm, f in SCEN.items():
        rows = []
        for b in sorted(buckets):
            ws = buckets[b]
            if b in simple:  # MAR21.56, 21.79: simple sum of absolute net weighted sensitivities per risk factor
                net = {}
                for k, w in ws:
                    net[k] = net.get(k, 0) + w
                rows.append((b, sum(abs(v) for v in net.values()), sum(w for _, w in ws)))
                continue
            q = sum(w1 * w2 * (1 if i == j else f(rho_fn(b, k1, k2))) for i, (k1, w1) in enumerate(ws) for j, (k2, w2) in enumerate(ws))
            K = mp.sqrt(max(q, mp.mpf(0)))
            rows.append((b, K, sum(w for _, w in ws)))
        tot = lambda S: sum(r[1] ** 2 for r in rows) + sum(f(gamma_fn(rows[i][0], rows[j][0])) * S[i] * S[j]  # noqa: E731
                                                          for i in range(len(rows)) for j in range(len(rows)) if i != j)
        S = [r[2] for r in rows]
        v, alt = tot(S), False
        if v < 0:
            S = [max(min(r[2], r[1]), -r[1]) for r in rows]
            v, alt = tot(S), True
        out[nm] = {"buckets": [{"bucket": str(r[0]), "k": float(r[1]), "s": float(r[2]), "s_used": float(s)} for r, s in zip(rows, S)],
                   "delta": float(mp.sqrt(max(v, mp.mpf(0)))), "alternative_used": alt}
    order = ["high", "medium", "low"]
    best = max(order, key=lambda k: (out[k]["delta"], -order.index(k)))
    return {"scenarios": out, "capital": out[best]["delta"], "binding_scenario": best}


def fx(inp, mut=None):
    spec = set(inp.get("specified_pairs", []))
    b = {}
    for x in inp["sensitivities"]:
        rw = mp.mpf("0.15") / (mp.sqrt(2) if x["pair"] in spec and mut != "no_sqrt2" else 1)
        b[x["pair"]] = [("FX", rw * mp.mpf(x["sensitivity"]))]
    return aggregate(b, lambda *_: 1, lambda *_: mp.mpf("0.60"))


def eq(inp, mut=None):
    b = {}
    for x in inp["sensitivities"]:
        bk = int(x["bucket"])
        rw = mp.mpf(EQ_RW[bk]) / (100 if x["kind"] == "REPO" else 1)
        b.setdefault(bk, []).append(((x["issuer"], x["kind"]), rw * mp.mpf(x["sensitivity"])))

    def rho(bk, k1, k2):
        (i1, t1), (i2, t2) = k1, k2
        if i1 == i2:
            return mp.mpf("0.999")
        r = mp.mpf(EQ_RHO[bk])
        return r if (t1 == t2 or mut == "no_repo_factor") else r * mp.mpf("0.999")
    return aggregate(b, rho, eq_gamma, simple=(11,))


# ---- CSR non-securitisation delta (MAR21.51 to 21.57)
CSR_RW = {1: "0.005", 2: "0.01", 3: "0.05", 4: "0.03", 5: "0.03", 6: "0.02", 7: "0.015", 8: "0.025", 9: "0.02", 10: "0.04", 11: "0.12",
          12: "0.07", 13: "0.085", 14: "0.055", 15: "0.05", 16: "0.12", 17: "0.015", 18: "0.05"}
SECTOR = ["1/9", "2/10", "3/11", "4/12", "5/13", "6/14", "7/15", "8", "16", "17", "18"]
T5 = [[None, 75, 10, 20, 25, 20, 15, 10, 0, 45, 45], [75, None, 5, 15, 20, 15, 10, 10, 0, 45, 45], [10, 5, None, 5, 15, 20, 5, 20, 0, 45, 45],
      [20, 15, 5, None, 20, 25, 5, 5, 0, 45, 45], [25, 20, 15, 20, None, 25, 5, 15, 0, 45, 45], [20, 15, 20, 25, 25, None, 5, 20, 0, 45, 45],
      [15, 10, 5, 5, 5, 5, None, 5, 0, 45, 45], [10, 10, 20, 5, 15, 20, 5, None, 0, 45, 45], [0] * 8 + [None, 0, 0],
      [45] * 8 + [0, None, 75], [45] * 8 + [0, 75, None]]


def sector(b):
    return {16: 8, 17: 9, 18: 10}.get(b, (b - 1) % 8 if b <= 15 else None) if b != 8 else 7


def csr_gamma(b, c):
    sb, sc = sector(b), sector(c)
    sec = mp.mpf(1) if sb == sc else mp.mpf(T5[sb][sc]) / 100
    rating = mp.mpf("0.5") if (b <= 15 and c <= 15 and (b <= 8) != (c <= 8)) else mp.mpf(1)
    return rating * sec


def csr(inp, mut=None):
    b = {}
    for x in inp["sensitivities"]:
        bk = int(x["bucket"])
        b.setdefault(bk, []).append(((x["issuer"], x["tenor"], x["curve"]), mp.mpf(CSR_RW[bk]) * mp.mpf(x["sensitivity"])))

    def rho(bk, k1, k2):
        name = 1 if k1[0] == k2[0] else mp.mpf("0.80" if bk in (17, 18) else "0.35")
        tenor = 1 if k1[1] == k2[1] else mp.mpf("0.65")
        basis = 1 if (k1[2] == k2[2] or mut == "no_basis") else mp.mpf("0.999")
        return name * tenor * basis
    return aggregate(b, rho, csr_gamma, simple=(16,))


# ---- commodity delta (MAR21.82 to 21.85)
CM_RW = {1: "0.30", 2: "0.35", 3: "0.60", 4: "0.80", 5: "0.40", 6: "0.45", 7: "0.20", 8: "0.35", 9: "0.25", 10: "0.35", 11: "0.50"}
CM_RHO = {1: "0.55", 2: "0.95", 3: "0.40", 4: "0.80", 5: "0.60", 6: "0.65", 7: "0.55", 8: "0.45", 9: "0.15", 10: "0.40", 11: "0.15"}


def cmdty(inp, mut=None):
    b = {}
    for x in inp["sensitivities"]:
        bk = int(x["bucket"])
        b.setdefault(bk, []).append(((x["commodity"], x["tenor"], x["location"]), mp.mpf(CM_RW[bk]) * mp.mpf(x["sensitivity"])))

    def rho(bk, k1, k2):
        name = 1 if k1[0] == k2[0] else mp.mpf(CM_RHO[bk])
        tenor = 1 if k1[1] == k2[1] else mp.mpf("0.99")
        loc = 1 if k1[2] == k2[2] else mp.mpf("0.999")
        return name * tenor * loc
    return aggregate(b, rho, lambda x, y: mp.mpf(0) if 11 in (x, y) else mp.mpf("0.20"))


def more(s):
    cs = [(dict(sensitivities=[dict(issuer="A", bucket=3, tenor="5Y", curve="BOND", sensitivity=1e6)]), "one CSR factor: 5%"),
          (dict(sensitivities=[dict(issuer="A", bucket=3, tenor="5Y", curve="BOND", sensitivity=1e6), dict(issuer="A", bucket=3, tenor="5Y", curve="CDS", sensitivity=-9e5),
                               dict(issuer="B", bucket=3, tenor="1Y", curve="BOND", sensitivity=5e5)]), "bond-CDS basis and a second name"),
          (dict(sensitivities=[dict(issuer="A", bucket=3, tenor="5Y", curve="BOND", sensitivity=1e6), dict(issuer="H", bucket=11, tenor="5Y", curve="BOND", sensitivity=4e5),
                               dict(issuer="I", bucket=17, tenor="3Y", curve="CDS", sensitivity=-2e6)]), "IG and HY same sector (rating 50%), index bucket"),
          (dict(sensitivities=[dict(issuer="O1", bucket=16, tenor="5Y", curve="BOND", sensitivity=1e6), dict(issuer="O2", bucket=16, tenor="5Y", curve="BOND", sensitivity=-1e6),
                               dict(issuer="A", bucket=1, tenor="10Y", curve="BOND", sensitivity=2e7)]), "other sector 16: simple sum, gamma 0")]
    for inp, d in cs:
        s.add("risk.frtb.csr_delta", inp, csr(inp), verified=["mpmath-50"], tags=["frtb", "csr"], description=d)
    MUT.append(("bond-CDS basis ignored", abs(csr(cs[1][0])["capital"] - csr(cs[1][0], "no_basis")["capital"])))
    assert MUT[-1][1] > 1e-9
    for inp, code, d in ((dict(sensitivities=[dict(issuer="A", bucket=19, tenor="5Y", curve="BOND", sensitivity=1.0)]), "E_INPUT", "unknown bucket"),
                         (dict(sensitivities=[dict(issuer="A", bucket=3, tenor="7Y", curve="BOND", sensitivity=1.0)]), "E_INPUT", "tenor not in 0.5Y, 1Y, 3Y, 5Y, 10Y")):
        s.add("risk.frtb.csr_delta", inp, error=code, cls="date_and_convention", tags=["invalid", "frtb"], description=d)
    cm = [(dict(sensitivities=[dict(commodity="BRENT", bucket=2, tenor="1Y", location="ICE", sensitivity=1e6)]), "one commodity factor: 35%"),
          (dict(sensitivities=[dict(commodity="BRENT", bucket=2, tenor="1Y", location="ICE", sensitivity=1e6), dict(commodity="WTI", bucket=2, tenor="1Y", location="NYMEX", sensitivity=-1e6)]), "Brent-WTI spread in bucket 2 (95%)"),
          (dict(sensitivities=[dict(commodity="BRENT", bucket=2, tenor="1Y", location="ICE", sensitivity=1e6), dict(commodity="BRENT", bucket=2, tenor="2Y", location="ICE", sensitivity=-1e6),
                               dict(commodity="GOLD", bucket=7, tenor="1Y", location="LBMA", sensitivity=5e5), dict(commodity="OTHER1", bucket=11, tenor="1Y", location="X", sensitivity=3e5)]), "calendar spread, gold, other commodity")]
    for inp, d in cm:
        s.add("risk.frtb.commodity_delta", inp, cmdty(inp), verified=["mpmath-50"], tags=["frtb", "commodity"], description=d)
    s.add("risk.frtb.commodity_delta", dict(sensitivities=[dict(commodity="X", bucket=12, tenor="1Y", location="X", sensitivity=1.0)]), error="E_INPUT",
          cls="date_and_convention", tags=["invalid", "frtb"], description="unknown bucket")


def main():
    s = Suite("frtb_f2b", SPEC, G)
    sp = ["EURUSD", "USDJPY", "GBPUSD"]
    fxrows = [(dict(sensitivities=[dict(pair="EURUSD", sensitivity=1e6)]), "one pair"),
              (dict(sensitivities=[dict(pair="EURUSD", sensitivity=1e6), dict(pair="USDJPY", sensitivity=-4e5)]), "two pairs, offsetting"),
              (dict(sensitivities=[dict(pair="EURUSD", sensitivity=1e6), dict(pair="USDJPY", sensitivity=-4e5)], specified_pairs=sp), "specified pairs: RW / sqrt 2"),
              (dict(sensitivities=[dict(pair="EURUSD", sensitivity=1e6), dict(pair="USDBRL", sensitivity=2e6), dict(pair="USDTRY", sensitivity=-3e6)]), "three pairs, low scenario binds?")]
    for inp, d in fxrows:
        s.add("risk.frtb.fx_delta", inp, fx(inp), verified=["mpmath-50"], tags=["frtb", "fx"], description=d)
    assert abs(s.cases[0]["expected"]["outputs"]["capital"] - 150000.0) < 1e-6
    caught_gap = abs(fx(fxrows[2][0])["capital"] - fx(fxrows[2][0], "no_sqrt2")["capital"])
    assert caught_gap > 1e-6
    MUT.append(("specified pair without sqrt 2", caught_gap))
    for inp, code, d in ((dict(sensitivities=[]), "E_INPUT", "no sensitivities"),
                         (dict(sensitivities=[dict(pair="EURUSD", sensitivity=1.0), dict(pair="EURUSD", sensitivity=2.0)]), "E_INPUT", "pair twice")):
        s.add("risk.frtb.fx_delta", inp, error=code, cls="date_and_convention", tags=["invalid", "frtb"], description=d)
    eqrows = [(dict(sensitivities=[dict(issuer="A", bucket=5, kind="SPOT", sensitivity=1e6)]), "one name: K = 30% x s"),
              (dict(sensitivities=[dict(issuer="A", bucket=5, kind="SPOT", sensitivity=1e6), dict(issuer="A", bucket=5, kind="REPO", sensitivity=5e7)]), "spot and repo, same issuer (99.9%)"),
              (dict(sensitivities=[dict(issuer="A", bucket=5, kind="SPOT", sensitivity=1e6), dict(issuer="B", bucket=5, kind="SPOT", sensitivity=-8e5),
                                   dict(issuer="B", bucket=5, kind="REPO", sensitivity=3e7)]), "two issuers in bucket 5"),
              (dict(sensitivities=[dict(issuer="A", bucket=1, kind="SPOT", sensitivity=1e6), dict(issuer="C", bucket=9, kind="SPOT", sensitivity=5e5),
                                   dict(issuer="IDX1", bucket=12, kind="SPOT", sensitivity=-2e6), dict(issuer="IDX2", bucket=13, kind="SPOT", sensitivity=1e6)]), "four buckets: 15%, 45%, 75% gammas"),
              (dict(sensitivities=[dict(issuer="A", bucket=12, kind="SPOT", sensitivity=3e6), dict(issuer="B", bucket=13, kind="SPOT", sensitivity=-3e6)]), "index hedge: 12 against 13"),
              (dict(sensitivities=[dict(issuer="X", bucket=11, kind="SPOT", sensitivity=1e6), dict(issuer="Y", bucket=11, kind="SPOT", sensitivity=-1e6),
                                   dict(issuer="A", bucket=5, kind="SPOT", sensitivity=1e6)]), "bucket 11: simple sum of absolutes, no offset, gamma 0 (MAR21.79, 21.80)")]
    for inp, d in eqrows:
        s.add("risk.frtb.equity_delta", inp, eq(inp), verified=["mpmath-50"], tags=["frtb", "equity"], description=d)
    assert abs(s.cases[6]["expected"]["outputs"]["capital"] - 300000.0) < 1e-6
    g = abs(eq(eqrows[2][0])["capital"] - eq(eqrows[2][0], "no_repo_factor")["capital"])
    assert g > 1e-9
    MUT.append(("spot-repo across issuers without 99.9%", g))
    for inp, code, d in ((dict(sensitivities=[dict(issuer="A", bucket=14, kind="SPOT", sensitivity=1.0)]), "E_INPUT", "unknown bucket"),
                         (dict(sensitivities=[dict(issuer="A", bucket=5, kind="SPOT", sensitivity=1.0), dict(issuer="A", bucket=5, kind="SPOT", sensitivity=2.0)]), "E_INPUT", "same factor twice"),
                         (dict(sensitivities=[dict(issuer="A", bucket=5, kind="DIVIDEND", sensitivity=1.0)]), "E_INPUT", "unknown kind")):
        s.add("risk.frtb.equity_delta", inp, error=code, cls="date_and_convention", tags=["invalid", "frtb"], description=d)
    more(s)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_f"
    s.write()
    common.GOLDEN = keep
    for m, gg in MUT:
        note(f"  mutant caught: {m} (gap {float(gg):.3e})")


if __name__ == "__main__":
    main()
