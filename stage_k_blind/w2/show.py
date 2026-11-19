import json
d = json.load(open('C:/Work/Claude/qf-blind/k2_results/blind_results.json'))['cases']
for k in ['drc_k-0004', 'drc_k-0005', 'drc_k-0007', 'drc_k-0008', 'drc_k-0011', 'ctp_k-0002', 'ctp_k-0003',
          'sec_k-0001', 'es_k-0005', 'cap_k-0002', 'rfet_k-0001', 'rfet_k-0002', 'rfet_k-0003', 'rfet_k-0004',
          'cva_k-0004', 'cva_k-0006', 'sacva_k-0005', 'sacva_k-0004', 'lex_k-0004', 'lex_k-0003', 'lev_k-0010']:
    print(k, json.dumps(d[k]))
