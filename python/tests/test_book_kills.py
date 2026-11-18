"""Kill tests for `quantforge_core.book` and `book_risk` mutants that survived the H-0 Actions run
44317826833 (conformance/mutation/python-h0-2026-11-18.md).

Each test checks behaviour from specifications/06-risk/book-sensitivities.md and
04-pricing/use-cases.md (use case 4): error code and field (the CLI contract, not the message
text), sensitivities against bump-and-reprice, the PCA repeated-eigenvalue rule, the OLS standard
error formula and the jump-to-default table.
"""

import math
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from quantforge_core import book, book_risk, curves, ois
from quantforge_core.errors import QfError
from quantforge_core.ois import OisTrade, Quote

AS_OF = date(2026, 11, 10)
QUOTES = [
    Quote(t, r)
    for t, r in (("1M", 0.043), ("1Y", 0.039), ("2Y", 0.0365), ("5Y", 0.0352), ("10Y", 0.0364))
]


def _err(fn: Any, *args: Any) -> tuple[str, str | None]:
    with pytest.raises(QfError) as e:
        fn(*args)
    return e.value.code, e.value.field


def test_errors_carry_code_and_field() -> None:
    assert _err(book.marks_resolve, AS_OF, ["X"], [], -1, [], 0.01) == (
        "E_DOMAIN",
        "max_age_days",
    )
    assert _err(book.factor_attribution, [0.1, 0.2, 0.3], [[0.1], [0.2]], ["A"]) == (
        "E_INPUT",
        "factor_returns",
    )
    sw = book_risk.BookSwap("A", 5, 0.03, "PAY")
    run = book_risk.ois_sensitivity
    assert _err(run, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", []) == ("E_INPUT", "swaps")
    assert _err(run, AS_OF, "SOFR", QUOTES, "LOG_LINEAR_DF", [sw, sw]) == ("E_INPUT", "swaps")


def test_collinear_factors_are_refused() -> None:
    """Two factors with B = 2A plus an intercept: X has rank 2 of 3 columns."""
    a = [0.01, -0.02, 0.015, 0.003, -0.007, 0.012]
    f = [[x, 2 * x] for x in a]
    y = [0.5 * x + 0.001 for x in a]
    assert _err(book.factor_attribution, y, f, ["A", "B"]) == ("E_DOMAIN", "factor_returns")


def test_beta_standard_error_one_factor() -> None:
    """Simple regression: se(beta) = sqrt(s^2 / sum (x - xbar)^2), s^2 = SSR / (T - 2)."""
    x = [0.01, -0.02, 0.015, 0.003, -0.007, 0.012, -0.004]
    y = [0.002 + 0.8 * v + e for v, e in zip(x, [1e-3, -2e-3, 5e-4, 0.0, 1.5e-3, -1e-3, 2e-4])]
    out: dict[str, Any] = book.factor_attribution(y, [[v] for v in x], ["A"])
    n = len(x)
    xb, yb = sum(x) / n, sum(y) / n
    sxx = sum((v - xb) ** 2 for v in x)
    beta = sum((v - xb) * (w - yb) for v, w in zip(x, y)) / sxx
    alpha = yb - beta * xb
    ssr = sum((w - alpha - beta * v) ** 2 for v, w in zip(x, y))
    se = math.sqrt(ssr / (n - 2) / sxx)
    assert out["betas"][0] == pytest.approx(beta, rel=1e-10)
    assert out["beta_se"][0] == pytest.approx(se, rel=1e-9)


def _pv(quotes: list[Quote], interp: str, swaps: list[book_risk.BookSwap]) -> list[float]:
    out: dict[str, Any] = book_risk.ois_sensitivity(AS_OF, "SOFR", quotes, interp, swaps)
    return list(out["pv"])


@pytest.mark.parametrize("interp", ["LOG_LINEAR_DF", "LINEAR_ZERO"])
def test_quote_sensitivity_matches_bump_and_reprice(interp: str) -> None:
    """IFT chain rule = central difference of the repriced book, including a 12Y swap whose late
    flows sit beyond the last pillar (extrapolation) and a 3Y swap on interior segments."""
    swaps = [
        book_risk.BookSwap("L", 12, 0.035, "PAY"),
        book_risk.BookSwap("M", 3, 0.037, "RECEIVE"),
    ]
    out: dict[str, Any] = book_risk.ois_sensitivity(AS_OF, "SOFR", QUOTES, interp, swaps)
    sens = out["quote_sensitivity"]["matrix"]
    h = 1e-6
    for j in range(len(QUOTES)):
        up = [replace(q, rate=q.rate + h) if k == j else q for k, q in enumerate(QUOTES)]
        dn = [replace(q, rate=q.rate - h) if k == j else q for k, q in enumerate(QUOTES)]
        fd = [(a - b) / (2 * h) for a, b in zip(_pv(up, interp, swaps), _pv(dn, interp, swaps))]
        for i in range(len(swaps)):
            assert sens[i][j] == pytest.approx(fd[i], rel=1e-5, abs=1e-8), (i, j)


def _hadamard_changes(scales: list[float]) -> list[list[float]]:
    """8 rows, one orthogonal zero-mean +-1 column per scale: the covariance is diagonal with
    eigenvalues scale^2 * 8 / 7."""
    h = [[1.0]]
    while len(h) < 8:
        h = [r + r for r in h] + [r + [-v for v in r] for r in h]
    return [[s * h[t][c + 1] for c, s in enumerate(scales)] for t in range(8)]


def test_pca_eigenvalues_loadings_and_ratios() -> None:
    out: dict[str, Any] = book_risk.pca(_hadamard_changes([3.0, 2.0, 1.0]), 2)
    lam = [9.0 * 8 / 7, 4.0 * 8 / 7, 1.0 * 8 / 7]
    assert out["eigenvalues"] == pytest.approx(lam, rel=1e-12)
    assert out["explained_ratio"] == pytest.approx([v / sum(lam) for v in lam[:2]], rel=1e-12)
    assert out["loadings"][0] == pytest.approx([1.0, 0.0, 0.0], abs=1e-12)
    assert out["loadings"][1] == pytest.approx([0.0, 1.0, 0.0], abs=1e-12)


def test_pca_refuses_a_repeated_eigenvalue_after_the_first() -> None:
    """Eigenvalues 4, 2, 2, 1 with two components: loading 2 is not unique (lambda_2 = lambda_3)."""
    changes = _hadamard_changes([2.0, math.sqrt(2.0), math.sqrt(2.0), 1.0])
    assert _err(book_risk.pca, changes, 2) == ("E_DOMAIN", "components")


def _trade_pv(data: curves.CurveData, trade: OisTrade, shifts: dict[int, float]) -> float:
    """PV with pillar zero-rate shifts s_k: D_k -> D_k exp(-t_k s_k)."""
    times = [(d - data.as_of).days / 365 for d in data.dates]
    dfs = tuple(
        f * math.exp(-times[k] * shifts.get(k, 0.0)) for k, f in enumerate(data.discount_factors)
    )
    curve = curves.build(replace(data, discount_factors=dfs))
    return ois.trade_pv(trade, ois.periods(trade.convention, data.as_of, trade.tenor), curve)[0]


def test_cross_gamma_matches_second_differences() -> None:
    data, _ = ois.bootstrap("SOFR", AS_OF, QUOTES, "LOG_LINEAR_DF")
    trade = OisTrade("SOFR", "7Y", 0.036, 1e6, "PAY")
    bp = 1.0
    out: dict[str, Any] = book_risk.cross_gamma(data, trade, bp)
    assert out["value"] == pytest.approx(_trade_pv(data, trade, {}), rel=1e-13)
    h = bp * 1e-4
    g = out["cross_gamma"]
    for i in range(len(data.dates)):
        for j in range(i + 1):
            if i == j:
                fd = _trade_pv(data, trade, {i: h}) - 2 * out["value"]
                fd += _trade_pv(data, trade, {i: -h})
            else:
                fd = (
                    _trade_pv(data, trade, {i: h, j: h})
                    - _trade_pv(data, trade, {i: h, j: -h})
                    - _trade_pv(data, trade, {i: -h, j: h})
                    + _trade_pv(data, trade, {i: -h, j: -h})
                ) / 4
            assert g[i][j] == pytest.approx(fd / bp**2, rel=1e-4, abs=1e-6), (i, j)
    assert any(abs(g[i][j]) > 1e-3 for i in range(len(g)) for j in range(i))


def test_jtd_table_and_zero_notional() -> None:
    """Loss on default per kind; a zero notional is allowed (notional >= 0)."""
    out: dict[str, Any] = book_risk.jtd(
        [
            ("B", "BOND", 100.0, 0.4, 95.0),
            ("P", "CDS_PROTECTION_BUYER", 100.0, 0.4, 2.0),
            ("S", "CDS_PROTECTION_SELLER", 100.0, 0.4, -2.0),
            ("Z", "BOND", 0.0, 0.4, 0.0),
        ]
    )
    assert out["jtd"] == pytest.approx([40.0 - 95.0, 60.0 - 2.0, -60.0 + 2.0, 0.0], abs=1e-12)
