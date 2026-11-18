import json, re, math
from fractions import Fraction as F
from decimal import Decimal as D, getcontext
getcontext().prec = 60

def dec(x): return D(repr(x)) if not isinstance(x, int) else D(x)

def ac(X, T, N, sigma, eps, eta, gamma, lam):
    X, T, sigma, eps, eta, gamma, lam = map(dec, (X, T, sigma, eps, eta, gamma, lam))
    tau = T / N
    et = eta - gamma * tau / 2
    if et <= 0: raise ValueError("E_DOMAIN")
    if lam == 0:
        x = [X * (N - j) / N for j in range(N + 1)]
        kappa = D(0)
    else:
        y = lam * sigma**2 * tau**2 / (2 * et)
        kt = (y + (y * (y + 2)).sqrt()).ln_1p() / tau if hasattr(D, 'ln_1p') else (1 + y + (y * (y + 2)).sqrt()).ln() / tau
        kappa = kt
        sh = lambda a: (a.exp() - (-a).exp()) / 2
        den = sh(kappa * T)
        x = [X * sh(kappa * (T - j * tau)) / den for j in range(N + 1)]
    n = [x[k - 1] - x[k] for k in range(1, N + 1)]
    E = gamma * X**2 / 2 + eps * X + et / tau * sum(v * v for v in n)
    V = sigma**2 * tau * sum(v * v for v in x[1:])
    return n, E, V

def dtof(d): return F(d)  # Decimal -> Fraction exact

def largest_remainder(X, weights):
    tot = sum(weights)
    ex = [X * w / tot for w in weights]
    fl = [e.__floor__() for e in ex]
    rem = X - sum(fl)
    order = sorted(range(len(ex)), key=lambda i: (-(ex[i] - fl[i]), i))
    for i in order[:rem]: fl[i] += 1
    return fl

def run(c):
    X = c["quantity"]
    n, E, V = ac(X, c["horizon"], c["n_steps"], c["sigma"], c["epsilon"], c["eta"], c["gamma"], c["risk_aversion"])
    if c["risk_aversion"] == 0:
        w = [F(int(X), c["n_steps"])] * c["n_steps"]   # exact linear trades
    else:
        w = [F(v) for v in n]
    lots = largest_remainder(int(X), w)
    k = c["completed_steps"]
    fp = [F(str(p)) for p in c["fill_prices"]]
    filled = sum(lots[:k])
    fees = F(str(c["fee_per_unit"])) * filled
    s = 1 if c["side"] == "BUY" else -1
    Pd, P0, Pc = (F(str(c[a])) for a in ("decision_price", "arrival_price", "end_price"))
    delay = s * filled * (P0 - Pd)
    execu = s * sum(lots[i] * (fp[i] - P0) for i in range(k))
    opp = s * (int(X) - filled) * (Pc - Pd)
    total = delay + execu + opp + fees
    bps = total / (int(X) * Pd) * 10000
    return dict(lots=lots, expected_cost=float(dtof(E)), variance=float(dtof(V)), filled=int(filled),
                fees=float(fees), delay=float(delay), execution=float(execu), opportunity=float(opp),
                total=float(total), total_bps=float(bps))

res = {}
for line in open("../uc5_packet/uc5_cases.blind.md"):
    m = re.match(r"\| (uc5_h-\d+) \| `(.*)` \|", line)
    if m: res[m.group(1)] = run(json.loads(m.group(2)))
json.dump(res, open("blind_results.json", "w"), indent=1, sort_keys=True)
print(json.dumps(res, indent=1))
