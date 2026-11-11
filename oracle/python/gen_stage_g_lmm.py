"""Stage G wave 3b: LIBOR market model (lognormal forward-rate model), closed-form layer.

Slice LMM: caplets and floorlets under the LMM with the abcd instantaneous volatility (Black's formula on the integrated
variance), and European swaptions by Rebonato's frozen-weight approximation with exponential correlation.

Goldens come from this file's own replicas at 50 digits (mpmath, the variance integrals by mp.quad). The outside oracle
is QuantLib 1.44: `AbcdFunction.covariance` for every variance and covariance integral, `DiscountCurve.discount` for the
curve, `blackFormula` for the option value, combined by plain arithmetic (rule 11.2.5, as G-13). A case counts only if
every output matches.

    cd oracle/python && uv run python -W ignore gen_stage_g_lmm.py
"""
import json
from pathlib import Path

import mpmath as mp
import QuantLib as ql

from qf_oracle import common
from qf_oracle.common import Suite, note
from gen_stage_g_w1 import CURVE, NEG, Curve, ql_curve

mp.mp.dps = 50
G = "oracle/python/gen_stage_g_lmm.py"
A = "simple_analytic"
FOLDER = "stage_g"
HERE = Path(__file__).resolve().parent
CAPOP, SWOP = "rates.lmm.capfloor", "rates.lmm.swaption_rebonato"
MUTANTS = []
ABCD = dict(a=-0.06, b=0.17, c=0.54, d=0.17)  # Rebonato's typical humped shape [Reb 2004, ch. 6; BM 6.3.2]
LOW = {"times": [1.0, 2.0, 3.0, 5.0], "discount_factors": [0.999, 0.997, 0.994, 0.985]}
FLAT = dict(a=0.0, b=0.0, c=1.0, d=0.20)  # constant 20% volatility: the Black-76 limit


def caught(name, gap, tol=1e-9):
    assert gap > tol, f"mutant '{name}' is not caught: gap {gap:.3e}"
    MUTANTS.append((name, float(gap)))


def sig(v, Ti, t):
    a, b, c, d = (mp.mpf(v[k]) for k in "abcd")
    x = mp.mpf(Ti) - t
    return (a + b * x) * mp.exp(-c * x) + d


def cov(v, Ti, Tj, upto):
    if upto <= 0:
        return mp.mpf(0)
    return mp.quad(lambda t: sig(v, Ti, t) * sig(v, Tj, t), [0, mp.mpf(upto)])


def black(typ, F, K, sd, df):
    F, K, sd = mp.mpf(F), mp.mpf(K), mp.mpf(sd)
    d1 = (mp.log(F / K) + sd * sd / 2) / sd
    d2 = d1 - sd
    N = lambda x: mp.ncdf(x)
    return df * (F * N(d1) - K * N(d2) if typ == "CALL" else K * N(-d2) - F * N(-d1))


def cap_value(inp, mut=None):
    cv, v, K, n = Curve(**inp["curve"]), inp["abcd"], mp.mpf(inp["strike"]), mp.mpf(inp["notional"])
    Ts = [mp.mpf(t) for t in inp["period_times"]]
    typ = "CALL" if inp["cap_floor"] == "CAP" else "PUT"
    lets, vols, fwds = [], [], []
    for t0, t1 in zip(Ts, Ts[1:]):
        tau = t1 - t0
        F = (cv.P(t0) / cv.P(t1) - 1) / tau
        var = cov(v, t0, t0, t1 if mut == "to_payment" else t0)
        lets.append(n * tau * black(typ, F, K, mp.sqrt(var), cv.P(t1)))
        vols.append(mp.sqrt(var / t0))
        fwds.append(F)
    return {"price": float(sum(lets)), "caplet_prices": [float(x) for x in lets],
            "forward_rates": [float(x) for x in fwds], "black_vols": [float(x) for x in vols]}


def ql_cap(inp):
    h, v = ql_curve(inp["curve"]), inp["abcd"]
    f = ql.AbcdFunction(v["a"], v["b"], v["c"], v["d"])
    Ts, K, n = inp["period_times"], inp["strike"], inp["notional"]
    t = ql.Option.Call if inp["cap_floor"] == "CAP" else ql.Option.Put
    lets, vols, fwds = [], [], []
    for t0, t1 in zip(Ts, Ts[1:]):
        tau = t1 - t0
        F = (h.discount(t0) / h.discount(t1) - 1) / tau
        var = f.covariance(0.0, t0, t0, t0)
        lets.append(n * tau * ql.blackFormula(t, K, F, var ** 0.5, h.discount(t1)))
        vols.append((var / t0) ** 0.5)
        fwds.append(F)
    return {"price": sum(lets), "caplet_prices": lets, "forward_rates": fwds, "black_vols": vols}


def swn_value(inp, mut=None):
    cv, v, n = Curve(**inp["curve"]), inp["abcd"], mp.mpf(inp["notional"])
    T0, K, beta = mp.mpf(inp["expiry_years"]), mp.mpf(inp["fixed_rate"]), mp.mpf(inp["correlation_beta"])
    Ts = [T0] + [mp.mpf(t) for t in inp["payment_times"]]
    taus = [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    Ps = [cv.P(t) for t in Ts]
    ann = sum(tau * P for tau, P in zip(taus, Ps[1:]))
    F = [(Ps[i - 1] / Ps[i] - 1) / taus[i - 1] for i in range(1, len(Ts))]
    w = [taus[i] * Ps[i + 1] / ann for i in range(len(taus))]
    S = sum(wi * fi for wi, fi in zip(w, F))
    fix = Ts[:-1]
    var = mp.mpf(0)
    for i in range(len(F)):
        for j in range(len(F)):
            rho = 1 if mut == "no_corr" else mp.exp(-beta * abs(fix[i] - fix[j]))
            var += w[i] * w[j] * F[i] * F[j] * rho * cov(v, fix[i], fix[j], T0)
    var /= S * S
    typ = "CALL" if inp["side"] == "PAY" else "PUT"
    price = n * black(typ, S, K, mp.sqrt(var), ann)
    return {"price": float(price), "swap_rate": float(S), "annuity": float(ann), "black_vol": float(mp.sqrt(var / T0))}


def ql_swn(inp):
    h, v = ql_curve(inp["curve"]), inp["abcd"]
    f = ql.AbcdFunction(v["a"], v["b"], v["c"], v["d"])
    T0, K, beta, n = inp["expiry_years"], inp["fixed_rate"], inp["correlation_beta"], inp["notional"]
    Ts = [T0] + list(inp["payment_times"])
    taus = [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    Ps = [h.discount(t) for t in Ts]
    ann = sum(tau * P for tau, P in zip(taus, Ps[1:]))
    F = [(Ps[i - 1] / Ps[i] - 1) / taus[i - 1] for i in range(1, len(Ts))]
    w = [taus[i] * Ps[i + 1] / ann for i in range(len(taus))]
    S = sum(a * b for a, b in zip(w, F))
    fix = Ts[:-1]
    import math
    var = sum(w[i] * w[j] * F[i] * F[j] * math.exp(-beta * abs(fix[i] - fix[j])) * f.covariance(0.0, T0, fix[i], fix[j])
              for i in range(len(F)) for j in range(len(F))) / (S * S)
    t = ql.Option.Call if inp["side"] == "PAY" else ql.Option.Put
    return {"price": n * ql.blackFormula(t, K, S, var ** 0.5, ann), "swap_rate": S, "annuity": ann, "black_vol": (var / T0) ** 0.5}


def agree(out, q):
    for k, a in out.items():
        b = q[k]
        pairs = zip(a, b) if isinstance(a, list) else [(a, b)]
        for x, y in pairs:
            tol = 1e-6 + 1e-9 * abs(x) if k in ("price", "caplet_prices") else 1e-12 + 1e-10 * abs(x)
            if abs(x - y) > tol:
                return False
    return True


def write(s, n_out, key, rule):
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    note(f"{s.name} outside (QuantLib 1.44): {n_out} of {len(s.cases)}")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d[key] = {"counted": n_out, "total": len(s.cases), "rule": rule}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


LIM = {"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional; variance integrals by quadrature"}


def lmm_cap():
    s = Suite("lmmcap_g", "specifications/04-pricing/lmm.md", G)
    n_out = 0
    for vname, v in (("abcd", ABCD), ("flat", FLAT)):
        for Ts in ([0.5 * k for k in range(1, 11)], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]):
            for cf in ("CAP", "FLOOR"):
                for K in (0.03, 0.045):
                    inp = dict(curve=CURVE, abcd=v, period_times=Ts, strike=K, cap_floor=cf, notional=1e6)
                    out, q = cap_value(inp), ql_cap(inp)
                    ok = agree(out, q)
                    n_out += ok
                    if not ok:
                        note(f"  QL lmm cap differs {vname} {cf} {K}")
                    s.add(CAPOP, inp, out, cls=A, verified=["mpmath-50", "cap-floor-parity"] + (["quantlib-1.44"] if ok else []),
                          tags=["lmm", "capfloor", vname, cf.lower()], limit=LIM,
                          description=f"LMM {vname} {cf} K={K}, {len(Ts) - 1} periods to {Ts[-1]}y")
    inp = dict(curve=LOW, abcd=ABCD, period_times=[1.0, 2.0, 3.0], strike=0.002, cap_floor="CAP", notional=1e6)
    out, q = cap_value(inp), ql_cap(inp)
    ok = agree(out, q)
    n_out += ok
    s.add(CAPOP, inp, out, cls=A, verified=["mpmath-50"] + (["quantlib-1.44"] if ok else []), tags=["lmm", "capfloor", "low-rate"],
          limit=LIM, description="low-rate curve, all forwards positive")
    # parity on every cap/floor pair: cap - floor = notional sum tau P(t_i) (F_i - K)
    for i in range(0, 16, 4):
        for j in range(2):
            c, f = s.cases[i + j], s.cases[i + 2 + j]
            inp = c["inputs"]
            cv = Curve(**inp["curve"])
            Ts = inp["period_times"]
            sw = sum((cv.P(a) - (1 + inp["strike"] * (b - a)) * cv.P(b)) for a, b in zip(Ts, Ts[1:])) * inp["notional"]
            assert abs(c["expected"]["outputs"]["price"] - f["expected"]["outputs"]["price"] - float(sw)) < 1e-6
    # flat abcd: every black_vol is exactly d
    for c in s.cases:
        if "flat" in c["tags"]:
            assert all(abs(x - 0.2) < 1e-14 for x in c["expected"]["outputs"]["black_vols"])
    b = dict(curve=CURVE, abcd=ABCD, period_times=[1.0, 2.0, 3.0], strike=0.04, cap_floor="CAP", notional=1e6)
    caught("variance integrated to payment, not fixing", abs(cap_value(b)["price"] - cap_value(b, "to_payment")["price"]), 1e-6)
    e = dict(curve=CURVE, abcd=ABCD, period_times=[1.0, 2.0, 3.0], strike=0.04, cap_floor="CAP", notional=1.0)
    errs = [(dict(e, period_times=[1.0]), "E_INPUT", "one period time"), (dict(e, period_times=[0.0, 1.0]), "E_DOMAIN", "first fixing at 0"),
            (dict(e, period_times=[2.0, 1.0]), "E_INPUT", "period times not increasing"), (dict(e, strike=0.0), "E_DOMAIN", "strike <= 0 (lognormal)"),
            (dict(e, abcd=dict(ABCD, c=0.0)), "E_DOMAIN", "c <= 0"), (dict(e, abcd=dict(ABCD, d=-0.01)), "E_DOMAIN", "d < 0"),
            (dict(e, abcd=dict(ABCD, a=-0.2)), "E_DOMAIN", "a + d <= 0 (volatility not positive at expiry)"),
            (dict(e, curve=NEG, period_times=[0.5, 1.0]), "E_DOMAIN", "forward rate <= 0"),
            (dict(e, cap_floor="COLLAR"), "E_INPUT", "unknown cap_floor")]
    for inp, code, d in errs:
        s.add(CAPOP, inp, error=code, cls="date_and_convention", tags=["invalid", "lmm"], description=d)
    write(s, n_out, "lmmcap_g", "QuantLib AbcdFunction.covariance(0, T_fix, T_fix, T_fix), DiscountCurve.discount and blackFormula per caplet, summed")


def lmm_swn():
    s = Suite("lmmswn_g", "specifications/04-pricing/lmm.md", G)
    n_out = 0
    for vname, v in (("abcd", ABCD), ("flat", FLAT)):
        for beta in (0.0, 0.1, 0.5):
            for T0, pays in ((1.0, [2.0, 3.0, 4.0, 5.0, 6.0]), (5.0, [6.0, 7.0, 8.0, 9.0, 10.0]), (2.0, [2.5, 3.0, 3.5, 4.0])):
                for side in ("PAY", "RECEIVE"):
                    inp = dict(curve=CURVE, abcd=v, correlation_beta=beta, expiry_years=T0, payment_times=pays,
                               fixed_rate=0.035, side=side, notional=1e6)
                    out, q = swn_value(inp), ql_swn(inp)
                    ok = agree(out, q)
                    n_out += ok
                    if not ok:
                        note(f"  QL lmm swaption differs {vname} {beta} {T0} {side}")
                    s.add(SWOP, inp, out, cls=A, verified=["mpmath-50", "payer-receiver-parity"] + (["quantlib-1.44"] if ok else []),
                          tags=["lmm", "swaption", vname, side.lower()], limit=LIM,
                          description=f"LMM Rebonato {vname} beta={beta} {T0}y into {pays[-1] - T0}y {side}")
    # parity: payer - receiver = notional annuity (S - K); flat vol with beta 0 gives black_vol = d exactly
    for i in range(0, len(s.cases), 2):
        p, r = s.cases[i]["expected"]["outputs"], s.cases[i + 1]["expected"]["outputs"]
        assert abs(p["price"] - r["price"] - 1e6 * p["annuity"] * (p["swap_rate"] - 0.035)) < 1e-6
        if "flat" in s.cases[i]["tags"] and s.cases[i]["inputs"]["correlation_beta"] == 0.0:
            assert abs(p["black_vol"] - 0.2) < 1e-14
    b = dict(curve=CURVE, abcd=ABCD, correlation_beta=0.5, expiry_years=5.0, payment_times=[6.0, 7.0, 8.0, 9.0, 10.0],
             fixed_rate=0.035, side="PAY", notional=1e6)
    caught("correlation ignored (rho = 1)", abs(swn_value(b)["price"] - swn_value(b, "no_corr")["price"]), 1e-6)
    e = dict(b, notional=1.0)
    errs = [(dict(e, payment_times=[]), "E_INPUT", "no payment times"), (dict(e, expiry_years=0.0), "E_DOMAIN", "expiry = 0"),
            (dict(e, payment_times=[5.0, 6.0]), "E_INPUT", "first payment not after expiry"),
            (dict(e, correlation_beta=-0.1), "E_DOMAIN", "beta < 0"), (dict(e, fixed_rate=0.0), "E_DOMAIN", "fixed_rate <= 0"),
            (dict(e, side="BUY"), "E_INPUT", "unknown side")]
    for inp, code, d in errs:
        s.add(SWOP, inp, error=code, cls="date_and_convention", tags=["invalid", "lmm"], description=d)
    write(s, n_out, "lmmswn_g", "QuantLib AbcdFunction.covariance(0, T0, T_i, T_j) per pair, DiscountCurve.discount for weights and annuity, blackFormula; exp correlation by arithmetic")


if __name__ == "__main__":
    lmm_cap()
    lmm_swn()
    for m, g in MUTANTS:
        note(f"  mutant caught: {m} (gap {g:.3e})")
