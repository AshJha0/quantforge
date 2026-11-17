"""Unit tests for quantforge_core.correlation (06-risk/correlation.md, rulings E-B18 to E-B21,
E-B31, E-B33, E-B39). Implied correlation and dispersion are worked by hand; the nearest
correlation case is Higham's 3x3 example (IMA J. Numer. Anal. 22, 2002)."""

import math

import pytest

from quantforge_core import correlation as c
from quantforge_core.errors import QfError


def _err(fn, code: str, field: str) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    # the message is a readable sentence, not a placeholder or shouting (kills the
    # message-text mutants, which no code or field check can see)
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()


def test_validate_flags() -> None:
    ok = c.validate([[1.0, 0.5], [0.5, 1.0]])
    assert ok["valid"] is True and ok["psd"] is True
    assert ok["min_eigenvalue"] == pytest.approx(0.5)
    asym = c.validate([[1.0, 0.5], [0.4, 1.0]])
    assert asym["symmetric"] is False and asym["valid"] is False
    assert asym["min_eigenvalue"] == pytest.approx(0.55)
    diag = c.validate([[1.0, 0.0], [0.0, 0.9]])
    assert diag["unit_diagonal"] is False and diag["valid"] is False
    rng = c.validate([[1.0, 1.5], [1.5, 1.0]])
    assert rng["in_range"] is False and rng["psd"] is False
    assert rng["min_eigenvalue"] == pytest.approx(-0.5)
    edge = c.validate([[1.0, 1.0], [1.0, 1.0]])
    assert edge["in_range"] is True and edge["valid"] is True
    assert c.validate([[1.0, -1.0], [-1.0, 1.0]])["valid"] is True
    npsd = c.validate([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]])
    assert npsd["psd"] is False and npsd["in_range"] is True and npsd["valid"] is False
    _err(lambda: c.validate([]), "E_INPUT", "matrix")
    _err(lambda: c.validate([[1.0, 0.0]]), "E_INPUT", "matrix")


def test_nearest_higham_example() -> None:
    y, dist = c.nearest([[1.0, 1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0]])
    assert y[0][1] == pytest.approx(0.7607, abs=1e-4)
    assert y[0][2] == pytest.approx(0.1573, abs=1e-4)
    assert y[1][2] == pytest.approx(0.7607, abs=1e-4)
    assert all(y[i][i] == 1.0 for i in range(3))
    expect = math.sqrt(4 * (1 - y[0][1]) ** 2 + 2 * y[0][2] ** 2)
    assert dist == pytest.approx(expect)
    assert dist == pytest.approx(0.5278, abs=1e-4)
    same, d0 = c.nearest([[1.0, 0.3], [0.3, 1.0]])
    assert (
        same[0] == pytest.approx([1.0, 0.3])
        and same[1] == pytest.approx([0.3, 1.0])
        and d0 == pytest.approx(0.0, abs=1e-12)
    )
    _err(lambda: c.nearest([[1.0, 0.2], [0.3, 1.0]]), "E_INPUT", "matrix")
    _err(lambda: c.nearest([[1.0], [1.0]]), "E_INPUT", "matrix")


def test_nearest_no_convergence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "_MAX_SWEEPS", 1)
    _err(
        lambda: c.nearest([[1.0, 1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0]]),
        "E_NO_CONVERGENCE",
        "matrix",
    )


def test_implied_by_hand() -> None:
    # w = (0.5, 0.5), vols 0.2 and 0.3: own = 0.0025 * 13 = 0.0325, cross = 2 * 0.25 * 0.06
    rho = c.implied([0.5, 0.5], [0.2, 0.3], 0.2)
    assert rho == pytest.approx((0.04 - 0.0325) / 0.03)
    # a zero weight drops its name
    assert c.implied([0.5, 0.0, 0.5], [0.2, 9.0, 0.3], 0.2) == pytest.approx(rho)
    three = c.implied([0.2, 0.3, 0.5], [0.1, 0.2, 0.3], 0.18)
    own = 0.04 * 0.01 + 0.09 * 0.04 + 0.25 * 0.09
    cross = 2 * (0.2 * 0.3 * 0.1 * 0.2 + 0.2 * 0.5 * 0.1 * 0.3 + 0.3 * 0.5 * 0.2 * 0.3)
    assert three == pytest.approx((0.18**2 - own) / cross)


def test_implied_errors() -> None:
    _err(lambda: c.implied([1.0], [0.2], 0.2), "E_INPUT", "weights")
    _err(lambda: c.implied([0.5, 0.5], [0.2], 0.2), "E_INPUT", "weights")
    _err(lambda: c.implied([-0.5, 0.5], [0.0, 0.2], 0.0), "E_DOMAIN", "weights")
    _err(lambda: c.implied([0.5, 0.5], [0.0, 0.2], 0.0), "E_DOMAIN", "vols")
    _err(lambda: c.implied([0.5, 0.5], [0.2, 0.2], 0.0), "E_DOMAIN", "index_vol")
    _err(lambda: c.implied([0.0, 1.0], [0.2, 0.2], 0.2), "E_DOMAIN", "weights")


def test_dispersion_by_hand() -> None:
    out = c.dispersion([0.5, 0.5], [0.2, 0.3], 0.2, [0.25, 0.3], 0.18, 1000.0)
    legs = [1000.0 * 0.5 / 0.4, 1000.0 * 0.5 / 0.6]
    assert out["constituent_variance_notionals"] == pytest.approx(legs)
    assert out["index_variance_notional"] == pytest.approx(1000.0 / 0.4)
    pnl = legs[0] * (0.0625 - 0.04) + legs[1] * 0.0 - 2500.0 * (0.0324 - 0.04)
    assert out["pnl"] == pytest.approx(pnl)
    assert out["implied_correlation"] == pytest.approx((0.04 - 0.0325) / 0.03)
    own = 0.25 * (0.0625 + 0.09)
    assert out["realized_correlation"] == pytest.approx((0.0324 - own) / (0.5 * 0.075))


def test_dispersion_errors() -> None:
    f = c.dispersion
    _err(lambda: f([0.5, 0.5], [0.2], 0.2, [0.2, 0.2], 0.2, 1.0), "E_INPUT", "weights")
    _err(lambda: f([0.5, 0.5], [0.2, 0.2], 0.2, [0.2], 0.2, 1.0), "E_INPUT", "weights")
    _err(lambda: f([0.5, 0.5], [0.0, 0.2], 0.2, [0.2, 0.2], 0.2, 1.0), "E_DOMAIN", "vol_strikes")
    _err(lambda: f([0.5, 0.5], [0.2, 0.2], 0.0, [0.2, 0.2], 0.2, 1.0), "E_DOMAIN", "vol_strikes")
    _err(lambda: f([0.5, 0.5], [0.2, 0.2], 0.2, [0.0, 0.2], 0.2, 1.0), "E_DOMAIN", "realized_vols")
    _err(lambda: f([0.5, 0.5], [0.2, 0.2], 0.2, [0.2, 0.2], 0.0, 1.0), "E_DOMAIN", "realized_vols")
