"""Daily paper ledger (specifications/12-platform/paper-ledger-daily.md, rulings KR-70 to KR-89).

Standard library only. Every financial number of a day comes from a CLI operation (calendar, curve
interpolation, bond price, pre-trade estimate, pre-trade check, lit venue simulator, post-trade attribution,
book legs): `build_day` only arranges the calls, changes units, rounds floats to the stated decimals and adds
decimals. `replay` is a second, independent path: it re-derives every day's cash, positions, P&L and explain
terms from the ledger rows alone, in exact decimal, with no CLI and no other data.

Nothing here reaches a venue or places an order. Fills come from the simulator only.
"""
import datetime as dt
import hashlib
import json
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FORMAT = "qf-paper-ledger/1"
GENESIS = "0" * 64
KINDS = ("GENESIS", "DAY", "GAP")
D0 = Decimal(0)
CENT = Decimal("0.01")
DAY_FLOAT_TOL = Decimal("0.000001")  # KR-86: one unit of the last recorded decimal of a mark


class PaperError(Exception):
    """A refusal: the run writes nothing."""


def load_config(path=None):
    return json.loads(Path(path or HERE / "config.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ numbers


def plain(d):
    """A decimal as a plain string: no exponent, no trailing zeros, no negative zero."""
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def fstr(x):
    """A binary64 result of a CLI operation as the shortest decimal string that reads back to it."""
    return plain(Decimal(repr(float(x))))


def rstr(x, places):
    """A binary64 result rounded half-even to `places` decimals (KR-76)."""
    return plain(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-places), ROUND_HALF_EVEN))


def strings(v):
    """Every scalar as a string, so the tree fits the canonical form (only `seq` is an integer)."""
    if isinstance(v, dict):
        return {k: strings(x) for k, x in v.items()}
    if isinstance(v, list):
        return [strings(x) for x in v]
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return fstr(v)
    return str(v)


# ------------------------------------------------------------------ ledger rows and chain (KR-80, KR-81)


def canonical(record):
    """Canonical bytes of a row without its hash: the HR-45 rule of paper-trading.md, reused unchanged."""

    def check(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                check(x, f"{path}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                check(x, f"{path}[{i}]")
        elif not isinstance(v, str) and not (isinstance(v, int) and not isinstance(v, bool) and path == ".seq"):
            raise PaperError(f"{path} must be a string (only seq is an integer)")

    body = {k: v for k, v in record.items() if k != "hash"}
    check(body, "")
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def row_hash(record):
    return hashlib.sha256(canonical(record)).hexdigest()


def make_row(seq, ts, kind, label, body, prev):
    rec = {"seq": seq, "ts": ts, "kind": kind, "label": label, "format": FORMAT, "body": body, "prev": prev}
    rec["hash"] = row_hash(rec)
    return rec


def line(rec):
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def read_text(path):
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def parse(text):
    """Rows of a ledger text. Raises ValueError on a line that is not one JSON object (HR-78: no repeated key)."""
    rows = []
    for n, ln in enumerate(text.splitlines()):
        rec = json.loads(ln, object_pairs_hook=_no_duplicates)
        if not isinstance(rec, dict):
            raise ValueError(f"line {n} is not an object")
        rows.append(rec)
    return rows


def bad(seq, reason, detail=""):
    return {"ok": False, "first_bad_seq": seq, "reason": reason, "detail": detail}


def check_chain(text, label):
    """Chain check only. Reasons PARSE, SEQ, HASH, LINK, LABEL, FORMAT, KIND. Never repairs."""
    prev = GENESIS
    rows = []
    for n, ln in enumerate(text.splitlines()):
        try:
            rec = json.loads(ln, object_pairs_hook=_no_duplicates)
            if not isinstance(rec, dict):
                return bad(n, "PARSE")
            stored = rec["hash"]
            computed = row_hash(rec)
        except (ValueError, KeyError, PaperError) as e:
            return bad(n, "PARSE", str(e))
        if rec.get("seq") != n:
            return bad(n, "SEQ")
        if computed != stored:
            return bad(n, "HASH")
        if rec.get("prev") != prev:
            return bad(n, "LINK")
        if rec.get("label") != label:
            return bad(n, "LABEL")
        if rec.get("format") != FORMAT:
            return bad(n, "FORMAT")
        if rec.get("kind") not in KINDS or (rec["kind"] == "GENESIS") != (n == 0):
            return bad(n, "KIND")
        prev = stored
        rows.append(rec)
    return {"ok": True, "rows": rows, "head": prev}


# ------------------------------------------------------------------ recorded par yields (forward log)


def par_state(entries, series, fields):
    """{date: ({field: decimal string}, hash of the last forward-log row that set one of them)} for dates with
    every field. Later rows replace earlier observations, as the recorder's own replay does."""
    obs, src = {}, {}
    for e in entries:
        r = e["record"]
        if r["series_id"] != series:
            continue
        for key, v in (r["value"]["payload"].get("observations") or {}).items():
            d, f = key.split("|")
            if f in fields:
                obs.setdefault(d, {})[f] = fstr(v)
                src[d] = e["hash"]
    return {d: (v, src[d]) for d, v in obs.items() if all(f in v for f in fields)}


# ------------------------------------------------------------------ dates


def iso(d):
    return d.isoformat()


def day(s):
    return dt.date.fromisoformat(s)


def add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 February
        return d.replace(year=d.year + n, day=28)


def instant(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def stamp(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def case(cid, op, inputs):
    return {"schema_version": "1.0", "case_id": cid, "operation": op, "inputs": inputs}


class Calendar:
    """Business days from `core.calendar.is_business_day` (the library calendar decides, KR-73)."""

    def __init__(self, runner, name):
        self.runner, self.name, self.known = runner, name, {}

    def load(self, start, end):
        need = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
        need = [d for d in need if d not in self.known]
        if need:
            out = self.runner([case(iso(d), "core.calendar.is_business_day", {"calendar": self.name, "date": iso(d)})
                               for d in need])
            for d in need:
                self.known[d] = bool(out[iso(d)]["is_business_day"])

    def is_open(self, d):
        self.load(d, d)
        return self.known[d]

    def next_open(self, d):
        self.load(d, d + dt.timedelta(days=10))
        n = d + dt.timedelta(days=1)
        while not self.known[n]:
            n += dt.timedelta(days=1)
        return n

    def open_between(self, after, upto):
        """Business days d with after < d <= upto."""
        if upto <= after:
            return []
        self.load(after, upto)
        return [d for d in (after + dt.timedelta(days=i) for i in range(1, (upto - after).days + 1)) if self.known[d]]

    def cutoff(self, d, cfg):
        """Last instant a row for business day d is on time (KR-82): the cutoff time on the next business day."""
        h, m, s = (int(x) for x in cfg["on_time_cutoff_utc"].split(":"))
        return dt.datetime.combine(self.next_open(d), dt.time(h, m, s), dt.timezone.utc)


# ------------------------------------------------------------------ holdout guard (plan 14.10 rule 6)


def holdout_windows():
    import sys
    sys.path.insert(0, str(ROOT / "research"))
    import holdout_scan
    return holdout_scan.windows()


def holdout_hit(date, windows):
    return sorted(k for k, (lo, hi) in windows.items() if lo <= date <= hi)


# ------------------------------------------------------------------ state carried between days


def new_state(cfg):
    return {"cash": Decimal(cfg["start_cash"]), "nav": Decimal(cfg["start_cash"]), "date": None, "par": None,
            "pos": {i["symbol"]: D0 for i in cfg["instruments"]}, "bonds": {}, "k": 0, "pnl": D0}


def advance(state, body):
    """State after a DAY row, read from the row."""
    return {"cash": Decimal(body["cash_close"]), "nav": Decimal(body["nav_close"]), "date": body["date"],
            "par": body["par_yields"], "pos": {s: Decimal(v) for s, v in body["positions_close"].items()},
            "bonds": {s: v["new"] for s, v in body["instruments"].items()},
            "k": state["k"] + (1 if body["timing"] == "on_time" else 0),
            "pnl": state["pnl"] + Decimal(body["pnl"])}


def seed_for(date, prev_hash, symbol):
    return hashlib.sha256(f"{FORMAT}|{date}|{prev_hash}|{symbol}".encode("ascii")).hexdigest()


def book_for(cfg, inst, seed, q_ref):
    """The synthetic book around par (KR-77): `book_levels` levels a tick apart from the assumed half spread,
    each showing 20% to 50% of the day's reference quantity, the percentage read from the seed bytes."""
    lot, tick, h = Decimal(cfg["lot_size"]), Decimal(cfg["tick_size"]), Decimal(inst["half_spread"])
    par = Decimal(cfg["par_price"])
    raw = bytes.fromhex(seed)
    n = cfg["book_levels"]

    def qty(b):
        pct = cfg["depth_percent_min"] + b % cfg["depth_percent_span"]
        return max(lot, (q_ref * pct / 100 / lot).to_integral_value(ROUND_FLOOR) * lot)

    asks = [[plain(par + h + i * tick), plain(qty(raw[i]))] for i in range(n)]
    bids = [[plain(par - h - i * tick), plain(qty(raw[n + i]))] for i in range(n)]
    return {"bids": bids, "asks": asks}


def lit_events(book, order):
    ev = []
    for name, side in (("asks", "SELL"), ("bids", "BUY")):
        for i, (p, q) in enumerate(book[name]):
            ev.append({"op": "NEW", "id": f"BOOK-{name}-{i}", "trader": "BOOK", "side": side, "type": "LIMIT",
                       "price": p, "qty": q})
    ev.append({"op": "NEW", "id": order["order_id"], "trader": "PAPER", "side": order["side"],
               "type": order["type"], "price": order["limit_price"], "qty": order["quantity"]})
    return ev


# ------------------------------------------------------------------ one day through the CLI


def build_day(cfg, runner, state, date, par, source, ts, timing, prev_hash, gaps, run):
    """The body of the DAY row for `date`. `state` is the state after the previous DAY row (or the start)."""
    places, par_px, freq = cfg["mark_decimals"], cfg["par_price"], cfg["coupon_frequency"]
    insts = cfg["instruments"]
    d = day(date)
    first = state["date"] is None
    days = 0 if first else (d - day(state["date"])).days
    if not first and days <= 0:
        raise PaperError(f"{date} is not after the previous ledger day {state['date']}")
    xs = [k["years"] for k in cfg["knots"]]
    out_i = {}

    # 1. yields of yesterday's par bonds on yesterday's and today's curve, at their shorter maturity
    taus = {}
    if not first:
        for i in insts:
            # curve time in years of 365.25 days, held inside the knots (flat beyond the ends, KR-76)
            t = (day(state["bonds"][i["symbol"]]["maturity"]) - d).days / 365.25
            taus[i["symbol"]] = min(max(t, xs[0]), xs[-1])
        at = [taus[i["symbol"]] for i in insts]
        r = runner([
            case("roll", "core.interp.evaluate", {"method": cfg["interp"], "x": xs, "at": at,
                                                  "y": [float(state["par"][k["field"]]) for k in cfg["knots"]]}),
            case("close", "core.interp.evaluate", {"method": cfg["interp"], "x": xs, "at": at,
                                                   "y": [float(par[k["field"]]) for k in cfg["knots"]]})])
        for n, i in enumerate(insts):
            out_i[i["symbol"]] = {"tau": fstr(taus[i["symbol"]]), "y_roll": rstr(r["roll"]["values"][n], places),
                                  "y_close": rstr(r["close"]["values"][n], places)}

    # 2. prices: the old bonds at both yields, the new par bonds for their duration
    cases = []
    new = {}
    for i in insts:
        s = i["symbol"]
        new[s] = {"coupon": par[i["field"]], "maturity": iso(add_years(d, i["years"]))}
        c = float(Decimal(new[s]["coupon"]) / 100)
        cases.append(case(f"new|{s}", "bond.price.from_yield", {
            "bond": {"maturity": new[s]["maturity"], "coupon": c, "frequency": freq}, "settlement": date, "yield": c}))
        if not first:
            old = state["bonds"][s]
            bond = {"maturity": old["maturity"], "coupon": float(Decimal(old["coupon"]) / 100), "frequency": freq}
            for leg in ("roll", "close"):
                cases.append(case(f"{leg}|{s}", "bond.price.from_yield", {
                    "bond": bond, "settlement": date, "yield": float(Decimal(out_i[s][f"y_{leg}"]) / 100)}))
    r = runner(cases)
    instruments = {}
    for i in insts:
        s = i["symbol"]
        new[s]["mod_duration"] = rstr(r[f"new|{s}"]["modified_duration"], places)
        row = {"position_open": plain(state["pos"][s]), "new": new[s]}
        if not first:
            accrued = rstr(r[f"close|{s}"]["accrued"], places)
            clean_roll, clean_close = rstr(r[f"roll|{s}"]["clean"], places), rstr(r[f"close|{s}"]["clean"], places)
            row.update(old=state["bonds"][s], accrued=accrued, clean_roll=clean_roll, clean_close=clean_close,
                       mark=plain(Decimal(clean_close) + Decimal(accrued)), **out_i[s])
        instruments[s] = row

    # 3. the order the fixed rule asks for (on-time days only, KR-75 and KR-82)
    order = None
    no_order = None
    q_ref = {s: _q_ref(cfg, new[s]["mod_duration"]) for s in new}
    if timing != "on_time":
        no_order = "late run: no order is sent on a day recorded after its cut-off"
    else:
        step = cfg["rule"][state["k"] % len(cfg["rule"])]
        inst = next(i for i in insts if i["symbol"] == step["symbol"])
        s = inst["symbol"]
        qty = q_ref[s] if step["side"] == "BUY" else state["pos"][s]
        if qty <= 0:
            no_order = f"rule step SELL {s}: no position to sell"
        else:
            sign = 1 if step["side"] == "BUY" else -1
            reach = Decimal(inst["half_spread"]) + (cfg["book_levels"] - 1) * Decimal(cfg["tick_size"])
            seed = seed_for(date, prev_hash, s)
            order = {"order_id": f"{date}-1", "symbol": s, "side": step["side"], "type": cfg["order_type"],
                     "quantity": plain(qty), "limit_price": plain(Decimal(par_px) + sign * reach),
                     "ref_price": par_px, "rule_step": str(state["k"] % len(cfg["rule"])), "seed": seed,
                     "book": book_for(cfg, inst, seed, q_ref[s]), "fill_source": cfg["fill_label"]}

    # 4. legs of the open positions, cash interest, pre-trade estimate
    cases = []
    if not first:
        rate = plain(Decimal(state["par"][cfg["cash_rate_field"]]) / 100)
        cases.append(case("cash", "paper.book.end_of_day", {
            "cash_open": plain(state["cash"]), "cash_rate": rate, "debit_rate": rate, "days": days}))
        for i in insts:
            s, x = i["symbol"], instruments[i["symbol"]]
            for leg, a, b in (("roll", par_px, x["clean_roll"]), ("curve", x["clean_roll"], x["clean_close"]),
                              ("carry", x["clean_close"], x["mark"])):
                cases.append(case(f"{leg}|{s}", "paper.book.end_of_day", {
                    "cash_open": "0", "position_open": x["position_open"], "prev_close": a, "close": b}))
    if order:
        inst = next(i for i in insts if i["symbol"] == order["symbol"])
        tp = cfg["tca_pretrade"]
        pre_in = {"quantity": float(order["quantity"]), "adv": float(tp["adv_multiple"] * q_ref[order["symbol"]]),
                  "daily_vol": inst["daily_vol"], "participation": tp["participation"],
                  "half_spread_bps": float(Decimal(inst["half_spread"]) / Decimal(par_px) * 10000),
                  "params": tp["params"], "price": float(par_px)}
        cases.append(case("tca_pre", "exec.tca.pretrade", pre_in))
    r = runner(cases) if cases else {}
    interest = Decimal(r["cash"]["cash_interest"]) if not first else D0
    legs = {leg: sum((Decimal(r[f"{leg}|{i['symbol']}"]["market"]) for i in insts), D0) if not first else D0
            for leg in ("roll", "curve", "carry")}
    for i in insts:
        if not first:
            instruments[i["symbol"]]["pnl"] = {leg: r[f"{leg}|{i['symbol']}"]["market"] for leg in ("carry", "roll", "curve")}
    cash_mid = state["cash"] + interest + legs["roll"] + legs["curve"] + legs["carry"]  # after the daily re-strike

    # 5. pre-trade limit check, then the simulator only if accepted
    fills = []
    if order:
        order["tca_pretrade"] = {**{k: fstr(v) for k, v in r["tca_pre"].items()}, "label": cfg["tca_pretrade_label"]}
        chk = runner([case("chk", "paper.pretrade.check", {
            "order": {k: order[k] for k in ("side", "type", "quantity", "limit_price")}, "ref_price": par_px,
            "position": plain(state["pos"][order["symbol"]]), "cash": plain(cash_mid), "orders_today": 0,
            "limits": cfg["limits"]})])["chk"]
        order["pretrade"] = {"accepted": "true" if chk["accepted"] else "false", "reasons": list(chk["reasons"])}
        if chk["accepted"]:
            sim = runner([case("lit", "exec.sim.lit.run", {
                "tick_size": cfg["tick_size"], "lot_size": cfg["lot_size"], "fee_schedule": cfg["fee_schedule"],
                "events": lit_events(order["book"], order)})])["lit"]
            if any(x["id"] == order["order_id"] for x in sim["rejects"]):
                raise PaperError(f"the venue simulator rejected {order['order_id']}: {sim['rejects']}")
            taker = Decimal(cfg["fee_schedule"]["taker_fee"])
            for f in sim["fills"]:
                if f["taker_id"] == order["order_id"]:
                    fills.append({"quantity": f["qty"], "price": f["price"],
                                  "fee": plain(taker * Decimal(f["qty"]) * Decimal(f["price"]))})
            status = "FILLED" if sum((Decimal(f["quantity"]) for f in fills), D0) == Decimal(order["quantity"]) \
                else ("PARTIALLY_FILLED" if fills else "CANCELED")
        else:
            status = "REJECTED"
        filled = sum((Decimal(f["quantity"]) for f in fills), D0)
        order.update(status=status, fills=fills, filled=plain(filled),
                     cancelled=plain(D0 if status == "REJECTED" else Decimal(order["quantity"]) - filled))

    # 6. post-trade TCA for the order, and the fill leg of every instrument at the new par price
    cases = []
    for i in insts:
        s = i["symbol"]
        fl = [{"side": order["side"], **f} for f in fills] if order and order["symbol"] == s else []
        cases.append(case(f"fill|{s}", "paper.book.end_of_day", {
            "cash_open": "0", "position_open": instruments[s]["position_open"], "prev_close": par_px,
            "close": par_px, "fills": fl}))
    if order:
        cases.append(case("tca", "exec.tca.attribution", {
            "side": order["side"], "decision_price": float(par_px), "arrival_mid": float(par_px),
            "end_price": float(par_px), "order_quantity": float(order["quantity"]),
            "fills": [{"quantity": float(f["quantity"]), "price": float(f["price"]), "mid": float(par_px)} for f in fills],
            "fees": float(sum((Decimal(f["fee"]) for f in fills), D0))}))
    r = runner(cases)
    if order:
        order["tca"] = {k: fstr(v) for k, v in r["tca"].items()}
    trading = sum((Decimal(r[f"fill|{i['symbol']}"]["trading"]) for i in insts), D0)
    fees = sum((Decimal(r[f"fill|{i['symbol']}"]["fees"]) for i in insts), D0)
    positions = {i["symbol"]: r[f"fill|{i['symbol']}"]["position"] for i in insts}
    cash_close = cash_mid + sum((Decimal(r[f"fill|{i['symbol']}"]["cash_close"]) for i in insts), D0)
    nav_close = cash_mid + sum((Decimal(r[f"fill|{i['symbol']}"]["nav_close"]) for i in insts), D0)
    pnl = nav_close - state["nav"]
    carry = legs["carry"] + interest
    total = carry + legs["roll"] + legs["curve"] + trading + fees
    unexplained = pnl - total
    if abs(unexplained) > Decimal(cfg["unexplained_threshold"]):
        raise PaperError(f"{date}: unexplained {unexplained} is over the threshold; nothing written")
    on_time = state["k"] + (1 if timing == "on_time" else 0)
    return {
        "date": date, "prev_date": state["date"] or "", "days": str(days), "timing": timing,
        "gaps_since_prev": list(gaps), "run": run, "source": source, "par_yields": dict(par),
        "instruments": instruments, "orders": [order] if order else [], "no_order": no_order or "",
        "cash_rate": "" if first else plain(Decimal(state["par"][cfg["cash_rate_field"]]) / 100),
        "cash_open": plain(state["cash"]), "cash_close": plain(cash_close), "positions_close": positions,
        "nav_open": plain(state["nav"]), "nav_close": plain(nav_close), "pnl": plain(pnl),
        "explain": {"carry": plain(carry), "coupon_accrual": plain(legs["carry"]), "cash_interest": plain(interest),
                    "roll_down": plain(legs["roll"]), "curve_move": plain(legs["curve"]),
                    "fills_costs": plain(trading + fees), "trading": plain(trading), "fees": plain(fees),
                    "unexplained": plain(unexplained), "total": plain(total)},
        "cumulative": {"recorded_trading_days": str(on_time), "pnl": plain(state["pnl"] + pnl)},
    }


def _q_ref(cfg, mod_duration):
    """Units (USD 100 face each) whose DV01 is the target: one unit at par moves duration / 100 USD a basis point."""
    lot = Decimal(cfg["lot_size"])
    return (Decimal(cfg["target_dv01_usd"]) * 100 / Decimal(mod_duration) / lot).to_integral_value(ROUND_FLOOR) * lot


# ------------------------------------------------------------------ independent replay from the rows alone (KR-84)


def replay_day(cfg, state, b):
    """Re-derives one DAY row in exact decimal from the row and the state before it. Returns (reason, detail)
    for the first disagreement, or None. No CLI, no data beyond the ledger."""
    par_px = Decimal(cfg["par_price"])

    def eq(name, got, want, reason):
        return None if Decimal(got) == want else (reason, f"{name}: row {got}, replay {plain(want)}")

    first = state["date"] is None
    days = 0 if first else (day(b["date"]) - day(state["date"])).days
    checks = [("prev_date", b["prev_date"] == (state["date"] or ""), "DATE"), ("days", b["days"] == str(days), "DATE")]
    for name, ok, reason in checks:
        if not ok:
            return reason, name
    for e in (eq("cash_open", b["cash_open"], state["cash"], "CASH"), eq("nav_open", b["nav_open"], state["nav"], "NAV")):
        if e:
            return e
    interest = D0
    if not first:
        rate = Decimal(state["par"][cfg["cash_rate_field"]]) / 100
        interest = (state["cash"] * rate * days / 365).quantize(CENT, ROUND_HALF_EVEN)
    carry = roll = curve = settle = D0
    pos = {}
    for i in cfg["instruments"]:
        s = i["symbol"]
        x = b["instruments"].get(s)
        if x is None:
            return "POSITION", f"{s} missing"
        n = state["pos"][s]
        if Decimal(x["position_open"]) != n:
            return "POSITION", f"{s} position_open: row {x['position_open']}, replay {plain(n)}"
        pos[s] = n
        if first:
            continue
        if x["old"] != state["bonds"][s]:
            return "POSITION", f"{s}: the bond marked is not the one struck on {state['date']}"
        a, cr, cc = Decimal(x["accrued"]), Decimal(x["clean_roll"]), Decimal(x["clean_close"])
        if Decimal(x["mark"]) != cc + a:
            return "EXPLAIN", f"{s} mark is not clean_close + accrued"
        carry += n * a
        roll += n * (cr - par_px)
        curve += n * (cc - cr)
        settle += n * (Decimal(x["mark"]) - par_px)
    trading = fees = flow = D0
    if len(b["orders"]) > int(cfg["limits"]["max_orders_per_day"]) or (b["timing"] != "on_time" and b["orders"]):
        return "ORDER", "an order on a late day, or more orders than the daily limit"
    for o in b["orders"]:
        sgn = {"BUY": 1, "SELL": -1}[o["side"]]
        q = Decimal(o["quantity"])
        got = sum((Decimal(f["quantity"]) for f in o["fills"]), D0)
        if o["pretrade"]["accepted"] != "true" and o["fills"]:
            return "ORDER", f"{o['order_id']}: a rejected order has fills"
        if got > q or Decimal(o["filled"]) != got:
            return "ORDER", f"{o['order_id']}: fills do not add to filled, or exceed the order"
        for f in o["fills"]:
            fq, fp, ff = Decimal(f["quantity"]), Decimal(f["price"]), Decimal(f["fee"])
            trading += sgn * fq * (par_px - fp)
            fees -= ff
            flow -= sgn * fq * fp + ff
            pos[o["symbol"]] += sgn * fq
    cash_close = state["cash"] + interest + settle + flow
    nav_close = cash_close + par_px * sum(pos.values(), D0)
    pnl = nav_close - state["nav"]
    total = carry + interest + roll + curve + trading + fees
    ex = b["explain"]
    for e in (
        eq("coupon_accrual", ex["coupon_accrual"], carry, "EXPLAIN"),
        eq("cash_interest", ex["cash_interest"], interest, "EXPLAIN"),
        eq("carry", ex["carry"], carry + interest, "EXPLAIN"),
        eq("roll_down", ex["roll_down"], roll, "EXPLAIN"),
        eq("curve_move", ex["curve_move"], curve, "EXPLAIN"),
        eq("trading", ex["trading"], trading, "EXPLAIN"),
        eq("fees", ex["fees"], fees, "EXPLAIN"),
        eq("fills_costs", ex["fills_costs"], trading + fees, "EXPLAIN"),
        eq("total", ex["total"], total, "EXPLAIN"),
        eq("unexplained", ex["unexplained"], pnl - total, "EXPLAIN"),
        eq("cash_close", b["cash_close"], cash_close, "CASH"),
        eq("nav_close", b["nav_close"], nav_close, "NAV"),
        eq("pnl", b["pnl"], pnl, "NAV"),
    ):
        if e:
            return e
    if abs(Decimal(ex["unexplained"])) > Decimal(cfg["unexplained_threshold"]):
        return "EXPLAIN", f"unexplained {ex['unexplained']} over the threshold {cfg['unexplained_threshold']}"
    stated = Decimal(ex["carry"]) + Decimal(ex["roll_down"]) + Decimal(ex["curve_move"]) + Decimal(ex["fills_costs"])
    if abs(Decimal(b["pnl"]) - stated) > Decimal(cfg["unexplained_threshold"]):
        return "EXPLAIN", "P&L is not the sum of carry, roll-down, curve move and fills and costs"
    for s, v in pos.items():
        if Decimal(b["positions_close"].get(s, "NaN")) != v:
            return "POSITION", f"{s} positions_close: row {b['positions_close'].get(s)}, replay {plain(v)}"
    # cash plus positions reconcile to the ledger (K-2): the row's own three numbers must agree as well
    if Decimal(b["cash_close"]) + par_px * sum((Decimal(v) for v in b["positions_close"].values()), D0) != Decimal(b["nav_close"]):
        return "NAV", "cash plus positions does not equal nav_close"
    return None


def same(a, b, path=""):
    """Deep comparison of a recorded body with a recomputed one: decimal strings within KR-86's tolerance,
    everything else exactly. Returns the first differing path, or None."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}"
            e = same(a[k], b[k], f"{path}.{k}")
            if e:
                return e
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return path
        for n, (x, y) in enumerate(zip(a, b)):
            e = same(x, y, f"{path}[{n}]")
            if e:
                return e
        return None
    if a == b:
        return None
    try:
        x, y = Decimal(a), Decimal(b)
    except Exception:
        return path
    return None if abs(x - y) <= DAY_FLOAT_TOL * max(Decimal(1), abs(x), abs(y)) else path


def verify(text, cfg=None, runner=None, windows=None, calendar=None):
    """Full check of a ledger text. Order: chain, genesis and configuration, dates (business days, no missing
    day, holdout windows, timing label), exact replay of every day, and, with a `runner`, a rebuild of every
    day through the CLI. Returns {ok, records, recorded_trading_days, late_days, gaps, head, pnl} or
    {ok: False, first_bad_seq, reason, detail}. Never repairs."""
    with localcontext() as ctx:
        ctx.prec = 80
        return _verify(text, cfg, runner, windows, calendar)


def _verify(text, cfg, runner, windows, calendar):
    label = (cfg or load_config())["label"]
    ch = check_chain(text, label)
    if not ch["ok"]:
        return ch
    rows = ch["rows"]
    if not rows:
        return {"ok": True, "records": 0, "recorded_trading_days": 0, "late_days": 0, "gaps": 0, "head": GENESIS,
                "pnl": "0", "last_date": None}
    g = rows[0]["body"]
    if hashlib.sha256(canonical({"c": g["config"]})).hexdigest() != g["config_sha256"]:
        return bad(0, "CONFIG", "config_sha256 does not match the configuration in the genesis row")
    if cfg is not None and strings(cfg) != g["config"]:
        return bad(0, "CONFIG", "the configuration file differs from the one fixed in the genesis row")
    lcfg = _typed(g["config"], cfg or load_config())
    windows = holdout_windows() if windows is None else windows
    cal = calendar or (Calendar(runner, lcfg["calendar"]) if runner else None)
    state = new_state(lcfg)
    last, last_ts, late, gaps = None, rows[0]["ts"], 0, 0
    pending = []
    for rec in rows[1:]:
        n, b = rec["seq"], rec["body"]
        try:
            date = b["date"]
            d = day(date)
            if rec["ts"] < last_ts:
                return bad(n, "DATE", "ts goes backwards")
            if last is not None and d <= last:
                return bad(n, "DATE", f"{date} is not after {iso(last)}")
            if instant(rec["ts"]).date() < d:
                return bad(n, "DATE", f"row for {date} written before that day")
            hit = holdout_hit(date, windows)
            if hit:
                return bad(n, "HOLDOUT", f"{date} is inside the holdout window of {', '.join(hit)}")
            if cal is not None:
                if not cal.is_open(d):
                    return bad(n, "DATE", f"{date} is not a {lcfg['calendar']} business day")
                if last is not None and cal.open_between(last, d)[:-1]:
                    miss = ", ".join(iso(x) for x in cal.open_between(last, d)[:-1])
                    return bad(n, "MISSING_DAY", f"no row for business day(s) {miss}")
                on_time = instant(rec["ts"]) < cal.cutoff(d, lcfg)
            last, last_ts = d, rec["ts"]
            if rec["kind"] == "GAP":
                gaps += 1
                pending.append(date)
                if cal is not None and on_time:
                    return bad(n, "TIMING", f"gap for {date} declared before its cut-off")
                continue
            if b["gaps_since_prev"] != pending:
                return bad(n, "MISSING_DAY", "gaps_since_prev does not list the GAP rows before this day")
            pending = []
            if b["timing"] not in ("on_time", "late") or (cal is not None and (b["timing"] == "on_time") != on_time):
                return bad(n, "TIMING", f"timing {b['timing']!r} does not match ts {rec['ts']}")
            e = replay_day(lcfg, state, b)
            if e:
                return bad(n, e[0], e[1])
            if runner is not None:
                again = build_day(lcfg, runner, state, date, b["par_yields"], b["source"], rec["ts"], b["timing"],
                                  rec["prev"], b["gaps_since_prev"], b["run"])
                diff = same(b, again)
                if diff:
                    return bad(n, "RECOMPUTE", f"{diff} differs from a rebuild through the CLI")
            if int(b["cumulative"]["recorded_trading_days"]) != state["k"] + (1 if b["timing"] == "on_time" else 0):
                return bad(n, "COUNT", "recorded_trading_days")
            late += b["timing"] == "late"
            state = advance(state, b)
            if Decimal(b["cumulative"]["pnl"]) != state["pnl"]:
                return bad(n, "NAV", "cumulative pnl")
        except (KeyError, ValueError, TypeError, ArithmeticError, PaperError) as e:
            return bad(n, "SCHEMA", f"{type(e).__name__}: {e}")
    return {"ok": True, "records": len(rows), "recorded_trading_days": state["k"], "late_days": late, "gaps": gaps,
            "head": ch["head"], "pnl": plain(state["pnl"]), "nav": plain(state["nav"]),
            "last_date": iso(last) if last else None, "calendar_checked": cal is not None,
            "recomputed": runner is not None}


def _typed(stringed, template):
    """The genesis configuration back in the types of config.json (the template gives the types only)."""
    if isinstance(template, dict):
        return {k: _typed(v, template[k]) if k in template else v for k, v in stringed.items()}
    if isinstance(template, list):
        return [_typed(v, template[min(n, len(template) - 1)]) if template else v for n, v in enumerate(stringed)]
    if isinstance(template, bool):
        return stringed == "true"
    if isinstance(template, int):
        return int(stringed)
    if isinstance(template, float):
        return float(stringed)
    return stringed


# ------------------------------------------------------------------ a run: every day that is due


def genesis_body(cfg):
    c = strings(cfg)
    return {"config": c, "config_sha256": hashlib.sha256(canonical({"c": c})).hexdigest(), "spec": cfg["spec"],
            "statement": cfg["statement"], "ceiling": cfg["ceiling"], "start_cash": cfg["start_cash"]}


def run(cfg, runner, ledger_text, log_entries, now, commit="unknown", impl="python", windows=None):
    """Appends every row that is due at `now` (KR-82, KR-83). Returns (new ledger text, new rows, notes).
    Refuses (PaperError) if the existing ledger does not verify or a date falls in a holdout window."""
    with localcontext() as ctx:
        ctx.prec = 80
        return _run(cfg, runner, ledger_text, log_entries, now, commit, impl, windows)


def _run(cfg, runner, ledger_text, log_entries, now, commit, impl, windows):
    windows = holdout_windows() if windows is None else windows
    cal = Calendar(runner, cfg["calendar"])
    v = _verify(ledger_text, cfg, None, windows, cal)
    if not v["ok"]:
        raise PaperError(f"existing ledger does not verify: seq {v['first_bad_seq']} {v['reason']} {v['detail']}")
    rows = check_chain(ledger_text, cfg["label"])["rows"]
    fields = [k["field"] for k in cfg["knots"]]
    par = par_state(log_entries, cfg["source_series"], fields)
    today = now.date()
    state = new_state(cfg)
    pending = []
    for rec in rows[1:]:
        if rec["kind"] == "DAY":
            state, pending = advance(state, rec["body"]), []
        else:
            pending.append(rec["body"]["date"])
    last = day(rows[-1]["body"]["date"]) if len(rows) > 1 else None
    ts, notes, new = stamp(now), [], []
    head = rows[-1]["hash"] if rows else GENESIS
    seq = len(rows)

    def add(kind, body):
        nonlocal head, seq
        rec = make_row(seq, ts, kind, cfg["label"], body, head)
        new.append(rec)
        head, seq = rec["hash"], seq + 1
        return rec

    if last is None:
        # the ledger starts on the latest business day whose curve is recorded and still on time: no back-fill
        cands = [d for d in cal.open_between(today - dt.timedelta(days=10), today)
                 if iso(d) in par and now < cal.cutoff(d, cfg)]
        if not cands:
            return ledger_text, [], ["no business day with a recorded curve is on time yet; nothing written"]
        due = [cands[-1]]
        if not rows:
            add("GENESIS", genesis_body(cfg))
    else:
        due = cal.open_between(last, today)
    for d in due:
        date = iso(d)
        hit = holdout_hit(date, windows)
        if hit:
            raise PaperError(f"{date} is inside the holdout window of {', '.join(hit)}; nothing written")
        late = now >= cal.cutoff(d, cfg)
        if date not in par:
            if not late:
                notes.append(f"{date}: curve not recorded yet and the cut-off has not passed; stopping")
                break
            add("GAP", {"date": date, "reason": "no complete recorded par curve for this business day by its cut-off",
                        "run": {"commit": commit, "impl": impl}})
            pending.append(date)
            notes.append(f"{date}: GAP")
            continue
        yields, src = par[date]
        body = build_day(cfg, runner, state, date, yields, {"series": cfg["source_series"], "row_hash": src},
                         ts, "late" if late else "on_time", head, pending, {"commit": commit, "impl": impl})
        e = replay_day(cfg, state, body)
        if e:
            raise PaperError(f"{date}: the row built does not replay ({e[0]}: {e[1]}); nothing written")
        add("DAY", body)
        state, pending = advance(state, body), []
        notes.append(f"{date}: DAY {body['timing']} pnl {body['pnl']} nav {body['nav_close']} "
                     f"orders {len(body['orders'])} recorded_trading_days {body['cumulative']['recorded_trading_days']}")
    return ledger_text + "".join(line(r) + "\n" for r in new), new, notes


# ------------------------------------------------------------------ anchors (KR-81; as tools/forward-log/anchor.py)


def anchor_make(text, cfg, out_dir, when):
    ch = check_chain(text, cfg["label"])
    if not ch["ok"] or not ch["rows"]:
        raise PaperError("ledger is empty or its chain is broken; nothing to anchor")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{when}.json"
    rec = {"count": len(ch["rows"]), "head": ch["head"], "time": when, "format": FORMAT,
           "config_sha256": ch["rows"][0]["body"]["config_sha256"]}
    p.write_text(json.dumps(rec, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return p


def anchor_check(text, cfg, anchors_dir):
    """Chain check, then every anchor: line `count` must still have hash `head`. Returns the number checked."""
    ch = check_chain(text, cfg["label"])
    if not ch["ok"]:
        raise PaperError(f"chain: seq {ch['first_bad_seq']} {ch['reason']}")
    hashes = [r["hash"] for r in ch["rows"]]
    files = sorted(Path(anchors_dir).glob("*.json"))
    for f in files:
        a = json.loads(f.read_text(encoding="utf-8"))
        if a["count"] > len(hashes):
            raise PaperError(f"{f.name}: anchor covers {a['count']} rows but the ledger has {len(hashes)}; rows were removed")
        if hashes[a["count"] - 1] != a["head"]:
            raise PaperError(f"{f.name}: row {a['count']} hash differs from the anchor; the ledger was rewritten")
    return len(files)


# ------------------------------------------------------------------ runners


def cli_runner(impl="python"):
    """Cases through one `quantforge --batch` process (tools/workflows/common.py). Raises on an error result."""
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "workflows"))
    import common

    def go(cases):
        return outputs(common.batch(cases, impl).values())

    return go


def outputs(results):
    out = {}
    for r in results:
        if r.get("status") != "ok":
            raise PaperError(f"CLI case {r.get('case_id')} failed: {json.dumps(r.get('error'))}")
        out[r["case_id"]] = r["outputs"]
    return out
