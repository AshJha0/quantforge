"""R2: par and key-rate risk goldens. Suite r2/risk_r2. Spec: specifications/06-risk/par-and-key-rate.md.

Expected values come from the own OIS bootstrap and pricers (qf_oracle.rates, gen_stage_d_w2). Each case is then
recomputed in QuantLib from its own objects: OISRateHelper on SimpleQuotes for par bumps, MakeOIS and
DiscountingBondEngine for values, PiecewiseZeroSpreadedTermStructure for key-rate bumps. The run stops on any gap above
the case's tolerance. The par-from-zero Jacobian identity is checked on every pair.
"""
import math
from datetime import date, timedelta

import QuantLib as ql

from qf_oracle import common
from qf_oracle.common import Suite, note
from qf_oracle import rates as RT
from qf_oracle.rates import Curve, ois_legs, ois_periods
import gen_stage_b as B
import gen_stage_d as D
import gen_stage_d_w2 as W2

G = "oracle/python/gen_r2_risk.py"
AS_OF = D.AS_OF
Q = D.Q
I = "interpolation"
QUOTES = {"SOFR": B.SOFR_Q, "ESTR": D.ESTR_Q}
BP = 1e-4


class PillarBump:
    """Pillar i's discount factor times exp(-h t_i); re-interpolated with the curve's own rule."""
    def __init__(self, pil, dfs, i, h):
        self.c = Curve(AS_OF, pil, [v * (math.exp(-h * (p - AS_OF).days / 365) if k == i else 1.0) for k, (p, v) in enumerate(zip(pil, dfs))])
        self.as_of = AS_OF

    def df(self, d):
        return self.c.df(d)


def ql_pillar(jc, prod, i, h):
    a = date.fromisoformat(jc["as_of"])
    ql.Settings.instance().evaluationDate = Q(a)
    ds = [date.fromisoformat(p["date"]) for p in jc["pillars"]]
    vs = [p["discount_factor"] * (math.exp(-h * (d - a).days / 365) if k == i else 1.0) for k, (p, d) in enumerate(zip(jc["pillars"], ds))]
    c = ql.DiscountCurve([Q(a)] + [Q(d) for d in ds], [1.0] + vs, ql.Actual365Fixed())
    c.enableExtrapolation()
    return ql_value(prod, ql.YieldTermStructureHandle(c))


class Shifted:
    """D(t) exp(-h w(t) t): a zero-rate shift with weight function w."""
    def __init__(self, cv, h, w):
        self.cv, self.h, self.w, self.as_of = cv, h, w, cv.as_of

    def df(self, d):
        t = (d - self.as_of).days / 365
        return self.cv.df(d) * math.exp(-self.h * self.w(t) * t)


def tri(ks, i):
    def w(t):
        if t <= ks[0]:
            return 1.0 if i == 0 else 0.0
        if t >= ks[-1]:
            return 1.0 if i == len(ks) - 1 else 0.0
        if i > 0 and ks[i - 1] <= t <= ks[i]:
            return (t - ks[i - 1]) / (ks[i] - ks[i - 1])
        if i < len(ks) - 1 and ks[i] <= t <= ks[i + 1]:
            return (ks[i + 1] - t) / (ks[i + 1] - ks[i])
        return 0.0
    return w


def value(prod, cv):
    if prod["kind"] == "OIS":
        t = prod["trade"]
        a, fl = ois_legs(t["convention"], ois_periods(t["convention"], AS_OF, t["tenor"]), cv)
        return (1 if t["side"] == "PAY" else -1) * t["notional"] * (fl - t["fixed_rate"] * a)
    b = prod
    dp, _ = W2.curve_dirty(b["bond"], date.fromisoformat(b["settlement"]), cv)
    return b["notional"] * dp / 100


def build(conv, quotes):
    cv, dfs, per = D.bootstrap_ois_j(conv, AS_OF, quotes)
    return cv, [p[-1][2] for p in per], dfs


def diff(f, h, scheme, bp):
    return (f(h) - f(-h)) / (2 * bp) if scheme == "CENTRAL" else (f(h) - f(0)) / bp


# ---------------------------------------------------------------- QuantLib side
def ql_curve(conv, quotes):
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    c = RT.CONV[conv]
    sq = [ql.SimpleQuote(r) for _, r in quotes]
    hs = [ql.OISRateHelper(c["spot_lag"], B.qper(t), ql.QuoteHandle(q), D.qindex(conv), ql.YieldTermStructureHandle(), True, c["payment_lag"])
          for (t, _), q in zip(quotes, sq)]
    crv = ql.PiecewiseLogLinearDiscount(Q(AS_OF), hs, ql.Actual365Fixed())
    crv.enableExtrapolation()
    return crv, sq, hs


def ql_value(prod, h):
    if prod["kind"] == "OIS":
        t = prod["trade"]
        c = RT.CONV[t["convention"]]
        sw = ql.MakeOIS(B.qper(t["tenor"]), D.qindex(t["convention"], h), t["fixed_rate"], settlementDays=c["spot_lag"], paymentLag=c["payment_lag"],
                        nominal=t["notional"], swapType=ql.Swap.Payer if t["side"] == "PAY" else ql.Swap.Receiver,
                        pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True)
        return sw.NPV()
    st = date.fromisoformat(prod["settlement"])
    ev = ql.Settings.instance().evaluationDate
    qb, _ = W2.ql_bond(prod["bond"], st)  # sets the evaluation date to settlement; put it back so curves do not move
    ql.Settings.instance().evaluationDate = ev
    return prod["notional"] * ql.CashFlows.npv(qb.cashflows(), h, False, Q(st), Q(st)) / 100


def ql_par(conv, quotes, prod, bump, scheme):
    crv, sq, _ = ql_curve(conv, quotes)
    h = ql.YieldTermStructureHandle(crv)
    base = [q.value() for q in sq]

    def at(js, s):
        for j, q in enumerate(sq):
            q.setValue(base[j] + (s if j in js else 0.0))
        v = ql_value(prod, h)
        for j, q in enumerate(sq):
            q.setValue(base[j])
        return v
    hh = bump * BP
    par = diff(lambda s: at(range(len(sq)), s), hh, scheme, bump)
    bk = [diff(lambda s, j=j: at({j}, s), hh, scheme, bump) for j in range(len(sq))]
    return at(set(), 0.0), par, bk


def ql_key(jc, keys, prod, bump, scheme):
    a = date.fromisoformat(jc["as_of"])
    ql.Settings.instance().evaluationDate = Q(a)
    base = ql.DiscountCurve([Q(a)] + [Q(date.fromisoformat(p["date"])) for p in jc["pillars"]], [1.0] + [p["discount_factor"] for p in jc["pillars"]], ql.Actual365Fixed())
    base.enableExtrapolation()
    bh = ql.YieldTermStructureHandle(base)

    def at(weights, s):
        qs = [ql.QuoteHandle(ql.SimpleQuote(s * w)) for w in weights]
        sp = ql.PiecewiseZeroSpreadedTermStructure(bh, qs, [Q(k) for k in keys])
        sp.enableExtrapolation()
        return ql_value(prod, ql.YieldTermStructureHandle(sp))
    n, hh = len(keys), bump * BP
    kr = [diff(lambda s, i=i: at([1.0 if j == i else 0.0 for j in range(n)], s), hh, scheme, bump) for i in range(n)]
    par = diff(lambda s: at([1.0] * n, s), hh, scheme, bump)
    return ql_value(prod, bh), kr, par


def close(a, b, tol):
    assert abs(a - b) <= tol, (a, b, tol)


# ---------------------------------------------------------------- cases
def products():
    ois = [("SOFR", "2Y", .0345, "RECEIVE", 2.5e7), ("SOFR", "10Y", .0390, "PAY", 1e7), ("SOFR", "30Y", .0400, "RECEIVE", 5e6), ("ESTR", "5Y", .0195, "PAY", 1e7)]
    out = [(c, {"kind": "OIS", "trade": {"convention": c, "tenor": t, "fixed_rate": k, "notional": N, "side": s}}, N) for c, t, k, s, N in ois]
    for b, N in ((W2.BONDS[0], 1e7), (W2.BONDS[2], 2.5e7), (W2.BONDS[4], 5e6)):
        out.append(("SOFR", {"kind": "BOND", "bond": b, "settlement": str(W2.SET), "notional": N}, N))
    return out


def main():
    D.estr()
    s = Suite("risk_r2", "specifications/06-risk/par-and-key-rate.md", G)
    worst = {"par": 0.0, "key": 0.0, "jac": 0.0, "id": 0.0}
    curves = {c: build(c, QUOTES[c]) for c in QUOTES}
    plim = lambda N: {"absolute": 1e-8 * N, "relative": 1e-7, "reason": "difference of curve solves; solves stop below 1e-13 in rate"}  # noqa: E731
    klim = lambda N: {"absolute": 1e-9 * N, "relative": 1e-9, "reason": "no solve; curve tolerance on notional"}  # noqa: E731
    for conv, prod, N in products():
        quotes = QUOTES[conv]
        cv, pil, dfs = curves[conv]
        jq = [{"tenor": t, "rate": r} for t, r in quotes]
        for bump, scheme in ((1.0, "CENTRAL"),) + (((10.0, "CENTRAL"), (1.0, "FORWARD")) if prod.get("kind") == "OIS" and prod["trade"]["tenor"] == "10Y" else ()):
            hh = bump * BP

            def pv_par(js, sh):
                q2 = [(t, r + (sh if j in js else 0.0)) for j, (t, r) in enumerate(quotes)]
                return value(prod, build(conv, q2)[0] if sh else cv)
            v0 = value(prod, cv)
            par = diff(lambda sh: pv_par(range(len(quotes)), sh), hh, scheme, bump)
            bk = [diff(lambda sh, j=j: pv_par({j}, sh), hh, scheme, bump) for j in range(len(quotes))]
            qv, qpar, qbk = ql_par(conv, quotes, prod, bump, scheme)
            tol = 1e-8 * N + 1e-7 * abs(par)
            close(qv, v0, 1e-9 * N)
            close(qpar, par, tol)
            for a, b in zip(qbk, bk):
                close(a, b, tol)
            worst["par"] = max(worst["par"], abs(qpar - par) / N, *(abs(a - b) / N for a, b in zip(qbk, bk)))
            if scheme == "CENTRAL" and bump == 1.0:
                assert abs(sum(bk) - par) <= 1e-4 * abs(par), (sum(bk), par)
                par_ref = (par, bk)
            s.add("risk.curve.par", {"as_of": str(AS_OF), "convention": conv, "quotes": jq, "interpolation": "LOG_LINEAR_DF", "product": prod, "bump_bp": bump, "scheme": scheme},
                  {"value": v0, "par_dv01": par, "par_buckets": bk}, cls=I, verified=["independent-replay", D.QLV], tags=["r2", "par-risk", prod["kind"].lower(), scheme.lower()], limit=plim(N))
        # Key-rate on the bootstrapped curve, keys at the pillars (for the Jacobian identity) and at a coarse grid.
        jc = D.jcurve(cv, pil, dfs)
        grids = [("triangular-pillars", pil), ("triangular-coarse", [AS_OF + timedelta(days=round(365 * y)) for y in (1, 2, 5, 10, 30)])]
        v0 = value(prod, cv)
        zpar = diff(lambda sh: value(prod, Shifted(cv, sh, lambda t: 1.0)), BP, "CENTRAL", 1.0)
        for name, keys in grids:
            ks = [(k - AS_OF).days / 365 for k in keys]
            kr = [diff(lambda sh, i=i: value(prod, Shifted(cv, sh, tri(ks, i))), BP, "CENTRAL", 1.0) for i in range(len(ks))]
            qv, qkr, qz = ql_key(jc, keys, prod, 1.0, "CENTRAL")
            tol = 1e-9 * N + 1e-9 * abs(zpar)
            close(qv, v0, 1e-9 * N)
            close(qz, zpar, tol)
            for a, b in zip(qkr, kr):
                close(a, b, tol)
            worst["key"] = max(worst["key"], abs(qz - zpar) / N, *(abs(a - b) / N for a, b in zip(qkr, kr)))
            assert abs(sum(kr) - zpar) <= 1e-6 * abs(zpar), (name, sum(kr), zpar)
            s.add("risk.curve.key_rate", {"curve": jc, "mode": "TRIANGULAR", "key_dates": [str(k) for k in keys], "product": prod, "bump_bp": 1.0, "scheme": "CENTRAL"},
                  {"value": v0, "key_rates": kr, "zero_dv01": zpar}, cls=I, verified=["independent-replay", D.QLV], tags=["r2", "key-rate", prod["kind"].lower(), name], limit=klim(N))
        zero_rows = [diff(lambda sh, i=i: value(prod, PillarBump(pil, dfs, i, sh)), BP, "CENTRAL", 1.0) for i in range(len(pil))]
        qrows = [diff(lambda sh, i=i: ql_pillar(jc, prod, i, sh), BP, "CENTRAL", 1.0) for i in range(len(pil))]
        for a, b in zip(qrows, zero_rows):
            close(a, b, 1e-9 * N + 1e-9 * abs(zpar))
            worst["key"] = max(worst["key"], abs(a - b) / N)
        assert abs(sum(zero_rows) - zpar) <= 1e-6 * abs(zpar), ("pillar", sum(zero_rows), zpar)
        s.add("risk.curve.key_rate", {"curve": jc, "mode": "PILLAR", "key_dates": None, "product": prod, "bump_bp": 1.0, "scheme": "CENTRAL"},
              {"value": v0, "key_rates": zero_rows, "zero_dv01": zpar}, cls=I, verified=["independent-replay", D.QLV], tags=["r2", "key-rate", prod["kind"].lower(), "pillar"], limit=klim(N))
        # Par from zero through the Jacobian.
        J = jacobian(conv, quotes, pil)
        ppar, pb = par_ref
        for j in range(len(quotes)):
            est = sum(zero_rows[i] * J[i][j] for i in range(len(pil)))
            gap = abs(est - pb[j])
            worst["id"] = max(worst["id"], gap / abs(ppar))
            assert gap <= 1e-3 * abs(ppar) + 1e-6 * N, (conv, prod.get("kind"), j, est, pb[j])
    # Jacobian cases, with a QuantLib check.
    for conv in QUOTES:
        quotes = QUOTES[conv]
        cv, pil, dfs = curves[conv]
        J = jacobian(conv, quotes, pil)
        qJ = ql_jacobian(conv, quotes)
        for r, qr in zip(J, qJ):
            for a, b in zip(r, qr):
                close(a, b, 1e-6)
                worst["jac"] = max(worst["jac"], abs(a - b))
        zs = [-math.log(cv.df(p)) / ((p - AS_OF).days / 365) for p in pil]
        s.add("risk.curve.jacobian", {"as_of": str(AS_OF), "convention": conv, "quotes": [{"tenor": t, "rate": r} for t, r in quotes], "interpolation": "LOG_LINEAR_DF", "bump_bp": 1.0},
              {"pillar_dates": [str(p) for p in pil], "zero_rates": zs, "jacobian": J}, cls=I, verified=["independent-replay", D.QLV], tags=["r2", "jacobian"],
              output_classes={"pillar_dates": "date_and_convention"}, limit={"absolute": 1e-6, "relative": 0.0, "reason": "ratio of curve-solve differences to a 1 bp bump"})
    # Errors.
    base = next(c for c in s.cases if c["operation"] == "risk.curve.par")["inputs"]
    kb = next(c for c in s.cases if c["operation"] == "risk.curve.key_rate")["inputs"]
    s.add("risk.curve.par", {**base, "bump_bp": 0.0}, error="E_DOMAIN", cls="date_and_convention", tags=["r2", "invalid"])
    s.add("risk.curve.par", {**base, "bump_bp": 150.0}, error="E_DOMAIN", cls="date_and_convention", tags=["r2", "invalid"])
    s.add("risk.curve.par", {**base, "scheme": "BACKWARD"}, error="E_SCHEMA", cls="date_and_convention", tags=["r2", "invalid"])
    s.add("risk.curve.par", {**base, "product": {"kind": "CAP"}}, error="E_SCHEMA", cls="date_and_convention", tags=["r2", "invalid"])
    s.add("risk.curve.par", {**base, "convention": "ESTR", "quotes": [{"tenor": t, "rate": r} for t, r in D.ESTR_Q]}, error="E_INPUT", cls="date_and_convention",
          tags=["r2", "invalid"], description="OIS trade convention differs from the curve's")
    s.add("risk.curve.key_rate", {**kb, "key_dates": list(reversed(kb["key_dates"]))}, error="E_INPUT", cls="date_and_convention", tags=["r2", "invalid"])
    s.add("risk.curve.key_rate", {**kb, "mode": "PILLAR"}, error="E_INPUT", cls="date_and_convention", tags=["r2", "invalid"], description="PILLAR needs key_dates null")
    s.add("risk.curve.key_rate", {**kb, "key_dates": [kb["curve"]["as_of"]]}, error="E_INPUT", cls="date_and_convention", tags=["r2", "invalid"], description="key on as_of")
    s.add("risk.curve.key_rate", {**kb, "product": {"kind": "BOND", "bond": W2.BONDS[0], "settlement": str(W2.SET), "notional": -1.0}}, error="E_DOMAIN", cls="date_and_convention", tags=["r2", "invalid"])
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "r2"
    for c in s.cases:
        c["tags"].append("synthetic")
    s.write()
    common.GOLDEN = keep
    note(f"risk_r2: QuantLib worst gaps per unit notional: par {worst['par']:.1e}, key-rate {worst['key']:.1e}; Jacobian {worst['jac']:.1e}; par-from-zero identity worst {worst['id']:.1e} of par DV01")


def jacobian(conv, quotes, pil):
    n = len(quotes)
    zs = lambda q2: [-math.log(build(conv, q2)[0].df(p)) / ((p - AS_OF).days / 365) for p in pil]  # noqa: E731
    cols = []
    for j in range(n):
        up = zs([(t, r + (BP if k == j else 0.0)) for k, (t, r) in enumerate(quotes)])
        dn = zs([(t, r - (BP if k == j else 0.0)) for k, (t, r) in enumerate(quotes)])
        cols.append([(a - b) / (2 * BP) for a, b in zip(up, dn)])
    J = [[cols[j][i] for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            J[i][j] = 0.0  # exact: pillar i depends only on quotes 0..i; differences here are below 1e-12
    return J


def ql_jacobian(conv, quotes):
    crv, sq, hs = ql_curve(conv, quotes)
    piv = [h.pillarDate() for h in hs]
    z = lambda: [crv.zeroRate(p, ql.Actual365Fixed(), ql.Continuous).rate() for p in piv]  # noqa: E731
    base = [q.value() for q in sq]
    n = len(sq)
    J = [[0.0] * n for _ in range(n)]
    for j in range(n):
        sq[j].setValue(base[j] + BP)
        up = z()
        sq[j].setValue(base[j] - BP)
        dn = z()
        sq[j].setValue(base[j])
        for i in range(n):
            J[i][j] = 0.0 if j > i else (up[i] - dn[i]) / (2 * BP)
    return J


if __name__ == "__main__":
    main()
