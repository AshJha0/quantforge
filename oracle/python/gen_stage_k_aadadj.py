"""Stage K item K-8 (AAD part): sensitivities of the G-41 valuation adjustments, `xva.sens.aad` on
`xva.adjustments.value`.

Spec: specifications/06-risk/xva-aad-adjustments.md. Rulings: specifications/stage-k-rulings-xva-aad.md KR-262 to
KR-268 (PROPOSED). Writes datasets/golden/stage_k/aadadj_k.json.

Oracle (KR-265): every gradient entry is a bump-and-revalue in 50-digit arithmetic. The forward formulas of G-41
are evaluated in mpmath at 50 digits on the binary64 inputs (`mp.mpf(float)` is exact), with the overlap floor
replaced by the branch the binary64 forward pass takes (KR-264), and each input is bumped centrally by
`d = 1e-12 max(1, |x|)` and by `d / 2`, Richardson-combined: `(4 D(d/2) - D(d)) / 3`. Truncation is of order
`d^4` (about 1e-48 of the scale) and rounding about `1e-50 |f| / d` (about 1e-38), so the reference is exact far
below the 1e-8 acceptance. Independently, the hand-derived closed-form adjoint is evaluated in mpmath and must agree
with the bump to 1e-30 of the entry's scale before anything is written; that checks the derivation the four builds
port, not only the numbers.

    wsl: cd oracle/python && ~/qf-oracle-venv/bin/python -W ignore gen_stage_k_aadadj.py
"""
import json

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_k_aadadj.py"
SPEC = "specifications/06-risk/xva-aad-adjustments.md"
OP = "xva.sens.aad"
WRAPPED = "xva.adjustments.value"
ORACLE = "mpmath-50 Richardson central bump of the 50-digit forward (KR-265)"
ADJOINT = "mpmath-50 closed-form adjoint (hand-derived), agrees with the bump to 1e-30 of the scale"
HAND = "hand: expected code decided from the rulings (KR-267, KR-230 order), not blind re-derived"
LIMIT = {"absolute": 1e-12, "relative": 1e-10,
         "reason": "KR-265: a derivative exact to rounding; implies |AAD - bump| <= 1e-8 max(1, |bump|) (plan 14.8)"}
TAGS = ("stage_k", "xva", "aad", "sensitivities", "synthetic")
MAX_BUCKETS = 10_000

mp.mp.dps = 50


# ---------------------------------------------------------------- forward in 50 digits (G-41, bucket hazards KR-263)

def _m(x):
    return mp.mpf(x)


def params(inp):
    """The differentiable inputs as 50-digit numbers. Hazards are per bucket (all equal to the flat input)."""
    n = len(inp["times"])
    p = {
        "t": [_m(x) for x in inp["times"]],
        "hc": [_m(inp["counterparty"]["hazard_rate"])] * n,
        "hb": [_m(inp["own"]["hazard_rate"])] * n,
        "rc": _m(inp["counterparty"]["recovery"]),
        "rb": _m(inp["own"]["recovery"]),
        "df": [_m(x) for x in inp["discount_factors"]],
        "ee": [_m(x) for x in inp["ee"]],
        "ene": [_m(x) for x in inp["ene"]],
        "sb": _m(inp["funding"]["borrow_spread"]),
        "sl": _m(inp["funding"]["lend_spread"]),
        "overlap": bool(inp["funding"]["exclude_dva_overlap"]),
    }
    if "im" in inp:
        p["im"], p["sim"] = [_m(x) for x in inp["im"]], _m(inp["im_spread"])
    if "capital" in inp:
        p["cap"], p["hur"] = [_m(x) for x in inp["capital"]], _m(inp["hurdle_rate"])
    return p


def active_branch(inp):
    """KR-264: the overlap floor's branch, decided on the binary64 value the forward pass computes."""
    f = inp["funding"]
    if not f["exclude_dva_overlap"]:
        return None
    x = f["lend_spread"] - inp["own"]["hazard_rate"] * (1 - inp["own"]["recovery"])
    return x >= 0


def survival(h, dt):
    s, acc = [mp.mpf(1)], mp.mpf(0)
    for hj, d in zip(h, dt):
        acc += hj * d
        s.append(mp.exp(-acc))
    return s


def forward(p, branch):
    t = p["t"]
    n = len(t)
    dt = [t[0]] + [t[i] - t[i - 1] for i in range(1, n)]
    sc, sb = survival(p["hc"], dt), survival(p["hb"], dt)
    w = [p["df"][i] * sc[i] * sb[i] * dt[i] for i in range(n)]
    cva = (1 - p["rc"]) * mp.fsum(p["df"][i] * p["ee"][i] * (sc[i] - sc[i + 1]) * sb[i] for i in range(n))
    dva = (1 - p["rb"]) * mp.fsum(p["df"][i] * (-p["ene"][i]) * (sb[i] - sb[i + 1]) * sc[i] for i in range(n))
    if branch is None:
        sl = [p["sl"]] * n
    elif branch:
        sl = [p["sl"] - p["hb"][i] * (1 - p["rb"]) for i in range(n)]
    else:
        sl = [mp.mpf(0)] * n
    fca = p["sb"] * mp.fsum(w[i] * p["ee"][i] for i in range(n))
    fba = mp.fsum(sl[i] * w[i] * (-p["ene"][i]) for i in range(n))
    out = {"cva": cva, "dva": dva, "fca": fca, "fba": fba, "fva": fca - fba}
    if "im" in p:
        out["mva"] = p["sim"] * mp.fsum(w[i] * p["im"][i] for i in range(n))
    if "cap" in p:
        out["kva"] = p["hur"] * mp.fsum(w[i] * p["cap"][i] for i in range(n))
    return out


# ---------------------------------------------------------------- the differentiated inputs (KR-263)

def keys(p):
    """Gradient keys in canonical order (KR-263), each (key, scalar?)."""
    k = [("counterparty.hazard_rate", True), ("counterparty.hazard_buckets", False), ("counterparty.recovery", True),
         ("own.hazard_rate", True), ("own.hazard_buckets", False), ("own.recovery", True),
         ("discount_factors", False), ("ee", False), ("ene", False),
         ("funding.borrow_spread", True), ("funding.lend_spread", True)]
    if "im" in p:
        k += [("im", False), ("im_spread", True)]
    if "cap" in p:
        k += [("capital", False), ("hurdle_rate", True)]
    return k


FIELD = {"counterparty.recovery": "rc", "own.recovery": "rb", "discount_factors": "df", "ee": "ee", "ene": "ene",
         "funding.borrow_spread": "sb", "funding.lend_spread": "sl", "im": "im", "im_spread": "sim",
         "capital": "cap", "hurdle_rate": "hur", "counterparty.hazard_buckets": "hc", "own.hazard_buckets": "hb"}


def bumped(p, key, idx, eps):
    q = dict(p)
    if key in ("counterparty.hazard_rate", "own.hazard_rate"):
        f = "hc" if key.startswith("counterparty") else "hb"
        q[f] = [x + eps for x in p[f]]
    elif idx is None:
        q[FIELD[key]] = p[FIELD[key]] + eps
    else:
        arr = list(p[FIELD[key]])
        arr[idx] += eps
        q[FIELD[key]] = arr
    return q


def base_value(p, key, idx):
    if key == "counterparty.hazard_rate":
        return p["hc"][0]
    if key == "own.hazard_rate":
        return p["hb"][0]
    v = p[FIELD[key]]
    return v if idx is None else v[idx]


def bump_gradient(p, branch):
    """KR-265: Richardson central difference of the 50-digit forward for every (output, key, index)."""
    outs = list(forward(p, branch))
    grad = {o: {} for o in outs}
    for key, scalar in keys(p):
        idxs = [None] if scalar else range(len(p["t"]))
        cols = {o: [] for o in outs}
        for idx in idxs:
            d = mp.mpf("1e-12") * max(1, abs(base_value(p, key, idx)))

            def dd(h, key=key, idx=idx):
                up, dn = forward(bumped(p, key, idx, h), branch), forward(bumped(p, key, idx, -h), branch)
                return {o: (up[o] - dn[o]) / (2 * h) for o in outs}

            a, b = dd(d), dd(d / 2)
            for o in outs:
                cols[o].append((4 * b[o] - a[o]) / 3)
        for o in outs:
            grad[o][key] = cols[o][0] if scalar else cols[o]
    return grad


# ---------------------------------------------------------------- the closed-form adjoint (what the builds port)

def adjoint_gradient(p, branch):
    t = p["t"]
    n = len(t)
    dt = [t[0]] + [t[i] - t[i - 1] for i in range(1, n)]
    tt = [mp.mpf(0)] + list(t)
    sc, sb = survival(p["hc"], dt), survival(p["hb"], dt)
    w = [p["df"][i] * sc[i] * sb[i] * dt[i] for i in range(n)]
    lc, lb = 1 - p["rc"], 1 - p["rb"]
    if branch is None:
        sl = [p["sl"]] * n
    elif branch:
        sl = [p["sl"] - p["hb"][i] * lb for i in range(n)]
    else:
        sl = [mp.mpf(0)] * n

    def acc():
        z = [mp.mpf(0)] * n
        return {"gsc": [mp.mpf(0)] * (n + 1), "gsb": [mp.mpf(0)] * (n + 1), "df": list(z), "ee": list(z),
                "ene": list(z), "rc": mp.mpf(0), "rb": mp.mpf(0), "sb": mp.mpf(0), "sl": mp.mpf(0),
                "im": list(z), "sim": mp.mpf(0), "cap": list(z), "hur": mp.mpf(0), "hbd": list(z)}

    def through_w(a, i, gw):
        a["df"][i] += gw * sc[i] * sb[i] * dt[i]
        a["gsc"][i] += gw * p["df"][i] * sb[i] * dt[i]
        a["gsb"][i] += gw * p["df"][i] * sc[i] * dt[i]

    def cva():
        a = acc()
        for i in range(n):
            bb = sc[i] - sc[i + 1]
            a["rc"] -= p["df"][i] * p["ee"][i] * bb * sb[i]
            a["df"][i] += lc * p["ee"][i] * bb * sb[i]
            a["ee"][i] += lc * p["df"][i] * bb * sb[i]
            a["gsc"][i] += lc * p["df"][i] * p["ee"][i] * sb[i]
            a["gsc"][i + 1] -= lc * p["df"][i] * p["ee"][i] * sb[i]
            a["gsb"][i] += lc * p["df"][i] * p["ee"][i] * bb
        return a

    def dva():
        a = acc()
        for i in range(n):
            x, bb = -p["ene"][i], sb[i] - sb[i + 1]
            a["rb"] -= p["df"][i] * x * bb * sc[i]
            a["df"][i] += lb * x * bb * sc[i]
            a["ene"][i] -= lb * p["df"][i] * bb * sc[i]
            a["gsb"][i] += lb * p["df"][i] * x * sc[i]
            a["gsb"][i + 1] -= lb * p["df"][i] * x * sc[i]
            a["gsc"][i] += lb * p["df"][i] * x * bb
        return a

    def funding(coef, prof, sign, gprof, gcoef):
        a = acc()
        for i in range(n):
            x = sign * prof[i]
            a[gprof][i] += sign * coef[i] * w[i]
            g = w[i] * x
            if gcoef == "sl":
                if branch is None or branch:
                    a["sl"] += g
                if branch:
                    a["rb"] += g * p["hb"][i]
                    a["hbd"][i] -= g * lb
            else:
                a[gcoef] += g
            through_w(a, i, coef[i] * x)
        return a

    raw = {"cva": cva(), "dva": dva(), "fca": funding([p["sb"]] * n, p["ee"], 1, "ee", "sb"),
           "fba": funding(sl, p["ene"], -1, "ene", "sl")}
    if "im" in p:
        raw["mva"] = funding([p["sim"]] * n, p["im"], 1, "im", "sim")
    if "cap" in p:
        raw["kva"] = funding([p["hur"]] * n, p["cap"], 1, "cap", "hur")

    def finish(a):
        g = {}
        hc_b = [-dt[j] * mp.fsum(a["gsc"][k] * sc[k] for k in range(j + 1, n + 1)) for j in range(n)]
        hb_b = [-dt[j] * mp.fsum(a["gsb"][k] * sb[k] for k in range(j + 1, n + 1)) + a["hbd"][j] for j in range(n)]
        g["counterparty.hazard_rate"] = mp.fsum(-a["gsc"][k] * tt[k] * sc[k] for k in range(n + 1))
        g["counterparty.hazard_buckets"] = hc_b
        g["counterparty.recovery"] = a["rc"]
        g["own.hazard_rate"] = mp.fsum(-a["gsb"][k] * tt[k] * sb[k] for k in range(n + 1)) + mp.fsum(a["hbd"])
        g["own.hazard_buckets"] = hb_b
        g["own.recovery"] = a["rb"]
        for k, f in (("discount_factors", "df"), ("ee", "ee"), ("ene", "ene"), ("funding.borrow_spread", "sb"),
                     ("funding.lend_spread", "sl")):
            g[k] = a[f]
        if "im" in p:
            g["im"], g["im_spread"] = a["im"], a["sim"]
        if "cap" in p:
            g["capital"], g["hurdle_rate"] = a["cap"], a["hur"]
        return g

    grad = {o: finish(a) for o, a in raw.items()}
    grad["fva"] = {k: ([x - y for x, y in zip(v, grad["fba"][k])] if isinstance(v, list) else v - grad["fba"][k])
                   for k, v in grad["fca"].items()}
    return grad


def _flat(g):
    for o, row in g.items():
        for k, v in row.items():
            for i, x in enumerate(v if isinstance(v, list) else [v]):
                yield (o, k, i), x


def gradient(inp, wrt=None):
    p, branch = params(inp), active_branch(inp)
    bump, adj = bump_gradient(p, branch), adjoint_gradient(p, branch)
    a = dict(_flat(adj))
    for k, x in _flat(bump):
        scale = max(1, abs(x))
        assert abs(a[k] - x) <= mp.mpf("1e-30") * scale, (k, x, a[k])
    vals = forward(p, branch)
    out = {o: common.f(v) for o, v in vals.items()}
    names = [k for k, _ in keys(p)] if wrt is None else [k for k, _ in keys(p) if k in wrt]
    out["gradient"] = {o: {k: (common.f(row[k]) if not isinstance(row[k], list) else [common.f(x) for x in row[k]])
                           for k in names} for o, row in bump.items()}
    return out


# ---------------------------------------------------------------- cases

def g41():
    path = common.ROOT / "datasets" / "golden" / "stage_g" / "xvaadj_g.json"
    return {c["case_id"]: c for c in json.loads(path.read_text("utf-8"))["cases"]}


def req(inputs, wrt=None, operation=WRAPPED):
    r = {"operation": operation, "inputs": inputs}
    if wrt is not None:
        r["wrt"] = wrt
    return r


def with_(base, **kw):
    x = json.loads(json.dumps(base))
    for k, v in kw.items():
        if k in ("counterparty", "own", "funding"):
            x[k].update(v)
        else:
            x[k] = v
    return x


def build():
    s = Suite("aadadj_k", SPEC, G)
    g = g41()
    base = g["xvaadj_g-0001"]["inputs"]
    vb = (ORACLE, ADJOINT)

    def value(inp, desc, wrt=None, check_g=None):
        out = gradient(inp, wrt)
        if check_g:
            exp = g[check_g]["expected"]["outputs"]
            for k, v in exp.items():
                assert abs(out[k] - v) <= 1e-14 * max(1, abs(v)), (check_g, k, out[k], v)
        s.add(OP, req(inp, wrt), out, cls="aad_sensitivity", verified=vb, tags=TAGS, limit=LIMIT, description=desc)
        return out

    o1 = value(base, "xvaadj_g-0001 (K-8b design aadx_k-0001): full gradient of cva, dva, fca, fba, fva",
               check_g="xvaadj_g-0001")
    value(g["xvaadj_g-0002"]["inputs"], "xvaadj_g-0002 (K-8b design aadx_k-0002): overlap excluded, effective lending "
          "spread 0.002, 20 bp above the floor's kink", check_g="xvaadj_g-0002")
    both = with_(g["xvaadj_g-0003"]["inputs"], capital=[40.0, 42.0, 38.0, 30.0], hurdle_rate=0.1)
    value(both, "with im and capital: gradient of mva and kva as well")
    value(with_(base, ee=[0.0] * 4, ene=[0.0] * 4), "zero exposure: every adjustment 0; the profile entries keep "
          "their derivatives, hazard and spread entries are 0 (boundary)")
    value(with_(base, counterparty={"recovery": 0.0}, own={"recovery": 0.0}), "recovery 0 for both names (boundary)")
    value(with_(base, counterparty={"recovery": 0.999999}, own={"recovery": 0.99}),
          "recovery near 1: counterparty 0.999999, own 0.99 (boundary)")
    value({"times": [1.0], "discount_factors": [0.97], "ee": [100.0], "ene": [-40.0],
           "counterparty": {"hazard_rate": 0.03, "recovery": 0.4}, "own": {"hazard_rate": 0.01, "recovery": 0.4},
           "funding": {"borrow_spread": 0.01, "lend_spread": 0.004, "exclude_dva_overlap": True}},
          "single bucket, overlap excluded (lending spread 0.004 - 0.006 < 0: the floor holds, branch 0)")
    value(with_(base, counterparty={"hazard_rate": 0.0}, own={"hazard_rate": 0.0}),
          "hazard 0 for both names: cva = dva = 0, hazard derivatives are the analytic ones at 0 (boundary)")
    value(with_(base, own={"hazard_rate": 0.01, "recovery": 0.5}, funding={"lend_spread": 0.005,
                                                                           "exclude_dva_overlap": True}),
          "on the overlap kink: lend_spread - h_b (1 - R_b) = 0.005 - 0.01 x 0.5 = 0 exactly in binary64; the "
          "linear branch is taken (KR-264)")
    value(with_(base, own={"hazard_rate": 0.02}, funding={"lend_spread": 0.008, "exclude_dva_overlap": True}),
          "below the kink: lend_spread 0.008 < h_b (1 - R_b) = 0.012, effective spread 0, fba 0 and its lend_spread, "
          "own hazard and own recovery entries 0")
    value(base, "wrt subset: counterparty.hazard_rate and ee only", wrt=["ee", "counterparty.hazard_rate"])
    six = {"times": [0.25, 0.5, 1.0, 2.0, 3.5, 5.0], "discount_factors": [0.995, 0.99, 0.975, 0.95, 0.91, 0.87],
           "ee": [0.0, 35.5, 120.25, 0.0, 410.0, 95.0], "ene": [-12.0, 0.0, -80.5, -150.0, 0.0, -30.25],
           "counterparty": {"hazard_rate": 0.5, "recovery": 0.25}, "own": {"hazard_rate": 0.003, "recovery": 0.6},
           "funding": {"borrow_spread": 0.0125, "lend_spread": 0.0035, "exclude_dva_overlap": True},
           "im": [50.0, 55.0, 60.0, 40.0, 20.0, 5.0], "im_spread": 0.004}
    value(six, "six uneven buckets, zeros in ee and ene, counterparty hazard 0.5, overlap on (0.0035 - 0.0012 > 0)")
    n = 40
    times = [0.25 * (i + 1) for i in range(n)]
    long = {"times": times, "discount_factors": [float(mp.exp(-0.035 * t)) for t in times],
            "ee": [float(1e6 * mp.sqrt(t) * (10 - t) / 10) for t in times],
            "ene": [float(-4e5 * mp.sqrt(t) * (10 - t) / 10) for t in times],
            "counterparty": {"hazard_rate": 0.015, "recovery": 0.4}, "own": {"hazard_rate": 0.008, "recovery": 0.4},
            "funding": {"borrow_spread": 0.009, "lend_spread": 0.006, "exclude_dva_overlap": False}}
    value(long, "40 quarterly buckets to 10 years, a swap-like profile on 1,000,000 notional")

    def err(inp, code, desc, two=None):
        tags = ("stage_k", "xva", "aad", "error") + (("e2", "two-errors") if two else ())
        if code == "E_DOMAIN" and "NaN" in json.dumps(inp) and not two:
            tags = ("stage_k", "e1", "non-finite-input", "xva", "aad", "error")
        s.add(OP, inp, error=code, verified=("hand", HAND), tags=tags, description=desc)

    err(req(base, operation="xva.cva.magic"), "E_SCHEMA", "operation not supported (K-8b design aadx_ke-0003, one "
        "error): an unlisted operation is E_SCHEMA (KR-262)")
    err(req(base, wrt=5), "E_SCHEMA", "wrt not a list")
    err(req(base, wrt=["ee", 3]), "E_SCHEMA", "wrt holds a non-string")
    err(req(base, operation="xva.cva.magic") | {"wrt": 5}, "E_SCHEMA",
        "two errors: [schema] unlisted operation and [schema] wrt 5 (K-8b design aadx_ke-0003)", two=True)
    err(req(base, wrt=["counterparty.colour"]), "E_INPUT", "wrt names no differentiated input (K-8b design "
        "aadx_ke-0001)")
    err(req(base, wrt=["im"]), "E_INPUT", "wrt names im, which the request does not carry")
    err(req(base, wrt=[]), "E_INPUT", "wrt empty")
    err(req(base, wrt=["ee", "ee"]), "E_INPUT", "wrt names ee twice")
    err(req(with_(base, counterparty={"recovery": 1.0})), "E_DOMAIN",
        "wrapped operation's own error: counterparty recovery 1 (K-8b design aadx_ke-0002)")
    no_ee = json.loads(json.dumps(base))
    del no_ee["ee"]
    err(req(no_ee), "E_SCHEMA", "wrapped inputs without ee")
    err({"operation": WRAPPED}, "E_SCHEMA", "no inputs object")
    err(req(with_(base, ee=[120.0, "NaN", 130.0, 80.0])), "E_DOMAIN", "E1 (F-2): ee[1] NaN")
    err(req(with_(base, discount_factors=[0.985, "Infinity", 0.955, 0.94])), "E_DOMAIN",
        "E1 (F-2): discount_factors[1] Infinity")
    err(req(with_(base, ene=[0.0, -1.0, 2.0, -3.0])), "E_DOMAIN", "ene above 0")
    err(req(with_(base, times=[0.5, 1.0, 1.0, 2.0])), "E_INPUT", "times not increasing")
    # two errors at once, KR-230 order: schema, limit, finite, structural, domain
    err(req(with_(base, counterparty={"recovery": 1.0}), operation="xva.cva.magic"), "E_SCHEMA",
        "two errors: [schema] unlisted operation and [domain] counterparty recovery 1", two=True)
    err(req(with_(base, ee=[120.0, "NaN", 130.0, 80.0], discount_factors=[0.985, 0.97, 0.955])), "E_DOMAIN",
        "two errors: [finite] ee[1] NaN and [structural] three discount factors for four times", two=True)
    err(req(with_(base, own={"hazard_rate": "NaN"}), wrt=["counterparty.colour"]), "E_DOMAIN",
        "two errors: [finite] own hazard NaN and [structural] wrt names no input", two=True)
    err(req(with_(base, counterparty={"recovery": 1.0}), wrt=["counterparty.colour"]), "E_INPUT",
        "two errors: [structural] wrt names no input and [domain] counterparty recovery 1", two=True)
    err(req(with_(base, times=[0.5, 0.4, 1.5, 2.0], ee=[120.0, -1.0, 130.0, 80.0])), "E_INPUT",
        "two errors: [structural] times not increasing and [domain] ee below 0", two=True)
    err(req(with_(base, ee=["NaN", 150.0, 130.0, 80.0], counterparty={"hazard_rate": -0.01})), "E_DOMAIN",
        "two errors: [finite] ee[0] NaN and [domain] counterparty hazard below 0 (both E_DOMAIN; the finite rule "
        "names ee)", two=True)
    big = [float(i + 1) for i in range(MAX_BUCKETS + 1)]
    err(req(with_(base, times=big)), "E_LIMIT", "two errors: [limit] 10,001 times (KR-266) and [structural] four "
        "discount factors for 10,001 times", two=True)
    err(req(with_(base, times=big, own={"hazard_rate": "NaN"})), "E_LIMIT",
        "two errors: [limit] 10,001 times and [finite] own hazard NaN", two=True)
    return s, o1


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    s, o1 = build()
    s.write()
    common.GOLDEN = keep
    gr = o1["gradient"]["cva"]
    note(f"aadadj_k-0001 cva {o1['cva']!r}; d cva / d h_c {gr['counterparty.hazard_rate']!r}; "
         f"d cva / d R_c {gr['counterparty.recovery']!r}; d cva / d h_b {gr['own.hazard_rate']!r}; "
         f"d fca / d s_b {o1['gradient']['fca']['funding.borrow_spread']!r}; d cva / d ee[1] {gr['ee'][1]!r}")


if __name__ == "__main__":
    main()
