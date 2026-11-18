import json, zlib, re, sys
from decimal import Decimal as D, ROUND_FLOOR, ROUND_CEILING


def fmt(d):
    if d == 0:
        return "0"
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), 'f')


# ---------------- order book ----------------
def crc_string(bids, asks, pdec, qdec):
    def f(x, dec):
        return format(D(x).quantize(D(1).scaleb(-dec)), 'f').replace('.', '').lstrip('0')
    a = sorted(asks.items(), key=lambda kv: kv[0])[:10]
    b = sorted(bids.items(), key=lambda kv: -kv[0])[:10]
    out = ""
    for p, (ps, qs) in a + b:
        out += f(ps, pdec) + f(qs, qdec)
    return out


def ob(inp):
    depth = inp["depth"]; pd = inp["price_decimals"]; qd = inp["qty_decimals"]
    bids, asks = {}, {}
    st = dict.fromkeys("messages snapshots updates level_changes deletes_of_absent_level truncated_levels checksum_checked checksum_failed checkpoint_checked checkpoint_failed crossed locked gaps resyncs".split(), 0)
    events = []
    have_snap = False

    def trunc():
        for side, rev in ((bids, True), (asks, False)):
            for k in sorted(side, reverse=rev)[depth:]:
                del side[k]
                st["truncated_levels"] += 1

    def check(i, m):
        if m.get("checksum") is not None:
            st["checksum_checked"] += 1
            if zlib.crc32(crc_string(bids, asks, pd, qd).encode()) != m["checksum"]:
                st["checksum_failed"] += 1
                events.append({"i": i, "kind": "CHECKSUM_FAIL"})
        if bids and asks:
            bb, ba = max(bids), min(asks)
            if bb > ba:
                st["crossed"] += 1; events.append({"i": i, "kind": "CROSSED"})
            elif bb == ba:
                st["locked"] += 1; events.append({"i": i, "kind": "LOCKED"})

    for i, m in enumerate(inp["messages"]):
        if m["type"] == "gap":
            bids.clear(); asks.clear(); have_snap = False
            st["gaps"] += 1; events.append({"i": i, "kind": "GAP"})
            continue
        st["messages"] += 1
        if m["type"] == "snapshot":
            st["snapshots"] += 1
            bids.clear(); asks.clear()
            for side, key in ((bids, "bids"), (asks, "asks")):
                for p, q in m[key]:
                    if D(q) != 0:
                        side[D(p)] = (p, q)
            trunc(); have_snap = True; check(i, m)
        else:
            st["updates"] += 1
            if not have_snap:
                events.append({"i": i, "kind": "UPDATE_BEFORE_SNAPSHOT"})
                continue
            for side, key in ((bids, "bids"), (asks, "asks")):
                for p, q in m[key]:
                    st["level_changes"] += 1
                    if D(q) == 0:
                        if D(p) in side:
                            del side[D(p)]
                        else:
                            st["deletes_of_absent_level"] += 1
                    else:
                        side[D(p)] = (p, q)
            trunc(); check(i, m)
    out = {"book": {"bids": [list(bids[k]) for k in sorted(bids, reverse=True)],
                    "asks": [list(asks[k]) for k in sorted(asks)]},
           "stats": st, "events": events,
           "crc32": zlib.crc32(crc_string(bids, asks, pd, qd).encode())}
    if inp.get("emit_checksum_string"):
        out["checksum_string"] = crc_string(bids, asks, pd, qd)
    return out


# ---------------- lit engine ----------------
class O:
    pass


def lit(inp):
    tick = D(inp["tick_size"]); fs = inp["fee_schedule"]
    tf = D(fs["taker_fee"]); mr = D(fs["maker_rebate"])
    resting = {}
    seqc = [0]

    def nseq():
        seqc[0] += 1
        return seqc[0]
    fills = []; rejects = []; cancelled = []
    cons = {}; fees = {}; fc = [0]

    def C(i):
        return cons.setdefault(i, dict(submitted=D(0), filled=D(0), cancelled=D(0), rejected=D(0)))

    def opp(side):
        return [o for o in resting.values() if o.side != side and o.price is not None]

    def ok_price(side, lim, p):
        return lim is None or (p <= lim if side == "BUY" else p >= lim)

    def tier(o):
        if o.kind == "PEG_MID":
            return 1
        return 0 if o.display > 0 else 2

    def match(tid, trader, side, lim, qty):
        rem = qty
        while rem > 0:
            c = [o for o in opp(side) if ok_price(side, lim, o.price) and (o.display + o.hidden) > 0]
            if not c:
                break
            bp = min(o.price for o in c) if side == "BUY" else max(o.price for o in c)
            lv = sorted([o for o in c if o.price == bp], key=lambda o: (tier(o), o.seq))
            m = lv[0]
            from_hidden = m.kind == "PEG_MID" or m.display == 0
            avail = m.hidden if from_hidden else m.display
            t = min(rem, avail)
            if from_hidden:
                m.hidden -= t
            else:
                m.display -= t
            rem -= t
            fc[0] += 1
            fills.append({"taker_id": tid, "maker_id": m.id, "price": fmt(bp), "qty": fmt(t), "seq": fc[0]})
            notional = bp * t
            fees[trader] = fees.get(trader, D(0)) + tf * notional
            fees[m.trader] = fees.get(m.trader, D(0)) - mr * notional
            C(tid)["filled"] += t; C(m.id)["filled"] += t
            if m.kind == "ICEBERG" and m.display == 0 and m.hidden > 0:
                n = min(m.dcfg, m.hidden); m.hidden -= n; m.display = n; m.seq = nseq()
            if m.display == 0 and m.hidden == 0:
                del resting[m.id]
        return rem

    def refs(side, excl=None):
        ps = [o.price for o in resting.values()
              if o.side == side and o.kind != "PEG_MID" and o is not excl and o.price is not None]
        if not ps:
            return None
        return max(ps) if side == "BUY" else min(ps)

    def peg_price(o):
        if o.kind == "PEG_MID":
            bb = refs("BUY"); ba = refs("SELL")
            if bb is None or ba is None:
                return None
            mid = (bb + ba) / 2
            if o.side == "BUY":
                return min((mid / tick).to_integral_value(ROUND_FLOOR) * tick, o.lim)
            return max((mid / tick).to_integral_value(ROUND_CEILING) * tick, o.lim)
        r = refs(o.side, o)
        if r is None:
            return None
        return min(r, o.lim) if o.side == "BUY" else max(r, o.lim)

    def reprice():
        for o in sorted([o for o in resting.values() if o.kind in ("PEG_MID", "PEG_PRIMARY")], key=lambda o: o.seq):
            p = peg_price(o)
            if p != o.price:
                o.price = p; o.seq = nseq()

    def rest(i, ev, side, qty, lim, t):
        o = O(); o.id = i; o.trader = ev["trader"]; o.side = side; o.kind = t; o.lim = lim
        o.price = lim; o.display = qty; o.hidden = D(0); o.dcfg = None
        if t == "ICEBERG":
            o.dcfg = D(ev["display_qty"]); o.display = min(o.dcfg, qty); o.hidden = qty - o.display
        elif t == "PEG_MID":
            o.display = D(0); o.hidden = qty; o.price = None
        elif t == "PEG_PRIMARY":
            o.price = None
        resting[i] = o
        if t in ("PEG_MID", "PEG_PRIMARY"):
            o.price = peg_price(o)
        o.seq = nseq()

    for ev in inp["events"]:
        op = ev["op"]; i = ev["id"]
        if op == "NEW":
            qty = D(ev["qty"]); t = ev["type"]; side = ev["side"]
            lim = D(ev["price"]) if "price" in ev else None
            C(i)["submitted"] += qty
            if t == "FOK":
                avail = sum(o.display + o.hidden for o in opp(side) if ok_price(side, lim, o.price))
                if avail < qty:
                    rejects.append({"id": i, "reason": "FOK_UNFILLABLE"}); C(i)["rejected"] += qty
                else:
                    match(i, ev["trader"], side, lim, qty)
            elif t == "POST_ONLY":
                if any(ok_price(side, lim, o.price) for o in opp(side)):
                    rejects.append({"id": i, "reason": "POST_ONLY_WOULD_CROSS"}); C(i)["rejected"] += qty
                else:
                    rest(i, ev, side, qty, lim, "LIMIT")
            elif t in ("IOC", "MARKET"):
                rem = match(i, ev["trader"], side, lim, qty)
                if rem > 0:
                    cancelled.append({"id": i, "qty": fmt(rem)}); C(i)["cancelled"] += rem
            elif t in ("LIMIT", "ICEBERG"):
                rem = match(i, ev["trader"], side, lim, qty)
                if rem > 0:
                    rest(i, ev, side, rem, lim, t)
            else:
                rest(i, ev, side, qty, lim, t)
        elif op == "CANCEL":
            if i not in resting:
                rejects.append({"id": i, "reason": "UNKNOWN_ID"})
            else:
                o = resting.pop(i); q = o.display + o.hidden
                cancelled.append({"id": i, "qty": fmt(q)}); C(i)["cancelled"] += q
        elif op == "MODIFY":
            if i not in resting:
                rejects.append({"id": i, "reason": "UNKNOWN_ID"})
            else:
                o = resting[i]; nq = D(ev["qty"]); cur = o.display + o.hidden
                if nq < cur:
                    C(i)["cancelled"] += cur - nq
                    d = cur - nq
                    if o.kind == "PEG_MID":
                        o.hidden -= d
                    else:
                        take = min(d, o.hidden); o.hidden -= take; d -= take; o.display -= d
                elif nq > cur:
                    C(i)["submitted"] += nq - cur
                    if o.kind == "PEG_MID" or o.kind == "ICEBERG":
                        o.hidden += nq - cur
                    else:
                        o.display = nq
                    o.seq = nseq()
        reprice()
    book = {}; mbp = {}
    for side, key in (("BUY", "bids"), ("SELL", "asks")):
        os_ = sorted([o for o in resting.values() if o.side == side and o.price is not None],
                     key=lambda o: ((-o.price if side == "BUY" else o.price), o.seq))
        book[key] = [{"id": o.id, "price": fmt(o.price), "display_qty": fmt(o.display),
                      "hidden_qty": fmt(o.hidden), "seq": o.seq} for o in os_]
        lv = {}
        for o in os_:
            lv[o.price] = lv.get(o.price, D(0)) + o.display
        mbp[key] = [[fmt(p), fmt(q)] for p, q in sorted(lv.items(), reverse=(side == "BUY")) if q > 0]
    for i, c in cons.items():
        o = resting.get(i); c["resting"] = (o.display + o.hidden) if o else D(0)
        assert c["submitted"] == c["filled"] + c["resting"] + c["cancelled"] + c["rejected"], (i, c)
    return {"fills": fills, "rejects": rejects, "cancelled": cancelled, "book": book, "mbp": mbp,
            "fees": {t: fmt(v) for t, v in fees.items()},
            "conservation": {i: {k: fmt(v) for k, v in c.items()} for i, c in cons.items()},
            "label": "simulated venue; not a real exchange"}


def parse_cases(path, prefix):
    txt = open(path, encoding="utf-8").read()
    return {m.group(1): json.loads(m.group(2))
            for m in re.finditer(r"^\| (%s-\d{4}) \| (\{.*\}) \|$" % prefix, txt, re.M)}


if __name__ == "__main__":
    base = sys.argv[1]
    results = {}
    for cid, inp in parse_cases(base + "/order-book.blind.md", "ob_h").items():
        results[cid] = ob(inp)
    for cid, inp in parse_cases(base + "/lit-matching.blind.md", "lit_h").items():
        results[cid] = lit(inp)
    s = json.dumps(results, sort_keys=True, separators=(",", ":"))
    open(sys.argv[2], "w", encoding="utf-8", newline="\n").write(s + "\n")
    print(len(results), sorted(results))
