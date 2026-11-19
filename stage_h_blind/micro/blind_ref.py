import json, hashlib
from decimal import Decimal as D, getcontext
from fractions import Fraction as F
getcontext().prec = 60
def sq(x): return x.sqrt()
def f(x): return float(x)
def ols0(x, y):
    n=len(x)
    if n<2: return 'E_INPUT'
    sxx=sum(a*a for a in x)
    if sxx==0: return 'E_INPUT'
    b=sum(a*c for a,c in zip(x,y))/sxx
    s2=sum((c-b*a)**2 for a,c in zip(x,y))/(n-1)
    return {'beta':f(b),'SE':f(sq(s2/sxx))}
def ols1(t,y):
    n=len(t)
    if n<3: return 'E_INPUT'
    mt=sum(t)/n; my=sum(y)/n
    stt=sum((a-mt)**2 for a in t)
    sl=sum((a-mt)*(c-my) for a,c in zip(t,y))/stt
    ic=my-sl*mt
    sse=sum((c-ic-sl*a)**2 for a,c in zip(t,y))
    if sse<D('1e-40'): se=D(0)   # exact fit (HR-74)
    else: se=sq(sse/(n-2)/stt)
    return -sl, se
def resil(sinf,pts):
    if any(s<=sinf for _,s in pts): return 'E_DOMAIN'
    r=ols1([D(t) for t,_ in pts],[(D(s)-D(sinf)).ln() for _,s in pts])
    if r=='E_INPUT': return r
    return {'kappa':f(r[0]),'SE':f(r[1])}
R={}
R['mest_h-0001']={'lambda':f(D(12)/4),'SE':f(sq(D(12)/4/4))}
R['mest_h-0002']='E_DOMAIN'
Ls=[(D(2),1),(D(3),0),(D(5),1)]; C=sum(c for _,c in Ls); th=D(C)/sum(l for l,_ in Ls)
R['mest_h-0003']={'theta':f(th),'SE':f(th/D(C).sqrt())}
R['mest_h-0004']='E_INPUT'
R['mest_h-0005']=resil(D(1),[(D(0),D(5)),(D(1),D(3)),(D(2),D(2))])
R['mest_h-0006']=resil(D(1),[(D(0),D(5)),(D(1),D('0.5'))])
r=ols1([D(k) for k in range(4)],[D(v).ln() for v in (800,400,200,100)])
R['mest_h-0007']={'alpha':f(r[0]),'SE':f(r[1])}
R['mest_h-0008']=ols0([D(1),D(-1),D(2)],[D('0.02'),D('-0.01'),D('0.05')])
c=ols0([D(1),D(2)],[D('0.01'),D('0.02')])
s=ols0([D(1),D(-1),D(1)],[D('0.05'),D('-0.03'),D('0.04')])
cb=D('0.01'); sb=D('0.12')/3
R['mest_h-0009']={'calm':c,'stressed':s,'ratio':f(sb/cb)}
def mv(v):
    n=len(v); m=sum(v)/n
    return m, sum((a-m)**2 for a in v)/(n-1)
def pva(p,a):
    if len(p)<2 or len(a)<2: return 'E_INPUT'
    mp,vp=mv(p); ma,va=mv(a)
    return {'delta':f(ma-mp),'SE':f(sq(va/len(a)+vp/len(p)))}
R['mest_h-0010']=pva([D(-1),D('-0.5'),D(0)],[D(1),D('1.5'),D(2)])
R['mest_h-0011']=pva([D(-1)],[D(1),D(2)])

# venue
mids=[(D(0),D('100.00')),(D(1),D('100.02')),(D(5),D('100.05')),(D(10),D('99.98'))]
fills=[('A',1,D(100),D('100.01'),D(0)),('A',-1,D(200),D('100.03'),D(1)),('B',1,D(300),D('100.00'),D(1))]
orders=[('A',D(500),D(300)),('B',D(300),D(300))]
def midat(u):
    m=None
    for t,v in mids:
        if t<=u: m=v
    if m is None: raise ValueError('E_INPUT')
    return m
def venue(fills,orders,hs,rates=False):
    for _,_,q,p,_ in fills:
        if q<=0 or p<=0: return 'E_DOMAIN'
    for _,sn,fl in orders:
        if sn<=0 or fl<0: return 'E_DOMAIN'
    for _,sn,fl in orders:
        if fl>sn: return 'E_INPUT'
    if any(h<0 for h in hs): return 'E_DOMAIN'
    out={}
    vs=sorted({x[0] for x in fills})
    try:
        for h in hs:
            for V in vs:
                fl=[x for x in fills if x[0]==V]
                sq_=sum(q for _,_,q,_,_ in fl)
                num=sum(s*q*(midat(t+h)-p) for _,s,q,p,t in fl)
                den=sum(q*p for _,_,q,p,_ in fl)
                tox=sum(q for _,s,q,p,t in fl if s*(midat(t+h)-p)<0)
                out[f'{V}|h={h}']={'markout':f(num/sq_),'markout_bps':f(D(10000)*num/den),'toxicity':f(tox/sq_)}
    except ValueError: return 'E_INPUT'
    if rates:
        for V in sorted({o[0] for o in orders}):
            o=[x for x in orders if x[0]==V]
            out[f'fill_rate|{V}']=f(sum(a for _,_,a in o)/sum(b for _,b,_ in o))
    return out
R['venue_h-0001']=venue(fills,orders,[D(5)])
R['venue_h-0002']=venue(fills,orders,[D(10)])
R['venue_h-0003']=venue(fills,orders,[D(0)])
R['venue_h-0004']=venue([],orders,[],True)
R['venue_h-0005']=venue(fills,[('A',D(500),D(600)),('B',D(300),D(300))],[D(5)])
R['venue_h-0006']=venue(fills+[('B',1,D(10),D(100),D(-1))],orders,[D(0)])
R['venue_h-0007']=venue(fills,orders,[D(-1)])
blob=json.dumps(R,indent=1,sort_keys=True)
open('blind_results.json','w').write(blob+'\n')
h=hashlib.sha256(open('blind_results.json','rb').read()).hexdigest()
open('blind_results.sha256','w').write(h+' *blind_results.json\n')
print(blob); print(h, len(R))
# alternatives for notes
print(venue(fills+[('B',1,D(10),D(100),D(-1))],orders,[D(5)]))
