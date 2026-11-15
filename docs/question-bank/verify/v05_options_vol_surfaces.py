"""Recompute every worked-example number in 05-options-vol-surfaces.md and check the printed string.

Run from the repo's python directory:
  PYTHONPATH=. <venv python> ../docs/question-bank/verify/v05_options_vol_surfaces.py
"""
import math
from pathlib import Path

from quantforge_core import arb_surface as A
from quantforge_core import black, sabr, smile
from quantforge_core import fx_smile as FX
from quantforge_core import heston as H
from quantforge_core.black import Option

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "05-options-vol-surfaces.md").read_text(encoding="utf-8")
SPECS = ROOT.parents[1] / "specifications"
checks = 0


def has(s: str, text: str = TEXT) -> None:
    global checks
    assert s in text, f"missing: {s!r}"
    checks += 1


def f(x: float, fmt: str) -> str:
    return format(x, fmt)


# Q5.1
bs = Option("BLACK_SCHOLES", "CALL", 100.0, 1.0, 100.0, rate=0.03, dividend_yield=0.01)
bsp = Option("BLACK_SCHOLES", "PUT", 100.0, 1.0, 100.0, rate=0.03, dividend_yield=0.01)
c, p = black.price(bs, 0.2), black.price(bsp, 0.2)
assert abs((c - p) - math.exp(-0.03) * (bs.forward - 100)) < 1e-12
has(f"call is {c:.6f}"); has(f"put {p:.6f}"); has(f"difference, {c - p:.6f}")
# Q5.3
bach = black.price(Option("BACHELIER", "CALL", 0.01, 1.0, 0.01, discount_factor=0.97), 0.007)
assert abs(bach - 0.97 * 0.007 / math.sqrt(2 * math.pi)) < 1e-15
has(f"call is {bach:.8f} per unit");
neg = black.price(Option("BACHELIER", "CALL", -0.002, 1.0, -0.001, discount_factor=0.97), 0.007)
has(f"the call is {neg:.8f}")
# Q5.4
sh = black.price(Option("BLACK_76", "CALL", 0.0, 2.0, -0.001, discount_factor=0.95, shift=0.02), 0.2)
has(f"the call is {sh:.8f}.")
# Q5.5
has(f"returns a vol of {black.implied(bs, c):.6f}")
# Q5.6
deep = black.greeks(Option("BLACK_SCHOLES", "CALL", 160.0, 0.1, 100.0, rate=0.03), 0.2)
has(f"worth {deep['price']:.2e} with vega {deep['vega']:.2e}")
assert deep["vega"] < 1e-3
# Q5.7
g = black.greeks(bs, 0.2)
has(f"delta {g['delta']:.6f}"); has(f"gamma {g['gamma']:.7f}"); has(f"vega {g['vega']:.4f} per 1.00")
has(f"so {g['vega'] / 100:.6f} per vol point"); has(f"theta {g['theta']:.5f} per year")
has(f"rho {g['rho']:.4f} per 1.00")
# Q5.8 / Q5.9
b76 = black.greeks(Option("BLACK_76", "CALL", 100.0, 1.0, 102.0, discount_factor=0.97), 0.25)
assert b76["rho"] == -b76["price"]
has(f"price {b76['price']:.4f}, rho {b76['rho']:.4f}"); has(f"theta {b76['theta']:.5f}.")
has(f"vanna {b76['vanna']:.7f} and volga {b76['volga']:.5f}")
assert abs(g["vanna"]) < 1e-12 and abs(g["volga"]) < 1e-12
# Q5.10
bg = black.bump_greeks(bs, 0.2)
has(f"analytic delta {g['delta']:.8f} against bumped {bg['delta']:.8f}")
assert f(g["vega"], ".6f") == f(bg["vega"], ".6f")
has(f"both {g['vega']:.6f} to six")
# Q5.11
surf = smile.Surface([0.5, 1.0], [-0.2, 0.0, 0.2], [[0.24, 0.2, 0.18], [0.23, 0.2, 0.19]])
sv = smile.surface_vega(surf, [smile.Position("CALL", 100.0, 100.0, 0.98, 0.75, 1.0)])
has(f"PV {sv['pv']:.5f}"); has(f"vega {sv['bucket_vega'][0][1]:.4f} on the 0.5-year")
has(f"{sv['bucket_vega'][1][1]:.4f} on the 1-year"); has(f"parallel {sv['parallel_vega']:.6f}")
has(f"bucket sum of {sv['bucket_sum']:.6f}")
# Q5.12
has(f"strike is {smile.delta_to_strike(100.0, 0.2, 1.0, 'CALL', 0.25, 'FORWARD', None):.3f} under forward")
has(f"and {smile.delta_to_strike(100.0, 0.2, 1.0, 'CALL', 0.25, 'SPOT', math.exp(-0.01)):.3f} under spot")
# Q5.13
rb = smile.rr_bf(100.0, 1.0, 0.2, "DELTA_NEUTRAL", -0.03, 0.005, 0.25, "FORWARD", None)
has(f"ATM strike {rb['atm_strike']:.3f}, call vol {rb['call_vol']:.2f}, put vol {rb['put_vol']:.2f}")
has(f"call strike {rb['call_strike']:.3f}, put strike {rb['put_strike']:.4f}")
# Q5.14 / Q5.15
e = smile.svi_evaluate(smile.Svi(0.04, 0.4, -0.4, 0.0, 0.1), [-0.5, 0.0, 0.5], 1.0)
has(f"`w = {e['total_variance'][1]:.2f}` and implied vol {e['implied_vol'][1]:.6f}")
has(f"`w = {e['total_variance'][0]:.6f}` and vol {e['implied_vol'][0]:.6f}")
has(f"`min_g = {e['min_g']:.7f}`")
bad = smile.svi_evaluate(smile.Svi(0.001, 1.5, -0.9, 0.0, 0.05),
                         [-1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0], 1.0)
assert bad["g"].index(bad["min_g"]) == 2
has(f"`min_g = {bad['min_g']:.5f}` at `k = -0.2`")
# Q5.16
ss = smile.ssvi_evaluate(-0.7, 1.5, 0.5, [0.04, 0.1], [-0.5, 0.0, 0.5])
assert ss["butterfly_free"] and ss["calendar_free"]
has(f"`w = {ss['total_variance'][0][0]:.6f}` at `k = -0.5`")
# Q5.17
s2 = A.ssvi_to_svi(-0.7, 1.5, 0.5, 0.04)
has(f"`a = {s2.a:.4f}`, `b = {s2.b:.6f}`, `m = {s2.m:.7f}`, `sigma = {s2.sigma:.7f}`")
w1 = smile.svi_evaluate(s2, [0.3], 1.0)["total_variance"][0]
w2 = smile.ssvi_evaluate(-0.7, 1.5, 0.5, [0.04], [0.3])["total_variance"][0][0]
assert abs(w1 - w2) < 1e-15
has(f"`w = {w1:.7f}` at `k = 0.3`")
# Q5.18
w, v = smile.surface_query(surf, [(0.75, 0.0), (0.75, 0.1), (2.0, 0.0)])
has(f"`w = {w[0]:.2f}`, vol {v[0]:.1f}. At `(0.75, 0.1)`: `w = {w[1]:.6f}`, vol {v[1]:.6f}")
has(f"`w = {w[2]:.2f}`, vol {v[2]:.1f}.")
# Q5.19
s19 = smile.Surface([0.5, 1.0], [-0.2, 0.0, 0.2], [[0.24, 0.2, 0.18], [0.17, 0.15, 0.14]])
assert smile.surface_check(s19)["arbitrage_free"]
has(f"from {0.5 * 0.2 ** 2:.2f} to {1.0 * 0.15 ** 2:.4f}")
# Q5.20
lee = A.surface_check([A.Slice(1.0, smile.Svi(0.02, 1.2, 0.7, 0.0, 0.1))], [0.0], False)
assert lee["wing_violations"] == [{"expiry_index": 0, "side": "RIGHT", "kind": "LEE"}]
has(f"`sR = {1.2 * 1.7:.2f}`, `sL = {1.2 * 0.3:.2f}`")
# Q5.21
fv = A.forward_vols([0.5, 1.0, 2.0], [0.20, 0.22, 0.21])
has(f"forward vols {fv[0]:.1f}, {fv[1]:.6f}, {fv[2]:.6f}")
# Q5.22 / Q5.23
sl = [A.Slice(0.5, smile.Svi(0.01, 0.1, -0.5, 0.0, 0.1)), A.Slice(1.0, smile.Svi(0.02, 0.12, -0.4, 0.0, 0.15))]
_, iv, lv = A.dupire(sl, [(0.75, 0.0), (0.75, -0.2)])
has(f"implied vol {iv[0]:.6f}, local vol {lv[0]:.6f}"); has(f"implied {iv[1]:.6f}, local {lv[1]:.6f}")
_, ivj, lvj = A.dupire(sl, [(0.5 * (1 - 1e-9), 0.0), (0.5, 0.0)])
has(f"local vol {lvj[0]:.6f} just before 0.5 years and {lvj[1]:.6f} at 0.5 years")
# Q5.24
p1 = smile.Svi(0.02, 0.12, -0.4, 0.0, 0.15)
ds = A.smile_dynamics(p1, 1.0, 100.0, 105.0, 0.02, 0.0, [90.0, 100.0, 110.0], "STICKY_STRIKE", "CALL")
dd = A.smile_dynamics(p1, 1.0, 100.0, 105.0, 0.02, 0.0, [90.0, 100.0, 110.0], "STICKY_DELTA", "CALL")
has("keeps vols " + ", ".join(f"{x:.6f}" for x in ds["vols_shifted"]))
has("moves them to " + ", ".join(f"{x:.6f}" for x in dd["vols_shifted"]))
has("Deltas: " + ", ".join(f"{x:.6f}" for x in ds["deltas"]))
has("against " + ", ".join(f"{x:.6f}" for x in dd["deltas"]) + " (sticky delta)")
# Q5.25
vov, mc = A.vol_of_vol([0.20, 0.21, 0.195, 0.205, 0.22, 0.215], 252.0, "LOG")
has(f"vol of vol {vov:.6f}"); has(f"mean change {mc:.7f}")
# Q5.26
P = sabr.Sabr(0.03, 2.0, 0.04, 0.5, -0.3, 0.4)
hv = sabr.hagan(P, [0.02, 0.03, 0.04])
has("vols " + ", ".join(f"{x:.6f}" for x in hv) + " at strikes")
# Q5.27 / Q5.28
Pn = sabr.Sabr(0.01, 10.0, 0.03, 0.5, -0.3, 0.6)
dens, mind, negd = sabr.density(Pn, [0.0005, 0.001, 0.002, 0.005, 0.01], 0.0002, "REPORT")
assert negd and dens[0] == mind
has(f"`min_density = {mind:.3f}` at 0.05%")
af = sabr.arbfree(Pn, 400, 100, 400, [0.005, 0.01, 0.02])
has(f"mass {af['mass']:.6f}, mean {af['mean']:.6f}"); has(f"absorbed mass {af['absorbed']:.6f}")
has(f"minimum density {af['min_density']:.8f}")
has("Implied vols " + ", ".join(f"{x:.6f}" for x in af["vols"]))
# Q5.29
ks = [0.02, 0.025, 0.03, 0.035, 0.04]
al, rh, nu, rm = sabr.calibrate(0.03, 2.0, 0.5, 0.0, ks, sabr.hagan(P, ks), None)
has(f"`alpha = {al:.6f}`, `rho = {rh:.6f}`, `nu = {nu:.6f}`")
assert rm < 1e-15
# Q5.30
h = H.Heston(0.04, 1.5, 0.04, 0.5, -0.7)
hp = H.heston_price(100.0, [90.0, 100.0, 110.0], 1.0, 0.03, 0.0, h, "CALL")
has(f"calls {hp[0]:.4f}, {hp[1]:.5f}, {hp[2]:.5f} at 90")
hs = H.heston_price(100.0, [100.0], 1.0, 0.0, 0.0, H.Heston(0.09, 2.0, 0.04, 1e-3, -0.5), "CALL")[0]
vbar = 0.04 + (0.09 - 0.04) * (1 - math.exp(-2.0)) / 2.0
atm = Option("BLACK_SCHOLES", "CALL", 100.0, 1.0, 100.0)
has(f"Heston {hs:.5f}, `vbar = {vbar:.7f}`, Black-Scholes at `sqrt(vbar)` {black.price(atm, math.sqrt(vbar)):.5f}, at `sqrt(v0)` {black.price(atm, 0.3):.4f}")
# Q5.31
j = H.Jumps(0.5, -0.1, 0.15)
bp = H.bates_price(100.0, [90.0, 100.0, 110.0], 1.0, 0.03, 0.0, h, j, "CALL")
has(f"{bp[0]:.4f}, {bp[1]:.4f}, {bp[2]:.5f} at 90, 100, 110")
mp = H.merton_price(100.0, [90.0, 100.0, 110.0], 1.0, 0.03, 0.0, 0.2, j, "CALL")
has(f"{mp[0]:.4f}, {mp[1]:.4f}, {mp[2]:.5f}; plain Black-Scholes at 90 is "
    f"{black.price(Option('BLACK_SCHOLES', 'CALL', 90.0, 1.0, 100.0, rate=0.03), 0.2):.4f}")
# Q5.33 / Q5.34 / Q5.35 / Q5.36
gk = FX.option_price(1.085, 1.10, 0.5, 0.045, 0.03, 0.08, "CALL", 1e6)
has(f"price USD {gk['price']:,.2f}"); has(f"premium {gk['premium_pct_foreign']:.7f}")
has(f"forward {gk['forward']:.6f}"); has(f"delta EUR {gk['delta']:,.0f}"); has(f"vega USD {gk['vega']:,.0f}")
dt = FX.delta_from_strike(1.085, 1.10, 0.5, 0.045, 0.03, 0.08, "CALL")
has(f"SPOT {dt['SPOT']:.6f}, FORWARD {dt['FORWARD']:.6f}, SPOT_PA {dt['SPOT_PA']:.6f}, FORWARD_PA {dt['FORWARD_PA']:.6f}")
pa = FX.delta_to_strike(1.085, 0.5, 0.045, 0.03, 0.08, "CALL", 0.25, "SPOT_PA")
sp = FX.delta_to_strike(1.085, 0.5, 0.045, 0.03, 0.08, "CALL", 0.25, "SPOT")
has(f"strike is {pa:.6f} under SPOT_PA and {sp:.6f} under SPOT")
dns = FX.atm_strike(1.085, 0.5, 0.045, 0.03, 0.08, "DNS", "SPOT")
dpa = FX.atm_strike(1.085, 0.5, 0.045, 0.03, 0.08, "DNS", "SPOT_PA")
has(f"DNS {dns:.6f} (SPOT delta) and {dpa:.6f} (SPOT_PA)")
sq = FX.smile_from_quotes(1.085, 0.5, 0.045, 0.03, 0.08, -0.01, 0.0025, 0.25, "SPOT", "DNS")
has(f"call vol {sq['call_vol']:.4f}, put vol {sq['put_vol']:.4f}, ATM strike {sq['atm_strike']:.6f}, "
    f"call strike {sq['call_strike']:.6f}, put strike {sq['put_strike']:.6f}")
# Q5.37
cap = 1e7 * 0.25 * black.price(Option("BLACK_76", "CALL", 0.037, 1.0, 0.035, discount_factor=0.955), 0.24)
has(f"caplet {cap:,.2f}")
# Q5.38 / Q5.39 / Q5.40: golden values quoted from the spec; check they are in it
cube = (SPECS / "05-volatility" / "rates-vol-cube.md").read_text(encoding="utf-8")
for s in ("24.000, 23.143, 21.956, 21.096, 19.706%", "alpha 0.048, beta 0.5, rho -0.27, nu 0.44",
          "Forward 3.5718%", "annuity 4.35104", "Hagan vol 25.265%", "rho = -0.27995", "20.22%"):
    has(s, cube); has(s.replace("Forward", "forward"))
yv = 0.055 / (6.4 * 0.0425)
has(f"= {yv:.6f}`, or {yv * 100:.2f}%"); has(f"read as {0.055 / 6.4 * 100:.2f}%")
print(f"v05 OK: {checks} checks")
