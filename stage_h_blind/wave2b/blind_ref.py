import json, hashlib, itertools, os
from decimal import Decimal, getcontext
from fractions import Fraction
getcontext().prec = 60
D = Decimal


def fmt(d):
    d = D(d)
    if d == 0:
        return "0"
    return format(d.normalize(), 'f')


def r6_frac(x):  # Fraction -> str, 6dp half-even, trailing zeros stripped
    n = x * 10**6
    q, rem = divmod(n.numerator, n.denominator)
    twice = 2 * rem
    if twice > n.denominator or (twice == n.denominator and q % 2 == 1):
        q += 1
    return fmt(D(q) / D(10**6))


def r6_dec(x):
    return fmt(x.quantize(D('0.000001'), rounding='ROUND_HALF_EVEN'))


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


LABEL_D = "simulated venue; not a real dark pool"


# ---------------- dark pool ----------------
def dark_run(inp):
    cfg = inp["config"]
    p_firm = D(cfg["p_firm"])
    pen = int(cfg["penalty_events"])
    bid = ask = None
    orders = []
    fills = []
    invs = []
    susp = []
    seq = 0
    for ev_no, ev in enumerate(inp["events"], 1):
        op = ev["op"]
        if op == "BOOK":
            bid = D(ev["bid"]) if ev.get("bid") is not None else None
            ask = D(ev["ask"]) if ev.get("ask") is not None else None
        elif op == "NEW":
            seq += 1
            orders.append(dict(id=ev["id"], side=ev["side"], open=D(ev["qty"]),
                               limit=D(ev["limit"]) if "limit" in ev else None,
                               min_qty=D(ev.get("min_qty", "1")), kind=ev["kind"], seq=seq, sus=[]))
        elif op == "CANCEL":
            orders = [o for o in orders if o["id"] != ev["id"]]
        mid = None
        if bid is not None and ask is not None and bid < ask:
            mid = (bid + ask) / 2
        if mid is None:
            continue

        def elig(o):
            if o["open"] <= 0:
                return False
            if any(a <= ev_no <= b for a, b in o["sus"]):
                return False
            if o["limit"] is None:
                return True
            return o["limit"] >= mid if o["side"] == "BUY" else o["limit"] <= mid
        guard = 0
        while guard < 10000:
            guard += 1
            match = None
            buys = sorted([o for o in orders if o["side"] == "BUY" and elig(o)], key=lambda o: o["seq"])
            sells = sorted([o for o in orders if o["side"] == "SELL" and elig(o)], key=lambda o: o["seq"])
            for b in buys:
                for s in sells:
                    q = min(b["open"], s["open"])
                    if q >= b["min_qty"] and q >= s["min_qty"]:
                        match = (b, s, q)
                        break
                if match:
                    break
            if not match:
                break
            b, s, q = match
            conds = [(o, c) for o, c in ((b, s), (s, b)) if o["kind"] == "CONDITIONAL"]
            if conds:
                declined = False
                for o, c in conds:
                    res = "FIRMED" if p_firm == 1 else "DECLINED"
                    invs.append(dict(id=o["id"], contra_id=c["id"], event=ev_no, result=res))
                    if res == "DECLINED":
                        declined = True
                        o["sus"].append((ev_no, ev_no + pen))
                        susp.append(dict(id=o["id"], from_event=ev_no + 1, to_event=ev_no + pen))
                if declined:
                    continue
            b["open"] -= q
            s["open"] -= q
            fills.append(dict(buy_id=b["id"], sell_id=s["id"], price=fmt(mid), qty=fmt(q), seq=len(fills) + 1))
    resting = [dict(id=o["id"], side=o["side"], open_qty=fmt(o["open"]), seq=o["seq"])
               for o in sorted(orders, key=lambda o: o["seq"]) if o["open"] > 0]
    return dict(fills=fills, invitations=invs, suspensions=susp, resting=resting, label=LABEL_D)


def markouts(inp):
    out = []
    for f in inp["fills"]:
        sg = D(1) if f["side"] == "BUY" else D(-1)
        fp = D(f["fill_price"])
        m = {}
        for h, mid in f["mid_at"].items():
            m[h] = r6_dec(sg * (D(mid) - fp) / fp * 10000)
        out.append(dict(markouts_bp=m))
    return dict(fills=out)


# ---------------- SOR ----------------
def sor(inp):
    S = int(D(inp["S"]))

    def F(k):
        return Fraction(inp[k])
    h, f, th, lu, lo = F("h"), F("f"), F("theta"), F("lambda_u"), F("lambda_o")
    venues = inp["venues"]
    rows = inp["lit_samples"]
    lit_idx = [i for i, v in enumerate(venues) if v["kind"] == "LIT"]
    dark_dists = {}
    for i, v in enumerate(venues):
        if v["kind"] == "DARK":
            T = [Fraction(1)] + [Fraction(t) for t in v["tail"]] + [Fraction(0)]
            dark_dists[i] = [(k, T[k] - T[k + 1]) for k in range(len(T) - 1) if T[k] - T[k + 1] != 0]
    scen = []
    dk = sorted(dark_dists)
    for row in rows:
        for combo in itertools.product(*[dark_dists[i] for i in dk]):
            w = Fraction(1, len(rows))
            for _, p in combo:
                w *= p
            xi = {lit_idx[j]: Fraction(row[j]) for j in range(len(lit_idx))}
            s = {i: combo[j][0] for j, i in enumerate(dk)}
            scen.append((w, xi, s))
    K = len(venues)
    res = []
    for tup in itertools.product(range(S + 1), repeat=1 + K):
        M, L = tup[0], tup[1:]
        ec = ef = pu = Fraction(0)
        for w, xi, s in scen:
            A = Fraction(M)
            cost = (h + f) * M
            for k, v in enumerate(venues):
                if v["kind"] == "LIT":
                    Q = Fraction(v["Q"])
                    x = xi[k]
                    fill = max(x - Q, 0) - max(x - Q - L[k], 0)
                else:
                    fill = Fraction(min(L[k], s[k]))
                A += fill
                cost -= (h + Fraction(v["r"]) - Fraction(v["as"])) * fill
            under = max(S - A, 0)
            over = max(A - S, 0)
            cost += th * (M + sum(L) + under) + lu * under + lo * over
            ec += w * cost
            ef += w * min(A, S)
            pu += w * (1 if A < S else 0)
        res.append((ec, tup, ef, pu))
    res.sort(key=lambda r: (r[0], r[1]))
    ec, tup, ef, pu = res[0]
    out = dict(M=str(tup[0]), L=[str(x) for x in tup[1:]], expected_cost=r6_frac(ec),
               expected_fill=r6_frac(ef), p_underfill=r6_frac(pu))
    return out, res


# ---------------- paper trading ----------------
LABEL_P = "crypto venue; simulated"


def q2(x):
    return D(x).quantize(D('0.01'), rounding='ROUND_HALF_EVEN')


class Book:
    def __init__(s, cash):
        s.cash = D(cash)
        s.n = D(0)
        s.c = D(0)
        s.real = D(0)
        s.fees = D(0)

    def fill(s, side, q, p, fee):
        sg = 1 if side == "BUY" else -1
        q = D(q)
        p = D(p)
        fee = D(fee)
        s.cash -= sg * q * p + fee
        s.fees += fee
        if s.n == 0 or (s.n > 0) == (sg > 0):
            s.c = (abs(s.n) * s.c + q * p) / (abs(s.n) + q)
            s.n += sg * q
        else:
            m = min(q, abs(s.n))
            s.real += m * (p - s.c) * (1 if s.n > 0 else -1)
            rem = q - m
            s.n += sg * m
            if rem > 0:
                s.c = p
                s.n += sg * rem
            elif s.n == 0:
                s.c = D(0)


def eod(n_open, p_prev, close, cash_open, fills, cash_rate="0", debit_rate="0", borrow_rate="0", d=1):
    close = D(close)
    mkt = D(n_open) * (close - D(p_prev)) if n_open != 0 else D(0)
    trading = sum(((1 if sd == "BUY" else -1) * D(q) * (close - D(p)) for sd, q, p, fee in fills), D(0))
    fees = -sum((D(fee) for *_, fee in fills), D(0))
    r = D(cash_rate) if D(cash_open) >= 0 else D(debit_rate)
    ci = q2(D(cash_open) * r * d / 365)
    bor = D(0)
    if D(n_open) < 0:
        bor = -q2(abs(D(n_open)) * D(p_prev) * D(borrow_rate) * d / 365)
    fin = ci + bor
    return dict(market=mkt, trading=trading, fees=fees, financing=fin, total=mkt + trading + fees + fin,
                cash_interest=ci, short_borrow=bor)


def fmtd(dd):
    return {k: fmt(v) for k, v in dd.items()}


LIM = dict(max_order_qty=D(10), max_notional=D(1000), max_abs_position=D(5), price_band=D("0.05"),
           max_orders_per_day=3, kill_switch=False, allow_short=True)


def pretrade(order, pref=D(100), n=D(0), cash=D(10000), today=0, lim=LIM, mode="simulated"):
    if mode != "simulated":
        return dict(error="E_UNSUPPORTED_OPERATION")
    sg = 1 if order["side"] == "BUY" else -1
    q = D(order["qty"])
    pchk = D(order["limit"]) if order["type"] == "LIMIT" else pref * (1 + sg * lim["price_band"])
    r = []
    if lim["kill_switch"]:
        r.append("KILL_SWITCH")
    if today >= lim["max_orders_per_day"]:
        r.append("MAX_ORDERS")
    if q > lim["max_order_qty"]:
        r.append("MAX_QTY")
    if order["type"] == "LIMIT" and abs(D(order["limit"]) - pref) / pref > lim["price_band"]:
        r.append("PRICE_BAND")
    if q * pchk > lim["max_notional"]:
        r.append("MAX_NOTIONAL")
    if abs(n + sg * q) > lim["max_abs_position"]:
        r.append("MAX_POSITION")
    if (not lim["allow_short"]) and n + sg * q < 0:
        r.append("NO_SHORT")
    if order["side"] == "BUY" and q * pchk > cash:
        r.append("INSUFFICIENT_CASH")
    return dict(accepted=not r, reasons=r)


def rec_hash(rec):
    r = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(canon(r).encode("ascii")).hexdigest()


def verify(recs):
    prev = "0" * 64
    for i, r in enumerate(recs):
        bad = None
        if r.get("seq") != i:
            bad = "SEQ"
        elif r.get("hash") != rec_hash(r):
            bad = "HASH"
        elif r.get("prev") != prev:
            bad = "LINK"
        elif r.get("label") != LABEL_P:
            bad = "LABEL"
        if bad:
            return dict(ok=False, records=len(recs), first_bad_seq=i, reason=bad)
        prev = r["hash"]
    return dict(ok=True, records=len(recs), first_bad_seq=None, reason=None)


def mkrec(seq, ts, kind, body, prev, label=LABEL_P):
    r = dict(seq=seq, ts=ts, kind=kind, body=body, prev=prev)
    if label is not None:
        r["label"] = label
    r["hash"] = rec_hash(r)
    return r


def main():
    R = {}
    base = {"firm_delay": 0, "lot_size": "1", "p_firm": "1", "penalty_events": 2, "seed": 20261118, "tick_size": "0.01"}

    def cfg(p):
        c = dict(base)
        c["p_firm"] = p
        return c
    book = {"op": "BOOK", "bid": "100.00", "ask": "100.10"}

    def N(id, side, qty, kind="FIRM", **k):
        return dict(op="NEW", id=id, side=side, qty=qty, kind=kind, **k)
    R["dark_h-0001"] = dark_run(dict(config=cfg("1"), events=[book, N("B1", "BUY", "100"), N("S1", "SELL", "60")]))
    R["dark_h-0002"] = dark_run(dict(config=cfg("1"), events=[book, N("B1", "BUY", "100", min_qty="80"), N("S1", "SELL", "60")]))
    R["dark_h-0003"] = dark_run(dict(config=cfg("1"), events=[book, N("B1", "BUY", "100", limit="100.04"), N("S1", "SELL", "60"),
                                {"op": "BOOK", "bid": "100.00", "ask": "100.01"}, {"op": "BOOK", "bid": "100.02", "ask": "100.02"}]))

    def sc(p):
        return dict(config=cfg(p), events=[book, N("C1", "BUY", "50", "CONDITIONAL"), N("S1", "SELL", "30"),
                    {"op": "BOOK", "bid": "100.00", "ask": "100.20"}, {"op": "BOOK", "bid": "100.00", "ask": "100.20"},
                    {"op": "BOOK", "bid": "100.00", "ask": "100.30"}])
    R["dark_h-0004"] = dict(scenarios=[dark_run(sc("1")), dark_run(sc("0"))])
    mo = {"1": "100.07", "10": "100.00", "60": "100.15"}
    R["dark_h-0007"] = markouts(dict(fills=[dict(fill_price="100.05", mid_at=mo, side="BUY"),
                                            dict(fill_price="100.05", mid_at=mo, side="SELL")]))
    # SOR
    b = dict(S="10", f="0.3", h="0.5", lambda_o="1", theta="0")

    def lit(Q, r):
        return {"Q": Q, "as": "0", "kind": "LIT", "r": r}
    R["sor_h-0001"] = sor(dict(b, lambda_u="0.1", lit_samples=[["10"], ["12"], ["15"]], venues=[lit("0", "0.2")]))[0]
    R["sor_h-0002"] = sor(dict(b, lambda_u="10", lit_samples=[["0"], ["0"], ["0"], ["2"]], venues=[lit("0", "0.2")]))[0]
    R["sor_h-0003"] = sor(dict(b, lambda_u="4", lit_samples=[[x] for x in "0 2 4 6 8 10 12 14".split()], venues=[lit("2", "0.2")]))[0]
    R["sor_h-0005"] = sor(dict(b, S="4", lambda_u="1", lit_samples=[["0"], ["4"]],
                               venues=[lit("0", "0.2"), {"as": "0.1", "kind": "DARK", "r": "0", "tail": ["0.5", "0.5", "0.5", "0"]}]))[0]
    o, rk = sor(dict(b, S="2", lambda_u="1", lit_samples=[["0", "1"], ["2", "3"]], venues=[lit("0", "0.3"), lit("1", "0.1")]))
    o["ranking"] = [dict(M=str(t[0]), L=[str(x) for x in t[1:]], expected_cost=r6_frac(c)) for c, t, _, _ in rk]
    R["sor_h-0006"] = o
    # paper
    bk = Book("10000")
    bk.fill("BUY", "2", "100", "0.20")
    bk.fill("SELL", "1", "110", "0.11")
    R["pt_h-0001"] = dict(avg_cost=fmt(bk.c), cash=fmt(bk.cash), fees=fmt(bk.fees), position=fmt(bk.n), realised=fmt(bk.real))
    fl = [("BUY", "2", "100", "0.20"), ("SELL", "1", "110", "0.11")]
    e = eod(0, "0", "105", "10000", fl)
    cash2 = bk.cash + e["financing"]
    R["pt_h-0002"] = dict(fmtd(e), nav_close=fmt(cash2 + bk.n * 105), nav_open="10000", cash_close=fmt(cash2), position="1")
    e = eod(1, "105", "102", cash2, [], cash_rate="0.0365")
    c3 = cash2 + e["financing"]
    R["pt_h-0003"] = dict(fmtd(e), nav_close=fmt(c3 + 102), nav_open=fmt(cash2 + 105), cash_close=fmt(c3), position="1")
    e = eod(-2, "50", "50", "10100", [], cash_rate="0.0365", borrow_rate="0.0730")
    c4 = D("10100") + e["financing"]
    R["pt_h-0004"] = dict(fmtd(e), nav_close=fmt(c4 - 2 * 50), nav_open=fmt(D(10100) - 100), cash_close=fmt(c4), position="-2")
    b5 = Book("0")
    b5.n = D(1)
    b5.c = D(100)
    b5.fill("SELL", "3", "90", "0")
    R["pt_h-0005"] = dict(avg_cost=fmt(b5.c), cash_delta=fmt(b5.cash), fees=fmt(b5.fees), position=fmt(b5.n), realised=fmt(b5.real))
    e = eod(0, "0", "0", "-1000", [], debit_rate="0.0730", d=3)
    R["pt_h-0006"] = dict(fmtd(e), cash_close=fmt(D(-1000) + e["financing"]), position="0")

    def O(side, qty, typ, limit=None):
        d = dict(side=side, qty=qty, type=typ)
        if limit:
            d["limit"] = limit
        return d
    base_o = O("BUY", "3", "LIMIT", "101")
    R["pt_h-0010"] = pretrade(base_o)
    R["pt_h-0011"] = pretrade(O("BUY", "11", "LIMIT", "100"))
    R["pt_h-0012"] = pretrade(O("BUY", "3", "LIMIT", "106"))
    R["pt_h-0013"] = pretrade(O("SELL", "10", "LIMIT", "100"), n=D(4))
    R["pt_h-0014"] = pretrade(O("BUY", "3", "MARKET"), cash=D(300))
    R["pt_h-0015"] = pretrade(base_o, today=3)
    R["pt_h-0016"] = pretrade(base_o, lim=dict(LIM, kill_switch=True))
    R["pt_h-0017"] = pretrade(O("SELL", "2", "LIMIT", "100"), n=D(1), lim=dict(LIM, allow_short=False))
    R["pt_h-0018"] = pretrade(base_o, mode="live")
    body = dict(order_id="O1", symbol="BTC-USD", side="BUY", type="LIMIT", quantity="3", limit_price="101")
    TS = "2026-11-18T00:00:01Z"
    r0 = mkrec(0, TS, "ORDER", body, "0" * 64)
    R["pt_h-0020"] = dict(canonical_bytes=canon({k: v for k, v in r0.items() if k != "hash"}), hash=r0["hash"],
                          record=r0, verify=verify([r0]))
    t = json.loads(json.dumps(r0))
    t["body"]["limit_price"] = "102"
    R["pt_h-0021"] = dict(verify=verify([t]))
    r1 = mkrec(1, "2026-11-18T00:00:02Z", "ORDER", dict(body, order_id="O2"), "0" * 64)
    R["pt_h-0022"] = dict(verify=verify([r0, r1]))
    nl = mkrec(0, TS, "ORDER", body, "0" * 64, label=None)
    R["pt_h-0023"] = dict(hash=nl["hash"], record=nl, verify=verify([nl]))
    here = os.path.dirname(os.path.abspath(__file__))
    data = (canon(R) + "\n").encode("ascii")
    with open(os.path.join(here, "blind_results.json"), "wb") as fh:
        fh.write(data)
    with open(os.path.join(here, "blind_results.sha256"), "w") as fh:
        fh.write(hashlib.sha256(data).hexdigest() + " *blind_results.json\n")
    print(len(R), hashlib.sha256(data).hexdigest())
    print(json.dumps(R, indent=1, sort_keys=True))


main()
