"""R6 finding 3: the curve Jacobian must match a central difference in every entry.

Before R6 the implementation zeroed every entry above the diagonal. That is exact for
local interpolations (a pillar's zero rate depends only on quotes up to its own tenor)
but wrong for the stage F methods, whose interpolant couples later pillars into earlier
discount factors used by the bootstrap. This test compares each entry with an
independent central difference built from the bootstrap directly.
"""
import math
from datetime import date

import pytest

from quantforge_core import ois
from quantforge_core import risk_curve as R
from quantforge_core.curves import INTERPOLATIONS
from quantforge_core.ois import Quote

AS_OF = date(2026, 1, 6)
QUOTES = [Quote("1Y", 0.035), Quote("2Y", 0.034), Quote("3Y", 0.0345), Quote("5Y", 0.036),
          Quote("7Y", 0.037), Quote("10Y", 0.038)]
H = 1e-4


def _zeros(shifts: list[float], interpolation: str) -> list[float]:
    moved = [Quote(q.tenor, q.mid + s) for q, s in zip(QUOTES, shifts, strict=True)]
    data = ois.bootstrap("SOFR", AS_OF, moved, interpolation)[0]
    return [-math.log(v) / ((d - AS_OF).days / 365)
            for d, v in zip(data.dates, data.discount_factors, strict=True)]


def _central(interpolation: str) -> list[list[float]]:
    n = len(QUOTES)
    cols = []
    for j in range(n):
        up = _zeros([H if k == j else 0.0 for k in range(n)], interpolation)
        dn = _zeros([-H if k == j else 0.0 for k in range(n)], interpolation)
        cols.append([(u - d) / (2 * H) for u, d in zip(up, dn, strict=True)])
    return [[cols[j][i] for j in range(n)] for i in range(n)]


# TENSION_SPLINE and HYBRID need tension / step_end, which risk.curve.jacobian has no input for
# (question to the spec lane, R6_PYTHON_HANDOVER.md); they are E_INPUT today.
@pytest.mark.parametrize("interpolation",
                         [m for m in INTERPOLATIONS if m not in ("TENSION_SPLINE", "HYBRID")])
def test_jacobian_matches_central_difference(interpolation: str) -> None:
    got = R.jacobian(AS_OF, "SOFR", QUOTES, interpolation, 1.0)["jacobian"]
    ref = _central(interpolation)
    assert isinstance(got, list)
    for i, row in enumerate(ref):
        for j, value in enumerate(row):
            assert got[i][j] == pytest.approx(value, abs=1e-6), (interpolation, i, j)


def test_mbs_psa_above_cpr_one_is_domain_error() -> None:
    """R6 finding 18: above about 1667% PSA the SMM would be complex; E_DOMAIN instead."""
    from quantforge_core import mbs
    from quantforge_core.errors import QfError

    with pytest.raises(QfError) as e:
        mbs.mbs_cashflows((1e6, 0.065, 0.06, 60, 0, "PSA", 5000.0))
    assert e.value.code == "E_DOMAIN"
    assert mbs.mbs_cashflows((1e6, 0.065, 0.06, 60, 0, "PSA", 1666.0))["wal"]
