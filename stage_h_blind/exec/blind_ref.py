import json, math, sys
from fractions import Fraction as F
PK = "/mnt/c/Work/Claude/institutional-quant-engine-plan/stage_h_blind/exec_packet/"
class Err(Exception): pass
def fr(x):
    if isinstance(x, bool) or not isinstance(x,(int,float)) or (isinstance(x,float) and not math.isfinite(x)): raise Err("E_DOMAIN")
    return F(str(x)) if isinstance(x,float) else F(x)
def fl(x): return float(x)
def floor_half(x): return math.floor(x + F(1,2))
def twap(X, N, units):
    if units:
        q, r = divmod(int(X), N); return [F(q + (1 if i < r else 0)) for i in range(N)]
    return [X / N] * N
def vwap(X, w, units):
    s = sum(w)
    if s == 0: raise Err("E_DOMAIN")
    ex = [X * wi / s for wi in w]
    if not units: return ex
    fl_ = [math.floor(e) for e in ex]; rem = int(X) - sum(fl_)
    order = sorted(range(len(w)), key=lambda i: (-(ex[i] - fl_[i]), i))
    for i in order[:rem]: fl_[i] += 1
    return [F(v) for v in fl_]
def check_units(X, units):
    if units and X.denominator != 1: raise Err("E_INPUT")
def arrival(i):
    X = fr(i["quantity"]); N = i["n_buckets"]; k = fr(i["urgency"]); units = i.get("mode","CONTINUOUS") == "UNITS"
    if not isinstance(N,int) or N < 1: raise Err("E_INPUT")
    if X <= 0: raise Err("E_INPUT")
    if k < 0: raise Err("E_DOMAIN")
    check_units(X, units)
    kf = float(k)
    if k == 0: C = [X * j / N for j in range(N+1)]
    else:
        den = math.sinh(kf * N)
        C = [X - F(float(X) * math.sinh(kf*(N-j)) / den) for j in range(N+1)]
        C[0] = F(0); C[N] = X
    if units:
        C = [floor_half(c) for c in C]; C[N] = int(X); C[0] = 0
        return {"slices": [int(C[j]-C[j-1]) for j in range(1,N+1)]}
    return {"slices": [fl(C[j]-C[j-1]) for j in range(1,N+1)]}
def close(i):
    X = fr(i["quantity"]); V = fr(i["close_volume"]); p = fr(i["auction_participation"]); w = [fr(v) for v in i["profile"]]
    units = i.get("mode","CONTINUOUS") == "UNITS"
    if p < 0 or p > 1 or V < 0: raise Err("E_DOMAIN")
    if len(w) == 0: raise Err("E_INPUT")
    if any(v < 0 for v in w): raise Err("E_DOMAIN")
    if X <= 0: raise Err("E_INPUT")
    check_units(X, units)
    A = p * V
    if units: A = F(math.floor(A))
    A = min(X, A); rem = X - A
    if rem == 0: sl = [F(0)]*len(w)
    else: sl = vwap(rem, w, units)
    cv = (lambda v: int(v)) if units else fl
    return {"auction_quantity": cv(A), "slices": [cv(s) for s in sl]}
def lseek(i):
    side = i["side"]; X = fr(i["quantity"]); L = fr(i["limit_price"]); a = fr(i["take_fraction"]); books = i["books"]
    if side not in ("BUY","SELL"): raise Err("E_INPUT")
    if a <= 0 or a > 1 or L <= 0: raise Err("E_DOMAIN")
    if X <= 0: raise Err("E_INPUT")
    buy = side == "BUY"
    bk = []
    for b in books:
        lv = []
        for pr, sz in b:
            pr = fr(pr); sz = fr(sz)
            if pr <= 0: raise Err("E_DOMAIN")
            if sz <= 0: raise Err("E_INPUT")
            lv.append((pr, sz))
        for u, v in zip(lv, lv[1:]):
            if (buy and not v[0] > u[0]) or (not buy and not v[0] < u[0]): raise Err("E_INPUT")
        bk.append(lv)
    if not bk: raise Err("E_INPUT")
    R = X; sl = []; av = []; notional = F(0)
    for lv in bk:
        ins = [(p,s) for p,s in lv if (p <= L if buy else p >= L)]
        A = sum(s for _,s in ins); c = min(R, a*A); left = c; cost = F(0)
        for p,s in ins:
            t = min(left, s); cost += t*p; left -= t
            if left == 0: break
        sl.append(c); av.append(cost/c if c > 0 else None); notional += cost; R -= c
    filled = sum(sl)
    return {"slices": [fl(c) for c in sl], "avg_prices": [None if v is None else fl(v) for v in av],
            "filled": fl(filled), "residual": fl(X - filled), "notional": fl(notional),
            "avg_fill_price": None if filled == 0 else fl(notional/filled)}
def sgn(s):
    if s == "BUY": return 1
    if s == "SELL": return -1
    raise Err("E_INPUT")
def pair(i):
    A = i["leg_a"]; B = i["leg_b"]; pm = i["pair_mode"]; N = i["n_buckets"]; units = i.get("mode","CONTINUOUS") == "UNITS"
    XA = fr(A["quantity"]); PA = fr(A["price"]); PB = fr(B["price"]); sA = sgn(A["side"]); sB = sgn(B["side"])
    if pm == "CASH_BALANCED":
        if sA == sB: raise Err("E_INPUT")
    elif pm == "HEDGED":
        h = fr(i["hedge_ratio"])
        if h <= 0: raise Err("E_DOMAIN")
    else: raise Err("E_INPUT")
    if PA <= 0 or PB <= 0: raise Err("E_DOMAIN")
    if not isinstance(N,int) or N < 1: raise Err("E_INPUT")
    if XA <= 0: raise Err("E_INPUT")
    check_units(XA, units)
    r = PA/PB if pm == "CASH_BALANCED" else h
    a = twap(XA, N, units); CA = []; t = F(0)
    for v in a: t += v; CA.append(t)
    CB = [floor_half(r*c) if units else r*c for c in CA]
    b = [CB[0]] + [CB[j]-CB[j-1] for j in range(1,N)]
    cash = [sA*CA[j]*PA + sB*CB[j]*PB for j in range(N)]
    cv = (lambda v: int(v)) if units else fl
    return {"slices_a": [cv(v) for v in a], "slices_b": [cv(v) for v in b], "quantity_b": cv(CB[-1]),
            "cash_imbalance": [fl(c) for c in cash]}
def basket(i):
    legs = i["legs"]; N = i["n_buckets"]; units = i.get("mode","CONTINUOUS") == "UNITS"
    if len(legs) == 0: raise Err("E_INPUT")
    if not isinstance(N,int) or N < 1: raise Err("E_INPUT")
    for l in legs:
        if fr(l["price"]) <= 0: raise Err("E_DOMAIN")
    sls = []; cash = [F(0)]*N; gross = F(0)
    for l in legs:
        X = fr(l["quantity"]); P = fr(l["price"]); s = sgn(l["side"])
        if X <= 0: raise Err("E_INPUT")
        check_units(X, units)
        sl = twap(X, N, units); sls.append(sl); gross += X*P; c = F(0)
        for j in range(N): c += sl[j]; cash[j] += s*c*P
    cv = (lambda v: int(v)) if units else fl
    return {"slices": [[cv(v) for v in sl] for sl in sls], "cash_imbalance": [fl(c) for c in cash], "gross_notional": fl(gross)}
def pretrade(i):
    X = fr(i["quantity"]); adv = fr(i["adv"]); sg = fr(i["daily_vol"]); p = fr(i["participation"]); hs = fr(i["half_spread_bps"]); pr = i["params"]
    a1,a2,a3,a4,b1 = [float(pr[k]) for k in ("a1","a2","a3","a4","b1")]
    P = i.get("price")
    if X <= 0: raise Err("E_INPUT")
    if adv <= 0 or sg < 0 or p <= 0 or p >= 1 or hs < 0 or a1 <= 0 or b1 < 0 or b1 > 1: raise Err("E_DOMAIN")
    if P is not None and fr(P) <= 0: raise Err("E_DOMAIN")
    if sg == 0 and a3 <= 0: raise Err("E_DOMAIN")
    x, s, pf = float(X/adv), float(sg), float(p)
    ist = a1 * x**a2 * (s**a3 if s > 0 else 0.0)
    imp = b1*ist*pf**a4 + (1-b1)*ist
    spread = float(hs); T = float(X/(p*adv))
    tr = 1e4*s*math.sqrt(T/3)
    out = {"istar_bps": ist, "impact_bps": imp, "spread_bps": spread, "expected_cost_bps": spread+imp,
           "duration_days": T, "timing_risk_bps": tr}
    if P is not None:
        Pf = float(P); out["expected_cost"] = (spread+imp)*float(X)*Pf/1e4; out["timing_risk"] = tr*float(X)*Pf/1e4
    return out
def attribution(i):
    s = sgn(i["side"]); Pd = fr(i["decision_price"]); m0 = fr(i["arrival_mid"]); Pc = fr(i["end_price"]); X = fr(i["order_quantity"])
    fills = i["fills"]; fees = fr(i["fees"])
    if X <= 0: raise Err("E_INPUT")
    for f in fills:
        if fr(f["quantity"]) <= 0: raise Err("E_INPUT")
    Q = sum((fr(f["quantity"]) for f in fills), F(0))
    if Q > X: raise Err("E_INPUT")
    for v in [Pd,m0,Pc] + [fr(f[k]) for f in fills for k in ("price","mid")]:
        if v <= 0: raise Err("E_DOMAIN")
    delay = s*Q*(m0-Pd)
    imp = s*sum((fr(f["quantity"])*(fr(f["mid"])-m0) for f in fills), F(0))
    spr = s*sum((fr(f["quantity"])*(fr(f["price"])-fr(f["mid"])) for f in fills), F(0))
    opp = s*(X-Q)*(Pc-Pd)
    tot = delay+imp+spr+opp+fees
    return {"delay": fl(delay), "impact": fl(imp), "spread": fl(spr), "execution": fl(imp+spr), "opportunity": fl(opp),
            "fees": fl(fees), "total": fl(tot), "total_bps": fl(tot/(X*Pd)*10000)}
OPS = {"exec.algo.arrival":arrival,"exec.algo.close":close,"exec.algo.liquidity_seek":lseek,"exec.algo.pair":pair,
       "exec.algo.basket":basket,"exec.tca.pretrade":pretrade,"exec.tca.attribution":attribution}
res = {}
for fn in ("alg_h.inputs.json","tcx_h.inputs.json"):
    for c in json.load(open(PK+fn))["cases"]:
        try: res[c["case_id"]] = OPS[c["operation"]](c["inputs"])
        except Err as e: res[c["case_id"]] = {"error": str(e)}
json.dump(res, open("blind_results.json","w"), indent=1, sort_keys=True)
print(len(res))
