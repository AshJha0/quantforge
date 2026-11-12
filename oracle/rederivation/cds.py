"""CDS index option (Pedersen-adjusted Black), derived from spec section + first-principles derivation."""
import math, datetime as dt
from scipy.optimize import brentq

def add_months(d, n):
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    import calendar
    day = min(d.day, calendar.monthrange(y, m)[1])
    return dt.date(y, m, day)

def periods(expiry, maturity):
    out = []
    a = expiry
    k = 0
    while True:
        k += 1
        b = add_months(expiry, 3 * k)
        if b >= maturity:
            b = maturity
            out.append((a, b)); break
        out.append((a, b)); a = b
    return out

def ncdf(x): return 0.5 * math.erfc(-x / math.sqrt(2))

def black(F, K, v, call):
    if v <= 0:
        return max(F - K, 0.0) if call else max(K - F, 0.0)
    d1 = (math.log(F / K) + 0.5 * v * v) / v
    d2 = d1 - v
    if call: return F * ncdf(d1) - K * ncdf(d2)
    return K * ncdf(-d2) - F * ncdf(-d1)

def legs(per, tfun, r, h, R):
    prot = 0.0; ann = 0.0
    for a, b in per:
        m = a + dt.timedelta(days=(b - a).days // 2)
        Pm = math.exp(-r * tfun(m)); Pb = math.exp(-r * tfun(b))
        Sa = math.exp(-h * tfun(a)); Sb = math.exp(-h * tfun(b))
        prot += (1 - R) * Pm * (Sa - Sb)
        ann += (b - a).days / 360 * Pb * Sb + (m - a).days / 360 * Pm * (Sa - Sb)
    return prot, ann

def cdsindex_option(i):
    D = dt.date.fromisoformat
    asof, exp, mat = D(i['as_of']), D(i['expiry']), D(i['maturity'])
    r, h, R, K, C, N, sig = i['rate'], i['hazard_rate'], i['recovery'], i['strike'], i['coupon'], i['notional'], i['vol']
    per = periods(exp, mat)
    t = lambda d: (d - asof).days / 365
    prot, A = legs(per, t, r, h, R)
    F = prot / A
    T = t(exp)
    FEP = (1 - R) * (-math.expm1(-h * T)) * math.exp(-r * T)
    tp = lambda d: (d - exp).days / 365
    def ratio(x):
        p, a = legs(per, tp, r, x, R)
        return p / a
    hi = 2 * K / (1 - R)
    while ratio(hi) <= K: hi *= 2
    hK = brentq(lambda x: ratio(x) - K, 0.0, hi, xtol=1e-17, rtol=4*2.3e-16, maxiter=500)
    AK = legs(per, tp, r, hK, R)[1]
    G = (K - C) * AK
    Fadj = F + FEP / A
    Kadj = C + G * math.exp(-r * T) / A
    if Fadj <= 0 or Kadj <= 0:
        return {"status": "could_not_derive", "reason": "Fadj or Kadj nonpositive (domain error per spec)"}
    price = N * A * black(Fadj, Kadj, sig * math.sqrt(T), i['type'] == 'PAYER')
    return dict(price=price, forward_spread=F, adjusted_forward=Fadj, adjusted_strike=Kadj,
                risky_annuity=A, strike_annuity=AK, strike_hazard=hK,
                exercise_upfront=N * G, front_end_protection=N * FEP)
