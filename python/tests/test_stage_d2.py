"""Stage D waves 2 and 3 (D2 to D6): checks the golden suites do not make on their own."""
import json
import math
from datetime import date
from typing import Any

import pytest

from quantforge_core import bonds, credit, equity_curves, inflation, xccy
from quantforge_core.bonds import Bond
from quantforge_core.cli.main import run_case
from quantforge_core.curve_fits import _basis
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError
from quantforge_core.inflation import CpiCurveData

AS_OF = date(2026, 11, 6)
BOND = Bond(date(2029, 11, 15), 0.0425, 2)
SETTLE = date(2026, 11, 9)


def _flat(rate=0.03, as_of=AS_OF):
    ds = (date(2027, 11, 8), date(2031, 11, 6), date(2046, 11, 6))
    return CurveData(as_of, "LOG_LINEAR_DF", ds,
                     tuple(math.exp(-rate * (d - as_of).days / 365) for d in ds))


def _code(operation, inputs):
    document = {"schema_version": "1.0", "case_id": "t", "operation": operation,
                "inputs": inputs}
    out = run_case(json.dumps(document))
    out = out if isinstance(out, dict) else json.loads(out)
    return out["error"]["code"] if out.get("status") == "error" else "ok"


def _code_of(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


# D2 bonds and repo

def test_month_end_maturity_keeps_month_ends() -> None:
    prev, ds = bonds.dates_around(date(2031, 2, 28), 2, SETTLE)
    assert prev == date(2026, 8, 31) and ds[0] == date(2027, 2, 28) and ds[1] == date(2027, 8, 31)


def test_yield_round_trip_and_par_bond() -> None:
    p = bonds.price_from_yield(BOND, SETTLE, 0.041)
    assert bonds.yield_from_price(BOND, SETTLE, p["clean"])["yield"] == pytest.approx(0.041,
                                                                                       abs=1e-14)
    on_coupon = bonds.price_from_yield(BOND, date(2027, 5, 15), 0.0425)
    assert on_coupon["clean"] == pytest.approx(100, abs=1e-11) and on_coupon["accrued"] == 0
    assert bonds.yield_from_price(BOND, SETTLE, 300)["yield"] < 0


def test_duration_matches_bumped_price() -> None:
    p = bonds.price_from_yield(BOND, SETTLE, 0.04)
    h = 1e-6
    up, dn = (bonds.price_from_yield(BOND, SETTLE, 0.04 + s)["dirty"] for s in (h, -h))
    assert -(up - dn) / (2 * h) / p["dirty"] == pytest.approx(p["modified_duration"], rel=1e-7)


@pytest.mark.parametrize("f,args,code", [
    (bonds.price_from_yield, (BOND, date(2029, 11, 15), 0.04), "E_DATE_ORDER"),
    (bonds.price_from_yield, (BOND, SETTLE, -2.0), "E_DOMAIN"),
    (bonds.yield_from_price, (BOND, SETTLE, -1.0), "E_DOMAIN"),
    (bonds.price_from_curve, (BOND, date(2026, 11, 5), _flat()), "E_OUT_OF_RANGE"),
    (bonds.z_spread, (BOND, SETTLE, _flat(), -5.0), "E_DOMAIN"),
])
def test_bond_checks(f, args, code) -> None:
    assert _code_of(f, *args) == code


def test_z_spread_recovers_and_asset_swap_is_zero_at_curve_price() -> None:
    target = bonds.price_from_curve(BOND, SETTLE, _flat())
    assert bonds.z_spread(BOND, SETTLE, _flat(), target["clean"]) == pytest.approx(0, abs=1e-13)
    annuity, spread = bonds.asset_swap(BOND, SETTLE, _flat(), target["dirty"])
    assert annuity > 0 and spread == pytest.approx(0, abs=1e-15)


def test_frn_par_identity_on_one_curve() -> None:
    s, m = date(2026, 11, 16), date(2029, 11, 16)
    c = _flat()
    from quantforge_core import curves
    built = curves.build(c)
    e = date(2027, 2, 16)
    rate = (built.discount(s) / built.discount(e) - 1) / ((e - s).days / 360)
    out = bonds.frn_price(s, m, 4, rate, 0.0, 0.0, c, c)
    assert out["dirty"] == pytest.approx(100, abs=1e-11)


def test_repo_round_trip_and_checks() -> None:
    f: dict[str, Any] = bonds.repo_forward(BOND, SETTLE, date(2027, 6, 1), 100.4, 0.0385, 0.04)
    assert f["special_spread"] == pytest.approx(0.0015)
    r = bonds.repo_implied(BOND, SETTLE, date(2027, 6, 1), 100.4, f["forward_clean"])
    assert r == pytest.approx(0.0385, abs=1e-14)
    assert _code_of(bonds.repo_forward, BOND, SETTLE, SETTLE, 100, 0.03, None) == "E_DATE_ORDER"
    assert _code_of(bonds.repo_forward, BOND, SETTLE, BOND.maturity, 100, 0.03, None) == "E_INPUT"


def test_conversion_factor_checks_and_six_percent_bond() -> None:
    assert bonds.conversion_factor(Bond(date(2036, 12, 1), 0.06, 2), 2026, 12, 0.06) == 1.0
    assert _code_of(bonds.conversion_factor, BOND, 2026, 12, 0.05) == "E_INPUT"
    assert _code_of(bonds.conversion_factor, Bond(BOND.maturity, 0.04, 1), 2026, 12,
                    0.06) == "E_INPUT"


def test_futures_basis_ctd_and_empty() -> None:
    rows, ctd = bonds.futures_basis(104, SETTLE, date(2026, 12, 1), 0.0385,
                                    [(BOND, 100.6, 0.95), (BOND, 100.6, 0.97)])
    assert ctd == 1 and rows[1]["implied_repo"] > rows[0]["implied_repo"]
    assert _code_of(bonds.futures_basis, 104, SETTLE, date(2026, 12, 1), 0.0385, []) == "E_INPUT"


def test_nelson_siegel_recovers_truth_and_checks() -> None:
    truth = [0.04, -0.01, 0.005]
    bs = [Bond(date(2028 + k, 11, 15), 0.04, 2) for k in range(5)]
    prices: list[float] = []
    for b in bs:
        fl = bonds.flows(b, SETTLE)
        prices.append(sum(cf * math.exp(-t * sum(x * y for x, y in zip(
            truth, _basis(t, 2.0), strict=True))) for d, cf in zip(fl.dates, fl.amounts,
                                                                          strict=True)
            for t in ((d - SETTLE).days / 365,)))
    betas, res = bonds.fit_nelson_siegel(SETTLE, 2.0, list(zip(bs, prices, strict=True)), None)
    assert betas == pytest.approx(truth, abs=1e-9) and max(map(abs, res)) < 1e-8
    pairs = list(zip(bs, prices, strict=True))
    assert _code_of(bonds.fit_nelson_siegel, SETTLE, 2.0, pairs, [1, 1, 0, 0, 0]) == "E_INPUT"
    assert _code_of(bonds.fit_nelson_siegel, SETTLE, 2.0, pairs, [1, 1, 1, 1, -1]) == "E_DOMAIN"
    assert _code_of(bonds.fit_nelson_siegel, SETTLE, 0.0, pairs, None) == "E_DOMAIN"


def test_bond_frequency_and_null_keys_are_schema() -> None:
    b = {"maturity": "2029-11-15", "coupon": 0.04, "frequency": 3}
    assert _code("bond.price.from_yield", {"bond": b, "settlement": "2026-11-09",
                                           "yield": 0.04}) == "E_SCHEMA"
    good = {**b, "frequency": 2}
    base = {"bond": good, "start": "2026-11-09", "end": "2026-12-09", "clean_price": 100,
            "repo_rate": 0.03}
    assert _code("repo.forward", base) == "E_SCHEMA"
    assert _code("repo.forward", {**base, "gc_rate": None}) == "ok"


# D3 cross-currency and NDF

START = date(2026, 11, 10)


def test_xccy_schedule_and_checks() -> None:
    ends = xccy.schedule(("SOFR", "ESTR"), START, 12)
    assert len(ends) == 4 and all(e.weekday() < 5 for e in ends)
    assert _code_of(xccy.schedule, ("SOFR", "ESTR"), START, 10) == "E_INPUT"
    assert _code_of(xccy.schedule, ("SOFR", "ESTR"), date(2026, 11, 11), 12) == "E_INPUT"


def test_xccy_bootstrap_reprices_and_zero_spread_pv() -> None:
    quotes = [(12, 0.001), (24, 0.0015)]
    data, error = xccy.bootstrap(_flat(), _flat(0.02), "SOFR", "ESTR", START, quotes,
                                 "LOG_LINEAR_DF")
    assert error < 1e-13
    foreign, dom, _pv = xccy.pv(_flat(), _flat(0.02), data, 1.1, START, 24, 1e6, 0.0015,
                               "RECEIVE_FOREIGN")
    assert foreign == pytest.approx(0, abs=1e-6) and dom == pytest.approx(0, abs=1e-6)
    assert _code_of(xccy.bootstrap, _flat(), _flat(), "SOFR", "ESTR", START,
                    [(24, 0.0), (12, 0.0)], "LOG_LINEAR_DF") == "E_INPUT"


def test_ndf_checks_and_fixing() -> None:
    args = (_flat(), _flat(0.05), 88.0)
    pv, f = xccy.ndf_pv(*args, date(2027, 5, 6), date(2027, 5, 10), 90.0, 1e6, "BUY", 92.0)
    assert f == 92.0 and pv > 0
    assert _code_of(xccy.ndf_pv, *args, date(2027, 5, 10), date(2027, 5, 6), 90.0, 1e6, "BUY",
                    None) == "E_DATE_ORDER"
    assert _code_of(xccy.ndf_pv, *args, AS_OF, date(2027, 5, 6), 90.0, 1e6, "BUY",
                    None) == "E_INPUT"
    assert _code_of(xccy.ndf_pv, *args, date(2027, 5, 6), date(2027, 5, 6), 0.0, 1e6, "BUY",
                    None) == "E_DOMAIN"


# D4 credit

def test_cds_dates() -> None:
    assert credit.maturity(AS_OF, "5Y") == date(2031, 12, 20)
    assert credit.maturity(date(2026, 3, 19), "6M") == date(2026, 6, 20)
    assert _code_of(credit.periods, date(2026, 12, 21), date(2031, 12, 20)) == "E_INPUT"


def test_cds_bootstrap_reprices_and_flat_hazard_identity() -> None:
    quotes = [("1Y", 0.006), ("5Y", 0.012)]
    pillars = credit.bootstrap(AS_OF, _flat(), 0.4, quotes)
    hz = credit.check_hazard(AS_OF, [d for d, _ in pillars], [q for _, q in pillars])
    for tenor, spread in quotes:
        out = credit.price(AS_OF, _flat(), hz, 0.4, credit.maturity(AS_OF, tenor), 0.01, 1.0,
                           "BUY_PROTECTION", "STANDARD")
        assert out["par_spread"] == pytest.approx(spread, abs=1e-13)
    digital = credit.price(AS_OF, _flat(), hz, 0.4, credit.maturity(AS_OF, "5Y"), 0.01, 1.0,
                           "BUY_PROTECTION", "DIGITAL")
    standard = credit.price(AS_OF, _flat(), hz, 0.4, credit.maturity(AS_OF, "5Y"), 0.01, 1.0,
                            "BUY_PROTECTION", "STANDARD")
    assert digital["protection_leg"] == pytest.approx(standard["protection_leg"] / 0.6)


@pytest.mark.parametrize("recovery,quotes,code", [
    (1.0, [("1Y", 0.01)], "E_DOMAIN"),
    (-0.1, [("1Y", 0.01)], "E_DOMAIN"),
    (0.4, [("5Y", 0.01), ("1Y", 0.01)], "E_INPUT"),
    (0.4, [("1Y", 0.0)], "E_DOMAIN"),
    (0.4, [], "E_INPUT"),
])
def test_cds_bootstrap_checks(recovery, quotes, code) -> None:
    assert _code_of(credit.bootstrap, AS_OF, _flat(), recovery, quotes) == code


def test_index_and_composite() -> None:
    hz = credit.check_hazard(AS_OF, [date(2031, 12, 20)], [0.9])
    ups, intrinsic, basis = credit.index_intrinsic(AS_OF, _flat(), [(hz, 0.4, 1.0), (hz, 0.4, 3.0)],
                                                   date(2031, 12, 20), 0.01, 0.0)
    assert intrinsic == pytest.approx(ups[0]) and basis == -intrinsic
    assert _code_of(credit.index_intrinsic, AS_OF, _flat(), [], date(2031, 12, 20), 0.01,
                    0.0) == "E_INPUT"
    q = [("1Y", 0.01), ("5Y", 0.02)]
    spreads, _ = credit.composite(AS_OF, _flat(), 0.4, [(q, 1.0), (q, 1.0)], 2.0)
    assert spreads == pytest.approx([0.02, 0.04])
    assert _code_of(credit.composite, AS_OF, _flat(), 0.4, [(q, 1.0), (q[:1], 1.0)],
                    1.0) == "E_INPUT"
    assert _code_of(credit.composite, AS_OF, _flat(), 0.4, [(q, 1.0)], 0.0) == "E_DOMAIN"


def test_hazard_checks() -> None:
    assert _code_of(credit.check_hazard, AS_OF, [AS_OF], [0.9]) == "E_INPUT"
    assert _code_of(credit.check_hazard, AS_OF, [date(2027, 1, 1)], [0.0]) == "E_DOMAIN"


# D5 equity

DIVS = [(date(2026, 12, 18), 18.0), (date(2027, 3, 19), 16.5)]


def test_implied_dividends_recover_known_and_checks() -> None:
    expiry = date(2027, 3, 19)
    _, f = 0, equity_curves._forward
    from quantforge_core import curves
    c = curves.build(_flat())
    price = f(5000, c, 0.003, 0.0, DIVS, expiry)
    xs, periods, _ = equity_curves.dividend_implied(5000, _flat(), 0.003, [(expiry, price)])
    assert periods == xs
    assert equity_curves.borrow_implied(5000, _flat(), DIVS, expiry, price) == pytest.approx(
        0.003, abs=1e-14)
    assert _code_of(equity_curves.dividend_implied, 5000, _flat(), 0.0, [(AS_OF, 1.0)]) == "E_INPUT"
    assert _code_of(equity_curves.dividend_implied, 5000, _flat(), 0.0, [(expiry, 0.0)]) == "E_DOMAIN"
    assert _code_of(equity_curves.borrow_implied, 5000, _flat(), DIVS, expiry,
                    1e6) == "E_NOT_BRACKETED"


def test_futures_basis_zero_at_fair_and_checks() -> None:
    assert _code_of(equity_curves.futures_basis, 5000, _flat(), 0.003, 0.001, DIVS,
                    date(2027, 6, 1), 1.0) == "E_NOT_BRACKETED"
    from quantforge_core import curves
    fair = equity_curves._forward(5000, curves.build(_flat()), 0.003, 0.001, DIVS, date(2027, 6, 1))
    fair2, basis2, s2 = equity_curves.futures_basis(5000, _flat(), 0.003, 0.001, DIVS,
                                               date(2027, 6, 1), fair)
    assert basis2 == 0 and s2 == pytest.approx(0.001, abs=1e-14) and fair2 == fair
    assert _code_of(equity_curves.futures_basis, 5000, _flat(), 0.0, 0.0, [], AS_OF,
                    1.0) == "E_DATE_ORDER"


def test_index_ops() -> None:
    cons = [("A", 10.0, 5.0, [(date(2027, 1, 1), 1.0)]), ("B", 5.0, 4.0, [(date(2027, 1, 1), 2.0)])]
    out = equity_curves.index_dividends(10.0, cons, [(date(2027, 1, 1), date(2027, 1, 1))], [3.0])
    assert out["points"] == [2.0] and out["period_points"] == [2.0] and out["basis"] == [1.0]
    level, divisor, w = equity_curves.rebalance(10.0, [("A", 10.0, 5.0)], [("A", 5.0, 5.0),
                                                                       ("B", 5.0, 5.0)])
    assert level == 5.0 and divisor == 10.0 and w == [0.5, 0.5]
    assert _code_of(equity_curves.rebalance, 10.0, [("A", 1.0, 1.0), ("A", 1.0, 1.0)], []) == "E_INPUT"
    assert _code_of(equity_curves.index_dividends, 10.0, cons, [], [1.0]) == "E_INPUT"


@pytest.mark.parametrize("action,params", [
    ("RIGHTS", {"new_per_old": 0.0, "subscription_price": 1.0}),
    ("RIGHTS", {"new_per_old": 1.0, "subscription_price": -1.0}),
    ("SPECIAL_DIVIDEND", {"amount": 0.0}),
    ("REVERSE_SPLIT", {"ratio": -1.0}),
])
def test_corporate_action_domain(action, params) -> None:
    assert _code_of(equity_curves.corporate_action, action, 100.0, 1.0, 1.0, params) == "E_DOMAIN"


def test_trs_at_inception_on_flat_curve_and_checks() -> None:
    e, f, pv = equity_curves.trs_pv(5000, _flat(), 0.0, [], AS_OF, date(2027, 11, 8), 5000, 1.0, 0.0,
                               "RECEIVE_EQUITY", None)
    assert pv == pytest.approx(0, abs=1e-8) and e == pytest.approx(f)
    assert _code_of(equity_curves.trs_pv, 5000, _flat(), 0.0, [], date(2026, 9, 1), date(2027, 3, 1),
                    5000, 1.0, 0.0, "RECEIVE_EQUITY", None) == "E_INPUT"


# D6 inflation

CPI = CpiCurveData(inflation.index(2026, 8), 300.0, ((1, 0.02), (2, 0.025)), None)


def test_cpi_pillars_reprice_with_and_without_seasonality() -> None:
    season = tuple(1 + 0.001 * k for k in range(12))
    for data in (CPI, CpiCurveData(CPI.base, 300.0, CPI.quotes, season)):
        assert inflation.cpi(data, [CPI.base + 12])[0] == pytest.approx(306.0, rel=1e-15)
        assert inflation.cpi(data, [CPI.base + 24])[0] == pytest.approx(300 * 1.025 ** 2,
                                                                        rel=1e-15)


@pytest.mark.parametrize("quotes,season,code", [
    (((1, 0.02), (1, 0.03)), None, "E_INPUT"),
    (((1.5, 0.02),), None, "E_INPUT"),
    (((1, -1.0),), None, "E_DOMAIN"),
    (((1, 0.02),), (1.0,) * 11, "E_INPUT"),
    (((1, 0.02),), (1.0,) * 11 + (0.0,), "E_DOMAIN"),
])
def test_cpi_checks(quotes, season, code) -> None:
    assert _code_of(inflation.cpi, CpiCurveData(CPI.base, 300.0, quotes, season),
                    [CPI.base]) == code
    assert _code_of(inflation.cpi, CPI, [CPI.base - 1]) == "E_OUT_OF_RANGE"


def test_zcis_at_market_is_zero_and_linker_ratio() -> None:
    pv, ratio = inflation.zcis_pv(CPI, _flat(), 2, 0.025, 1e6, "RECEIVE_INFLATION",
                                  date(2028, 11, 10))
    assert pv == pytest.approx(0, abs=1e-8) and ratio == pytest.approx(1.025 ** 2)
    fixings = [(inflation.index(2026, 8), 300.0), (inflation.index(2026, 9), 301.0)]
    out = inflation.linker_price(BOND, SETTLE, 0.02, 300.0, fixings)
    assert out["ref_cpi"] == pytest.approx(300 + 8 / 30)
    assert out["nominal_clean"] == pytest.approx(out["real_clean"] * out["index_ratio"])
    assert _code_of(inflation.linker_price, BOND, date(2027, 3, 9), 0.02, 300.0,
                    fixings) == "E_INPUT"


def test_linker_from_curve_reference_month_checks() -> None:
    early = CpiCurveData(inflation.index(2026, 10), 300.0, CPI.quotes, None)
    assert _code_of(inflation.linker_price_curve, BOND, SETTLE, 300.0, early,
                    _flat()) == "E_OUT_OF_RANGE"
    assert inflation.linker_price_curve(BOND, SETTLE, 300.0, CPI, _flat()) > 100
