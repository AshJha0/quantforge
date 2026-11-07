#!/usr/bin/env python3
"""Workflow (a), plan 11.2.7: end-of-day USD and GBP curves, sanity bands, key-rate risk of a sample swap book.

  python tools/workflows/eod_curves.py [--impl python] [--out reports/workflows] [--trades 50] [--data DIR]

USD: the US Treasury daily par yield curve, bootstrapped by `rates.ois.bootstrap` with SOFR conventions.
     Treasury par yields are not SOFR swap rates, so this is a proxy curve, labelled as such. Free data has no
     SOFR swap quotes. The SOFR fixing is checked against the curve's front end.
GBP: the Bank of England's fitted OIS and nominal government spot curves (boe_curves.py) are the
     reference, with SONIA fixings. All bands run on them, but only pass or fail is published: the curves are
     Bank copyright for internal non-commercial use (terms in boe_curves.py; kept out of the recorder on purpose).
     The library builds no GBP curve of its own, because free data has no SONIA swap quotes.
--data reads saved source files (the same names as the fetch) instead of fetching, for tests and reruns.

Exit status: 0 all fail-level checks passed, 1 otherwise.
"""
import argparse
import csv
import datetime as dt
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import sanity  # noqa: E402
import boe_curves  # noqa: E402
from sample_book import book, digest  # noqa: E402

UST_TENORS = {"1 Mo": "1M", "2 Mo": "2M", "3 Mo": "3M", "4 Mo": "4M", "6 Mo": "6M", "1 Yr": "1Y", "2 Yr": "2Y",
              "3 Yr": "3Y", "5 Yr": "5Y", "7 Yr": "7Y", "10 Yr": "10Y", "20 Yr": "20Y", "30 Yr": "30Y"}
CURVE_LABEL = "USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve."


def load(name, url, data_dir):
    if data_dir:
        return (Path(data_dir) / name).read_bytes()
    return c.fetch(url)


def treasury(raw):
    """Rows newest first as published: [(iso date, [{"tenor", "rate"}])]"""
    out = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        d = dt.datetime.strptime(row["Date"], "%m/%d/%Y").date().isoformat()
        quotes = [{"tenor": t, "rate": float(row[k]) / 100} for k, t in UST_TENORS.items() if row.get(k, "").strip()]
        out.append((d, quotes))
    return sorted(out)


def sofr(raw):
    return sorted((r["effectiveDate"], r["percentRate"] / 100) for r in json.loads(raw)["refRates"])


def sonia(raw):
    rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    next(rows)
    return sorted((dt.datetime.strptime(r[0], "%d %b %Y").date().isoformat(), float(r[1]) / 100) for r in rows if len(r) > 1 and r[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", default="python")
    ap.add_argument("--out", default=str(c.ROOT / "reports" / "workflows"))
    ap.add_argument("--trades", type=int, default=50)
    ap.add_argument("--data")
    a = ap.parse_args()
    year = dt.date.today().year
    ust = treasury(load("us-treasury-par-yields.csv", c.source_url("us-treasury-par-yields", year), a.data))
    sf = sofr(load("nyfed-sofr.json", c.source_url("nyfed-sofr", year), a.data))
    so = sonia(load("boe-sonia.csv", c.source_url("boe-sonia", year), a.data))
    as_of, quotes = ust[-1]
    prev_quotes = ust[-2][1] if len(ust) > 1 else None
    r = c.Report("EOD curves", as_of, a.out)
    r.data.update({"usd_quotes": quotes, "curve_label": CURVE_LABEL, "impl": a.impl})

    # ---- USD curve ----
    r.h("USD")
    r.p(f"{CURVE_LABEL} As of {as_of}, {len(quotes)} tenors. Implementation: {a.impl}.")
    sanity.check_quotes(r, "USD par quotes", quotes, prev_quotes)
    sanity.check_fixings(r, "SOFR", sf)
    boot = c.batch([c.case("usd", "rates.ois.bootstrap", {"convention": "SOFR", "as_of": as_of, "quotes": quotes,
                                                           "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"})], a.impl)["usd"]
    r.check("USD bootstrap", "fail", boot["status"] == "ok", boot.get("error", {}).get("message", "ok"))
    if boot["status"] == "ok":
        pillars = boot["outputs"]["pillars"]
        rows = sanity.check_curve(r, "USD curve", as_of, pillars)
        sanity.check_front_end(r, "USD", sf[-1][1], quotes[0]["rate"])
        r.data["usd_pillars"] = pillars
        r.table(["Pillar", "t (y)", "DF", "Zero (cc, %)", "Fwd to pillar (%)"],
                [(d, f"{t:.3f}", f"{df:.8f}", f"{z * 100:.4f}", f"{f * 100:.4f}") for d, t, df, z, f in rows])
        key_rate_section(r, as_of, quotes, {"as_of": as_of, "interpolation": "LOG_LINEAR_DF", "pillars": pillars}, a)

    # ---- GBP ----
    r.h("GBP")
    sanity.check_fixings(r, "SONIA", so, redact=True)  # raw SONIA stays local until the Bank answers (sources.json)
    gbp_reference(r, so, a)
    r.data["sonia_latest_date"] = so[-1][0]
    notices = [c.SOURCES[s]["notice"] for s in ("us-treasury-par-yields", "nyfed-sofr", "boe-sonia")] + [boe_curves.NOTICE]
    return r.write(notices)


def gbp_reference(r, so, a):
    """BoE fitted OIS and nominal government spot curves as the GBP reference. Values withheld (boe_curves.py)."""
    gb = sanity.BANDS["gbp_reference"]
    try:
        raw = load("boe-yield-curves.zip", boe_curves.URL, a.data)
        ois, nom = boe_curves.spot_curves(raw, "ois"), boe_curves.spot_curves(raw, "nominal")
    except (OSError, KeyError, ValueError, StopIteration) as e:
        r.check("GBP BoE curves read", "fail", False, str(e)[:120])
        return
    r.check("GBP BoE curves read", "fail", bool(ois and nom), f"OIS {len(ois)} days, nominal {len(nom)} days")
    if not (ois and nom):
        return
    sanity.check_zero_curve(r, "GBP BoE OIS spot", ois[-1][1], ois[-2][1] if len(ois) > 1 else None, redact=True)
    sanity.check_zero_curve(r, "GBP BoE nominal spot", nom[-1][1], nom[-2][1] if len(nom) > 1 else None, redact=True)
    sanity.check_curve_gap(r, "GBP OIS vs nominal gap", ois[-1][1], nom[-1][1], gb["ois_vs_nominal_warn"], redact=True)
    front = ois[-1][1][0]
    r.check("GBP SONIA vs shortest OIS spot", "warn", abs(so[-1][1] - front[1]) <= gb["sonia_vs_ois_front_warn"],
            f"value withheld vs {gb['sonia_vs_ois_front_warn']}; OIS shortest maturity {front[0]}y")
    r.check("GBP BoE curve date vs SONIA", "warn", ois[-1][0] >= so[-1][0], f"BoE {ois[-1][0]}, SONIA {so[-1][0]}")
    r.p(f"Reference: Bank of England fitted OIS spot curve ({len(ois[-1][1])} maturities) and nominal government spot curve "
        f"({len(nom[-1][1])} maturities) for {ois[-1][0]}, from the latest yield curve data zip, with SONIA fixings to {so[-1][0]}. "
        "Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, "
        "and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. "
        "The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.")
    r.data["gbp_reference"] = {"boe_date": ois[-1][0], "ois_maturities": len(ois[-1][1]), "nominal_maturities": len(nom[-1][1])}


def key_rate_section(r, as_of, quotes, curve, a):
    trades = book(a.trades)
    tenors = sorted({t["tenor"] for t in trades})
    probes = c.batch([c.case(f"par-{t}", "rates.ois.pv", {"curve": curve, "trade": {"convention": "SOFR", "tenor": t,
                      "fixed_rate": 0.0, "notional": 1.0, "side": "PAY"}}) for t in tenors], a.impl)
    par = {}
    for t in tenors:
        res = probes[f"par-{t}"]
        r.check(f"USD par probe {t}", "fail", res["status"] == "ok", res.get("error", {}).get("message", "ok"))
        if res["status"] == "ok":
            par[t] = res["outputs"]["par_rate"]
    cases = [c.case(t["id"], "risk.ois.dv01", {"as_of": as_of, "quotes": quotes, "interpolation": "LOG_LINEAR_DF",
             "trade": {"convention": "SOFR", "tenor": t["tenor"], "fixed_rate": round(par[t["tenor"]] + t["offset"], 8),
                       "notional": t["notional"], "side": t["side"]}}) for t in trades if t["tenor"] in par]
    res = c.batch(cases, a.impl)
    bad = [k for k, v in res.items() if v["status"] != "ok"]
    r.check("USD key-rate risk", "fail", not bad, f"{len(res) - len(bad)}/{len(res)} trades ok; failed {bad[:5] or 'none'}")
    ok = [v["outputs"] for v in res.values() if v["status"] == "ok"]
    if not ok:
        return
    kr = [sum(o["key_rate"][i] for o in ok) for i in range(len(quotes))]
    total = sum(o["dv01"] for o in ok)
    # Cross-check: key rates should add up close to the parallel DV01; reported, not enforced, until R2 sets the threshold.
    r.check("USD sum of key rates vs parallel DV01", "warn", abs(sum(kr) - total) <= 0.01 * max(1.0, abs(total)),
            f"sum {sum(kr):,.2f} vs DV01 {total:,.2f}")
    r.h("USD key-rate risk, sample book", 3)
    r.p(f"{len(ok)} synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 "
        f"`{digest(trades)[:16]}`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.")
    r.table(["Key rate", "DV01 (USD/bp)"], [(q["tenor"], f"{v:,.2f}") for q, v in zip(quotes, kr)] + [("Parallel", f"{total:,.2f}")])
    r.data.update({"book_sha256": digest(trades), "key_rate": dict(zip([q["tenor"] for q in quotes], kr)), "dv01": total})


if __name__ == "__main__":
    sys.exit(main())
