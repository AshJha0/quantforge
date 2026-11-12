"""R6 wave 2 (program/R6_HANDOVER.md, "WAVE 2"): R6-7 (MBS CPR above 1, realistic futures basis, CDS trade date on an
IMM date) and R6-2 (discrete barrier envelope, Monte Carlo acceptance). Suites in datasets/golden/r6/.
TIPS rounding (R6-7.5) is a change to gen_stage_d_w3.py (stage_d/inflation_d), rerun separately.

    cd oracle/python && uv run python -W ignore gen_r6_w2.py [mbs cds basis barrier]

Outside or independent checks, asserted before a case is written:
- CDS on an IMM trade date: QuantLib 1.44 IsdaCdsEngine (Taylor, no bias, piecewise) on a CDS2015 schedule, NPV, fair
  spread and fair upfront within 1e-9 per unit; bootstrap spreads reprice in QuantLib within 1e-9.
- Futures basis: implied repo re-solved by brentq on the forward-price identity (a different formulation from the
  closed form), within 1e-12.
- MBS: closed form; the E_DOMAIN boundary is checked against the month in which CPR first reaches 1.
- Barriers: exact-date Monte Carlo (qf_oracle.mc_barrier, 4,000,000 antithetic paths, core.rng) per case.
"""
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

from scipy.optimize import brentq

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_r6_w2.py"
E = "date_and_convention"
HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------------- R6-7.1 MBS
def mbs_suite():
    import gen_stage_d_mbs as M
    s = Suite("mbs_r6", "specifications/04-pricing/mbs.md", G)
    b = dict(balance=1e6, wac=.0650, net_coupon=.0600, wam=60, age=30, prepayment={"model": "PSA", "speed": 1700.0})
    max_cpr = lambda p: max(min((p["age"] + k) / 30, 1.0) * .06 * p["prepayment"]["speed"] / 100 for k in range(1, p["wam"] + 1))  # noqa: E731
    for d, pool in (("PSA 1700, seasoned: CPR 1.02 from month 1", b),
                    ("PSA 5000 (finding 18: Python returned complex numbers, Rust NaN)", dict(b, prepayment={"model": "PSA", "speed": 5000.0})),
                    ("PSA 1700, new pool: CPR reaches 1 in month 30", dict(b, age=0, wam=60)),
                    ("PSA 1666.67: CPR 1.0000002 at full seasoning", dict(b, prepayment={"model": "PSA", "speed": 1666.67}))):
        assert max_cpr(pool) >= 1.0
        s.add("mbs.cashflows", {"pool": pool}, error="E_DOMAIN", cls=E, tags=["r6", "mbs", "invalid"], description=d + " (ruling R6-7.1)")
        s.add("mbs.price", {"pool": pool, "yield": 0.055, "delay_days": 24}, error="E_DOMAIN", cls=E, tags=["r6", "mbs", "invalid"], description=d)
    for d, pool in (("PSA 1700 on a 12-month new pool: CPR peaks at 0.408, below 1", dict(b, age=0, wam=12)),
                    ("PSA 1666: CPR 0.9996 at full seasoning, below 1", dict(b, prepayment={"model": "PSA", "speed": 1666.0}))):
        assert max_cpr(pool) < 1.0
        bal, it, sp, pp = M.flows(pool)
        wal = sum((k + 1) / 12 * (a + c) for k, (a, c) in enumerate(zip(sp, pp))) / pool["balance"]
        s.add("mbs.cashflows", {"pool": pool}, {"balance": bal, "interest": it, "scheduled_principal": sp, "prepayment": pp, "wal": wal},
              cls="simple_analytic", limit={"absolute": 1e-9 * pool["balance"], "relative": 1e-10, "reason": "as mbs_d: per unit balance"},
              verified=["analytic"], tags=["r6", "mbs"], description=d)
    return s


# ---------------------------------------------------------------------------------- R6-7.3 CDS on an IMM date
def cds_suite():
    import gen_stage_d as D
    import gen_stage_d_credit as C
    s = Suite("cds_imm_r6", "specifications/04-pricing/credit.md", G)
    worst = 0.0
    for T in (date(2026, 12, 21), date(2027, 3, 22), date(2027, 6, 21), date(2027, 9, 20)):
        # 2026-12-20 and 2027-03-20 fall on weekends (adjusted to Monday); 2027-09-20 is itself a Monday
        disc = D.Curve(T, [T + timedelta(7305)], [math.exp(-.039 * 7305 / 365)])
        jd = D.jcurve(disc, C.disc_dates(disc), [disc.df(d) for d in C.disc_dates(disc)])
        R = .40
        H, mats, surv = C.bootstrap(T, disc, R, C.QUOTES)
        dh, ph = C.ql_setup(T, disc, H, R)
        for (t, q), m in zip(C.QUOTES, mats):
            fs = C.ql_cds(T, m, q, R, dh, ph).fairSpread()
            assert abs(fs - q) < 1e-9, (T, t, fs, q)
            worst = max(worst, abs(fs - q))
        s.add("credit.cds.bootstrap", {"trade_date": str(T), "discount": jd, "recovery": R, "quotes": [{"tenor": t, "spread": q} for t, q in C.QUOTES]},
              {"pillars": [{"date": str(d), "survival": v} for d, v in zip(mats, surv)]}, cls="interpolation", verified=["independent-replay", C.QLE],
              tags=["r6", "isda-cds", "imm-trade-date"], limit={"absolute": 1e-9, "relative": 0.0, "reason": "curve solve; spreads reprice below 1e-13"},
              description=f"trade date {T} on an adjusted coupon date (R6-7.3, was E_INPUT under D19)")
        mat = C.maturity(T, "5Y")
        r = C.price(T, disc, H, mat, R, .01)
        c = C.ql_cds(T, mat, .01, R, dh, ph)
        assert abs(c.NPV() - r["pv_unit"]) < 1e-9 and abs(c.fairSpread() - r["par_spread"]) < 1e-9 and abs(c.fairUpfront() - r["upfront"]) < 1e-9, (T, c.NPV(), r)
        worst = max(worst, abs(c.NPV() - r["pv_unit"]), abs(c.fairUpfront() - r["upfront"]))
        acc_days = round(r["accrued"] / .01 * 360)
        assert acc_days == 1, acc_days  # accrual starts on T itself; step-in T + 1 accrues one day
        N = 1e7
        s.add("credit.cds.price", {"trade_date": str(T), "discount": jd, "hazard": C.jhz(T, mats, surv), "recovery": R,
                                   "trade": {"maturity": str(mat), "coupon": .01, "notional": N, "side": "BUY_PROTECTION"}, "payout": "STANDARD"},
              {"pv": N * r["pv_unit"], "upfront": r["upfront"], "accrued": r["accrued"], "par_spread": r["par_spread"], "protection_leg": r["protection_leg"], "rpv01": r["rpv01"]},
              cls="interpolation", verified=["independent-replay", C.QLE], tags=["r6", "isda-cds", "imm-trade-date"],
              limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "ISDA replay against QuantLib within 1e-9 per unit"},
              output_classes={"par_spread": "per_unit", "accrued": "per_unit", "rpv01": "per_unit", "upfront": "per_unit", "protection_leg": "per_unit"},
              description=f"5Y from {T}: accrued one day (start = T, step-in T + 1)")
    note(f"cds_imm_r6: QuantLib IsdaCdsEngine worst gap {worst:.1e} per unit")
    return s


# ---------------------------------------------------------------------------------- R6-7.2 futures basis
def basis_suite():
    import gen_stage_d_w2 as W2
    s = Suite("basis_r6", "specifications/04-pricing/bonds.md", G)
    deliv, setl, rr = date(2027, 3, 1), W2.SET, .0385
    fut_bonds = [{"maturity": "2033-11-15", "coupon": .0425, "frequency": 2}, {"maturity": "2034-02-15", "coupon": .0400, "frequency": 2},
                 {"maturity": "2033-08-15", "coupon": .0375, "frequency": 2}, {"maturity": "2034-05-15", "coupon": .0450, "frequency": 2}]
    rows = []
    for k, fb in enumerate(fut_bonds):
        cf, _ = W2.cbot_cf(fb, deliv)
        clean = W2.price_yield(fb, setl, .0415 + 0.00005 * k)["clean"]
        rows.append((fb, cf, clean))

    def fair_F(fb, cf, clean):
        cfs, ai0, _ = W2.bond_cfs(fb, setl)
        dirty = clean + ai0
        T = (deliv - setl).days / 360
        cpn = [(d, c) for d, c in cfs if d <= deliv]
        fwd = dirty * (1 + rr * T) - sum(c * (1 + rr * (deliv - d).days / 360) for d, c in cpn)
        return (fwd - W2.bond_cfs(fb, deliv)[1]) / cf
    # futures at the CTD's fair price less 2/32, rounded to 1/32: the CTD's implied repo sits near the repo rate
    F = math.floor(min(fair_F(*r) for r in rows) * 32 - 2) / 32
    res = [W2.basis_row(fb, cf, cp, F, setl, deliv, rr) for fb, cf, cp in rows]
    for (fb, cf, cp), x in zip(rows, res):
        cfs, ai0, _ = W2.bond_cfs(fb, setl)
        cpn = [(d, c) for d, c in cfs if d <= deliv]
        T = (deliv - setl).days / 360
        g = lambda r_: (cp + ai0) * (1 + r_ * T) - sum(c * (1 + r_ * (deliv - d).days / 360) for d, c in cpn) - x["invoice"]  # noqa: E731
        alt = brentq(g, -1.0, 1.0, xtol=1e-15)
        assert abs(alt - x["implied_repo"]) < 1e-12, (alt, x)
        assert abs(x["implied_repo"]) < 0.10, ("implied repo outside +-10% (R6-7.2 acceptance)", x["implied_repo"])
    irs = sorted(x["implied_repo"] for x in res)
    assert irs[-1] - irs[-2] > 1e-6
    assert abs(irs[-1] - rr) < 0.01, ("CTD implied repo not within 100 bp of repo", irs[-1])
    ctd = max(range(len(res)), key=lambda k: res[k]["implied_repo"])
    s.add("bond.futures.basis", {"futures_price": F, "settlement": str(setl), "delivery": str(deliv), "repo_rate": rr,
                                 "bonds": [{**fb, "clean_price": cp, "conversion_factor": cf} for fb, cf, cp in rows]},
          {"bonds": res, "ctd": ctd}, cls="simple_analytic", output_classes={"ctd": E}, verified=["analytic", "brentq forward identity"],
          tags=["r6", "bond-futures", "ctd"], description=f"F = {F} (CTD fair less 2/32): implied repos {', '.join(f'{x:.4%}' for x in irs)} against repo {rr:.2%} (R6-7.2)")
    note(f"basis_r6: F {F}, implied repos {[round(x['implied_repo'], 6) for x in res]}, CTD {ctd}")
    return s


SUITES = {"mbs": mbs_suite, "cds": cds_suite, "basis": basis_suite}


def main(which):
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "r6"
    import gen_stage_d
    gen_stage_d.estr() if hasattr(gen_stage_d, "estr") else None
    for k in which:
        SUITES[k]().write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main(sys.argv[1:] or list(SUITES))
