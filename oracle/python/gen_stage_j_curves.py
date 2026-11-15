"""Stage J curves lane (v0.9.0): financing term structures and liquidity cost curves.

Specs: specifications/02-curves/financing-term-structure.md, specifications/10-execution/liquidity-curve.md;
rulings specifications/stage-j-rulings-curves.md (J-C-1 onwards).

Independent oracle: mpmath at 50 digits, written from the spec text only. No golden is taken from an implementation
under test. No free published worked example exists for either curve (J-C-9), so every value case is either a hand
derivation (marked "hand" and checked here against a closed form written out in the comment) or reference-computed.

    cd oracle/python && uv run python -W ignore gen_stage_j_curves.py
"""
import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_j_curves.py"
FOLDER = "stage_j"
SA, EX = "simple_analytic", "date_and_convention"
SPEC_FIN = "specifications/02-curves/financing-term-structure.md"
SPEC_LIQ = "specifications/10-execution/liquidity-curve.md"


class QfErr(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def M(x):
    return mp.mpf(x)


def f(x):
    return float(x)


# ---------------------------------------------------------------- financing term structure (J-C-2 to J-C-5)

def _increasing_positive(ts):
    return all(t > 0 for t in ts) and all(b > a for a, b in zip(ts, ts[1:]))


def _lin(ts, ys, t):
    """Linear in y on knots (0, 0), (ts[k], ys[k]); t inside (0, ts[-1]]."""
    xs, vs = [M(0)] + [M(x) for x in ts], [M(0)] + list(ys)
    for k in range(1, len(xs)):
        if t <= xs[k]:
            w = (t - xs[k - 1]) / (xs[k] - xs[k - 1])
            return vs[k - 1] + w * (vs[k] - vs[k - 1])
    raise AssertionError("outside coverage")


def build_curve(inp):
    ft, fz = inp["funding_times"], inp["funding_zero_rates"]
    qt, qr = inp["quote_times"], inp["repo_rates"]
    bt, bf = inp["borrow_times"], inp["borrow_fees"]
    if len(ft) != len(fz) or len(qt) != len(qr) or len(bt) != len(bf) or not ft or not qt:
        raise QfErr("E_INPUT")
    if not _increasing_positive(ft) or not _increasing_positive(qt) or not _increasing_positive(bt):
        raise QfErr("E_INPUT")
    if any(1 + r * t <= 0 for r, t in zip(qr, qt)):
        raise QfErr("E_DOMAIN")
    if any(b < 0 for b in bf):
        raise QfErr("E_DOMAIN")
    bcum = [M(b) * M(t) for b, t in zip(bf, bt)]
    if any(y < x for x, y in zip(bcum, bcum[1:])):
        raise QfErr("E_DOMAIN")
    if qt[-1] > ft[-1]:
        raise QfErr("E_DOMAIN")
    zt = [M(z) * M(t) for z, t in zip(fz, ft)]
    cover = min(ft[-1], qt[-1], bt[-1] if bt else qt[-1])

    def Zt(t):
        return _lin(ft, zt, M(t))

    scum = [mp.log(1 + M(r) * M(t)) - Zt(t) for r, t in zip(qr, qt)]

    def S(t):
        return _lin(qt, scum, M(t))

    def B(t):
        return _lin(bt, bcum, M(t)) if bt else M(0)

    return {"cover": cover, "Zt": Zt, "S": S, "B": B, "scum": scum, "qt": qt, "has_borrow": bool(bt)}


def term_curve_ref(inp):
    c = build_curve(inp)
    q = inp["query_times"]
    if not q or not _increasing_positive(q):
        raise QfErr("E_INPUT")
    if q[-1] > c["cover"]:
        raise QfErr("E_DOMAIN")
    pf = [mp.exp(-c["Zt"](t) - c["S"](t)) for t in q]
    fwd, prev_t, prev_p = [], M(0), M(1)
    for t, p in zip(q, pf):
        fwd.append(f((prev_p / p - 1) / (M(t) - prev_t)))
        prev_t, prev_p = M(t), p
    return {
        "pillar_spreads": [f(s / M(t)) for s, t in zip(c["scum"], c["qt"])],
        "spread": [f(c["S"](t) / M(t)) for t in q],
        "financing_df": [f(p) for p in pf],
        "financing_rate": [f((1 / p - 1) / M(t)) for p, t in zip(pf, q)],
        "forward_financing": fwd,
        "borrow_fee": [f(c["B"](t) / M(t)) for t in q] if c["has_borrow"] else None,
    }


def forward_ref(inp):
    c = build_curve(inp)
    s, T = inp["spot"], inp["maturity_years"]
    dt, da = inp["dividend_times"], inp["dividend_amounts"]
    if len(dt) != len(da):
        raise QfErr("E_INPUT")
    if any(b <= a for a, b in zip(dt, dt[1:])):
        raise QfErr("E_INPUT")
    if s <= 0 or T <= 0 or T > c["cover"] or any(a < 0 for a in da):
        raise QfErr("E_DOMAIN")

    def C(t):
        return mp.exp(-c["Zt"](t) - c["S"](t) + c["B"](t))

    pv = sum((M(a) * C(t) for t, a in zip(dt, da) if 0 < t <= T), M(0))
    fwd = (M(s) - pv) / C(T)
    if fwd <= 0:
        raise QfErr("E_DOMAIN")
    return {"forward": f(fwd), "carry": f(fwd - M(s)), "carry_factor": f(C(T)),
            "financing_df": f(mp.exp(-c["Zt"](T) - c["S"](T))), "pv_dividends": f(pv)}


# ---------------------------------------------------------------- liquidity cost curve (J-C-6 to J-C-8)

def liq_ref(inp):
    hs = inp["half_spread_bps"]
    V, sig = inp["daily_volume"], inp["daily_vol"]
    Y = inp.get("coefficient", 1.0)
    d = inp.get("exponent", 0.5)
    z = inp.get("risk_multiplier", 0.0)
    Q, H = inp["sizes"], inp["horizons_days"]
    if not Q or not H:
        raise QfErr("E_INPUT")
    if hs < 0 or V <= 0 or sig < 0 or Y < 0 or z < 0 or not 0 < d <= 1 or any(q < 0 for q in Q) or any(h <= 0 for h in H):
        raise QfErr("E_DOMAIN")
    sp = M(hs) / 10000
    imp = [[M(Y) * M(sig) * (M(q) / (M(V) * M(h))) ** M(d) for h in H] for q in Q]
    risk = [M(z) * M(sig) * mp.sqrt(M(h) / 3) for h in H]
    tot = [[sp + imp[i][j] + risk[j] for j in range(len(H))] for i in range(len(Q))]
    out = {"spread_cost": f(sp), "impact": [[f(x) for x in r] for r in imp], "timing_risk": [f(x) for x in risk],
           "total_cost": [[f(x) for x in r] for r in tot], "optimal_horizon": None, "min_cost": None}
    b = M(z) * M(sig) / mp.sqrt(3)
    if b > 0 and Y > 0:
        hstar, cmin = [], []
        for q in Q:
            a = M(Y) * M(sig) * (M(q) / M(V)) ** M(d)
            if a == 0:
                hstar.append(0.0)
                cmin.append(f(sp))
                continue
            h = (2 * M(d) * a / b) ** (1 / (M(d) + M("0.5")))
            hstar.append(f(h))
            cmin.append(f(sp + a * h ** (-M(d)) + b * mp.sqrt(h)))
        out["optimal_horizon"], out["min_cost"] = hstar, cmin
    return out


# ---------------------------------------------------------------- suites

def mk(suite, op, ref, inp, code=None, desc=None, verified=("reference-computed",), tags=()):
    try:
        out = ref(inp)
        assert code is None, f"{suite.name}: expected {code}, got a value ({desc})"
        suite.add(op, inp, outputs=out, cls=SA, verified=verified, tags=("curves", "synthetic") + tuple(tags),
                  description=desc)
    except QfErr as e:
        assert e.code == code, f"{suite.name} {desc}: expected {code}, got {e.code}"
        suite.add(op, inp, error=code, cls=EX, verified=("reference-computed",), tags=("invalid", "curves") + tuple(tags),
                  description=desc)


FUND = {"funding_times": [0.25, 0.5, 1.0, 2.0], "funding_zero_rates": [0.040, 0.041, 0.0415, 0.042]}
QUOTES = {"quote_times": [1 / 12, 0.25, 0.5, 1.0], "repo_rates": [0.0425, 0.0430, 0.0435, 0.0440]}
BORROW = {"borrow_times": [0.25, 1.0], "borrow_fees": [0.0030, 0.0050]}
NOB = {"borrow_times": [], "borrow_fees": []}


def build():
    suites = []
    s = Suite("termfin_j", SPEC_FIN, G); suites.append(s)
    OPC, OPF = "repo.term.curve", "eq.forward.term_financed"

    # Hand case 1 (spec worked example): flat funding 4 % to 1y, one 1y term repo at 5 % simple.
    # S(1) = ln 1.05 - 0.04 = 0.0087901641694320; at t = 0.5: S = 0.0043950820847160, spread 0.0087901641694320,
    # P_f(0.5) = exp(-0.02 - 0.0043950820847160) = 0.97590019..., financing_rate = (1/P_f - 1)/0.5.
    hand = {"funding_times": [1.0], "funding_zero_rates": [0.04], "quote_times": [1.0], "repo_rates": [0.05],
            "borrow_times": [], "borrow_fees": [], "query_times": [0.5, 1.0]}
    o = term_curve_ref(hand)
    assert abs(o["pillar_spreads"][0] - (mp.log(1.05) - 0.04)) < 1e-16
    assert abs(o["financing_rate"][1] - 0.05) < 1e-15  # round trip of the quote
    mk(s, OPC, term_curve_ref, hand, desc="hand: S(1) = ln 1.05 - 0.04; the 1y query returns the 5 % quote", verified=("hand", "reference-computed"))
    # Hand case 2: repo equal to the funding curve's own simple rate gives a zero spread everywhere.
    r1 = float((mp.exp(M("0.04")) - 1))
    mk(s, OPC, term_curve_ref, dict(hand, repo_rates=[r1], query_times=[0.25, 0.5, 1.0]),
       desc="hand: repo at the funding simple rate (e^0.04 - 1) gives spread 0 and forward e^0.01-1 over 0.25", verified=("hand", "reference-computed"))
    # Hand case 3: borrow 0.3 % to 0.25y, 0.5 % to 1y: cumulative 0.00075 and 0.005, forward fee (0.005-0.00075)/0.75.
    mk(s, OPC, term_curve_ref, dict(hand, **BORROW, query_times=[0.25, 0.625, 1.0]),
       desc="hand: borrow term fees; at 0.625 cumulative 0.00075 + 0.375 x 0.0056667 = 0.002875, fee 0.0046", verified=("hand", "reference-computed"))
    base = dict(FUND, **QUOTES, **BORROW)
    mk(s, OPC, term_curve_ref, dict(base, query_times=[1 / 12, 0.25, 0.5, 1.0]), desc="pillar queries round-trip every quote")
    mk(s, OPC, term_curve_ref, dict(base, query_times=[0.01, 0.1, 0.3, 0.42, 0.77, 0.99]), desc="between pillars")
    mk(s, OPC, term_curve_ref, dict(FUND, **QUOTES, **NOB, query_times=[0.2, 0.6]), desc="no borrow: borrow_fee null")
    mk(s, OPC, term_curve_ref, dict(FUND, quote_times=[0.25, 0.5, 1.0], repo_rates=[0.0395, 0.0380, 0.0390], **NOB,
                                     query_times=[0.25, 0.4, 0.75]), desc="special repo below funding: negative spreads")
    mk(s, OPC, term_curve_ref, dict(FUND, quote_times=[0.5, 2.0], repo_rates=[-0.001, 0.002], **NOB, query_times=[0.5, 1.5, 2.0]),
       desc="negative repo rate allowed while 1 + R T > 0")
    for d, ch, code in [
        ("funding length mismatch", {"funding_zero_rates": [0.04]}, "E_INPUT"),
        ("quote length mismatch", {"repo_rates": [0.04]}, "E_INPUT"),
        ("borrow length mismatch", {"borrow_fees": [0.003]}, "E_INPUT"),
        ("no quotes", {"quote_times": [], "repo_rates": []}, "E_INPUT"),
        ("quote times not increasing", {"quote_times": [0.25, 0.25, 0.5, 1.0]}, "E_INPUT"),
        ("zero funding time", {"funding_times": [0.0, 0.5, 1.0, 2.0]}, "E_INPUT"),
        ("query times not increasing", {"query_times": [0.5, 0.2]}, "E_INPUT"),
        ("no queries", {"query_times": []}, "E_INPUT"),
        ("1 + R T <= 0", {"repo_rates": [-13.0, 0.043, 0.0435, 0.044]}, "E_DOMAIN"),
        ("negative borrow fee", {"borrow_fees": [-0.001, 0.005]}, "E_DOMAIN"),
        ("cumulative borrow falls", {"borrow_fees": [0.010, 0.001]}, "E_DOMAIN"),
        ("quote beyond the funding curve", {"quote_times": [1 / 12, 0.25, 0.5, 2.5]}, "E_DOMAIN"),
        ("query beyond last quote", {"query_times": [0.5, 1.5]}, "E_DOMAIN"),
    ]:
        mk(s, OPC, term_curve_ref, {**base, "query_times": [0.5], **ch}, code=code, desc=d)

    # Equity forward. Hand case: flat 4 % funding, 5 % term repo to 1y, no borrow or dividends:
    # C(1) = 1/1.05, F = 100 x 1.05 = 105, carry 5.
    fh = dict(hand, spot=100.0, maturity_years=1.0, dividend_times=[], dividend_amounts=[])
    fh.pop("query_times")
    o = forward_ref(fh)
    assert abs(o["forward"] - 105.0) < 1e-12
    mk(s, OPF, forward_ref, fh, desc="hand: F = 100 x 1.05 = 105 on the 5 % term repo", verified=("hand", "reference-computed"))
    fh2 = dict(fh, dividend_times=[0.5], dividend_amounts=[2.0])
    # F = (100 - 2 C(0.5)) / C(1), C(0.5) = exp(-0.02 - S(0.5)), S(0.5) = S(1)/2.
    mk(s, OPF, forward_ref, fh2, desc="hand: one dividend of 2 at 0.5 carried on C(0.5) = exp(-0.02 - S(1)/2)", verified=("hand", "reference-computed"))
    fb = dict(base, spot=50.0, maturity_years=0.75, dividend_times=[0.1, 0.4, 0.9], dividend_amounts=[0.3, 0.35, 0.4])
    mk(s, OPF, forward_ref, fb, desc="term repo, term borrow, two of three dividends inside the horizon")
    mk(s, OPF, forward_ref, dict(fb, **NOB), desc="as above without borrow")
    mk(s, OPF, forward_ref, dict(fb, maturity_years=1.0, dividend_times=[-0.1, 1.0], dividend_amounts=[5.0, 0.5]),
       desc="dividend at t <= 0 ignored; dividend at T counts")
    for d, ch, code in [
        ("spot zero", {"spot": 0.0}, "E_DOMAIN"),
        ("maturity beyond coverage", {"maturity_years": 1.5}, "E_DOMAIN"),
        ("maturity zero", {"maturity_years": 0.0}, "E_DOMAIN"),
        ("negative dividend", {"dividend_amounts": [0.3, -0.35, 0.4]}, "E_DOMAIN"),
        ("dividend times not increasing", {"dividend_times": [0.4, 0.1, 0.9]}, "E_INPUT"),
        ("dividend length mismatch", {"dividend_amounts": [0.3]}, "E_INPUT"),
        ("forward not positive", {"dividend_amounts": [30.0, 30.0, 0.4]}, "E_DOMAIN"),
    ]:
        mk(s, OPF, forward_ref, dict(fb, **ch), code=code, desc=d)

    # ---- liquidity cost curve
    s = Suite("liqcurve_j", SPEC_LIQ, G); suites.append(s)
    OPL = "liq.curve.cost"
    # Hand case (spec worked example): sigma 2 %, V = 1e7, Y = 1, delta 0.5, half spread 5 bp, z = 0.
    # Q = 1e5, h = 1: impact 0.02 x sqrt(0.01) = 0.002 (= exec.impact.sqrt imp_h-0001); h = 4: 0.001.
    lh = {"half_spread_bps": 5.0, "daily_volume": 1.0e7, "daily_vol": 0.02, "sizes": [1.0e5, 4.0e5], "horizons_days": [1.0, 4.0]}
    o = liq_ref(lh)
    assert abs(o["impact"][0][0] - 0.002) < 1e-17 and abs(o["impact"][1][0] - 0.004) < 1e-17 and abs(o["impact"][0][1] - 0.001) < 1e-17
    mk(s, OPL, liq_ref, lh, desc="hand: impact 0.002 at Q=1e5, h=1 (stage H imp_h-0001); 0.004 at 4x Q; 0.001 at 4x h", verified=("hand", "reference-computed"))
    # Hand case 2 with risk: z = sqrt(3), sigma 0.02 -> b = 0.02; a(Q=1e5) = 0.002, delta 0.5:
    # h* = (2 x 0.5 x 0.002 / 0.02)^(1/1) = 0.1 day; min cost = 5e-4 + 0.002/sqrt(0.1) + 0.02 sqrt(0.1).
    lr = dict(lh, risk_multiplier=float(mp.sqrt(3)), sizes=[1.0e5], horizons_days=[0.1, 1.0])
    o = liq_ref(lr)
    assert abs(o["optimal_horizon"][0] - 0.1) < 1e-15
    mk(s, OPL, liq_ref, lr, desc="hand: z = sqrt 3 gives b = sigma; h* = 2 delta a / b = 0.1 day", verified=("hand", "reference-computed"))
    mk(s, OPL, liq_ref, dict(lh, sizes=[0.0, 1e4, 1e5, 1e6, 5e6], horizons_days=[0.25, 0.5, 1, 2, 5, 10, 20], risk_multiplier=1.645),
       desc="grid with timing risk at z = 1.645")
    mk(s, OPL, liq_ref, dict(lh, exponent=0.6, coefficient=0.7, sizes=[2e5, 8e5], horizons_days=[1, 3, 10], risk_multiplier=2.0),
       desc="Almgren et al. 3/5 exponent, Y = 0.7")
    mk(s, OPL, liq_ref, dict(lh, exponent=1.0, sizes=[1e5], horizons_days=[1, 2], risk_multiplier=1.0), desc="linear impact, delta = 1")
    mk(s, OPL, liq_ref, dict(lh, daily_vol=0.0, risk_multiplier=1.0), desc="zero volatility: no impact, no risk, optimum null")
    mk(s, OPL, liq_ref, dict(lh, coefficient=0.0, risk_multiplier=1.0), desc="Y = 0: optimum null")
    for d, ch, code in [
        ("no sizes", {"sizes": []}, "E_INPUT"),
        ("no horizons", {"horizons_days": []}, "E_INPUT"),
        ("volume zero", {"daily_volume": 0.0}, "E_DOMAIN"),
        ("negative vol", {"daily_vol": -0.01}, "E_DOMAIN"),
        ("negative size", {"sizes": [-1.0]}, "E_DOMAIN"),
        ("zero horizon", {"horizons_days": [0.0, 1.0]}, "E_DOMAIN"),
        ("exponent zero", {"exponent": 0.0}, "E_DOMAIN"),
        ("exponent above one", {"exponent": 1.5}, "E_DOMAIN"),
        ("negative half spread", {"half_spread_bps": -1.0}, "E_DOMAIN"),
        ("negative risk multiplier", {"risk_multiplier": -1.0}, "E_DOMAIN"),
        ("negative coefficient", {"coefficient": -0.5}, "E_DOMAIN"),
    ]:
        mk(s, OPL, liq_ref, dict(lh, **ch), code=code, desc=d)
    return suites


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    tot = [0, 0, 0]
    for s in build():
        s.write()
        tot[0] += len(s.cases)
        tot[1] += sum(c["expected"]["status"] == "ok" for c in s.cases)
        tot[2] += sum(c["expected"]["status"] == "error" for c in s.cases)
    common.GOLDEN = keep
    note(f"stage J curves: {tot[0]} cases, value {tot[1]}, error {tot[2]}")


if __name__ == "__main__":
    main()
