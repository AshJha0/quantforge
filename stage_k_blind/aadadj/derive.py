import json, os
from mpmath import mp, mpf, exp
mp.dps = 60
here = os.path.dirname(os.path.abspath(__file__))
inputs = json.load(open(os.path.join(here, 'inputs.json')))
template = json.load(open(os.path.join(here, 'template.json')))

def forward(P, br):
    """P: dict of mpf params; br: per-bucket bool (linear floor branch). Returns dict of outputs."""
    n = len(P['t'])
    t = P['t']; D = P['D']; ee = P['ee']; ene = P['ene']
    hc = P['hc']; hb = P['hb']; Rc = P['Rc']; Rb = P['Rb']
    sb_, sl = P['sb'], P['sl']
    Sc = [mpf(1)]; Sb = [mpf(1)]
    ac = mpf(0); ab = mpf(0)
    for i in range(n):
        dt = t[i] - (t[i-1] if i else 0)
        ac += hc[i]*dt; ab += hb[i]*dt
        Sc.append(exp(-ac)); Sb.append(exp(-ab))
    cva = dva = fca = fba = mpf(0); mva = kva = mpf(0)
    for i in range(n):
        dt = t[i] - (t[i-1] if i else 0)
        W = D[i]*Sc[i]*Sb[i]*dt
        cva += (1-Rc)*D[i]*ee[i]*(Sc[i]-Sc[i+1])*Sb[i]
        dva += (1-Rb)*D[i]*(-ene[i])*(Sb[i]-Sb[i+1])*Sc[i]
        fca += sb_*W*ee[i]
        slp = (sl - hb[i]*(1-Rb)) if (br[i] if P['ov'] else True) else mpf(0)
        if not P['ov']: slp = sl
        fba += slp*W*(-ene[i])
        if 'im' in P: mva += P['ims']*W*P['im'][i]
        if 'cap' in P: kva += P['hur']*W*P['cap'][i]
    out = dict(cva=cva, dva=dva, fca=fca, fba=fba, fva=fca-fba)
    if 'im' in P: out['mva'] = mva
    if 'cap' in P: out['kva'] = kva
    return out

def build(inp):
    n = len(inp['times'])
    f = inp['funding']
    P = dict(t=[mpf(x) for x in inp['times']], D=[mpf(x) for x in inp['discount_factors']],
             ee=[mpf(x) for x in inp['ee']], ene=[mpf(x) for x in inp['ene']],
             hc=[mpf(inp['counterparty']['hazard_rate'])]*n, hb=[mpf(inp['own']['hazard_rate'])]*n,
             Rc=mpf(inp['counterparty']['recovery']), Rb=mpf(inp['own']['recovery']),
             sb=mpf(f['borrow_spread']), sl=mpf(f['lend_spread']), ov=bool(f['exclude_dva_overlap']))
    if 'im' in inp: P['im'] = [mpf(x) for x in inp['im']]; P['ims'] = mpf(inp['im_spread'])
    if 'capital' in inp: P['cap'] = [mpf(x) for x in inp['capital']]; P['hur'] = mpf(inp['hurdle_rate'])
    # branch decided in binary64 (flat input hazard)
    x = f['lend_spread'] - inp['own']['hazard_rate']*(1-inp['own']['recovery'])
    br = [x >= 0.0]*n
    return P, br

def copyP(P):
    Q = dict(P)
    for k, v in P.items():
        if isinstance(v, list): Q[k] = list(v)
    return Q

# accessors: (get, set) of a parameter given a spec
def shifted(P, spec, delta):
    Q = copyP(P)
    kind, idx = spec
    if kind == 'flat_hc': Q['hc'] = [h+delta for h in Q['hc']]
    elif kind == 'flat_hb': Q['hb'] = [h+delta for h in Q['hb']]
    elif kind == 'hc': Q['hc'][idx] += delta
    elif kind == 'hb': Q['hb'][idx] += delta
    elif kind == 'D': Q['D'][idx] += delta
    elif kind == 'ee': Q['ee'][idx] += delta
    elif kind == 'ene': Q['ene'][idx] += delta
    elif kind == 'im': Q['im'][idx] += delta
    elif kind == 'cap': Q['cap'][idx] += delta
    else: Q[kind] += delta
    return Q

def base_value(P, spec):
    kind, idx = spec
    m = {'flat_hc': P['hc'][0], 'flat_hb': P['hb'][0]}
    if kind in m: return m[kind]
    if idx is not None and isinstance(P[kind], list): return P[kind][idx]
    return P[kind]

def deriv(P, br, spec):
    x = base_value(P, spec)
    d0 = mpf('1e-12')*max(mpf(1), abs(x))
    def Dd(d):
        a = forward(shifted(P, spec, d), br); b = forward(shifted(P, spec, -d), br)
        return {k: (a[k]-b[k])/(2*d) for k in a}
    d1 = Dd(d0); d2 = Dd(d0/2)
    return {k: (4*d2[k]-d1[k])/3 for k in d1}

KEYMAP = {  # template key -> (spec kind, vector?)
 'counterparty.hazard_rate': ('flat_hc', False), 'counterparty.hazard_buckets': ('hc', True),
 'counterparty.recovery': ('Rc', False), 'own.hazard_rate': ('flat_hb', False),
 'own.hazard_buckets': ('hb', True), 'own.recovery': ('Rb', False),
 'discount_factors': ('D', True), 'ee': ('ee', True), 'ene': ('ene', True),
 'funding.borrow_spread': ('sb', False), 'funding.lend_spread': ('sl', False),
 'im': ('im', True), 'im_spread': ('ims', False), 'capital': ('cap', True), 'hurdle_rate': ('hur', False)}

answers = {}
for cid, case in inputs.items():
    inp = case['inputs']
    P, br = build(inp)
    n = len(P['t'])
    vals = forward(P, br)
    tmpl = template[cid]
    ans = {k: float(vals[k]) for k in tmpl if k != 'gradient'}
    grad = {}
    cache = {}
    for out, keys in tmpl['gradient'].items():
        grad[out] = {}
        for key, v in keys.items():
            kind, vec = KEYMAP[key]
            if vec:
                arr = []
                for j in range(len(v)):
                    ck = (kind, j)
                    if ck not in cache: cache[ck] = deriv(P, br, ck)
                    arr.append(float(cache[ck][out]))
                grad[out][key] = arr
            else:
                ck = (kind, None)
                if ck not in cache: cache[ck] = deriv(P, br, ck)
                grad[out][key] = float(cache[ck][out])
    ans['gradient'] = grad
    answers[cid] = ans
    # sanity: flat hazard derivative equals sum of bucket derivatives
json.dump(answers, open(os.path.join(here, 'answers.json'), 'w'), indent=1)
