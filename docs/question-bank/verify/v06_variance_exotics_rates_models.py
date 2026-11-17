"""Recompute every worked-example number in 06-variance-exotics-rates-models.md and check the text.

Run from the repo's python directory:
  PYTHONPATH=. <venv python> ../docs/question-bank/verify/v06_variance_exotics_rates_models.py
"""
import math
from datetime import date
from pathlib import Path

from quantforge_core import equity_curves as EC
from quantforge_core import exotics as X
from quantforge_core import lmm
from quantforge_core import shortrate as S
from quantforge_core import variance as V
from quantforge_core.errors import QfError

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / "06-variance-exotics-rates-models.md").read_text(encoding="utf-8")
SPECS = ROOT.parents[1] / "specifications"
checks = 0


def has(s: str, text: str = TEXT) -> None:
    global checks
    assert s in text, f"missing: {s!r}"
    checks += 1


def sci(x: float, spec: str) -> str:
    """Scientific notation without the leading zero in the exponent, as the text prints it."""
    return format(x, spec).replace("e-0", "e-")


def short(x: float) -> str:
    """Shortest scientific form to 7 significant figures: 2.134e-4."""
    m, ex = format(x, ".6e").split("e")
    return f"{m.rstrip('0').rstrip('.')}e{int(ex)}"


# Q6.1
rv, rvol, pay = V.varswap_realized([100, 101, 99.5, 100.25, 102, 101.5], 252.0, 0.04, 1e6)
has(f"realised variance {rv:.7f}, vol {rvol:.6f} ({rvol * 100:.2f}%)"); has(f"payoff is {pay:,.2f}")
# Q6.2
d0, d1 = date(2026, 1, 2), date(2027, 1, 2)
assert (d1 - d0).days == 365
ks = [float(k) for k in range(50, 155, 5)]
fv, fvol, pv = V.varswap_fair_strike(d0, d1, 100.0, 0.03, 0.0, [k for k in ks if k <= 100],
                                     [k for k in ks if k >= 100], [(k, 0.2) for k in ks], 5.0, 0.04, 1e6)
has(f"fair variance {fv:.7f}, fair vol {fvol:.6f}, PV {pv:.2f}")
k1 = [float(k) for k in range(50, 151)]
fv1, fvol1, _ = V.varswap_fair_strike(d0, d1, 100.0, 0.03, 0.0, [k for k in k1 if k <= 100],
                                      [k for k in k1 if k >= 100], [(k, 0.2) for k in k1], 1.0, 0.04, 1e6)
has(f"fair variance is {fv1:.7f}, vol {fvol1:.6f}")
# Q6.3 (scratch formula of the spec)
f = lambda K: 2 * ((K - 100) / 100 - math.log(K / 100))  # noqa: E731
s0, s1 = (f(110) - f(100)) / 10, (f(120) - f(110)) / 10
e = lambda x: f"{x:.5e}".replace("e-0", "e-")  # noqa: E731
has(f"weight {e(s0)}"); has(f"has {e(s1 - s0)}"); has(f"= {e(2 * 10 / 110 ** 2)}`")
# Q6.5 / Q6.6
Q = V.Quote
strip = [Q(90, 10.5, 11.5, 0.5, 0.7), Q(95, 6.0, 6.6, 1.4, 1.6), Q(100, 2.9, 3.1, 2.9, 3.3),
         Q(105, 1.0, 1.2, 5.8, 6.6), Q(110, 0.3, 0.5, 10.0, 11.0)]
fwd, k0, var, _ = V.vix_term_variance(43200, 0.0, strip)
T = 43200 / 525600
corr = (1 / T) * (fwd / k0 - 1) ** 2
has(f"Forward {fwd:.1f}, so `K0 = {k0}`"); has(f"variance {var:.7f}.")
has(f"strip term alone is {var + corr:.6f}"); has(f"removes {corr:.7f} to leave {var:.7f}")
# Q6.7: the Cboe sample result is quoted from the spec
has("13.9278424", (SPECS / "05-volatility" / "vix-index.md").read_text(encoding="utf-8")); has("13.9278424")
# Q6.8
idx, nv, xv = V.vix_index((30240, 0.0, strip), (50400, 0.0, strip))
has(f"near variance {nv:.6f}, next {xv:.7f}, index {idx:.4f}")
# Q6.9 / Q6.10 / Q6.11
ll, vs, nxt = V.garch_loglik([0.01, -0.02], 1e-5, 0.1, 0.8, "SAMPLE")
has(f"variances {sci(vs[0], '.1e')} and {sci(vs[1], '.1e')}, next variance {sci(nxt, '.2e')}, log-likelihood {ll:.6f}")
fc, tot, ann, vl = V.garch_forecast(1e-5, 0.1, 0.8, nxt, 5, 252.0)
has("`V_L = " + f"{vl:.0e}".replace("e-0", "e-") + "`"); has("forecasts " + ", ".join(short(x) for x in fc))
has("total " + f"{tot:.5e}".replace("e-0", "e-")); has(f"annualised vol {ann:.6f}")
has(f"is {math.log(0.5) / math.log(0.9):.2f} periods")
ll1, _, _ = V.garch_loglik([0.01, -0.02], 1e-5, 0.1, 0.8, 1e-4)
has(f"log-likelihood {ll1:.6f} instead of {ll:.6f}")
# Q6.13 .. Q6.21
s, k, t, r, q, v = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
has(f"worth {X.digital(s, k, t, r, q, v, 'CALL', 'CASH_OR_NOTHING', 1.0):.6f}")
has(f"asset call is worth {X.digital(s, k, t, r, q, v, 'CALL', 'ASSET_OR_NOTHING', 1.0):.4f}")
di = X.barrier(s, k, t, r, q, v, "CALL", 90.0, 0.0, "DOWN_IN")
do = X.barrier(s, k, t, r, q, v, "CALL", 90.0, 0.0, "DOWN_OUT")
van, put = X.gbs(1.0, s, k, t, r, r - q, v), X.gbs(-1.0, s, k, t, r, r - q, v)
assert abs(di + do - van) < 1e-12
has(f"down-and-in call {di:.5f}, down-and-out call {do:.5f}, sum {di + do:.4f}, equal to the vanilla call {van:.4f}")
bgk = X.barrier(s, k, t, r, q, v, "CALL", 90.0, 0.0, "DOWN_OUT", "DISCRETE", 252)
has(f"shifted barrier is {90 * math.exp(-0.5826 * v * math.sqrt(1 / 252)):.4f} and the down-and-out call is {bgk:.5f}, against {do:.5f}")
try:
    X.barrier(s, k, t, r, q, v, "PUT", 90.0, 0.0, "DOWN_OUT", "DISCRETE", 252)
    raise AssertionError("put should be refused")
except QfError as err:
    assert err.code == "E_DOMAIN"
has(f"geometric call is {X.asian_geometric(s, k, t, r, q, v, 'CALL', 'CONTINUOUS', []):.5f}")
has(f"it is {X.asian_geometric(s, k, t, r, q, v, 'CALL', 'DISCRETE', [0.25, 0.5, 0.75, 1.0]):.5f}, closer to the vanilla {van:.4f}")
has(f"minimum of 95 the price is {X.lookback(s, t, r, q, v, 'CALL', 95.0):.4f}")
has(f"(minimum 100) it is {X.lookback(s, t, r, q, v, 'CALL', 100.0):.4f}")
has(f"`rho = -0.3` the call is {X.quanto(s, k, t, 0.05, 0.03, 0.02, 0.25, 0.10, -0.3, 'CALL'):.4f}")
has(f"`rho = 0` it is {X.quanto(s, k, t, 0.05, 0.03, 0.02, 0.25, 0.10, 0.0, 'CALL'):.5f}")
has(f"chooser {X.chooser(s, k, t, r, q, v, 0.5):.4f}, against call {van:.4f} plus put {put:.5f} = {van + put:.4f}")
has(f"strike 3 gives {X.kirk(50.0, 45.0, 3.0, 1.0, 0.05, 0.3, 0.25, 0.6):.5f}")
has(f"(Margrabe) gives {X.kirk(50.0, 45.0, 0.0, 1.0, 0.05, 0.3, 0.25, 0.6):.5f}")
bk = X.basket([100.0, 100.0], [0.5, 0.5], [0.2, 0.3], [[1, 0.5], [0.5, 1]], 100.0, 1.0, 0.03, "CALL")
has(f"basket vol {bk['basket_vol']:.6f}, price {bk['price']:.5f}")
# Q6.22 .. Q6.24
cr = X.crr(100.0, 100.0, 1.0, 0.05, 0.0, 0.25, "PUT", 500)
has(f"American {cr['american']:.5f}, European {cr['european']:.5f}, early exercise premium {cr['early_exercise_premium']:.6f}")
has(f"BAW {X.baw(100.0, 100.0, 1.0, 0.05, 0.0, 0.25, 'PUT'):.5f} against the 500-step tree's {cr['american']:.5f}")
fd = X.fd(100.0, 100.0, 1.0, 0.05, 0.0, 0.25, "PUT", "AMERICAN", 201, 200, 5.0)
has(f"price {fd['price']:.5f}, delta {fd['delta']:.6f}, gamma {fd['gamma']:.7f}")
has(f"about {cr['american'] - fd['price']:.3f} below")
# Q6.25
ca = EC.corporate_action("RIGHTS", 50.0, 1000.0, 48.0, {"new_per_old": 0.25, "subscription_price": 40.0})
has(f"factor {ca['factor']:.2f}, theoretical ex price {ca['ex_price']:.0f}, adjusted shares {ca['adjusted_shares']:,.2f}, adjusted strike {ca['adjusted_strike']:.2f}")
assert abs(ca["adjusted_shares"] * ca["adjusted_strike"] - 48000) < 1e-9
# Q6.26 / Q6.27
vz = S.zcb(S.make_model("VASICEK", 0.1, 0.01, 0.04, None, 0.03), 0.03, 0.0, 5.0)
has(f"discount factor {vz['discount_factor']:.6f}, zero rate {vz['zero_rate']:.7f}")
cz = S.zcb(S.make_model("CIR", 0.2, 0.05, 0.04, None, 0.03), 0.03, 0.0, 5.0)
has(f"discount factor {cz['discount_factor']:.6f}, zero rate {cz['zero_rate']:.7f}")
has(f"`2ab = {2 * 0.2 * 0.04:.3f}` against `sigma^2 = {0.05 ** 2:.4f}`")
# Q6.28 / Q6.29
times = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
hw = S.curve_model(times, [math.exp(-0.03 * x) for x in times], 0.05, 0.01)
pt = [2.0, 3.0, 4.0, 5.0, 6.0]
pa = S.swaption(hw, 1.0, pt, 0.03, "PAYER", 1e6)
re = S.swaption(hw, 1.0, pt, 0.03, "RECEIVER", 1e6)
diff = pa["price"] - re["price"]
assert abs(diff - pa["annuity"] * (pa["forward_swap_rate"] - 0.03)) < 1e-6
has(f"payer {pa['price']:,.2f}, receiver {re['price']:,.2f}, forward swap rate {pa['forward_swap_rate'] * 100:.5f}%")
has(f"Payer minus receiver, {diff:,.2f}")
g = S.make_grid(201, 100, 6.0)
be = S.bermudan_swaption(hw, 1.0, pt, 0.03, "PAYER", 1e6, [1.0, 2.0, 3.0, 4.0, 5.0], g)["price"]
b1 = S.bermudan_swaption(hw, 1.0, pt, 0.03, "PAYER", 1e6, [1.0], g)["price"]
has(f"Bermudan {be:,.2f}"); has(f"same grid: {b1:,.2f}, against Jamshidian {pa['price']:,.2f} ({(1 - b1 / pa['price']) * 100:.2f}% low)")
# Q6.31 / Q6.32
lt = [0.5, 1, 2, 3, 5, 7, 10]
ld = [math.exp(-0.03 * x) for x in lt]
abcd = (-0.06, 0.17, 0.54, 0.17)
cp = lmm.capfloor(lt, ld, abcd, [0.5 * i for i in range(1, 11)], 0.03, "CAP", 1e6)
has(f"price {cp['price']:,.2f}; first three Black vols " + ", ".join(f"{x:.6f}" for x in cp["black_vols"][:3]))
lspec = (SPECS / "04-pricing" / "lmm.md").read_text(encoding="utf-8")
for x, sx in zip(cp["black_vols"][:3], ("0.1547", "0.1869", "0.2088")):
    assert f"{x:.4f}" == sx
    has(sx, lspec)
r0 = lmm.swaption_rebonato(lt, ld, abcd, 0.0, 5.0, [6.0, 7.0, 8.0, 9.0, 10.0], 0.035, "PAY", 1e6)
r5 = lmm.swaption_rebonato(lt, ld, abcd, 0.5, 5.0, [6.0, 7.0, 8.0, 9.0, 10.0], 0.035, "PAY", 1e6)
has(f"Black vol is {r0['black_vol']:.6f} and the price {r0['price']:,.2f}")
has(f"vol is {r5['black_vol']:.6f} and the price {r5['price']:,.2f}")
has("0.2283", lspec); has("0.1670", lspec)
print(f"v06 OK: {checks} checks")
