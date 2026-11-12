"""Agency MBS pass-through cash flows and pricing (specifications/04-pricing/mbs.md)."""

from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

Pool = tuple[float, float, float, int, int, str, float]
Flows = tuple[list[float], list[float], list[float], list[float], float]


def mbs_cashflows(pool: Pool) -> dict[str, object]:
    bal, interest, sched, prepay, wal = _flows(pool)
    return {"balance": bal, "interest": interest, "scheduled_principal": sched,
            "prepayment": prepay, "wal": wal}


def _flows(pool: Pool) -> Flows:
    balance, wac, net, wam, age, model, speed = pool
    if not 1 <= wam <= 1200 or age < 0:
        raise QfError("E_INPUT", "wam must be at least 1 and age at least 0", "pool")
    if wac <= 0:
        raise QfError("E_DOMAIN", "wac must be positive", "wac")
    if net > wac:
        raise QfError("E_INPUT", "net_coupon is above wac", "net_coupon")
    if balance <= 0 or (model == "CPR" and not 0 <= speed < 1) or (model == "PSA" and speed < 0):
        raise QfError("E_DOMAIN", "balance, rate or speed out of domain", "pool")
    r = wac / 12
    b = balance
    bal, interest, sched, prepay = [], [], [], []
    for k in range(1, wam + 1):
        n = wam - k + 1
        cpr = speed if model == "CPR" else min((age + k) / 30, 1) * 0.06 * speed / 100
        if cpr > 1:  # R6 finding 18: above ~1667% PSA the SMM would be complex
            raise QfError("E_DOMAIN", "PSA speed gives a CPR above 100%", "pool")
        smm = 1 - (1 - cpr) ** (1 / 12)
        if k == wam:
            sp = b
        else:
            sp = b * r / (1 - (1 + r) ** (-n)) - b * r
        pp = smm * (b - sp)
        bal.append(b)
        interest.append(b * net / 12)
        sched.append(sp)
        prepay.append(pp)
        b = b - sp - pp
    wal = ordered_sum(k / 12 * (s + p) for k, (s, p) in enumerate(zip(sched, prepay, strict=True),
                                                                   start=1)) / balance
    return bal, interest, sched, prepay, wal


def mbs_price(pool: Pool, y: float, delay_days: int) -> tuple[float, float, float]:
    _, ints, sched, pre, wal = _flows(pool)
    if delay_days < 0:
        raise QfError("E_INPUT", "delay_days must not be negative", "delay_days")
    if not 1 + y / 12 > 0:
        raise QfError("E_DOMAIN", "1 + yield/12 must be positive", "yield")
    v = 1 / (1 + y / 12)
    terms = []
    for k, (a, b, c) in enumerate(zip(ints, sched, pre, strict=True), start=1):
        t = k + delay_days / 30
        terms.append((t, (a + b + c) * v ** t))
    pv = ordered_sum(x for _, x in terms)
    duration = ordered_sum(t / 12 * x * v for t, x in terms) / pv
    return 100 * pv / pool[0], duration, wal


guard(globals())
