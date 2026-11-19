import json, math, time
import numpy as np
from blind_ref import *
inputs = json.load(open(PACKET + "/inputs/K-8.inputs.json"))["cases"]
c = {x["case_id"]: x for x in inputs}

# 1. independent Q check: D(t) P(t,T) vs textbook HW bond (f free)
a, s, t, T, f = 0.05, 0.01, 2.0, 5.0, 0.0123
c2 = s * s / (2 * a * a); c4 = s * s / (4 * a)
I = t + 2 * math.expm1(-a * t) / a - math.expm1(-2 * a * t) / (2 * a)
B = -math.expm1(-a * (T - t)) / a
e1 = math.expm1(-a * t); e2 = math.expm1(-2 * a * t)
x = 0.007
P0t, P0T = 0.9, 0.8
alpha = f + c2 * (1 - math.exp(-a * t)) ** 2
r = x + alpha
Pt = P0T / P0t * math.exp(B * f - s * s / (4 * a) * (1 - math.exp(-2 * a * t)) * B * B - B * r)
Dt = P0t * math.exp(-c2 * I)
Q = math.exp(math.log(P0T) - c2 * (I + B * e1 * e1) + c4 * e2 * B * B - B * x)
print("Q check", Dt * Pt, Q, Dt * Pt / Q - 1)

# 2. European limit via Gaussian quadrature (case 6, single exercise at 1.0), cases 4 style with exercise [1]
inp = c["k8_k-0006"]["inputs"]
tt = 1.0
a = inp["mean_reversion"]; s = inp["sigma"]
times = [0.0] + inp["curve"]["times"]; lnp = [0.0] + [math.log(v) for v in inp["curve"]["discount_factors"]]
def lnP(u):
    for j, tj in enumerate(times):
        if tj == u: return lnp[j]
    k = max(j for j in range(len(times) - 1) if times[j] < u)
    return lnp[k] + (lnp[k + 1] - lnp[k]) * (u - times[k]) / (times[k + 1] - times[k])
c2 = s * s / (2 * a * a); c4 = s * s / (4 * a)
I = tt + 2 * math.expm1(-a * tt) / a - math.expm1(-2 * a * tt) / (2 * a)
var = s * s * (1 - math.exp(-2 * a * tt)) / (2 * a)
cov = s * s / a * ((1 - math.exp(-a * tt)) / a - (1 - math.exp(-2 * a * tt)) / (2 * a))
mu = -cov
xs = np.linspace(mu - 12 * math.sqrt(var), mu + 12 * math.sqrt(var), 400001)
pdf = np.exp(-(xs - mu) ** 2 / (2 * var)) / math.sqrt(2 * math.pi * var)
pays = [p for p in inp["payment_times"] if p > tt]
def Qv(u):
    Bv = -math.expm1(-a * (u - tt)) / a
    e1 = math.expm1(-a * tt); e2 = math.expm1(-2 * a * tt)
    return np.exp(lnP(u) - c2 * (I + Bv * e1 * e1) + c4 * e2 * Bv * Bv - Bv * xs)
ann = 0; prev = tt
for u in pays:
    ann = ann + Qv(u) * (u - prev); prev = u
E = math.exp(lnP(tt) - c2 * I) - Qv(pays[-1]) - inp["fixed_rate"] * ann
integ = np.trapezoid(pdf * np.maximum(E, 0), xs)
euro = inp["notional"] * math.exp(c2 * I) * integ
print("European quadrature", euro)
for nx, spy in [(101, 50), (201, 100), (401, 200), (401, 400)]:
    pr, P = run(inp, cell_override={"nx": nx, "steps_per_year": spy})
    print("grid", nx, spy, pr.v, pr.v / euro - 1)

# 3. convergence of the multi-exercise case 1 price/ladder
base = c["k8_k-0001"]["inputs"]
for nx, spy in [(41, 20), (101, 50), (201, 100)]:
    t0 = time.time()
    pr, P = run(base, cell_override={"nx": nx, "steps_per_year": spy})
    print("c1", nx, spy, pr.v, pr.d[1], pr.d[4], pr.d[10], pr.d[11], round(time.time() - t0, 1))

# 4. bump check
for cid in ["k8_k-0005"]:
    inp = c[cid]["inputs"]
    pr, P = run(inp)
    dfs = inp["curve"]["discount_factors"]
    worst = 0
    for j in range(P + 2):
        eps = 1e-6
        if j < P:
            h = dfs[j] * eps
            up = list(dfs); dn = list(dfs); up[j] += h; dn[j] -= h
            pu = run(inp, override={"dfs": up})[0].v; pd = run(inp, override={"dfs": dn})[0].v
        else:
            key = "a" if j == P else "sigma"
            v0 = inp["mean_reversion"] if j == P else inp["sigma"]
            h = v0 * eps
            pu = run(inp, override={key: v0 + h})[0].v; pd = run(inp, override={key: v0 - h})[0].v
        fd = (pu - pd) / (2 * h)
        an = pr.d[j]
        print(cid, j, an, fd, (fd - an) / (abs(an) + 1e-9) if an != 0 else fd)
# 5. literal-boundary sensitivity
for cid in ["k8_k-0005", "k8_k-0007"]:
    inp = c[cid]["inputs"]
    p1 = run(inp)[0]; p2 = run(inp, literal_boundary=True)[0]
    print("literal-boundary", cid, p1.v, p2.v, p2.v / p1.v - 1, "d_a", p1.d[10], p2.d[10])
    p3 = run(inp, xfactor="x")[0]
    print("x-factor alt", cid, p3.v / p1.v - 1)
