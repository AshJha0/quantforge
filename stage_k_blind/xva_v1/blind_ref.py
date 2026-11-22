import json
from mpmath import mp, mpf, exp, sqrt, npdf, ncdf, erfinv, findroot
mp.dps = 60
def F(x): return float(x)
def D(t): return exp(-mpf('0.03')*mpf(t))
def P(x): return mpf(x)
def invphi(q):
    q=mpf(q); return sqrt(2)*erfinv(2*q-1)
def phi(x): return exp(-x*x/2)/sqrt(2*mp.pi)
def Phi(x): return ncdf(x)
R={}
# ColVA
T=[P(x) for x in ('0','0.5','1','1.5','2')]
def colva(C,Delta,W_h=None,r=None):
    tot=P(0); fl=P(0)
    for i in range(4):
        d=T[i+1]-T[i]; De=Delta[i] if isinstance(Delta,list) else Delta
        w=exp(-(W_h)*T[i+1]) if W_h else 1
        tot-=P(C[i])*P(De)*d*D(T[i+1])*w
        if r: fl-=P(C[i])*max(-P(r[i]),0)*d*D(T[i+1])*w
    return tot,fl
C=[100,80,50,20]
R['colva_k-0001']={'colva':F(colva(C,'0.001')[0])}
R['colva_k-0002']={'colva':F(colva(C,'0.001',P('0.03'))[0])}
c,f=colva(C,'0.001',None,['-0.005','0','0.01','-0.002'])
R['colva_k-0003']={'colva':F(c),'collateral_floor':F(f)}
# MVA
tm=[P(x) for x in ('0.5','1','1.5','2')]
df=[P(x) for x in ('0.985','0.97','0.955','0.94')]
hC,hB=P('0.02'),P('0.01'); fb=P('0.008'); sI=P('0.001')
def mva(IM):
    s=P(0);prev=P(0)
    for i in range(4):
        d=tm[i]-prev; prev=tm[i]
        s+=(fb-sI)*d*exp(-(hC+hB)*tm[i])*df[i]*P(IM[i])
    return s
R['mva_k-0001']={'mva':F(mva(['100','90','70','40']))}
k=invphi('0.99')*sqrt(P(10)/250)
IM=[k*P(s) for s in (1000,1200,900,500)]
R['mva_k-0002']={'mva':F(mva(IM))}
# regression
x=[P(v) for v in ('-1','-0.5','0','0.5','1','1.5')]; X=[P(v) for v in (3,-2,1,-1,2,-4)]
import mpmath
n=6
A=mpmath.matrix([[1,xi] for xi in x]); y=mpmath.matrix([Xi**2 for Xi in X])
beta=mpmath.lu_solve(A.T*A,A.T*y)
mX=sum(X)/n
q=invphi('0.99')
ims=[q*sqrt(max(beta[0]+beta[1]*xi-mX**2,0)) for xi in x]
R['mva_k-0003']={'expected_im':F(sum(ims)/n)}
# stressed
def eepe(ee,grid,Ts=1):
    e=P(0);s=P(0)
    for k in range(len(ee)):
        e=P(ee[k]) if k==0 else max(e,P(ee[k]))
        if k>0 and grid[k]<=Ts: s+=e*(grid[k]-grid[k-1])
    return s/Ts
g=[P(v) for v in ('0','0.25','0.5','0.75','1')]
al=P('1.4')
def strcase(wA,alpha=al):
    A=(( [10,14,12,15,11],[10,20,24,22,18],P(wA)))
    B=(( [20,18,22,19,16],[20,16,15,14,12],P('0.04')))
    o={}
    ec={};es={};ed={}
    for n_,(c,s,w) in (('A',A),('B',B)):
        ec[n_]=eepe(c,g);es[n_]=eepe(s,g)
    Kc=sum(alpha*ec[n_]*w for n_,w in (('A',A[2]),('B',B[2])))
    Ks=sum(alpha*es[n_]*w for n_,w in (('A',A[2]),('B',B[2])))
    cal='stressed' if Ks>Kc else 'current'
    used={n_:alpha*(es[n_] if cal=='stressed' else ec[n_]) for n_ in 'AB'}
    return ec,es,Kc,Ks,cal,used
ec,es,Kc,Ks,cal,used=strcase('0.08')
R['str_k-0001']={'eepe_current_A':F(ec['A']),'eepe_stressed_A':F(es['A']),'eepe_current_B':F(ec['B']),'eepe_stressed_B':F(es['B']),'ead_used_A':F(used['A']),'ead_used_B':F(used['B']),'k_current':F(Kc),'k_stressed':F(Ks),'calibration':cal}
ec,es,Kc,Ks,cal,used=strcase('0.004')
R['str_k-0002']={'k_current':F(Kc),'k_stressed':F(Ks),'calibration':cal,'ead_used_A':F(used['A']),'ead_used_B':F(used['B'])}
R['str_k-0003']={'calibration':'current'}
h=P('0.5')
R['str_k-0004']={'eepe_current':F(eepe([10,12,9,0,0],g,h)),'eepe_stressed':F(eepe([10,15,11,0,0],g,h))}
# mpor
def mp_(repo,n,ill,disp,N):
    Fv=5 if repo else 10
    if n>5000 or ill: Fv=20
    if disp>2: Fv*=2
    return Fv+N-1
R['mpor_k-0001']={'floor':mp_(True,10,False,0,1)}
R['mpor_k-0002']={'floor':mp_(False,10,False,0,1)}
R['mpor_k-0003']={'floor':mp_(False,10,False,0,5)}
R['mpor_k-0004']={'floor':mp_(False,6000,False,0,1)}
R['mpor_k-0005']={'floor':mp_(False,10,False,3,1)}
fl=mp_(False,10,True,3,3)
R['mpor_k-0006']={'floor':fl,'mpor_days':max(15,fl),'binding':fl>=15}
# fva
def interp_st(tenors,sp,t):
    # s(T)*T by linear interpolation in T, 0 at origin, flat forward (s*T extended with last-pillar forward... see notes)
    pts=[(P(0),P(0))]+[(P(a),P(b)*P(a)) for a,b in zip(tenors,sp)]
    t=P(t)
    for (a,u),(b,v) in zip(pts,pts[1:]):
        if t<=b: return u+(v-u)*(t-a)/(b-a)
    (a,u),(b,v)=pts[-2],pts[-1]
    if len(pts)>=3:
        return v+(v-u)/(b-a)*(t-b)
    return v+(v/b)*(t-b)
def fva(times,ee,ene,bc,lc,hC,hB,RB,excl=False):
    times=[P(t) for t in times]; fca=P(0);fba=P(0);prev=P(0)
    for i,t in enumerate(times):
        d=t-prev
        fb_=(interp_st(*bc,t)-interp_st(*bc,prev))/d
        fl_=(interp_st(*lc,t)-interp_st(*lc,prev))/d
        if excl: fl_=max(fl_-P(hB)*(1-P(RB)),0)
        w=exp(-(P(hC)+P(hB))*prev)*D(t)
        fca+=fb_*d*w*P(ee[i]); fba+=fl_*d*w*abs(P(ene[i]))
        prev=t
    return fca,fba
bc=([1,2],['0.010','0.012']); lc=([1,2],['0.004','0.005'])
a,b=fva([1,2],[10,6],[-4,-8],bc,lc,'0.02','0.01','0.4')
R['fva_k-0001']={'fca':F(a),'fba':F(b),'fva':F(a-b)}
a,b=fva([1,2],[10,6],[-4,-8],bc,lc,'0.02','0.01','0.6',True)
R['fva_k-0002']={'fba':F(b)}
R['fva_k-0003']={'fca':None,'fba':None}
R['fva_k-0006']={'fca':None}
R['aadx_k-0001']={k_:None for k_ in ("d_cva_d_h_c","d_cva_d_r_c","d_cva_d_h_b","d_fca_d_s_b","d_cva_d_ee[1]")}
# colva_k-0003 etc fine; cln not in template
tmpl=json.load(open('../xva_v1_packet/template.json'))
out={}
for k_,v in tmpl.items():
    out[k_]={f:R[k_][f] for f in v}
json.dump(out,open('blind_results.json','w'),indent=1)
print(json.dumps(out,indent=1))
