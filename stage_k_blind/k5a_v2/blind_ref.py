import json, math
from fractions import Fraction
from decimal import Decimal, getcontext
getcontext().prec = 80
LABEL = "latency-aware analytics on simulated data"
P = "C:/Work/Claude/qf-blind/k5a_v2_packet/inputs/K-5a.inputs.json"

def compute(positions, h):
    terms, Ls, rhos = [], [], []
    ah = abs(h)
    for p in positions:
        N, T, y = p["notional"], p["maturity"], p["yield"]
        v = N * math.exp(-y * T)
        a = -T * h
        b = ((T * T) * h) * h / 2
        terms.append(v * (a + b))
        e = math.exp(-T * min(y, y + h))
        L = ((ah * ah) * ah) * (((T * T) * T) * abs(N) * e) / 6
        g = abs(math.expm1(-h * T))
        rho = 2.0**-49 * (1 + T * abs(y) + T * ah) * (abs(v) * (T * ah + (T * T) * (h * h) + g) + L)
        Ls.append(L); rhos.append(rho)
    return math.fsum(terms), math.fsum(Ls + rhos)

def exact_reval(positions, h):
    s = Decimal(0)
    for p in positions:
        N, T, y = Decimal(p["notional"]), Decimal(p["maturity"]), Decimal(p["yield"])
        H = Decimal(h)
        s += N * ((-(y + H) * T).exp() - (-y * T).exp())
    return s

if __name__ == "__main__":
    d = json.load(open(P))
    out = {"cases": {}}
    chk = []
    for c in d["cases"]:
        pos, h = c["inputs"]["positions"], c["inputs"]["shift"]
        est, bd = compute(pos, h)
        out["cases"][c["case_id"]] = {"estimate_pnl": est, "bound": bd, "label": LABEL}
        diff = abs(Decimal(est) - exact_reval(pos, h))
        chk.append((c["case_id"], est, bd, float(diff), Decimal(bd) >= diff))
    json.dump(out, open("blind_results.json", "w"), indent=1)
    for r in chk: print(r)
