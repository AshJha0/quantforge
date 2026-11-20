import json, math
from fractions import Fraction
from decimal import Decimal, getcontext, Context, setcontext

TWO_POW = 2.0 ** 500
TINY = 2.0 ** -500
TWO_OVER_PI = 0.6366197723675814


def sigma_of(ch):
    n = len(ch)
    mean = math.fsum(ch) / n
    s2 = math.fsum([(c - mean) * (c - mean) for c in ch])
    sig = math.sqrt(s2 / (n - 1))
    M = max(abs(c) for c in ch)
    if sig <= 2.0 ** -26 * M:
        raise ValueError("E_DOMAIN no noise scale")
    return sig


def t_rate(nu, k):
    rn = math.sqrt(nu)
    if k <= rn:
        den = nu + k * k
        c2 = nu / den
        root = math.sqrt(den)
        s = k / root
        c = rn / root
    else:
        r = rn / k
        w = math.sqrt(1 + r * r)
        s = 1 / w
        c = r / w
        c2 = c * c
    odd = nu % 2 == 1
    if odd:
        m = (nu - 1) // 2
        def step(t, j): return (t * ((2 * j + 2) * c2)) / (2 * j + 3)
    else:
        m = nu // 2
        def step(t, j): return (t * ((2 * j + 1) * c2)) / (2 * j + 2)
    t = 1.0
    S = 0.0
    e = 0
    for j in range(m):
        if e == 0:
            S = S + t
        t = step(t, j)
        if 0 < t < TINY:
            t = t * TWO_POW
            e += 1
    if odd:
        A = TWO_OVER_PI * (math.atan2(c, s) - s * c * S)
    else:
        A = 1 - s * S
    if A >= 0.125:
        return A
    R = 0.0
    j = m
    while True:
        R = R + t
        t = step(t, j)
        j += 1
        if t <= R * 2.0 ** -60:
            break
        if t < TINY:
            t = t * TWO_POW
            R = R * TWO_POW
            e += 1
    alpha = TWO_OVER_PI * s * c * R if odd else s * R
    for _ in range(e):
        alpha = alpha * TINY
    return alpha


def nominal(k):
    """2*Phi(-k) via 100-digit Decimal; erfc series for k<10, Mills continued fraction otherwise."""
    ctx = Context(prec=700, Emax=10**9, Emin=-10**9)
    setcontext(ctx)
    K = Decimal(k)
    if k < 10:
        # erf(x) = 2/sqrt(pi) sum (-1)^n x^(2n+1)/(n!(2n+1)), x=k/sqrt2 ; 2Phi(-k)=1-erf(x)
        x2 = K * K / 2
        x = (x2).sqrt()
        term = x
        tot = Decimal(0)
        n = 0
        while True:
            tot += term / (2 * n + 1)
            n += 1
            term = -term * x2 / n
            if abs(term) < Decimal(10) ** -60 and n > 5:
                break
        pi = _pi()
        erf = 2 / pi.sqrt() * tot
        return float(1 - erf)
    # Mills: Phi(-k) = phi(k) * R, R = 1/(k+1/(k+2/(k+3/(k+...))))
    f = Decimal(0)
    for i in range(3000, 0, -1):
        f = Decimal(i) / (K + f)
    R = 1 / (K + f)
    pi = _pi()
    phi = (-(K * K) / 2).exp() / (2 * pi).sqrt()
    return float(2 * phi * R)


def _pi():
    # Machin
    def atan_inv(n):
        n = Decimal(n); x = 1 / n; s = x; t = x; i = 1
        while abs(t) > Decimal(10) ** -690:
            t = -t / (n * n); i += 2; s += t / i
        return s
    return 4 * (4 * atan_inv(5) - atan_inv(239))


def check(inp):
    ch = inp["changes"]; k = inp["k"]; d = inp["days_since"]
    sig = sigma_of(ch)
    thr = k * sig * math.sqrt(d)
    fire = abs(inp["x_now"] - inp["x_ref"]) > thr
    return {"fire": bool(fire), "sigma": sig, "threshold": thr,
            "false_alarm_rate": t_rate(len(ch) - 1, k), "nominal_rate": nominal(k)}


if __name__ == "__main__":
    P = "C:/Work/Claude/qf-blind/trig_k_v2_packet/"
    inp = json.load(open(P + "inputs/K-4c.inputs.json"))
    tpl = json.load(open(P + "output_template.json"))["results_skeleton"]
    for c in inp["cases"]:
        tpl["cases"][c["case_id"]] = check(c["inputs"])
    json.dump(tpl, open("blind_results.json", "w"), indent=1)
