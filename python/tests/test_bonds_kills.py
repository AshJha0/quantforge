"""Kill tests for `quantforge_core.bonds` mutants that survived the H-0 Actions run 44317826833
(conformance/mutation/python-h0-2026-11-18.md).

Error checks pin code and field (the CLI contract), not the message text. The Z-spread test uses a
deeply distressed price (dirty below 1 per 100 face), which the spec allows: only a dirty price
that is not positive is refused (specifications/04-pricing/bonds*.md). The futures test checks the
net basis definition: forward dirty price at repo minus the invoice amount.
"""

import math
from datetime import date
from typing import Any

import pytest

from quantforge_core import bonds
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

BOND = bonds.Bond(date(2030, 6, 15), 0.05, 2)
FLAT = CurveData(
    date(2026, 6, 15),
    "LOG_LINEAR_DF",
    (date(2027, 6, 15), date(2036, 6, 15)),
    (math.exp(-0.04 * 365 / 365), math.exp(-0.04 * 3653 / 365)),
)


def _err(fn: Any, *args: Any) -> tuple[str, str | None]:
    with pytest.raises(QfError) as e:
        fn(*args)
    return e.value.code, e.value.field


def test_error_codes_and_fields() -> None:
    early = date(2026, 6, 1)
    assert _err(bonds.price_from_curve, BOND, early, FLAT) == ("E_OUT_OF_RANGE", "settlement")
    assert _err(bonds.z_spread, BOND, date(2026, 7, 1), FLAT, -5.0) == ("E_DOMAIN", "clean_price")


def _dirty_at(z: float, settlement: date) -> float:
    """Dirty price per 100 face discounting each flow at D(t) exp(-z t), forward to settlement."""
    fl = bonds.flows(BOND, settlement)
    from quantforge_core import curves

    curve = curves.build(FLAT)

    def ds(d: date) -> float:
        return curve.discount(d) * math.exp(-z * curve.time(d))

    return sum(cf * ds(d) for d, cf in zip(fl.dates, fl.amounts, strict=True)) / ds(settlement)


def test_z_spread_of_a_distressed_price_below_one() -> None:
    settlement = date(2026, 6, 15)
    dirty = _dirty_at(3.0, settlement)
    assert 0 < dirty < 1
    fl = bonds.flows(BOND, settlement)
    assert bonds.z_spread(BOND, settlement, FLAT, dirty - fl.accrued) == pytest.approx(
        3.0, abs=1e-9
    )


def test_futures_net_basis_is_forward_dirty_minus_invoice() -> None:
    settle, delivery, r = date(2026, 6, 15), date(2026, 12, 1), 0.0385
    rows, _ = bonds.futures_basis(104.0, settle, delivery, r, [(BOND, 100.6, 0.95)])
    fwd: dict[str, Any] = bonds.repo_forward(BOND, settle, delivery, 100.6, r, None)
    invoice = 104.0 * 0.95 + bonds.accrued_at(BOND, delivery)
    assert rows[0]["invoice"] == pytest.approx(invoice, rel=1e-15)
    assert rows[0]["net_basis"] == pytest.approx(fwd["forward_dirty"] - invoice, rel=1e-12)
