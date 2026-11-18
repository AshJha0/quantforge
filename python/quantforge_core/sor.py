"""`exec.sor.allocate`: order placement over simulated lit and dark venues ([CK] Cont-Kukanov).

Spec: specifications/10-execution/smart-order-router.md (rulings HR-37 to HR-40). Simulated
venues; router scored in simulation only.

Cost per scenario is [CK] eq. 5 with the dark extension of HR-37:
    (h + f) M - sum_k (h + r_k - as_k) fill_k + theta (M + sum_k L_k + (S - A)_+)
        + lambda_u (S - A)_+ + lambda_o (A - S)_+,
LIT fill = (xi - Q)_+ - (xi - Q - L)_+, DARK fill = min(L, s), A = M + sum fills. The expectation
is exact: equally weighted `lit_samples` rows times the independent dark distributions given by
their tails, in rational arithmetic (`fractions.Fraction`), rounded half-even to 6 decimals only
on output.

Methods: `SAMPLE_AVERAGE` (HR-39; exhaustive integer search over 0..S per coordinate, HR-38, ties
to the lexicographically smallest (M, L_1, ..., L_K); coordinate descent from the [CK] Prop. 3
start when the grid exceeds 10^6 points), `CLOSED_FORM` ([CK] Prop. 3, one lit venue, empirical
left-inverse quantile), `STOCHASTIC_APPROX` ([CK] section 4 projected subgradient with averaged
iterates, rounded to the best neighbouring integer point).
"""

import itertools
import math
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from typing import Any

from .dark_pool import asset_class
from .errors import QfError
from .finite import guard
from .lit_matching import _dec
from .order_book import EXACT, check_range
from .rng import Xoshiro256

LABEL = "simulated venues; router scored in simulation only"
MAX_VENUES = 64
MAX_SAMPLES = 1_000_000
MAX_GRID = 1_000_000
METHODS = ("SAMPLE_AVERAGE", "CLOSED_FORM", "STOCHASTIC_APPROX")


def _frac(v: Any, path: str) -> Fraction:
    return Fraction(_dec(v, path))


def _lots(v: Any, path: str) -> int:
    d = _dec(v, path)
    if d != d.to_integral_value() or d < 0:
        raise QfError("E_DOMAIN", f"{path}: not a non-negative integer number of lots", path)
    return int(d)


def _r(x: Fraction) -> Fraction:
    """HR-57/HR-58: every exact value the router computes must be a decimal in range, else `E_LIMIT`.
    The checks sit at the same steps as the C++ and Java ports (each sum, difference and product of
    the cost of a scenario and of the row totals), so the four builds agree on which inputs fail."""
    with localcontext(EXACT):
        check_range(Decimal(x.numerator) / Decimal(x.denominator), "sor")
    return x


def _dec18(x: Fraction) -> float:
    """`x` rounded half-even to 18 decimals, then read as binary64 (correctly rounded)."""
    with localcontext(EXACT):
        d = (Decimal(x.numerator) / Decimal(x.denominator)).quantize(
            Decimal(10) ** -18, rounding=ROUND_HALF_EVEN
        )
    return float(d)


def _se(mean_cost: Fraction, mean_sq: Fraction, n_rows: int) -> str:
    """HR-40 standard error, one rule in all four builds: a = E[c^2] and b = E[c], each exact, rounded
    half-even to 18 decimals and read as binary64; then in binary64, with no fused multiply-add,
    se = sqrt(max(a - b * b, 0) / n_rows); written rounded half-even to 6 decimals from the exact
    binary value. The binary64 steps are IEEE 754 basic operations, so every build gets the same bits."""
    a, b = _dec18(mean_sq), _dec18(mean_cost)
    bb = b * b
    se = math.sqrt(max(a - bb, 0.0) / n_rows)
    return _fmt6(round(Fraction(se) * 10**6))  # exact binary value, ties to even


def _out(x: Fraction) -> str:
    """`x` rounded half-even to 6 decimals, exactly (`round` on a Fraction ties to even), with no
    decimal context in between, so a 36-digit value keeps every digit."""
    return _fmt6(round(x * 10**6))


def _fmt6(q: int) -> str:
    """The decimal string of q / 10^6: no exponent, no trailing zeros, "0" for zero (HR-12)."""
    sign, q = ("-" if q < 0 else ""), abs(q)
    whole, frac = divmod(q, 10**6)
    tail = f"{frac:06d}".rstrip("0")
    return "0" if q == 0 else f"{sign}{whole}" + (f".{tail}" if tail else "")


class Problem:
    def __init__(self, inp: dict[str, Any]):
        self.S = _lots(inp.get("S"), "S")
        if self.S <= 0:
            raise QfError("E_DOMAIN", "S must be positive", "S")
        g = {k: _frac(inp.get(k), k) for k in ("h", "f", "theta", "lambda_u", "lambda_o")}
        if any(g[k] < 0 for k in ("theta", "lambda_u", "lambda_o")):
            raise QfError("E_DOMAIN", "negative penalty", "lambda_u")
        self.h, self.f, self.theta, self.lu, self.lo = (
            g["h"],
            g["f"],
            g["theta"],
            g["lambda_u"],
            g["lambda_o"],
        )
        venues = inp.get("venues")
        if not isinstance(venues, list) or not venues:
            raise QfError("E_INPUT", "venues: empty", "venues")
        order_class = asset_class(inp.get("asset_class"), "asset_class")
        classes = [
            asset_class(
                v.get("asset_class") if isinstance(v, dict) else None, f"venues/{k}/asset_class"
            )
            for k, v in enumerate(venues)
        ]
        if any(c != order_class for c in classes):
            raise QfError(
                "E_INPUT", "a venue's asset_class differs from the order's (HR-93)", "venues"
            )
        for k, v in enumerate(venues):
            if isinstance(v, dict) and v.get("kind") == "DARK":
                asset_class(classes[k], f"venues/{k}/asset_class", dark=True)
        if len(venues) > MAX_VENUES:
            raise QfError("E_LIMIT", "more than 64 venues", "venues")
        self.kinds: list[str] = []
        self.Q: list[int] = []
        self.coef: list[Fraction] = []  # h + r - as
        self.tails: list[list[Fraction]] = []
        for k, v in enumerate(venues):
            kind = v.get("kind") if isinstance(v, dict) else None
            if kind not in ("LIT", "DARK"):
                raise QfError("E_SCHEMA", f"venues/{k}/kind", "venues")
            self.kinds.append(kind)
            self.coef.append(
                _r(
                    _r(self.h + _frac(v.get("r"), f"venues/{k}/r"))
                    - _frac(v.get("as"), f"venues/{k}/as")
                )
            )
            if kind == "LIT":
                self.Q.append(_lots(v.get("Q"), f"venues/{k}/Q"))
                self.tails.append([])
            else:
                self.Q.append(0)
                tail = [_frac(t, f"venues/{k}/tail") for t in v.get("tail", [])]
                if any(not 0 <= t <= 1 for t in tail) or any(
                    a < b for a, b in itertools.pairwise(tail)
                ):
                    raise QfError("E_DOMAIN", f"venues/{k}/tail: not a tail", "venues")
                self.tails.append(tail)
        self.want_sq = (
            inp.get("report_se", False) is True
        )  # only then is sum p c^2 computed (and range-checked)
        self.lit = [k for k, kd in enumerate(self.kinds) if kd == "LIT"]
        self.dark = [k for k, kd in enumerate(self.kinds) if kd == "DARK"]
        rows = inp.get("lit_samples", [])
        if self.lit and (not isinstance(rows, list) or not rows):
            raise QfError("E_INPUT", "lit_samples: empty", "lit_samples")
        if len(rows) > MAX_SAMPLES:
            raise QfError("E_LIMIT", "more than 10^6 samples", "lit_samples")
        self.rows = [[_lots(x, f"lit_samples/{i}") for x in r] for i, r in enumerate(rows)] or [[]]
        if any(len(r) != len(self.lit) for r in self.rows):
            raise QfError("E_INPUT", "lit_samples: one value per LIT venue per row", "lit_samples")

    def tail(self, k: int, s: int) -> Fraction:
        t = self.tails[k]
        return Fraction(1) if s <= 0 else (t[s - 1] if s <= len(t) else Fraction(0))

    def dark_dist(self, k: int, L: int) -> list[tuple[int, Fraction]]:
        """Distribution of min(L, s) for dark venue k."""
        out = [(j, _r(self.tail(k, j) - self.tail(k, j + 1))) for j in range(L)]
        out.append((L, self.tail(k, L)))
        return [(j, p) for j, p in out if p]

    def scenario_cost(self, M: int, L: list[int], fills: list[int]) -> tuple[Fraction, int]:
        """Cost of one scenario, each step range-checked (HR-57) in the order the C++ port takes."""
        A = M + sum(fills)
        under, over = max(self.S - A, 0), max(A - self.S, 0)
        c = _r(_r(self.h + self.f) * M)
        for k in range(len(L)):
            if fills[k]:
                c = _r(c - _r(self.coef[k] * fills[k]))
        if self.theta:
            c = _r(c + _r(self.theta * (M + sum(L) + under)))
        if under:
            c = _r(c + _r(self.lu * under))
        if over:
            c = _r(c + _r(self.lo * over))
        return c, A

    def evaluate(self, M: int, L: list[int]) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        """Exact (expected cost, E min(A, S), P(A < S), E cost^2)."""
        dists = [self.dark_dist(k, L[k]) for k in self.dark]
        # Row sums first (each step range-checked, HR-57), divided by the row count at the end.
        cost = fill = under = sq = Fraction(0)
        n_rows = len(self.rows)
        for row in self.rows:
            base = [0] * len(L)
            for i, k in enumerate(self.lit):
                x = row[i] - self.Q[k]
                base[k] = max(x, 0) - max(x - L[k], 0)
            for combo in itertools.product(*dists) if dists else [()]:
                p = Fraction(1)
                fills = list(base)
                for (j, pj), k in zip(combo, self.dark):
                    fills[k] = j
                    p = _r(p * pj)
                c, A = self.scenario_cost(M, L, fills)
                cost = _r(cost + _r(p * c))
                if self.want_sq:
                    sq = _r(sq + _r(_r(p * c) * c))
                fill = _r(fill + _r(p * min(A, self.S)))
                if A < self.S:
                    under = _r(under + p)
        return cost / n_rows, fill / n_rows, under / n_rows, sq / n_rows

    # ------------------------------------------------------------ methods
    def closed_form(self) -> tuple[int, list[int]]:
        """[CK] Prop. 3 for one lit venue, F the empirical CDF of xi, left-inverse quantile."""
        if self.kinds != ["LIT"]:
            raise QfError("E_DOMAIN", "CLOSED_FORM needs exactly one LIT venue", "method")
        xs = sorted(r[0] for r in self.rows)
        n, Q, S = len(xs), self.Q[0], self.S
        r_eff = _r(self.coef[0] - self.h)
        num = _r(_r(_r(self.h + self.h) + self.f) + r_eff)
        base = _r(_r(self.h + r_eff) + self.theta)

        def count(x: int) -> int:  # n F(x)
            return sum(1 for v in xs if v <= x)

        # lambda_u <= num / F(x) - base  <=>  (lambda_u + base) c <= num n, with c = n F(x) > 0; compared in
        # this cross-multiplied form, each step range-checked (HR-57), as the C++, Java and Rust ports do.
        lb, numn = _r(self.lu + base), _r(num * n)
        c_lo, c_hi = count(Q + S), count(Q)
        if c_lo == 0 or _r(lb * c_lo) <= numn:
            return 0, [S]
        if c_hi != 0 and _r(lb * c_hi) >= numn:
            return S, [0]
        if lb == 0:
            raise QfError("E_DOMAIN", "lambda_u + h + r + theta is zero", "lambda_u")
        q = xs[-1]
        for v in xs:
            lhs = _r(lb * count(v))
            if (lhs >= numn) if lb > 0 else (lhs <= numn):
                q = v
                break
        M = min(max(S - q + Q, 0), S)
        return M, [S - M]

    def sample_average(
        self, ranking: bool
    ) -> tuple[tuple[int, ...], list[tuple[Fraction, tuple[int, ...]]]]:
        K = len(self.kinds)
        if (self.S + 1) ** (K + 1) <= MAX_GRID:
            scored = sorted(
                (self.evaluate(t[0], list(t[1:]))[0], t)
                for t in itertools.product(range(self.S + 1), repeat=K + 1)
            )
            return scored[0][1], scored if ranking else []
        if ranking:
            raise QfError("E_LIMIT", "ranking needs a grid of at most 10^6 points", "ranking")
        return self._descent(), []

    def _start(self) -> tuple[int, ...]:
        if self.kinds == ["LIT"]:
            M, L = self.closed_form()
            return (M, *L)
        return (0, *([self.S] if self.kinds[0] == "LIT" else [0]), *([0] * (len(self.kinds) - 1)))

    def _descent(self, start: tuple[int, ...] | None = None) -> tuple[int, ...]:
        """Exact coordinate descent on the sample-average cost from `start` (default the [CK]
        single-venue start); each pass tries every value 0..S per coordinate."""
        best = list(self._start() if start is None else start)
        cur = self.evaluate(best[0], best[1:])[0]
        changed = True
        while changed:
            changed = False
            for i in range(len(best)):
                for v in range(self.S + 1):
                    t = list(best)
                    t[i] = v
                    c = self.evaluate(t[0], t[1:])[0]
                    if (c, tuple(t)) < (cur, tuple(best)):
                        best, cur, changed = t, c, True
        return tuple(best)

    def stochastic(self, iterations: int, step: float, seed: int) -> tuple[int, ...]:
        """[CK] section 4: projected subgradient on X in [0, S]^(K+1), step / sqrt(n), iterates
        averaged; the average is rounded to the best floor/ceiling neighbour (HR-38)."""
        rng = Xoshiro256.seeded(seed)
        K = len(self.kinds)
        x = [float(v) for v in self._start()]
        avg = [0.0] * (K + 1)
        h, f, th, lu, lo = (float(v) for v in (self.h, self.f, self.theta, self.lu, self.lo))
        coef = [float(c) for c in self.coef]
        for n in range(1, iterations + 1):
            row = self.rows[min(int(rng.uniform() * len(self.rows)), len(self.rows) - 1)]
            room = [0.0] * K  # 1 when the venue's outflow exceeds the posted size
            fills = [0.0] * K
            for i, k in enumerate(self.lit):
                xi = row[i] - self.Q[k]
                fills[k] = min(max(xi, 0.0), x[k + 1])
                room[k] = 1.0 if xi > x[k + 1] else 0.0
            for k in self.dark:
                u, s = rng.uniform(), 0
                while s < len(self.tails[k]) and u < float(self.tails[k][s]):
                    s += 1
                fills[k] = min(float(s), x[k + 1])
                room[k] = 1.0 if s > x[k + 1] else 0.0
            A = x[0] + sum(fills)
            g_a = (-(lu + th) if A < self.S else 0.0) + (lo if A > self.S else 0.0)
            grad = [h + f + th + g_a] + [th + room[k] * (g_a - coef[k]) for k in range(K)]
            eta = step / math.sqrt(n)
            x = [min(max(v - eta * g, 0.0), float(self.S)) for v, g in zip(x, grad)]
            avg = [a + (v - a) / n for a, v in zip(avg, x)]
        cands = itertools.product(*[sorted({math.floor(a), math.ceil(a)}) for a in avg])
        rounded = min((self.evaluate(t[0], list(t[1:]))[0], t) for t in cands)[1]
        # The subgradient is zero where the cost is flat in a coordinate (posted size beyond every
        # outflow, theta = 0), so the averaged iterate can stop anywhere on that plateau; an exact
        # coordinate-descent polish from the rounded point moves it to the integer optimum.
        return self._descent(rounded)


def _step(v: Any) -> float:
    """`step`, the one Real input: a JSON number, or "NaN" / "Infinity" / "-Infinity" (E_SCHEMA otherwise)."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise QfError("E_SCHEMA", "step: not a number", "step")
    if isinstance(v, str) and v not in ("NaN", "Infinity", "-Infinity"):
        raise QfError("E_SCHEMA", "step: not a number", "step")
    return float(v)


def allocate(inp: dict[str, Any]) -> dict[str, Any]:
    step = _step(inp.get("step", 1.0))
    if not math.isfinite(
        step
    ):  # F-2 (E1): a non-finite Real input is E_DOMAIN, the first rule check
        raise QfError("E_DOMAIN", "step: not finite", "step")
    p = Problem(inp)
    method = inp.get("method", "SAMPLE_AVERAGE")
    if method not in METHODS:
        raise QfError("E_SCHEMA", "method", "method")
    want_rank = inp.get("ranking", False) is True
    ranking: list[tuple[Fraction, tuple[int, ...]]] = []
    if method == "CLOSED_FORM":
        M, L = p.closed_form()
        best = (M, *L)
    elif method == "STOCHASTIC_APPROX":
        best = p.stochastic(int(inp.get("iterations", 10_000)), step, int(inp.get("seed", 0)))
    else:
        best, ranking = p.sample_average(want_rank)
    cost, fill, under, sq = p.evaluate(best[0], list(best[1:]))
    out: dict[str, Any] = {
        "M": str(best[0]),
        "L": [str(v) for v in best[1:]],
        "expected_cost": _out(cost),
        "expected_fill": _out(fill),
        "p_underfill": _out(under),
    }
    if inp.get("report_se", False) is True:
        out["expected_cost_se"] = _se(cost, sq, len(p.rows))
        out["label"] = LABEL
    if want_rank:
        out["ranking"] = [
            {"M": str(t[0]), "L": [str(v) for v in t[1:]], "expected_cost": _out(c)}
            for c, t in ranking
        ]
    return out


guard(globals())
