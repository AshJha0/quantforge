"""Book lifecycle and marks: independent implementation from the spec page (no primary source exists).
Exact rational arithmetic (fractions) on the decimal text of each JSON number."""
from fractions import Fraction
import datetime as dt

def F(x): return Fraction(repr(x)) if isinstance(x, float) else Fraction(x)
def f(x): return float(x)

def sgn(x): return (x > 0) - (x < 0)

def lifecycle(inp):
    pos = {}
    for p in inp['positions']:
        q = F(p['quantity'])
        if p['instrument'] in pos: return {"error": "E_INPUT"}
        if q != 0: pos[p['instrument']] = [q, F(p['average_cost'])]
    realized = {}
    closed = set()
    fixings = {}
    last = None

    def trade(inst, dq, price):
        if inst in closed: raise ValueError('E_INPUT closed')
        price = F(price)
        q, a = pos.get(inst, [Fraction(0), Fraction(0)])
        if q == 0 or sgn(q) == sgn(dq):
            nq = q + dq
            na = (q * a + dq * price) / nq
            pos[inst] = [nq, na]
        else:
            c = min(abs(dq), abs(q))
            realized[inst] = realized.get(inst, Fraction(0)) + sgn(q) * c * (price - a)
            nq = q + dq
            if nq == 0: pos.pop(inst, None)
            elif sgn(nq) == sgn(q): pos[inst] = [nq, a]
            else: pos[inst] = [nq, price]

    try:
        for e in inp['events']:
            d = e['date']
            if last is not None and d < last: return {"error": "E_INPUT"}
            last = d
            t = e['type']
            if t == 'TRADE':
                dq = F(e['quantity'])
                if dq == 0: return {"error": "E_DOMAIN"}
                trade(e['instrument'], dq, e['price'])
            elif t == 'FIXING':
                k = (e['index'], d)
                if k in fixings: return {"error": "E_INPUT"}
                fixings[k] = e['value']
            elif t in ('EXPIRY', 'DEFAULT'):
                i = e['instrument']
                if i not in pos: return {"error": "E_INPUT"}
                trade(i, -pos[i][0], e['settlement_price'] if t == 'EXPIRY' else e['recovery_price'])
                closed.add(i)
            elif t == 'ROLL':
                i, j = e['from'], e['to']
                if i not in pos: return {"error": "E_INPUT"}
                q = pos[i][0]
                trade(i, -q, e['from_price'])
                closed.add(i)
                trade(j, q, e['to_price'])
            else:
                return {"error": "E_SCHEMA"}
    except ValueError:
        return {"error": "E_INPUT"}
    positions = [dict(instrument=i, quantity=f(v[0]), average_cost=f(v[1])) for i, v in sorted(pos.items())]
    rp = [dict(instrument=i, pnl=f(v)) for i, v in sorted(realized.items())]
    tot = sum(realized.values(), Fraction(0))
    fx = [dict(index=k[0], date=k[1], value=v) for k, v in sorted(fixings.items())]
    return dict(positions=positions, realized_pnl=rp, total_realized=f(tot), fixings=fx)

def marks(inp):
    asof = dt.date.fromisoformat(inp['as_of'])
    maxage = inp['max_age_days']
    thr = F(inp['ipv_threshold']) if inp.get('ipv_threshold') is not None else None
    ipv = {r['instrument']: F(r['price']) for r in inp.get('ipv') or []}
    srcs = inp['sources']
    rows = []
    for inst in inp['instruments']:
        row = None
        for si, s in enumerate(srcs):
            qs = [q for q in s['quotes'] if q['instrument'] == inst and dt.date.fromisoformat(q['date']) == asof]
            if qs:
                row = (qs[0]['price'], s['name'], 'PRIMARY' if si == 0 else 'FALLBACK', 0); break
        if row is None:
            best = None
            for si, s in enumerate(srcs):
                for q in s['quotes']:
                    if q['instrument'] != inst: continue
                    qd = dt.date.fromisoformat(q['date'])
                    age = (asof - qd).days
                    if age < 0 or age > maxage: continue
                    if best is None or qd > best[0]:   # strictly later date wins; earlier source wins ties
                        best = (qd, si, q['price'], s['name'], age)
            if best: row = (best[2], best[3], 'STALE', best[4])
        if row is None:
            rows.append(dict(instrument=inst, price=None, source=None, status='MISSING', age_days=None, ipv_diff=None, ipv_breach=False))
            continue
        price, sname, status, age = row
        diff = None; breach = False
        if inst in ipv:
            diff = (F(price) - ipv[inst]) / ipv[inst]
            breach = abs(diff) > thr
        rows.append(dict(instrument=inst, price=price, source=sname, status=status, age_days=age,
                         ipv_diff=None if diff is None else f(diff), ipv_breach=bool(breach)))
    return dict(marks=rows)
