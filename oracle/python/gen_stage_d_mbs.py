"""Stage D golden cases, wave 3, D9: MBS prepayment (CPR, PSA) and pass-through pricing. Analytic. Same rules as gen_stage_d.py."""
from qf_oracle.common import note
import gen_stage_d as D
from gen_stage_d import A, E, S, caught, write

POOLS = [dict(balance=1e6, wac=.0650, net_coupon=.0600, wam=60, age=0, prepayment={"model": "PSA", "speed": 150.0}),
         dict(balance=2.5e6, wac=.0575, net_coupon=.0525, wam=357, age=3, prepayment={"model": "PSA", "speed": 100.0}),
         dict(balance=5e5, wac=.0425, net_coupon=.0375, wam=120, age=40, prepayment={"model": "CPR", "rate": .08})]


def flows(p, mut=None):
    B, r, n0 = p["balance"], p["wac"] / 12, p["wam"]
    bal, it, sp, pp = [], [], [], []
    for k in range(1, n0 + 1):
        age = p["age"] + k - (1 if mut == "PSA age off by one" else 0)
        pm = p["prepayment"]
        cpr = pm["rate"] if pm["model"] == "CPR" else min(age / 30, 1.0) * .06 * pm["speed"] / 100
        smm = cpr / 12 if mut == "SMM = CPR / 12" else 1 - (1 - cpr) ** (1 / 12)
        n = n0 - k + 1
        pay = B * r / (1 - (1 + r) ** (-n))
        s = pay - B * r
        pr = smm * (B - s)
        bal.append(B)
        it.append(B * (p["wac"] if mut == "interest at gross rate" else p["net_coupon"]) / 12)
        sp.append(s)
        pp.append(pr)
        B = B - s - pr
    return bal, it, sp, pp


def mbs_d():
    s = S("mbs_d", "04-pricing/mbs.md")
    cop = "mbs.cashflows"
    for p in POOLS:
        bal, it, sp, pp = flows(p)
        assert abs(bal[-1] - sp[-1] - pp[-1]) < 1e-6
        wal = sum((k + 1) / 12 * (a + b) for k, (a, b) in enumerate(zip(sp, pp))) / p["balance"]
        s.add(cop, {"pool": p}, {"balance": bal, "interest": it, "scheduled_principal": sp, "prepayment": pp, "wal": wal}, cls=A, verified=["analytic", "psa-standard"], tags=["mbs"],
              limit={"absolute": 1e-9 * p["balance"], "relative": 1e-10, "reason": "360 months of products; errors grow with length"})
        for mut in ("PSA age off by one", "SMM = CPR / 12", "interest at gross rate"):
            if mut.startswith("PSA") and p["prepayment"]["model"] != "PSA":
                continue
            if mut.startswith("PSA") and p["age"] >= 30:
                continue
            b2, i2, s2, p2 = flows(p, mut)
            gap = max(max(abs(a - b) for a, b in zip(i2, it)), max(abs(a - b) for a, b in zip(p2, pp)))
            caught("mbs_d", f"{mut}, pool {p['wam']}m", gap, 1e-9 * p["balance"] + 1e-10 * p["balance"])
    pop = "mbs.price"
    for p, y, dl in ((POOLS[0], .0550, 24), (POOLS[1], .0590, 24), (POOLS[2], .0400, 0)):
        bal, it, sp, pp = flows(p)
        cf = [a + b + c for a, b, c in zip(it, sp, pp)]
        v = 1 / (1 + y / 12)
        ts = [k + dl / 30 for k in range(1, len(cf) + 1)]
        P = sum(c * v ** t for c, t in zip(cf, ts))
        dP = sum(-t / 12 * c * v ** (t + 1) for c, t in zip(cf, ts))
        price = 100 * P / p["balance"]
        wal = sum((k + 1) / 12 * (a + b) for k, (a, b) in enumerate(zip(sp, pp))) / p["balance"]
        s.add(pop, {"pool": p, "yield": y, "delay_days": dl}, {"price": price, "modified_duration": -dP / P, "wal": wal}, cls=A, verified=["analytic"], tags=["mbs", "pass-through"])
        if dl:
            caught("mbs_d", f"payment delay ignored, pool {p['wam']}m", abs(100 * sum(c * v ** (k + 1) for k, c in enumerate(cf)) / p["balance"] - price), 1e-10 * 100)
    b = dict(POOLS[0])
    s.add(cop, {"pool": {**b, "net_coupon": .07}}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="net coupon above WAC")
    s.add(cop, {"pool": {**b, "wam": 0}}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(cop, {"pool": {**b, "prepayment": {"model": "CPR", "rate": 1.0}}}, error="E_DOMAIN", cls=E, tags=["invalid"], description="CPR in [0, 1)")
    s.add(cop, {"pool": {**b, "prepayment": {"model": "PSA", "speed": -50.0}}}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(cop, {"pool": {**b, "wac": 0.0}}, error="E_DOMAIN", cls=E, tags=["invalid", "ruling"], description="WAC must be > 0")
    s.add(pop, {"pool": b, "yield": .05, "delay_days": -1}, error="E_INPUT", cls=E, tags=["invalid"])
    note("mbs_d: PSA ramp, SMM, level-pay amortisation by the standard formulas; the last month retires the balance within 1e-6")
    write(s)


def main():
    D.MUTANTS.clear()
    mbs_d()
    note(f"stage D D9: {len(D.MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    main()
