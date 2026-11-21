"""Packet builder's recheck (hidden side): recompute the 8 second-lane expected values from the packet's inputs with
the rules as the stripped text states them, standard-library Python only, and report the error against the
KR-67 tolerance max(1e-12 |e|, 1e-15). Our own second computation: it counts as no outside check. It shows only that
the stripped text is enough to reach the golden values at that tolerance; both Q_KS forms are evaluated alone too.

    python -I program/stage_h_blind_w2/ima2_recheck.py <checkout>
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ima2_make_packet import CASES  # noqa: E402


def avg_ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = 2 * ((i + j) / 2 + 1)  # doubled average rank, an integer
        i = j + 1
    return [int(x) for x in r]


def spearman(x, y):
    n = len(x)
    a = [r - (n + 1) for r in avg_ranks(x)]
    b = [r - (n + 1) for r in avg_ranks(y)]
    sxy = sum(p * q for p, q in zip(a, b))
    sxx = sum(p * p for p in a)
    syy = sum(q * q for q in b)
    return max(-1.0, min(1.0, sxy / math.sqrt(float(sxx) * float(syy))))


def ks_count(x, y):
    return max(abs(sum(v <= t for v in y) - sum(v <= t for v in x)) for t in set(x) | set(y))


def q_alt(x):
    s, k = 0.0, 1
    while True:
        t = math.exp(-2 * k * k * x * x)
        if t == 0:
            return 2 * s
        s += t if k % 2 else -t
        k += 1


def q_theta(x):
    s, k = 0.0, 1
    while True:
        t = math.exp(-(2 * k - 1) ** 2 * math.pi ** 2 / (8 * x * x))
        if t == 0:
            return 1 - math.sqrt(2 * math.pi) / x * s
        s += t
        k += 1


def q_ks(x):
    return 1.0 if x <= 0 else (q_theta(x) if x < 1 else q_alt(x))


def zone(r, d, n):
    if r > 0.80 and 100 * d < 9 * n:
        return "GREEN"
    if r < 0.70 or 100 * d > 12 * n:
        return "RED"
    return "AMBER"


def normal_es_factor():
    lo, hi = 0.0, 10.0
    for _ in range(200):
        m = (lo + hi) / 2
        if 0.5 * math.erfc(m / math.sqrt(2)) > 0.025:
            lo = m
        else:
            hi = m
    z = (lo + hi) / 2
    return math.exp(-z * z / 2) / math.sqrt(2 * math.pi) / (1 - 0.975)


def main():
    root = Path(sys.argv[1])
    exp = json.loads((root / "program/stage_h_blind_w2/ima2_expected.json").read_text(encoding="utf-8"))["cases"]
    worst = 0.0
    print("case\tfield\texpected\trecomputed\terror/tolerance")
    for cid, op, inp in CASES:
        if op == "risk.frtb.pla":
            h, r = inp["hpl"], inp["rtpl"]
            n = len(h)
            d = ks_count(h, r)
            rs = spearman(h, r)
            x = (d / n) * math.sqrt(n / 2)
            got = {"spearman": rs, "ks": d / n, "ks_count": d, "zone": zone(rs, d, n), "ks_pvalue_asymptotic": q_ks(x),
                   "(alternating only)": q_alt(x) if x > 0 else 1.0, "(theta only)": q_theta(x) if x > 0 else 1.0}
        else:
            f = normal_es_factor()
            e = [s * f for s in inp["sigma"]]
            got = {"es_by_horizon": e, "es": math.sqrt(math.fsum(w * v * v for w, v in zip((1, 1, 2, 2, 6), e)))}
        for fld in exp[cid]["fields"]:
            ev = fld["value"]
            names = [fld["path"]] + ([k for k in got if k.startswith("(")] if fld["path"] == "ks_pvalue_asymptotic" else [])
            for name in names:
                g = got[name]
                if isinstance(ev, str):
                    ratio = 0.0 if g == ev else math.inf
                elif isinstance(ev, list):
                    ratio = max(abs(a - b) / max(1e-12 * abs(b), 1e-15) for a, b in zip(g, ev))
                else:
                    ratio = abs(g - ev) / max(1e-12 * abs(ev), 1e-15)
                if not name.startswith("("):
                    worst = max(worst, ratio)
                print(f"{cid}\t{name}\t{ev!r}\t{g!r}\t{ratio:.3g}")
    print(f"# worst error / tolerance over the compared fields: {worst:.3g} ({'all within' if worst <= 1 else 'OUTSIDE'})")
    return 0 if worst <= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
