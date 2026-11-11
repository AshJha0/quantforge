"""FRTB standardised approach beyond GIRR delta: FX, equity, CSR (non-securitisation) and
commodity delta, and vega and curvature for every class but CSR securitisations.

Specifications: specifications/06-risk/frtb-sa-fx-equity.md (rulings G-48, G-49) and
specifications/06-risk/frtb-sa-vega-curvature.md (ruling G-51); aggregation MAR21.4 and the three
correlation scenarios MAR21.6 as specifications/06-risk/frtb-sa-girr.md.
"""
import math
from collections.abc import Callable, Hashable, Sequence

from .errors import QfError
from .finite import guard
from .var_risk import _SCENARIOS, _scaled

Factor = tuple[Hashable, ...]
Rho = Callable[[str, Factor, Factor], float]
Gamma = Callable[[str, str], float]
CLASSES = ("GIRR", "CSR_NONSEC", "EQUITY", "COMMODITY", "FX")

# MAR21.77 Table 10 (spot weights; repo weights are 1% of these)
_EQ_RW = {1: 0.55, 2: 0.60, 3: 0.45, 4: 0.55, 5: 0.30, 6: 0.35, 7: 0.40, 8: 0.50, 9: 0.70,
          10: 0.50, 11: 0.70, 12: 0.15, 13: 0.25}
# MAR21.53 Table 4
_CSR_RW = {1: 0.005, 2: 0.010, 3: 0.050, 4: 0.030, 5: 0.030, 6: 0.020, 7: 0.015, 8: 0.025,
           9: 0.020, 10: 0.040, 11: 0.120, 12: 0.070, 13: 0.085, 14: 0.055, 15: 0.050,
           16: 0.120, 17: 0.015, 18: 0.050}
_CSR_TENORS = ("0.5Y", "1Y", "3Y", "5Y", "10Y")
# MAR21.57 Table 5, sectors 1/9 .. 7/15 as 1..7, then 8, 16, 17, 18 (upper triangle)
_SECTORS = (1, 2, 3, 4, 5, 6, 7, 8, 16, 17, 18)
_TABLE5 = {
    1: (75, 10, 20, 25, 20, 15, 10, 0, 45, 45),
    2: (5, 15, 20, 15, 10, 10, 0, 45, 45),
    3: (5, 15, 20, 5, 20, 0, 45, 45),
    4: (20, 25, 5, 5, 0, 45, 45),
    5: (25, 5, 15, 0, 45, 45),
    6: (5, 20, 0, 45, 45),
    7: (5, 0, 45, 45),
    8: (0, 45, 45),
    16: (0, 0),
    17: (75,),
}
# MAR21.82 Table 11 and MAR21.83 Table 12
_CMD_RW = {1: 0.30, 2: 0.35, 3: 0.60, 4: 0.80, 5: 0.40, 6: 0.45, 7: 0.20, 8: 0.35, 9: 0.25,
           10: 0.35, 11: 0.50}
_CMD_RHO = {1: 0.55, 2: 0.95, 3: 0.40, 4: 0.80, 5: 0.60, 6: 0.65, 7: 0.55, 8: 0.45, 9: 0.15,
            10: 0.40, 11: 0.15}


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def bucket_key(label: str) -> tuple[int, str]:
    """Bucket order: by length, then text (`5` < `9` < `11`, `EUR` < `USD`)."""
    return len(label), label


# --- per-class correlations ----------------------------------------------------------------------


def _eq_name_rho(bucket: int) -> float:
    """MAR21.78: different issuers, same kind."""
    if bucket <= 4:
        return 0.15
    if bucket <= 8:
        return 0.25
    return {9: 0.075, 10: 0.125}.get(bucket, 0.80)


def _eq_gamma(b: str, c: str) -> float:
    x, y = int(b), int(c)
    if 11 in (x, y):
        return 0.0
    if x <= 10 and y <= 10:
        return 0.15
    if {x, y} == {12, 13}:
        return 0.75
    return 0.45


def _csr_name_rho(bucket: int) -> float:
    return 0.80 if bucket in (17, 18) else 0.35


def _sector(bucket: int) -> int:
    return bucket - 8 if 9 <= bucket <= 15 else bucket


def _csr_gamma(b: str, c: str) -> float:
    x, y = int(b), int(c)
    rating = 0.5 if (x <= 15 and y <= 15 and (x <= 8) != (y <= 8)) else 1.0
    s, t = _sector(x), _sector(y)
    if s == t:
        sector = 1.0
    else:
        i, j = sorted((_SECTORS.index(s), _SECTORS.index(t)))
        sector = _TABLE5[_SECTORS[i]][j - i - 1] / 100
    return rating * sector


def _cmd_gamma(b: str, c: str) -> float:
    return 0.0 if 11 in (int(b), int(c)) else 0.20


# --- aggregation (MAR21.4, 21.6) -----------------------------------------------------------------


def _net(items: Sequence[tuple[Factor, float]]) -> list[tuple[Factor, float]]:
    out: dict[Factor, float] = {}
    for f, w in items:
        out[f] = out.get(f, 0.0) + w
    return list(out.items())


def aggregate(buckets: dict[str, list[tuple[Factor, float]]], rho: Rho, gamma: Gamma,
              simple: frozenset[str] = frozenset(), measure: str = "delta") -> dict[str, object]:
    """Weighted sensitivities per bucket to capital under the three scenarios. Buckets in
    `simple` (other sector) take `K = sum |net WS|` with no correlation."""
    order = sorted(buckets, key=bucket_key)
    scenarios: dict[str, object] = {}
    values: dict[str, float] = {}
    for sc in _SCENARIOS:
        ks, ss = [], []
        for name in order:
            items = buckets[name]
            if name in simple:
                ks.append(sum(abs(w) for _, w in _net(items)))
            else:
                total = sum(w * w for _, w in items)
                for i, (fi, wi) in enumerate(items):
                    for j, (fj, wj) in enumerate(items):
                        if i != j:
                            total += _scaled(rho(name, fi, fj), sc) * wi * wj
                ks.append(math.sqrt(max(0.0, total)))
            ss.append(sum(w for _, w in items))

        def under(s: Sequence[float], ks: Sequence[float] = ks, sc: str = sc) -> float:
            total = sum(k * k for k in ks)
            for b in range(len(s)):
                for c in range(len(s)):
                    if b != c:
                        total += _scaled(gamma(order[b], order[c]), sc) * s[b] * s[c]
            return total

        used = list(ss)
        value = under(ss)
        alternative = False
        if value < 0:
            alternative = True
            used = [max(min(s, k), -k) for s, k in zip(ss, ks, strict=True)]
            value = under(used)
        values[sc] = math.sqrt(max(0.0, value))
        scenarios[sc] = {
            "buckets": [{"bucket": c, "k": k, "s": s, "s_used": u}
                        for c, k, s, u in zip(order, ks, ss, used, strict=True)],
            measure: values[sc], "alternative_used": alternative}
    binding = max(_SCENARIOS, key=lambda sc: (values[sc], -_SCENARIOS.index(sc)))
    return {"scenarios": scenarios, "capital": values[binding], "binding_scenario": binding}


# --- delta ---------------------------------------------------------------------------------------


def fx_delta(sensitivities: Sequence[tuple[str, float]],
             specified: Sequence[str]) -> dict[str, object]:
    """FX delta: RW 15% (over sqrt 2 for a specified pair), one factor per bucket, gamma 60%."""
    if not sensitivities:
        raise _input("no sensitivities", "sensitivities")
    pairs = [p for p, _ in sensitivities]
    if len(set(pairs)) != len(pairs):
        raise _input("a pair appears twice", "sensitivities")
    listed = set(specified)
    buckets: dict[str, list[tuple[Factor, float]]] = {
        p: [((p,), (0.15 / math.sqrt(2) if p in listed else 0.15) * s)] for p, s in sensitivities}
    return aggregate(buckets, lambda b, f, g: 1.0, lambda b, c: 0.6)


def equity_delta(sensitivities: Sequence[tuple[str, int, str, float]]) -> dict[str, object]:
    """Equity delta, spot and repo, buckets 1 to 13 (MAR21.77 to 21.80); bucket 11 by sum."""
    if not sensitivities:
        raise _input("no sensitivities", "sensitivities")
    for _, bucket, kind, _ in sensitivities:
        if bucket not in _EQ_RW:
            raise _input(f"bucket {bucket} is not an equity bucket", "bucket")
        if kind not in ("SPOT", "REPO"):
            raise _input(f"{kind} is not SPOT or REPO", "kind")
    keys = [(i, b, k) for i, b, k, _ in sensitivities]
    if len(set(keys)) != len(keys):
        raise _input("the same factor appears twice", "sensitivities")
    buckets: dict[str, list[tuple[Factor, float]]] = {}
    for issuer, bucket, kind, s in sensitivities:
        rw = _EQ_RW[bucket] * (0.01 if kind == "REPO" else 1.0)
        buckets.setdefault(str(bucket), []).append(((issuer, kind), rw * s))

    def rho(bucket: str, f: Factor, g: Factor) -> float:
        if f[0] == g[0]:
            return 0.999
        base = _eq_name_rho(int(bucket))
        return base if f[1] == g[1] else base * 0.999

    return aggregate(buckets, rho, _eq_gamma, frozenset({"11"}))


def csr_delta(sensitivities: Sequence[tuple[str, int, str, str, float]]) -> dict[str, object]:
    """CSR non-securitisation delta (MAR21.51 to 21.57); bucket 16 by sum."""
    if not sensitivities:
        raise _input("no sensitivities", "sensitivities")
    for _, bucket, tenor, curve, _ in sensitivities:
        if bucket not in _CSR_RW:
            raise _input(f"bucket {bucket} is not a CSR bucket", "bucket")
        if tenor not in _CSR_TENORS:
            raise _input(f"{tenor} is not a CSR tenor", "tenor")
        if curve not in ("BOND", "CDS"):
            raise _input(f"{curve} is not BOND or CDS", "curve")
    keys = [(i, b, t, c) for i, b, t, c, _ in sensitivities]
    if len(set(keys)) != len(keys):
        raise _input("the same factor appears twice", "sensitivities")
    buckets: dict[str, list[tuple[Factor, float]]] = {}
    for issuer, bucket, tenor, curve, s in sensitivities:
        buckets.setdefault(str(bucket), []).append(((issuer, tenor, curve), _CSR_RW[bucket] * s))

    def rho(bucket: str, f: Factor, g: Factor) -> float:
        name = 1.0 if f[0] == g[0] else _csr_name_rho(int(bucket))
        tenor = 1.0 if f[1] == g[1] else 0.65
        basis = 1.0 if f[2] == g[2] else 0.999
        return name * tenor * basis

    return aggregate(buckets, rho, _csr_gamma, frozenset({"16"}))


def commodity_delta(sensitivities: Sequence[tuple[str, int, str, str, float]]
                    ) -> dict[str, object]:
    """Commodity delta (MAR21.82 to 21.85)."""
    if not sensitivities:
        raise _input("no sensitivities", "sensitivities")
    for _, bucket, _, _, _ in sensitivities:
        if bucket not in _CMD_RW:
            raise _input(f"bucket {bucket} is not a commodity bucket", "bucket")
    keys = [(c, b, t, loc) for c, b, t, loc, _ in sensitivities]
    if len(set(keys)) != len(keys):
        raise _input("the same factor appears twice", "sensitivities")
    buckets: dict[str, list[tuple[Factor, float]]] = {}
    for cty, bucket, tenor, loc, s in sensitivities:
        buckets.setdefault(str(bucket), []).append(((cty, tenor, loc), _CMD_RW[bucket] * s))

    def rho(bucket: str, f: Factor, g: Factor) -> float:
        cty = 1.0 if f[0] == g[0] else _CMD_RHO[int(bucket)]
        tenor = 1.0 if f[1] == g[1] else 0.99
        basis = 1.0 if f[2] == g[2] else 0.999
        return cty * tenor * basis

    return aggregate(buckets, rho, _cmd_gamma)


# --- vega and curvature (G-51) -------------------------------------------------------------------


def _class_bucket(risk_class: str, bucket: object) -> str:
    """Checks a bucket label for its class and returns it as text."""
    if risk_class in ("GIRR", "FX"):
        if not isinstance(bucket, str) or not bucket:
            raise _input("GIRR and FX buckets are currency or pair labels", "bucket")
        return bucket
    table = {"EQUITY": _EQ_RW, "CSR_NONSEC": _CSR_RW, "COMMODITY": _CMD_RW}[risk_class]
    if isinstance(bucket, bool) or not isinstance(bucket, int) or bucket not in table:
        raise _input(f"bucket {bucket} is not a {risk_class} bucket", "bucket")
    return str(bucket)


def _name_rho(risk_class: str, bucket: str, a: Hashable, b: Hashable) -> float:
    """The delta correlation along the name dimension only (MAR21.94 FAQ1)."""
    if risk_class in ("GIRR", "FX") or a == b:
        return 1.0
    if risk_class == "EQUITY":
        return _eq_name_rho(int(bucket))
    if risk_class == "CSR_NONSEC":
        return _csr_name_rho(int(bucket))
    return _CMD_RHO[int(bucket)]


def _gamma(risk_class: str) -> Gamma:
    return {"GIRR": lambda b, c: 0.5, "FX": lambda b, c: 0.6, "EQUITY": _eq_gamma,
            "CSR_NONSEC": _csr_gamma, "COMMODITY": _cmd_gamma}[risk_class]


def _simple(risk_class: str) -> frozenset[str]:
    return {"EQUITY": frozenset({"11"}), "CSR_NONSEC": frozenset({"16"})}.get(
        risk_class, frozenset())


def _check_class(risk_class: str) -> None:
    if risk_class not in CLASSES:
        raise _input(f"{risk_class} is not a risk class of this slice", "risk_class")


def vega(risk_class: str, sensitivities: Sequence[tuple[object, str | None, float,
                                                         float | None, float]]
         ) -> dict[str, object]:
    """`risk.frtb.vega`: rows (bucket, name, option_maturity, underlying_maturity, vega)."""
    _check_class(risk_class)
    if not sensitivities:
        raise _input("no sensitivities", "sensitivities")
    girr = risk_class == "GIRR"
    buckets: dict[str, list[tuple[Factor, float]]] = {}
    for bucket, name, t, u, vr in sensitivities:
        label = _class_bucket(risk_class, bucket)
        if girr and u is None:
            raise _input("GIRR vega needs underlying_maturity", "underlying_maturity")
        if not girr and u is not None:
            raise _input("underlying_maturity is for GIRR only", "underlying_maturity")
        if risk_class not in ("GIRR", "FX") and name is None:
            raise _input("this class needs a name", "name")
        if not t > 0:
            raise QfError("E_DOMAIN", "option_maturity must be above 0", "option_maturity")
        if u is not None and not u > 0:
            raise QfError("E_DOMAIN", "underlying_maturity must be above 0",
                          "underlying_maturity")
        rw = 0.7778 if (risk_class == "EQUITY" and int(label) in (1, 2, 3, 4, 5, 6, 7, 8, 12,
                                                                    13)) else 1.0
        buckets.setdefault(label, []).append(((name, t, u), rw * vr))
    buckets = {b: _net(items) for b, items in buckets.items()}
    a = 0.01

    def rho(bucket: str, f: Factor, g: Factor) -> float:
        tf, tg = float(f[1]), float(g[1])  # type: ignore[arg-type]
        mat = math.exp(-a * abs(tf - tg) / min(tf, tg))
        if girr:
            uf, ug = float(f[2]), float(g[2])  # type: ignore[arg-type]
            return min(mat * math.exp(-a * abs(uf - ug) / min(uf, ug)), 1.0)
        return min(_name_rho(risk_class, bucket, f[0], g[0]) * mat, 1.0)

    return aggregate(buckets, rho, _gamma(risk_class), _simple(risk_class), "vega")


def _psi(x: float, y: float) -> float:
    return 0.0 if x < 0 and y < 0 else 1.0


def curvature(risk_class: str, factors: Sequence[tuple[object, str | None, float, float]],
              fx_scalar: bool) -> dict[str, object]:
    """`risk.frtb.curvature`: rows (bucket, name, cvr_up, cvr_down) (MAR21.5, 21.98 to 21.101)."""
    _check_class(risk_class)
    if fx_scalar and risk_class != "FX":
        raise _input("fx_scalar is for FX only", "fx_scalar")
    if not factors:
        raise _input("no factors", "factors")
    rows: dict[str, list[tuple[Hashable, float, float]]] = {}
    seen = set()
    scale = 1.5 if fx_scalar else 1.0
    for bucket, name, up, down in factors:
        label = _class_bucket(risk_class, bucket)
        if (label, name) in seen:
            raise _input("the same factor appears twice", "factors")
        seen.add((label, name))
        rows.setdefault(label, []).append((name, up / scale, down / scale))
    order = sorted(rows, key=bucket_key)
    simple = _simple(risk_class)
    gamma = _gamma(risk_class)
    scenarios: dict[str, object] = {}
    values: dict[str, float] = {}
    for sc in _SCENARIOS:
        ks: list[float] = []
        ss: list[float] = []
        sel: list[str] = []
        for label in order:
            items = rows[label]
            names = [r[0] for r in items]
            cvrs = ([r[1] for r in items], [r[2] for r in items])
            sums = [sum(cvrs[0]), sum(cvrs[1])]
            if label in simple:
                kp = sum(max(v, 0.0) for v in cvrs[0])
                km = sum(max(v, 0.0) for v in cvrs[1])
            else:
                k2: list[float] = []
                for side in cvrs:
                    total = sum(max(v, 0.0) ** 2 for v in side)
                    for i, vi in enumerate(side):
                        for j, vj in enumerate(side):
                            if i != j:
                                c = _name_rho(risk_class, label, names[i], names[j])
                                total += _scaled(c * c, sc) * vi * vj * _psi(vi, vj)
                    k2.append(math.sqrt(max(0.0, total)))
                kp, km = k2
            up = kp > km or (kp == km and sums[0] > sums[1])
            ks.append(kp if up else km)
            ss.append(sums[0] if up else sums[1])
            sel.append("UP" if up else "DOWN")
        total = 0.0
        for k in ks:
            total += k * k
        for b in range(len(order)):
            for c in range(len(order)):
                if b != c:
                    g = gamma(order[b], order[c])
                    total += _scaled(g * g, sc) * ss[b] * ss[c] * _psi(ss[b], ss[c])
        values[sc] = math.sqrt(max(0.0, total))
        scenarios[sc] = {"buckets": [{"bucket": b, "k": k, "s": s, "selected": x}
                                     for b, k, s, x in zip(order, ks, ss, sel, strict=True)],
                         "curvature": values[sc]}
    binding = max(_SCENARIOS, key=lambda sc: (values[sc], -_SCENARIOS.index(sc)))
    return {"scenarios": scenarios, "capital": values[binding], "binding_scenario": binding}


guard(globals())
