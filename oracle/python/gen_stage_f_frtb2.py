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
EQ_RW = {1: "0.55", 2: "0.60", 3: "0.45", 4: "0.55", 5: "0.30", 6: "0.35", 7: "0.40", 8: "0.50", 9: "0.70", 10: "0.50", 12: "0.15", 13: "0.25"}
EQ_RHO = {1: "0.15", 2: "0.15", 3: "0.15", 4: "0.15", 5: "0.25", 6: "0.25", 7: "0.25", 8: "0.25", 9: "0.075", 10: "0.125", 12: "0.80", 13: "0.80"}
SCEN = {"medium": lambda r: r, "high": lambda r: min(mp.mpf("1.25") * r, mp.mpf(1)), "low": lambda r: max(2 * r - 1, mp.mpf("0.75") * r)}
MUT = []


def eq_gamma(b, c):
    if b <= 10 and c <= 10:
        return mp.mpf("0.15")
    if {b, c} == {12, 13}:
        return mp.mpf("0.75")
    return mp.mpf("0.45")


def aggregate(buckets, rho_fn, gamma_fn):
    """buckets: {name: [(factor, WS)]}. MAR21.4 with the MAR21.6 scenarios and the MAR21.4(5)(b) alternative."""
    out = {}
    for nm, f in SCEN.items():
        rows = []
        for b in sorted(buckets):
            ws = buckets[b]
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
    return aggregate(b, rho, eq_gamma)


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
              (dict(sensitivities=[dict(issuer="A", bucket=12, kind="SPOT", sensitivity=3e6), dict(issuer="B", bucket=13, kind="SPOT", sensitivity=-3e6)]), "index hedge: 12 against 13")]
    for inp, d in eqrows:
        s.add("risk.frtb.equity_delta", inp, eq(inp), verified=["mpmath-50"], tags=["frtb", "equity"], description=d)
    assert abs(s.cases[6]["expected"]["outputs"]["capital"] - 300000.0) < 1e-6
    g = abs(eq(eqrows[2][0])["capital"] - eq(eqrows[2][0], "no_repo_factor")["capital"])
    assert g > 1e-9
    MUT.append(("spot-repo across issuers without 99.9%", g))
    for inp, code, d in ((dict(sensitivities=[dict(issuer="A", bucket=11, kind="SPOT", sensitivity=1.0)]), "E_INPUT", "bucket 11 (MAR21.79) not in this slice"),
                         (dict(sensitivities=[dict(issuer="A", bucket=14, kind="SPOT", sensitivity=1.0)]), "E_INPUT", "unknown bucket"),
                         (dict(sensitivities=[dict(issuer="A", bucket=5, kind="SPOT", sensitivity=1.0), dict(issuer="A", bucket=5, kind="SPOT", sensitivity=2.0)]), "E_INPUT", "same factor twice"),
                         (dict(sensitivities=[dict(issuer="A", bucket=5, kind="DIVIDEND", sensitivity=1.0)]), "E_INPUT", "unknown kind")):
        s.add("risk.frtb.equity_delta", inp, error=code, cls="date_and_convention", tags=["invalid", "frtb"], description=d)
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
