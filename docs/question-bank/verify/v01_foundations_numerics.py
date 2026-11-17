"""Recompute every worked-example number in 01-foundations-numerics.md and check it appears there.

Run from python/:  PYTHONPATH=. <venv python> ../docs/question-bank/verify/v01_foundations_numerics.py
"""
import math
import sys
from datetime import date
from pathlib import Path

from quantforge_core import (calendars, compounding, cos, integrate, interp, linalg, money, pde,
                             roots, schedules, stats)
from quantforge_core.black import big_n
from quantforge_core.daycount import year_fraction as yf
from quantforge_core.errors import QfError

MD = Path(__file__).resolve().parents[1] / "01-foundations-numerics.md"
checks: list[str] = []


def c(s: str) -> None:
    checks.append(s)


def err(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
    except QfError as e:
        return e.code
    return "none"


def bs(call: bool, s, k, r, q, v, t) -> float:
    """Black-Scholes, scratch formula (QuantForge's black module uses its own Option type)."""
    d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    if call:
        return s * math.exp(-q * t) * big_n(d1) - k * math.exp(-r * t) * big_n(d2)
    return k * math.exp(-r * t) * big_n(-d2) - s * math.exp(-q * t) * big_n(-d1)


D = date
# --- day counts
c(f"ACT_360 = {yf('ACT_360', D(2024,1,1), D(2024,7,1)):.6f}")
c(f"ACT_365F = {yf('ACT_365F', D(2024,1,1), D(2024,7,1)):.6f}")
c(f"ACT_ACT_ISDA = {yf('ACT_ACT_ISDA', D(2003,11,1), D(2004,5,1)):.12f}")
c(f"ACT_ACT_ICMA = {yf('ACT_ACT_ICMA', D(2003,11,1), D(2004,5,1), frequency=2, ref_start=D(2003,11,1), ref_end=D(2004,5,1)):.6f}")
s0, e0 = D(2024, 2, 29), D(2024, 8, 31)
for conv in ("THIRTY_360_BOND", "THIRTY_360_US", "THIRTY_E_360", "THIRTY_E_PLUS_360"):
    c(f"{conv} = {yf(conv, s0, e0) * 360:.0f}/360")
c(f"THIRTY_E_360_ISDA = {yf('THIRTY_E_360_ISDA', s0, e0, termination=D(2029, 8, 31)) * 360:.0f}/360")
c(f"ONE_ONE same day = {yf('ONE_ONE', s0, s0):g}")
c(f"reversed dates: {err(yf, 'ACT_360', e0, s0)}")
a1 = yf('ACT_ACT_AFB', D(2004,2,28), D(2008,2,28))
a2 = yf('ACT_ACT_AFB', D(2004,2,28), D(2008,2,29))
c(f"AFB to 2008-02-28 = {a1:.9f}")
c(f"AFB to 2008-02-29 = {a2:.9f}")
c(f"Strata 4 + 1/366 = {4 + 1/366:.9f}")
c(f"AFB 1994-02-10 to 1997-06-30 = {yf('ACT_ACT_AFB', D(1994,2,10), D(1997,6,30)):.9f}")
bd = calendars.business_days_between("GBLO", D(2024,1,1), D(2024,7,1))
c(f"GBLO business days = {bd}")
c(f"BUS_252 = {yf('BUS_252', D(2024,1,1), D(2024,7,1), calendar='GBLO'):.6f}")
# --- calendars
c(f"Easter Sunday 2026 = {calendars.easter_sunday(2026)}")
c(f"Good Friday 2026 = {calendars.good_friday(2026)}")
c(f"USGS 2026-04-03 business day = {calendars.is_business_day('USGS', D(2026,4,3))}")
c(f"USGS 2025-04-18 business day = {calendars.is_business_day('USGS', D(2025,4,18))}")
c(f"GBLO 2026-04-03 business day = {calendars.is_business_day('GBLO', D(2026,4,3))}")
sat = D(2024, 8, 31)
for conv in ("FOLLOWING", "MODIFIED_FOLLOWING", "PRECEDING"):
    c(f"{conv} -> {calendars.adjust('GBLO', sat, conv)}")
c(f"GBLO holidays Aug 2024 = {[str(h) for h in calendars.holidays('GBLO', 2024) if h.month == 8]}")
c(f"EOM true -> {calendars.add_tenor('GBLO', D(2023,2,28), '1M', 'MODIFIED_FOLLOWING', True)}")
c(f"EOM false -> {calendars.add_tenor('GBLO', D(2023,2,28), '1M', 'MODIFIED_FOLLOWING', False)}")
c(f"EOM true from 2024-03-30 -> {calendars.add_tenor('GBLO', D(2024,3,30), '1M', 'MODIFIED_FOLLOWING', True)}")
c(f"add_business_days(0) from Saturday -> {calendars.add_business_days('GBLO', sat, 0)}")
c(f"add_business_days(2) from Friday 2024-08-23 -> {calendars.add_business_days('GBLO', D(2024,8,23), 2)}")
c(f"business_days_between Mon-Mon = {calendars.business_days_between('GBLO', D(2024,9,2), D(2024,9,9))}")
# --- schedules
ps = schedules.generate(D(2024,1,15), D(2025,4,15), 6, "GBLO", False, 0)
for p in ps:
    c(f"| {p.start} | {p.end} | {p.payment} |")
# --- compounding
C = compounding.Compounding
c(f"simple D = {compounding.discount_factor(0.05, 2, C('SIMPLE')):.9f}")
c(f"semi-annual D = {compounding.discount_factor(0.05, 2, C('PERIODIC', 2)):.9f}")
c(f"continuous D = {compounding.discount_factor(0.05, 2, C('CONTINUOUS')):.9f}")
c(f"continuous rate = {compounding.convert(0.05, 2, C('PERIODIC', 2), C('CONTINUOUS')):.9f}")
c(f"annual rate = {compounding.convert(0.05, 2, C('PERIODIC', 2), C('PERIODIC', 1)):.9f}")
c(f"t = 0 convert: {err(compounding.convert, 0.05, 0, C('SIMPLE'), C('CONTINUOUS'))}")
c(f"negative continuous D = {compounding.discount_factor(-0.005, 3, C('CONTINUOUS')):.9f}")
c(f"r = -4 quarterly: {err(compounding.discount_factor, -4.0, 1, C('PERIODIC', 4))}")
# --- money
c(f"round 2.675 GBP -> {money.round_money('2.675', 'GBP')[0]}")
c(f"round 2.665 GBP -> {money.round_money('2.665', 'GBP')[0]}")
c(f"round 1234.5 JPY -> {money.round_money('1234.5', 'JPY')[0]}")
c(f"round 1235.5 JPY -> {money.round_money('1235.5', 'JPY')[0]}")
c(f"0.1 + 0.2 = {money.add_money('0.1', 'USD', '0.2', 'USD')[0]}")
c(f"1.50 + -1.5 = {money.add_money('1.50', 'USD', '-1.5', 'USD')[0]}")
c(f"GBP + USD: {err(money.add_money, '1', 'GBP', '1', 'USD')}")
c(f"25 BP = {money.convert(25, 'BP', 'DECIMAL'):g} DECIMAL = {money.convert(25, 'BP', 'PERCENT'):g} PERCENT")
# --- roots
f = lambda x: x ** 3 - 2 * x - 5
df = lambda x: 3 * x * x - 2
rb = roots.bisection(f, 2, 3)
rr = roots.brent(f, 2, 3)
rn = roots.newton(f, df, 2.0)
c(f"bisection root = {rb.root:.12f}, {rb.iterations} iterations")
c(f"brent root = {rr.root:.12f}, {rr.iterations} iterations")
c(f"newton root = {rn.root:.12f}, {rn.iterations} iterations")
c(f"no bracket: {err(roots.bisection, f, 3, 4)}")
c(f"zero derivative: {err(roots.newton, lambda x: x * x + 1, lambda x: 2 * x, 0.0)}")
# --- integration
true = math.e - 1
for name, val in (("trapezoid", integrate.trapezoid(math.exp, 0, 1, 16)),
                  ("simpson", integrate.simpson(math.exp, 0, 1, 16)),
                  ("gauss_legendre", integrate.gauss_legendre(math.exp, 0, 1, 16))):
    c(f"{name} n=16 error = {abs(val - true):.2e}")
gk = integrate.gauss_kronrod(lambda x: 1 / math.sqrt(x), 0, 1, 1e-10)
gkv = gk[0] if isinstance(gk, tuple) else gk.value
c(f"gauss_kronrod inv_sqrt error = {abs(gkv - 2):.1e}")
# --- interpolation
xs, dfs = [1.0, 2.0], [0.97, 0.93]
lin = interp.evaluate("linear", xs, dfs, [1.5])[0][0]
loglin = interp.evaluate("log_linear", xs, dfs, [1.5])[0][0]
c(f"linear DF(1.5) = {lin:.6f}")
c(f"log_linear DF(1.5) = {loglin:.6f}")
c(f"geometric mean = {math.sqrt(0.97 * 0.93):.6f}")
kx, ky = [0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 0.0, 0.0, 1.0, 1.0]
nat = interp.evaluate("cubic_natural", kx, ky, [1.5, 3.5])[0]
pch = interp.evaluate("monotone_pchip", kx, ky, [1.5, 3.5])[0]
c(f"cubic_natural at 1.5 = {nat[0]:.6f}, at 3.5 = {nat[1]:.6f}")
c(f"monotone_pchip at 1.5 = {pch[0]:.6f}, at 3.5 = {pch[1]:.6f}")
mt, mr = [1.0, 2.0, 5.0, 10.0], [0.03, 0.035, 0.04, 0.042]
mc = interp.monotone_convex(mt, mr, [2.0, 3.0, 5.0], False)
mcz = mc["zero_rates"] if isinstance(mc, dict) else mc[1]
mcf = mc["forwards"] if isinstance(mc, dict) else mc[0]
c(f"zero rate at 2 = {mcz[0]:.12f}")
c(f"zero rate at 3 = {mcz[1]:.6f}")
c(f"zero rate at 5 = {mcz[2]:.12f}")
c(f"forward at 3 = {mcf[1]:.6f}")
# --- finite differences (scratch stencil, as core.diff.central)
for h in (1e-1, 1e-4, 1e-8):
    d1 = (math.exp(1 + h) - math.exp(1 - h)) / (2 * h)
    c(f"h = {h:.0e}: error {abs(d1 - math.e):.1e}")
corr = [[1.0, 0.8, 0.3], [0.8, 1.0, 0.5], [0.3, 0.5, 1.0]]
L = linalg.cholesky(corr)
c(f"L = [[{L[0][0]:.6f}], [{L[1][0]:.6f}, {L[1][1]:.6f}], [{L[2][0]:.6f}, {L[2][1]:.6f}, {L[2][2]:.6f}]]")
bad = [[1.0, 0.9, 0.2], [0.9, 1.0, 0.9], [0.2, 0.9, 1.0]]
c(f"eigenvalues = {', '.join(f'{v:.6f}' for v in linalg.eigen_symmetric(bad))}")
c(f"cholesky: {err(linalg.cholesky, bad)}")
# --- PDE
args = (100.0, 100.0, 0.05, 0.02, 0.2, 1.0)
exact = bs(True, *args)
c(f"Black-Scholes call = {exact:.6f}")
for j, m in ((400, 200), (800, 400)):
    p = pde.bs_european("CALL", *args, j, m)
    c(f"J = {j}, M = {m}: price {p.price:.6f}, error {abs(p.price - exact):.2e}")
    if j == 400:
        c(f"delta {p.delta:.6f}, gamma {p.gamma:.6f}")
v, s = 0.2, 1.0
d1 = (math.log(1) + (0.05 - 0.02 + 0.02)) / 0.2
c(f"analytic delta {math.exp(-0.02) * big_n(d1):.6f}, gamma {math.exp(-0.02) * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) / (100 * 0.2):.6f}")
# --- COS
cp = cos.european("CALL", 100, 110, 0.05, 0.02, 1.0, cos.BlackScholes(0.2), 256, 10)
c(f"COS call K=110 = {cp[0]:.10f}")
c(f"analytic = {bs(True, 100, 110, 0.05, 0.02, 0.2, 1.0):.10f}")
c(f"range a = {cp[1]:.6f}, b = {cp[2]:.6f}")
c64 = cos.european("CALL", 100, 110, 0.05, 0.02, 1.0, cos.BlackScholes(0.2), 16, 10)[0]
c(f"N = 16: {c64:.6f}")
# --- statistics
data = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
c(f"quantiles = {', '.join(f'{q:g}' for q in stats.quantile(data, [0.25, 0.5, 0.9]))}")
summ = stats.summary(data)
c(f"variance = {summ['variance']:.6f}")
ew = stats.ewma_variance([0.01, -0.02, 0.015], 0.94)
c(f"ewma = {', '.join(f'{v:.6e}' for v in ew)}")
big = [1e9 + v for v in (4.0, 7.0, 13.0, 16.0)]
naive = (sum(v * v for v in big) - 4 * (sum(big) / 4) ** 2) / 3
c(f"two-pass variance = {stats.summary(big)['variance']:g}")
c(f"naive formula = {naive:g}")

if __name__ == "__main__":
    if not MD.exists() or "--print" in sys.argv:
        print("\n".join(checks))
        sys.exit(0)
    text = MD.read_text(encoding="utf-8")
    missing = [s for s in checks if s not in text]
    for s in missing:
        print("MISSING:", s)
    assert not missing, f"{len(missing)} strings missing"
    print(f"v01 OK: {len(checks)} checks")
