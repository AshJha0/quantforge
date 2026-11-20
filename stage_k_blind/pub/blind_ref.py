import json, math
from fractions import Fraction

PK = 'C:/Work/Claude/qf-blind/pub_packet/'
OUT = 'C:/Work/Claude/qf-blind/pub_blind/'
PAR = json.load(open(PK + 'tables/sa-ccr-parameters.json'))
BT = json.load(open(PK + 'tables/frtb-ima-backtest-tables.blind.json'))
T2 = {(r['asset_class'], r['subclass']): r for r in PAR['table2']}


def Phi(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# ---------- binomial (exact rational) ----------
def cdf_frac(n, k, p):
    q = 1 - p
    tot = Fraction(0)
    for j in range(0, k + 1):
        tot += math.comb(n, j) * p**j * q**(n - j)
    return tot


def zone_bounds(n, p, a=Fraction(95, 100), r=Fraction(9999, 10000)):
    q = 1 - p
    tot = Fraction(0)
    amber = red = None
    for j in range(0, n + 1):
        tot += math.comb(n, j) * p**j * q**(n - j)
        if amber is None and tot >= a:
            amber = j
        if red is None and tot >= r:
            red = j
        if amber is not None and red is not None:
            break
    return amber, red


MULT = BT['multiplier_250']


def frtb_zone(inp):
    n = inp['observations']
    x = max(inp['exceptions_actual'], inp['exceptions_hypothetical'])
    p = Fraction(1, 100)
    amber, red = zone_bounds(n, p)
    cp = cdf_frac(n, x, p)
    z = 'RED' if x >= red else ('AMBER' if x >= amber else 'GREEN')
    if n == 250:
        m = MULT[x] if x <= 9 else BT['multiplier_red']
    else:
        m = None
    return {'exceptions': x, 'cumulative_probability': float(cp), 'zone': z,
            'amber_from': amber, 'red_from': red, 'multiplier': m}


PLUS = [0, 0, 0, 0, 0, 0.40, 0.50, 0.65, 0.75, 0.85]


def traffic(inp):
    n = inp['observations']
    x = inp['exceptions']
    c = inp['confidence']
    cf = Fraction(repr(c))
    p = 1 - cf
    cp = cdf_frac(n, x, p)
    z = 'GREEN' if cp < Fraction(95, 100) else ('YELLOW' if cp < Fraction(9999, 10000) else 'RED')
    if n == 250 and cf == Fraction(99, 100):
        pf = float(PLUS[x]) if x <= 9 else 1.0
    else:
        pf = None
    return {'cumulative_probability': float(cp), 'zone': z, 'plus_factor': pf}


# ---------- SA-CCR ----------
CLASSES = ['IR', 'FX', 'CREDIT', 'EQUITY', 'COMMODITY']
TREAT = ['NORMAL', 'BASIS', 'VOLATILITY']


def single_factor(items):
    s1 = sum(rho * a for a, rho in items)
    s2 = sum((1 - rho * rho) * a * a for a, rho in items)
    return math.sqrt(s1 * s1 + s2)


def saccr_core(inp, margined_mode, mpor):
    trades = inp['trades']
    rows = []
    for t in trades:
        ac = t['asset_class']
        kind = t.get('kind', 'LINEAR')
        tr = t.get('treatment', 'NORMAL')
        row = T2[(ac, t.get('subclass'))]
        if ac in ('IR', 'CREDIT'):
            sd = max((math.exp(-0.05 * t['start']) - math.exp(-0.05 * t['end'])) / 0.05, 10 / 250)
            d = t['notional'] * sd
        else:
            sd = None
            d = t['notional']
        if margined_mode:
            mf = 1.5 * math.sqrt(mpor / 250)
        else:
            mf = math.sqrt(min(max(t['maturity'], 10 / 250), 1.0))
        pos = t['position']
        if kind == 'LINEAR':
            delta = 1.0 if pos == 'LONG' else -1.0
        elif kind == 'OPTION':
            sig = row['option_volatility']
            T = t['exercise']
            lam = t.get('shift', 0)
            d1 = (math.log((t['underlying_price'] + lam) / (t['strike'] + lam)) + sig * sig * T / 2) / (sig * math.sqrt(T))
            if t['option_type'] == 'CALL':
                delta = Phi(d1) if pos == 'BOUGHT' else -Phi(d1)
            else:
                delta = -Phi(-d1) if pos == 'BOUGHT' else Phi(-d1)
        else:
            A = t['attachment']
            D = t['detachment']
            m = 15 / ((1 + 14 * A) * (1 + 14 * D))
            delta = m if pos == 'BOUGHT' else -m
        eff = d * mf * delta
        sf = row['supervisory_factor'] * PAR['treatment_scale'][tr]
        rows.append(dict(t=t, ac=ac, tr=tr, row=row, sd=sd, d=d, mf=mf, delta=delta, eff=eff, sf=sf))
    hs = {}
    for r in rows:
        ac = r['ac']
        tr = r['tr']
        if tr != 'NORMAL' or ac in ('IR', 'FX'):
            key = r['t']['hedging_set']
        elif ac in ('CREDIT', 'EQUITY'):
            key = ''
        else:
            key = r['row']['hedging_set']
        hs.setdefault((CLASSES.index(ac), TREAT.index(tr), key), []).append(r)
    hsl = []
    addon = {c: 0.0 for c in CLASSES}
    for k in sorted(hs):
        rs = hs[k]
        ac = CLASSES[k[0]]
        if ac == 'IR':
            b = [0.0, 0.0, 0.0]
            for r in rs:
                E = r['t']['end']
                i = 0 if E < 1 else (1 if E <= 5 else 2)
                b[i] += r['eff']
            if inp.get('ir_offset', True):
                en = math.sqrt(b[0]**2 + b[1]**2 + b[2]**2 + 1.4 * b[0] * b[1] + 1.4 * b[1] * b[2] + 0.6 * b[0] * b[2])
            else:
                en = abs(b[0]) + abs(b[1]) + abs(b[2])
            a = rs[0]['sf'] * en
        elif ac == 'FX':
            a = rs[0]['sf'] * abs(sum(r['eff'] for r in rs))
        else:
            ents = {}
            for r in rs:
                ents.setdefault(r['t']['entity'], []).append(r)
            items = []
            for e, er in ents.items():
                rho = 0.4 if ac == 'COMMODITY' else er[0]['row']['correlation']
                items.append((er[0]['sf'] * sum(r['eff'] for r in er), rho))
            a = single_factor(items)
        addon[ac] += a
        hsl.append({'asset_class': ac, 'treatment': TREAT[k[1]], 'key': k[2], 'addon': a})
    agg = sum(addon[c] for c in CLASSES)
    V = sum(t['market_value'] for t in trades)
    C = inp.get('collateral', 0)
    if V - C >= 0:
        m = 1.0
    elif agg == 0:
        m = 0.05
    else:
        m = min(1.0, 0.05 + 0.95 * math.exp((V - C) / (2 * 0.95 * agg)))
    pfe = m * agg
    if margined_mode:
        mg = inp['margin']
        rc = max(V - C, mg['threshold'] + mg['mta'] - mg['nica'], 0.0)
    else:
        rc = max(V - C, 0.0)
    ead = 1.4 * (rc + pfe)
    return dict(ead=ead, rc=rc, pfe=pfe, multiplier=m, addon_aggregate=agg, addon=addon, v=V, c=C,
                hedging_sets=hsl,
                trades=[{'id': r['t']['id'], 'supervisory_duration': r['sd'], 'adjusted_notional': r['d'],
                         'maturity_factor': r['mf'], 'delta': r['delta'], 'effective_notional': r['eff'],
                         'supervisory_factor': r['sf']} for r in rows])


def mpor_of(inp):
    mg = inp['margin']
    fl = 10 if mg['remargin_days'] == 1 else 9 + mg['remargin_days']
    if len(inp['trades']) > 5000 or mg.get('illiquid', False):
        fl = max(fl, 20)
    if mg.get('disputes', False):
        fl *= 2
    return max(fl, mg.get('mpor_days') or 0)


def saccr(inp):
    um = saccr_core(inp, False, None)
    if 'margin' not in inp:
        um.update(margined=False, mpor_days=None, ead_unmargined=None, capped=False)
        return um
    mp = mpor_of(inp)
    mr = saccr_core(inp, True, mp)
    eu = um['ead']
    capped = eu < mr['ead']
    mr['ead'] = min(mr['ead'], eu)
    mr.update(margined=True, mpor_days=mp, ead_unmargined=eu, capped=capped)
    return mr


ORDER = ['ead', 'rc', 'pfe', 'multiplier', 'addon_aggregate', 'addon', 'v', 'c', 'margined', 'mpor_days',
         'ead_unmargined', 'capped', 'hedging_sets', 'trades']


def main():
    cases = json.load(open(PK + 'inputs/pub.inputs.json'))['cases']
    res = {}
    for c in cases:
        op = c['operation']
        if op == 'risk.saccr.ead':
            r = saccr(c['inputs'])
            r = {k: r[k] for k in ORDER}
        elif op == 'risk.frtb.backtest.zone':
            r = frtb_zone(c['inputs'])
        else:
            r = traffic(c['inputs'])
        res[c['case_id']] = r
    tmpl = json.load(open(PK + 'output_template.json'))['results_skeleton']
    assert set(tmpl['cases']) == set(res)
    for k in tmpl['cases']:
        assert list(tmpl['cases'][k]) == list(res[k]), k
    open(OUT + 'blind_results.json', 'w').write(json.dumps({'cases': res}, indent=1))


if __name__ == '__main__':
    main()
