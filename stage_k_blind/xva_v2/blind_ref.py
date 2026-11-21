import json, os, re, copy, math
from mpmath import mp, mpf, exp, sqrt, erfinv, ncdf, npdf, quad, inf, ceil as mceil
mp.dps = 60
PK = r"C:/Work/Claude/qf-blind/xva_v2_packet/"
OUT = r"C:/Work/Claude/qf-blind/xva_v2_out/blind_results.json"
I = json.load(open(PK + "inputs.json"))
T = json.load(open(PK + "template.json"))
FX = json.load(open(PK + "fixed_inputs.json"))


def conv(x):
    if isinstance(x, bool) or isinstance(x, str) or x is None:
        return x
    if isinstance(x, (int, float)):
        return mpf(x)
    if isinstance(x, list):
        return [conv(v) for v in x]
    if isinstance(x, dict):
        return {k: conv(v) for k, v in x.items()}
    return x


def zq(q):
    return sqrt(2) * erfinv(2 * q - 1)


def Phi(x):
    return ncdf(x)


def phi(x):
    return npdf(x)


def S(h, t):
    return exp(-h * t)


# ---------- G-41 ----------
def adj(p):
    t = [mpf(0)] + p['times']
    D = p['discount_factors']
    ee = p['ee']
    ene = p['ene']
    hc, Rc = p['counterparty']['hazard_rate'], p['counterparty']['recovery']
    hb, Rb = p['own']['hazard_rate'], p['own']['recovery']
    sb, sl = p['funding']['borrow_spread'], p['funding']['lend_spread']
    if p['funding'].get('exclude_dva_overlap'):
        sl = max(sl - hb * (1 - Rb), mpf(0))
    cva = dva = fca = fba = mpf(0)
    for i in range(1, len(t)):
        d = t[i] - t[i - 1]
        k = i - 1
        Sc0, Sc1, Sb0, Sb1 = S(hc, t[i - 1]), S(hc, t[i]), S(hb, t[i - 1]), S(hb, t[i])
        cva += D[k] * ee[k] * (Sc0 - Sc1) * Sb0
        dva += D[k] * abs(ene[k]) * (Sb0 - Sb1) * Sc0
        fca += D[k] * ee[k] * Sc0 * Sb0 * d
        fba += D[k] * abs(ene[k]) * Sc0 * Sb0 * d
    return dict(cva=(1 - Rc) * cva, dva=(1 - Rb) * dva, fca=sb * fca, fba=sl * fba, fva=sb * fca - sl * fba)


# ---------- curves ----------
def sT(curve, Tq):
    ten = curve['tenors']
    z = curve['zero_spreads']
    pts = [(mpf(0), mpf(0))] + [(ten[j], z[j] * ten[j]) for j in range(len(ten))]
    if Tq >= pts[-1][0]:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        return y1 + (Tq - x1) * (y1 - y0) / (x1 - x0)
    for j in range(1, len(pts)):
        if Tq <= pts[j][0]:
            (x0, y0), (x1, y1) = pts[j - 1], pts[j]
            return y0 + (Tq - x0) * (y1 - y0) / (x1 - x0)


def fwd(curve, t):
    f = []
    for i in range(len(t)):
        a = t[i - 1] if i else mpf(0)
        f.append((sT(curve, t[i]) - sT(curve, a)) / (t[i] - a))
    return f


def funding(p):
    t = p['times']
    D = p['discount_factors']
    ee = p['ee']
    ene = p['ene']
    hc = p['counterparty']['hazard_rate']
    hb, Rb = p['own']['hazard_rate'], p['own']['recovery']
    fb = fwd(p['borrow_curve'], t)
    fl = fwd(p['lend_curve'], t)
    if p.get('exclude_dva_overlap'):
        fl = [max(x - hb * (1 - Rb), mpf(0)) for x in fl]
    fca = fba = mpf(0)
    for i in range(len(t)):
        a = t[i - 1] if i else mpf(0)
        d = t[i] - a
        w = S(hc, a) * S(hb, a) * D[i] * d
        fca += fb[i] * w * ee[i]
        fba += fl[i] * w * abs(ene[i])
    return dict(fca=fca, fba=fba, fva=fca - fba, forward_borrow=fb, forward_lend=fl)


# ---------- IM, MVA ----------
def im_project(p):
    m = p['method']
    if m == 'GIVEN':
        return dict(expected_im=p['profile'])
    if m == 'NORMAL_MPOR':
        dpy = p.get('days_per_year', mpf(250))
        q = p.get('quantile', mpf('0.99'))
        z = zq(q)
        return dict(expected_im=[z * s * sqrt(p['mpor_days'] / dpy) for s in p['stdev']])
    if m == 'REGRESSION':
        x = p['regressor']
        X = p['increment']
        n = int(p['order'])
        q = p.get('quantile', mpf('0.99'))
        N = len(x)
        A = mp.matrix(N, n + 1)
        for r in range(N):
            for c in range(n + 1):
                A[r, c] = x[r] ** c
        y = mp.matrix([v * v for v in X])
        beta = mp.qr_solve(A, y)[0]
        fit = A * beta
        mX = sum(X) / N
        z = zq(q)
        im = [z * sqrt(max(fit[r] - mX * mX, mpf(0))) for r in range(N)]
        return dict(im=im, expected_im=sum(im) / N)


def mva(p):
    t = p['times']
    D = p['discount_factors']
    hc = p['counterparty']['hazard_rate']
    hb = p['own']['hazard_rate']
    ei = p['expected_im']
    out = {}
    if isinstance(ei, dict):
        ei = im_project(ei)['expected_im']
        out['expected_im'] = ei
    fb = fwd(p['borrow_curve'], t) if 'borrow_curve' in p else [p['borrow_spread']] * len(t)
    sI = p['im_spread']
    terms = []
    for i in range(len(t)):
        a = t[i - 1] if i else mpf(0)
        d = t[i] - a
        terms.append((fb[i] - sI) * d * S(hc, a) * S(hb, a) * D[i] * ei[i])
    out['terms'] = terms
    out['mva'] = sum(terms)
    return out


# ---------- G-40 collateral ----------
def collateral_paths(values, csa, l):
    Hr, Hp, mta = csa['threshold_receive'], csa['threshold_post'], csa['minimum_transfer_amount']
    IA = csa.get('independent_amount', mpf(0))
    res = []
    for V in values:
        Tg = [max(v - Hr, 0) - max(-v - Hp, 0) + IA for v in V]
        K = [Tg[0]]
        for j in range(1, len(V)):
            K.append(Tg[j] if abs(Tg[j] - K[j - 1]) >= mta else K[j - 1])
        res.append([K[max(i - l, 0)] for i in range(len(V))])
    return res


def sum_trades(trades, ns):
    tr = [x for x in trades if x['netting_set'] == ns]
    P = len(tr[0]['values'])
    n = len(tr[0]['values'][0])
    return [[sum(x['values'][p][i] for x in tr) for i in range(n)] for p in range(P)]


def colva(p):
    t = p['times']
    n = len(t) - 1
    D = p['discount_factors']
    out = {}
    if 'trades' in p:
        ns = list(p['csa'].keys())[0]
        V = sum_trades(p['trades'], ns)
        csa = p['csa'][ns]
        C = collateral_paths(V, csa, int(csa['mpor_steps']))
        prof = [sum(C[q][i] for q in range(len(C))) / len(C) for i in range(n)]
        out['collateral_profile'] = prof
        col = prof
    else:
        col = p['collateral']
    sp = p['spread']
    sp = sp if isinstance(sp, list) else [sp] * n
    surv = p.get('survival', 'NONE')
    W = [exp(-(p['counterparty']['hazard_rate'] + p['own']['hazard_rate']) * t[i]) if surv == 'BOTH' else mpf(1)
         for i in range(n)]
    terms = [-col[i] * sp[i] * (t[i + 1] - t[i]) * D[i] * W[i] for i in range(n)]
    out['terms'] = terms
    out['colva'] = sum(terms)
    if 'overnight_rates' in p:
        r = p['overnight_rates']
        out['collateral_floor'] = -sum(col[i] * max(-r[i], 0) * (t[i + 1] - t[i]) * D[i] * W[i] for i in range(n))
    return out


# ---------- closeout ----------
def closeout_normal(p):
    s = p['sigma'] * sqrt(p['mpor_days'] / p.get('days_per_year', mpf(250)))
    H = p['threshold_receive']
    v0 = p['v0']
    im = p['im'] if 'im' in p else zq(p['im_quantile']) * s
    vm = max(v0 - H, mpf(0))
    m = v0 - vm - im
    return dict(s=s, vm=vm, im=im, ee=m * Phi(m / s) + s * phi(m / s))


def closeout_paths(p):
    t = p['times']
    n = len(t)
    res = {}
    for ns, csa in p['csa'].items():
        V = sum_trades(p['trades'], ns)
        l = int(csa['mpor_steps'])
        P = len(V)
        C = collateral_paths(V, csa, l)
        im = p.get('im_received', [mpf(0)] * n)
        iml = [im[max(i - l, 0)] for i in range(n)]
        q = p['pfe_quantile']

        def prof(use_im):
            return [[max(V[k][i] - C[k][i] - (iml[i] if use_im else 0), 0) for k in range(P)] for i in range(n)]
        E = prof(True)
        E0 = prof(False)
        ee = [sum(r) / P for r in E]
        ee0 = [sum(r) / P for r in E0]
        ene = [sum(min(V[k][i] - C[k][i], 0) for k in range(P)) / P for i in range(n)]
        pfe = []
        for i in range(n):
            srt = sorted(E[i])
            idx = int(mceil(q * P))
            pfe.append(srt[max(idx, 1) - 1])
        T0 = t[0]
        epe = sum(ee[i] * (t[i] - t[i - 1]) for i in range(1, n)) / (t[-1] - t[0])
        eee = [ee[0]]
        for i in range(1, n):
            eee.append(max(eee[-1], ee[i]))
        idxs = [i for i in range(1, n) if t[i] <= T0 + 1]
        eeff = sum(eee[i] * (t[i] - t[i - 1]) for i in idxs) / (t[idxs[-1]] - T0)
        res[ns] = dict(ee=ee, ene=ene, pfe=pfe, epe=epe, effective_epe=eeff, ee_no_im=ee0)
    return dict(netting_sets=res)


# ---------- WWR ----------
def erfinv_pd(pd):
    return sqrt(2) * erfinv(2 * pd - 1)


def wwr(p):
    t = p['times']
    D = p['discount_factors']
    mu = p['mean']
    s = p['stdev']
    h, R, rho = p['hazard_rate'], p['recovery'], p['rho']

    def run(rho):
        c = -rho
        r = sqrt(1 - c * c)

        def G(i, beta):
            if beta is None:
                return mpf(0)
            a = -mu[i] / s[i]
            up = max(a, mpf(0)) + 26
            br = [a]
            x = a
            while x < up:
                x = x + 2
                br.append(min(x, up))
            P = quad(lambda z: phi(z) * Phi((beta - c * z) / r), br)
            Ez = quad(lambda z: z * phi(z) * Phi((beta - c * z) / r), br)
            return mu[i] * P + s[i] * Ez
        betas = [None] + [erfinv_pd(1 - exp(-h * ti)) for ti in t]
        terms = []
        fac = []
        for i in range(len(t)):
            dG = G(i, betas[i + 1]) - G(i, betas[i])
            terms.append((1 - R) * D[i] * dG)
            EE = mu[i] * Phi(mu[i] / s[i]) + s[i] * phi(mu[i] / s[i])
            pd1 = 1 - exp(-h * t[i])
            pd0 = 1 - exp(-h * (t[i - 1] if i else 0))
            fac.append(dG / (EE * (pd1 - pd0)))
        return terms, fac
    terms, fac = run(rho)
    ind, _ = run(mpf(0))
    return dict(cva=sum(terms), bucket_terms=terms, wwr_factor=fac, cva_independent=sum(ind))


# ---------- portfolio_hw CVA with EE fixed ----------
def hw_cva(p, dee):
    t = [mpf(0)] + p['exposure_times']
    h, R = p['hazard_rate'], p['recovery']
    return dict(cva=(1 - R) * sum(dee[i] * (exp(-h * t[i]) - exp(-h * t[i + 1])) for i in range(len(dee))))


# ---------- stressed EEPE ----------
def stressed(p):
    g = p['grid']
    alpha = p.get('alpha', mpf('1.4'))
    m = len(g) - 1
    res = {}
    Kc = Ks = mpf(0)
    for ns in p['netting_sets']:
        w = ns['capital_weight']
        mat = ns.get('maturity')
        Ts = mat if (mat is not None and mat < 1) else mpf(1)
        d = {}
        for lab in ('current', 'stressed'):
            ee = ns['ee_' + lab]
            eee = [ee[0]]
            for k in range(1, m + 1):
                eee.append(max(eee[-1], ee[k]))
            eepe = sum(eee[k] * (g[k] - g[k - 1]) for k in range(1, m + 1) if g[k] <= Ts) / Ts
            d['eee_' + lab] = eee
            d['eepe_' + lab] = eepe
            d['ead_' + lab] = alpha * eepe
        Kc += w * d['ead_current']
        Ks += w * d['ead_stressed']
        res[ns['id']] = d
    cal = 'stressed' if Ks > Kc else 'current'
    for d in res.values():
        d['ead_used'] = d['ead_' + cal]
    return dict(netting_sets=res, k_current=Kc, k_stressed=Ks, calibration=cal)


def mpor(p):
    F = 5 if p['repo_only'] else 10
    if p['max_trades_last_quarter'] > 5000 or p['illiquid']:
        F = 20
    if p['long_disputes_last_two_quarters'] > 2:
        F *= 2
    fl = F + p['remargin_days'] - 1
    out = dict(floor_days=fl)
    if 'model_mpor_days' in p:
        out['mpor_days'] = max(p['model_mpor_days'], fl)
        out['binding'] = bool(p['model_mpor_days'] <= fl)
    return out


def shocked(p):
    ten = p['curve']['tenors']
    z = p['curve']['zero_rates']
    sc = p['scenario']
    st, sb = sc['tenors'], sc['shift_bp']
    scale = p.get('scale', mpf(1))

    def interp(x):
        if x <= st[0]:
            return sb[0]
        if x >= st[-1]:
            return sb[-1]
        for j in range(1, len(st)):
            if x <= st[j]:
                return sb[j - 1] + (x - st[j - 1]) * (sb[j] - sb[j - 1]) / (st[j] - st[j - 1])
    bp = [interp(x) * scale for x in ten]
    zr = [z[j] + bp[j] / 10000 for j in range(len(ten))]
    return dict(applied_bp=bp, shocked_zero_rates=zr,
                shocked_discount_factors=[exp(-zr[j] * ten[j]) for j in range(len(ten))])


OPS = {'xva.adjustments.value': adj, 'xva.colva.value': colva, 'xva.funding.asymmetric': funding,
       'xva.mva.value': mva, 'xva.wwr.cva_gaussian_copula': wwr, 'xva.exposure.closeout_normal': closeout_normal,
       'xva.exposure.closeout': closeout_paths, 'xva.im.project': im_project, 'xva.exposure.stressed_eepe': stressed,
       'xva.mpor.days': mpor, 'xva.stress.shocked': shocked}


def get_set(d, path, val=None, setv=False):
    keys = []
    for tk in path.split('.'):
        m = re.match(r'(\w+)(?:\[(\d+)\])?$', tk)
        keys.append((m.group(1), None if m.group(2) is None else int(m.group(2))))
    cur = d
    for j, (k, ix) in enumerate(keys):
        last = j == len(keys) - 1
        if ix is None:
            if last:
                if setv:
                    cur[k] = val
                return cur[k]
            cur = cur[k]
        else:
            if last:
                if setv:
                    cur[k][ix] = val
                return cur[k][ix]
            cur = cur[k][ix]


def grad(fn, params, path, out):
    x = get_set(params, path)
    h = mpf(10) ** -11 * max(mpf(1), abs(x))

    def f(v):
        q = copy.deepcopy(params)
        get_set(q, path, v, True)
        return fn(q)[out]
    return (-f(x + 2 * h) + 8 * f(x + h) - 8 * f(x - h) + f(x - 2 * h)) / (12 * h)


def tofloat(x):
    if isinstance(x, mpf):
        return float(x)
    if isinstance(x, list):
        return [tofloat(v) for v in x]
    if isinstance(x, dict):
        return {k: tofloat(v) for k, v in x.items()}
    return x


def fill(tmpl, res):
    if isinstance(tmpl, dict):
        o = {}
        for k, v in tmpl.items():
            sub = res[k] if (isinstance(res, dict) and k in res) else None
            o[k] = fill(v, sub)
        return o
    if isinstance(tmpl, list):
        return [fill(v, res[i] if isinstance(res, list) and i < len(res) else None) for i, v in enumerate(tmpl)]
    return tofloat(res) if res is not None else None


results = {}
for case, c in I.items():
    op = c['operation']
    inp = conv(c['inputs'])
    if op == 'xva.sens.aad':
        inner = inp['operation']
        ip = inp['inputs']
        wrt = c['inputs']['wrt']
        if inner == 'xva.exposure.portfolio_hw':
            dee = conv(FX['expsim_g-0003']['discounted_ee'])
            fn = lambda q, dee=dee: hw_cva(q, dee)
        else:
            fn = OPS[inner]
        res = dict(fn(ip))
        res['gradient'] = {o: {w: grad(fn, ip, w, o) for w in wrt} for o in c['inputs']['outputs']}
    else:
        res = OPS[op](inp)
    results[case] = fill(T[case], res)


def nulls(x):
    if x is None:
        return 1
    if isinstance(x, dict):
        return sum(nulls(v) for v in x.values())
    if isinstance(x, list):
        return sum(nulls(v) for v in x)
    return 0


for k, v in results.items():
    n = nulls(v)
    if n:
        print('NULL leaves', k, n)
for k, v in results.items():
    if k.startswith('mpor_'):
        for kk in ('floor_days', 'mpor_days'):
            if kk in v and v[kk] is not None:
                v[kk] = int(v[kk])
json.dump(results, open(OUT, 'w'), indent=1)
print('done', len(results))
