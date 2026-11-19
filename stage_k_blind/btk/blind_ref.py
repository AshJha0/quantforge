import json
from fractions import Fraction
from math import comb
P = "C:/Work/Claude/qf-blind/btk_packet/"
MULT = [1.5,1.5,1.5,1.5,1.5,1.7,1.76,1.83,1.88,1.92]

def cdf(n, p, k):
    q = 1 - p
    return sum(comb(n, i) * p**i * q**(n-i) for i in range(k+1))

def first_from(n, thr):
    p = Fraction(1, 100); c = Fraction(0)
    q = 1 - p
    for k in range(n+1):
        c += comb(n, k) * p**k * q**(n-k)
        if c >= thr:
            return k
    return n

def zone(i):
    n = i["observations"]; x = max(i["exceptions_actual"], i["exceptions_hypothetical"])
    a = first_from(n, Fraction(95, 100)); r = first_from(n, Fraction(9999, 10000))
    z = "RED" if x >= r else "AMBER" if x >= a else "GREEN"
    m = None
    if n == 250:
        m = MULT[x] if x <= 9 else 2.0
    return dict(exceptions=x, cumulative_probability=float(cdf(n, Fraction(1,100), x)),
                zone=z, amber_from=a, red_from=r, multiplier=m)

def desk(i):
    n = i["observations"]
    x99 = max(i["exceptions_99_actual"], i["exceptions_99_hypothetical"])
    x975 = max(i["exceptions_975_actual"], i["exceptions_975_hypothetical"])
    b99 = x99 > 12; b975 = x975 > 30
    return dict(exceptions_99=x99, exceptions_975=x975,
                cumulative_probability_99=float(cdf(n, Fraction(1,100), x99)),
                cumulative_probability_975=float(cdf(n, Fraction(25,1000), x975)),
                breach_99=b99, breach_975=b975, eligible=not (b99 or b975))

def count(i):
    v, a, h = i["var"], i["actual"], i["hypothetical"]
    def days(pl):
        return [t for t in range(len(v)) if v[t] is None or pl[t] is None or -pl[t] > v[t]]
    da, dh = days(a), days(h)
    return dict(observations=len(v), exceptions_actual=len(da), exceptions_hypothetical=len(dh),
                exceptions=max(len(da), len(dh)), days_actual=da, days_hypothetical=dh)

ops = {"risk.frtb.backtest.zone": zone, "risk.frtb.backtest.desk": desk, "risk.frtb.backtest.count": count}
d = json.load(open(P + "inputs/btk.inputs.json"))
out = {"cases": {c["case_id"]: ops[c["operation"]](c["inputs"]) for c in d["cases"]}}
open("blind_results.json", "w").write(json.dumps(out, indent=1))
