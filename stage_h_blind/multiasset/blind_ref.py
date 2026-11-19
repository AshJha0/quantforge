import json
from decimal import Decimal as D, getcontext, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN
from fractions import Fraction as F
import datetime as dt
getcontext().prec = 80


def s(d):
    return format(D(d), 'f')


def err(code):
    return {"status": "error", "error_code": code}


LAB_SIM = "simulated venue; not a real exchange"
LAB_FX = "simulated venue; not a real exchange; no real FX data"
LAB_RT = "simulated venue; not a real exchange; no real rates data"


def ok(label, **kw):
    r = {"status": "ok", "label": label}
    r.update(kw)
    return r


# ---- equities
TABLE = ((D(0), D("0.0001")), (D(1), D("0.01")))


def tick_for(price):
    t = None
    for fl, tk in TABLE:
        if fl <= price:
            t = tk
    return t


def round_price(price, side):
    price = D(price)
    if price <= 0:
        return err("E_DOMAIN")
    t = tick_for(price)
    n = (price / t).to_integral_value(ROUND_FLOOR if side == "BUY" else ROUND_CEILING)
    return ok(LAB_SIM, price=s((n * t).quantize(t)), tick=s(t))


def fee_check(fee, price, cap_check=True):
    price = D(price)
    fee = D(fee)
    cap = D("0.003") if price >= 1 else price * D("0.003")
    if cap_check and fee > cap:
        return err("E_DOMAIN")
    return ok(LAB_SIM, taker_fee=s(fee), cap=s(cap))


def bday(d, hol=()):
    return d.weekday() < 5 and d not in hol


def add_bd(d, n, okf):
    while n > 0:
        d += dt.timedelta(1)
        if okf(d):
            n -= 1
    return d


# ---- auction
INF = D("Infinity")


def uncross(orders, tick, ref):
    tick = D(tick)
    ref = D(ref)
    buys = [o for o in orders if o["side"] == "B"]
    sells = [o for o in orders if o["side"] == "S"]
    lims = [D(o["limit"]) for o in orders if o["limit"] != "MARKET"]
    mk = [o["id"] for o in orders if o["limit"] == "MARKET"]

    def resting(rem):
        return [{"id": o["id"], "side": o["side"], "limit": o["limit"], "qty": rem.get(o["id"], o["qty"])}
                for o in orders if o["limit"] != "MARKET" and rem.get(o["id"], o["qty"]) > 0]

    def none():
        return ok(LAB_SIM, price=None, volume=0, imbalance=0, fills=[], residual=resting({}), cancelled=mk)

    if not lims or not buys or not sells:
        return none()
    lo, hi = min(lims), max(lims)
    cands = []
    p = lo
    while p <= hi:
        cands.append(p)
        p += tick
    bl = lambda o: INF if o["limit"] == "MARKET" else D(o["limit"])
    sl = lambda o: D(0) if o["limit"] == "MARKET" else D(o["limit"])
    rows = []
    for p in cands:
        B = sum(o["qty"] for o in buys if bl(o) >= p)
        S = sum(o["qty"] for o in sells if sl(o) <= p)
        rows.append((p, min(B, S), B - S))
    mv = max(r[1] for r in rows)
    if mv == 0:
        return none()
    r = [x for x in rows if x[1] == mv]
    mi = min(abs(x[2]) for x in r)
    r = [x for x in r if abs(x[2]) == mi]
    if len(r) > 1:
        if all(x[2] > 0 for x in r):
            r = [max(r, key=lambda x: x[0])]
        elif all(x[2] < 0 for x in r):
            r = [min(r, key=lambda x: x[0])]
    if len(r) > 1:
        md = min(abs(x[0] - ref) for x in r)
        r = [x for x in r if abs(x[0] - ref) == md]
    if len(r) > 1:
        r = [max(r, key=lambda x: x[0])]
    pp, V, I = r[0]

    def alloc(side_orders, key, eligible):
        left = V
        res = []
        rem = {}
        for o in sorted([o for o in side_orders if eligible(o)], key=key):
            f = min(o["qty"], left)
            left -= f
            if f > 0:
                res.append({"id": o["id"], "side": o["side"], "qty": f, "price": s(pp)})
            rem[o["id"]] = o["qty"] - f
        return res, rem

    fb, rb = alloc(buys, lambda o: (-bl(o), o["seq"]), lambda o: bl(o) >= pp)
    fs, rs = alloc(sells, lambda o: (sl(o), o["seq"]), lambda o: sl(o) <= pp)
    rb.update(rs)
    return ok(LAB_SIM, price=s(pp), volume=V, imbalance=I, fills=fb + fs, residual=resting(rb),
              cancelled=[i for i in mk if rb.get(i, 1) > 0])


# ---- FX
def stream(mid, half_pips, tick, pip=D("0.0001")):
    mid = D(mid)
    h = D(half_pips) * pip
    tick = D(tick)
    bid = ((mid - h) / tick).to_integral_value(ROUND_FLOOR) * tick
    ask = ((mid + h) / tick).to_integral_value(ROUND_CEILING) * tick
    return ok(LAB_FX, quotes=[{"time": 0, "mid": s(mid), "bid": s(bid.quantize(tick)), "ask": s(ask.quantize(tick))}])


def request(bid, ask, qmid, side, mid_after, thr, sym, p, u, pip=D("0.0001")):
    bid, ask, qmid, mid_after, thr, p, u = map(D, (bid, ask, qmid, mid_after, thr, p, u))
    move = (mid_after - qmid) / pip
    adverse = move > 0 if side == "BUY" else move < 0
    px = ask if side == "BUY" else bid
    out = None
    if sym:
        if abs(move) > thr:
            out = "LL_PRICE"
    elif adverse and abs(move) > thr:
        out = "LL_PRICE"
    if out is None and u < p:
        out = "LL_RANDOM"
    if out:
        return ok(LAB_FX, outcome=out, price=None, move_pips=s(move))
    return ok(LAB_FX, outcome="FILL", price=s(px), move_pips=s(move))


PRI = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]


def spot(pair, trade, hols):
    b, q = pair[:3], pair[3:]
    if b not in PRI or q not in PRI or PRI.index(b) >= PRI.index(q):
        return err("E_INPUT")
    h = lambda c: hols.get(c, set())
    good = lambda d: bday(d) and d not in h(b) and d not in h(q)
    d = add_bd(trade, 1 if pair == "USDCAD" else 2, good)
    while not (good(d) and d not in h("USD")):
        d += dt.timedelta(1)
    return ok(LAB_FX, spot_date=d.isoformat())


def pipval(pair, notional):
    pip = D("0.01") if pair[3:] == "JPY" else D("0.0001")
    return ok(LAB_FX, pip=s(pip), pip_value=s(D(notional) * pip), currency=pair[3:])


# ---- rates
FR = {"": F(0), "1": F(1, 8), "2": F(1, 4), "+": F(1, 2), "5": F(5, 8), "6": F(3, 4), "7": F(7, 8)}
INV = {v: k for k, v in FR.items()}


def parse32(t):
    h, rest = t.split("-", 1)
    if len(rest) < 2 or not rest[:2].isdigit():
        return None
    ff = int(rest[:2])
    f = rest[2:]
    if ff > 31 or f not in FR:
        return None
    return F(int(h)) + (ff + FR[f]) / 32


def todec(fr):
    return D(fr.numerator) / D(fr.denominator)


def parse(t):
    v = parse32(t)
    if v is None:
        return err("E_DOMAIN")
    return ok(LAB_RT, value=s(todec(v)), fraction="%d/%d" % (v.numerator, v.denominator))


def fmt32(x, res):
    n = x * res
    if n.denominator != 1:
        return err("E_DOMAIN")
    h, r = divmod(int(n), res)
    t32 = F(r * 32, res)
    ff = int(t32)
    frac = t32 - ff
    if frac not in INV:
        return err("E_DOMAIN")
    return ok(LAB_RT, text="%d-%02d%s" % (h, ff, INV[frac]))


def bond_price(c, y, n, f=2):
    c, y = D(c), D(y)
    cp = 100 * c / f
    r = 1 + y / f
    return sum(cp / r ** i for i in range(1, n + 1)) + 100 / r ** n


def q12(p):
    return s(p.quantize(D("1e-12"), ROUND_HALF_EVEN))


def fut_ticks(text, tick):
    n = parse32(text) / tick
    return int(n) if n.denominator == 1 else None


def roundtrip(buy, sell, qty, tick, tv, fee):
    tb, ts = fut_ticks(buy, tick), fut_ticks(sell, tick)
    if tb is None or ts is None:
        return err("E_DOMAIN")
    gross = D(ts - tb) * qty * D(tv)
    fees = D(fee) * qty * 2
    return ok(LAB_RT, buy_ticks=tb, sell_ticks=ts, gross=s(gross), fees=s(fees), pnl=s(gross - fees))


R = {}
for i, (side, px) in enumerate([("BUY", "10.005"), ("SELL", "10.005"), ("BUY", "0.12345"),
                                ("SELL", "0.12345"), ("SELL", "0.99995"), ("BUY", "25.00")], 1):
    R["eqc_h-000%d" % i] = round_price(px, side)
R["eqc_h-0007"] = fee_check("0.0031", 20)
R["eqc_h-0008"] = ok(LAB_SIM, settle_date=add_bd(dt.date(2026, 11, 20), 1, bday).isoformat())
R["fxc_h-0001"] = pipval("EURUSD", 1000000)
R["fxc_h-0002"] = pipval("USDJPY", 1000000)
R["fxc_h-0003"] = spot("EURUSD", dt.date(2026, 11, 16), {})
R["fxc_h-0004"] = spot("EURUSD", dt.date(2026, 11, 24), {"USD": {dt.date(2026, 11, 26)}})
R["fxc_h-0005"] = spot("EURUSD", dt.date(2026, 11, 20), {})
R["fxc_h-0006"] = spot("USDCAD", dt.date(2026, 11, 20), {})
R["fxc_h-0007"] = spot("USDEUR", dt.date(2026, 11, 16), {})
for i, t in enumerate(["99-16", "99-16+", "99-162", "99-167"], 1):
    R["rtc_h-000%d" % i] = parse(t)
R["rtc_h-0005"] = fmt32(F(101296875, 1000000), 64)
R["rtc_h-0006"] = fmt32(F(1013, 10), 128)
R["rtc_h-0007"] = ok(LAB_RT, tick_value=s(D(100000) * (D(1) / D(64)) / 100))
R["rtc_h-0008"] = ok(LAB_RT, price=q12(bond_price("0.04", "0.05", 2)))
R["rtc_h-0009"] = ok(LAB_RT, price=q12(bond_price("0.04", "0.04", 4)))
R["rtc_h-0010"] = ok(LAB_RT, price=q12(100 * (1 - D("0.05") * 91 / 360)))


def O(i, side, lim, q, seq):
    return {"id": i, "side": side, "limit": lim, "qty": q, "seq": seq}


base = [O("s1", "B", "10.02", 100, 1), O("s2", "B", "10.01", 200, 2), O("s3", "B", "10.00", 300, 3),
        O("s4", "S", "9.99", 150, 4), O("s5", "S", "10.01", 250, 5), O("s6", "S", "10.03", 100, 6)]
R["auc_h-0001"] = uncross(base, "0.01", "10.00")
R["auc_h-0002"] = uncross(base, "0.01", "10.00")
two = [O("b1", "B", "10.02", 100, 1), O("a1", "S", "10.00", 100, 2)]
R["auc_h-0003"] = uncross(two, "0.01", "10.01")
R["auc_h-0004"] = uncross(two, "0.01", "10.05")
R["auc_h-0005"] = uncross(two, "0.01", "10.005")
R["auc_h-0006"] = uncross([O("b1", "B", "10.02", 200, 1), O("a1", "S", "10.00", 100, 2),
                           O("a2", "S", "10.01", 50, 3)], "0.01", "10.00")
R["auc_h-0007"] = uncross([O("b1", "B", "MARKET", 100, 1), O("a1", "S", "MARKET", 100, 2)], "0.01", "0")
R["auc_h-0008"] = uncross([O("b1", "B", "10.00", 100, 1), O("b2", "B", "10.01", 100, 2)], "0.01", "0")

R["fxv_h-0001"] = stream("1.08512", 1, "0.00001")
R["fxv_h-0002"] = stream("1.085125", 1, "0.00001")
q = ("1.0850", "1.0852", "1.0851")
R["fxv_h-0003"] = request(*q, "BUY", "1.0855", 2, True, "0.05", "0.50")
R["fxv_h-0004"] = request(*q, "BUY", "1.0852", 2, True, "0.05", "0.50")
R["fxv_h-0005"] = request(*q, "BUY", "1.0852", 2, True, "0.05", "0.03")
R["fxv_h-0006"] = request(*q, "BUY", "1.0847", 2, True, "0.05", "0.50")
R["fxv_h-0007"] = request(*q, "BUY", "1.0847", 2, False, "0.05", "0.50")
R["fxv_h-0008"] = request(*q, "SELL", "1.0848", 2, False, "0.05", "0.50")
R["fxv_h-0009"] = request(*q, "BUY", "1.0853", 2, True, "0.05", "0.50")

T64, T32 = F(1, 64), F(1, 32)
R["fut_h-0001"] = ok(LAB_RT, ticks=fut_ticks("110-16+", T64))
R["fut_h-0002"] = fmt32(F(7073, 64), 64)
n = parse32("110-162") / T64
R["fut_h-0003"] = err("E_DOMAIN") if n.denominator != 1 else ok(LAB_RT, ticks=int(n))
R["fut_h-0004"] = roundtrip("110-16", "110-17+", 3, T64, "15.625", "0")
R["fut_h-0005"] = roundtrip("110-16", "110-17+", 3, T64, "15.625", "1.00")
tb, ts = fut_ticks("120-00", T32), fut_ticks("119-31", T32)
R["fut_h-0006"] = ok(LAB_RT, entry_ticks=tb, settle_ticks=ts,
                     variation_margin=s(D(ts - tb) * D("31.25")), pnl=s(D(ts - tb) * D("31.25")))

js = json.dumps(R, sort_keys=True, indent=1)
open("blind_results.json", "w", newline="\n").write(js + "\n")
print(len(R))
print(js)
