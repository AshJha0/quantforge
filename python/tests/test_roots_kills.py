"""Kill tests for `quantforge_core.roots` mutants that survived the H-0 Actions run 44373491612
(conformance/mutation/python-h0-2026-11-18.md).

specifications/01-core/root-finders.md: every result carries `iterations`, `residual` and
`termination` (`X_TOL`, `F_TOL` or `EXACT`); `max_iter` caps the iterations, so a solve that
needs k iterations must also succeed with `max_iter = k`.
"""

import math

import pytest

from quantforge_core import roots


def _cubic(x: float) -> float:
    return x**3 - 2 * x - 5  # Wallis' cubic, root near 2.0946


def test_brent_reports_each_termination_with_its_residual() -> None:
    r = roots.brent(_cubic, 2.0, 3.0)
    assert r.termination == "X_TOL"
    assert r.residual == _cubic(r.root)
    f = roots.brent(_cubic, 2.0, 3.0, x_tol=1e-300, f_tol=1e-3)
    assert f.termination == "F_TOL" and abs(f.residual) <= 1e-3
    assert f.residual == _cubic(f.root)
    # Secant step from the bracket ends lands on the root of a line exactly.
    e = roots.brent(lambda x: x - 0.5, 0.0, 2.0, x_tol=1e-300)
    assert e.termination == "EXACT" and e.root == 0.5 and e.residual == 0.0


def test_brent_max_iter_is_the_cap_not_less() -> None:
    k = roots.brent(_cubic, 2.0, 3.0).iterations
    assert k >= 3
    r = roots.brent(_cubic, 2.0, 3.0, max_iter=k)
    assert r.iterations == k and r.termination == "X_TOL"


def test_newton_reports_termination_and_residual() -> None:
    def df(x: float) -> float:
        return 3 * x * x - 2

    r = roots.newton(_cubic, df, 2.0)
    assert r.termination == "X_TOL" and r.residual == _cubic(r.root)
    f = roots.newton(_cubic, df, 2.0, x_tol=1e-300, f_tol=1e-6)
    assert f.termination == "F_TOL" and f.residual == _cubic(f.root)
    assert f.root == pytest.approx(2.0945514815423265, abs=1e-6)
    assert math.isfinite(f.residual)
