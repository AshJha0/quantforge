"""Kill tests for `quantforge_core.compounding` mutants that survived the H-0 Actions run
44373491612 (conformance/mutation/python-h0-2026-11-18.md).

The checks and their order come from specifications/01-core/compounding.md: E_SCHEMA for an
unknown kind or a missing or unlisted PERIODIC frequency, then E_DOMAIN for `1 + r t <= 0`
(SIMPLE) or `1 + r/n <= 0` (PERIODIC), boundary included. Code and field are pinned, not text.
"""

import math
from typing import Any

import pytest

from quantforge_core.compounding import Compounding, convert
from quantforge_core.errors import QfError

CONT = Compounding("CONTINUOUS")


def _err(fn: Any, *args: Any) -> tuple[str, str | None]:
    with pytest.raises(QfError) as e:
        fn(*args)
    return e.value.code, e.value.field


@pytest.mark.parametrize(
    ("bad", "field"),
    [
        (Compounding("ANNUAL"), "compounding"),
        (Compounding("PERIODIC"), "frequency"),
        (Compounding("PERIODIC", 5), "frequency"),
    ],
)
def test_schema_errors_on_either_side(bad: Compounding, field: str) -> None:
    assert _err(convert, 0.05, 1.0, bad, CONT) == ("E_SCHEMA", field)
    assert _err(convert, 0.05, 1.0, CONT, bad) == ("E_SCHEMA", field)


def test_every_listed_frequency_is_accepted() -> None:
    for n in (1, 2, 3, 4, 6, 12):
        r = convert(0.05, 2.0, Compounding("PERIODIC", n), CONT)
        assert r == pytest.approx(n * math.log(1 + 0.05 / n), rel=1e-14)


def test_domain_boundaries_are_refused() -> None:
    simple = Compounding("SIMPLE")
    assert _err(convert, -0.5, 2.0, simple, CONT) == ("E_DOMAIN", "rate")  # 1 + r t = 0
    assert _err(convert, -0.6, 2.0, simple, CONT) == ("E_DOMAIN", "rate")
    semi = Compounding("PERIODIC", 2)
    assert _err(convert, -2.0, 1.0, semi, CONT) == ("E_DOMAIN", "rate")  # 1 + r/n = 0
    assert _err(convert, -3.0, 1.0, semi, CONT) == ("E_DOMAIN", "rate")
    assert _err(convert, 0.05, 0.0, CONT, CONT) == ("E_DOMAIN", "t")


def test_just_inside_the_boundaries_converts() -> None:
    # Negative rates are allowed while 1 + r t (or 1 + r/n) stays positive.
    r = convert(-0.49, 2.0, Compounding("SIMPLE"), CONT)
    assert r == pytest.approx(math.log(1 - 0.98) / 2.0, rel=1e-12)
    r2 = convert(-1.9, 1.0, Compounding("PERIODIC", 2), CONT)
    assert r2 == pytest.approx(2 * math.log(1 - 0.95), rel=1e-12)
