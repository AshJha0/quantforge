"""Recompute every worked-example number in 04-products-fx-inflation.md and check it is printed there.

Run from the repository's python directory:
  PYTHONPATH=. python ../docs/question-bank/verify/v04_products_fx_inflation.py
"""
import sys
from datetime import date
from pathlib import Path

from quantforge_core import (bonds, commodity, curves, equity, equity_curves, fx, inflation, mbs, ois,
                             sensitivities, xccy)
from quantforge_core.bonds import Bond
from quantforge_core.equity import ParityQuote
from quantforge_core.fx import FxForward, FxMarket, FxSwap
from quantforge_core.inflation import CpiCurveData, index
from quantforge_core.ois import OisTrade, Quote

MD = Path(__file__).resolve().parents[1] / "04-products-fx-inflation.md"
checks: list[str] = []
add = checks.append

AS_OF = date(2026, 11, 6)
QUOTES = [Quote("1Y", 0.035), Quote("2Y", 0.0335), Quote("3Y", 0.033),
          Quote("5Y", 0.0335), Quote("7Y", 0.0345), Quote("10Y", 0.036)]
sofr, _ = ois.bootstrap("SOFR", AS_OF, QUOTES, "LOG_LINEAR_DF")

# Swap (tutorial 1)
trade = OisTrade("SOFR", "5Y", 0.034, 10_000_000.0, "PAY")
val, par, ann = ois.pv(sofr, trade)
add(f"PV {val['pv']:.4f} USD")
add(f"par {par:.10f}")
add(f"annuity {ann:.6f}")
dv01, kr = sensitivities.dv01(AS_OF, QUOTES, "LOG_LINEAR_DF", trade)
add(f"DV01 {dv01:.4f}")
add(f"5Y key rate {kr[3]:.4f}")
add(f"{ann * 1e7 * 1e-4:.2f}")
recv = OisTrade("SOFR", "5Y", 0.034, 10_000_000.0, "RECEIVE")
add(f"RECEIVE PV {ois.pv(sofr, recv)[0]['pv']:.4f}")

# Bonds (tutorial 2)
bond = Bond(date(2029, 11, 15), 0.0425, 2)
settle = date(2026, 11, 9)
p = bonds.price_from_curve(bond, settle, sofr)
add(f"dirty {p['dirty']:.6f}")
add(f"accrued {p['accrued']:.6f}")
add(f"clean {p['clean']:.6f}")
y = bonds.yield_from_price(bond, settle, p["clean"])
r = bonds.price_from_yield(bond, settle, y["yield"])
add(f"yield {y['yield']:.10f}")
add(f"Macaulay {r['macaulay_duration']:.6f}")
add(f"modified {r['modified_duration']:.6f}")
add(f"convexity {r['convexity']:.6f}")
dy = 0.0010
up = bonds.price_from_yield(bond, settle, y["yield"] + dy)["dirty"]
approx = r["dirty"] * (1 - r["modified_duration"] * dy + 0.5 * r["convexity"] * dy * dy)
add(f"exact {up:.8f}")
add(f"approximation {approx:.8f}")

# Z-spread and asset swap
z = bonds.z_spread(bond, settle, sofr, p["clean"] - 1.0)
add(f"z_spread {z:.8f}")
add(f"{z * 1e4:.2f} bp")
asw_ann, asw = bonds.asset_swap(bond, settle, sofr, p["dirty"] - 1.0)
add(f"annuity {asw_ann:.6f}")
add(f"spread {asw:.8f}")

# FRN par identity
frn_mat = date(2029, 11, 9)
c = curves.build(sofr)
nxt = date(2027, 2, 9)
cur = (c.discount(settle) / c.discount(nxt) - 1) / ((nxt - settle).days / 360)
frn = bonds.frn_price(settle, frn_mat, 4, cur, 0.0, 0.0, sofr, sofr)
add(f"FRN dirty {frn['dirty']:.6f}")
frn2 = bonds.frn_price(settle, frn_mat, 4, cur, 0.0, 0.0050, sofr, sofr)
add(f"dm 50 bp dirty {frn2['dirty']:.6f}")

# Repo
fwd = bonds.repo_forward(bond, settle, date(2026, 12, 9), p["clean"], 0.0385, None)
add(f"forward dirty {fwd['forward_dirty']:.6f}")
add(f"forward clean {fwd['forward_clean']:.6f}")
add(f"interest {fwd['interest']:.6f}")
back = bonds.repo_implied(bond, settle, date(2026, 12, 9), p["clean"], fwd["forward_clean"])
add(f"implied repo {back:.10f}")
sp = bonds.repo_forward(bond, settle, date(2026, 12, 9), p["clean"], 0.0360, 0.0385)
add(f"special_spread {sp['special_spread']:.4f}")
add(f"specialness_value {sp['specialness_value']:.6f}")

# Conversion factor and futures basis
basket = [Bond(date(2034, 11, 15), 0.0425, 2), Bond(date(2035, 8, 15), 0.04, 2),
          Bond(date(2036, 2, 15), 0.045, 2)]
cfs = [bonds.conversion_factor(b, 2027, 3, 0.06, "TEN_YEAR") for b in basket]
for b, cf in zip(basket, cfs, strict=True):
    add(f"{b.maturity} CF {cf:.4f}")
cleans = [bonds.price_from_curve(b, settle, sofr)["clean"] for b in basket]
delivery = date(2027, 3, 31)
fwds = [bonds.repo_forward(b, settle, delivery, cl, 0.0385, None)["forward_clean"]
        for b, cl in zip(basket, cleans, strict=True)]
fut = round(min(f / cf for f, cf in zip(fwds, cfs, strict=True)) - 2 / 32, 6)
add(f"futures price {fut:.6f}")
out, ctd = bonds.futures_basis(fut, settle, delivery, 0.0385,
                               [(b, cl, cf) for b, cl, cf in zip(basket, cleans, cfs, strict=True)])
for o in out:
    add(f"implied repo {o['implied_repo']:.6f}, net basis {o['net_basis']:.6f}")
add(f"ctd {ctd}")

# Nelson-Siegel fit and rich/cheap
fit_bonds = [Bond(date(2028, 5, 15), 0.03, 2), Bond(date(2029, 11, 15), 0.0425, 2),
             Bond(date(2030, 8, 15), 0.0375, 2), Bond(date(2031, 11, 15), 0.035, 2),
             Bond(date(2033, 5, 15), 0.04, 2), Bond(date(2035, 11, 15), 0.045, 2)]
dirty = [bonds.price_from_curve(b, settle, sofr)["dirty"] for b in fit_bonds]
dirty[3] -= 0.30  # the 2031 bond is made 30 cents cheap
acc = [bonds.flows(b, settle).accrued for b in fit_bonds]
mkt_clean = [d - a for d, a in zip(dirty, acc, strict=True)]
mods = [bonds.price_from_yield(b, settle, bonds.yield_from_price(b, settle, cl)["yield"])["modified_duration"]
        for b, cl in zip(fit_bonds, mkt_clean, strict=True)]
w = [1 / m ** 2 for m in mods]
betas, res = bonds.fit_nelson_siegel(settle, 2.5, list(zip(fit_bonds, dirty, strict=True)), w)
add("betas " + ", ".join(f"{b:.6f}" for b in betas))
add(f"residual {res[3]:.6f}")
ym = bonds.yield_from_price(fit_bonds[3], settle, mkt_clean[3])["yield"]
yf = bonds.yield_from_price(fit_bonds[3], settle, mkt_clean[3] + res[3])["yield"]
add(f"yield_residual_bp {(ym - yf) * 1e4:.2f}")
add(f"largest other residual {max(abs(x) for i, x in enumerate(res) if i != 3):.6f}")

# FX
sonia, _ = ois.bootstrap("SONIA", AS_OF, [Quote("1Y", 0.0400), Quote("2Y", 0.0385),
                                          Quote("5Y", 0.0375)], "LOG_LINEAR_DF")
m = FxMarket("GBPUSD", 1.2800, AS_OF, sonia, sofr)
sd = fx.spot_date("GBPUSD", AS_OF)
add(f"spot date {sd}")
vd = date(2027, 11, 10)
f1, pts = fx.outright(m, vd)
add(f"forward {f1:.6f}")
add(f"points {pts:.2f}")
fv, delta = fx.forward_pv(m, FxForward(1_000_000.0, 1.2700, vd, "BUY"))
add(f"FX PV {fv['pv']:.2f} USD")
add(f"fx_delta {delta:.2f}")
swv, swd = fx.swap_pv(m, FxSwap(1_000_000.0, sd, 1.2800, vd, f1, "BUY"))
add(f"swap PV {swv['pv']:.2f}")
add(f"swap fx_delta {swd:.2f}")
nodes = fx.implied(m, [(12, -60.0)])
add(f"implied_ratio {nodes[0]['implied_ratio']:.8f}")
add(f"basis_bp {nodes[0]['basis_bp']:.2f}")

# NDF
ndf_off, _ = ois.bootstrap("SOFR", AS_OF, [Quote("1Y", 0.065), Quote("2Y", 0.064)], "LOG_LINEAR_DF")
npv, nf = xccy.ndf_pv(sofr, ndf_off, 83.50, date(2027, 5, 6), date(2027, 5, 10), 85.00,
                      1_000_000.0, "BUY", None)
add(f"NDF forward {nf:.6f}")
add(f"NDF PV {npv:.2f}")

# Inflation
cpi_data = CpiCurveData(index(2026, 8), 320.0, ((1, 0.025), (2, 0.026), (5, 0.0255)), None)
vals = inflation.cpi(cpi_data, [index(2028, 8), index(2027, 2)])
add(f"I(2028-08) = {vals[0]:.6f}")
add(f"I(2027-02) = {vals[1]:.6f}")
seas = (0.998, 0.999, 1.002, 1.003, 1.003, 1.002, 0.999, 1.000, 1.001, 0.999, 0.997, 0.997)
cpi_s = CpiCurveData(index(2026, 8), 320.0, ((1, 0.025), (2, 0.026), (5, 0.0255)), seas)
vs = inflation.cpi(cpi_s, [index(2028, 8), index(2027, 2)])
add(f"seasonal I(2028-08) = {vs[0]:.6f}")
add(f"seasonal I(2027-02) = {vs[1]:.6f}")
zpv, zr = inflation.zcis_pv(cpi_data, sofr, 5, 0.0250, 10_000_000.0, "RECEIVE_INFLATION",
                            date(2031, 11, 10))
add(f"index_ratio {zr:.8f}")
add(f"ZCIS PV {zpv:.2f}")
linker = Bond(date(2034, 7, 15), 0.0125, 2)
lk = inflation.linker_price(linker, date(2026, 11, 10), 0.018, 300.0,
                            [(index(2026, 8), 321.123456789), (index(2026, 9), 321.987654321)])
add(f"ref_cpi {lk['ref_cpi']:.5f}")
add(f"index_ratio {lk['index_ratio']:.5f}")
add(f"real_clean {lk['real_clean']:.6f}")
add(f"nominal_clean {lk['nominal_clean']:.6f}")

# Equity
add(f"F = {equity.flat(100.0, 0.04, 0.05, 1.0, [(0.5, 2.0)]):.7f}")
import math
add(f"wrong form {(100 - 2 * math.exp(-0.04 * 0.5)) * math.exp(-0.01):.7f}")
add(f"about {-math.log(0.70) / ((date(2036, 11, 6) - AS_OF).days / 365) * 100:.2f}% continuous")
pq = [ParityQuote(90, 12.10, 12.30, 1.95, 2.05), ParityQuote(100, 5.60, 5.80, 5.20, 5.30),
      ParityQuote(110, 1.85, 1.95, 11.20, 11.40)]
pf, pd, pres, outside = equity.parity(pq, None)
add(f"parity forward {pf:.6f}")
add(f"parity discount factor {pd:.6f}")
flat_funding = curves.CurveData(AS_OF, "LOG_LINEAR_DF", (date(2036, 11, 6),), (0.70,))
fwd_d, _ = curves.discount(flat_funding, [date(2027, 11, 6)])
pvd, per, yields = equity_curves.dividend_implied(4500.0, flat_funding, 0.0,
                                                 [(date(2027, 6, 18), 4560.0), (date(2027, 12, 17), 4600.0)])
add(f"pv_dividends {pvd[0]:.4f}, {pvd[1]:.4f}")
add(f"dividend_yields {yields[0]:.6f}, {yields[1]:.6f}")
b_imp = equity_curves.borrow_implied(50.0, flat_funding, [(date(2027, 3, 15), 0.50)],
                                     date(2027, 11, 5), 51.00)
add(f"borrow_rate {b_imp:.8f}")

# Commodities
cq = [(index(2027, 1), 3.80), (index(2027, 7), 3.20), (index(2028, 1), 3.90)]
add("flat " + ", ".join(f"{x:.6f}" for x in commodity.commodity_forwards(cq, None, [index(2027, 4)])))
season = (0.10, 0.08, 0.02, -0.04, -0.06, -0.05, -0.04, -0.04, -0.03, 0.00, 0.05, 0.09)
add("seasonal " + ", ".join(f"{x:.6f}" for x in commodity.commodity_forwards(cq, season, [index(2027, 4)])))
cy, cv, arb = commodity.storage_carry(sofr, [(date(2027, 1, 15), 75.0), (date(2027, 7, 15), 78.0)], 0.02)
add(f"convenience_yield {cy[0]:.6f}")
add(f"carry_value {cv[0]:.6f}")
add(f"arbitrage {arb[0]}")

# MBS
pool = (1_000_000.0, 0.065, 0.06, 360, 0, "PSA", 150.0)
fl = mbs.mbs_cashflows(pool)
add(f"wal {fl['wal']:.6f}")
add(f"month 1 prepayment {fl['prepayment'][0]:.4f}")
add(f"month 30 prepayment {fl['prepayment'][29]:.4f}")
pr0, md0, _ = mbs.mbs_price(pool, 0.06, 0)
pr25, md25, _ = mbs.mbs_price(pool, 0.06, 25)
add(f"price {pr0:.6f}")
add(f"delay 25 price {pr25:.6f}")
add(f"modified_duration {md25:.6f}")
fl100 = mbs.mbs_cashflows((1_000_000.0, 0.065, 0.06, 360, 0, "PSA", 100.0))
add(f"PSA 100 wal {fl100['wal']:.6f}")

if __name__ == "__main__":
    text = MD.read_text(encoding="utf-8") if MD.exists() else ""
    missing = [s for s in checks if s not in text]
    if missing:
        print("MISSING:")
        for s in missing:
            print("  " + s)
        sys.exit(1)
    print(f"v04 OK: {len(checks)} checks")
