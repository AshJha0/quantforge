import json
from fractions import Fraction as F
from decimal import Decimal

def D(x):
    return F(Decimal(x if isinstance(x, str) else repr(x)))

def ERR(c):
    return {"status": "error", "error_code": c}

def run(mids, fills, orders, horizons):
    mids = [(D(t), D(m)) for t, m in mids]
    fills = [(v, s, D(q), D(p), D(t)) for v, s, q, p, t in fills]
    orders = [(v, D(a), D(b)) for v, a, b in orders]
    hs = [D(h) for h in horizons]
    # structural E_INPUT
    if any(f > s for _, s, f in orders):
        return ERR("E_INPUT")
    if any(mids[i][0] >= mids[i + 1][0] for i in range(len(mids) - 1)):
        return ERR("E_INPUT")
    # E_DOMAIN
    if any(m <= 0 for _, m in mids) or any(q <= 0 or p <= 0 for _, _, q, p, _ in fills) \
       or any(s <= 0 or f < 0 for _, s, f in orders) or any(h < 0 for h in hs):
        return ERR("E_DOMAIN")
    def mid(u):
        r = None
        for t, m in mids:
            if t <= u:
                r = m
        return r
    venues = sorted({f[0] for f in fills})
    rows = []
    for V in venues:
        for h, hraw in zip(hs, horizons):
            N = Q = P = T = F(0)
            for v, s, q, p, t in fills:
                if v != V: continue
                m = mid(t + h)
                if m is None:
                    return ERR("E_INPUT")
                sg = 1 if s == "BUY" else -1
                x = sg * (m - p)
                N += q * x; Q += q; P += q * p
                if x < 0: T += q
            rows.append({"venue": V, "h": float(h), "markout": float(N / Q),
                         "markout_bps": float(10000 * N / P), "toxicity": float(T / Q)})
    fr = {}
    for V in sorted({o[0] for o in orders}):
        S = sum(a for v, a, b in orders if v == V); Fl = sum(b for v, a, b in orders if v == V)
        fr[V] = float(Fl / S)
    return {"fill_rates": fr, "markouts": rows}

mids = [(0, "100.00"), (1, "100.02"), (5, "100.05"), (10, "99.98")]
fills = [("A", "BUY", "100", "100.01", "0"), ("A", "SELL", "200", "100.03", "1"), ("B", "BUY", "300", "100.00", "1")]
orders = [("A", "500", "300"), ("B", "300", "300")]
ordA = [("A", "500", "600"), ("B", "300", "300")]
R = {}
R["venue_h-0001"] = run(mids, fills, orders, ["5"])
R["venue_h-0002"] = run(mids, fills, orders, ["10"])
R["venue_h-0003"] = run(mids, fills, orders, ["0"])
R["venue_h-0004"] = run(mids, fills, orders, [])
R["venue_h-0005"] = run(mids, fills, ordA, [])
R["venue_h-0006"] = run(mids, fills + [("B", "BUY", "10", "100", "-1")], orders, ["0"])
R["venue_h-0007"] = run(mids, fills, orders, ["-1"])
R["venue_h-0008"] = run(mids, fills, ordA, ["-1"])
R["venue_h-0010"] = run([(0, "100")], [("A", "BUY", "1e20", "99.99", "0"), ("A", "BUY", "1e-20", "99", "0"), ("A", "SELL", "1e20", "99.99", "0")], [("A", "3", "1")], ["0"])
json.dump(R, open("blind_results.json", "w"), indent=1, sort_keys=True)
