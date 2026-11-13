"""FRTB SA SBM (MAR21), written from the Basel Framework PDF text and formula images (pages cited in SOURCES.md).
No parameter here was taken from the specs pages."""
import math

SCEN = ("high", "medium", "low")

def scale(x, sc):  # MAR21.6
    if sc == "high": return min(1.25 * x, 1.0)
    if sc == "low": return max(2 * x - 1.0, 0.75 * x)
    return x

def bkey(b):
    s = str(b); return (len(s), s)

def ten(s):
    assert s.endswith('Y'); return float(s[:-1])

# ---------------- generic delta / vega aggregation (MAR21.4) ----------------
def aggregate(buckets, rho, gamma, sumabs, sc):
    K = {}; S = {}
    for b, fl in buckets.items():
        S[b] = sum(w for _, w in fl)
        if sumabs(b):
            K[b] = sum(abs(w) for _, w in fl)
        else:
            tot = sum(w * w for _, w in fl)
            for i, (ki, wi) in enumerate(fl):
                for j, (kj, wj) in enumerate(fl):
                    if i != j:
                        tot += scale(rho(b, ki, kj), sc) * wi * wj
            K[b] = math.sqrt(max(0.0, tot))
    bl = sorted(buckets, key=bkey)
    def total(Sd):
        t = sum(K[b] ** 2 for b in bl)
        for b in bl:
            for c in bl:
                if b != c: t += scale(gamma(b, c), sc) * Sd[b] * Sd[c]
        return t
    t = total(S); alt = False; Su = dict(S)
    if t < 0:
        alt = True
        Su = {b: max(min(S[b], K[b]), -K[b]) for b in bl}
        t = total(Su)
    return dict(buckets=[dict(bucket=b, k=K[b], s=S[b], s_used=Su[b]) for b in bl],
                value=math.sqrt(max(0.0, t)), alternative_used=alt)

def finish(valname, per):
    out = {}
    for sc in SCEN:
        r = per[sc]
        out[sc] = dict(buckets=r['buckets'], **{valname: r['value']}, alternative_used=r['alternative_used'])
    vals = [per[s]['value'] for s in SCEN]
    m = max(vals)
    return dict(scenarios=out, capital=m, binding_scenario=SCEN[vals.index(m)])

# ---------------- GIRR delta (MAR21.41-21.50) ----------------
GIRR_TENORS = [0.25, 0.5, 1, 2, 3, 5, 10, 15, 20, 30]
GIRR_RW = {0.25: .017, 0.5: .017, 1: .016, 2: .013, 3: .012, 5: .011, 10: .011, 15: .011, 20: .011, 30: .011}  # Table 1
SPEC_CCY = {"EUR", "USD", "GBP", "AUD", "JPY", "SEK", "CAD"}  # footnote 283
TABLE2 = """100.0 97.0 91.4 81.1 71.9 56.6 40.0 40.0 40.0 40.0
97.0 100.0 97.0 91.4 86.1 76.3 56.6 41.9 40.0 40.0
91.4 97.0 100.0 97.0 94.2 88.7 76.3 65.7 56.6 41.9
81.1 91.4 97.0 100.0 98.5 95.6 88.7 82.3 76.3 65.7
71.9 86.1 94.2 98.5 100.0 98.0 93.2 88.7 84.4 76.3
56.6 76.3 88.7 95.6 98.0 100.0 97.0 94.2 91.4 86.1
40.0 56.6 76.3 88.7 93.2 97.0 100.0 98.5 97.0 94.2
40.0 41.9 65.7 82.3 88.7 94.2 98.5 100.0 99.0 97.0
40.0 40.0 56.6 76.3 84.4 91.4 97.0 99.0 100.0 98.5
40.0 40.0 41.9 65.7 76.3 86.1 94.2 97.0 98.5 100.0"""
T2 = [[float(x) / 100 for x in l.split()] for l in TABLE2.split('\n')]

def girr_tenor_rho(t1, t2):  # MAR21.46 fn 284 (theta = 3%), verified against Table 2 below
    return max(math.exp(-0.03 * abs(t1 - t2) / min(t1, t2)), 0.40)

def check_table2():
    for i, a in enumerate(GIRR_TENORS):
        for j, b in enumerate(GIRR_TENORS):
            assert abs(girr_tenor_rho(a, b) - T2[i][j]) < 5.1e-4, (a, b)

def girr_delta(inp):
    red = bool(inp.get('specified_currency_reduction', False))
    rc = inp.get('reporting_currency')
    spec = set(SPEC_CCY) | ({rc} if rc else set())
    buckets = {}
    for s in inp['sensitivities']:
        rf = s['risk_factor']; ccy = s['currency']
        if rf in ('INFLATION', 'XCCY_BASIS'):
            rw = 0.016; kind = rf; t = None
        else:
            t = ten(rf); rw = GIRR_RW[t]; kind = 'T'
        if red and ccy in spec: rw /= math.sqrt(2)   # 21.44 (applied to all GIRR weights of that currency)
        buckets.setdefault(ccy, []).append(((s['curve'], kind, t), rw * s['sensitivity']))
    def rho(b, k1, k2):
        (c1, kd1, t1), (c2, kd2, t2) = k1, k2
        if kd1 == 'XCCY_BASIS' or kd2 == 'XCCY_BASIS': return 0.0   # 21.49
        if kd1 == 'INFLATION' and kd2 == 'INFLATION': return 0.999   # 21.47 FAQ1
        if kd1 == 'INFLATION' or kd2 == 'INFLATION': return 0.40     # 21.48
        base = girr_tenor_rho(t1, t2) if t1 != t2 else 1.0
        return base if c1 == c2 else base * 0.999                    # 21.45, 21.47
    per = {sc: aggregate(buckets, rho, lambda b, c: 0.5, lambda b: False, sc) for sc in SCEN}  # 21.50
    out = finish('delta', per)
    for sc in SCEN:
        for bb in out['scenarios'][sc]['buckets']: bb['currency'] = bb['bucket']
    return out

# ---------------- FX delta (MAR21.86-21.89) ----------------
BASEL_PAIRS_NON_USD = {"EUR","JPY","GBP","AUD","CAD","CHF","MXN","CNY","NZD","RUB","HKD","SGD","TRY","KRW","SEK","ZAR","INR","NOK","BRL"}  # fn 293
def fx_eligible(pair):
    a, b = pair[:3], pair[3:]
    if 'USD' in (a, b):
        o = b if a == 'USD' else a
        return o in BASEL_PAIRS_NON_USD
    return a in BASEL_PAIRS_NON_USD and b in BASEL_PAIRS_NON_USD   # fn 294 first-order cross

def fx_delta(inp):
    sp = set(inp.get('specified_pairs') or [])
    buckets = {}
    for s in inp['sensitivities']:
        rw = 0.15   # 21.87
        p = s['pair']
        if p in sp or (p[3:] + p[:3]) in sp:
            if not fx_eligible(p): raise ValueError('specified pair not eligible under MAR21.88: ' + p)
            rw /= math.sqrt(2)
        buckets.setdefault(p, []).append((p, rw * s['sensitivity']))
    per = {sc: aggregate(buckets, lambda *a: 0, lambda b, c: 0.6, lambda b: False, sc) for sc in SCEN}  # 21.89
    return finish('delta', per)

# ---------------- equity (MAR21.72-21.80) ----------------
EQ_RW = {1:55,2:60,3:45,4:55,5:30,6:35,7:40,8:50,9:70,10:50,11:70,12:15,13:25}  # Table 10 spot, %; repo = spot/100 (printed)
def eq_bucket_rho(b):  # 21.78(2)
    if b in (1,2,3,4): return .15
    if b in (5,6,7,8): return .25
    if b == 9: return .075
    if b == 10: return .125
    if b in (12,13): return .80
    return None
def eq_gamma(b, c):  # 21.80
    if b == 11 or c == 11: return 0.0
    if b <= 10 and c <= 10: return 0.15
    if {b, c} == {12, 13}: return 0.75
    return 0.45

def equity_delta(inp):
    buckets = {}
    for s in inp['sensitivities']:
        b = int(s['bucket']); rw = EQ_RW[b] / 100 * (1.0 if s['kind'] == 'SPOT' else 0.01)
        buckets.setdefault(b, []).append(((s['issuer'], s['kind']), rw * s['sensitivity']))
    def rho(b, k1, k2):
        (i1, kd1), (i2, kd2) = k1, k2
        if i1 == i2: return 0.999 if kd1 != kd2 else 1.0
        return eq_bucket_rho(b) * (0.999 if kd1 != kd2 else 1.0)
    per = {sc: aggregate(buckets, rho, eq_gamma, lambda b: b == 11, sc) for sc in SCEN}
    return finish('delta', per)

# ---------------- CSR non-securitisation (MAR21.51-21.57) ----------------
CSR_RW = {1:.5,2:1,3:5,4:3,5:3,6:2,7:1.5,8:2.5,9:2,10:4,11:12,12:7,13:8.5,14:5.5,15:5,16:12,17:1.5,18:5}  # Table 4 %
_cols = [1,2,3,4,5,6,7,8,16,17,18]   # Table 5 columns (1 stands for 1/9, ...)
_rows = {1:[75,10,20,25,20,15,10,0,45,45], 2:[5,15,20,15,10,10,0,45,45], 3:[5,15,20,5,20,0,45,45],
         4:[20,25,5,5,0,45,45], 5:[25,5,15,0,45,45], 6:[5,20,0,45,45], 7:[5,0,45,45], 8:[0,45,45],
         16:[0,0], 17:[75]}   # upper triangle as printed on p. 599, row = first sector class, values for later columns
SECG = {}
for r, vals in _rows.items():
    ci = _cols.index(r)
    assert len(vals) == len(_cols) - ci - 1, r
    for k, v in enumerate(vals):
        c = _cols[ci + 1 + k]; SECG[(r, c)] = v / 100; SECG[(c, r)] = v / 100
def sector_class(b):
    return ((b - 1) % 8) + 1 if b <= 15 else b
def csr_gamma(b, c):
    sb, sc_ = sector_class(b), sector_class(c)
    gs = 1.0 if sb == sc_ else SECG[(sb, sc_)]
    gr = 0.5 if (b <= 15 and c <= 15 and ((b <= 8) != (c <= 8))) else 1.0   # IG 1-8, HY/NR 9-15
    return gr * gs

def csr_delta(inp):
    buckets = {}
    for s in inp['sensitivities']:
        b = int(s['bucket'])
        buckets.setdefault(b, []).append(((s['issuer'], s['tenor'], s['curve']), CSR_RW[b] / 100 * s['sensitivity']))
    def rho(b, k1, k2):
        (n1, t1, c1), (n2, t2, c2) = k1, k2
        rn = 1.0 if n1 == n2 else (0.80 if b in (17, 18) else 0.35)
        rt = 1.0 if t1 == t2 else 0.65
        rb = 1.0 if c1 == c2 else 0.999
        return rn * rt * rb
    per = {sc: aggregate(buckets, rho, csr_gamma, lambda b: b == 16, sc) for sc in SCEN}
    return finish('delta', per)

# ---------------- commodity (MAR21.81-21.85) ----------------
COM_RW = {1:30,2:35,3:60,4:80,5:40,6:45,7:20,8:35,9:25,10:35,11:50}   # Table 11
COM_RHO = {1:55,2:95,3:40,4:80,5:60,6:65,7:55,8:45,9:15,10:40,11:15}  # Table 12
def com_gamma(b, c): return 0.0 if (b == 11 or c == 11) else 0.20     # 21.85

def commodity_delta(inp):
    buckets = {}
    for s in inp['sensitivities']:
        b = int(s['bucket'])
        buckets.setdefault(b, []).append(((s['commodity'], s['tenor'], s['location']), COM_RW[b] / 100 * s['sensitivity']))
    def rho(b, k1, k2):
        (m1, t1, l1), (m2, t2, l2) = k1, k2
        rc = 1.0 if m1 == m2 else COM_RHO[b] / 100
        rt = 1.0 if t1 == t2 else 0.99
        rl = 1.0 if l1 == l2 else 0.999
        return rc * rt * rl
    per = {sc: aggregate(buckets, rho, com_gamma, lambda b: False, sc) for sc in SCEN}
    return finish('delta', per)

# ---------------- vega (MAR21.90-21.95) ----------------
LARGE_EQ = (1,2,3,4,5,6,7,8,12,13)
def vega_rw(cls, b):            # Table 13 printed values
    return 0.7778 if (cls == 'EQUITY' and int(b) in LARGE_EQ) else 1.0
def vega_rw_unrounded(cls, b):  # fn 295: min(55% sqrt(LH/10), 100%)
    return min(0.55 * math.sqrt(20 / 10), 1.0) if (cls == 'EQUITY' and int(b) in LARGE_EQ) else 1.0

def vega(inp, rwf=vega_rw):
    cls = inp['risk_class']
    a = 0.01
    buckets = {}; net = {}
    for s in inp['sensitivities']:
        b = s['bucket'] if cls in ('GIRR', 'FX') else int(s['bucket'])
        key = (s.get('name'), s['option_maturity'], s.get('underlying_maturity'))
        net[(b, key)] = net.get((b, key), 0.0) + s['vega']
    for (b, key), v in net.items():
        buckets.setdefault(b, []).append((key, rwf(cls, b) * v))
    def rho_opt(T1, T2): return math.exp(-a * abs(T1 - T2) / min(T1, T2))
    def rho(b, k1, k2):
        (n1, T1, U1), (n2, T2, U2) = k1, k2
        if cls == 'GIRR':
            return min(rho_opt(T1, T2) * rho_opt(U1, U2), 1.0)   # 21.93
        if cls == 'FX' or n1 == n2: d = 1.0
        elif cls == 'EQUITY': d = eq_bucket_rho(b)
        elif cls == 'CSR_NONSEC': d = 0.80 if b in (17, 18) else 0.35
        elif cls == 'COMMODITY': d = COM_RHO[b] / 100
        return min(d * rho_opt(T1, T2), 1.0)                      # 21.94
    gam = {'GIRR': lambda b, c: 0.5, 'FX': lambda b, c: 0.6, 'EQUITY': eq_gamma, 'CSR_NONSEC': csr_gamma, 'COMMODITY': com_gamma}[cls]
    other = {'EQUITY': lambda b: b == 11, 'CSR_NONSEC': lambda b: b == 16}.get(cls, lambda b: False)
    per = {sc: aggregate(buckets, rho, gam, other, sc) for sc in SCEN}
    return finish('vega', per)

# ---------------- curvature (MAR21.5, 21.96-21.101) ----------------
def curvature(inp):
    cls = inp['risk_class']
    div = 1.5 if inp.get('fx_scalar') else 1.0     # MAR21.98
    buckets = {}
    for f in inp['factors']:
        b = f['bucket'] if cls in ('GIRR', 'FX') else int(f['bucket'])
        buckets.setdefault(b, []).append((f.get('name'), f['cvr_up'] / div, f['cvr_down'] / div))
    if cls in ('GIRR', 'FX'):
        for fl in buckets.values():
            if len(fl) > 1: raise ValueError('more than one curvature factor in a GIRR/FX bucket')
    def rho_d(b):
        if cls == 'EQUITY': return eq_bucket_rho(b)
        if cls == 'CSR_NONSEC': return 0.80 if b in (17, 18) else 0.35   # only rho^name (21.100)
        if cls == 'COMMODITY': return COM_RHO[b] / 100
        return 0.0
    gam_d = {'GIRR': lambda b, c: 0.5, 'FX': lambda b, c: 0.6, 'EQUITY': eq_gamma, 'CSR_NONSEC': csr_gamma, 'COMMODITY': com_gamma}[cls]
    other = {'EQUITY': lambda b: b == 11, 'CSR_NONSEC': lambda b: b == 16}.get(cls, lambda b: False)
    psi = lambda x, y: 0.0 if (x < 0 and y < 0) else 1.0
    out = {}; vals = []
    for sc in SCEN:
        K = {}; S = {}; sel = {}
        for b, fl in buckets.items():
            Kd = {}; Sd = {}
            for sign in (+1, -1):
                cv = [(x[1] if sign > 0 else x[2]) for x in fl]
                Sd[sign] = sum(cv)
                if other(b):
                    Kd[sign] = sum(max(c, 0.0) for c in cv)
                else:
                    t = sum(max(c, 0.0) ** 2 for c in cv)
                    r = scale(rho_d(b) ** 2, sc)    # 21.100: squared delta rho, then scenario
                    for i in range(len(cv)):
                        for j in range(len(cv)):
                            if i != j: t += r * cv[i] * cv[j] * psi(cv[i], cv[j])
                    Kd[sign] = math.sqrt(max(0.0, t))
            if Kd[1] > Kd[-1]: up = True
            elif Kd[1] < Kd[-1]: up = False
            else: up = Sd[1] > Sd[-1]               # 21.5(3)(a)(iii)
            sel[b] = 'up' if up else 'down'
            K[b] = max(Kd[1], Kd[-1]); S[b] = Sd[1] if up else Sd[-1]
        bl = sorted(buckets, key=bkey)
        t = sum(K[b] ** 2 for b in bl)
        for b in bl:
            for c in bl:
                if b != c: t += scale(gam_d(b, c) ** 2, sc) * S[b] * S[c] * psi(S[b], S[c])   # 21.101
        v = math.sqrt(max(0.0, t)); vals.append(v)
        out[sc] = dict(buckets=[dict(bucket=b, k=K[b], s=S[b], selected=sel[b]) for b in bl], curvature=v)
    m = max(vals)
    return dict(scenarios=out, capital=m, binding_scenario=SCEN[vals.index(m)])

check_table2()
