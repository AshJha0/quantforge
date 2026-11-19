import json, hashlib, os
from decimal import Decimal as D, localcontext, ROUND_HALF_EVEN

PK = "/mnt/c/Work/Claude/institutional-quant-engine-plan/stage_h_blind/paper2_packet/pt_h.inputs.json"
OUT = "/mnt/c/Work/Claude/institutional-quant-engine-plan/stage_h_blind/paper2_blind/blind_results.json"
LABEL = "crypto venue; simulated"
CEIL = "Paper trading on free data; simulated fills; no evidence of tradable profitability."
Z64 = "0" * 64


def fmt(d):
    d = D(d)
    if d == 0:
        return "0"
    with localcontext() as c:
        c.prec = 200
        return format(d.normalize(), "f")


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def mkrec(seq, ts, kind, body, prev):
    r = {"seq": seq, "ts": ts, "kind": kind, "label": LABEL, "body": body, "prev": prev}
    h = hashlib.sha256(canon(r).encode("ascii")).hexdigest()
    r2 = dict(r)
    r2["hash"] = h
    return r2


def fstr(f):
    return fmt(D(repr(f)))


def apply_fill(fills, cash=None, pos="0", avg="0"):
    n = D(pos); c = D(avg); real = D(0); fees = D(0); cd = D(0)
    with localcontext() as ctx:
        ctx.prec = 200
        for f in fills:
            s = 1 if f["side"] == "BUY" else -1
            q = D(f["quantity"]); p = D(f["price"]); fee = D(f.get("fee", "0"))
            cd -= s * q * p + fee
            fees += fee
            if n == 0 or s * n > 0:
                c = ((abs(n) * c + q * p) / (abs(n) + q)).quantize(D(1).scaleb(-18), rounding=ROUND_HALF_EVEN)
                n += s * q
            else:
                m = min(q, abs(n))
                real += m * (p - c) * (1 if n > 0 else -1)
                n += s * q
                if q > m:
                    c = p
        out = {"position": fmt(n), "avg_cost": fmt(c), "realised": fmt(real), "fees": fmt(fees), "label": LABEL}
        if cash is None:
            out["cash_delta"] = fmt(cd)
        else:
            out["cash"] = fmt(D(cash) + cd)
    return out


def verify(text):
    lines = text.splitlines()
    recs = 0
    prev = Z64

    def bad(i, why):
        return {"ok": False, "records": recs, "first_bad_seq": i, "reason": why, "head": None, "label": LABEL}

    def hook(pairs):
        ks = [k for k, _ in pairs]
        if len(ks) != len(set(ks)):
            raise ValueError("dup")
        return dict(pairs)

    def nofloat(s):
        raise ValueError("float")

    def numchk(v):
        if v is None or isinstance(v, (str, bool)):
            return True
        if isinstance(v, (int, float)):
            return False
        if isinstance(v, list):
            return all(numchk(x) for x in v)
        if isinstance(v, dict):
            return all(numchk(x) for x in v.values())
        return False

    for i, ln in enumerate(lines):
        try:
            o = json.loads(ln, object_pairs_hook=hook, parse_float=nofloat)
        except Exception:
            return bad(i, "PARSE")
        if not isinstance(o, dict) or "hash" not in o:
            return bad(i, "PARSE")
        if not all(numchk(v) for k, v in o.items() if k != "seq"):
            return bad(i, "PARSE")
        sq = o.get("seq")
        if "seq" in o and (isinstance(sq, bool) or not isinstance(sq, int)):
            return bad(i, "PARSE")
        if sq != i:
            return bad(i, "SEQ")
        r = {k: v for k, v in o.items() if k != "hash"}
        if hashlib.sha256(canon(r).encode("ascii")).hexdigest() != o["hash"]:
            return bad(i, "HASH")
        if o.get("prev") != prev:
            return bad(i, "LINK")
        if o.get("label") != LABEL:
            return bad(i, "LABEL")
        prev = o["hash"]
        recs += 1
    return {"ok": True, "records": recs, "first_bad_seq": None, "reason": None, "head": prev, "label": LABEL}


def pretrade(order, ref, pos, cash, today, L):
    s = 1 if order["side"] == "BUY" else -1
    q = D(order["quantity"]); P = D(ref)
    lim = D(order["limit_price"]) if order["type"] != "MARKET" else None
    pchk = lim if lim is not None else P * (1 + s * D(L["price_band"]))
    r = []
    if L.get("kill_switch", False): r.append("KILL_SWITCH")
    if today >= L["max_orders_per_day"]: r.append("MAX_ORDERS")
    if q > D(L["max_order_qty"]): r.append("MAX_QTY")
    if lim is not None and abs(lim - P) > D(L["price_band"]) * P: r.append("PRICE_BAND")
    if q * pchk > D(L["max_notional"]): r.append("MAX_NOTIONAL")
    if abs(D(pos) + s * q) > D(L["max_abs_position"]): r.append("MAX_POSITION")
    if not L.get("allow_short", True) and D(pos) + s * q < 0: r.append("NO_SHORT")
    if order["side"] == "BUY" and q * pchk > D(cash): r.append("INSUFFICIENT_CASH")
    return r


def walk_lit(order, snap, fs, top_only=False):
    s = 1 if order["side"] == "BUY" else -1
    q = D(order["quantity"])
    book = snap["asks"] if s == 1 else snap["bids"]
    lim = D(order["limit_price"]) if order["type"] != "MARKET" else None
    out = []
    for p, a in book:
        p = D(p); a = D(a)
        if q <= 0:
            break
        if lim is not None and ((s == 1 and p > lim) or (s == -1 and p < lim)):
            break
        t = min(q, a)
        out.append((t, p, D(fs["taker_fee"]) * t * p))
        q -= t
        if top_only:
            break
    return out, q


def session(inp):
    cash0 = D(inp["cash"]); L = inp["limits"]
    recs = []; results = []
    pos = {}; cash = cash0
    today = 0; accepted = []
    prev = Z64
    fs = inp["lit"]["fee_schedule"]

    def add(ts, kind, body):
        nonlocal prev
        r = mkrec(len(recs), ts, kind, body, prev)
        prev = r["hash"]
        recs.append(r)

    for st in inp["script"]:
        ts = st["ts"]
        if st["op"] == "SUBMIT":
            o = {k: v for k, v in st["order"].items() if k != "mode"}
            o.setdefault("venue", "LIT")
            snap = st["snapshot"]
            mid = (D(snap["bids"][0][0]) + D(snap["asks"][0][0])) / 2
            reasons = pretrade(o, mid, pos.get(o["symbol"], D(0)), cash, today, L)
            today += 1
            if reasons:
                b = dict(o); b["reasons"] = reasons
                add(ts, "REJECT", b)
                results.append({"status": "REJECTED", "reasons": reasons})
                continue
            b = dict(o); b["decision_price"] = fmt(mid)
            add(ts, "ORDER", b)
            s = 1 if o["side"] == "BUY" else -1
            Q = D(o["quantity"])
            fills = []
            if o["venue"] == "LIT":
                f, rem = walk_lit(o, snap, fs)
                fills = [(o["order_id"], "LIT", q, p, fee) for q, p, fee in f]
            else:
                # GUESS: spec of exec.sor.allocate / dark sim not in packet.
                f, rem = walk_lit(o, snap, fs, top_only=True)
                fills = [(o["order_id"] + "-LIT", "LIT", q, p, fee) for q, p, fee in f]
                room = Q - sum((x[2] for x in fills), D(0))
                contra = sum((D(e["qty"]) for e in st.get("contra", []) if e.get("op") == "NEW"), D(0))
                dq = min(room, contra)
                if dq > 0:
                    fills.append((o["order_id"] + "-DARK", "DARK", dq, mid, D(0)))
            filled = D(0)
            for child, ven, q, p, fee in fills:
                add(ts, "FILL", {"order_id": o["order_id"], "child_id": child, "venue": ven, "symbol": o["symbol"],
                                 "side": o["side"], "quantity": fmt(q), "price": fmt(p), "fee": fmt(fee)})
                filled += q
                pos[o["symbol"]] = pos.get(o["symbol"], D(0)) + s * q
                cash -= s * q * p + fee
            unf = Q - filled
            rests = unf > 0 and o["type"] == "LIMIT" and o["venue"] == "LIT"
            if unf > 0 and not rests:
                add(ts, "CANCEL", {"order_id": o["order_id"], "quantity": fmt(unf)})
            accepted.append({"o": o, "mid": mid, "fills": fills, "rests": rests, "Q": Q, "unf": unf})
            results.append({"status": "OPEN" if rests else "DONE", "filled": fmt(filled)})
        elif st["op"] == "CLOSE":
            marks = {k: D(v) for k, v in st["marks"].items()}
            days = st.get("days", 1)
            cr = D(st.get("cash_rate", "0")); dr = D(st.get("debit_rate", "0"))
            for a in accepted:
                o = a["o"]
                if a["rests"]:
                    add(ts, "CANCEL", {"order_id": o["order_id"], "quantity": fmt(a["unf"])})
                s = 1 if o["side"] == "BUY" else -1
                dec = float(a["mid"]); arr = dec; end = float(marks[o["symbol"]]); Qf = float(a["Q"])
                filledf = 0.0
                for x in a["fills"]:
                    filledf += float(x[2])
                delay = s * filledf * (arr - dec)
                sm = 0.0
                for x in a["fills"]:
                    sm += float(x[2]) * (float(x[3]) - arr)
                execu = s * sm
                opp = s * (Qf - filledf) * (end - dec) + 0.0
                fees = float(sum((x[4] for x in a["fills"]), D(0)))
                total = delay + execu + opp + fees
                bps = total / (Qf * dec) * 1e4
                add(ts, "TCA", {"order_id": o["order_id"], "delay": fstr(delay), "execution": fstr(execu),
                                "opportunity": fstr(opp), "total": fstr(total), "total_bps": fstr(bps)})
            market = D(0)  # session starts flat: n_open = 0
            trading = D(0); fee_sum = D(0)
            for a in accepted:
                s = 1 if a["o"]["side"] == "BUY" else -1
                for x in a["fills"]:
                    trading += s * x[2] * (marks[a["o"]["symbol"]] - x[3])
                    fee_sum += x[4]
            r = cr if cash0 >= 0 else dr
            interest = (cash0 * r * days / 365).quantize(D("0.01"), rounding=ROUND_HALF_EVEN)
            borrow = D(0)
            fin = interest + borrow
            total = market + trading - fee_sum + fin
            nav = cash + fin + sum((pos[k] * marks[k] for k in pos), D(0))
            eod = {"market": fmt(market), "trading": fmt(trading), "fees": fmt(-fee_sum), "financing": fmt(fin),
                   "interest": fmt(interest), "borrow": fmt(borrow), "total": fmt(total), "nav": fmt(nav),
                   "label": LABEL, "ceiling": CEIL}
            add(ts, "EOD", eod)
            results.append({"status": "CLOSED", "eod": eod})
    return {"results": results, "records": recs, "head": prev,
            "positions": {k: fmt(v) for k, v in pos.items()}, "cash": fmt(cash), "label": LABEL, "ceiling": CEIL}


def main():
    cases = json.load(open(PK))
    out = {}
    for cid, c in cases.items():
        op, i = c["operation"], c["inputs"]
        if op == "paper.book.apply_fill":
            out[cid] = apply_fill(i["fills"], i.get("cash"), i.get("position", "0"), i.get("avg_cost", "0"))
        elif op == "paper.ledger.verify":
            out[cid] = verify(i["text"])
        elif op == "paper.session.run":
            out[cid] = session(i)
    with open(OUT, "w", newline="\n") as f:
        f.write(json.dumps(out, sort_keys=True, indent=1, ensure_ascii=True) + "\n")


main()
