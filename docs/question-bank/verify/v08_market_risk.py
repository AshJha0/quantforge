"""Recompute every worked-example number in 08-market-risk.md and check it appears there.

Run from the repository's python directory:
    PYTHONPATH=. python ../docs/question-bank/verify/v08_market_risk.py
Add --dump to print the expected strings without checking.
"""
import json
import math
import sys
from pathlib import Path

from quantforge_core.cli.main import run_case

HERE = Path(__file__).resolve()
MD = HERE.parents[1] / "08-market-risk.md"
REPO = HERE.parents[3]


def golden(suite, case_id):
    with open(REPO / "datasets" / "golden" / suite, encoding="utf-8") as f:
        [c] = [c for c in json.load(f)["cases"] if c["case_id"] == case_id]
    return c


def run(op, inputs):
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "qb", "operation": op, "inputs": inputs}))
    assert r["status"] == "ok", r
    return r["outputs"]


def rung(suite, case_id):
    c = golden(suite, case_id)
    return c["inputs"], run(c["operation"], c["inputs"])


checks = []
chk = checks.append

# Q8.1, Q8.2, Q8.13: par risk of a 2Y receiver (risk_r2-0001)
pi, par = rung("r2/risk_r2.json", "risk_r2-0001")
chk(f"par_dv01 = {par['par_dv01']:,.2f}")
chk(f"2Y bucket {par['par_buckets'][5]:,.2f}")
fwd = run("risk.curve.par", {**pi, "scheme": "FORWARD"})
chk(f"FORWARD gives {fwd['par_dv01']:,.4f}")
chk(f"CENTRAL gives {par['par_dv01']:,.4f}")
b10 = run("risk.curve.par", {**pi, "bump_bp": 10.0})
chk(f"10 bp central bump gives {b10['par_dv01']:,.4f}")

# Q8.3 duration and convexity
cf = run("risk.cashflows", {"cashflows": [{"t": 1.0, "amount": 5.0}, {"t": 2.0, "amount": 5.0},
                                          {"t": 3.0, "amount": 105.0}], "yield": 0.04})
chk(f"pv {cf['pv']:.6f}")
chk(f"duration {cf['duration']:.6f}")
chk(f"convexity {cf['convexity']:.6f}")
dp = -cf["duration"] * cf["pv"] * 0.0001
chk(f"about {dp:.6f} per bp")

# Q8.4, Q8.21 historical VaR / ES (risk_f4-0003, first 250 days, as tutorial 5)
pnl = golden("stage_f/risk_f4.json", "risk_f4-0003")["inputs"]["pnl"]
first, second = pnl[:250], pnl[250:]
h = run("risk.var.historical", {"pnl": first, "confidence": 0.99})
chk(f"VaR {h['var']:,.2f}")
chk(f"ES {h['es']:,.2f}")
chk(f"tail_count {h['tail_count']}")
losses = sorted(-x for x in first)
chk(f"largest {losses[-1]:,.2f}")
chk(f"second {losses[-2]:,.2f}")
chk(f"old estimator {sum(losses[-3:]) / 3:,.2f}")

# Q8.5 parametric
_, pv = rung("stage_f/risk_f4.json", "risk_f4-0026")
chk(f"var = {pv['var']:,.2f}")
chk(f"es = {pv['es']:,.2f}")

# Q8.6 Kupiec
k0 = run("risk.backtest.kupiec", {"observations": 250, "exceptions": 0, "confidence": 0.99})
chk(f"LR_uc = {k0['lr_uc']:.6f}")
chk(f"p-value {k0['p_value']:.6f}")
exc = sum(1 for x in second if -x > h["var"])
k4 = run("risk.backtest.kupiec", {"observations": 250, "exceptions": exc, "confidence": 0.99})
chk(f"{exc} exceptions give LR_uc {k4['lr_uc']:.6f}")
chk(f"p-value {k4['p_value']:.6f}")

# Q8.7 traffic light
for x in (4, 5, 10):
    t = run("risk.backtest.traffic_light", {"observations": 250, "exceptions": x, "confidence": 0.99})
    chk(f"{x} exceptions: {t['zone']}, P(X <= {x}) = {t['cumulative_probability']:.6f}, plus factor {t['plus_factor']:.2f}")
t5 = run("risk.backtest.traffic_light", {"observations": 500, "exceptions": 4, "confidence": 0.99})
chk(f"plus_factor {t5['plus_factor']}")

# Q8.8 ES Z2
_, z = rung("stage_j/esbt_j.json", "esbt_j-0001")
chk(f"z2 = {z['z2']:.6f}")

# Q8.9 concentration
c = run("risk.concentration.measures", {"exposures": [50.0, -30.0, 20.0], "top_n": 1})
chk(f"hhi = {c['hhi']:.6f}")
chk(f"effective_number = {c['effective_number']:.6f}")
chk(f"top_n_share = {c['top_n_share']:.6f}")

# Q8.10 limits
lim = run("risk.limits.check", {"measures": {"VAR": 4.2e6, "DV01": -95000.0, "VEGA": 30000.0},
                                "limits": {"VAR": {"soft": 4e6, "hard": 5e6}, "DV01": {"soft": 80000.0, "hard": 90000.0},
                                           "VEGA": {"soft": 50000.0, "hard": 60000.0}}})
for name in ("DV01", "VAR", "VEGA"):
    chk(f"{name} {lim['measures'][name]['status']} at utilisation {lim['measures'][name]['utilisation']:.4f}")
chk(f"overall {lim['overall']}")

# Q8.11 model reserve
_, mr = rung("stage_g/reserve_g.json", "reserve_g-0001")
chk(f"range {mr['range']:.4f}")
chk(f"reserve {mr['reserve']:.4f}")
chk(f"relative_reserve {mr['relative_reserve'] * 100:.4f}%")

# Q8.12 JTD
_, j = rung("stage_f/risk_f3.json", "risk_f3-0046")
chk(f"jtd = {j['total']:,.2f}")

# Q8.13 par vs zero, Q8.14 key rate
ki, kr = rung("r2/risk_r2.json", "risk_r2-0002")
chk(f"zero_dv01 = {kr['zero_dv01']:,.2f}")
chk(f"sum of TRIANGULAR key rates {sum(kr['key_rates']):,.2f}")
pk = run("risk.curve.key_rate", {**ki, "mode": "PILLAR", "key_dates": None})
chk(f"sum of PILLAR key rates {sum(pk['key_rates']):,.2f}")
chk(f"PILLAR 2Y bucket {pk['key_rates'][5]:,.2f}")
chk(f"TRIANGULAR 2Y bucket {kr['key_rates'][5]:,.2f}")

# Q8.15, Q8.16 Jacobian and par-from-zero
_, jac = rung("r2/risk_r2.json", "risk_r2-0031")
J = jac["jacobian"]
chk(f"J[0][0] = {J[0][0]:.6f}")
chk(f"J[5][5] = {J[5][5]:.6f}")
upper = max(abs(J[i][k]) for i in range(len(J)) for k in range(i + 1, len(J)))
chk(f"largest entry above the diagonal {upper:.1e}")
chain = [sum(pk["key_rates"][i] * J[i][col] for i in range(len(J))) for col in range(len(J))]
chk(f"chain rule gives {chain[5]:,.4f}")
chk(f"par bucket {par['par_buckets'][5]:,.4f}")

# Q8.17 P&L explain
_, pe = rung("r2/pnl_r2.json", "pnl_r2-0001")
chk(f"full_pnl {pe['full_pnl']:,.2f}")
chk(f"risk_pnl {pe['risk_pnl']:,.2f}")
chk(f"unexplained {pe['unexplained']:,.2f}")
chk(f"threshold {pe['threshold']:,.2f}")

# Q8.18 FHS
fi, fh = rung("stage_f/risk_f4.json", "risk_f4-0019")
chk(f"{len(fi['returns'])} daily returns")
chk(f"lambda {fi['lambda']}")
chk(f"sigma_next {fh['sigma_next']:.6f}")
chk(f"FHS VaR {fh['var']:,.2f}")
chk(f"FHS ES {fh['es']:,.2f}")
hp = run("risk.var.historical", {"pnl": [fi["position_value"] * r for r in fi["returns"]], "confidence": fi["confidence"]})
chk(f"plain historical VaR {hp['var']:,.2f}")

# Q8.19 Monte Carlo VaR
mi, mc = rung("stage_f/risk_f4.json", "risk_f4-0037")
chk(f"MC VaR {mc['var']:,.2f}")
chk(f"MC ES {mc['es']:,.2f}")
w, S = mi["weights"], mi["covariance"]
sd = math.sqrt(sum(w[a] * S[a][b] * w[b] for a in range(2) for b in range(2)))
pp = run("risk.var.parametric", {"mean": 0.0, "std": sd, "confidence": 0.99})
chk(f"portfolio standard deviation {sd:,.2f}")
chk(f"parametric VaR {pp['var']:,.2f}")
chk(f"parametric ES {pp['es']:,.2f}")

# Q8.20 Christoffersen
_, ch = rung("stage_f/risk_f4.json", "risk_f4-0064")
tr = ch["transitions"]
chk(f"n00 = {tr['n00']}, n01 = {tr['n01']}, n10 = {tr['n10']}, n11 = {tr['n11']}")
chk(f"LR_uc {ch['lr_uc']:.6f}")
chk(f"LR_ind {ch['lr_ind']:.6f}")
chk(f"LR_cc {ch['lr_cc']:.6f}")
chk(f"p_cc {ch['p_cc']:.6f}")

# Q8.22 GIRR delta
_, g1 = rung("stage_f/frtb_f.json", "frtb_f-0001")
chk(f"capital {g1['capital']:,.2f}")
quotes = [{"tenor": n, "rate": r} for n, r in
          [("1Y", 0.035), ("2Y", 0.0335), ("3Y", 0.033), ("5Y", 0.0335), ("7Y", 0.0345), ("10Y", 0.036)]]
swap = {"convention": "SOFR", "tenor": "5Y", "fixed_rate": 0.034, "notional": 10_000_000.0, "side": "PAY"}
kr5 = run("risk.ois.dv01", {"as_of": "2026-11-06", "quotes": quotes, "interpolation": "LOG_LINEAR_DF",
                            "trade": swap})["key_rate"]
rows = [{"currency": "USD", "curve": "SOFR", "risk_factor": q["tenor"], "sensitivity": d / 0.0001}
        for q, d in zip(quotes, kr5) if d != 0.0]
fr = run("risk.frtb.girr_delta", {"sensitivities": rows, "specified_currency_reduction": False})
chk(f"5Y sensitivity {rows[-1]['sensitivity']:,.0f}")
chk(f"GIRR delta capital {fr['capital']:,.2f}")
chk(f"binding scenario {fr['binding_scenario']}")
chk(f"medium {fr['scenarios']['medium']['delta']:,.2f}")

# Q8.23 FX
_, fx = rung("stage_f/frtb_f2b.json", "frtb_f2b-0002")
chk(f"medium {fx['scenarios']['medium']['delta']:,.2f}")
chk(f"low {fx['scenarios']['low']['delta']:,.2f}")
chk(f"high {fx['scenarios']['high']['delta']:,.2f}")

# Q8.24 equity
_, eq = rung("stage_f/frtb_f2b.json", "frtb_f2b-0008")
chk(f"medium K = {eq['scenarios']['medium']['delta']:,.2f}")
chk(f"high K = {eq['scenarios']['high']['delta']:,.2f}")

# Q8.25 LVaR
_, lv = rung("stage_f/risk_f4b.json", "risk_f4b-0017")
chk(f"liquidity_cost {lv['liquidity_cost']:,.2f}")
chk(f"lvar {lv['lvar']:,.2f}")

# Q8.26 horizon
hz = run("risk.vol.horizon", {"daily_vol": 0.01, "ar1": 0.2, "horizon_days": 10})
chk(f"variance_ratio {hz['variance_ratio']:.6f}")
chk(f"vol {hz['vol']:.6f}")
chk(f"sqrt_rule_vol {hz['sqrt_rule_vol']:.6f}")

# Q8.27 Euler
eu = run("risk.contrib.euler", {"weights": [0.7, 0.3], "covariance": [[0.04, 0.012], [0.012, 0.09]]})
chk(f"volatility {eu['volatility']:.6f}")
chk("contributions " + ", ".join(f"{x:.6f}" for x in eu["contributions"]))
chk("shares " + ", ".join(f"{x:.6f}" for x in eu["shares"]))

# Q8.28 sbm_total
_, sb = rung("r6/sbm_total_r6.json", "sbm_total_r6-0001")
chk(f"capital {sb['capital']:,.2f}")
chk(f"sum_of_component_capitals {sb['sum_of_component_capitals']:,.2f}")

# Q8.29 vega
_, vg = rung("stage_f/frtb_f2c.json", "frtb_f2c-0001")
rho = math.exp(-0.01 * 4) * math.exp(-0.01 * 1)
chk(f"rho = {rho:.6f}")
chk(f"K_EUR = {vg['scenarios']['medium']['buckets'][0]['k']:,.2f}")
chk(f"vega capital {vg['capital']:,.2f}")

# Q8.30 curvature (tutorial 15 case)
cv = run("risk.frtb.curvature", {"risk_class": "GIRR", "factors": [
    {"bucket": "EUR", "cvr_up": 500_000.0, "cvr_down": 300_000.0},
    {"bucket": "USD", "cvr_up": -200_000.0, "cvr_down": 400_000.0}]})
chk(f"curvature capital {cv['capital']:,.2f}")
chk("selected " + ", ".join(f"{b['bucket']} {b['selected']}" for b in cv["scenarios"]["high"]["buckets"]))

# Q8.31 AAD vs bump (tutorial 5)
curve = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
deal = {"mean_reversion": 0.05, "sigma": 0.01, "curve": curve, "notional": 1_000_000.0, "start_years": 1.0,
        "payment_times": [2.0, 3.0, 4.0, 5.0, 6.0], "fixed_rate": 0.039462, "swaption_type": "PAYER",
        "exercise_times": [1.0, 2.0, 3.0, 4.0, 5.0], "grid": {"nx": 101, "steps_per_year": 50, "width": 6.0}}
aad = run("rates.shortrate.bermudan_ladder", deal)
hs = deal["sigma"] * 1e-4
up = run("rates.shortrate.bermudan_swaption", {**deal, "sigma": deal["sigma"] + hs})["price"]
dn = run("rates.shortrate.bermudan_swaption", {**deal, "sigma": deal["sigma"] - hs})["price"]
chk(f"price {aad['price']:,.4f}")
chk(f"AAD dV/dsigma {aad['d_price_d_sigma']:,.2f}")
chk(f"bump dV/dsigma {(up - dn) / (2 * hs):,.2f}")
chk(f"dV/da {aad['d_price_d_mean_reversion']:,.2f}")

# Q8.32 IFT limit case (risk_f3-0005)
bi, bk = rung("stage_f/risk_f3.json", "risk_f3-0005")
row = bk["quote_sensitivity"]["matrix"][0]
jmax = max(range(len(row)), key=lambda q: abs(row[q]))
chk(f"book_pv {abs(bk['book_pv']):.6f}")
chk(f"d pv / d q_5Y = {row[jmax]:.6f}")
chk(f"quote {bi['quotes'][jmax]['tenor']}")

# Q8.33 PCA
_, pc = rung("stage_f/risk_f3.json", "risk_f3-0010")
chk("explained_ratio " + ", ".join(f"{x:.6f}" for x in pc["explained_ratio"]))
chk("first loading " + ", ".join(f"{x:.4f}" for x in pc["loadings"][0]))
chk("second loading " + ", ".join(f"{x:.4f}" for x in pc["loadings"][1]))

# Q8.34 reverse stress
_, rs = rung("stage_f/risk_f4b.json", "risk_f4b-0001")
chk(f"scale {rs['scale']:.6f}")
chk(f"without gamma {50 / 1275:.6f}")

# Q8.35 MC Greeks (tutorial 15)
opt = {"spot": 100.0, "strike": 100.0, "expiry_years": 1.0, "rate": 0.03, "dividend_yield": 0.01, "vol": 0.2,
       "paths": 10_000, "seed": "20261109", "payoff": "CALL"}
pw = run("risk.mc.greeks", {**opt, "method": "PATHWISE"})
lr = run("risk.mc.greeks", {**opt, "method": "LIKELIHOOD_RATIO"})
chk(f"pathwise delta {pw['delta']:.6f} +- {pw['delta_se']:.6f}")
chk(f"likelihood-ratio delta {lr['delta']:.6f} +- {lr['delta_se']:.6f}")
chk(f"pathwise vega {pw['vega']:.4f} +- {pw['vega_se']:.4f}")
chk(f"likelihood-ratio vega {lr['vega']:.4f} +- {lr['vega_se']:.4f}")
nd = 0.5 * (1 + math.erf(0.2 / math.sqrt(2)))
chk(f"Black-Scholes delta {math.exp(-0.01) * nd:.6f}")

if "--dump" in sys.argv:
    print("\n".join(checks))
    sys.exit(0)
text = MD.read_text(encoding="utf-8")
missing = [s for s in checks if s not in text]
assert not missing, "missing in md:\n" + "\n".join(missing)
print(f"v08 OK: {len(checks)} checks")
