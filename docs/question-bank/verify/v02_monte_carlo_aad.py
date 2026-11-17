"""Recompute every worked-example number in 02-monte-carlo-aad.md and check it appears there.

Run from python/:  PYTHONPATH=. <venv python> ../docs/question-bank/verify/v02_monte_carlo_aad.py
"""
import json
import math
import sys
from pathlib import Path

from quantforge_core import aad_ladder, mc_greeks, monte_carlo, rng, sobol
from quantforge_core.black import big_n, small_n
from quantforge_core.errors import QfError

ROOT = Path(__file__).resolve().parents[3]
MD = Path(__file__).resolve().parents[1] / "02-monte-carlo-aad.md"
checks: list[str] = []


def c(s: str) -> None:
    checks.append(s)


def err(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
    except QfError as e:
        return e.code
    return "none"


def bs_call(s, k, r, q, v, t):
    """Scratch closed form (price, delta, vega, digital delta), not the library."""
    d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    price = s * math.exp(-q * t) * big_n(d1) - k * math.exp(-r * t) * big_n(d2)
    delta = math.exp(-q * t) * big_n(d1)
    vega = s * math.exp(-q * t) * small_n(d1) * math.sqrt(t)
    ddelta = math.exp(-r * t) * small_n(d2) / (s * v * math.sqrt(t))
    return price, delta, vega, ddelta


# --- RNG
u = rng.uniforms(42, 0, 3)
c(f"uniforms(seed 42) = {', '.join(f'{x:.12f}' for x in u)}")
c(f"first u64 = {rng.next_u64(42, 0, 1)[0]}")
c(f"stream 1 first uniform = {rng.uniforms(42, 1, 1)[0]:.12f}")
c(f"smallest u = 2^-53 = {2.0 ** -53:.6e}")
c(f"largest u = 1 - 2^-53 = {1 - 2.0 ** -53!r}")
c(f"inverse_normal(0.975) = {rng.inverse_normal([0.975])[0]:.12f}")
c(f"inverse_normal(1e-10) = {rng.inverse_normal([1e-10])[0]:.9f}")
c(f"inverse_normal(1.0): {err(rng.inverse_normal, [1.0])}")
full = rng.uniforms(42, 0, 8)
c(f"skip=3 matches draws 4 to 8: {rng.uniforms(42, 0, 5, skip=3) == full[3:]}")
c(f"same seed twice identical: {rng.normals(7, 0, 1000) == rng.normals(7, 0, 1000)}")
# --- Sobol
pts = sobol.points(2, 4)
c("Sobol 2-d points: " + ", ".join(f"({p[0]:g}, {p[1]:g})" for p in pts))
c(f"sobol dimensions 65: {err(sobol.points, 65, 1)}")
# --- MC engine
S, K, R, Q, V, T = 100.0, 100.0, 0.05, 0.02, 0.2, 1.0
exact = bs_call(S, K, R, Q, V, T)[0]
c(f"Black-Scholes = {exact:.6f}")
res = {}
for meth, n in (("PLAIN", 100000), ("ANTITHETIC", 100000), ("CONTROL_VARIATE", 100000),
                ("SOBOL", 65536)):
    p, se = monte_carlo.gbm_european("CALL", S, K, R, Q, V, T, n, 1, 20261115, 0, meth)
    res[meth] = (p, se)
    c(f"{meth}: price {p:.6f}, stderr {se:.6f}, error {p - exact:+.6f}")
p, se = res["PLAIN"]
c(f"error in stderr units = {(p - exact) / se:+.2f}")
for n in (1000, 4000, 16000):
    _, se_n = monte_carlo.gbm_european("CALL", S, K, R, Q, V, T, n, 1, 20261115, 0, "PLAIN")
    c(f"N = {n}: stderr {se_n:.4f}")
c(f"variance ratio antithetic/plain = {(res['ANTITHETIC'][1] / res['PLAIN'][1]) ** 2:.3f}")
c(f"variance ratio control/plain = {(res['CONTROL_VARIATE'][1] / res['PLAIN'][1]) ** 2:.3f}")
p12, _ = monte_carlo.gbm_european("CALL", S, K, R, Q, V, T, 4096, 12, 20261115, 0, "SOBOL")
c(f"SOBOL 12 steps, 4096 paths: error {p12 - exact:+.6f}")
c(f"SOBOL 65 steps: {err(monte_carlo.gbm_european, 'CALL', S, K, R, Q, V, T, 16, 65, 1, 0, 'SOBOL')}")
# --- MC Greeks (golden parameters of mcgreeks_g)
gp = (100.0, 100.0, 1.0, 0.03, 0.01, 0.2)
_, bd, bv, _ = bs_call(100.0, 100.0, 0.03, 0.01, 0.2, 1.0)
c(f"closed-form call delta = {bd:.6f}, vega = {bv:.4f}")
for meth, eps, h in (("PATHWISE", None, None), ("LIKELIHOOD_RATIO", None, None),
                     ("BUMP", None, 0.01)):
    g = mc_greeks.greeks(*gp, "CALL", meth, 10000, 20261109, eps, h)
    c(f"call {meth}: delta {g['delta']:.6f} (se {g['delta_se']:.6f}), vega {g['vega']:.4f} (se {g['vega_se']:.4f})")
dd = bs_call(100.0, 100.0, 0.03, 0.01, 0.2, 1.0)[3]
c(f"closed-form digital delta = {dd:.6f}")
for meth, eps, h in (("PATHWISE", 1.0, None), ("LIKELIHOOD_RATIO", None, None),
                     ("BUMP", None, 0.01)):
    g = mc_greeks.greeks(*gp, "DIGITAL_CALL", meth, 10000, 20261109, eps, h)
    c(f"digital {meth}: delta {g['delta']:.6f} (se {g['delta_se']:.6f})")
c(f"digital PATHWISE without width: {err(mc_greeks.greeks, *gp, 'DIGITAL_CALL', 'PATHWISE', 10000, 20261109, None, None)}")
c(f"paths = 1: {err(mc_greeks.greeks, *gp, 'CALL', 'PATHWISE', 1, 20261109, None, None)}")
# golden agreement
gold = json.loads((ROOT / "datasets/golden/stage_g/mcgreeks_g.json").read_text())
case = next(x for x in gold["cases"] if x["expected"]["status"] == "ok"
            and x["inputs"].get("payoff") == "CALL" and x["inputs"].get("method") == "PATHWISE")
gi = case["inputs"]
gg = mc_greeks.greeks(gi["spot"], gi["strike"], gi["expiry_years"], gi["rate"], gi["dividend_yield"],
                      gi["vol"], "CALL", "PATHWISE", gi["paths"], int(gi["seed"]), None, None)
diff = abs(gg["delta"] - case["expected"]["outputs"]["delta"])
c(f"golden {case['case_id']} delta {case['expected']['outputs']['delta']:.6f}, library differs by {diff:.0e}")
# --- AAD ladder (golden aadladder_g-0001)
lg = json.loads((ROOT / "datasets/golden/stage_g/aadladder_g.json").read_text())["cases"][0]
li = lg["inputs"]
out = aad_ladder.bermudan_ladder(li["curve"]["times"], li["curve"]["discount_factors"],
                                 li["mean_reversion"], li["sigma"], False, li["start_years"],
                                 li["payment_times"], li["fixed_rate"], li["swaption_type"],
                                 li["notional"], li["exercise_times"], li["grid"]["nx"],
                                 li["grid"]["steps_per_year"], li["grid"]["width"])
c(f"price = {out['price']:,.2f}")
c(f"d_price_d_sigma = {out['d_price_d_sigma']:,.0f}")
c(f"d_price_d_mean_reversion = {out['d_price_d_mean_reversion']:,.0f}")
dfs = out["d_price_d_discount_factors"]
c("d_price_d_discount_factors = " + ", ".join(f"{x:,.0f}" for x in dfs))
c(f"1bp of sigma adds about {out['d_price_d_sigma'] * 1e-4:,.0f}")
worst = max(abs(a - b) / max(abs(b), 1e-6 * li["notional"])
            for a, b in zip(dfs, lg["expected"]["outputs"]["d_price_d_discount_factors"]))
c(f"largest relative gap to the golden reference = {worst:.0e}")

if __name__ == "__main__":
    if not MD.exists() or "--print" in sys.argv:
        print("\n".join(checks))
        sys.exit(0)
    text = MD.read_text(encoding="utf-8")
    missing = [s for s in checks if s not in text]
    for s in missing:
        print("MISSING:", s)
    assert not missing, f"{len(missing)} strings missing"
    print(f"v02 OK: {len(checks)} checks")
