"""Q5a: limit-case and convergence-order checks for the stage E numerical methods that have no
outside source (plan section 12.1). Rust, Java and C++ carry the same checks; the SLV
calibration round trip on a Heston surface runs here only (it needs a Monte Carlo harness)."""
import itertools
import math
from typing import Any

import numpy as np

from quantforge_core import arb_surface, pde
from quantforge_core import exotics as ex
from quantforge_core import heston as hm
from quantforge_core.smile import Svi

X0 = math.log(100.0)


def _order(e):
    return [math.log2(abs(a / b)) for a, b in itertools.pairwise(e)]


def _slv_gap(nx, nv, nt):
    """Largest |L - 1| within 0.3 of ln(spot) for a flat 20% surface and Heston with
    v0 = theta = 0.04 and vanishing vol of vol: SLV then reduces to Heston with L = 1."""
    flat = [arb_surface.Slice(1.0, Svi(0.04, 0.0, 0.0, 0.0, 0.1))]
    out: dict[str, Any] = hm.slv_leverage(100.0, 1.0, 0.0, 0.0, hm.Heston(0.04, 2.0, 0.04, 0.01, -0.7), flat,
                          hm.Grid(nx, nv, nt, X0 - 1.0, X0 + 1.0, 0.25))
    assert abs(out["mass"] - 1.0) < 1e-3
    return max(abs(lev - 1) for x, lev in zip(out["x"], out["leverage"]) if abs(x - X0) < 0.3)


def test_slv_heston_limit_leverage_one_within_discretisation_error() -> None:
    coarse, fine = _slv_gap(41, 20, 20), _slv_gap(81, 40, 40)
    assert coarse < 0.07
    assert fine < 0.6 * coarse  # discretisation error, about first order


def test_fd_american_put_matches_fine_tree() -> None:
    tree = ex.crr(100, 100, 1, 0.05, 0.0, 0.2, "PUT", 1000)["american"]
    fd = ex.fd(100, 100, 1, 0.05, 0.0, 0.2, "PUT", "AMERICAN", 401, 1600, 5.0)["price"]
    # Backward Euler error at this grid is about 2e-3; the tree's about 5e-4.
    assert abs(fd - tree) < 5e-3


def test_fd_american_put_zero_rate_is_european() -> None:
    am = ex.fd(100, 100, 1, 0.0, 0.0, 0.2, "PUT", "AMERICAN", 401, 400, 5.0)["price"]
    eu = ex.fd(100, 100, 1, 0.0, 0.0, 0.2, "PUT", "EUROPEAN", 401, 400, 5.0)["price"]
    assert abs(am - eu) < 1e-12
    assert abs(am - ex.gbs(-1, 100, 100, 1, 0.0, 0.0, 0.2)) < 5e-3


def test_crank_nicolson_second_order() -> None:
    exact = ex.gbs(1, 100, 105, 1, 0.03, 0.02, 0.2)
    errs = [pde.bs_european("CALL", 100, 105, 0.03, 0.01, 0.2, 1, j, j // 2).price - exact
            for j in (100, 200, 400)]
    assert all(1.8 <= p <= 2.2 for p in _order(errs))


def test_fd_reference_scheme_orders():
    exact = ex.gbs(-1, 100, 100, 1, 0.05, 0.05, 0.2)

    def fd(nx, nt):
        return ex.fd(100, 100, 1, 0.05, 0.0, 0.2, "PUT", "EUROPEAN", nx, nt, 5.0)["price"]
    # Space: halve dx and quarter dt, so the O(dt) term keeps pace with O(dx^2).
    space = [fd(nx, nt) - exact for nx, nt in ((51, 25), (101, 100), (201, 400))]
    assert all(1.8 <= p <= 2.2 for p in _order(space))
    # Time: Richardson on successive differences at a fixed fine grid.
    f = [fd(401, nt) for nt in (50, 100, 200, 400)]
    assert all(0.8 <= p <= 1.2 for p in _order([a - b for a, b in itertools.pairwise(f)]))


def test_crr_first_order() -> None:
    exact = ex.gbs(-1, 100, 100, 1, 0.05, 0.05, 0.2)
    errs = [ex.crr(100, 100, 1, 0.05, 0.0, 0.2, "PUT", n)["european"] - exact
            for n in (100, 200, 400)]
    assert all(0.8 <= p <= 1.2 for p in _order(errs))


def _implied(price, strike, t):
    lo, hi = 1e-4, 3.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ex.gbs(1, 100.0, strike, t, 0.0, 0.0, mid) < price else (lo, mid)
    return (lo + hi) / 2


def test_slv_calibrated_to_heston_surface_has_unit_leverage_and_reprices() -> None:
    """Heston prices -> SVI surface -> Dupire -> SLV leverage. Pure Heston has
    sigma_LV^2 = E[v | x], so the calibrated leverage must be near 1 and an SLV Monte Carlo
    must reprice the Heston vanillas."""
    h = hm.Heston(0.04, 1.5, 0.04, 0.3, -0.5)
    expiries = [0.125 * n for n in range(1, 11)]  # to 1.25, so t = 1 is interpolated
    ks = [-0.4 + 0.1 * i for i in range(9)]
    strikes = [100.0 * math.exp(k) for k in ks]
    rows = [[_implied(p, k, t) ** 2 * t
             for p, k in zip(hm.heston_price(100.0, strikes, t, 0.0, 0.0, h, "CALL"), strikes)]
            for t in expiries]
    slices, _, _ = arb_surface.fit_surface(expiries, ks, rows, False)
    times = (0.125, 0.25, 0.5, 0.75, 1.0)
    levs, xs = [], None
    for t in times:
        out = hm.slv_leverage(100.0, t, 0.0, 0.0, h, slices,
                              hm.Grid(81, 80, max(2, round(24 * t)), X0 - 0.8, X0 + 0.8, 0.3))
        xs = np.array(out["x"])
        levs.append(np.array(out["leverage"]))
        if t >= 0.5:  # at short expiries the start-density width (2 dx) dominates
            gap = max(abs(lev - 1) for x, lev in zip(xs, levs[-1]) if abs(x - X0) < 0.3)
            assert gap < 0.06, (t, gap)
    rng = np.random.default_rng(7)
    n, steps = 20_000, 48
    dt = 1.0 / steps
    x, v = np.full(n, X0), np.full(n, h.v0)
    for s in range(steps):
        assert xs is not None
        lev = np.interp(x, xs, levs[int(np.searchsorted(times, s * dt + dt / 2))])
        z1 = rng.standard_normal(n)
        z2 = h.rho * z1 + math.sqrt(1 - h.rho**2) * rng.standard_normal(n)
        vp = np.maximum(v, 0.0)  # full truncation Euler
        x = x - 0.5 * lev * lev * vp * dt + lev * np.sqrt(vp * dt) * z1
        v = v + h.kappa * (h.theta - vp) * dt + h.xi * np.sqrt(vp * dt) * z2
    for k in (90.0, 100.0, 110.0):
        pay = np.maximum(np.exp(x) - k, 0.0)
        se = pay.std() / math.sqrt(n)
        ref = hm.heston_price(100.0, [k], 1.0, 0.0, 0.0, h, "CALL")[0]
        assert abs(pay.mean() - ref) < 3 * se, (k, pay.mean(), ref, se)
