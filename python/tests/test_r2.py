"""R2: par and key-rate risk, the Jacobian, P&L explain (06-risk/par-and-key-rate.md, pnl-explain.md)."""
from datetime import date

import pytest

from quantforge_core import risk_curve as R
from quantforge_core.bonds import Bond
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError
from quantforge_core.ois import OisTrade, Quote

AS_OF = date(2026, 1, 6)
QUOTES = [Quote("1Y", 0.035), Quote("2Y", 0.034), Quote("5Y", 0.036), Quote("10Y", 0.038)]


def _ois(side="RECEIVE", tenor="5Y", notional=1e7):
    return R.Product("OIS", trade=OisTrade("SOFR", tenor, 0.036, notional, side))


BOND = R.Product("BOND", bond=Bond(date(2031, 2, 15), 0.04, 2), settlement=AS_OF, notional=1e6)


def _code(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.field


def test_par_signs_and_bucket_sum():
    rec = R.par(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", _ois(), 1.0, "CENTRAL")
    pay = R.par(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", _ois("PAY"), 1.0, "CENTRAL")
    assert rec["par_dv01"] < 0 < pay["par_dv01"]
    assert rec["par_dv01"] == pytest.approx(-pay["par_dv01"], rel=1e-12)
    assert sum(rec["par_buckets"]) == pytest.approx(rec["par_dv01"], rel=1e-4)
    # a 5Y swap has no exposure to the 10Y quote, and most to the 5Y one
    assert rec["par_buckets"][3] == 0.0
    assert abs(rec["par_buckets"][2]) == max(abs(b) for b in rec["par_buckets"])
    fwd = R.par(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", _ois(), 1.0, "FORWARD")
    assert fwd["par_dv01"] == pytest.approx(rec["par_dv01"], rel=1e-3)


def test_bond_risk_is_negative_and_scales_with_notional():
    a = R.par(AS_OF, "SOFR", QUOTES, "LINEAR_ZERO", BOND, 1.0, "CENTRAL")
    big = R.Product("BOND", bond=BOND.bond, settlement=AS_OF, notional=2e6)
    b = R.par(AS_OF, "SOFR", QUOTES, "LINEAR_ZERO", big, 1.0, "CENTRAL")
    assert a["par_dv01"] < 0
    assert b["value"] == pytest.approx(2 * a["value"], rel=1e-14)
    assert b["par_dv01"] == pytest.approx(2 * a["par_dv01"], rel=1e-12)


def _curve():
    return CurveData(AS_OF, "LOG_LINEAR_DF", (date(2027, 1, 6), date(2031, 1, 6), date(2036, 1, 6)),
                     (0.965, 0.84, 0.69))


@pytest.mark.parametrize("mode,keys", [
    ("TRIANGULAR", [date(2027, 1, 6), date(2029, 1, 6), date(2033, 1, 6)]),
    ("TRIANGULAR", [date(2030, 1, 6)]),
    ("PILLAR", None),
])
def test_key_rates_sum_to_zero_dv01(mode, keys):
    out = R.key_rate(_curve(), mode, keys, _ois(), 1.0, "CENTRAL")
    assert sum(out["key_rates"]) == pytest.approx(out["zero_dv01"], rel=1e-6)
    assert len(out["key_rates"]) == (len(keys) if keys else 3)


def test_triangle_weights_sum_to_one():
    keys = [1.0, 3.0, 7.0]
    for t in (0.0, 0.5, 1.0, 2.2, 3.0, 5.0, 7.0, 30.0):
        assert sum(R._triangle(keys, i)(t) for i in range(3)) == pytest.approx(1.0, abs=1e-15)


def test_jacobian_is_lower_triangular_with_unit_diagonal_scale():
    out = R.jacobian(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", 1.0)
    j = out["jacobian"]
    assert all(j[i][k] == 0.0 for i in range(4) for k in range(i + 1, 4))
    assert all(0.5 < j[i][i] < 2.0 for i in range(4))
    assert len(out["pillar_dates"]) == len(out["zero_rates"]) == 4


def test_par_from_zero_chain_rule():
    par = R.par(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", _ois(), 1.0, "CENTRAL")
    jac = R.jacobian(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", 1.0)
    from quantforge_core.ois import bootstrap
    data = bootstrap("SOFR", AS_OF, QUOTES, "LOG_LINEAR_DF")[0]
    keys = R.key_rate(data, "PILLAR", None, _ois(), 1.0, "CENTRAL")["key_rates"]
    for k in range(4):
        implied = sum(keys[i] * jac["jacobian"][i][k] for i in range(4))
        assert implied == pytest.approx(par["par_buckets"][k], abs=1e-3 * abs(par["par_dv01"]))


def test_pnl_explain_small_and_zero_moves():
    end = [Quote(q.tenor, q.mid + 0.0001) for q in QUOTES]
    out = R.pnl_explain(AS_OF, "SOFR", "LOG_LINEAR_DF", QUOTES, end, _ois(), 1.0)
    assert out["explained"] is True
    assert out["full_pnl"] == pytest.approx(out["risk_pnl"], rel=1e-3)
    assert out["gross_risk_pnl"] >= abs(out["risk_pnl"])
    assert out["threshold"] == pytest.approx(
        0.05 * max(abs(out["full_pnl"]), out["gross_risk_pnl"]) + 1e-8 * 1e7)
    still = R.pnl_explain(AS_OF, "SOFR", "LOG_LINEAR_DF", QUOTES, QUOTES, _ois(), 1.0)
    assert still["full_pnl"] == still["risk_pnl"] == still["gross_risk_pnl"] == 0.0
    assert still["threshold"] == pytest.approx(0.1) and still["explained"]


def test_pnl_explain_large_move_on_long_bond_fails():
    end = [Quote(q.tenor, q.mid + 0.015) for q in QUOTES]
    long_bond = R.Product("BOND", bond=Bond(date(2035, 8, 15), 0.0425, 2), settlement=AS_OF,
                          notional=1e6)
    out = R.pnl_explain(AS_OF, "SOFR", "LOG_LINEAR_DF", QUOTES, end, long_bond, 1.0)
    assert out["full_pnl"] < 0 and abs(out["unexplained"]) > 0


def test_checks_and_their_order():
    assert _code(R.par, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", _ois(), 0.0, "CENTRAL")[0] == "E_DOMAIN"
    assert _code(R.par, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", _ois(), 101.0, "CENTRAL")[0] == "E_DOMAIN"
    bad = R.Product("BOND", bond=BOND.bond, settlement=AS_OF, notional=0.0)
    assert _code(R.par, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", bad, 1.0, "CENTRAL")[0] == "E_DOMAIN"
    estr = R.Product("OIS", trade=OisTrade("ESTR", "5Y", 0.03, 1e7, "PAY"))
    assert _code(R.par, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", estr, 1.0, "CENTRAL")[0] == "E_INPUT"
    # bump_bp is checked before the convention
    assert _code(R.par, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", estr, -1.0, "CENTRAL")[0] == "E_DOMAIN"
    assert _code(R.key_rate, _curve(), "PILLAR", [date(2027, 1, 6)], _ois(), 1.0,
                 "CENTRAL")[1] == "key_dates"
    assert _code(R.key_rate, _curve(), "TRIANGULAR", [], _ois(), 1.0, "CENTRAL")[1] == "key_dates"
    assert _code(R.key_rate, _curve(), "TRIANGULAR", [date(2029, 1, 1), date(2028, 1, 1)], _ois(),
                 1.0, "CENTRAL")[1] == "key_dates"
    other = [Quote("1Y", 0.035), Quote("3Y", 0.034), Quote("5Y", 0.036), Quote("10Y", 0.038)]
    assert _code(R.pnl_explain, AS_OF, "SOFR", "LOG_LINEAR_DF", QUOTES, other, _ois(),
                 1.0) == ("E_INPUT", "quotes_end")
    assert _code(R.jacobian, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", 0.0)[0] == "E_DOMAIN"
