import json, math, os, calendar
from datetime import date, timedelta
P = 'C:/Work/Claude/qf-blind/k2_packet/'
OUT = 'C:/Work/Claude/qf-blind/k2_results/'

RANK = {'COVERED': 4, 'SENIOR': 3, 'NON_SENIOR': 2, 'EQUITY': 1}
LGD = {'EQUITY': 1.0, 'NON_SENIOR': 1.0, 'SENIOR': 0.75, 'COVERED': 0.25}
RATING_RW = {'AAA': 0.005, 'AA': 0.02, 'A': 0.03, 'BBB': 0.06, 'BB': 0.15, 'B': 0.30,
             'CCC': 0.50, 'UNRATED': 0.15, 'DEFAULTED': 1.0}


def mat_w(m):
    return 1.0 if m >= 1 else max(m, 0.25)


def gross_jtd(p, lgd_override=None):
    lgd = LGD[p['seniority']] if lgd_override is None else lgd_override
    if p.get('lgd_applies', True) is False:
        lgd = 1.0
    pnl = p['market_value'] - p['notional']
    if p['notional'] > 0:
        return max(lgd * p['notional'] + pnl, 0.0)
    if p['notional'] < 0:
        return min(lgd * p['notional'] + pnl, 0.0)
    return 0.0


def offset(items):
    """items: list of (seniority, scaled_jtd) in input order -> (net_long, net_short<=0)."""
    longs = [[RANK[s], v] for s, v in items if v > 0]
    shorts = [[RANK[s], v] for s, v in items if v < 0]
    for sh in sorted(shorts, key=lambda x: -x[0]):
        need = -sh[1]
        for lg in sorted(longs, key=lambda x: x[0]):
            if need <= 0:
                break
            if lg[0] >= sh[0] and lg[1] > 0:
                use = min(need, lg[1])
                lg[1] -= use
                need -= use
        sh[1] = -need
    return sum(l[1] for l in longs), sum(s[1] for s in shorts)


def drc_nonsec(inp):
    res = {'positions': {}, 'obligors': {}, 'buckets': {}}
    byob = {}
    obbucket = {}
    for p in inp['positions']:
        g = gross_jtd(p)
        w = mat_w(p['maturity_years'])
        res['positions'][p['id']] = {'gross_jtd': g, 'weight': w, 'scaled_jtd': w * g}
        byob.setdefault(p['obligor'], []).append((p['seniority'], w * g))
        obbucket[p['obligor']] = p['bucket']
    bk = {}
    for ob, items in byob.items():
        nl, ns = offset(items)
        rw = RATING_RW[inp['ratings'][ob]]
        res['obligors'][ob] = {'net_long': nl, 'net_short': ns, 'rw': rw}
        b = bk.setdefault(obbucket[ob], [0.0, 0.0, 0.0, 0.0])
        b[0] += nl
        b[1] += -ns
        b[2] += rw * nl
        b[3] += rw * (-ns)
    total = 0.0
    for b, (sl, ss, wl, ws) in bk.items():
        hbr = sl / (sl + ss) if (sl + ss) != 0 else None
        drc = max(wl - hbr * ws, 0.0) if hbr is not None else 0.0
        res['buckets'][b] = {'hbr': hbr, 'wtd_long': wl, 'wtd_short': ws, 'drc': drc}
        total += drc
    res['drc'] = total
    return res


def drc_sec(inp):
    net = {}
    for p in inp['positions']:
        k = (p['bucket'], p['pool'], p['tranche'])
        net.setdefault(k, [0.0, p['rw']])
        net[k][0] += mat_w(p['maturity_years']) * p['market_value']
    bk = {}
    for (b, pool, tr), (v, rw) in net.items():
        x = bk.setdefault(b, [0.0, 0.0, 0.0, 0.0])
        if v > 0:
            x[0] += v
            x[2] += rw * v
        else:
            x[1] += -v
            x[3] += rw * (-v)
    res = {'buckets': {}}
    tot = 0.0
    for b, (sl, ss, wl, ws) in bk.items():
        hbr = sl / (sl + ss) if sl + ss != 0 else None
        drc = max(wl - hbr * ws, 0.0) if hbr is not None else 0.0
        res['buckets'][b] = {'hbr': hbr, 'drc': drc}
        tot += drc
    res['drc'] = tot
    return res


def drc_ctp(inp):
    if 'bucket_drc' in inp:
        d = inp['bucket_drc']
        return {'drc': max(sum(max(x, 0) + 0.5 * min(x, 0) for x in d), 0.0)}
    net = {}
    for p in inp['positions']:
        k = (p['index'], p['series'], p['tranche'])
        net.setdefault(k, [0.0, p['rw']])
        net[k][0] += mat_w(p['maturity_years']) * p['market_value']
    bk = {}
    SL = SS = 0.0
    for (idx, s, t), (v, rw) in net.items():
        x = bk.setdefault(idx, [0.0, 0.0])
        if v > 0:
            x[0] += rw * v
            SL += v
        else:
            x[1] += rw * (-v)
            SS += -v
    hbr = SL / (SL + SS) if SL + SS != 0 else 0.0
    res = {'hbr_ctp': hbr, 'buckets': {}}
    s = 0.0
    for idx, (wl, ws) in bk.items():
        d = wl - hbr * ws
        res['buckets'][idx] = {'drc': d}
        s += max(d, 0) + 0.5 * min(d, 0)
    res['drc'] = max(s, 0.0)
    return res


def rrao(inp):
    t = 0.0
    for i in inp['instruments']:
        if i['back_to_back']:
            continue
        if i['kind'] == 'OTHER' and i['listed_or_clearable']:
            continue
        t += i['gross_notional'] * (0.01 if i['kind'] == 'EXOTIC' else 0.001)
    return {'rrao': t}


def es_hist(pnl, c=0.975):
    if not pnl:
        return 0.0
    L = sorted(-x for x in pnl)
    n = len(L)
    nc = n * c
    w = n - nc
    if w == 0:
        return L[-1]
    m = math.floor(w)
    s = sum(L[n - m:]) + (w - m) * L[n - m - 1]
    return s / w


LH = [10, 20, 40, 60, 120]


def es_lh(inp):
    if 'es_t' in inp:
        e = list(inp['es_t'])
    else:
        e = [es_hist(l) for l in inp['pnl']]
    s = e[0] ** 2
    for j in range(1, 5):
        s += (e[j] * math.sqrt((LH[j] - LH[j - 1]) / 10)) ** 2
    return {'es_by_horizon': e, 'es': math.sqrt(s)}


def est(inp):
    r = inp['es_fc'] / inp['es_rc']
    return {'ratio': r, 'ratio_floored': r < 1, 'es': inp['es_rs'] * max(1.0, r)}


def imcc(inp):
    c = est(inp['portfolio'])['es']
    cl = {k: est(v)['es'] for k, v in inp['classes'].items()}
    return {'imcc_c': c, 'classes': cl, 'imcc': 0.5 * c + 0.5 * sum(cl.values())}


def ses(inp):
    a = math.sqrt(sum(x * x for x in inp['idio_credit']))
    b = math.sqrt(sum(x * x for x in inp['idio_equity']))
    k = inp['other']
    c = math.sqrt((0.6 * sum(k)) ** 2 + (1 - 0.36) * sum(x * x for x in k))
    return {'ses': a + b + c}


def mult(n):
    t = {0: 1.5, 1: 1.5, 2: 1.5, 3: 1.5, 4: 1.5, 5: 1.7, 6: 1.76, 7: 1.83, 8: 1.88, 9: 1.92}
    return t.get(n, 2.0)


def cap(inp):
    mc = mult(inp['exceptions']) + inp.get('qualitative_addon', 0)
    ca = max(inp['imcc_prev'] + inp['ses_prev'], mc * inp['imcc_avg'] + inp['ses_avg'])
    ga = ca + inp['drc']
    sa = sum(d['sa'] for d in inp['desks'])
    amber = sum(d['sa'] for d in inp['desks'] if d['zone'] == 'AMBER')
    k = 0.5 * amber / sa if amber > 0 else 0.0
    sur = k * max(0.0, sa - ga)
    acr = min(ga + sur + inp['c_u'], inp['sa_all']) + max(0.0, ga - sa)
    return {'m_c': mc, 'c_a': ca, 'ima_ga': ga, 'sa_ga': sa, 'k': k, 'surcharge': sur, 'acr_total': acr}


def rfet(inp):
    asof = date.fromisoformat(inp['as_of'])
    y, m = asof.year - 1, asof.month
    d0 = date(y, m, min(asof.day, calendar.monthrange(y, m)[1]))
    start = d0 + timedelta(days=1)  # window (d0, asof]
    days = sorted({date.fromisoformat(s) for s in inp['observations']})
    days = [d for d in days if start <= d <= asof]
    ds = set(days)
    cnts = []
    s = start
    while s + timedelta(days=89) <= asof:
        cnts.append((s, sum(1 for i in range(90) if (s + timedelta(days=i)) in ds)))
        s += timedelta(days=1)
    mn = min(c for _, c in cnts)
    fail = next(((a, c) for a, c in cnts if c < 4), None)
    crit1 = len(days) >= 24 and fail is None
    crit2 = len(days) >= 100
    return {'distinct_days': len(days), 'crit1': crit1, 'min_window_count': mn,
            'first_failing_window_start': fail[0].isoformat() if fail else None,
            'first_failing_window_count': fail[1] if fail else None,
            'crit2': crit2, 'pass': crit1 or crit2}


BA_RW = {'sovereign': (0.005, 0.02), 'local_gov': (0.01, 0.04), 'financials': (0.05, 0.12),
         'basic_materials_energy_industrials': (0.03, 0.07), 'consumer_transport_admin': (0.03, 0.085),
         'technology_telecom': (0.02, 0.055), 'health_utilities_professional': (0.015, 0.05),
         'other': (0.05, 0.12)}


def baRW(sector, q):
    return BA_RW[sector][0 if q == 'IG' else 1]


def DF(m):
    return -math.expm1(-0.05 * m) / (0.05 * m)


def cva_ba(inp):
    res = {'counterparties': {}}
    sc = {}
    for c in inp['counterparties']:
        s = 0.0
        for ns in c['netting_sets']:
            df = 1.0 if ns['imm'] else DF(ns['m'])
            s += ns['m'] * ns['ead'] * df
        sc[c['id']] = baRW(c['sector'], c['quality']) * s / 1.4
        res['counterparties'][c['id']] = {'scva': sc[c['id']]}
    S = sum(sc.values())
    S2 = sum(v * v for v in sc.values())
    kr = math.sqrt((0.5 * S) ** 2 + 0.75 * S2)
    res['k_reduced'] = kr
    if inp['version'] == 'REDUCED':
        res['capital'] = 0.65 * kr
    else:
        R = {'DIRECT': 1.0, 'LEGAL': 0.8, 'SECTOR_REGION': 0.5}
        snh = {k: 0.0 for k in sc}
        hma = {k: 0.0 for k in sc}
        for h in inp['single_name_hedges']:
            t = baRW(h['sector'], h['quality']) * h['m'] * h['notional'] * DF(h['m'])
            r = R[h['relation']]
            snh[h['counterparty']] += r * t
            hma[h['counterparty']] += (1 - r * r) * t * t
        ih = 0.0
        for i in inp['index_hedges']:
            rw = 0.7 * sum(c['weight'] * baRW(c['sector'], c['quality']) for c in i['constituents'])
            ih += rw * i['m'] * i['notional'] * DF(i['m'])
        for k in sc:
            res['counterparties'][k]['snh'] = snh[k]
            res['counterparties'][k]['hma'] = hma[k]
        d = [sc[k] - snh[k] for k in sc]
        kh = math.sqrt((0.5 * sum(d) - ih) ** 2 + 0.75 * sum(x * x for x in d) + sum(hma.values()))
        kf = 0.25 * kr + 0.75 * kh
        res.update({'ih': ih, 'k_hedged': kh, 'k_full': kf, 'capital': 0.65 * kf})
    res['rwa'] = 12.5 * res['capital']
    return res


IR_RW = {'1Y': 0.0111, '2Y': 0.0093, '5Y': 0.0074, '10Y': 0.0074, '30Y': 0.0074, 'inflation': 0.0111}
IR_RHO = {('1Y', '2Y'): .91, ('1Y', '5Y'): .72, ('1Y', '10Y'): .55, ('1Y', '30Y'): .31, ('1Y', 'inflation'): .40,
          ('2Y', '5Y'): .87, ('2Y', '10Y'): .72, ('2Y', '30Y'): .45, ('2Y', 'inflation'): .40,
          ('5Y', '10Y'): .91, ('5Y', '30Y'): .68, ('5Y', 'inflation'): .40, ('10Y', '30Y'): .83,
          ('10Y', 'inflation'): .40, ('30Y', 'inflation'): .40}
IR_SPEC = {'USD', 'EUR', 'GBP', 'AUD', 'CAD', 'SEK', 'JPY'}
CCS_RW = {'1a': (0.005, 0.02), '1b': (0.01, 0.04), '2': (0.05, 0.12), '3': (0.03, 0.07), '4': (0.03, 0.085),
          '5': (0.02, 0.055), '6': (0.015, 0.05), '7': (0.05, 0.12), '8': (0.015, 0.05)}


def sa_one(cls, kind, sens, rep):
    items = []
    for s in sens:
        f = s['factor']
        if cls == 'IR' and kind == 'DELTA':
            spec = s['bucket'] in IR_SPEC or s['bucket'] == rep
            rw = IR_RW[f] if spec else 0.0158
        elif cls == 'IR':
            rw = 1.0
        elif cls == 'FX':
            rw = 0.11 if kind == 'DELTA' else 1.0
        elif cls == 'CCS':
            rw = CCS_RW[s['bucket']][0 if f['quality'] == 'IG' else 1]
        else:
            raise ValueError('class not needed by the cases')
        items.append((s['bucket'], f, rw * s['s_cva'] - rw * s['s_hdg'], rw * s['s_hdg']))

    def rho(a, b, bucket):
        if cls == 'IR' and kind == 'DELTA':
            spec = bucket in IR_SPEC or bucket == rep
            if a == b:
                return 1.0
            if not spec:
                return 0.4
            return IR_RHO.get((a, b)) or IR_RHO[(b, a)]
        if cls == 'IR':
            return 0.4
        if cls == 'CCS':
            tt = 1.0 if a['tenor'] == b['tenor'] else 0.9
            if a['name'] == b['name']:
                nn = 1.0
            elif a.get('legal_group') == b.get('legal_group'):
                nn = 0.9
            else:
                nn = 0.5
            qq = 1.0 if a['quality'] == b['quality'] else 0.8
            return tt * nn * qq
        return 1.0

    bks = {}
    for it in items:
        bks.setdefault(it[0], []).append(it)
    out = {}
    Kb = {}
    Sb = {}
    for b, its in bks.items():
        sws = sum(i[2] for i in its)
        rad = sum(i[2] ** 2 for i in its)
        for x in range(len(its)):
            for y in range(len(its)):
                if x != y:
                    rad += rho(its[x][1], its[y][1], b) * its[x][2] * its[y][2]
        rad += 0.01 * sum(i[3] ** 2 for i in its)
        fl = rad < 0
        k = math.sqrt(max(0.0, rad))
        s = max(-k, min(sws, k))
        out[b] = {'k_b': k, 's_b': s, 'sum_ws': sws, 'floored': fl}
        Kb[b] = k
        Sb[b] = s
    g = {'IR': 0.5, 'FX': 0.6}.get(cls)
    rad = sum(k * k for k in Kb.values())
    bl = list(Kb)
    for x in bl:
        for y in bl:
            if x != y:
                if g is None:
                    raise NotImplementedError('multi-bucket CCS')
                rad += g * Sb[x] * Sb[y]
    return out, rad


def cva_sa(inp):
    res = {'classes': {}}
    tot = 0.0
    for key, sens in inp['classes'].items():
        cls, kind = key.split('.')
        out, rad = sa_one(cls, kind, sens, inp['reporting_currency'])
        k = inp['m_cva'] * math.sqrt(max(0.0, rad))
        res['classes'][key] = {'buckets': out, 'k': k}
        tot += k
    res['total'] = tot
    res['rwa'] = 12.5 * tot
    return res


CCF = {'DIRECT_CREDIT_SUBSTITUTE': 1, 'FORWARD_PURCHASE': 1, 'OTHER_CREDIT_SUBSTITUTE': 1, 'NIF_RUF': .5,
       'TRANSACTION_CONTINGENT': .5, 'COMMITMENT': .4, 'TRADE_LC': .2, 'UNCONDITIONALLY_CANCELLABLE': .1}


def leverage(inp):
    ob = sum(inp['on_balance'])
    de = sum(1.4 * (max(d['v'] - d['cvm_received'] + d['cvm_provided'], 0) + d['pfe']) for d in inp['derivatives'])
    wc = sum(max(w['notional'] - max(0, -w['fair_value']) - w['purchased_offset'], 0)
             for w in inp['written_credit_derivatives'])
    sf = 0.0
    for s in inp['sfts']:
        sf += s['gross_assets']
        if s['mna']:
            sf += max(0, sum(s['exposures']) - sum(s['collateral']))
        else:
            sf += sum(max(0, e - c) for e, c in zip(s['exposures'], s['collateral']))
    of = sum(o['notional'] * CCF[o['ccf_category']] for o in inp['off_balance'])
    ex = ob + de + wc + sf + of
    return {'on_balance': ob, 'derivatives': de, 'written_credit_derivatives': wc, 'sfts': sf,
            'off_balance': of, 'exposure': ex, 'ratio': inp['tier1'] / ex,
            'meets_minimum': inp['tier1'] >= 0.03 * ex}


def lex(inp):
    T = inp['tier1']
    exp = {c['id']: 0.0 for c in inp['counterparties']}
    for b in inp['banking_book']:
        exp[b['counterparty']] += b['value']
    for o in inp['off_balance']:
        exp[o['counterparty']] += o['notional'] * max(o['ccf'], 0.10)
    tb = {}
    for p in inp['trading_book']:
        tb.setdefault(p['counterparty'], []).append((p['seniority'], gross_jtd(p, lgd_override=1.0)))
    for cp, items in tb.items():
        nl, ns = offset(items)
        exp[cp] += nl
    for c in inp['crm']:
        exp[c['counterparty']] -= c['protected']
        exp[c['provider']] += c['protected']
    grp = {}
    gs = {}
    for c in inp['counterparties']:
        g = c.get('group', c['id'])
        grp[g] = grp.get(g, 0.0) + exp[c['id']]
        gs.setdefault(g, []).append(c)
    res = {'groups': {}}
    for g, e in grp.items():
        both = inp['bank_gsib'] and all(c.get('gsib', False) for c in gs[g])
        lim = (0.15 if both else 0.25) * T
        ex = all(c.get('exempt', False) for c in gs[g])
        res['groups'][g] = {'exposure': e, 'share': e / T, 'large': e >= 0.10 * T, 'limit': lim,
                            'breach': (e > lim) and not ex}
    return res


OPS = {'risk.frtb.drc_nonsec': drc_nonsec, 'risk.frtb.drc_sec_nonctp': drc_sec, 'risk.frtb.drc_ctp': drc_ctp,
       'risk.frtb.rrao': rrao, 'risk.frtb.ima.es_lh': es_lh, 'risk.frtb.ima.es_stressed': est,
       'risk.frtb.ima.imcc': imcc, 'risk.frtb.ima.ses': ses, 'risk.frtb.ima.capital': cap,
       'risk.frtb.rfet': rfet, 'risk.cva.ba': cva_ba, 'risk.cva.sa': cva_sa,
       'risk.capital.leverage': leverage, 'risk.capital.large_exposures': lex}


def fill(skel, val):
    if isinstance(skel, dict):
        return {k: fill(v, val[k]) for k, v in skel.items()}
    if isinstance(skel, list):
        return [fill(v, val[i]) for i, v in enumerate(skel)]
    return val


def main():
    tpl = json.load(open(P + 'output_template.json'))
    skel = tpl['results_skeleton']['cases']
    allres = {}
    for f in ['K-8a', 'K-8f', 'K-8g', 'K-8i']:
        for c in json.load(open(P + 'inputs/%s.inputs.json' % f))['cases']:
            allres[c['case_id']] = OPS[c['operation']](c['inputs'])
    assert set(allres) == set(skel), set(allres) ^ set(skel)
    out = {'cases': {cid: fill(skel[cid], allres[cid]) for cid in skel}}
    json.dump(out, open(OUT + 'blind_results.json', 'w'), indent=1)
    print(len(out['cases']), 'cases')


main()
