"""Sanity band checks on real curves. Neutral tooling: comparisons against tools/workflows/sanity_bands.json only."""
import json
from pathlib import Path

from common import years, zero_rate

BANDS = json.loads((Path(__file__).with_name("sanity_bands.json")).read_text(encoding="utf-8"))


def fmt(x):
    return f"{x:.6g}"


def check_fixings(report, name, series, redact=False):
    """series: [(date, rate)] oldest first. redact keeps values out of the report, for sources not cleared for redistribution."""
    b = BANDS["fixing"]
    date, rate = series[-1]
    report.check(f"{name} level", "fail", b["level_min"] <= rate <= b["level_max"], f"{date}: " + ("value withheld" if redact else fmt(rate)))
    if len(series) > 1:
        ch = abs(rate - series[-2][1])
        report.check(f"{name} day change", "fail", ch <= b["day_change_fail"], ("value withheld" if redact else f"{fmt(ch)}") + f" vs {b['day_change_fail']}")
        report.check(f"{name} day change (warn)", "warn", ch <= b["day_change_warn"], ("value withheld" if redact else f"{fmt(ch)}") + f" vs {b['day_change_warn']}")


def check_quotes(report, name, quotes, previous=None):
    """quotes, previous: [{"tenor", "rate"}] in tenor order."""
    b = BANDS["par_quotes"]
    out = [q for q in quotes if not b["level_min"] <= q["rate"] <= b["level_max"]]
    report.check(f"{name} quote levels", "fail", not out, f"outside band: {[q['tenor'] for q in out] or 'none'}")
    gaps = [(a["tenor"], c["tenor"]) for a, c in zip(quotes, quotes[1:]) if abs(c["rate"] - a["rate"]) > b["adjacent_tenor_gap_warn"]]
    report.check(f"{name} adjacent tenor gaps", "warn", not gaps, f"{gaps or 'none'}")
    if previous:
        prev = {q["tenor"]: q["rate"] for q in previous}
        moves = {q["tenor"]: abs(q["rate"] - prev[q["tenor"]]) for q in quotes if q["tenor"] in prev}
        worst = max(moves.items(), key=lambda kv: kv[1]) if moves else ("-", 0.0)
        report.check(f"{name} day change", "fail", worst[1] <= b["day_change_fail"], f"largest {worst[0]} {fmt(worst[1])}")
        report.check(f"{name} day change (warn)", "warn", worst[1] <= b["day_change_warn"], f"largest {worst[0]} {fmt(worst[1])}")


def check_curve(report, name, as_of, pillars):
    """pillars: [{"date", "discount_factor"}]. Returns rows (date, t, df, zero, forward to next) for the report."""
    b = BANDS["curve"]
    rows, prev = [], (0.0, 1.0)
    for p in pillars:
        t, df = years(p["date"], as_of), p["discount_factor"]
        z = zero_rate(df, t)
        fwd = zero_rate(df / prev[1], t - prev[0]) if t > prev[0] else float("nan")
        rows.append((p["date"], t, df, z, fwd))
        prev = (t, df)
    dfs = [r[2] for r in rows]
    report.check(f"{name} discount factors in band", "fail", all(b["df_min"] < d <= b["df_max"] for d in dfs),
                 f"min {fmt(min(dfs))}, max {fmt(max(dfs))}")
    rises = [r[0] for r, q in zip(rows, rows[1:]) if q[2] > r[2] + b["df_increase_tolerance"]]
    # A rising discount factor means a negative forward: possible, so warn only.
    report.check(f"{name} discount factors non-increasing", "warn", not rises, f"rises after {rises or 'none'}")
    zs, fs = [r[3] for r in rows], [r[4] for r in rows]
    report.check(f"{name} zero rates in band", "fail", all(b["zero_min"] <= z <= b["zero_max"] for z in zs),
                 f"min {fmt(min(zs))}, max {fmt(max(zs))}")
    report.check(f"{name} forwards in band", "fail", all(b["forward_min"] <= f <= b["forward_max"] for f in fs),
                 f"min {fmt(min(fs))}, max {fmt(max(fs))}")
    return rows


def check_front_end(report, name, fixing, shortest):
    lim = BANDS["front_end"]["fixing_vs_shortest_quote_warn"]
    report.check(f"{name} fixing vs shortest quote", "warn", abs(fixing - shortest) <= lim, f"{fmt(fixing - shortest)} vs ±{lim}")


def check_zero_curve(report, name, points, previous=None, redact=False):
    """points, previous: [(years, continuously compounded zero)]. Same curve bands as check_curve, on zeros,
    plus the par-quote day-change bands applied to zeros at matching maturities. Forwards between points are
    (z2 t2 - z1 t1) / (t2 - t1), a unit change."""
    b, q = BANDS["curve"], BANDS["par_quotes"]

    def show(text):
        return "value withheld" if redact else text

    zs = [z for _, z in points]
    fwds = [(z2 * t2 - z1 * t1) / (t2 - t1) for (t1, z1), (t2, z2) in zip(points, points[1:]) if t2 > t1]
    report.check(f"{name} zero rates in band", "fail", all(b["zero_min"] <= z <= b["zero_max"] for z in zs),
                 show(f"min {fmt(min(zs))}, max {fmt(max(zs))}") + f"; {len(points)} maturities")
    report.check(f"{name} forwards in band", "fail", all(b["forward_min"] <= f <= b["forward_max"] for f in fwds),
                 show(f"min {fmt(min(fwds))}, max {fmt(max(fwds))}") if fwds else "fewer than two maturities")
    if previous:
        prev = dict(previous)
        moves = [abs(z - prev[t]) for t, z in points if t in prev]
        worst = max(moves) if moves else 0.0
        report.check(f"{name} day change", "fail", worst <= q["day_change_fail"], show(f"largest {fmt(worst)}") + f" vs {q['day_change_fail']}")
        report.check(f"{name} day change (warn)", "warn", worst <= q["day_change_warn"], show(f"largest {fmt(worst)}") + f" vs {q['day_change_warn']}")


def check_curve_gap(report, name, a, b, limit, redact=False):
    """Largest gap between two zero curves at shared maturities; a warn-level consistency check."""
    other = dict(b)
    gaps = [abs(z - other[t]) for t, z in a if t in other]
    worst = max(gaps) if gaps else float("nan")
    report.check(name, "warn", bool(gaps) and worst <= limit,
                 ("value withheld" if redact else f"largest {fmt(worst)}") + f" vs {limit}; {len(gaps)} shared maturities")
