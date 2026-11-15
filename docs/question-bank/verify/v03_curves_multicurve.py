"""Recompute every worked-example number in 03-curves-multicurve.md and check it is printed there.

Run from the repository's python directory:
  PYTHONPATH=. python ../docs/question-bank/verify/v03_curves_multicurve.py
"""
import math
import sys
from datetime import date, timedelta
from pathlib import Path

from quantforge_core import csa, curve_fits, curves, futures, joint, ois, overnight, projection, steps
from quantforge_core.curves import CurveData
from quantforge_core.ois import Quote
from quantforge_core.projection import FraTrade, ProjectionQuote, SwapTrade

MD = Path(__file__).resolve().parents[1] / "03-curves-multicurve.md"
checks: list[str] = []


def add(s: str) -> None:
    checks.append(s)


AS_OF = date(2026, 11, 6)
QUOTES = [Quote("1Y", 0.035), Quote("2Y", 0.0335), Quote("3Y", 0.033),
          Quote("5Y", 0.0335), Quote("7Y", 0.0345), Quote("10Y", 0.036)]

# Q3.1 / Q3.2: the tutorial 1 SOFR curve, a discount factor and zero rate between pillars.
sofr, err = ois.bootstrap("SOFR", AS_OF, QUOTES, "LOG_LINEAR_DF")
add(f"1Y pillar {sofr.dates[0]}")
add(f"D = {sofr.discount_factors[0]:.12f}")
add(f"2Y pillar {sofr.dates[1]}")
add(f"D = {sofr.discount_factors[1]:.12f}")
mid = date(2028, 5, 15)
d_mid, z_mid = curves.discount(sofr, [mid])
add(f"t = {(mid - AS_OF).days / 365:.6f}")
add(f"D(2028-05-15) = {d_mid[0]:.10f}")
add(f"zero rate {z_mid[0]:.8f}")
lz = CurveData(AS_OF, "LINEAR_ZERO", sofr.dates, sofr.discount_factors)
d_lz, _ = curves.discount(lz, [mid])
add(f"LINEAR_ZERO gives {d_lz[0]:.10f}")
add(f"{(d_lz[0] - d_mid[0]) * 1e6:.3f} per million")

# Q3.3 forward
fwd = curves.forward(sofr, sofr.dates[0], sofr.dates[1], "ACT_360")
add(f"forward = {fwd:.8f}")

# Q3.4 extrapolation
far = date(2038, 11, 15)
d_far, z_far = curves.discount(sofr, [far])
t9, t10 = ((d - AS_OF).days / 365 for d in sofr.dates[-2:])
f_last = -math.log(sofr.discount_factors[-1] / sofr.discount_factors[-2]) / (t10 - t9)
add(f"f = {f_last:.8f}")
add(f"D(2038-11-15) = {d_far[0]:.10f}")

# Q3.5 bootstrap error
add(f"max_repricing_error {err:.1e}")

# Q3.6 par rate and annuity
ps5 = ois.periods("SOFR", AS_OF, "5Y")
ann, flt = ois.legs("SOFR", ps5, curves.build(sofr))
add(f"A = {ann:.8f}")
add(f"F = {flt:.8f}")
add(f"K = F/A = {flt / ann:.10f}")

# Q3.7 telescoping error, 10Y
ps10 = ois.periods("SOFR", AS_OF, "10Y")
c = curves.build(sofr)
_, f10 = ois.legs("SOFR", ps10, c)
tele = c.discount(ps10[0].start) - c.discount(ps10[-1].end)
add(f"general floating leg {f10:.8f}")
add(f"telescoped {tele:.8f}")
add(f"difference {tele - f10:.3e}")

# Q3.8 spot from a Saturday
p_sat = ois.periods("SOFR", date(2026, 11, 7), "1Y")
add(f"spot {p_sat[0].start}")
add(f"end {p_sat[0].end}")
add(f"payment {p_sat[0].payment}")
p_gbp = ois.periods("SONIA", AS_OF, "1Y")
add(f"SONIA starts {p_gbp[0].start}")

# Q3.9 compounding from fixings
cr = ois.compound([0.0430, 0.0431, 0.0429], [1, 3, 1], 360)
simple = (0.0430 * 1 + 0.0431 * 3 + 0.0429 * 1) / 5
add(f"compounded_rate = {cr:.10f}")
add(f"simple average {simple:.10f}")

# Q3.10 compound_dated methods, SOFR over December 2026
fix = []
d0 = date(2026, 11, 1)
for i in range(70):
    d = d0 + timedelta(days=i)
    fix.append((d, 0.0430 if d < date(2026, 12, 10) else 0.0405 if d < date(2026, 12, 30) else 0.0390))
st, en = date(2026, 12, 1), date(2027, 1, 4)
res = {}
for method, k in [("NONE", 0), ("LOOKBACK", 5), ("OBSERVATION_SHIFT", 5), ("LOCKOUT", 5)]:
    r, acc, intr = overnight.compound_dated("SOFR", st, en, method, k, fix)
    res[method] = r
    add(f"{method} {r:.8f}")
add(f"accrual {acc:.8f}")

# Q3.11 fallback
fr, sa, fb = overnight.fallback("USD-LIBOR-3M", date(2026, 12, 1), date(2027, 3, 1), fix + [
    (d0 + timedelta(days=i), 0.0390) for i in range(70, 130)])
add(f"compounded {fr:.8f}")
add(f"fallback_rate {fb:.8f}")

# Q3.12 negative rates
neg, _ = ois.bootstrap("ESTR", AS_OF, [Quote("1Y", -0.005), Quote("2Y", -0.003)], "LOG_LINEAR_DF")
add(f"1Y discount factor {neg.discount_factors[0]:.10f}")

# Q3.13 interpolation methods compared
probe = date(2032, 5, 14)
for m, kw in [("LOG_LINEAR_DF", {}), ("LINEAR_ZERO", {}), ("MONOTONE_CONVEX", {}),
              ("MONOTONIC_LOG_CUBIC", {}), ("TENSION_SPLINE", {"tension": 1.0})]:
    cd, e = ois.bootstrap("SOFR", AS_OF, QUOTES, m, **kw)
    dfs, _, fw = curves.inspect(cd, [probe])
    add(f"| `{m}` | {dfs[0]:.10f} | {fw[0]:.6f} |")

# Q3.14 hybrid
hy, e = ois.bootstrap("SOFR", AS_OF, QUOTES, "HYBRID", step_end=sofr.dates[1])
_, _, fh = curves.inspect(hy, [date(2027, 6, 1), date(2032, 5, 14)])
add(f"forward at 2027-06-01 {fh[0]:.6f}")
_, _, fl = curves.inspect(sofr, [date(2027, 6, 1)])
assert abs(fl[0] - fh[0]) < 1e-12

# Q3.15 jumps / turn of year
fac = math.exp(-0.0025 * 3 / 365)
add(f"factor = {fac:.10f}")
jumped, _ = ois.bootstrap("SOFR", AS_OF, QUOTES, "LOG_LINEAR_DF", jumps=((date(2026, 12, 31), fac),))
dj, _ = curves.discount(jumped, [date(2026, 12, 30), date(2027, 1, 4)])
dn, _ = curves.discount(sofr, [date(2026, 12, 30), date(2027, 1, 4)])
add(f"with the jump {dj[1]:.10f}")
add(f"without {dn[1]:.10f}")

# Q3.16 projection curve
TERM = [ProjectionQuote("DEPOSIT", 3, 0.0372), ProjectionQuote("FRA", 3, 0.0368),
        ProjectionQuote("FRA", 6, 0.0362), ProjectionQuote("SWAP", 24, 0.0358),
        ProjectionQuote("SWAP", 36, 0.0352), ProjectionQuote("SWAP", 60, 0.0356)]
proj, perr = projection.bootstrap(sofr, "USD-TERM-3M", AS_OF, TERM, "LOG_LINEAR_DF")
add(f"first projection pillar {proj.dates[0]}")
add(f"P = {proj.discount_factors[0]:.10f}")
add(f"projection max error {perr:.1e}")
val, par = projection.swap_pv(sofr, proj, SwapTrade("USD-TERM-3M", 60, 0.0366, 10_000_000.0, "PAY"))
add(f"par_rate {par:.10f}")
add(f"PV {val['pv']:.4f}")

# Q3.17 FRA
fstart = date(2027, 5, 10)
fv, ff = projection.fra_pv(sofr, proj, FraTrade("USD-TERM-3M", fstart, 0.0350, 10_000_000.0, "PAY"))
add(f"forward_rate {ff:.8f}")
add(f"FRA PV {fv['pv']:.4f}")

# Q3.18 basis
bs = projection.basis_spread(sofr, proj, "USD-TERM-3M", 60)
add(f"spread = {bs:.8f}")
add(f"{bs * 1e4:.2f} bp")

# Q3.19 futures convexity
fr_, cv, fwr = futures.convexity(96.25, 1.0, 1.25, 0.01, 0.03)
add(f"futures_rate {fr_:.6f}")
add(f"convexity {cv:.8f}")
add(f"forward_rate {fwr:.8f}")
fr2, cv2, _ = futures.convexity(96.25, 5.0, 5.25, 0.01, 0.03)
add(f"at 5 years {cv2 * 1e4:.3f} bp")
add(f"{cv * 1e4:.3f} bp")

# Q3.20 step curve
dfs, ons = steps.step_curve(AS_OF, 0.0430, [(date(2026, 12, 10), 0.0405), (date(2027, 1, 28), 0.0380)],
                            (), [date(2026, 12, 10), date(2027, 2, 15)])
add(f"D(2026-12-10) = {dfs[0]:.10f}")
add(f"D(2027-02-15) = {dfs[1]:.10f}")
hand = math.exp(-(0.0430 * 34 + 0.0405 * 49 + 0.0380 * 18) / 365)
add(f"hand {hand:.10f}")

# Q3.22 CSA discount
csa_d = csa.discount(sofr, 0.0010, None, [date(2031, 11, 6)])
base5, _ = curves.discount(sofr, [date(2031, 11, 6)])
add(f"Dc = {base5[0]:.10f}")
add(f"D = {csa_d[0]:.10f}")
csa_fx = csa.discount(sofr, 0.0, (1.28, [(date(2031, 11, 6), 1.3150)]), [date(2031, 11, 6)])
add(f"D_X = {csa_fx[0]:.10f}")

# Q3.23 OIS basis spread between two projection curves
shift = [Quote(q.tenor, q.rate + 0.0005) for q in QUOTES]
pb, _ = ois.bootstrap("SOFR", AS_OF, shift, "LOG_LINEAR_DF")
sp = csa.ois_spread("SOFR", "5Y", sofr, pb, sofr)
add(f"ois spread {sp * 1e4:.4f} bp")

# Q3.24 joint bootstrap
dj1, pj1, ej1 = csa.joint_bootstrap("SOFR", "USD-TERM-3M", AS_OF, QUOTES, TERM, "LOG_LINEAR_DF", "GLOBAL")
gap = max(abs(a - b) for a, b in zip(pj1.discount_factors, proj.discount_factors, strict=True))
add(f"largest pillar gap {gap:.1e}")

# Q3.25 joint solve Jacobian (one OIS curve, three quotes)
spec = [joint.CurveSpec("sofr", "OIS", convention="SOFR")]
ins = [joint.InstrumentSpec("q1", "sofr", "OIS", tenor="1Y", rate=0.035),
       joint.InstrumentSpec("q2", "sofr", "OIS", tenor="2Y", rate=0.0335),
       joint.InstrumentSpec("q3", "sofr", "OIS", tenor="3Y", rate=0.033)]
jr = joint.joint_solve(AS_OF, spec, ins)
jm = jr.jacobian
add(f"d ln D(1Y) / d q1 = {jm[0][0]:.6f}")
add(f"d ln D(3Y) / d q3 = {jm[2][2]:.6f}")
add(f"d ln D(1Y) / d q3 = {jm[0][2] + 0.0:.1f}")

# Q3.27 funding curve
spreads, fpill, _ = joint.funding_curve(sofr, [(date(2027, 5, 6), 0.0400), (date(2027, 11, 8), 0.0405)],
                                      [])
add(f"s_1 = {spreads[0]:.8f}")
add(f"s_2 = {spreads[1]:.8f}")

# Q3.28 smooth fit
knots = [1, 2, 3, 5, 7, 10]
mats = [1, 2, 3, 5, 7, 10]
zr = [0.0350, 0.0340, 0.0360, 0.0338, 0.0350, 0.0362]
f0, fit0, o0 = curve_fits.smooth(knots, mats, zr, 0.0)
f1, fit1, o1 = curve_fits.smooth(knots, mats, zr, 0.01)
add("lambda 0: " + ", ".join(f"{x:.5f}" for x in f0))
add(f"{max(abs(b - a) for a, b in zip(f0, f0[1:])) * 1e4:.0f} bp")
add(f"{max(abs(b - a) for a, b in zip(f1, f1[1:])) * 1e4:.0f} bp")
add("lambda 0.01: " + ", ".join(f"{x:.5f}" for x in f1))

# Q3.29 robust NS
rm = [0.5, 1, 2, 3, 5, 7, 10, 20]
ry = [0.0360, 0.0352, 0.0341, 0.0336, 0.0337, 0.0400, 0.0352, 0.0365]
b, rr, out, ob = curve_fits.robust(rm, ry, 2.5, 0.0005)
add("betas " + ", ".join(f"{x:.6f}" for x in b))
add(f"outliers {out}")
add(f"residual {rr[5] * 1e4:.2f} bp")

if __name__ == "__main__":
    text = MD.read_text(encoding="utf-8") if MD.exists() else ""
    missing = [s for s in checks if s not in text]
    if missing:
        print("MISSING:")
        for s in missing:
            print("  " + s)
        sys.exit(1)
    print(f"v03 OK: {len(checks)} checks")
