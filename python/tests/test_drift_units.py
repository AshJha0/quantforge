"""Unit tests for the drift detectors (11-research/drift-detectors.md, rulings J-W3-10 to
J-W3-13). CUSUM, Page-Hinkley and PSI values are worked by hand below; the KS p-values were
checked against scipy.stats.ks_2samp(method="exact")."""

import math

import pytest

from quantforge_core import drift
from quantforge_core.errors import QfError


def _err(fn, code: str, field: str) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    # the message is a readable sentence, not a placeholder or shouting (kills the
    # message-text mutants, which no code or field check can see)
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()


def test_cusum_up_down_and_reset() -> None:
    # z = 0, 3, 3 with k = 0.5: s+ = 0, 2.5, 5 > 4 at t = 2
    out = drift.cusum([0.0, 3.0, 3.0], 0.5, 4.0)
    assert out == {"alarms": [2], "directions": [1], "s_plus": 0.0, "s_minus": 0.0}
    nr = drift.cusum([0.0, 3.0, 3.0, 3.0], 0.5, 4.0, reset=False)
    assert nr["alarms"] == [2] and nr["s_plus"] == pytest.approx(5.0)
    dn = drift.cusum([-3.0, -3.0, 0.0], 0.5, 4.0)
    assert dn["alarms"] == [1] and dn["directions"] == [-1]
    assert dn["s_minus"] == 0.0 and dn["s_plus"] == 0.0
    # standardisation: x = 12, 16, 16 with mu0 = 10, sigma = 2 is z = 1, 3, 3
    st = drift.cusum([12.0, 16.0, 16.0], 0.5, 4.0, mu0=10.0, sigma=2.0)
    assert st["alarms"] == [2]
    part = drift.cusum([12.0, 16.0], 0.5, 4.0, mu0=10.0, sigma=2.0)
    assert part["alarms"] == [] and part["s_plus"] == pytest.approx(3.0)
    # equality with h is not an alarm
    eq = drift.cusum([4.5], 0.5, 4.0)
    assert eq["alarms"] == [] and eq["s_plus"] == pytest.approx(4.0)
    # the sums floor at zero
    fl = drift.cusum([-1.0, 1.0], 0.5, 4.0)
    assert fl["s_minus"] == 0.0 and fl["s_plus"] == pytest.approx(0.5)
    two = drift.cusum([5.0, 0.0, 5.0], 0.5, 4.0)
    assert two["alarms"] == [0, 2] and two["directions"] == [1, 1]


def test_cusum_errors() -> None:
    _err(lambda: drift.cusum([], 0.5, 4.0), "E_INPUT", "x")
    _err(lambda: drift.cusum([1.0], 0.0, 4.0), "E_DOMAIN", "k")
    _err(lambda: drift.cusum([1.0], 0.5, 0.0), "E_DOMAIN", "k")
    _err(lambda: drift.cusum([1.0], 0.5, 4.0, sigma=0.0), "E_DOMAIN", "k")
    _err(lambda: drift.cusum([1.0], math.nan, 4.0), "E_DOMAIN", "k")


def test_page_hinkley() -> None:
    # x = 0, 0, 10: running mean 10/3 at t = 2, m = 20/3 > 5
    up = drift.page_hinkley([0.0, 0.0, 10.0], 0.0, 5.0)
    assert up == {"alarms": [2], "directions": [1]}
    assert drift.page_hinkley([0.0, 0.0, 10.0], 0.0, 5.0, "down")["alarms"] == []
    dn = drift.page_hinkley([0.0, 0.0, -10.0], 0.0, 5.0)
    assert dn == {"alarms": [2], "directions": [-1]}
    assert drift.page_hinkley([0.0, 0.0, -10.0], 0.0, 5.0, "up")["alarms"] == []
    assert drift.page_hinkley([0.0, 0.0, -10.0], 0.0, 5.0, "down")["alarms"] == [2]
    # delta = 2: m = -2, -4, 2/3 so m - min = 14/3 < 5
    assert drift.page_hinkley([0.0, 0.0, 10.0], 2.0, 5.0)["alarms"] == []
    assert drift.page_hinkley([0.0, 0.0, 10.0], 1.0, 5.0)["alarms"] == [2]
    # exactly lambda is not an alarm: x = 0, 10 gives m = 5
    assert drift.page_hinkley([0.0, 10.0], 0.0, 5.0)["alarms"] == []
    x = [0.0, 0.0, 10.0, 0.0, 0.0, 10.0]
    assert drift.page_hinkley(x, 0.0, 5.0)["alarms"] == [2, 5]
    assert drift.page_hinkley(x, 0.0, 5.0, reset=False)["alarms"] == [2]
    assert drift.page_hinkley([6.0, 6.0], 0.0, 5.0)["alarms"] == []


def test_page_hinkley_errors() -> None:
    _err(lambda: drift.page_hinkley([], 0.0, 1.0), "E_INPUT", "x")
    _err(lambda: drift.page_hinkley([1.0], -0.1, 1.0), "E_DOMAIN", "delta")
    _err(lambda: drift.page_hinkley([1.0], 0.0, 0.0), "E_DOMAIN", "delta")
    _err(lambda: drift.page_hinkley([1.0], 0.0, 1.0, "sideways"), "E_INPUT", "direction")


R10 = [float(v) for v in range(1, 11)]


def test_psi_values() -> None:
    # bins = 2: edge r[4] = 5, reference shares 0.5 / 0.5
    test = [1.0] * 4 + [9.0] * 6
    out = drift.psi(R10, test, bins=2)
    assert out["reference_shares"] == pytest.approx([0.5, 0.5])
    assert out["test_shares"] == pytest.approx([0.4, 0.6])
    v = -0.1 * math.log(0.8) + 0.1 * math.log(1.2)
    assert out["psi"] == pytest.approx(v)
    assert out["alarm"] is False
    assert drift.psi(R10, test, bins=2, threshold=v / 2)["alarm"] is True
    # an empty bin is floored at 1e-4; a value on an edge falls in the lower bin
    fl = drift.psi(R10, [5.0] * 10, bins=2)
    assert fl["test_shares"] == pytest.approx([1.0, 1e-4])
    assert fl["psi"] == pytest.approx(0.5 * math.log(2.0) + (1e-4 - 0.5) * math.log(1e-4 / 0.5))
    assert fl["alarm"] is True
    # bins = 3: edges r[3] = 4 and r[6] = 7
    three = drift.psi(R10, R10, bins=3)
    assert three["reference_shares"] == pytest.approx([0.4, 0.3, 0.3])
    assert three["psi"] == 0.0 and three["alarm"] is False
    t3 = drift.psi(R10, [4.0, 4.1, 7.0, 7.1, 10.0, 11.0], bins=3)
    assert t3["test_shares"] == pytest.approx([1 / 6, 2 / 6, 3 / 6])
    t5 = drift.psi(R10, [0.0, 2.0, 3.0, 4.5, 6.0, 6.5, 8.0, 9.5, 20.0, 1.0], bins=5)
    assert t5["reference_shares"] == pytest.approx([0.2] * 5)
    assert t5["test_shares"] == pytest.approx([0.3, 0.1, 0.2, 0.2, 0.2])


def test_psi_errors() -> None:
    _err(lambda: drift.psi(R10, R10, bins=1), "E_INPUT", "bins")
    _err(lambda: drift.psi(R10[:3], R10, bins=4), "E_INPUT", "reference")
    _err(lambda: drift.psi(R10, R10[:3], bins=4), "E_INPUT", "reference")
    assert drift.psi(R10[:4], R10[:4], bins=4)["psi"] == 0.0
    _err(lambda: drift.psi(R10, R10, threshold=0.0), "E_DOMAIN", "threshold")


def test_ks_statistic_and_exact_p() -> None:
    out = drift.ks([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    assert out["statistic"] == 1.0
    assert out["p_value"] == pytest.approx(0.1)
    assert out["reject"] is False
    assert drift.ks([1.0, 2.0, 3.0], [4.0, 5.0, 6.0], level=0.1)["reject"] is True
    b = drift.ks([1.0, 2.0, 3.0, 7.0], [4.0, 5.0, 6.0])
    assert b["statistic"] == pytest.approx(0.75)
    assert b["p_value"] == pytest.approx(0.22857142857142862)
    c = drift.ks([1.0, 3.0, 5.0, 7.0, 9.0], [2.0, 4.0, 6.0, 8.0, 10.0, 12.0])
    assert c["statistic"] == pytest.approx(1 / 3)
    assert c["p_value"] == pytest.approx(0.8181818181818182)
    # reversed samples give the same answer
    r = drift.ks([2.0, 4.0, 6.0, 8.0, 10.0, 12.0], [1.0, 3.0, 5.0, 7.0, 9.0])
    assert r["p_value"] == pytest.approx(c["p_value"])
    same = drift.ks([1.0, 2.0], [1.0, 2.0])
    assert same["statistic"] == 0.0 and same["p_value"] == 1.0
    # ties step together: a = 1, 1, 2 and b = 1, 2, 2 differ by 1/3 after the 1s
    t = drift.ks([1.0, 1.0, 2.0], [1.0, 2.0, 2.0])
    assert t["statistic"] == pytest.approx(1 / 3)
    one = drift.ks([0.0], [1.0])
    assert one["statistic"] == 1.0 and one["p_value"] == pytest.approx(1.0)


def test_ks_helpers() -> None:
    assert drift._ks_d_scaled([1.0, 2.0, 3.0], [4.0, 5.0, 6.0]) == 9
    assert drift._ks_d_scaled([4.0], [1.0, 2.0]) == 2
    assert drift._ks_p(3, 3, 0) == 1.0
    assert drift._ks_p(3, 3, 9) == pytest.approx(0.1)
    assert drift._ks_p(2, 2, 4) == pytest.approx(2 / 6)
    assert drift._ks_p(2, 2, 2) == pytest.approx(1.0)
    assert drift._ks_p(3, 4, 9) == pytest.approx(0.22857142857142862)


def test_ks_errors() -> None:
    _err(lambda: drift.ks([], [1.0]), "E_INPUT", "a")
    _err(lambda: drift.ks([1.0], []), "E_INPUT", "b")
    _err(lambda: drift.ks([1.0], [2.0], level=0.0), "E_DOMAIN", "level")
    _err(lambda: drift.ks([1.0], [2.0], level=1.0), "E_DOMAIN", "level")
