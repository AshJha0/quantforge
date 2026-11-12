"""Paths changed to make the package mypy clean: behaviour must be unchanged."""
import math
from datetime import date

import pytest

from quantforge_core import compounding, daycount, interp, ois, roots
from quantforge_core.errors import QfError, required


def test_required_passes_values_and_rejects_none() -> None:
    assert required(0.0, "x") == 0.0
    with pytest.raises(QfError) as e:
        required(None, "x")
    assert e.value.code == "E_SCHEMA" and e.value.field == "x"


def test_periodic_compounding_round_trip() -> None:
    c = compounding.Compounding("PERIODIC", 2)
    d = compounding.discount_factor(0.05, 2.0, c)
    assert d == pytest.approx(1.025 ** -4)
    cont = compounding.Compounding("CONTINUOUS")
    assert compounding.convert(0.05, 2.0, c, cont) == pytest.approx(2 * math.log(1.025))
    with pytest.raises(QfError):
        compounding.discount_factor(-3.0, 1.0, c)


def test_daycount_icma_and_bus252() -> None:
    rs, re_ = date(2026, 5, 15), date(2026, 11, 15)
    assert daycount.year_fraction("ACT_ACT_ICMA", rs, date(2026, 8, 15), 2, rs, re_) == \
        pytest.approx(92 / (2 * 184))
    with pytest.raises(QfError) as e:
        daycount.year_fraction("ACT_ACT_ICMA", date(2026, 1, 1), re_, 2, rs, re_)
    assert e.value.code == "E_INPUT"
    assert daycount.year_fraction("BUS_252", date(2026, 11, 9), date(2026, 11, 16),
                                  calendar="GBLO") == 5 / 252


def test_interp_clamped_and_tension() -> None:
    x, y = [0.0, 1.0, 2.0], [0.0, 1.0, 4.0]
    values, slopes = interp.evaluate("cubic_clamped", x, y, [2.0], 0.0, 4.0)
    assert values == pytest.approx([4.0]) and slopes == pytest.approx([4.0])
    zero, _ = interp.evaluate("tension", x, y, [0.5], tension=0.0)
    natural, _ = interp.evaluate("cubic_natural", x, y, [0.5])
    assert zero == natural
    with pytest.raises(QfError) as e:
        interp.evaluate("tension", x, y, [0.5], tension=-1.0)
    assert e.value.code == "E_DOMAIN"


def test_quote_mid_and_bid_ask_check() -> None:
    assert ois.Quote("1Y", None, 0.01, 0.03).mid == pytest.approx(0.02)
    assert ois.Quote("1Y", 0.05).mid == 0.05
    with pytest.raises(QfError) as e:
        ois.bootstrap("SOFR", date(2026, 11, 6), [ois.Quote("1Y", None, 0.03, 0.01)],
                      "LOG_LINEAR_DF")
    assert e.value.code == "E_INPUT"


def test_newton_bracketed_and_open():
    def f(x):
        return x * x - 2

    def df(x):
        return 2 * x

    assert roots.newton(f, df, 1.0).root == pytest.approx(math.sqrt(2))
    assert roots.newton(f, df, 1.9, 0.0, 2.0).root == pytest.approx(math.sqrt(2))
    for args, code in (((1.0, 2.0, 0.0), "E_INPUT"), ((5.0, 0.0, 2.0), "E_INPUT"),
                       ((1.0, 2.0, 3.0), "E_NOT_BRACKETED")):
        with pytest.raises(QfError) as e:
            roots.newton(f, df, *args)
        assert e.value.code == code
    with pytest.raises(QfError) as e:
        roots.newton(f, df, 1.0, 0.0, None)
    assert e.value.code == "E_SCHEMA"
