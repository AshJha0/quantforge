"""Stage G wave 2d: Bermudan swaption on Hull-White by the pinned reference scheme of
specifications/04-pricing/short-rate-models.md, section `rates.shortrate.bermudan_swaption` (ruling G-18).

The golden is the scheme itself in binary64 (as exotic.american.fd, ruling E-A23). Evidence: a single exercise date
converges to the Jamshidian price (swaption_g) at first order in time and second in space; QuantLib 1.44
FdHullWhiteSwaptionEngine and TreeSwaptionEngine on the same trade agree within their own discretisation error.

    cd oracle/python && uv run python -W ignore gen_stage_g_berm.py
"""
import json
import math

import QuantLib as ql

from gen_stage_g_w1 import CURVE, DC, TODAY, Curve, ql_curve, jam_price, FOLDER, HERE
from qf_oracle import common
from qf_oracle.common import Suite, note

OP = "rates.shortrate.bermudan_swaption"
G = "oracle/python/gen_stage_g_berm.py"


class FCurve:
    """binary64 log-linear curve, same rules as gen_stage_g_w1.Curve."""

    def __init__(self, times, discount_factors):
        self.t = [0.0] + list(times)
        self.p = [1.0] + list(discount_factors)

    def seg(self, t):
        for i in range(1, len(self.t)):
            if t < self.t[i]:
                return i
        return len(self.t) - 1

    def fwd(self, t):
        i = self.seg(t)
        return -(math.log(self.p[i]) - math.log(self.p[i - 1])) / (self.t[i] - self.t[i - 1])

    def P(self, t):
        if t == 0.0:
            return 1.0
        i = self.seg(t)
        return self.p[i - 1] * math.exp(-self.fwd(self.t[i - 1]) * (t - self.t[i - 1]))


def price(inp):
    cv = FCurve(**inp["curve"])
    a, s = inp["mean_reversion"], inp["sigma"]
    T0, Ts, K = inp["start_years"], inp["payment_times"], inp["fixed_rate"]
    ex = inp["exercise_times"]
    nx, ntpy, width = inp["grid"]["nx"], inp["grid"]["steps_per_year"], inp["grid"]["width"]
    sgn = 1.0 if inp["swaption_type"] == "PAYER" else -1.0
    alpha = lambda t: cv.fwd(t) + s * s / (2 * a * a) * (1 - math.exp(-a * t)) ** 2  # noqa: E731
    sx = s * math.sqrt((1 - math.exp(-2 * a * ex[-1])) / (2 * a))
    h = width * sx
    dx = 2 * h / (nx - 1)
    xs = [-h + i * dx for i in range(nx)]

    def bond(t, T, r):
        B = (1 - math.exp(-a * (T - t))) / a
        lnA = math.log(cv.P(T) / cv.P(t)) + B * cv.fwd(t) - s * s / (4 * a) * (1 - math.exp(-2 * a * t)) * B * B
        return math.exp(lnA - B * r)

    def exercise(t):
        rest = [T for T in Ts if T > t]
        prev = [t] + rest[:-1]
        out = []
        for x in xs:
            r = x + alpha(t)
            ann = sum((Ti - Tp) * bond(t, Ti, r) for Tp, Ti in zip(prev, rest))
            out.append(sgn * (1 - bond(t, rest[-1], r) - K * ann))
        return out

    V = [max(e, 0.0) for e in exercise(ex[-1])]
    knots = [0.0] + ex
    for k in range(len(knots) - 1, 0, -1):
        t1, t0 = knots[k], knots[k - 1]
        n = max(1, math.ceil(ntpy * (t1 - t0)))
        dt = (t1 - t0) / n
        for j in range(n, 0, -1):
            t = t0 + (j - 1) * dt  # fully implicit: coefficients at the new (earlier) time
            al = alpha(t)
            m = nx - 2
            lo, di, up, rhs = [0.0] * m, [0.0] * m, [0.0] * m, [0.0] * m
            for i in range(1, nx - 1):
                x = xs[i]
                cl = 0.5 * s * s / (dx * dx) + a * x / (2 * dx)
                cu = 0.5 * s * s / (dx * dx) - a * x / (2 * dx)
                cd = -s * s / (dx * dx) - (x + al)
                lo[i - 1], di[i - 1], up[i - 1], rhs[i - 1] = -dt * cl, 1 - dt * cd, -dt * cu, V[i]
            # boundaries V0 = 2 V1 - V2, V(nx-1) = 2 V(nx-2) - V(nx-3), substituted into the first and last rows
            di[0] += 2 * lo[0]
            up[0] -= lo[0]
            di[-1] += 2 * up[-1]
            lo[-1] -= up[-1]
            # Thomas
            for i in range(1, m):
                w = lo[i] / di[i - 1]
                di[i] -= w * up[i - 1]
                rhs[i] -= w * rhs[i - 1]
            sol = [0.0] * m
            sol[-1] = rhs[-1] / di[-1]
            for i in range(m - 2, -1, -1):
                sol[i] = (rhs[i] - up[i] * sol[i + 1]) / di[i]
            V = [2 * sol[0] - sol[1]] + sol + [2 * sol[-1] - sol[-2]]
        if k - 1 >= 1:
            e = exercise(knots[k - 1])
            V = [max(v, ee) for v, ee in zip(V, e)]
    return inp["notional"] * V[(nx - 1) // 2]


def ql_berm(inp, engine):
    h = ql_curve(inp["curve"])
    model = ql.HullWhite(h, inp["mean_reversion"], inp["sigma"])
    T0 = inp["start_years"]
    d = lambda t: TODAY + int(round(t * 365))  # noqa: E731
    dates = [d(T0)] + [d(t) for t in inp["payment_times"]]
    sched = ql.Schedule(dates, ql.NullCalendar(), ql.Unadjusted)
    idx = ql.IborIndex("X", ql.Period(1, ql.Years), 0, ql.USDCurrency(), ql.NullCalendar(), ql.Unadjusted, False, DC, h)
    typ = ql.Swap.Payer if inp["swaption_type"] == "PAYER" else ql.Swap.Receiver
    sw = ql.VanillaSwap(typ, inp["notional"], sched, inp["fixed_rate"], DC, sched, idx, 0.0, DC)
    sw.setPricingEngine(ql.DiscountingSwapEngine(h))
    o = ql.Swaption(sw, ql.BermudanExercise([d(t) for t in inp["exercise_times"]]))
    o.setPricingEngine(ql.FdHullWhiteSwaptionEngine(model, 400, 400) if engine == "fd" else ql.TreeSwaptionEngine(model, 400))
    return o.NPV()


def main():
    s = Suite("bermudan_g", "specifications/04-pricing/short-rate-models.md", G)
    grid = {"nx": 201, "steps_per_year": 100, "width": 6.0}
    base = dict(mean_reversion=0.05, sigma=0.01, curve=CURVE, notional=1e6, start_years=1.0,
                payment_times=[2.0, 3.0, 4.0, 5.0, 6.0], grid=grid)
    rows = []
    for st in ("PAYER", "RECEIVER"):
        fwd = jam_price(dict(base, expiry_years=1.0, fixed_rate=0.03, swaption_type=st))["forward_swap_rate"]
        for K in (round(fwd - 0.005, 6), round(fwd, 6), round(fwd + 0.005, 6)):
            rows.append(dict(base, fixed_rate=K, swaption_type=st, exercise_times=[1.0, 2.0, 3.0, 4.0, 5.0]))
    rows.append(dict(base, fixed_rate=0.04, swaption_type="PAYER", exercise_times=[1.0]))  # European limit
    rows.append(dict(base, fixed_rate=0.04, swaption_type="RECEIVER", exercise_times=[1.0, 3.0]))
    rows.append(dict(base, mean_reversion=0.3, sigma=0.015, fixed_rate=0.04, swaption_type="PAYER", exercise_times=[1.0, 2.0, 3.0, 4.0, 5.0]))
    rows.append(dict(base, fixed_rate=0.04, swaption_type="PAYER", exercise_times=[1.0, 2.0, 3.0, 4.0, 5.0],
                     grid={"nx": 51, "steps_per_year": 12, "width": 5.0}))  # coarse grid pinned
    evid = []
    for inp in rows:
        v = price(inp)
        e = {"case": len(s.cases) + 1, "scheme": v}
        try:
            e["ql_fd_400x400"] = ql_berm(inp, "fd")
            e["ql_tree_400"] = ql_berm(inp, "tree")
        except Exception as ex:  # noqa: BLE001
            e["ql_error"] = str(ex)
        evid.append(e)
        s.add(OP, inp, {"price": v}, cls="root_finding", verified=["reference-scheme-float64"],
              tags=["shortrate", "bermudan", inp["swaption_type"].lower()],
              limit={"absolute": 1e-6, "relative": 1e-9, "reason": "pinned scheme; tridiagonal rounding only"},
              description=f"HW Bermudan {inp['swaption_type']} K={inp['fixed_rate']} ex={inp['exercise_times']} grid={inp['grid']}")
    # European limit and convergence order against Jamshidian
    eu = rows[6]
    jam = jam_price(dict(mean_reversion=0.05, sigma=0.01, curve=CURVE, notional=1e6, expiry_years=1.0,
                         payment_times=eu["payment_times"], fixed_rate=0.04, swaption_type="PAYER"))["price"]
    conv = []
    for lev in range(4):
        g = {"nx": 50 * 2 ** lev + 1, "steps_per_year": 25 * 2 ** lev, "width": 6.0}
        conv.append(price(dict(eu, grid=g)) - jam)
    orders = [math.log2(abs(conv[i] / conv[i + 1])) for i in range(3)]
    note(f"Bermudan scheme, European limit errors {['%.3e' % c for c in conv]}, observed orders {['%.2f' % o for o in orders]}")
    for e in evid:
        note(f"  case {e['case']}: scheme {e['scheme']:.4f}, QL FD {e.get('ql_fd_400x400', float('nan')):.4f}, QL tree {e.get('ql_tree_400', float('nan')):.4f}")
    e = dict(base, fixed_rate=0.04, swaption_type="PAYER", exercise_times=[1.0, 2.0])
    errs = [(dict(e, exercise_times=[1.5]), "E_INPUT", "exercise not a reset date"),
            (dict(e, exercise_times=[2.0, 1.0]), "E_INPUT", "exercise times not increasing"),
            (dict(e, grid={"nx": 50, "steps_per_year": 100, "width": 6.0}), "E_INPUT", "nx even"),
            (dict(e, grid={"nx": 201, "steps_per_year": 0, "width": 6.0}), "E_INPUT", "steps_per_year 0"),
            (dict(e, grid={"nx": 201, "steps_per_year": 100, "width": 0.0}), "E_DOMAIN", "width 0")]
    for inp, code, d in errs:
        s.add(OP, inp, error=code, cls="date_and_convention", tags=["invalid", "bermudan"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    (HERE.parent / "BERMUDAN_EVIDENCE_G.json").write_text(json.dumps(
        {"european_limit": {"jamshidian": jam, "errors": conv, "orders": orders}, "cases": evid}, indent=1) + chr(10), encoding="utf-8")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["bermudan_g"] = {"counted": 0, "total": len(s.cases), "rule": "not counted: the golden is the pinned scheme; QuantLib FD and tree values are convergence evidence (oracle/BERMUDAN_EVIDENCE_G.json)"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


# ================================================================================================ G3 callable bond (same scheme)
CB = "rates.shortrate.callable_bond"


def step_back(V, xs, dx, a, s, alpha, t0, t1, ntpy):
    nx = len(xs)
    n = max(1, math.ceil(ntpy * (t1 - t0)))
    dt = (t1 - t0) / n
    for j in range(n, 0, -1):
        t = t0 + (j - 1) * dt
        al = alpha(t)
        m = nx - 2
        lo, di, up, rhs = [0.0] * m, [0.0] * m, [0.0] * m, [0.0] * m
        for i in range(1, nx - 1):
            x = xs[i]
            cl = 0.5 * s * s / (dx * dx) + a * x / (2 * dx)
            cu = 0.5 * s * s / (dx * dx) - a * x / (2 * dx)
            cd = -s * s / (dx * dx) - (x + al)
            lo[i - 1], di[i - 1], up[i - 1], rhs[i - 1] = -dt * cl, 1 - dt * cd, -dt * cu, V[i]
        di[0] += 2 * lo[0]
        up[0] -= lo[0]
        di[-1] += 2 * up[-1]
        lo[-1] -= up[-1]
        for i in range(1, m):
            w = lo[i] / di[i - 1]
            di[i] -= w * up[i - 1]
            rhs[i] -= w * rhs[i - 1]
        sol = [0.0] * m
        sol[-1] = rhs[-1] / di[-1]
        for i in range(m - 2, -1, -1):
            sol[i] = (rhs[i] - up[i] * sol[i + 1]) / di[i]
        V = [2 * sol[0] - sol[1]] + sol + [2 * sol[-1] - sol[-2]]
    return V


def callable_price(inp):
    cv = FCurve(**inp["curve"])
    a, s = inp["mean_reversion"], inp["sigma"]
    Ts, c, N = inp["payment_times"], inp["coupon_rate"], inp["notional"]
    calls = set(inp["call_times"])
    cp = inp["call_price"]
    nx, ntpy, width = inp["grid"]["nx"], inp["grid"]["steps_per_year"], inp["grid"]["width"]
    alpha = lambda t: cv.fwd(t) + s * s / (2 * a * a) * (1 - math.exp(-a * t)) ** 2  # noqa: E731
    sx = s * math.sqrt((1 - math.exp(-2 * a * Ts[-1])) / (2 * a))
    h = width * sx
    dx = 2 * h / (nx - 1)
    xs = [-h + i * dx for i in range(nx)]
    knots = [0.0] + Ts
    V = [1.0 + c * (Ts[-1] - knots[-2])] * nx
    for k in range(len(knots) - 1, 0, -1):
        V = step_back(V, xs, dx, a, s, alpha, knots[k - 1], knots[k], ntpy)
        t = knots[k - 1]
        if t > 0:
            if t in calls:
                V = [min(v, cp) for v in V]
            V = [v + c * (t - knots[k - 2]) for v in V]
    return N * V[(nx - 1) // 2]


def g3():
    s = Suite("callable_g", "specifications/04-pricing/short-rate-models.md", G)
    grid = {"nx": 201, "steps_per_year": 100, "width": 6.0}
    base = dict(mean_reversion=0.05, sigma=0.01, curve=CURVE, notional=100.0, payment_times=[1.0 * k for k in range(1, 11)], grid=grid, call_price=1.0)
    rows = []
    for c in (0.03, 0.045, 0.06):
        rows.append(dict(base, coupon_rate=c, call_times=[3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]))
        rows.append(dict(base, coupon_rate=c, call_times=[5.0]))
    rows.append(dict(base, coupon_rate=0.045, call_times=[]))  # straight bond limit
    rows.append(dict(base, coupon_rate=0.05, call_times=[2.0, 4.0, 6.0, 8.0], call_price=1.02, sigma=0.015, mean_reversion=0.2))
    straight = lambda inp: inp["notional"] * (sum(inp["coupon_rate"] * (t - p) * FCurve(**inp["curve"]).P(t) for p, t in zip([0.0] + inp["payment_times"][:-1], inp["payment_times"])) + FCurve(**inp["curve"]).P(inp["payment_times"][-1]))  # noqa: E731
    for inp in rows:
        v = callable_price(inp)
        assert v <= straight(inp) + 1e-3 * inp["notional"]
        s.add(CB, inp, {"price": v}, cls="root_finding", verified=["reference-scheme-float64", "straight-bond-bound"],
              tags=["shortrate", "callable"], limit={"absolute": 1e-9, "relative": 1e-9, "reason": "pinned scheme; tridiagonal rounding only"},
              description=f"HW callable bond c={inp['coupon_rate']} calls={inp['call_times']} K={inp['call_price']}")
    lim = rows[6]
    conv = []
    for lev in range(4):
        g = {"nx": 50 * 2 ** lev + 1, "steps_per_year": 25 * 2 ** lev, "width": 6.0}
        conv.append(callable_price(dict(lim, grid=g)) - straight(lim))
    orders = [math.log2(abs(conv[i] / conv[i + 1])) for i in range(3)]
    note(f"callable scheme, straight-bond limit errors {['%.3e' % c for c in conv]}, orders {['%.2f' % o for o in orders]}")
    e = dict(base, coupon_rate=0.04, call_times=[3.0])
    errs = [(dict(e, call_times=[2.5]), "E_INPUT", "call not a coupon date"), (dict(e, call_times=[10.0]), "E_INPUT", "call at maturity"),
            (dict(e, call_price=0.0), "E_DOMAIN", "call_price 0"), (dict(e, payment_times=[]), "E_INPUT", "no payments")]
    for inp, code, d in errs:
        s.add(CB, inp, error=code, cls="date_and_convention", tags=["invalid", "callable"], description=d)
    for c_ in s.cases:
        c_["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    ev = HERE.parent / "BERMUDAN_EVIDENCE_G.json"
    d = json.loads(ev.read_text(encoding="utf-8"))
    d["callable_straight_limit"] = {"errors": conv, "orders": orders}
    ev.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["callable_g"] = {"counted": 0, "total": len(s.cases), "rule": "not counted: pinned scheme (G-18)"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2 or "BERM" in sys.argv:
        main()
    if len(sys.argv) < 2 or "CALL" in sys.argv:
        g3()
