"""Stage K wave 1 (PROPOSED specs): bitemporal store, incremental curve update, recalibration triggers, intraday
risk bounds and the Richardson guard.

Specs: specifications/01-core/bitemporal-store.md, 02-curves/incremental-update.md,
03-calibration/recalibration-triggers.md, 06-risk/intraday-risk-bounds.md, 06-risk/bermudan-ladder-k8.md
(`num.richardson.check`). Rulings: specifications/stage-k-rulings-w1.md KR-1 to KR-14 (PROPOSED).

Every case of the spec golden tables is written here in table order, so case ids match the tables. The E1 suite
(e1_k) is added by this lane: one non-finite input per operation (ruling F-2), hand-decided, not blind.

Oracle: mpmath at 50 digits on the binary64 inputs (`mp.mpf(float)` is exact). The generator asserts each table's
printed figures (to the digits printed) before writing, so a spec/oracle mismatch stops the run. idr_k-0001..0005
`bound` and `estimate_pnl` are filled here to full binary64 precision (the spec printed the bounds to 6 decimals and
left idr_k-0005 oracle-pending); `exact` revaluations are checked against the bound for every value case.

Evidence, recorded per case in `verified_by` from program/STAGE_K_BLIND_W1.md (DR-H2 blind lane, 38/38 MATCH):
- bt_k-0004 and bt_k-0006: blind on `status` only; `row` gap-decided by KR-14.
- trig_k-0004: blind on sigma, threshold and false_alarm_rate; `fire` gap-decided by KR-13.
- idr_k-0001..0004: `bound` blind-checked only to 6 decimals (5e-7 absolute), the precision the packet carried;
  `estimate_pnl` at 1e-9 relative.
- idr_k-0005: not blind (oracle-pending when the packet was built); mpmath only.
- idr_k-0006 and rich_k-0007: gap-decided by KR-12, not blind.
Outside check (KR-11): trig_k false_alarm_rate against SciPy `2*norm.sf(k)`.

    wsl: cd oracle/python && ~/qf-oracle-venv/bin/python -W ignore gen_stage_k_w1.py
"""
import json
import math

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_k_w1.py"
FOLDER = "stage_k"
BT = "specifications/01-core/bitemporal-store.md"
INC = "specifications/02-curves/incremental-update.md"
TRIG = "specifications/03-calibration/recalibration-triggers.md"
IDR = "specifications/06-risk/intraday-risk-bounds.md"
RICH = "specifications/06-risk/bermudan-ladder-k8.md"
LABEL = "latency-aware analytics on simulated data"  # KR-10

BLIND = "blind re-derivation DR-H2 2026-11-18 (program/STAGE_K_BLIND_W1.md): MATCH"
BLIND_ROW = BLIND + " on status only; row decided by gap ruling KR-14, not blind"
BLIND_FIRE = BLIND + " on sigma, threshold, false_alarm_rate; fire decided by gap ruling KR-13, not blind"
K5A = ("blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_K5A.md, packet manifest 1a9c4cbc): MATCH on "
       "estimate_pnl and bound at 1e-9 relative on full-precision values (largest relative difference 2.08e-16); "
       "label rules-stated (KR-10), no credit")
BLIND_IDR_W1 = (BLIND + "; bound blind-checked only to 6 decimals (5e-7 absolute, the precision the packet carried), "
             "estimate_pnl at 1e-9 relative")
NOT_BLIND_5 = "not blind: oracle-pending when the wave-1 blind packet was built; mpmath only"  # history (wave 1)
BLIND_IDR = K5A  # the K-5a packet (2026-11-19) supersedes the wave-1 6-decimal check for idr_k-0001..0004
K_FAR = ("added 2026-11-19 (branch k-w1-fu) so that every build keeps the stated 2 (1 - Phi(k)) in the far tail: "
         "not blind")
GAP_KR12 = "gap-decided by ruling KR-12 (E_DOMAIN code): not blind"
ADDED = "added by the oracle lane 2026-11-18 (E1, ruling F-2): hand, not blind re-derived"
ORACLE = "mpmath 50 digits"


class DomainError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def check(cond, code):
    if not cond:
        raise DomainError(code)


def run(fn, inp):
    try:
        return fn(inp), None
    except DomainError as e:
        return None, e.code


# ---------------------------------------------------------------- bitemporal store (KR-2, KR-14)

def instant(s):
    """Seconds since the epoch of an RFC 3339 instant with `Z` or a numeric offset, whole seconds."""
    import datetime as dt
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def zulu(sec):
    import datetime as dt
    return dt.datetime.fromtimestamp(sec, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bt_query(inp):
    recs = inp["records"]
    for r in recs:
        check(isinstance(r["sequence"], int) and r["sequence"] >= 1 and r["series_id"], "E_SCHEMA")
    for a, b in zip(recs, recs[1:]):
        check(b["sequence"] > a["sequence"], "E_INPUT")
    for a, b in zip(recs, recs[1:]):
        check(instant(b["knowledge_time"]) >= instant(a["knowledge_time"]), "E_INPUT")
    for r in recs:
        check(r["valid_to"] is None or instant(r["valid_to"]) > instant(r["valid_from"]), "E_INPUT")
    k, v = instant(inp["knowledge_as_of"]), instant(inp["valid_at"])
    cand = [r for r in recs if r["series_id"] == inp["series_id"] and instant(r["knowledge_time"]) <= k
            and instant(r["valid_from"]) <= v and (r["valid_to"] is None or v < instant(r["valid_to"]))]
    if not cand:
        return {"status": "NONE", "row": None}
    w = max(cand, key=lambda r: r["sequence"])
    if w.get("deleted", False):
        return {"status": "WITHDRAWN", "row": None}
    row = {k_: w[k_] for k_ in ("sequence", "valid_from", "valid_to", "knowledge_time", "value")}
    for k_ in ("valid_from", "valid_to", "knowledge_time"):  # KR-235(b): instants in Z form
        if row[k_] is not None:
            row[k_] = zulu(instant(row[k_]))
    return {"status": "FOUND", "row": row}


def z(d):
    return d if "T" in d else d + "T00:00:00Z"


def rec(seq, vf, vt, kt, value, deleted=False):
    r = {"sequence": seq, "series_id": "A", "valid_from": z(vf), "valid_to": None if vt is None else z(vt),
         "knowledge_time": z(kt), "value": value}
    if deleted:
        r["deleted"] = True
    return r


LOG = [rec(1, "2026-01-01", None, "2026-01-02", 100), rec(2, "2026-03-01", None, "2026-03-02", 110),
       rec(3, "2026-02-01", "2026-03-01", "2026-04-01", 105), rec(4, "2026-03-01", None, "2026-04-02", None, True)]


def bt_inp(k, v, log=None):
    return {"records": log or LOG, "series_id": "A", "knowledge_as_of": z(k), "valid_at": z(v)}


def _with(i, **kw):
    log = json.loads(json.dumps(LOG))
    log[i].update({k: z(v) for k, v in kw.items()})
    return log


BT_CASES = [  # (inputs, expected status, expected row.sequence, expected row.value, description, verified)
    (bt_inp("2026-03-15", "2026-02-15"), "FOUND", 1, 100, "seq 3 not yet known", BLIND),
    (bt_inp("2026-04-01", "2026-02-15"), "FOUND", 3, 105, "K inclusive; correction known", BLIND),
    (bt_inp("2026-03-15", "2026-03-10"), "FOUND", 2, 110, "seq 2 wins", BLIND),
    (bt_inp("2026-04-05", "2026-03-10"), "WITHDRAWN", None, None, "seq 4 wins and masks seq 2 and seq 1 (KR-2)",
     BLIND_ROW),
    (bt_inp("2026-04-05", "2026-01-15"), "FOUND", 1, 100, "only seq 1 covers January", BLIND),
    (bt_inp("2026-01-01T12:00:00Z", "2026-01-15"), "NONE", None, None, "nothing known yet", BLIND_ROW),
    (bt_inp("2026-04-01", "2026-03-01"), "FOUND", 2, 110, "seq 3 ends at 03-01 exclusive; seq 4 not yet known",
     BLIND),
    (bt_inp("2026-04-01", "2026-02-28T23:59:59Z"), "FOUND", 3, 105, "last second inside seq 3", BLIND),
    (bt_inp("2026-04-01", "2026-02-15", _with(2, valid_to="2026-02-01")), "E_INPUT", None, None,
     "seq 3 valid_to equal to its valid_from", BLIND),
    (bt_inp("2026-04-01", "2026-02-15", _with(2, knowledge_time="2026-03-01")), "E_INPUT", None, None,
     "seq 3 knowledge_time earlier than seq 2's", BLIND),
]
BT_AUDIT = [  # KR-235(b) (KA-A12)
    (bt_inp("2026-04-05", "2026-01-15", LOG + [dict(rec(5, "2026-01-01", None, "2026-04-03", 999), series_id="B")]),
     "FOUND", 1, 100, "a later record of series B covers V and is known by K: series A's answer is unchanged (the "
     "series condition of C)"),
    (bt_inp("2026-04-05", "2026-01-15", [dict(rec(1, "2026-01-01T01:00:00+01:00", None, "2026-01-02T09:30:00+05:30", 7))]),
     "FOUND", 1, 7, "instants with numeric offsets are output in Z form"),
]


def kr4_property(n_logs=2000, seed=20261118):
    """KR-4 on seeded generated logs: appending a record known after K leaves every (K, V) answer unchanged."""
    import random
    rnd = random.Random(seed)
    day = 86400
    base = instant("2026-01-01T00:00:00Z")

    def ts(d):
        import datetime as dt
        return dt.datetime.fromtimestamp(base + d * day, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for _ in range(n_logs):
        log, kt = [], 0
        for s in range(1, rnd.randint(1, 8) + 1):
            kt += rnd.randint(0, 3)
            vf = rnd.randint(0, 20)
            vt = None if rnd.random() < 0.3 else vf + rnd.randint(1, 10)
            r = {"sequence": s, "series_id": rnd.choice("AB"), "valid_from": ts(vf),
                 "valid_to": None if vt is None else ts(vt), "knowledge_time": ts(kt), "value": rnd.randint(0, 99)}
            if rnd.random() < 0.15:
                r["deleted"] = True
            log.append(r)
        k = rnd.randint(0, kt + 2)
        extra = {"sequence": len(log) + 1, "series_id": rnd.choice("AB"), "valid_from": ts(rnd.randint(0, 20)),
                 "valid_to": None, "knowledge_time": ts(max(kt, k + 1) + rnd.randint(0, 2)), "value": -1}
        for vd in range(0, 25):
            q = {"series_id": "A", "knowledge_as_of": ts(k), "valid_at": ts(vd)}
            assert bt_query(dict(q, records=log)) == bt_query(dict(q, records=log + [extra])), (log, extra, q)


# ---------------------------------------------------------------- incremental update (KR-5)

def bootstrap_mp(quotes):
    out = []
    for s in quotes:
        s = mp.mpf(s)
        out.append((1 - s * mp.fsum(out)) / (1 + s))
    return out


def bootstrap_f64(quotes):
    """The binary64 recursion in the spec's order: running sum left to right, then (1 - S s) / (1 + S)."""
    out, acc = [], 0.0
    for s in quotes:
        p = (1.0 - s * acc) / (1.0 + s)
        out.append(p)
        acc += p
    return out


def par_annual(inp):
    q = inp["quotes"]
    check(len(q) <= 200, "E_LIMIT")  # KR-230 order
    check(len(q) >= 1, "E_INPUT")
    check(all(s > -1 for s in q), "E_DOMAIN")
    return {"discount_factors": [common.f(p) for p in bootstrap_mp(q)]}


def inc_update(inp):
    pq, pd, nq = inp["previous_quotes"], inp["previous_discount_factors"], inp["new_quotes"]
    check(max(len(pq), len(pd), len(nq)) <= 200, "E_LIMIT")  # KR-230 order
    check(len(pq) >= 1 and len(pq) == len(pd) == len(nq), "E_INPUT")
    check(all(s > -1 for s in pq + nq), "E_DOMAIN")
    check(bootstrap_f64(pq) == pd, "E_INPUT")  # a stale cache must not be patched
    j = next((i for i, (a, b) in enumerate(zip(pq, nq)) if a != b), None)
    exact = bootstrap_mp(nq)
    return {"discount_factors": [common.f(p) for p in exact], "first_changed_index": j,
            "recomputed": 0 if j is None else len(nq) - j}


def fused_differs(count=2, seed=20261119):
    """KA-A8: seeded 10-quote vectors (uniform in [0, 0.06]) whose bootstrap differs in at least one bit when
    1 - S * acc is formed with a fused multiply-add. A build that contracts would call the cache stale."""
    import random
    rnd, out = random.Random(seed), []
    while len(out) < count:
        q = [round(rnd.uniform(0.0, 0.06), 6) for _ in range(10)]
        acc, fused = 0.0, []
        for x in q:
            with mp.workprec(300):  # 1 - x acc exactly, rounded once: what a fused multiply-add gives
                fused_num = float(mp.mpf(1) - mp.mpf(x) * mp.mpf(acc))
            p = fused_num / (1.0 + x)
            fused.append(p)
            acc += p
        if fused != bootstrap_f64(q):
            n = sum(a != b for a, b in zip(fused, bootstrap_f64(q)))
            out.append((q, f"10 seeded quotes whose fused-multiply-add bootstrap differs in {n} pillar(s): the cache "
                           "must be the unfused bootstrap, bit for bit (cli-contract.md numeric rules)"))
    return out


BASE = [0.02, 0.025, 0.03]
BASE_DF = bootstrap_f64(BASE)
INC_CASES = [
    ("curve.bootstrap.par_annual", {"quotes": BASE}, "base quotes; P_k = (1 - S_k sum P_i) / (1 + S_k)"),
    ("curve.incremental.update", {"previous_quotes": BASE, "previous_discount_factors": BASE_DF,
                                  "new_quotes": [0.02, 0.026, 0.03]}, "second quote ticks: pillar 0 copied"),
    ("curve.incremental.update", {"previous_quotes": BASE, "previous_discount_factors": BASE_DF,
                                  "new_quotes": [0.02, 0.025, 0.031]}, "last quote ticks: first two copied"),
    ("curve.incremental.update", {"previous_quotes": BASE, "previous_discount_factors": BASE_DF,
                                  "new_quotes": BASE}, "nothing changed: all copied"),
    ("curve.incremental.update", {"previous_quotes": BASE, "previous_discount_factors": BASE_DF,
                                  "new_quotes": [0.02, 0.025]}, "lengths differ"),
    ("curve.incremental.update", {"previous_quotes": BASE,
                                  "previous_discount_factors": BASE_DF[:2] + [math.nextafter(BASE_DF[2], math.inf)],
                                  "new_quotes": [0.02, 0.026, 0.03]},
     "stale cache: last factor one ulp above the bootstrap"),
]


# ---------------------------------------------------------------- recalibration triggers (KR-6, KR-13)

NOISE_FLOOR = 2.0 ** -26  # KR-233


def t_tail_mp(nu, k):
    """P(|T_nu| > k) at 50 digits: I_x(nu/2, 1/2), x = nu / (nu + k^2) (KR-232)."""
    nu_, k_ = mp.mpf(nu), mp.mpf(k)
    return mp.betainc(nu_ / 2, mp.mpf(1) / 2, 0, nu_ / (nu_ + k_ * k_), regularized=True)


def sigma_f64(c):
    """KR-233 arithmetic: exactly rounded sums, then the threshold test is decided on this binary64 value."""
    mean = math.fsum(c) / len(c)
    return math.sqrt(math.fsum((x - mean) * (x - mean) for x in c) / (len(c) - 1))


def trigger(inp):
    """KR-230 order (size limit, finite rule, structural E_INPUT, E_DOMAIN); KR-232 rate; KR-233 noise floor."""
    c, k, d = inp["changes"], inp["k"], inp["days_since"]
    check(len(c) <= 100_000, "E_LIMIT")
    check(all(isinstance(x, float) and math.isfinite(x) for x in c + [k, d, inp["x_ref"], inp["x_now"]]), "E_DOMAIN")
    check(len(c) >= 2, "E_INPUT")
    check(k > 0 and d >= 1, "E_DOMAIN")
    check(sigma_f64(c) > NOISE_FLOOR * max(abs(x) for x in c), "E_DOMAIN")
    cs = [mp.mpf(x) for x in c]
    mean = mp.fsum(cs) / len(cs)
    sigma = mp.sqrt(mp.fsum((x - mean) ** 2 for x in cs) / (len(cs) - 1))
    thr = mp.mpf(k) * sigma * mp.sqrt(mp.mpf(d))
    move = abs(mp.mpf(inp["x_now"]) - mp.mpf(inp["x_ref"]))
    return {"fire": bool(move > thr), "sigma": common.f(sigma), "threshold": common.f(thr),
            "false_alarm_rate": common.f(t_tail_mp(len(c) - 1, k)),
            "nominal_rate": common.f(mp.erfc(mp.mpf(k) / mp.sqrt(2)))}


C1 = [1.0, -1.0, 1.0, -1.0]
C2 = [0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0]
TRIG_CASES = [  # inputs, expected (sigma, threshold, fire, nominal rate) or error code, description, verified
    ((C1, 100.0, 105.0, 1.0, 3.0), (1.1547005383792515, 3.4641016151377546, True, 0.002699796063260186),
     "planted move", BLIND),
    ((C1, 100.0, 102.0, 1.0, 3.0), (1.1547005383792515, 3.4641016151377546, False, 0.002699796063260186),
     "noise", BLIND),
    ((C1, 100.0, 105.0, 4.0, 3.0), (1.1547005383792515, 6.928203230275509, False, 0.002699796063260186),
     "four days since calibration double the threshold", BLIND),
    ((C2, 0.0, 2.5, 1.0, 2.5), (1.0, 2.5, False, 0.012419330651552265),
     "move equal to the threshold does not fire (KR-13)", BLIND_FIRE),
    ((C2, 0.0, -2.5000001, 1.0, 2.5), (1.0, 2.5, True, 0.012419330651552265), "just past the threshold", BLIND),
    (([1.0], 100.0, 105.0, 1.0, 3.0), "E_INPUT", "fewer than two changes", BLIND),
    ((C1, 100.0, 105.0, 1.0, 0.0), "E_DOMAIN", "k <= 0", BLIND),
    (([1.0, 1.0, 1.0], 100.0, 105.0, 1.0, 3.0), "E_DOMAIN", "sigma = 0: no noise scale", BLIND),
    ((C1, 100.0, 105.0, 1.0, 30.0), (1.1547005383792515, 34.64101615137755, False, 9.813427854296374e-198),
     "far tail k = 30: 2 (1 - Phi(k)) to 1e-14 in nominal_rate; a bare erfc(k / sqrt 2) is 1.2e-13 off", K_FAR),
]
# KR-232 and KR-233 cases (audit A response, 2026-11-19): window sizes from 2 to 250 for the Student-t rate, and
# the noise floor. Expected sigma and threshold from mpmath; fire from the exact move; rates from mpmath.
W250 = [((-1.0) ** i) * (1.0 + (i % 7) / 8.0) for i in range(250)]
TRIG_AUDIT = [
    (([1.0, -1.0], 0.0, 10.0, 1.0, 3.0), "n = 2 (1 degree of freedom): rate 2 atan(1/3) / pi"),
    (([0.5, -0.25, 1.0], 0.0, 1.0, 1.0, 3.0), "n = 3 (2 degrees of freedom): rate 1 - 3 / sqrt(11)"),
    (([0.5, -0.25, 1.0, -1.0, 0.75], 0.0, 4.0, 2.0, 2.0), "n = 5, k = 2, d = 2"),
    (([((-1.0) ** i) * (0.5 + i / 16.0) for i in range(30)], 0.0, 1.0, 1.0, 3.0), "n = 30"),
    ((W250, 0.0, 5.0, 1.0, 3.0), "n = 250: the window of the spec's simulation"),
    ((C1, 0.0, 1.0, 1.0, 0.5), "small k: the complement branch (rate above 1/8)"),
    ((C2, 0.0, 1.0, 1.0, 1e3), "large k = 1e3 with n = 8: remainder branch, k above sqrt(nu)"),
]
TRIG_FLOOR = [  # KR-233
    (([0.1, 0.1, 0.1], 0.0, 0.0, 1.0, 3.0), "E_DOMAIN", "constant window [0.1] x 3: binary64 sigma 1.7e-17, below 2^-26 max|c| (KA-A5)"),
    (([0.2] * 6, 0.0, 0.0, 1.0, 3.0), "E_DOMAIN", "constant window [0.2] x 6 (KA-A5)"),
    (([0.0, 0.0], 0.0, 0.0, 1.0, 3.0), "E_DOMAIN", "zero window: sigma 0 and max|c| 0"),
    (([1.0, 1.0 + 2.0e-8], 0.0, 0.0, 1.0, 3.0), "E_DOMAIN", "sigma 1.41e-8 just below 2^-26 x 1.00000002 = 1.49e-8"),
    (([1.0, 1.0 + 2.2e-8], 0.0, 1e-7, 1.0, 3.0), None, "sigma 1.56e-8 just above 2^-26 x max|c|: a usable noise scale"),
]


def trig_inp(t):
    c, xr, xn, d, k = t
    return {"changes": c, "x_ref": xr, "x_now": xn, "days_since": d, "k": k}


# ---------------------------------------------------------------- intraday bounds (KR-7, KR-10, KR-12)

RHO = mp.mpf(2) ** -49  # KR-234: 16 u


def idr_parts(pos, h):
    """v, delta-gamma estimate, exact revaluation, Lagrange bound and the KR-234 rounding allowance of a position."""
    n, t, y = (mp.mpf(pos[k]) for k in ("notional", "maturity", "yield"))
    h = mp.mpf(h)
    v = n * mp.exp(-y * t)
    est = v * (-t * h + t * t * h * h / 2)
    exact = n * mp.exp(-(y + h) * t) - v
    bound = abs(h) ** 3 * t ** 3 * abs(n) * mp.exp(-t * min(y, y + h)) / 6
    g = abs(mp.expm1(-h * t))
    rho = RHO * (1 + t * abs(y) + t * abs(h)) * (abs(v) * (t * abs(h) + t * t * h * h + g) + bound)
    return v, est, exact, bound, rho


def idr(inp):
    ps, h = inp["positions"], inp["shift"]
    check(len(ps) <= 100_000, "E_LIMIT")
    check(isinstance(h, float) and all(isinstance(p[k], float) for p in ps for k in p), "E_DOMAIN")
    check(len(ps) >= 1, "E_INPUT")
    check(all(p["maturity"] > 0 for p in ps), "E_DOMAIN")
    parts = [idr_parts(p, h) for p in ps]
    return {"estimate_pnl": common.f(mp.fsum(p[1] for p in parts)),
            "bound": common.f(mp.fsum(p[3] + p[4] for p in parts)), "label": LABEL}


POS = {"notional": 1_000_000.0, "maturity": 5.0, "yield": 0.04}
IDR_CASES = [
    ({"positions": [POS], "shift": 0.01}, "delta-gamma with Lagrange bound, h = +1%", BLIND_IDR,
     (-39913.124212551616, 17.056891, 778800.783071404868, 778817.628865430243, 0.988)),
    ({"positions": [POS], "shift": -0.01}, "h = -1%: M3 at the lower yield", BLIND_IDR,
     (41959.951095246570, 17.931416, 860707.976425057807, 860690.704173228429, 0.963)),
    ({"positions": [POS], "shift": 0.0025}, "h = +25 bp: bound tight", BLIND_IDR,
     (-10170.171073390556, 0.266514, 808560.316321452466, 808560.582004591303, 0.997)),
    ({"positions": [POS], "shift": 0.05}, "h = +5%: large move, bound still holds", BLIND_IDR,
     (-179097.352235808532, 2132.111336, 637628.151621773293, 639633.400842173327, 0.940)),
    ({"positions": [POS, {"notional": -500_000.0, "maturity": 2.0, "yield": 0.03}], "shift": 0.01},
     "two positions, short 2y leg; bound = sum of position bounds (no netting of remainders)", K5A, None),
    ({"positions": [dict(POS, maturity=0.0)], "shift": 0.01}, "maturity <= 0 (KR-12)", GAP_KR12, None),
    ({"positions": [], "shift": 0.01}, "no positions", BLIND, None),
]
HEDGED = [POS, {"notional": -1_000_000.0 * (1 + 1e-12), "maturity": 5.0, "yield": 0.04}]
IDR_AUDIT = [  # KR-234 (KA-A6, KA-A7)
    ({"positions": [POS], "shift": 1e-9}, "h = 1e-9: the rounding allowance dominates (old bound 1.7e-20 against an error "
     "of 3.7e-19)"),
    ({"positions": [POS], "shift": -1e-12}, "h = -1e-12"),
    ({"positions": [POS], "shift": 1e-30}, "h = 1e-30, the smallest nonzero move of the domain D"),
    ({"positions": [POS], "shift": 0.0}, "h = 0: estimate and bound are 0"),
    ({"positions": HEDGED, "shift": 0.01}, "hedged book, N and -N(1 + 1e-12): the estimate cancels to 4e-8 (KA-A7)"),
    ({"positions": [POS], "shift": 0.4000000001}, "T h near 2, where the delta and gamma terms cancel (KA-A7)"),
    ({"positions": [{"notional": 1e15, "maturity": 1e-6, "yield": 1.0}, {"notional": -1e-6, "maturity": 100.0, "yield": -1.0}],
      "shift": -1.0}, "domain corners: T 1e-6 and 100, y 1 and -1, N 1e15 and -1e-6, h -1"),
]


# ---------------------------------------------------------------- Richardson guard (KR-9, KR-12)

def richardson(inp):
    vals, r, p = inp["values"], inp["ratio"], inp["assumed_order"]
    check(len(vals) == 3, "E_INPUT")
    check(r > 1 and p > 0, "E_DOMAIN")
    f1, f2, f3 = (mp.mpf(v) for v in vals)
    d1, d2 = f1 - f2, f2 - f3
    if d1 == 0 or d2 == 0 or (d1 > 0) != (d2 > 0):
        return {"status": "NON_MONOTONE", "observed_order": None, "extrapolated": None}
    obs = mp.log(d1 / d2) / mp.log(mp.mpf(r))
    if abs(obs - mp.mpf(p)) > mp.mpf("0.5"):
        return {"status": "ORDER_MISMATCH", "observed_order": common.f(obs), "extrapolated": None}
    rp = mp.mpf(r) ** mp.mpf(p)
    return {"status": "OK", "observed_order": common.f(obs), "extrapolated": common.f((rp * f3 - f2) / (rp - 1))}


RICH_CASES = [
    ([10.5, 10.125, 10.03125], 2.0, 2.0, ("OK", 2.0, 10.0), "second-order sequence; exact", BLIND),
    ([11.0, 10.5, 10.25], 2.0, 2.0, ("ORDER_MISMATCH", 1.0, None), "first-order data, second order assumed", BLIND),
    ([11.0, 10.5, 10.25], 2.0, 1.0, ("OK", 1.0, 10.0), "first-order data, first order assumed", BLIND),
    ([98464.0, 93700.0, 96435.0], 2.0, 2.0, ("NON_MONOTONE", None, None),
     "aadladder_g-0002 entry 1 at 201, 401, 801 (rounded): oscillates", BLIND),
    ([211255.0, 220895.0, 225712.0], 2.0, 2.0, ("ORDER_MISMATCH", 1.0008982225303467, None),
     "aadladder_g-0001 entry 1 (rounded): first order observed", BLIND),
    ([211255.0, 220895.0, 225712.0], 2.0, 1.0, ("OK", 1.0008982225303467, 230529.0),
     "first-order extrapolation: 2 x 225712 - 220895", BLIND),
    ([10.5, 10.125, 10.03125], 1.0, 2.0, "E_DOMAIN", "ratio <= 1 (KR-12)", GAP_KR12),
    ([10.5, 10.125], 2.0, 2.0, "E_INPUT", "two values, three needed", BLIND),
]


# ---------------------------------------------------------------- build

def close(a, b, digits):
    return abs(a - b) <= 0.5 * 10 ** (-digits) * max(1.0, abs(b))


def scipy_rate(k):
    try:
        from scipy.stats import norm
    except ImportError:
        return None
    return float(2 * norm.sf(k))


# K-5a version 2 blind lane (program/STAGE_K_BLIND_K5A_V2.md, compare 2026-11-19 23:35 UTC, first and only run):
# 9 of 11 MATCH on estimate_pnl and bound at 1e-9 relative. idr_k-0012 and idr_k-0013 (cancelling books) MISMATCH on
# estimate_pnl and are NOT counted; idr_k-0011 was not in the packet. Recorded 2026-11-20.
K5A_V2 = "blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_K5A_V2.md, spec 1.1.0): MATCH on estimate_pnl and bound"
K5A_V2_COUNTED = {1, 2, 3, 4, 5, 8, 9, 10, 14}


def idr_ver(ver):
    """KR-234 changed `bound`: a blind match of the old formula no longer covers it."""
    if ver in (BLIND_IDR, K5A):
        return ("blind re-derivation DR-H2 2026-11-19 (program/STAGE_K_BLIND_K5A.md): MATCH on estimate_pnl; bound "
                "redefined by KR-234 (Lagrange bound plus a rounding allowance), so its blind match of the old formula "
                "no longer counts; the K-5a version 2 packet re-derived both outputs (next entry)")
    return ver


def t_scipy_check(nu, k, rate):
    """Outside check of the KR-232 rate: scipy.stats.t (an independent library) against the 50-digit value."""
    from scipy.stats import t as student
    sp = float(2 * student.sf(k, nu))
    off = abs(sp / rate - 1) if rate else abs(sp)
    assert off <= 1e-11, (nu, k, sp, rate)
    return f"SciPy 2*t.sf(k, {nu}) outside check of false_alarm_rate (KR-232): agrees to {max(off, 1e-17):.0e} relative"


AUDIT = ("added by the audit-response lane 2026-11-19 (STAGE_K_R1_AUDIT_A.md; rulings KR-230 to KR-238): hand and "
         "oracle, not blind re-derived")
AUDIT_K5A_V2 = ("added by the audit-response lane 2026-11-19 (STAGE_K_R1_AUDIT_A.md; rulings KR-230 to KR-238): hand and "
                "oracle; blind re-derived afterwards by the K-5a version 2 lane (next entry)")
# K-4c version 2 blind lane (program/STAGE_K_BLIND_TRIG_V2.md, compare 2026-11-20, first and only run): 14 of 14
# value cases MATCH on every output at the goldens' tolerances; trig_k-0004 is not counted (fire gap-decided, KR-13).
TRIG_V2 = ("blind re-derivation DR-H2 2026-11-20 (program/STAGE_K_BLIND_TRIG_V2.md, spec 1.1.0): MATCH on fire, sigma, "
           "threshold, false_alarm_rate and nominal_rate")
TRIG_V2_MATCHED = {1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15, 16, 21}
TRIG_V2_NOCREDIT = {4}  # its fire stays gap-decided by KR-13; the entry it already has says so


def trig_v2_credit(cases):
    """Record the K-4c version 2 MATCH; earlier "not blind" notes are restated as history for the counted cases."""
    restate = [
        ("false_alarm_rate redefined by KR-232 is not blind)",
         "false_alarm_rate redefined by KR-232 was not covered by that match; see the version 2 entry)"),
        ("hand and oracle, not blind re-derived", "hand and oracle; blind re-derived afterwards by the K-4c version 2 lane"),
        ("in the far tail: not blind", "in the far tail; not in the wave-1 packet, blind re-derived by the K-4c version 2 lane"),
    ]
    for c in cases:
        n = int(c["case_id"].rsplit("-", 1)[1])
        if n not in TRIG_V2_MATCHED:
            continue
        assert c["expected"]["status"] == "ok", c["case_id"]
        if n not in TRIG_V2_NOCREDIT:
            vb = []
            for v in c["verified_by"]:
                for a, b in restate:
                    v = v.replace(a, b)
                vb.append(v)
            assert not any("not blind" in v for v in vb), (c["case_id"], vb)
            c["verified_by"] = vb
        c["verified_by"].append(TRIG_V2)


AUDIT_CHANGES = []  # before and after of every changed expected value (oracle/STAGE_K_AUDIT_A_CHECKS.json)


def build():
    suites, out = [], {}
    s = Suite("bt_k", BT, G)
    for inp, status, seq, value, desc, ver in BT_CASES:
        r, err = run(bt_query, inp)
        tags = ("stage_k", "core", "bitemporal", "synthetic")
        if status.startswith("E_"):
            assert err == status, (desc, err)
            s.add("core.store.bitemporal_query", inp, error=err, verified=("hand", ver), tags=tags + ("error",),
                  description=desc)
            continue
        assert err is None and r["status"] == status, (desc, r)
        if seq is None:
            assert r["row"] is None
        else:
            assert r["row"]["sequence"] == seq and r["row"]["value"] == value, (desc, r)
        s.add("core.store.bitemporal_query", inp, outputs=r, cls="date_and_convention", verified=("hand", ver),
              tags=tags, description=desc)
    for inp, status, seq, value, desc in BT_AUDIT:
        r, err = run(bt_query, inp)
        assert err is None and r["status"] == status and r["row"]["sequence"] == seq and r["row"]["value"] == value, r
        s.add("core.store.bitemporal_query", inp, outputs=r, cls="date_and_convention", verified=("hand", AUDIT),
              tags=("stage_k", "core", "bitemporal", "synthetic"), description="KR-235(b): " + desc)
    kr4_property()
    suites.append(s)

    s = Suite("inc_k", INC, G)
    lim = {"absolute": 1e-15, "relative": 0.0}
    want = {0: [0.980392156862745098, 0.951697752271640363, 0.914599323034920812],
            1: [0.980392156862745098, 0.949814623705232580, 0.914654171439767640],
            2: [0.980392156862745098, 0.951697752271640363, 0.911838227756386082]}
    want[3] = want[0]
    meta = {1: (1, 2), 2: (2, 1), 3: (None, 0)}
    for i, (op, inp, desc) in enumerate(INC_CASES):
        r, err = run(par_annual if op == "curve.bootstrap.par_annual" else inc_update, inp)
        tags = ("stage_k", "curves", "incremental", "synthetic")
        if err:
            assert err == "E_INPUT" and i in (4, 5)
            s.add(op, inp, error=err, verified=("hand", BLIND), tags=tags + ("error",), description=desc)
            continue
        for got, w in zip(r["discount_factors"], want[i]):
            assert abs(got - w) <= 1e-15, (i, got, w)
        for got, f64 in zip(r["discount_factors"], bootstrap_f64(inp.get("new_quotes", inp.get("quotes")))):
            assert abs(got - f64) <= 1e-15
        if i in meta:
            assert (r["first_changed_index"], r["recomputed"]) == meta[i], r
        oc = {"first_changed_index": "date_and_convention", "recomputed": "date_and_convention"} if i else None
        s.add(op, inp, outputs=r, cls="simple_analytic", limit=lim, output_classes=oc, verified=("hand", ORACLE, BLIND),
              tags=tags, description=desc)
    for q, desc in fused_differs():
        df = bootstrap_f64(q)
        nq = q[:-1] + [q[-1] + 0.001]
        inp = {"previous_quotes": q, "previous_discount_factors": df, "new_quotes": nq}
        r, err = run(inc_update, inp)
        assert err is None and r["first_changed_index"] == len(q) - 1
        s.add("curve.incremental.update", inp, outputs=r, cls="simple_analytic", limit=lim,
              output_classes={"first_changed_index": "date_and_convention", "recomputed": "date_and_convention"},
              verified=("hand", ORACLE, AUDIT), tags=("stage_k", "curves", "incremental", "synthetic"),
              description="KR-235(a): " + desc)
    suites.append(s)

    s = Suite("trig_k", TRIG, G)
    lim = {"absolute": 0.0, "relative": 1e-14}
    oc_t = {"fire": "date_and_convention", "false_alarm_rate": "tail_probability"}
    tags = ("stage_k", "calibration", "trigger", "synthetic")
    for t, want_, desc, ver in TRIG_CASES:
        inp = trig_inp(t)
        r, err = run(trigger, inp)
        if isinstance(want_, str):
            assert err == want_, (desc, err)
            s.add("calib.trigger.check", inp, error=err, verified=("hand", ver), tags=tags + ("error",),
                  description=desc)
            continue
        sig, thr, fire, rate = want_
        assert r["fire"] is fire and abs(r["sigma"] / sig - 1) <= 1e-15 and abs(r["threshold"] / thr - 1) <= 1e-15
        # The spec prints 0.002699796063260186; the 50-digit value rounds to ...189 (1.1e-15 relative,
        # inside the spec's 1e-14): the golden carries the oracle value.
        assert abs(r["nominal_rate"] / rate - 1) <= 1e-14, (r, rate)
        AUDIT_CHANGES.append({"case": f"trig_k-{len(s.cases) + 1:04d}", "output": "false_alarm_rate",
                              "before": r["nominal_rate"], "after": r["false_alarm_rate"], "ruling": "KR-232"})
        sp = scipy_rate(t[4])
        ver_ = ["hand", ORACLE, ver.replace("MATCH", "MATCH (on the KR-6 rate, now nominal_rate; false_alarm_rate "
                                                       "redefined by KR-232 is not blind)", 1)]
        if sp is not None and ver == K_FAR:
            # SciPy's norm.sf rounds k / sqrt 2 before erfc, the very loss this case guards against: it is
            # 5.7e-14 relative off at k = 30 (SciPy 1.18.1), so it is no check here.
            off = abs(sp / r["nominal_rate"] - 1)
            assert 1e-14 < off < 1e-12, (sp, r)
            ver_.append(f"SciPy 2*norm.sf(k) is {off:.1e} relative off on nominal_rate (it rounds k / sqrt 2 first): "
                        "no outside check of nominal_rate")
        elif sp is not None:
            assert abs(sp / r["nominal_rate"] - 1) <= 1e-14, (sp, r)
            ver_.append("SciPy 2*norm.sf(k) outside check of nominal_rate (KR-11): agrees to 1e-14 relative")
        ver_.append(t_scipy_check(len(t[0]) - 1, t[4], r["false_alarm_rate"]))
        s.add("calib.trigger.check", inp, outputs=r, cls="simple_analytic", limit=lim, output_classes=oc_t,
              verified=tuple(ver_), tags=tags, description=desc)
    for t, desc in TRIG_AUDIT:
        inp = trig_inp(t)
        r, err = run(trigger, inp)
        assert err is None, (desc, err)
        s.add("calib.trigger.check", inp, outputs=r, cls="simple_analytic", limit=lim, output_classes=oc_t,
              verified=("hand", ORACLE, t_scipy_check(len(t[0]) - 1, t[4], r["false_alarm_rate"]), AUDIT),
              tags=tags, description="KR-232: " + desc)
    for t, code, desc in TRIG_FLOOR:
        inp = trig_inp(t)
        r, err = run(trigger, inp)
        assert err == code, (desc, err, r)
        if code:
            s.add("calib.trigger.check", inp, error=err, verified=("hand", AUDIT), tags=tags + ("error",),
                  description="KR-233: " + desc)
        else:
            # KR-233: just above the floor the binary64 sigma is within 2.2e-8 relative of the exact one, so this case
            # compares at 3e-8 (the derived bound), not 1e-14
            s.add("calib.trigger.check", inp, outputs=r, cls="simple_analytic", limit={"absolute": 0.0, "relative": 3e-8},
                  output_classes=oc_t, verified=("hand", ORACLE, AUDIT), tags=tags, description="KR-233: " + desc)
    trig_v2_credit(s.cases)
    suites.append(s)

    s = Suite("idr_k", IDR, G)
    lim = {"absolute": 0.0, "relative": 1e-9}
    filled = []
    for inp, desc, ver, table in IDR_CASES:
        r, err = run(idr, inp)
        tags = ("stage_k", "risk", "intraday", "synthetic")
        if err:
            s.add("risk.intraday.delta_gamma_bound", inp, error=err, verified=("hand", ver), tags=tags + ("error",),
                  description=desc)
            continue
        parts = [idr_parts(p, inp["shift"]) for p in inp["positions"]]
        exact = mp.fsum(p[2] for p in parts)
        err_ = mp.fsum(p[1] for p in parts) - exact
        assert abs(err_) <= mp.fsum(p[3] for p in parts), desc  # the Lagrange bound holds
        AUDIT_CHANGES.append({"case": f"idr_k-{len(s.cases) + 1:04d}", "output": "bound",
                              "before": common.f(mp.fsum(p[3] for p in parts)), "after": r["bound"], "ruling": "KR-234"})
        if table is not None:
            est, bnd, ex_v, est_v, ratio = table
            v = parts[0][0]
            assert close(r["estimate_pnl"], est, 9) and abs(r["bound"] - bnd) <= 5e-7, (r, table)  # bound: the Lagrange
        # part printed in the spec; the KR-234 allowance adds at most 1.1e-11 relative
            assert abs(v + parts[0][2] - mp.mpf(ex_v)) < 1e-9 and abs(v + parts[0][1] - mp.mpf(est_v)) < 1e-9
            assert abs(float(abs(err_) / parts[0][3]) - ratio) <= 5e-4, (desc, float(abs(err_) / parts[0][3]))
        filled.append((s.name, len(s.cases) + 1, r, float(exact), float(err_)))
        s.add("risk.intraday.delta_gamma_bound", inp, outputs=r, cls="simple_analytic", limit=lim,
              output_classes={"label": "date_and_convention"}, verified=(ORACLE, idr_ver(ver)) + ((K5A_V2,) if len(s.cases) + 1 in K5A_V2_COUNTED else ()), tags=tags,
              description=desc)
    for inp, desc in IDR_AUDIT:
        r, err = run(idr, inp)
        assert err is None, desc
        parts = [idr_parts(p, inp["shift"]) for p in inp["positions"]]
        exact = mp.fsum(p[2] for p in parts)
        assert abs(mp.mpf(r["estimate_pnl"]) - exact) <= mp.mpf(r["bound"]), desc  # KR-234 claim on the golden
        filled.append((s.name, len(s.cases) + 1, r, float(exact), float(mp.fsum(p[1] for p in parts) - exact)))
        # KR-240 (KA-A7): with cancellation the binary64 estimate cannot reach 1e-9 relative to its own small value.
        # The tolerance adds, as an absolute term, the estimate's share of the KR-234 rounding allowance:
        # 2^-49 sum (1 + T|y| + T|h|) |v| (T|h| + T^2 h^2), which the derivation shows the binary64 estimate is within.
        h_ = mp.mpf(inp["shift"])
        share = mp.fsum(RHO * (1 + mp.mpf(q["maturity"]) * abs(mp.mpf(q["yield"])) + mp.mpf(q["maturity"]) * abs(h_))
                        * abs(p[0]) * (mp.mpf(q["maturity"]) * abs(h_) + (mp.mpf(q["maturity"]) * h_) ** 2)
                        for p, q in zip(parts, inp["positions"]))
        lim_ = lim
        if share > mp.mpf("1e-9") * abs(mp.mpf(r["estimate_pnl"])):
            lim_ = {"absolute": float(share), "relative": 1e-9}
            desc += (f" (cancelling: compared at 1e-9 relative plus {float(share):.3g} absolute, the estimate's share of "
                     "the KR-234 rounding allowance; KR-240)")
        s.add("risk.intraday.delta_gamma_bound", inp, outputs=r, cls="simple_analytic", limit=lim_,
              output_classes={"label": "date_and_convention"}, verified=((ORACLE, AUDIT_K5A_V2, K5A_V2) if len(s.cases) + 1 in K5A_V2_COUNTED else (ORACLE, AUDIT)), tags=tags,
              description="KR-234: " + desc)
    for name, i, r, ex, e in filled:
        note(f"{name}-{i:04d}: estimate_pnl {r['estimate_pnl']!r} bound {r['bound']!r} exact {ex!r} est-exact {e!r}")
    suites.append(s)

    s = Suite("rich_k", RICH, G)
    for vals, ratio, p, want_, desc, ver in RICH_CASES:
        inp = {"values": vals, "ratio": ratio, "assumed_order": p}
        r, err = run(richardson, inp)
        tags = ("stage_k", "numerics", "richardson", "synthetic")
        if isinstance(want_, str):
            assert err == want_, (desc, err)
            s.add("num.richardson.check", inp, error=err, verified=("hand", ver), tags=tags + ("error",),
                  description=desc)
            continue
        st, obs, ext = want_
        assert r["status"] == st and (r["observed_order"] == obs if obs is None or obs in (1.0, 2.0)
                                      else abs(r["observed_order"] / obs - 1) <= 1e-15), (desc, r)
        assert r["extrapolated"] == ext or abs(r["extrapolated"] - ext) <= 1e-9, (desc, r)
        s.add("num.richardson.check", inp, outputs=r, cls="simple_analytic", output_classes={"status": "date_and_convention"},
              verified=("hand", ORACLE, ver), tags=tags, description=desc)
    suites.append(s)

    e = Suite("e1_k", BT, G)
    e1 = [
        ("core.store.bitemporal_query", dict(bt_inp("2026-03-15", "2026-02-15"),
                                             records=[dict(LOG[0], value="NaN")] + LOG[1:]),
         "F-2/F-38: NaN token at the top level of records[0].value (from bt_k-0001)"),
        ("curve.bootstrap.par_annual", {"quotes": [0.02, "NaN", 0.03]}, "F-2: NaN at quotes/1 (from inc_k-0001)"),
        ("curve.incremental.update", dict(INC_CASES[1][1], new_quotes=[0.02, "Infinity", 0.03]),
         "F-2: Infinity at new_quotes/1 (from inc_k-0002)"),
        ("calib.trigger.check", dict(trig_inp(TRIG_CASES[0][0]), x_now="NaN"), "F-2: NaN at x_now (from trig_k-0001)"),
        ("risk.intraday.delta_gamma_bound", {"positions": [POS], "shift": "-Infinity"},
         "F-2: -Infinity at shift (from idr_k-0001)"),
        ("num.richardson.check", {"values": [10.5, "NaN", 10.03125], "ratio": 2.0, "assumed_order": 2.0},
         "F-2: NaN at values/1 (from rich_k-0001)"),
    ]
    for op, inp, desc in e1:
        e.add(op, inp, error="E_DOMAIN", verified=("hand", ADDED), tags=("stage_k", "e1", "non-finite-input"),
              description=desc)
    suites.append(e)
    suites.append(e2_suite())
    suites.append(lim_suite())
    return suites


def lim_suite():
    """KR-231 and KR-230 at the size limit (audit A pairs b and c, KA-A2): compact, as limits.json. A 100,001-record
    log of one repeated record is E_LIMIT although log check 2 (sequence increasing) also fails."""
    s = Suite("lim_k", BT, G)
    s.compact = True
    rec1 = {"sequence": 1, "series_id": "A", "valid_from": "2026-01-01T00:00:00Z", "valid_to": None,
            "knowledge_time": "2026-01-01T00:00:00Z", "value": 0}
    tags = ("stage_k", "e2", "two-errors", "error", "limit")
    s.add("core.store.bitemporal_query", {"records": [rec1] * 100_001, "series_id": "A",
                                          "knowledge_as_of": "2026-01-02T00:00:00Z", "valid_at": "2026-01-02T00:00:00Z"},
          error="E_LIMIT", verified=("hand", AUDIT), tags=tags,
          description="100,001 records, one above the generic array cap [limit], sequence repeating [structural] "
                      "(audit A pair c; KA-A2 boundary, KR-231)")
    s.add("calib.trigger.check", {"changes": [0.0, 1.0] * 50_000 + [0.0], "x_ref": 0.0, "x_now": 0.0, "days_since": 1.0,
                                  "k": 0.0},
          error="E_LIMIT", verified=("hand", AUDIT), tags=tags,
          description="100,001 changes [limit] and k = 0 [domain] (audit A pair b)")
    return s


TWO = "added by the coordinator lane 2026-11-19 (two errors at once): hand, not blind re-derived"
TWO_KR230 = ("expected code set by ruling KR-230 (one error order, HR-122; audit A, KA-A1) 2026-11-19: the HR-66 order "
             "of the first version gave {old}")
TWO_G31 = ("added by the K-8 port lane 2026-11-19 (two errors at once, size limit before domain by G-31): hand, not "
           "blind re-derived; Python and Java already gave E_LIMIT, the C++ and Rust builds were fixed to match")
TWO_G18 = ("added by the K-8 port lane 2026-11-19 (two errors at once, order HR-66): hand, not blind re-derived; "
           "Java, C++ and Rust already gave E_INPUT, the Python build was fixed to match")


def e2_suite():
    """Two errors in one case; the code is the earlier one in the HR-122 order (ruling KR-230): E_SCHEMA, E_LIMIT
    (input sizes), the F-2 finite rule, structural E_INPUT, E_DOMAIN, the stale-cache E_INPUT. The step of each
    error is named in brackets in the description; python/tests/test_stage_k_error_order.py checks every code
    against the order."""
    s = Suite("e2_k", BT, G)
    q201 = [0.01] * 201
    df201 = bootstrap_f64(q201)
    inc = INC_CASES[1][1]
    stale = BASE_DF[:2] + [math.nextafter(BASE_DF[2], math.inf)]
    trig = trig_inp(TRIG_CASES[0][0])
    rich = {"values": [10.5, 10.125, 10.03125], "ratio": 2.0, "assumed_order": 2.0}
    no_yield = {"notional": 1.0, "maturity": 1.0}
    cases = [
        ("core.store.bitemporal_query",
         bt_inp("2026-04-01", "2026-02-15", [dict(LOG[0], sequence=0)] + _with(2, knowledge_time="2026-03-01")[1:]),
         "E_SCHEMA", "sequence 0 in records[0] [schema] and seq 3 knowledge_time going back [structural]", None),
        ("core.store.bitemporal_query",
         bt_inp("2026-04-01", "2026-02-15", [dict(LOG[0], value="NaN"), dict(LOG[1], sequence=1)] + LOG[2:]),
         "E_DOMAIN", "sequence not increasing [structural] and NaN at records[0].value [finite]", "E_INPUT"),
        ("curve.bootstrap.par_annual", {"quotes": ["NaN"] + q201[1:]},
         "E_LIMIT", "NaN at quotes/0 [finite] and 201 quotes [limit]", "E_DOMAIN"),
        ("curve.bootstrap.par_annual", {"quotes": [-1.5] + q201[1:]},
         "E_LIMIT", "quote -1.5 [domain] and 201 quotes [limit]", "E_DOMAIN"),
        ("curve.incremental.update", dict(inc, new_quotes=[0.02, "NaN"]),
         "E_DOMAIN", "lengths differ [structural] and NaN at new_quotes/1 [finite]", "E_INPUT"),
        ("curve.incremental.update", dict(inc, previous_discount_factors=stale, new_quotes=[0.02, -2.0, 0.03]),
         "E_DOMAIN", "new quote -2 [domain] and a stale cache [after]", None),
        ("curve.incremental.update",
         {"previous_quotes": q201, "previous_discount_factors": df201[:-1] + [math.nextafter(df201[-1], math.inf)],
          "new_quotes": q201},
         "E_LIMIT", "stale cache [after] and 201 quotes [limit]", None),
        ("calib.trigger.check", dict(trig, changes=[1.0], k=0.0),
         "E_INPUT", "one change [structural] and k = 0 [domain]", None),
        ("calib.trigger.check", {kk: vv for kk, vv in dict(trig, k=0.0).items() if kk != "x_now"},
         "E_SCHEMA", "x_now missing [schema] and k = 0 [domain]", None),
        ("calib.trigger.check", dict(trig, changes=[1.0, 1.0, 1.0], days_since=0.5),
         "E_DOMAIN", "days_since 0.5 [domain] and sigma 0 [domain] (one code)", None),
        ("risk.intraday.delta_gamma_bound", {"positions": [], "shift": "NaN"},
         "E_DOMAIN", "no positions [structural] and NaN shift [finite] (audit A pair d)", "E_INPUT"),
        ("risk.intraday.delta_gamma_bound", {"positions": [dict(POS, maturity=0.0), no_yield], "shift": 0.01},
         "E_SCHEMA", "yield missing in positions[1] [schema] and maturity 0 in positions[0] [domain]", None),
        ("num.richardson.check", dict(rich, values=[10.5, 10.125], ratio=1.0),
         "E_INPUT", "two values [structural] and ratio 1 [domain]", None),
        ("num.richardson.check", {"values": rich["values"], "ratio": 1.0},
         "E_SCHEMA", "assumed_order missing [schema] and ratio 1 [domain]", None),
    ]
    for op, inp, code, desc, old_code in cases:
        ver = ("hand", TWO) if old_code is None else ("hand", TWO, TWO_KR230.format(old=old_code))
        if old_code is not None:
            AUDIT_CHANGES.append({"case": f"e2_k-{len(s.cases) + 1:04d}", "output": "error_code", "before": old_code,
                                  "after": code, "ruling": "KR-230"})
        s.add(op, inp, error=code, verified=ver, tags=("stage_k", "e2", "two-errors", "error"), description=desc)
    # The G-18 path (no `method`) of the two Bermudan operations. Before 2026-11-19 the Python build checked the
    # grid first and gave E_DOMAIN; Java, C++ and Rust gave E_INPUT (four-build probe, K-8 port lane).
    g18 = json.loads((common.ROOT / "datasets/golden/stage_g/aadladder_g.json").read_text("utf-8"))["cases"][0]
    bad = json.loads(json.dumps(g18["inputs"]))
    bad["exercise_times"] = [1.5]
    bad["grid"]["width"] = 0.0
    for op in ("rates.shortrate.bermudan_swaption", "rates.shortrate.bermudan_ladder"):
        s.add(op, bad, error="E_INPUT", verified=("hand", TWO_G18), tags=("stage_k", "e2", "two-errors", "error"),
              description="G-18 path (no method): exercise time 1.5 not a reset date [structural] "
                          "and grid width 0 [domain]")
    # G-31 puts the size limits after E_SCHEMA and before F-2 and the domain checks. Python and Java gave E_LIMIT;
    # C++ and Rust checked sigma first and gave E_DOMAIN (four-build probe, K-8 port lane; fixed there).
    big = json.loads(json.dumps(g18["inputs"]))
    big["sigma"] = 0.0
    big["grid"]["nx"] = 20001
    for op in ("rates.shortrate.bermudan_swaption", "rates.shortrate.bermudan_ladder"):
        s.add(op, big, error="E_LIMIT", verified=("hand", TWO_G31), tags=("stage_k", "e2", "two-errors", "error"),
              description="G-18 path (no method): sigma 0 [domain] and nx 20,001 above 10,001 [limit] (checked "
                          "before the domain checks by G-31)")
    # Audit A (KA-A1, ruling KR-230): the pairs the first version had no case for, appended so that the case ids
    # above stay as they were.
    more = [
        # audit A (KA-A1) pairs and the steps the first version had no case for
        ("calib.trigger.check", dict(trig, changes=["NaN"]),
         "E_DOMAIN", "changes [NaN]: one change [structural] and NaN [finite] (audit A pair a)", "E_INPUT"),
        ("num.richardson.check", dict(rich, values=[10.5, "NaN"]),
         "E_DOMAIN", "two values [structural] and NaN at values/1 [finite]", "E_INPUT"),
        ("core.store.bitemporal_query",
         bt_inp("2026-04-01", "2026-02-15", [dict(LOG[0], value="NaN"), dict(LOG[1], sequence=0)] + LOG[2:]),
         "E_SCHEMA", "sequence 0 in records[1] [schema] and NaN at records[0].value [finite]", None),
        ("curve.incremental.update", dict(inc, new_quotes=[0.02, -2.0]),
         "E_INPUT", "lengths differ [structural] and new quote -2 [domain]", None),
        ("curve.incremental.update", dict(inc, previous_discount_factors=stale, new_quotes=[0.02, 0.026, "Infinity"]),
         "E_DOMAIN", "Infinity at new_quotes/2 [finite] and a stale cache [after]", None),
    ]
    for op, inp, code, desc, old_code in more:
        s.add(op, inp, error=code, verified=("hand", AUDIT), tags=("stage_k", "e2", "two-errors", "error"),
              description=desc)
    return s


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    suites = build()
    for s in suites:
        s.write()
    common.GOLDEN = keep
    out = common.ROOT / "oracle" / "STAGE_K_AUDIT_A_CHANGES.json"
    out.write_text(json.dumps({"generator": G, "note": "before and after of every expected value of the wave 1 "
                               "goldens changed by the audit A rulings (KR-230 to KR-234), 2026-11-19",
                               "changes": AUDIT_CHANGES}, indent=1) + "\n", encoding="utf-8", newline="\n")
    note("stage K wave 1: " + ", ".join(f"{s.name} {len(s.cases)}" for s in suites))


if __name__ == "__main__":
    main()
