"""Stage F waves 2 and 3: limit cases from the specs."""
from datetime import date

from quantforge_core import book, book_risk, var_risk
from quantforge_core.ois import Quote

AS_OF = date(2026, 11, 10)
QUOTES = [Quote(t, r) for t, r in (("1M", 0.043), ("1Y", 0.039), ("2Y", 0.0365), ("5Y", 0.0352),
                                   ("10Y", 0.0364))]


def test_par_payer_limit() -> None:
    """A payer at par: pv 0, d pv / d own quote = its annuity (book-sensitivities.md)."""
    from quantforge_core import curves, ois
    data, _ = ois.bootstrap("SOFR", AS_OF, QUOTES, "LOG_LINEAR_DF")
    curve = curves.build(data)
    ps = ois.periods("SOFR", AS_OF, "5Y")
    annuity, floating = ois.legs("SOFR", ps, curve)
    swap = book_risk.BookSwap("P", 5, floating / annuity, "PAYER")
    out = book_risk.ois_sensitivity(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", [swap])
    assert abs(out["pv"][0]) < 1e-15  # type: ignore[index]
    row = out["quote_sensitivity"]["matrix"][0]  # type: ignore[index]
    assert abs(row[3] - annuity) < 1e-12
    assert all(abs(v) < 1e-12 for j, v in enumerate(row) if j != 3)


def test_zero_jacobian_upper_triangle_exact() -> None:
    out = book_risk.ois_sensitivity(AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF",
                                    [book_risk.BookSwap("A", 3, 0.04, "RECEIVER")])
    m = out["zero_jacobian"]["matrix"]  # type: ignore[index]
    assert all(m[i][j] == 0.0 for i in range(len(m)) for j in range(i + 1, len(m)))


def test_parametric_median_limit() -> None:
    assert abs(var_risk.parametric(3.0, 2.0, 0.5)["var"] + 3.0) < 1e-15  # type: ignore[operator]


def test_kupiec_zero_lr_at_expected_count() -> None:
    out = var_risk.kupiec(1000, 10, 0.99)
    assert out == {"lr_uc": 0.0, "p_value": 1.0}


def test_traffic_light_zones() -> None:
    zones = [var_risk.traffic_light(250, x, 0.99)["zone"] for x in (4, 5, 9, 10)]
    assert zones == ["GREEN", "YELLOW", "YELLOW", "RED"]


def test_girr_one_tenor() -> None:
    out = var_risk.girr_delta([("USD", "SOFR", "5Y", -2e6)], False, None)
    assert out["capital"] == 0.011 * 2e6 and out["binding_scenario"] == "high"


def test_reversal_opens_at_trade_price() -> None:
    events = [book.Event(AS_OF, "TRADE", "X", 10.0, 100.0),
              book.Event(AS_OF, "TRADE", "X", -15.0, 104.0)]
    out = book.lifecycle_apply([], events)
    assert out["positions"] == [{"instrument": "X", "quantity": -5.0, "average_cost": 104.0}]
    assert out["total_realized"] == 40.0


def test_attribution_identity() -> None:
    f = [[0.01 * k, 0.003 * (k % 3)] for k in range(12)]
    y = [0.002 + 0.5 * a - 0.2 * b + 0.0001 * (k % 2) for k, (a, b) in enumerate(f)]
    out = book.factor_attribution(y, f, ["A", "B"])
    total = out["alpha"] + sum(out["contributions"])  # type: ignore[arg-type,operator]
    assert abs(total - out["mean_return"]) < 1e-15  # type: ignore[operator]
