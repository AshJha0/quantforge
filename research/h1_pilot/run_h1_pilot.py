"""H-1 PILOT (stage H, owner decision 2026-11-18): run the H-1 methods end to end on the partial
recorded Kraken L2 days 2026-11-12..18. Pilot; partial days; crypto venue; not equities or rates;
no conclusions. These days are EXCLUDED from any later H-1 or H-18 study.

Reads the recorder output read-only and writes aggregates only (no individual order, trade or book
row). Stdlib only. Run from the repository root in WSL:

    flock ~/qf-wsl.lock python3 -I research/h1_pilot/run_h1_pilot.py DATA_DIR OUT_JSON

Methods (protocol draft research/H1-crypto-study-protocol.md on branch h-research, reduced):
(a) concave impact proxy E[dm|V] = c sign(V)|V|^delta per bucket size, grid NLS on delta with
    closed-form c, SE by day-block bootstrap (100 draws, seed 20261118);
(b) walk-the-book cost of immediate orders at one-minute snapshots (recorded depth only, overflow
    counted, not extrapolated);
(c) passive fill-probability bounds at the touch (lower: trade-through or traded qty at the level
    exceeding the displayed queue at placement; upper: any trade at or through the level);
(d) arrival-price TCA of simulated TWAP buy orders run through exec.sim.lit.run, decomposed with
    exec.tca.shortfall (Perold, HR-8).
"""

import bisect
import gzip
import hashlib
import json
import zlib
import math
import os
import random
import statistics
import sys
from datetime import datetime, timezone
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python"))
sys.path.insert(0, HERE)
from quantforge_core import lit_matching  # noqa: E402
import stage_h_execution_5202d98f as ex  # noqa: E402  (stage-h commit 5202d98f, unchanged code)

LABEL = "pilot; partial days; crypto venue; not equities or rates; no conclusions"
SEED = 20261118
SYMBOLS = ("BTC-USD", "ETH-USD")
NOTIONALS = (1e3, 1e4, 1e5, 1e6)
BUCKETS = (10, 60, 300)
HORIZONS = (1, 10, 60)
GAP_S = 600


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def load(sym_dir):
    """Return snapshots [(t, bids, asks)], trades [(t, +1/-1, price, qty)], file stats."""
    snaps, trades, files, bad = [], [], [], []
    for name in sorted(os.listdir(sym_dir)):
        path = os.path.join(sym_dir, name)
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()
        files.append((name, h))
        try:
            with gzip.open(path, "rt") as f:
                for line in f:
                    r = json.loads(line)
                    t = ts(r["t"])
                    if r["k"] == "book":
                        b = [(float(p), float(q)) for p, q in r["bids"]]
                        a = [(float(p), float(q)) for p, q in r["asks"]]
                        if b and a:
                            snaps.append((t, b, a))
                    elif r["k"] == "trade":
                        for d in r["d"]:
                            sd = 1 if d["side"] == "buy" else -1
                            trades.append((t, sd, float(d["price"]), float(d["qty"])))
        except (EOFError, OSError, ValueError, zlib.error):
            bad.append(name)  # truncated file still being written: rows read so far are kept
    snaps.sort(key=lambda x: x[0])
    trades.sort(key=lambda x: x[0])
    return snaps, trades, files, bad


def day_of(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def gaps(snaps, files):
    hours = {}
    for name, _ in files:
        hours.setdefault(name[:8], 0)
        hours[name[:8]] += 1
    out, times = {}, [s[0] for s in snaps]
    for i in range(1, len(times)):
        if times[i] - times[i - 1] > GAP_S:
            d = day_of(times[i - 1])
            out[d] = out.get(d, 0) + 1
    return {d: {"hour_files": n, "missing_hours": 24 - n, "gaps_over_10min": out.get(
        f"{d[:4]}-{d[4:6]}-{d[6:]}", 0)} for d, n in sorted(hours.items())}


def mid(s):
    return (s[1][0][0] + s[2][0][0]) / 2


def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(p * len(xs)))]


# (a) impact proxy --------------------------------------------------------------------------
def buckets(snaps, trades, b):
    """Per bucket: (day, normalised signed volume, dm bps); empty-trade buckets dropped."""
    st = [s[0] for s in snaps]
    vol, last = {}, {}
    for t, sd, p, qty in trades:
        k = int(t // b)
        vol[k] = vol.get(k, 0.0) + sd * qty * p
    for i, s in enumerate(snaps):
        last[int(s[0] // b)] = i
    rows = []
    for k, v in vol.items():
        if k in last and (k - 1) in last:
            m1, m0 = mid(snaps[last[k]]), mid(snaps[last[k - 1]])
            rows.append((day_of(k * b), v, (m1 - m0) / m0 * 1e4))
    by_day = {}
    for d, v, _ in rows:
        by_day.setdefault(d, []).append(abs(v))
    mean = {d: statistics.fmean(x) for d, x in by_day.items()}
    return [(d, v / mean[d], dm) for d, v, dm in rows if mean[d] > 0]


def fit(rows):
    floor = q([abs(v) for _, v, _ in rows], 0.05)
    xs = [(math.copysign(abs(v), v), dm) for _, v, dm in rows if abs(v) > floor]
    def sse(d):
        f = [math.copysign(abs(v) ** d, v) for v, _ in xs]
        c = sum(a * y for a, (_, y) in zip(f, xs)) / sum(a * a for a in f)
        return sum((y - c * a) ** 2 for a, (_, y) in zip(f, xs)), d, c

    lo, hi, g = 0.05, 2.0, (math.sqrt(5) - 1) / 2  # golden-section search on delta
    for _ in range(30):
        a, b = hi - g * (hi - lo), lo + g * (hi - lo)
        if sse(a)[0] < sse(b)[0]:
            hi = b
        else:
            lo = a
    best = sse((lo + hi) / 2)
    return best[1], best[2], len(xs)


def impact(snaps, trades):
    out = {}
    rng = random.Random(SEED)
    for b in BUCKETS:
        rows = buckets(snaps, trades, b)
        days = sorted({d for d, _, _ in rows})
        delta, c, n = fit(rows)
        per = {d: [r for r in rows if r[0] == d] for d in days}
        boot = []
        for _ in range(100):
            pick = [rng.choice(days) for _ in days]
            boot.append(fit([r for d in pick for r in per[d]])[0])
        se = statistics.stdev(boot)
        out[f"{b}s"] = {"delta": delta, "c_bps": c, "n_buckets": n, "days": len(days),
                        "se_day_bootstrap": se,
                        "ci95_percentile": [q(boot, 0.025), q(boot, 0.975)]}
    return out


# (b) walk the book -------------------------------------------------------------------------
def walk(levels, notional, m, buy):
    left, cost = notional, 0.0
    for p, qty in levels:
        take = min(left, p * qty)
        cost += take * ((p - m) if buy else (m - p)) / m
        left -= take
        if left <= 1e-9:
            return cost / notional * 1e4
    return None


def minute_snaps(snaps):
    out, seen = [], set()
    for s in snaps:
        k = int(s[0] // 60)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def walk_curves(mins):
    res = {}
    for side, buy in (("buy", True), ("sell", False)):
        for n in NOTIONALS:
            vals, over = [], 0
            for s in mins:
                c = walk(s[2] if buy else s[1], n, mid(s), buy)
                if c is None:
                    over += 1
                else:
                    vals.append(c)
            res[f"{side}_{int(n)}"] = {"median_bps": q(vals, 0.5), "p90_bps": q(vals, 0.9),
                                       "p99_bps": q(vals, 0.99), "snapshots": len(vals),
                                       "beyond_recorded_depth": over}
    return res


# (c) fill bounds ---------------------------------------------------------------------------
def fill_bounds(mins, trades):
    tt = [t[0] for t in trades]
    res = {}
    for h in HORIZONS:
        lo = up = n = 0
        for t0, bids, _ in mins:
            p, queue = bids[0]
            i, traded, fl, fu = bisect.bisect_right(tt, t0), 0.0, False, False
            while i < len(trades) and trades[i][0] <= t0 + h:
                _, sd, tp, tq = trades[i]
                if sd < 0 and tp <= p:  # seller-initiated trade at or through our bid
                    fu = True
                    if tp < p:
                        fl = True
                    else:
                        traded += tq
                        if traded > queue:
                            fl = True
                i += 1
            n += 1
            lo += fl
            up += fu
        res[f"{h}s"] = {"lower": lo / n, "upper": up / n, "placements": n}
    return res


# (d) TCA via the lit engine ----------------------------------------------------------------
def dstr(x, places):
    return format(Decimal(repr(x)).quantize(Decimal(1).scaleb(-places)), "f")


def child_fill(snap, usd, pdec):
    """Seed the engine with the recorded asks as resting orders, send a MARKET buy."""
    ev, m = [], mid(snap)
    for j, (p, qty) in enumerate(snap[2]):
        ev.append({"op": "NEW", "id": f"a{j}", "trader": "book", "side": "SELL",
                   "type": "LIMIT", "price": dstr(p, pdec), "qty": dstr(qty, 8)})
    qty = dstr(usd / m, 8)
    if Decimal(qty) <= 0:
        return [], 0.0
    ev.append({"op": "NEW", "id": "c", "trader": "algo", "side": "BUY", "type": "MARKET",
               "qty": qty})
    out = lit_matching.run(dstr(10 ** -pdec, pdec), "0.00000001", ev,
                           {"taker_fee": "0", "maker_rebate": "0"})
    return [(float(f["qty"]), float(f["price"])) for f in out["fills"]], float(qty)


def tca(snaps, pdec):
    rng = random.Random(SEED)
    st = [s[0] for s in snaps]
    days = sorted({day_of(t) for t in st})
    res = {}
    for size in (1e4, 1e5, 1e6):
        rows = []
        for d in days:
            idx = [i for i, t in enumerate(st) if day_of(t) == d]
            t0 = st[rng.choice(idx)]
            arr = snaps[bisect.bisect_left(st, t0)]
            fills, want, skipped = [], 0.0, 0
            for c in range(10):  # TWAP: 10 children, one per minute
                j = bisect.bisect_left(st, t0 + 60 * c)
                if j >= len(snaps) or st[j] - (t0 + 60 * c) > 5:
                    skipped += 1
                    continue  # no snapshot within 5 s: child skipped (counted as unfilled)
                f, w = child_fill(snaps[j], size / 10, pdec)
                fills += f
                want += w
            end = snaps[min(len(snaps) - 1, bisect.bisect_left(st, t0 + 600))]
            # parent quantity = what the children asked for, plus the skipped children's share
            qty_total = want + skipped * size / 10 / mid(arr)
            # engine fills never exceed the child quantity in Decimal; guard float summing
            qty_total = max(qty_total, sum(f[0] for f in fills))
            r = ex.tca_shortfall("BUY", mid(arr), mid(arr), mid(end), qty_total,
                                 [f for f in fills if f[0] > 0], 0.0, None)
            filled = sum(f[0] for f in fills)
            rows.append((r["total_bps"], r["execution"] / (qty_total * mid(arr)) * 1e4,
                         filled / qty_total))
        res[f"twap_buy_{int(size)}"] = {
            "orders": len(rows), "total_bps_mean": statistics.fmean(r[0] for r in rows),
            "total_bps_median": q([r[0] for r in rows], 0.5),
            "execution_bps_mean": statistics.fmean(r[1] for r in rows),
            "fill_ratio_min": min(r[2] for r in rows)}
    return res


def main(data_dir, out_path):
    report = {"label": LABEL, "excluded_from_later_studies": True,
              "dates": "2026-11-12..2026-11-18 (partial)", "seed": SEED, "symbols": {}}
    for sym in SYMBOLS:
        snaps, trades, files, bad = load(os.path.join(data_dir, sym))
        mins = minute_snaps(snaps)
        pdec = 1 if sym == "BTC-USD" else 2  # Kraken price precision for these pairs
        report["symbols"][sym] = {
            "files": len(files), "files_truncated_while_recording": bad,
            "files_sha256_of_list": hashlib.sha256(
                "".join(n + h for n, h in files).encode()).hexdigest(),
            "snapshots": len(snaps), "trade_prints": len(trades),
            "recorded_depth_levels": len(snaps[0][1]),
            "coverage_per_day": gaps(snaps, files),
            "a_impact_proxy": impact(snaps, trades),
            "b_walk_the_book": walk_curves(mins),
            "c_fill_bounds_touch_bid": fill_bounds(mins, trades),
            "d_tca_twap_lit_engine": tca(snaps, pdec),
        }
        print(sym, "done", file=sys.stderr)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
