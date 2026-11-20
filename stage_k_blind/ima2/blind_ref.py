import json, math, hashlib
from fractions import Fraction

def avg_ranks2(v):
    # doubled average ranks (integers): 2*r where r = average 1-based rank
    n = len(v); idx = sorted(range(n), key=lambda i: v[i]); r = [0]*n; i = 0
    while i < n:
        j = i
        while j+1 < n and v[idx[j+1]] == v[idx[i]]: j += 1
        # average of ranks i+1..j+1 = (i+j+2)/2 ; doubled = i+j+2
        for k in range(i, j+1): r[idx[k]] = i+j+2
        i = j+1
    return r

def spearman(h, t):
    n = len(h)
    a = [x-(n+1) for x in avg_ranks2(h)]; b = [x-(n+1) for x in avg_ranks2(t)]
    sxy = sum(x*y for x, y in zip(a, b)); sxx = sum(x*x for x in a); syy = sum(y*y for y in b)
    r = sxy/math.sqrt(sxx*syy)   # int*int exact, then float sqrt
    return max(-1.0, min(1.0, r)), sxy, sxx, syy

def ks_count(h, t):
    vals = sorted(set(h)|set(t)); hs = sorted(h); ts = sorted(t)
    import bisect
    return max(abs(bisect.bisect_right(ts, x)-bisect.bisect_right(hs, x)) for x in vals)

def qks(x):
    if x <= 0: return 1.0
    if x < 1:
        s = 0.0; k = 1
        while True:
            t = math.exp(-((2*k-1)**2)*math.pi**2/(8*x*x))
            if t == 0.0: break
            s += t; k += 1
        return 1.0 - math.sqrt(2*math.pi)/x*s
    s = 0.0; k = 1
    while True:
        t = math.exp(-2*k*k*x*x)
        if t == 0.0: break
        s += (-1)**(k-1)*t; k += 1
    return 2*s

def pla(h, t):
    n = len(h)
    r = spearman(h, t)[0]
    d = ks_count(h, t); ks = d/n
    rf = Fraction(r)  # exact value of binary64 r vs thresholds
    if r > 0.80 and 100*d < 9*n: z = "GREEN"
    elif r < 0.70 or 100*d > 12*n: z = "RED"
    else: z = "AMBER"
    return dict(spearman=r, ks=ks, ks_count=d, zone=z, ks_pvalue_asymptotic=qks(ks*math.sqrt(n/2)))

def probit(p):
    # solve 0.5*erfc(-z/sqrt2)=p by bisection then Newton
    lo, hi = 0.0, 10.0
    for _ in range(200):
        m = (lo+hi)/2
        if 0.5*math.erfc(-m/math.sqrt(2)) < p: lo = m
        else: hi = m
    z = (lo+hi)/2
    for _ in range(5):
        f = 0.5*math.erfc(-z/math.sqrt(2))-p
        z -= f/(math.exp(-z*z/2)/math.sqrt(2*math.pi))
    return z

def es_lh(sigma):
    z = probit(0.975); phi = math.exp(-z*z/2)/math.sqrt(2*math.pi)
    es = [s*phi/(1-0.975) for s in sigma]
    LH = [10, 20, 40, 60, 120]
    tot = es[0]**2
    for j in range(1, 5): tot += (es[j]*math.sqrt((LH[j]-LH[j-1])/10))**2
    return dict(es_by_horizon=es, es=math.sqrt(tot))

if __name__ == "__main__":
    inp = json.load(open("C:/Work/Claude/qf-blind/ima2_packet/inputs/ima2.inputs.json"))
    out = {"cases": {}}
    for c in inp["cases"]:
        i = c["inputs"]
        out["cases"][c["case_id"]] = pla(i["hpl"], i["rtpl"]) if c["operation"] == "risk.frtb.pla" else es_lh(i["sigma"])
    json.dump(out, open("blind_results.json", "w"), indent=1)
    print(json.dumps(out, indent=1)); print("z", repr(probit(0.975)))
