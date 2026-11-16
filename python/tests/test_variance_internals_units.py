"""Unit tests for the helpers of quantforge_core.variance: the logistic map and its inverse, the
variance-swap log-payoff function, the Nelder-Mead minimiser the GARCH fit and estimate are built
on, and the exact text of two input checks (05-volatility/garch.md, variance-swaps.md).

The full mutation run of this module (2026-11-16, 91 % killed) showed these helpers were seen only
through a converged optimum, where a changed reflection coefficient or a dropped overflow guard
moves nothing a likelihood test can see. The Nelder-Mead oracle below is the textbook method
(Lagarias, Reeds, Wright and Wright 1998: reflection 1, expansion 2, contraction 1/2, shrink 1/2),
written from the paper with the module's two documented choices: a strict "<" when accepting a
contraction and the stop |f_worst - f_best| <= 1e-14 (1 + |f_best|). Every other expected value is
a closed form worked by hand."""

import math
from collections.abc import Callable

import pytest

from quantforge_core import variance as v
from quantforge_core.errors import QfError

# --------------------------------------------------------------------------------------------
# the logistic map and its inverse


def test_sigmoid_values_and_no_overflow_in_either_tail() -> None:
    assert v._sigmoid(0.0) == 0.5
    assert v._sigmoid(-1.0) == pytest.approx(1 / (1 + math.e), rel=1e-15)
    assert v._sigmoid(1.0) == pytest.approx(math.e / (1 + math.e), rel=1e-15)
    assert v._sigmoid(-3.0) == pytest.approx(1 / (1 + math.exp(3.0)), rel=1e-15)
    # exp(1000) overflows binary64: each tail must use the form that does not evaluate it
    assert v._sigmoid(1000.0) == 1.0
    assert v._sigmoid(-1000.0) == 0.0
    assert v._sigmoid(-745.0) > 0.0  # exp(-745) is the smallest subnormal, not 0


def test_logit_inverts_the_sigmoid() -> None:
    assert v._logit(0.5) == 0.0
    assert v._logit(0.9) == pytest.approx(math.log(9.0), rel=1e-14)
    assert v._logit(0.2) == pytest.approx(-math.log(4.0), rel=1e-14)
    for x in (-4.0, -0.3, 0.7, 5.0):
        assert v._logit(v._sigmoid(x)) == pytest.approx(x, rel=1e-12)


# --------------------------------------------------------------------------------------------
# variance swap: f(K) = (2/T) ((K - S0)/S0 - ln(K/S0)), the replication payoff


def test_log_payoff_function_by_hand() -> None:
    # K = 110, S0 = 100, T = 0.5: 4 (0.1 - ln 1.1) = 0.0187592807...
    assert v._f(110.0, 100.0, 0.5) == pytest.approx(4 * (0.1 - math.log(1.1)), rel=1e-14)
    assert v._f(80.0, 100.0, 2.0) == pytest.approx(1.0 * (-0.2 - math.log(0.8)), rel=1e-14)
    assert v._f(100.0, 100.0, 1.0) == 0.0
    # convex with its minimum 0 at K = S0
    assert v._f(99.0, 100.0, 1.0) > 0.0 and v._f(101.0, 100.0, 1.0) > 0.0


# --------------------------------------------------------------------------------------------
# input checks: exact text


def _message(fn: Callable[[], object], code: str, field: str) -> str:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    return e.value.message


def test_sample_initial_variance_of_zero_returns_message() -> None:
    msg = _message(
        lambda: v.garch_loglik([0.0, 0.0, 0.0], 1e-6, 0.1, 0.8, "SAMPLE"),
        "E_DOMAIN",
        "initial_variance",
    )
    assert msg == "SAMPLE initial variance is zero"


def test_student_t_without_degrees_of_freedom_message() -> None:
    msg = _message(
        lambda: v.garch_loglik_t([0.01, -0.02], 1e-6, 0.1, 0.8, "SAMPLE", "STUDENT_T", None, 0.0),
        "E_INPUT",
        "degrees_of_freedom",
    )
    assert msg == "STUDENT_T needs degrees_of_freedom"


# --------------------------------------------------------------------------------------------
# Nelder-Mead against the textbook method


def _reference(
    f: Callable[[list[float]], float],
    start: list[float],
    step: float,
    iterations: int,
    seen: set[str],
) -> tuple[list[float], float]:
    n = len(start)
    pts = [list(start)]
    for i in range(n):
        p = [x + (step if j == i else 0.0) for j, x in enumerate(start)]
        pts.append(p)
    fs = [f(p) for p in pts]
    for _ in range(iterations):
        order = sorted(range(n + 1), key=lambda k: fs[k])  # stable: ties keep their order
        pts, fs = [pts[k] for k in order], [fs[k] for k in order]
        best, worst = fs[0], fs[n]
        if abs(worst - best) <= 1e-14 * (1 + abs(best)):
            seen.add("stop")
            break
        c = [sum(p[j] for p in pts[:n]) / n for j in range(n)]
        w = pts[n]
        xr = [cj + 1.0 * (cj - wj) for cj, wj in zip(c, w, strict=True)]
        fr = f(xr)
        if fr < best:
            xe = [cj + 2.0 * (cj - wj) for cj, wj in zip(c, w, strict=True)]
            fe = f(xe)
            if fe < fr:
                pts[n], fs[n] = xe, fe
                seen.add("expand")
            else:
                pts[n], fs[n] = xr, fr
                seen.add("reflect after expansion fails")
        elif fr < fs[n - 1]:
            pts[n], fs[n] = xr, fr
            seen.add("reflect")
        else:
            if fr < worst:  # outside contraction, toward the reflected point
                xc = [cj + 0.5 * (cj - wj) for cj, wj in zip(c, w, strict=True)]
                kind = "outside"
            else:  # inside contraction, toward the worst point
                xc = [cj - 0.5 * (cj - wj) for cj, wj in zip(c, w, strict=True)]
                kind = "inside"
            fc = f(xc)
            if fc < min(fr, worst):
                pts[n], fs[n] = xc, fc
                seen.add(kind)
            else:
                b = pts[0]
                pts = [b] + [
                    [bj + 0.5 * (pj - bj) for bj, pj in zip(b, p, strict=True)] for p in pts[1:]
                ]
                fs = [fs[0]] + [f(p) for p in pts[1:]]
                seen.add("shrink")
    k = min(range(n + 1), key=lambda i: fs[i])
    return pts[k], fs[k]


def _rosenbrock(x: list[float]) -> float:
    return 100 * (x[1] - x[0] ** 2) ** 2 + (1 - x[0]) ** 2


def _skewed(x: list[float]) -> float:
    return (
        (x[0] - 1) ** 2 + 3 * (x[1] + 0.5) ** 2 + 0.9 * (x[0] - 1) * (x[1] + 0.5) + (x[2] - 2) ** 4
    )


def _kinked(x: list[float]) -> float:
    return abs(x[0] - 0.3) + 2 * abs(x[1] + 0.1) + 0.01 * x[0] * x[1]


def _bumpy(x: list[float]) -> float:
    # local minima everywhere: some contractions fail, so the simplex shrinks
    return x[0] ** 2 + x[1] ** 2 + 0.5 * math.sin(37 * x[0]) * math.sin(41 * x[1])


CASES = [
    (_rosenbrock, [-1.2, 1.0], 0.5),
    (_skewed, [0.0, 0.0, 0.0], 0.7),
    (_kinked, [2.0, -1.5], 0.25),
    (_bumpy, [1.0, -0.7], 0.6),
    (lambda x: (x[0] - 0.25) ** 2, [3.0], 1.0),
]


@pytest.mark.parametrize("case", range(len(CASES)))
def test_nelder_mead_matches_the_textbook_iterate_by_iterate(case: int) -> None:
    f, start, step = CASES[case]
    seen: set[str] = set()
    for iterations in range(120):
        got = v._nelder_mead(f, list(start), step, iterations)
        want = _reference(f, list(start), step, iterations, seen)
        assert got == want, iterations


def test_nelder_mead_reference_runs_every_branch() -> None:
    # the comparison above is only as strong as the paths it walks
    seen: set[str] = set()
    for f, start, step in CASES:
        for iterations in (40, 120, 4000):
            assert v._nelder_mead(f, list(start), step, iterations) == _reference(
                f, list(start), step, iterations, seen
            )
    assert seen == {
        "expand",
        "reflect after expansion fails",
        "reflect",
        "outside",
        "inside",
        "shrink",
        "stop",
    }


def test_nelder_mead_converges_to_the_minimum() -> None:
    x, fx = v._nelder_mead(_rosenbrock, [-1.2, 1.0], 0.5, 4000)
    assert x == pytest.approx([1.0, 1.0], abs=1e-6) and fx < 1e-12
    # in one dimension the method can stop on two points of equal value either side of the
    # minimum: from 3 with step 1 it ends on {0, 0.5}, both f = 0.0625, and returns the first
    assert v._nelder_mead(lambda p: (p[0] - 0.25) ** 2, [3.0], 1.0, 4000) == ([0.0], 0.0625)


def test_nelder_mead_stops_at_once_on_a_flat_function() -> None:
    calls: list[list[float]] = []

    def flat(x: list[float]) -> float:
        calls.append(list(x))
        return 2.0

    assert v._nelder_mead(flat, [1.0, 2.0], 0.5, 100) == ([1.0, 2.0], 2.0)
    assert calls == [[1.0, 2.0], [1.5, 2.0], [1.0, 2.5]]
