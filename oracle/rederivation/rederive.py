"""Independent re-derivation driver. Reads inputs/*.json, writes results.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cds, frtb, book, traffic

def load(name): return json.load(open(os.path.join(HERE, 'inputs', name)))

def run():
    res = []
    for r in load('cdsidx_f.json'):
        o = cds.cdsindex_option(r['inputs'])
        e = dict(case_id=r['case_id'], operation=r['operation'])
        if o.get('status'): e.update(o)
        else: e.update({k: o[k] for k in r['output_names']})
        e['basis'] = 'own-knowledge-of-paper'
        e['basis_note'] = ('Pedersen (2003) adjusted forward/strike derived from own knowledge and first principles; '
                           'paper not opened. Leg schedule, day counts, mid-date rule, strike-hazard solve are conventions '
                           'taken from the spec page (spec-only part).')
        res.append(e)
    for fn in ['frtb_f.json', 'frtb_f2b.json', 'frtb_f2c.json']:
        for r in load(fn):
            op = r['operation'].split('.')[-1]
            e = dict(case_id=r['case_id'], operation=r['operation'])
            try:
                o = getattr(frtb, op)(r['inputs'])
                e.update({k: o[k] for k in r['output_names']})
                e['basis'] = 'primary-text'
                e['basis_note'] = ('All parameters/formulas from Basel Framework MAR21 (PDF pp. 570-574, 592-618). '
                                   'binding_scenario tie-break (first of high, medium, low) is a convention not in MAR21.')
                if op == 'vega' and r['inputs']['risk_class'] == 'EQUITY':
                    a = frtb.vega(r['inputs'], rwf=frtb.vega_rw_unrounded)
                    e['alt_capital_unrounded_vega_rw'] = a['capital']
            except Exception as ex:
                e.update(status='could_not_derive', reason=str(ex), basis='primary-text')
            res.append(e)
    for r in load('book_f.json'):
        e = dict(case_id=r['case_id'], operation=r['operation'])
        o = book.lifecycle(r['inputs']) if r['operation'] == 'book.lifecycle.apply' else book.marks(r['inputs'])
        if 'error' in o: e.update(status='could_not_derive', reason='rule gives ' + o['error'])
        else: e.update({k: o[k] for k in r['output_names']})
        e['basis'] = 'spec-only'
        e['basis_note'] = 'independent implementation from the spec by a different model; no primary source'
        res.append(e)
    for r in load('risk_f4.json'):
        o = traffic.traffic_light(r['inputs'])
        e = dict(case_id=r['case_id'], operation=r['operation'])
        e.update({k: o[k] for k in r['output_names']})
        e['basis'] = 'primary-text'
        e['basis_note'] = 'MAR32.9 Table 1, MAR99.9-99.17 Table 2, MAR33.42. plus_factor = multiplier - 1.5; null where the PDF gives no table (n != 250 or confidence != 99%).'
        if r['inputs']['observations'] == 250 and abs(r['inputs']['confidence'] - 0.99) < 1e-12:
            spec_scale = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0.40, 6: 0.50, 7: 0.65, 8: 0.75, 9: 0.85}
            e['spec_page_reading_plus_factor_NOT_FROM_PRIMARY'] = spec_scale.get(r['inputs']['exceptions'], 1.00)
        res.append(e)
    return res

if __name__ == '__main__':
    res = run()
    json.dump(res, open(os.path.join(HERE, 'results.json'), 'w'), indent=1)
    import collections
    print(len(res), collections.Counter(x['basis'] for x in res), sum(1 for x in res if x.get('status')))
