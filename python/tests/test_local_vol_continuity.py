"""R10 / ruling F-17: continuity of w and implied vol at slice expiries, the stated local-vol jump,
and smoothness inside an interval, on this build's own outputs (local-and-forward-vol.md)."""
import itertools
import math

import pytest

from quantforge_core import arb_surface
from quantforge_core.smile import Svi

SLICES = [
    arb_surface.Slice(0.25, Svi(0.02, 0.1, -0.4, 0.02, 0.2)),
    arb_surface.Slice(1.0, Svi(0.035, 0.11, -0.35, 0.03, 0.25)),
    arb_surface.Slice(2.0, Svi(0.06, 0.12, -0.3, 0.04, 0.3)),
]
TWO = SLICES[:2]
KS = (-0.4, 0.0, 0.3)


def _w(p: Svi, k: float) -> float:
    return p.a + p.b * (p.rho * (k - p.m) + math.sqrt((k - p.m) ** 2 + p.sigma ** 2))


def _point(slices, t, k):
    w, vol, local = arb_surface.dupire(slices, [(t, k)])
    return w[0], vol[0], local[0]


@pytest.mark.parametrize("slices", [SLICES, TWO], ids=["three", "two"])
@pytest.mark.parametrize("k", KS)
def test_w_and_vol_continuous_and_local_vol_jump(slices, k):
    for j, s in enumerate(slices):
        t = s.expiry_years
        left, node, right = (_point(slices, t * f, k) for f in (1 - 1e-9, 1.0, 1 + 1e-9))
        assert abs(left[0] - node[0]) <= 1e-9 * node[0]
        assert abs(left[1] - node[1]) <= 1e-9 * node[1]
        w_j = _w(s.svi, k)
        # left slope: flat-vol extrapolation at the short end, else the interval to the left
        if j == 0:
            slope_left = w_j / t
        else:
            p = slices[j - 1]
            slope_left = (w_j - _w(p.svi, k)) / (t - p.expiry_years)
        if j + 1 < len(slices):
            n = slices[j + 1]
            slope_right = (_w(n.svi, k) - w_j) / (n.expiry_years - t)
        else:
            slope_right = w_j / t  # beyond the last slice: flat vol
        g_over = node[2] ** 2 / slope_right  # 1/g from the node, which takes the right limit
        assert left[2] == pytest.approx(math.sqrt(slope_left * g_over), rel=1e-8)
        assert right[2] == pytest.approx(node[2], rel=1e-8)


@pytest.mark.parametrize("k", KS)
def test_local_vol_smooth_inside_intervals(k):
    edges = [0.0] + [s.expiry_years for s in SLICES] + [3.0]
    for a, b in itertools.pairwise(edges):
        for f in (0.1, 0.3, 0.5, 0.7, 0.9):
            t = a + f * (b - a)
            x, y = _point(SLICES, t, k)[2], _point(SLICES, t * (1 + 1e-9), k)[2]
            assert abs(x - y) <= 1e-6 * x
