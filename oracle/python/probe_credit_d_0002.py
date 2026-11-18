"""credit_d-0002 probe (2026-11-18): QuantLib ISDA reprice gap at the Saturday 5Y pillar. Run from oracle/python.
Prints the gap, its linearity in the hazard jump at the 5Y pillar, and that it vanishes when the 5Y node moves one day later."""
import sys,json,glob,math
sys.path.insert(0,'.')
import outside_d as O, QuantLib as ql
from datetime import date, timedelta
c=[c for f in glob.glob('../../datasets/golden/stage_d/credit*.json') for c in json.load(open(f))['cases'] if c['case_id']=='credit_d-0002'][0]
i=c['inputs'];pil=c['expected']['outputs']['pillars']
def run(pillars, mat, coupon, bias=ql.IsdaCdsEngine.NoBias, fwd=ql.IsdaCdsEngine.Piecewise, acc=ql.IsdaCdsEngine.Taylor):
    T=O.D(i['trade_date']); ql.Settings.instance().evaluationDate=O.Q(T)
    u=O.Used(); disc,_=O.curve(u,i['discount']); disc.enableExtrapolation()
    dates,hz,pt,pl=[O.Q(T)],[],0.0,0.0
    for p in pillars:
        t=(O.D(p['date'])-T).days/365; lq=-math.log(p['survival']); hz.append((lq-pl)/(t-pt)); dates.append(O.Q(O.D(p['date']))); pt,pl=t,lq
    hc=ql.HazardRateCurve(dates,[hz[0]]+hz,ql.Actual365Fixed()); hc.enableExtrapolation()
    cal=ql.WeekendsOnly()
    sch=ql.Schedule(O.Q(T),O.Q(O.D(mat)),ql.Period(3,ql.Months),cal,ql.Following,ql.Unadjusted,ql.DateGeneration.CDS2015,False)
    cd=ql.CreditDefaultSwap(ql.Protection.Buyer,1.0,0.0,coupon,sch,ql.Following,ql.Actual360(),True,True,O.Q(T)+1,cal.advance(O.Q(T),3,ql.Days),ql.FaceValueClaim(),ql.Actual360(True),True,O.Q(T),3)
    cd.setPricingEngine(ql.IsdaCdsEngine(ql.DefaultProbabilityTermStructureHandle(hc),i['recovery'],ql.YieldTermStructureHandle(disc),False,acc,bias,fwd))
    return cd.fairSpread()-coupon, cd, hz
e,cd,hz=run(pil,'2031-12-20',0.048); print('base',e, 'hazards',hz)

print('Flat fwd',run(pil,'2031-12-20',0.048,fwd=ql.IsdaCdsEngine.Flat)[0])
print('HalfDayBias',run(pil,'2031-12-20',0.048,bias=ql.IsdaCdsEngine.HalfDayBias)[0])
print('Exact acc',run(pil,'2031-12-20',0.048,acc=ql.IsdaCdsEngine.TaylorAndSum if hasattr(ql.IsdaCdsEngine,'TaylorAndSum') else ql.IsdaCdsEngine.Taylor)[0])
# drop pillars after 5Y: is the error from the segment beyond the pillar?
print('only to 5Y',run(pil[:4],'2031-12-20',0.048)[0])
# make 7Y hazard equal to 5Y hazard
T=O.D(i['trade_date'])
t5=(O.D(pil[3]['date'])-T).days/365; t7=(O.D(pil[4]['date'])-T).days/365
S5=pil[3]['survival']
for k in [0,0.5,1,2,4]:
    h7=hz[3]+k*(hz[4]-hz[3])
    p2=[dict(p) for p in pil[:4]]+[{'date':pil[4]['date'],'survival':S5*math.exp(-h7*(t7-t5))}]
    print('jump x',k, run(p2,'2031-12-20',0.048)[0])
for extra in [1,2]:
    d=(O.D(pil[3]['date'])+timedelta(extra)).isoformat()
    p2=[dict(p) for p in pil]; p2[3]={'date':d,'survival':S5*math.exp(-hz[3]*extra/365)}
    print('5Y node moved +%d day'%extra, run(p2,'2031-12-20',0.048)[0])
