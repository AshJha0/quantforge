import json, math
P='C:/Work/Claude/qf-blind/k5a_packet/'
LABEL="latency-aware analytics on simulated data"
def calc(pos,h):
    est=[];bd=[]
    for p in pos:
        N,T,y=p['notional'],p['maturity'],p['yield']
        V=N*math.exp(-y*T)
        est.append(V*(-T*h)+V*(T*T)*(h*h)/2.0)
        M3=T**3*abs(N)*math.exp(-T*min(y,y+h))
        bd.append(abs(h)**3*M3/6.0)
    return math.fsum(est),math.fsum(bd)
inp=json.load(open(P+'inputs/K-5a.inputs.json'))
out={"cases":{}}
for c in inp['cases']:
    e,b=calc(c['inputs']['positions'],c['inputs']['shift'])
    out['cases'][c['case_id']]={"estimate_pnl":e,"bound":b,"label":LABEL}
    # sanity vs exact revaluation
    r=math.fsum(p['notional']*(math.exp(-(p['yield']+c['inputs']['shift'])*p['maturity'])-math.exp(-p['yield']*p['maturity'])) for p in c['inputs']['positions'])
    print(c['case_id'],repr(e),repr(b),'|err|',abs(e-r),abs(e-r)<=b)
json.dump(out,open('blind_results.json','w'),indent=1)
