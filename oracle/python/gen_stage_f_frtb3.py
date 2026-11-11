"""Stage F carry-over wave 2b: FRTB-SA vega and curvature for GIRR, CSR non-securitisation, equity, commodity and FX
(ruling G-51). Source: the owner-supplied Basel Framework PDF (MAR21, version in force 2023-01-01), read page by page:
MAR21.4 (p. 570-571), MAR21.5 (p. 571-573), MAR21.6, MAR21.56 and 21.79 (other-sector buckets, p. 599, 609),
MAR21.92 Table 13 to MAR21.95 (p. 614-616), MAR21.98 to MAR21.101 (p. 616-618). Values: 50-digit mpmath.

    cd oracle/python && uv run python -W ignore gen_stage_f_frtb3.py
"""
import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note
from gen_stage_f_frtb2 import (CM_RHO, EQ_RHO, SCEN, csr_gamma, eq_gamma)

mp.mp.dps = 50
G = "oracle/python/gen_stage_f_frtb3.py"
SPEC = "specifications/06-risk/frtb-sa-vega-curvature.md"
CLASSES = ("GIRR", "CSR_NONSEC", "EQUITY", "COMMODITY", "FX")
MUT = []
ORDER = ["high", "medium", "low"]


def gamma_delta(rc, b, c):
    if rc == "GIRR":
        return mp.mpf("0.5")
    if rc == "CSR_NONSEC":
        return csr_gamma(int(b), int(c))
    if rc == "EQUITY":
        return eq_gamma(int(b), int(c))
    if rc == "COMMODITY":
        return mp.mpf(0) if 11 in (int(b), int(c)) else mp.mpf("0.20")
    return mp.mpf("0.60")  # FX, MAR21.89


def other_bucket(rc, b):
    return (rc == "EQUITY" and int(b) == 11) or (rc == "CSR_NONSEC" and int(b) == 16)


def name_rho(rc, b, n1, n2):
    """Delta correlation along the dimension shared by vega and curvature factors (MAR21.94 FAQ1, MAR21.100)."""
    if n1 == n2:
        return mp.mpf(1)
    if rc == "CSR_NONSEC":
        return mp.mpf("0.80" if int(b) in (17, 18) else "0.35")
    if rc == "EQUITY":
        return mp.mpf(EQ_RHO[int(b)])
    if rc == "COMMODITY":
        return mp.mpf(CM_RHO[int(b)])
    return mp.mpf(1)  # GIRR and FX: one name per bucket


def mat_rho(t1, t2, alpha="0.01"):
    t1, t2 = mp.mpf(t1), mp.mpf(t2)
    return mp.exp(-mp.mpf(alpha) * abs(t1 - t2) / min(t1, t2))


def vega_rw(rc, b):
    if rc == "EQUITY":
        return mp.mpf("0.7778") if int(b) in (1, 2, 3, 4, 5, 6, 7, 8, 12, 13) else mp.mpf(1)  # Table 13 and its FAQ1
    return mp.mpf(1)


def vega(inp, mut=None):
    rc = inp["risk_class"]
    bk = {}
    for x in inp["sensitivities"]:
        key = (x.get("name", ""), x["option_maturity"], x.get("underlying_maturity"))
        bk.setdefault(str(x["bucket"]), []).append((key, vega_rw(rc, x["bucket"]) * mp.mpf(x["vega"])))

    def rho(b, k1, k2):
        r = mat_rho(k1[1], k2[1])
        if rc == "GIRR":
            r *= mat_rho(k1[2], k2[2]) if mut != "no_underlying" else 1
        else:
            r *= name_rho(rc, b, k1[0], k2[0])
        return min(r, mp.mpf(1))
    out = {}
    for nm in ORDER:
        f = SCEN[nm]
        rows = []
        for b in sorted(bk, key=lambda s: (len(s), s)):
            ws = bk[b]
            if other_bucket(rc, b):
                net = {}
                for k, w in ws:
                    net[k] = net.get(k, 0) + w
                rows.append((b, sum(abs(v) for v in net.values()), sum(w for _, w in ws)))
                continue
            q = sum(w1 * w2 * (1 if i == j else f(rho(b, k1, k2))) for i, (k1, w1) in enumerate(ws) for j, (k2, w2) in enumerate(ws))
            rows.append((b, mp.sqrt(max(q, 0)), sum(w for _, w in ws)))
        tot = lambda S: sum(r[1] ** 2 for r in rows) + sum(f(gamma_delta(rc, rows[i][0], rows[j][0])) * S[i] * S[j]  # noqa: E731
                                                          for i in range(len(rows)) for j in range(len(rows)) if i != j)
        S = [r[2] for r in rows]
        v, alt = tot(S), False
        if v < 0:
            S = [max(min(r[2], r[1]), -r[1]) for r in rows]
            v, alt = tot(S), True
        out[nm] = {"buckets": [{"bucket": r[0], "k": float(r[1]), "s": float(r[2]), "s_used": float(s)} for r, s in zip(rows, S)],
                   "vega": float(mp.sqrt(max(v, 0))), "alternative_used": alt}
    best = max(ORDER, key=lambda k: (out[k]["vega"], -ORDER.index(k)))
    return {"scenarios": out, "capital": out[best]["vega"], "binding_scenario": best}


def psi(a, b):
    return 0 if (a < 0 and b < 0) else 1


def curvature(inp, mut=None):
    rc = inp["risk_class"]
    scal = mp.mpf("1.5") if inp.get("fx_scalar") else mp.mpf(1)
    bk = {}
    for x in inp["factors"]:
        bk.setdefault(str(x["bucket"]), []).append((x.get("name", ""), mp.mpf(x["cvr_up"]) / scal, mp.mpf(x["cvr_down"]) / scal))
    out = {}
    for nm in ORDER:
        f = SCEN[nm]
        rows = []
        for b in sorted(bk, key=lambda s: (len(s), s)):
            fs = bk[b]
            up, dn = sum(u for _, u, _ in fs), sum(d for _, _, d in fs)
            if other_bucket(rc, b):  # MAR21.56(2), 21.79(2)
                kp, km = sum(max(u, 0) for _, u, _ in fs), sum(max(d, 0) for _, _, d in fs)
            else:
                def kk(idx):
                    q = sum(max(t[idx], 0) ** 2 for t in fs)
                    q += sum(f(name_rho(rc, b, a[0], c[0]) ** (1 if mut == "unsquared" else 2)) * a[idx] * c[idx] * psi(a[idx], c[idx])
                             for i, a in enumerate(fs) for j, c in enumerate(fs) if i != j)
                    return mp.sqrt(max(q, 0))
                kp, km = kk(1), kk(2)
            sel_up = kp > km or (kp == km and up > dn)
            rows.append((b, max(kp, km), up if sel_up else dn, "UP" if sel_up else "DOWN"))
        tot = sum(r[1] ** 2 for r in rows) + sum(f(gamma_delta(rc, rows[i][0], rows[j][0]) ** 2) * rows[i][2] * rows[j][2] * psi(rows[i][2], rows[j][2])
                                                 for i in range(len(rows)) for j in range(len(rows)) if i != j)
        out[nm] = {"buckets": [{"bucket": r[0], "k": float(r[1]), "s": float(r[2]), "selected": r[3]} for r in rows],
                   "curvature": float(mp.sqrt(max(tot, 0)))}
    best = max(ORDER, key=lambda k: (out[k]["curvature"], -ORDER.index(k)))
    return {"scenarios": out, "capital": out[best]["curvature"], "binding_scenario": best}


def cvr(v_up, v_0, v_dn, rw, s):
    """MAR21.5(2) for one instrument, given its shocked prices: CVR+ and CVR-."""
    return -(v_up - v_0 - rw * s), -(v_dn - v_0 + rw * s)


def main():
    s = Suite("frtb_f2c", SPEC, G)
    vrows = [
        (dict(risk_class="GIRR", sensitivities=[dict(bucket="EUR", option_maturity=1.0, underlying_maturity=5.0, vega=1e6),
                                                 dict(bucket="EUR", option_maturity=5.0, underlying_maturity=10.0, vega=-6e5),
                                                 dict(bucket="USD", option_maturity=1.0, underlying_maturity=5.0, vega=8e5)]), "GIRR: maturity and underlying correlations, 50% across"),
        (dict(risk_class="EQUITY", sensitivities=[dict(bucket=5, name="A", option_maturity=0.5, vega=1e6), dict(bucket=5, name="A", option_maturity=1.0, vega=-5e5),
                                                   dict(bucket=9, name="S", option_maturity=1.0, vega=3e5), dict(bucket=11, name="O1", option_maturity=1.0, vega=2e5),
                                                   dict(bucket=11, name="O2", option_maturity=1.0, vega=-2e5)]), "equity: large cap 77.78%, small cap 100%, other sector simple sum"),
        (dict(risk_class="CSR_NONSEC", sensitivities=[dict(bucket=3, name="A", option_maturity=1.0, vega=1e6), dict(bucket=3, name="B", option_maturity=3.0, vega=4e5),
                                                       dict(bucket=11, name="H", option_maturity=1.0, vega=-3e5)]), "CSR: name x maturity; IG against HY same sector"),
        (dict(risk_class="COMMODITY", sensitivities=[dict(bucket=2, name="BRENT", option_maturity=1.0, vega=1e6), dict(bucket=2, name="WTI", option_maturity=1.0, vega=-9e5),
                                                      dict(bucket=7, name="GOLD", option_maturity=0.5, vega=4e5)]), "commodity: Table 12 names, 20% across"),
        (dict(risk_class="FX", sensitivities=[dict(bucket="EURUSD", option_maturity=0.5, vega=1e6), dict(bucket="EURUSD", option_maturity=3.0, vega=1e6),
                                               dict(bucket="USDJPY", option_maturity=1.0, vega=-5e5)]), "FX: maturity correlation only, 60% across"),
    ]
    for inp, d in vrows:
        s.add("risk.frtb.vega", inp, vega(inp), verified=["mpmath-50"], tags=["frtb", "vega", inp["risk_class"].lower()], description=d)
    MUT.append(("GIRR vega without the underlying-maturity factor", abs(vega(vrows[0][0])["scenarios"]["medium"]["vega"] - vega(vrows[0][0], "no_underlying")["scenarios"]["medium"]["vega"])))
    assert MUT[-1][1] > 1e-9
    one = dict(risk_class="FX", sensitivities=[dict(bucket="EURUSD", option_maturity=1.0, vega=1e6)])
    s.add("risk.frtb.vega", one, vega(one), verified=["mpmath-50"], tags=["frtb", "vega", "fx"], description="one factor: capital = 100% x VR")
    assert abs(s.cases[-1]["expected"]["outputs"]["capital"] - 1e6) < 1e-6
    for inp, code, d in ((dict(risk_class="CSR_SEC", sensitivities=one["sensitivities"]), "E_INPUT", "risk class not in this slice"),
                         (dict(risk_class="GIRR", sensitivities=[dict(bucket="EUR", option_maturity=1.0, vega=1.0)]), "E_INPUT", "GIRR without underlying_maturity"),
                         (dict(risk_class="FX", sensitivities=[dict(bucket="EURUSD", option_maturity=0.0, vega=1.0)]), "E_DOMAIN", "option maturity 0")):
        s.add("risk.frtb.vega", inp, error=code, cls="date_and_convention", tags=["invalid", "frtb"], description=d)
    # curvature: CVR from shocked prices for a long call (worked example), then aggregation cases
    up, dn = cvr(118.0, 100.0, 85.0, mp.mpf("0.30"), 50.0)  # delta 0.5 per unit, RW 30%, spot shocked +-30%
    crows = [
        (dict(risk_class="EQUITY", factors=[dict(bucket=5, name="A", cvr_up=float(up), cvr_down=float(dn))]), "one long-option factor: CVR from shocked prices"),
        (dict(risk_class="EQUITY", factors=[dict(bucket=5, name="A", cvr_up=-3e5, cvr_down=-2e5), dict(bucket=5, name="B", cvr_up=-1e5, cvr_down=4e5),
                                             dict(bucket=1, name="C", cvr_up=2e5, cvr_down=-1e5)]), "short and long gamma: psi and selection"),
        (dict(risk_class="GIRR", factors=[dict(bucket="EUR", cvr_up=5e5, cvr_down=3e5), dict(bucket="USD", cvr_up=-2e5, cvr_down=4e5)]), "GIRR: gamma 50% squared = 25%"),
        (dict(risk_class="CSR_NONSEC", factors=[dict(bucket=3, name="A", cvr_up=1e5, cvr_down=2e5), dict(bucket=3, name="B", cvr_up=1e5, cvr_down=-5e4),
                                                 dict(bucket=16, name="O", cvr_up=3e5, cvr_down=-1e5)]), "CSR: name only, squared; other sector 16"),
        (dict(risk_class="COMMODITY", factors=[dict(bucket=2, name="BRENT", cvr_up=2e5, cvr_down=2e5), dict(bucket=2, name="WTI", cvr_up=1e5, cvr_down=1e5)]), "tie K+ = K-: sum CVR+ not above sum CVR-, downward selected"),
        (dict(risk_class="FX", fx_scalar=True, factors=[dict(bucket="EURJPY", cvr_up=3e5, cvr_down=1.5e5), dict(bucket="EURGBP", cvr_up=-6e4, cvr_down=9e4)]), "FX scalar 1.5 (MAR21.98)"),
        (dict(risk_class="EQUITY", factors=[dict(bucket=11, name="O1", cvr_up=1e5, cvr_down=-4e4), dict(bucket=11, name="O2", cvr_up=-5e4, cvr_down=7e4)]), "equity other sector 11 (MAR21.79(2))"),
    ]
    for inp, d in crows:
        s.add("risk.frtb.curvature", inp, curvature(inp), verified=["mpmath-50"], tags=["frtb", "curvature", inp["risk_class"].lower()], description=d)
    MUT.append(("curvature correlation not squared", abs(curvature(crows[3][0])["capital"] - curvature(crows[3][0], "unsquared")["capital"])))
    assert MUT[-1][1] > 1e-9
    for inp, code, d in ((dict(risk_class="EQUITY", factors=[]), "E_INPUT", "no factors"),
                         (dict(risk_class="EQUITY", factors=[dict(bucket=5, name="A", cvr_up=1.0, cvr_down=1.0), dict(bucket=5, name="A", cvr_up=1.0, cvr_down=1.0)]), "E_INPUT", "same factor twice"),
                         (dict(risk_class="GIRR", fx_scalar=True, factors=[dict(bucket="EUR", cvr_up=1.0, cvr_down=1.0)]), "E_INPUT", "fx_scalar outside FX")):
        s.add("risk.frtb.curvature", inp, error=code, cls="date_and_convention", tags=["invalid", "frtb"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_f"
    s.write()
    common.GOLDEN = keep
    note(f"worked CVR: up {float(up)}, down {float(dn)}")
    for m, g in MUT:
        note(f"  mutant caught: {m} (gap {float(g):.3e})")


if __name__ == "__main__":
    main()
