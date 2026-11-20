"""Recompute every worked-example number in docs/question-bank/13-execution-microstructure.md and check the strings.

This script restates the spec formulas with the standard library and checks them against the spec goldens and the
page, so it needs no build. The stage H operations are now built in all four languages; moving this script onto
quantforge_core, like the other sets, is still to do.

Run: python docs/question-bank/verify/v13_execution_microstructure.py   (no package needed)
"""
from __future__ import annotations

import math
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[1] / "13-execution-microstructure.md").read_text(encoding="utf-8")
checks = 0


def has(s: str) -> None:
    global checks
    assert s in TEXT, f"missing in 13-execution-microstructure.md: {s!r}"
    checks += 1


def close(a: float, b: float, tol: float = 1e-9) -> None:
    assert abs(a - b) <= tol * max(1.0, abs(b)), (a, b)


# Q13.2 sched_h-0001
base, rem = divmod(1000, 3)
twap = [base + (1 if i < rem else 0) for i in range(3)]
assert twap == [334, 333, 333] and sum(twap) == 1000
has("`[334, 333, 333]`")

# Q13.3 sched_h-0003, 0004
assert [1000 * w / 10 for w in (1, 2, 3, 4)] == [100, 200, 300, 400]
has("`[100, 200, 300, 400]`")
raw = [10 / 3] * 3
out = [int(r) for r in raw]
for i in sorted(range(3), key=lambda i: (-(raw[i] - out[i]), i))[: 10 - sum(out)]:
    out[i] += 1
assert out == [4, 3, 3]
has("`[4, 3, 3]`")

# Q13.4 sched_h-0005
p, left, sl = 0.2, 1000, []
for v in (1000, 2000, 4000):
    s = min(left, int(p * v / (1 - p)))
    sl.append(s)
    left -= s
assert sl == [250, 500, 250] and left == 0
has("`[250, 500, 250]`, residual 0")
has("`250 / 1250 = 0.2`")
close(200 / 1200, 0.16667, 1e-4)
has("`200 / 1200 = 16.7 %`")

# Q13.5 sched_h-0006
close(0.1 / 0.9 * 900, 100)
has("filled 200, residual 800")

# Q13.7 ac_h-0001
X, T, N, sigma, eps, eta, gamma = 1e6, 5.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7
eta_t = eta - gamma * 1.0 / 2
close(eta_t, 2.375e-6)
E0 = 0.5 * gamma * X**2 + eps * X + eta_t * X**2 / T
close(E0, 662500)
has("`E = 1/2 gamma X^2 + epsilon X + eta_tilde X^2 / T = 125,000 + 62,500 + 475,000 = 662,500`")
V0 = sigma**2 * X**2 * (N - 1) * (2 * N - 1) / (6 * N)
close(V0, 1.083e12)
has("= 0.9025e12 x 1.2 = 1.083e12`")
close(sigma**2 * X**2 * T / 3, 1.504e12, 1e-3)
has("which gives 1.504e12 here")

# Q13.8 ac_h-0002, ac_h-0005
lam = 1e-6
close(1 + lam * sigma**2 / (2 * eta_t), 1.19)
kappa = math.acosh(1.19)
close(kappa, 0.6070761632, 1e-10)
x = [X * math.sinh(kappa * (T - j)) / math.sinh(kappa * T) for j in range(N + 1)]
close(x[1], 541955.5544, 1e-9)
E = 0.5 * gamma * X**2 + eps * X + eta_t * sum((x[j] - x[j + 1]) ** 2 for j in range(N))
V = sigma**2 * sum(h * h for h in x[1:])
close(E, 911226.986, 1e-9)
close(V, 3.641285721e11, 1e-9)
has("`kappa = 0.6070761632`; after day 1, 541,955.5544 shares")
has("`E = 911,226.986`, `V = 3.641285721e11`")
close(kappa * T, 3.0353808, 1e-7)
has("`kappa T = 3.0353808`")
assert 240000 < E - E0 < 250000 and abs(V / V0 - 1 / 3) < 0.01
has("about 249,000 dollars of expected cost buys a variance one third as large")

# Q13.9 ac_h-0004
eta5 = eta - gamma * 5 / 2
close(eta5, 1.875e-6)
close(0.5 * gamma * X**2 + eps * X + eta5 * X**2 / 5, 562500)
has("`E = 125,000 + 62,500 + 375,000 = 562,500`")

# Q13.11 tca_h-0001, 0002
fills = [(600, 100.20), (200, 100.30)]
Q = sum(q for q, _ in fills)
d, e, o = Q * 0.10, sum(q * (px - 100.10) for q, px in fills), (1000 - Q) * 1.0
close(d, 80)
close(e, 100)
close(o, 200)
close((d + e + o + 5) / (1000 * 100) * 1e4, 38.5)
has("total `80 + 100 + 200 + 5 = 385`, which is `385 / (1000 x 100) x 1e4 = 38.5` bp")
has("total -380 (`tca_h-0002`)")

# Q13.12 imp_h-0001, 0002
close(0.02 * math.sqrt(1e5 / 1e7), 0.002)
close(0.02 * math.sqrt(4e5 / 1e7), 0.004)
has("`0.02 x sqrt(0.01) = 0.002`, 20 bp")

# Q13.13 imp_h-0003, 0004
close(1000 / 10, 100)
close(8 * 1000 / 10, 800)
has("blocks of 100, rate 800")
close(1e5 / 4.231, 23635.0744504845, 1e-13)
close(2.231e5 / 4.231, 52729.8510990310, 1e-13)
has("blocks of 23,635.0744504845 and rate 52,729.8510990310")


# Q13.14, Q13.15 as_h-0001, 0005..0007
def spread(g: float, t: float, k: float = 1.5, sig: float = 2.0) -> float:
    return g * sig**2 * t + (2 / g) * math.log(1 + g / k)


r = 100 - 2 * 0.1 * 4
close(r, 99.2)
sp = spread(0.1, 1.0)
close(sp, 1.6907704228, 1e-10)
close(r - sp / 2, 98.3546147886, 1e-11)
close(r + sp / 2, 100.0453852114, 1e-11)
has("spread `0.4 + 20 ln(16/15) = 1.6907704228`; bid 98.3546147886, ask 100.0453852114")
for g, val, printed in ((0.1, 1.4907704228, 1.49), (0.01, 1.3489085437, 1.35), (1.0, 3.0216512475, 3.02)):
    close(spread(g, 0.5), val, 1e-10)
    assert abs(spread(g, 0.5) - printed) <= 0.005
has("1.4907704228, 1.3489085437 and 3.0216512475")

# Q13.19 to Q13.21 pt_h-0002, 0021, 0011
from decimal import Decimal as D
assert 2 * (D(105) - 100) + (-1) * (D(105) - 110) == 15
assert D(10000) - D("200.20") + D("109.89") == D("9909.69") and D("9909.69") + 105 - 10000 == D("14.69")
has("trading is `2 x (105 - 100) + (-1) x (105 - 110) = 15`; fees -0.31; total 14.69")
has("reason `HASH` (`pt_h-0021`)")
has("`MAX_QTY`, `MAX_NOTIONAL`, `MAX_POSITION` (`pt_h-0011`)")

# Q13.22 mest_h-0001
close(math.sqrt(12 / 4 / 4), 0.866025403784439, 1e-15)
has("sqrt(0.75) = 0.866025403784439")

# Q13.23 venue_h-0001
assert 100 * (D("100.05") - D("100.01")) == 4 and -200 * (D("100.05") - D("100.03")) == -4
has("gains 0.04 a share (+4) and a sell of 200 at 100.03 loses 0.02 a share (-4)")

# Q13.24 alg_h-0002, 0004
for n, v in ((1, 0.75), (2, 15 / 8), (3, 63 / 16)):
    close(math.sinh(n * math.log(2)), v, 1e-15)
close(1000 * (1 - 0.75 / (15 / 8)), 600, 1e-12)
close(2100 * (1 - (15 / 8) / (63 / 16)), 1100, 1e-12)
has("1,000 over two buckets is 600 and 400 (`alg_h-0002`)")

# Q13.25 tcx_h-0001
istar = 700 * math.sqrt(0.04) * 0.02
close(istar, 2.8, 1e-12)
close(0.9 * istar * 0.5 + 0.1 * istar + 1.5, 3.04, 1e-12)
close(1e4 * 0.02 * math.sqrt(0.16 / 3), 46.1880215352, 1e-10)
has("3.04 bp expected cost and 46.2 bp timing risk")

# Q13.26 recorded H-9 laptop figures (benchmarks/results/h9/README.md on branch h-lowlat)
assert 105 > 50 and 39 <= 150 and 47 <= 150
has("C++ p50 39 ns, Rust 47 ns, against 150")

# ---- Q13.27 to Q13.47: venues, book rebuild, conventions, checks, latency, paper financing ----
import itertools
import json
import zlib
from fractions import Fraction as F

GOLD = Path(__file__).resolve().parents[3] / "datasets" / "golden" / "stage_h"
_cases: dict = {}


def case(cid: str) -> dict:
    suite = cid.split("-")[0]
    if suite not in _cases:
        _cases[suite] = {c["case_id"]: c for c in json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))["cases"]}
    return _cases[suite][cid]


def out(cid: str) -> dict:
    e = case(cid)["expected"]
    assert e["status"] == "ok", (cid, e)
    return e["outputs"]


def err(cid: str) -> str:
    e = case(cid)["expected"]
    assert e["status"] == "error", (cid, e)
    return e["error_code"]


# Q13.27 dark_h-0001
o = out("dark_h-0001")
assert (D("100.00") + D("100.10")) / 2 == D("100.05")
assert o["fills"] == [{"buy_id": "B1", "price": "100.05", "qty": "60", "sell_id": "S1", "seq": 1}]
assert o["resting"][0]["open_qty"] == "40" and o["label"] == "simulated venue; not a real dark pool"
has("The pair fills 60 at 100.05; the buy rests with 40 open (`dark_h-0001`)")
assert out("dark_h-0007")["fills"][0]["markouts_bp"]["1"] == "1.999"

# Q13.28 dark_h-0002, 0003
assert out("dark_h-0002")["fills"] == [] and len(out("dark_h-0002")["resting"]) == 2
o = out("dark_h-0003")
assert (D("100.00") + D("100.01")) / 2 == D("100.005") and o["fills"][0]["price"] == "100.005" and o["fills"][0]["qty"] == "60"
has("60 fill at 100.005")

# Q13.29 dark_h-0004
a, b = out("dark_h-0004")["scenarios"]
assert a["invitations"][0]["result"] == "FIRMED" and a["invitations"][0]["event"] == 3 and a["fills"][0]["qty"] == "30"
assert a["resting"][0]["open_qty"] == "20"
assert [(i["event"], i["result"]) for i in b["invitations"]] == [(3, "DECLINED"), (6, "DECLINED")] and b["fills"] == []
has("the next invitation, at event 6, is declined too")


# Q13.30, Q13.31: sor_h-0003, 0005 by exhaustive search over eq. (5) (HR-37 to HR-39)
def router(inp: dict) -> dict:
    S, h, f, th = int(inp["S"]), F(inp["h"]), F(inp["f"]), F(inp["theta"])
    lu, lo = F(inp["lambda_u"]), F(inp["lambda_o"])
    lit = [v for v in inp["venues"] if v["kind"] == "LIT"]
    dark = [v for v in inp["venues"] if v["kind"] == "DARK"]
    rows = [[int(x) for x in r] for r in inp["lit_samples"]]
    dprobs = []
    for v in dark:
        t = [F(x) for x in v["tail"]] + [F(0)]
        dprobs.append([(0, 1 - t[0])] + [(s + 1, t[s] - t[s + 1]) for s in range(len(t) - 1)])
    best = None
    for X in itertools.product(range(S + 1), repeat=1 + len(inp["venues"])):
        M, Ls = X[0], X[1:]
        cost = fill = under = F(0)
        for row in rows:
            for draws in itertools.product(*dprobs):
                p = F(1, len(rows))
                for _, q in draws:
                    p *= q
                if p == 0:
                    continue
                A, c, li, di = M, (h + f) * M, 0, 0
                for v, L in zip(inp["venues"], Ls):
                    if v["kind"] == "LIT":
                        xi, Q = row[li], int(v["Q"])
                        fl = max(xi - Q, 0) - max(xi - Q - L, 0)
                        li += 1
                    else:
                        fl = min(L, draws[di][0])
                        di += 1
                    A += fl
                    c -= (h + F(v["r"]) - F(v["as"])) * fl
                un, ov = max(S - A, 0), max(A - S, 0)
                c += th * (M + sum(Ls) + un) + lu * un + lo * ov
                cost += p * c
                fill += p * min(A, S)
                under += p * (A < S)
        if best is None or cost < best[0]:
            best = (cost, X, fill, under)
    cost, X, fill, under = best
    return {"M": X[0], "L": list(X[1:]), "cost": cost, "fill": fill, "under": under}


for cid in ("sor_h-0003", "sor_h-0005"):
    r, g = router(case(cid)["inputs"]), out(cid)
    assert str(r["M"]) == g["M"] and [str(x) for x in r["L"]] == g["L"], (cid, r, g)
    assert r["cost"] == F(g["expected_cost"]) and r["fill"] == F(g["expected_fill"]) and r["under"] == F(g["p_underfill"]), cid
has("the router sends `M = 8` and posts `L = 2`, expected cost 7.35, expected fill 9.5, probability of underfill 0.25 (`sor_h-0003`)")
has("`M = 0`, `L = [4, 3]`, expected cost 0, expected fill 2.75 and probability of underfill 0.5 (`sor_h-0005`)")

# Q13.32 to Q13.35 lit_h
o = out("lit_h-0006")
assert [(x["maker_id"], x["qty"]) for x in o["fills"]] == [("I1", "10"), ("B2", "5")]
assert o["book"]["bids"][1] == {"display_qty": "10", "hidden_qty": "80", "id": "I1", "price": "100", "seq": 3}
has("showing 10 with 80 hidden")
o = out("lit_h-0007")
assert [(x["maker_id"], x["taker_id"]) for x in o["fills"]] == [("A", "S1"), ("B", "S2")]
assert o["conservation"]["A"] == {"cancelled": "5", "filled": "3", "rejected": "0", "resting": "8", "submitted": "16"}
has("16 submitted, 3 filled, 5 cancelled and 8 resting (`lit_h-0007`)")
o = out("lit_h-0003")
assert o["fills"] == [] and o["conservation"]["B1"]["rejected"] == "12"
o = out("lit_h-0004")
assert o["fills"][0]["price"] == "101" and o["fills"][0]["qty"] == "5" and o["cancelled"] == [{"id": "B1", "qty": "3"}]
has("so 3 are cancelled (`lit_h-0004`)")
o = out("lit_h-0008")
assert o["fills"] == [{"maker_id": "P1", "price": "101", "qty": "2", "seq": 1, "taker_id": "S1"}]
assert o["book"]["bids"][0]["hidden_qty"] == "3" and o["book"]["bids"][0]["display_qty"] == "0"
assert math.floor((100 + 103) / 2) == 101
has("the buy peg rounds down to 101")


# Q13.36 ob_h-0001, 0010: [KR-CRC] checksum recomputed
def kcrc(asks: list, bids: list) -> int:
    fmt = lambda x: x.replace(".", "").lstrip("0")  # noqa: E731
    return zlib.crc32("".join(fmt(p) + fmt(q) for p, q in asks[:10] + bids[:10]).encode())


m = case("ob_h-0001")["inputs"]["messages"][0]
assert kcrc(m["asks"], m["bids"]) == out("ob_h-0001")["crc32"] == 3310070434
assert zlib.crc32(b"12300100000000") == out("ob_h-0010")["crc32"] == 1057566538
assert out("ob_h-0010")["checksum_string"] == "12300100000000"
has("the checksum is 3310070434 (`ob_h-0001`")
has("the string `12300100000000`, whose CRC32 is 1057566538 (`ob_h-0010`)")

# Q13.37 ob_h-0004, 0006, 0007, 0008
assert out("ob_h-0004")["book"]["bids"][0] == ["100.0", "7.00000000"]
assert out("ob_h-0007")["stats"]["deletes_of_absent_level"] == 1
assert [e["kind"] for e in out("ob_h-0006")["events"]] == ["LOCKED", "CROSSED"]
o = out("ob_h-0008")
assert o["stats"]["gaps"] == 1 and o["stats"]["snapshots"] == 2 and [e["kind"] for e in o["events"]] == ["GAP", "UPDATE_BEFORE_SNAPSHOT"]
assert err("ob_h-0011") == "E_DOMAIN" and err("ob_h-0014") == "E_SCHEMA" and err("ob_h-0012") == "E_DOMAIN"
has("`gaps` 1, `snapshots` 2 (`ob_h-0008`)")

# Q13.38, Q13.39 eqc_h
assert out("eqc_h-0001")["price"] == "10.00" and out("eqc_h-0002")["price"] == "10.01"
assert out("eqc_h-0010")["price"] == "10.005" and err("eqc_h-0020") == "E_INPUT" and out("eqc_h-0022")["price"] == "10.005"
assert case("eqc_h-0020")["inputs"]["as_of"] == "2026-11-19" and case("eqc_h-0022")["inputs"]["as_of"] == "2027-11-01"
has("10.005 rounds to 10.00 for a buy and 10.01 for a sell")
assert out("eqc_h-0023")["cap"] == "0.003" and err("eqc_h-0024") == "E_DOMAIN"
assert [out(c)["round_lot"] for c in ("eqc_h-0025", "eqc_h-0026", "eqc_h-0027")] == [40, 100, 40]
assert [case(c)["inputs"]["as_of"] for c in ("eqc_h-0025", "eqc_h-0026", "eqc_h-0027")] == ["2026-11-19", "2025-10-31", "2025-11-03"]
has("At 500 the round lot is 40 on 2026-11-19 and on 2025-11-03, but 100 on 2025-10-31")

# Q13.40 fxc_h
assert out("fxc_h-0001") == {"currency": "USD", "pip_value": "100"} and out("fxc_h-0002") == {"currency": "JPY", "pip_value": "10000"}
assert D(1000000) * D("0.0001") == 100 and D(1000000) * D("0.01") == 10000
for cid, want in (("fxc_h-0004", "2026-11-27"), ("fxc_h-0006", "2026-11-23"), ("fxc_h-0008", "2026-11-27")):
    assert out(cid)["spot_date"] == want, cid
has("settles Monday 2026-11-23 (`fxc_h-0006`)")

# Q13.41 rtc_h
for cid, txt, val in (("rtc_h-0001", "99-16", F(99) + F(16, 32)), ("rtc_h-0002", "99-16+", F(99) + F(33, 64)),
                      ("rtc_h-0003", "99-162", F(99) + F(65, 128)), ("rtc_h-0004", "99-167", F(99) + F(67, 128))):
    assert case(cid)["inputs"]["text"] == txt and F(out(cid)["value"]) == val, cid
assert err("rtc_h-0015") == "E_SCHEMA"
has("99-162 is `99 + 16.25/32 = 99.5078125`; 99-167 is `99 + 16.75/32 = 99.5234375`")

# Q13.42 auc_h-0001: matched volume per tick
ords = case("auc_h-0001")["inputs"]["orders"]
V = {}
for k in range(999, 1004):
    p = D(k) / 100
    V[p] = min(sum(o_["qty"] for o_ in ords if o_["side"] == "BUY" and D(o_["limit"]) >= p),
               sum(o_["qty"] for o_ in ords if o_["side"] == "SELL" and D(o_["limit"]) <= p))
assert V == {D("9.99"): 150, D("10.00"): 150, D("10.01"): 300, D("10.02"): 100, D("10.03"): 0}
o = out("auc_h-0001")
assert o["price"] == "10.01" and o["volume"] == 300 and o["imbalance"] == -100
assert out("auc_h-0006")["price"] == "10.02" and out("auc_h-0009")["price"] == "10.01" and out("auc_h-0006")["volume"] == out("auc_h-0009")["volume"] == 150
has("uncrosses at 10.01 for 300 shares with an imbalance of -100")

# Q13.43 fxv_h
assert (D("1.0855") - D("1.0851")) / D("0.0001") == 4 and (D("1.0852") - D("1.0851")) / D("0.0001") == 1
assert out("fxv_h-0003")["outcome"] == "LL_PRICE" and out("fxv_h-0004") ["outcome"] == "FILL" and out("fxv_h-0004")["price"] == "1.0852"
has("`LL_PRICE`, no price (`fxv_h-0003`)")

# Q13.44 fut_h-0011: ZN tick 1/64, tick value 15.625
o = out("fut_h-0011")
ticks = (F("110.546875") - F("110.5")) / F(1, 64)
assert ticks == 3 and F(1, 64) * 1000 == F("15.625")
assert o["pnl"] == {"M": "-143.625", "N": "-3", "P": "134.625"} and o["fees"] == {"M": "3", "N": "3", "P": "6"}
assert 3 * 3 * F("15.625") - 6 == F("134.625") and -3 * 3 * F("15.625") - 3 == F("-143.625")
assert sum(F(v) for v in o["pnl"].values()) == -12
has("`3 x 3 x 15.625 - 6 = 134.625`")

# Q13.45 rule_h
assert err("rule_h-0016") == "E_INPUT" and err("rule_h-0012") == "E_LIMIT"
assert 0.3 / 0.2 == 1.4999999999999998 and out("rule_h-0003")["quantity_b"] == 2
assert len(json.loads((GOLD / "rule_h.json").read_text(encoding="utf-8"))["cases"]) == 40
has("`0.3 / 0.2` is 1.4999999999999998 in binary64")

# Q13.46 workload R (benchmarks/results/h9/README.md): recorded figures only
H9 = (Path(__file__).resolve().parents[3] / "benchmarks" / "results" / "h9" / "README.md").read_text(encoding="utf-8")
for s in ("0 failed of 31,287", "**9,223**", "about 58 levels", "Per level that is about 40 ns"):
    assert s in H9, s
has("C++ BTC/USD p99 9,223 ns against a 500 ns target")
has("R2 not obtained: the second recording attempt needed one unbroken 6-hour session, and all 30 sessions on 2026-11-19 and 2026-11-20 ended before hour 6")

# Q13.47 pt_h-0003
o = out("pt_h-0003")
interest = D("9909.69") * D("0.0365") / 365
assert interest == D("0.990969") and interest.quantize(D("0.01")) == D("0.99") == D(o["financing"])
assert o["market"] == "-3" and o["total"] == "-2.01" and o["cash_close"] == "9910.68" and o["nav_close"] == "10012.68"
has("`9909.69 x 0.0365 / 365 = 0.990969`, posted as 0.99")

print(f"v13: {checks} strings checked")
