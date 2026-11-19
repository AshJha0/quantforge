import json, sys
from decimal import Decimal as D, getcontext
from fractions import Fraction as F
getcontext().prec = 50
LABEL = "simulated venue; not a real exchange; no real rates data"
Q = {'': F(0), '0': F(0), '2': F(1,4), '5': F(1,2), '+': F(1,2), '7': F(3,4)}
def err(c): return {"status": "error", "error_code": c}
def dec(fr):
    return D(fr.numerator) / D(fr.denominator)
def parse(text):
    h, _, r = text.partition('-')
    if not h.lstrip('-').isdigit() or len(r) < 2 or not r[:2].isdigit(): raise ValueError("E_SCHEMA")
    ff = int(r[:2]); t = r[2:]
    if ff > 31 or t not in Q: raise ValueError("E_SCHEMA")
    return F(int(h)) + (ff + Q[t]) / 32
DEF = {"ZN": (D(100000), F(1,64)), "ZB": (D(100000), F(1,32))}
def contract(c):
    s = c.get("symbol"); f, t = DEF.get(s, (None, None))
    if "face" in c: f = D(c["face"])
    if "tick" in c: t = F(D(c["tick"]))
    return f, t
def tv(face, tick): return face * dec(tick) / 100
def ticks(price, tick):
    x = price / tick
    if x.denominator != 1: raise ValueError("E_DOMAIN")
    return int(x)
def brent(f, a, b, tol=1e-12):
    fa, fb = f(a), f(b)
    if fa * fb > 0: raise ValueError("E_DOMAIN")
    if abs(fa) < abs(fb): a, b, fa, fb = b, a, fb, fa
    c, fc, d, mflag = a, fa, b, True
    for _ in range(500):
        if fb == 0 or abs(b - a) < tol: return b
        if fa != fc and fb != fc:
            s = a*fb*fc/((fa-fb)*(fa-fc)) + b*fa*fc/((fb-fa)*(fb-fc)) + c*fa*fb/((fc-fa)*(fc-fb))
        else: s = b - fb*(b-a)/(fb-fa)
        lo, hi = sorted(((3*a+b)/4, b))
        if (not lo < s < hi) or (mflag and abs(s-b) >= abs(b-c)/2) or (not mflag and abs(s-b) >= abs(c-d)/2) \
           or (mflag and abs(b-c) < tol) or (not mflag and abs(c-d) < tol):
            s = (a+b)/2; mflag = True
        else: mflag = False
        fs = f(s); d, c, fc = c, b, fb
        if fa*fs < 0: b, fb = s, fs
        else: a, fa = s, fs
        if abs(fa) < abs(fb): a, b, fa, fb = b, a, fb, fa
    return b
def run(op, i):
    if op == "micro.rates.parse_32nds": return {"value": str(dec(parse(i["text"])))}
    if op == "micro.rates.tick_value": return {"tick_value": str(tv(D(i["face"]), F(D(i["tick"]))))}
    if op == "micro.rates.bond_yield":
        c, f, n, p = float(i["coupon"]), i["frequency"], i["periods"], float(i["price"])
        def g(y):
            return sum((100*c/f)/(1+y/f)**k for k in range(1, n+1)) + 100/(1+y/f)**n - p
        return {"yield": brent(g, 1e-9, 1.0) if g(1e-9)*g(1.0) <= 0 else brent(g, -0.5, 10.0)}
    face, tick = contract(i["contract"]); v = tv(face, tick)
    if op == "exec.sim.fut.pnl":
        tb = ticks(parse(i["buy_price"]), tick); ts = ticks(parse(i["sell_price"]), tick)
        q = i["qty"]; fees = D(i["fee_per_contract"]) * (2*q)
        return {"pnl": str((ts - tb) * q * v - fees), "fees": str(fees), "label": LABEL}
    if op == "exec.sim.fut.variation":
        sg = 1 if i["side"].upper() == "BUY" else -1
        prev = ticks(parse(i["price"]), tick); out = []
        for s in i["settlements"]:
            t = ticks(parse(s), tick); out.append(str(sg * (t - prev) * i["qty"] * v)); prev = t
        return {"variation_margin": out, "label": LABEL}
    raise ValueError("E_SCHEMA")
inp = json.load(open("C:/Work/Claude/institutional-quant-engine-plan/stage_h_blind/rates2_packet/inputs.json".replace("C:", "/mnt/c")))
res = {}
for k, c in inp.items():
    try: res[k] = run(c["operation"], c["inputs"])
    except ValueError as e: res[k] = err(str(e))
json.dump(res, open("blind_results.json", "w"), indent=1, sort_keys=True)
print(json.dumps(res, indent=1))
