"""K-9 review fixes: SABR chi(z) without cancellation (KR-340) and implied-vol acceptance (KR-341).

The shared goldens come from mpmath (oracle/python/gen_stage_k_rev1.py). Here the closed form is checked against
the direct formula evaluated at 80 digits with the decimal module, so the test needs no oracle dependency."""

import math
from decimal import Decimal, getcontext

import pytest

from quantforge_core import black
from quantforge_core.black import BACHELIER, BLACK_76, Option
from quantforge_core.errors import QfError
from quantforge_core.sabr import _chi

getcontext().prec = 80


def _chi_ref(z: float, rho: float) -> float:
    zd, rd = Decimal(z), Decimal(rho)
    s = (1 - 2 * rd * zd + zd * zd).sqrt()
    return float(((s + zd - rd) / (1 - rd)).ln())


@pytest.mark.parametrize("rho", [-0.95, -0.3, 0.0, 0.3, 0.95])
@pytest.mark.parametrize("z", [1.01e-7, -1.01e-7, 1e-6, -1e-4, 0.3, -0.7, 2.0, -5.0, 40.0, -300.0])
def test_chi_matches_high_precision(z: float, rho: float) -> None:
    ref = _chi_ref(z, rho)
    assert abs(_chi(z, rho) - ref) <= 9e-16 * abs(ref)  # 4 ulp; the sweep in the spec measured 3


def test_chi_small_z_direct_form_loses_digits() -> None:
    z, rho = 1.01e-7, 0.3
    direct = math.log((math.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
    ref = _chi_ref(z, rho)
    assert abs(direct / ref - 1) > 1e-9  # the defect KR-340 removes
    assert abs(_chi(z, rho) / ref - 1) < 1e-15


def test_implied_deep_otm_returns_the_vol() -> None:
    # Black-76 call F = 100, K = 300, T = 0.1, vol 0.1: price 1.48e-265 (golden ivdeep_c-0008)
    o = Option(BLACK_76, "CALL", 300.0, 0.1, 100.0)
    p = black.price(o, 0.1)
    assert p < 1e-260
    assert abs(black.implied(o, p) / 0.1 - 1) < 1e-9


def test_implied_subnormal_price_is_not_identified() -> None:
    o = Option(BACHELIER, "PUT", 86.83731917681901, 2.9082679923151997, 100.0)
    with pytest.raises(QfError) as e:
        black.implied(o, 1.5826e-319)
    assert e.value.code == "E_NO_CONVERGENCE"
