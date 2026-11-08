"""Stage E spec B, E4: rates and inflation vol (SABR swaption cube on D7, caplet stripping, bond futures options,
YoY and ZC inflation caps). Same rules as gen_stage_e_b.py; QuantLib is used only to build the stage D input curves."""
import mpmath as mp

from qf_oracle.common import note
from gen_stage_e_b import A, E, I, R, MUTANTS, S, caught, f, write

mp.mp.dps = 50
PK = ("alpha", "beta", "rho", "nu")


def black_mp(call, F, K, sd, D=1):
    F, K, sd = mp.mpf(F), mp.mpf(K), mp.mpf(sd)
    d1 = (mp.log(F / K) + sd * sd / 2) / sd
    d2 = d1 - sd
    return D * (F * mp.ncdf(d1) - K * mp.ncdf(d2) if call else K * mp.ncdf(-d2) - F * mp.ncdf(-d1))


def bach_mp(call, F, K, sd, D=1):
    F, K, sd = mp.mpf(F), mp.mpf(K), mp.mpf(sd)
    d = (F - K) / sd
    w = 1 if call else -1
    return D * (w * (F - K) * mp.ncdf(w * d) + sd * mp.npdf(d))


def opt_mp(model, call, F, K, v, t, D=1):
    sd = mp.mpf(v) * mp.sqrt(mp.mpf(t))
    return black_mp(call, F, K, sd, D) if model == "BLACK_76" else bach_mp(call, F, K, sd, D)


def hagan(F, K, t, a, b, r, n):
    """05-volatility/sabr.md Hagan formula."""
    F, K, t, a, b, r, n = map(mp.mpf, (F, K, t, a, b, r, n))
    Aq = (F * K) ** (1 - b)
    L = mp.log(F / K)
    c = (1 - b) ** 2 * L ** 2
    z = n / a * mp.sqrt(Aq) * L
    m = 1 - r * z / 2 - (3 * r * r - 2) * z * z / 12 if abs(z) < 1e-7 else z / mp.log((mp.sqrt(1 - 2 * r * z + z * z) + z - r) / (1 - r))
    den = mp.sqrt(Aq) * (1 + c / 24 + c * c / 1920)
    h = 1 + t * ((1 - b) ** 2 * a * a / (24 * Aq) + r * b * n * a / (4 * mp.sqrt(Aq)) + (2 - 3 * r * r) * n * n / 24)
    return a * m * h / den


def bilin(xs, ys, Z, x, y):
    i = len(xs) - 2 if x >= xs[-1] else max(k for k in range(len(xs) - 1) if xs[k] <= x)
    j = len(ys) - 2 if y >= ys[-1] else max(k for k in range(len(ys) - 1) if ys[k] <= y)
    u = (mp.mpf(x) - xs[i]) / (xs[i + 1] - xs[i])
    v = (mp.mpf(y) - ys[j]) / (ys[j + 1] - ys[j])
    return (1 - u) * (1 - v) * Z[i][j] + u * (1 - v) * Z[i + 1][j] + (1 - u) * v * Z[i][j + 1] + u * v * Z[i + 1][j + 1]


def env():
    import gen_stage_d as GD
    import gen_stage_d_vol as GV
    from qf_oracle.dates import yf
    from qf_oracle.rates import add_bd, add_months, adjust, schedule
    GD.estr()
    disc, jd, pc, jp = GV.curves()
    return dict(disc=disc, jd=jd, pc=pc, jp=jp, yf=yf, add_bd=add_bd, add_months=add_months, adjust=adjust, schedule=schedule, T0=GD.AS_OF)


def swap_fa(V, st, tm):
    yf, sc, disc, pc = V["yf"], V["schedule"], V["disc"], V["pc"]
    fx = sc("USGS", st, V["add_months"](st, tm), 12)
    fl = sc("USGS", st, V["add_months"](st, tm), 3)
    Aa = mp.fsum(mp.mpf(float(yf("THIRTY_360_BOND", a, e))) * disc.df(e) for a, e in zip(fx, fx[1:]))
    Fl = mp.fsum((mp.mpf(pc.df(a)) / pc.df(e) - 1) * disc.df(e) for a, e in zip(fl, fl[1:]))
    return Fl / Aa, Aa


def cube_price(V, cube, tr, mutant=None):
    T0 = V["T0"]
    spot = V["add_bd"]("USGS", T0, 2)
    ex = lambda m: V["adjust"]("USGS", V["add_months"](spot, m))  # noqa: E731
    ts = [mp.mpf((ex(m) - T0).days) / 365 for m in cube["expiries_months"]]
    ls = [mp.mpf(m) / 12 for m in cube["tenors_months"]]
    st = ex(tr["expiry_months"])
    t, L = mp.mpf((st - T0).days) / 365, mp.mpf(tr["tenor_months"]) / 12
    if mutant == "expiry-months-axis":
        ts = [mp.mpf(m) / 12 for m in cube["expiries_months"]]
    P = {k: bilin(ts, ls, [[mp.mpf(x) for x in row] for row in cube[k]], t, L) for k in PK}
    F, Aa = swap_fa(V, st, tr["tenor_months"])
    K = mp.mpf(tr["strike"])
    if mutant == "interp-vols":
        Z = [[hagan(F, K, t, *(cube[k][i][j] for k in PK)) for j in range(len(ls))] for i in range(len(ts))]
        vol = bilin(ts, ls, Z, t, L)
    else:
        vol = hagan(F, K, t, *(P[k] for k in PK))
    price = tr["notional"] * Aa * black_mp(tr["type"] == "PAYER", F, K, vol * mp.sqrt(t))
    return {"price": f(price), "forward_rate": f(F), "annuity": f(Aa), "vol": f(vol), "sabr": {k: f(P[k]) for k in PK}}


def cap_periods(V, sm, tm):
    T0 = V["T0"]
    spot = V["add_bd"]("USGS", T0, 2)
    st = V["adjust"]("USGS", V["add_months"](spot, sm))
    ds = V["schedule"]("USGS", st, V["add_months"](st, tm), 3)
    out = []
    for a, e in zip(ds, ds[1:]):
        al = mp.mpf(float(V["yf"]("ACT_360", a, e)))
        out.append((al, (mp.mpf(V["pc"].df(a)) / V["pc"].df(e) - 1) / al, mp.mpf(V["disc"].df(e)), mp.mpf((a - T0).days) / 365))
    return out


def strip(V, inp, mutant=None):
    """Caplet vols piecewise constant between cap maturities; each cap reprices at its flat vol."""
    N, K, model = inp["notional"], mp.mpf(inp["strike"]), inp["model"]
    allp = cap_periods(V, inp["start_months"], inp["cap_tenors_months"][-1])
    cpl = lambda p, v: N * p[0] * opt_mp(model, True, p[1], K, v, p[3], p[2])  # noqa: E731
    vols, prices, prev = [], [], 0
    for M, fv in zip(inp["cap_tenors_months"], inp["flat_vols"]):
        n = M // 3
        target = mp.fsum(cpl(p, fv) for p in allp[:n])
        prices.append(target)
        known = mp.fsum(cpl(p, v) for p, v in zip(allp[:prev], vols))
        seg = allp[prev:n]
        if mutant == "flat-is-caplet":
            vols += [mp.mpf(fv)] * len(seg)
        else:
            g = lambda v: known + mp.fsum(cpl(p, v) for p in seg) - target  # noqa: E731
            lo, hi = (mp.mpf("1e-6"), mp.mpf(3)) if model == "BLACK_76" else (mp.mpf("1e-7"), mp.mpf("0.1"))
            if g(lo) > 0:
                raise ArithmeticError("no positive caplet vol")
            v = mp.findroot(g, (lo, hi), solver="anderson")
            assert abs(g(v)) < 1e-30
            vols += [v] * len(seg)
        prev = n
    return {"caplet_vols": [f(v) for v in vols], "cap_prices": [f(x) for x in prices]}


CUBE = {"expiries_months": [6, 12, 24, 60], "tenors_months": [24, 60, 120],
        "alpha": [[.0525, .0490, .0460], [.0510, .0480, .0450], [.0490, .0465, .0440], [.0450, .0435, .0415]],
        "beta": [[.5, .5, .5]] * 4,
        "rho": [[-.20, -.25, -.30], [-.22, -.27, -.31], [-.25, -.29, -.33], [-.28, -.31, -.35]],
        "nu": [[.55, .48, .42], [.50, .44, .39], [.44, .39, .35], [.36, .33, .30]]}


def ratesvol_e():
    V = env()
    jd, jp = V["jd"], V["jp"]
    s = S("ratesvol_e", "05-volatility/rates-vol-cube.md")
    op = "rates.swaption.price_cube"
    LIM = {"absolute": 1e-9 * 1e7, "relative": 1e-9, "reason": "curve tolerance on notional, as D7"}
    for typ, em, tm, K in (("PAYER", 12, 60, .037), ("RECEIVER", 12, 60, .033), ("PAYER", 12, 60, .045), ("PAYER", 24, 120, .038), ("RECEIVER", 6, 24, .035),
                           ("PAYER", 18, 60, .036), ("PAYER", 36, 84, .040), ("RECEIVER", 48, 36, .030), ("PAYER", 60, 120, .042), ("PAYER", 9, 30, .0355),
                           ("RECEIVER", 30, 96, .028), ("PAYER", 12, 24, .060)):
        tr = {"type": typ, "expiry_months": em, "tenor_months": tm, "strike": K, "notional": 1e7}
        out = cube_price(V, CUBE, tr)
        node = em in CUBE["expiries_months"] and tm in CUBE["tenors_months"]
        s.add(op, {"discount": jd, "projection": jp, "cube": CUBE, "trade": tr}, out, cls=I, verified=["independent-replay", "mpmath-50"],
              tags=["cube", "sabr", "node" if node else "interpolated"], limit=LIM)
        for m in ("interp-vols", "expiry-months-axis"):
            gap = abs(cube_price(V, CUBE, tr, m)["price"] - out["price"])
            if gap > 0:
                caught("ratesvol_e", f"cube {em}x{tm} K={K}: {m}", gap, 1e-2 + 1e-9 * out["price"])
    b = {"discount": jd, "projection": jp, "cube": CUBE, "trade": {"type": "PAYER", "expiry_months": 12, "tenor_months": 60, "strike": .037, "notional": 1e7}}
    for d, bad, code in (("expiry before the first node", {"trade": {**b["trade"], "expiry_months": 3}}, "E_INPUT"),
                         ("tenor beyond the last node", {"trade": {**b["trade"], "tenor_months": 240}}, "E_INPUT"),
                         ("matrix shape", {"cube": {**CUBE, "nu": CUBE["nu"][:3]}}, "E_INPUT"),
                         ("node expiries not increasing", {"cube": {**CUBE, "expiries_months": [6, 24, 12, 60]}}, "E_INPUT"),
                         ("rho outside (-1, 1)", {"cube": {**CUBE, "rho": [[-1.0, -.25, -.3]] + CUBE["rho"][1:]}}, "E_DOMAIN"),
                         ("strike not positive", {"trade": {**b["trade"], "strike": 0.0}}, "E_DOMAIN")):
        s.add(op, {**b, **bad}, error=code, cls=E, tags=["invalid"], description=d)
    # caplet stripping
    sop = "rates.cap.strip"
    for model, K, flats in (("BLACK_76", .037, [.24, .235, .228, .222, .215]), ("BLACK_76", .042, [.22, .225, .222, .218, .212]),
                            ("BACHELIER", .037, [.0090, .0093, .0095, .0096, .0095]), ("BLACK_76", .030, [.26, .25, .24, .23, .22])):
        inp = {"discount": jd, "projection": jp, "model": model, "start_months": 3, "strike": K, "cap_tenors_months": [12, 24, 36, 48, 60], "flat_vols": flats, "notional": 1e7}
        out = strip(V, inp)
        s.add(sop, inp, out, cls=R, verified=["independent-replay", "mpmath-50 root"], tags=["strip", model.lower()],
              output_classes={"caplet_vols": R}, limit={"absolute": 1e-9 * 1e7, "relative": 1e-9, "reason": "cap prices: curve tolerance on notional"})
        o2 = strip(V, inp, "flat-is-caplet")
        caught("ratesvol_e", f"strip {model} K={K}: flat vol used as caplet vol", max(abs(x - y) for x, y in zip(o2["caplet_vols"], out["caplet_vols"])), 1e-10 + 1e-10 * max(out["caplet_vols"]))
    bad = {"discount": jd, "projection": jp, "model": "BLACK_76", "start_months": 3, "strike": .037, "cap_tenors_months": [12, 24, 36], "flat_vols": [.30, .30, .12], "notional": 1e7}
    try:
        strip(V, bad)
        raise AssertionError("arbitrage case stripped")
    except ArithmeticError:
        pass
    s.add(sop, bad, error="E_ARBITRAGE", cls=E, tags=["invalid", "arbitrage", "ruling"], description="flat vol falls so fast that the last segment needs a caplet vol at or below zero")
    for d, bd, code in (("tenor not a multiple of 3", {"cap_tenors_months": [12, 20, 36]}, "E_INPUT"), ("tenors not increasing", {"cap_tenors_months": [24, 12, 36]}, "E_INPUT"),
                        ("one flat vol per tenor", {"flat_vols": [.3, .3]}, "E_INPUT"), ("flat vol not positive", {"flat_vols": [.3, 0.0, .3]}, "E_DOMAIN")):
        s.add(sop, {**bad, "flat_vols": [.24, .235, .228], **bd}, error=code, cls=E, tags=["invalid"], description=d)
    # bond futures options
    bop, iop = "rates.bondfut.option_price", "rates.bondfut.implied_vol"
    CTD = {111.25: (.0425, 6.4), 118.5: (.0395, 8.1), 98.75: (.0480, 4.2), 131.0: (.0430, 15.6)}
    for typ, F, K, t, D, v in (("CALL", 111.25, 112.0, .1, .9962, .055), ("PUT", 111.25, 110.0, .1, .9962, .058), ("CALL", 118.5, 118.5, .25, .9905, .072),
                               ("PUT", 98.75, 101.0, .5, .981, .049), ("CALL", 131.0, 140.0, .2, .9925, .09)):
        pr = opt_mp("BLACK_76", typ == "CALL", F, K, v, t, D)
        s.add(bop, {"type": typ, "futures_price": F, "strike": K, "expiry_years": t, "discount_factor": D, "vol": v, "contract_size": 1e5},
              {"price": f(pr), "contract_value": f(pr * 1e5 / 100)}, cls=A, verified=["independent-replay", "mpmath-50"], tags=["bondfut"],
              limit={"absolute": 1e-9, "relative": 1e-10, "reason": "1e-9 per 100 face: 1e-6 currency on a 100k contract"})
        y, dur = CTD[F]
        prem = f(pr)
        iv = mp.findroot(lambda x: opt_mp("BLACK_76", typ == "CALL", F, K, x, t, D) - prem, (mp.mpf("1e-3"), mp.mpf(1)), solver="anderson")
        s.add(iop, {"type": typ, "futures_price": F, "strike": K, "expiry_years": t, "discount_factor": D, "premium": prem, "ctd_yield": y, "ctd_modified_duration": dur},
              {"price_vol": f(iv), "yield_vol": f(iv / (dur * y))}, cls=R, verified=["independent-replay", "mpmath-50 root"], tags=["bondfut", "implied"])
        caught("ratesvol_e", f"bondfut {typ} {F}/{K}: yield vol without the yield factor", abs(f(iv / dur) - f(iv / (dur * y))), 1e-10)
    s.add(iop, {"type": "CALL", "futures_price": 111.25, "strike": 100.0, "expiry_years": .1, "discount_factor": .9962, "premium": 11.0, "ctd_yield": .0425, "ctd_modified_duration": 6.4},
          error="E_DOMAIN", cls=E, tags=["invalid"], description="premium below discounted intrinsic: no implied vol")
    s.add(bop, {"type": "CALL", "futures_price": 111.25, "strike": 112.0, "expiry_years": 0.0, "discount_factor": .9962, "vol": .05, "contract_size": 1e5}, error="E_DOMAIN", cls=E,
          tags=["invalid"], description="expiry_years must be positive")
    # inflation caps
    yop, zop = "infl.cap.yoy_price", "infl.cap.zc_price"
    per = None
    for model, typ, K, vs in (("BLACK_76", "CAP", .03, [.35, .33, .31, .30, .29]), ("BACHELIER", "CAP", .03, [.0105, .0102, .0100, .0098, .0096]),
                              ("BACHELIER", "FLOOR", .0, [.0105, .0102, .0100, .0098, .0096]), ("BLACK_76", "FLOOR", .02, [.38, .36, .34, .33, .32])):
        per = [{"accrual": 1.0, "discount_factor": f(mp.exp(-mp.mpf(".037") * (k + 1))), "yoy_forward": [.0285, .0262, .0248, .0241, .0238][k], "expiry_years": k + .75, "vol": vs[k]}
               for k in range(5)]
        cpl = [1e7 * p["accrual"] * opt_mp(model, typ == "CAP", p["yoy_forward"], K, p["vol"], p["expiry_years"], p["discount_factor"]) for p in per]
        s.add(yop, {"model": model, "type": typ, "strike": K, "notional": 1e7, "periods": per}, {"caplets": [f(x) for x in cpl], "price": f(mp.fsum(cpl))}, cls=A,
              verified=["independent-replay", "mpmath-50"], tags=["inflation", "yoy"], limit={"absolute": 1e-12 * 1e7, "relative": 1e-10, "reason": "1e-12 per unit notional"})
        alt = mp.fsum(1e7 * p["accrual"] * opt_mp(model, typ == "CAP", p["yoy_forward"], K, p["vol"], p["expiry_years"] + .25, p["discount_factor"]) for p in per)
        caught("ratesvol_e", f"yoy {model} {typ}: time to payment, not to fixing", abs(f(alt - mp.fsum(cpl))), 1e-5 + 1e-10 * f(mp.fsum(cpl)))
    s.add(yop, {"model": "BLACK_76", "type": "FLOOR", "strike": .0, "notional": 1e7, "periods": per}, error="E_DOMAIN", cls=E, tags=["invalid"], description="Black needs a positive strike")
    for typ, FI, T, K, D, v, model in (("CAP", 1.1268, 5.0, .025, .8305, .028, "BLACK_76"), ("FLOOR", 1.1268, 5.0, .0, .8305, .028, "BLACK_76"),
                                       ("CAP", 1.2593, 10.0, .02, .6905, .035, "BLACK_76"), ("FLOOR", 1.0512, 2.0, .03, .9284, .022, "BLACK_76"),
                                       ("CAP", 1.1268, 5.0, .025, .8305, .031, "BACHELIER")):
        Kr = (1 + mp.mpf(K)) ** mp.mpf(T)
        pr = 1e7 * opt_mp(model, typ == "CAP", FI, Kr, v, T, D)
        s.add(zop, {"model": model, "type": typ, "forward_index_ratio": FI, "years": T, "strike": K, "discount_factor": D, "vol": v, "notional": 1e7},
              {"price": f(pr), "strike_ratio": f(Kr)}, cls=A, verified=["independent-replay", "mpmath-50"], tags=["inflation", "zc"],
              limit={"absolute": 1e-12 * 1e7, "relative": 1e-10, "reason": "1e-12 per unit notional"})
        if K:
            caught("ratesvol_e", f"zc {typ} {T}y: simple strike 1 + KT", abs(f(1e7 * opt_mp(model, typ == "CAP", FI, 1 + mp.mpf(K) * T, v, T, D) - pr)), 1e-5 + 1e-10 * f(pr))
    s.add(zop, {"model": "BLACK_76", "type": "CAP", "forward_index_ratio": 1.1268, "years": 0.0, "strike": .02, "discount_factor": 1.0, "vol": .03, "notional": 1e7}, error="E_DOMAIN",
          cls=E, tags=["invalid"], description="years must be positive")
    note("ratesvol_e: SABR cube from interpolated parameters on D7 swaptions; caplet strip by root in mpmath; Black and Bachelier in mpmath")
    write(s)


def e4():
    MUTANTS.clear()
    ratesvol_e()
    note(f"stage E E4: {len(MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    e4()
