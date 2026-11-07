#!/usr/bin/env python3
"""Workflow (b): Treasury and gilt rich/cheap screen (specifications/04-pricing/workflow-b-rich-cheap.md, R2).

  python tools/workflows/rich_cheap.py [--impl python] [--date YYYY-MM-DD] [--data DIR] [--history DIR] [--out reports/workflows]

DATA SOURCES ARE BLOCKED FOR AUTOMATED USE (terms checked 2026-11-07), so this job never fetches. It reads price files
a person has downloaded and placed in --data, in a neutral CSV layout, one file per market and day:
    DIR/ust-YYYY-MM-DD.csv and DIR/gilt-YYYY-MM-DD.csv
    columns: id,type,coupon,maturity,clean_price      (type: fixed | bill | frn | tips | linker | strip | callable | rump)
Without files it writes a dated BLOCKED report saying why, and exits 0, so the daily job stays green and visible.

Terms record:
  - TreasuryDirect FedInvest prices (https://www.treasurydirect.gov/GA-FI/FedInvest/selectSecurityPriceDate):
    robots.txt has "User-agent: * / Disallow: /", so every path is closed to automated clients. terms.htm s.2 allows viewing,
    downloading and printing "for non-commercial personal use only", and public display, reproduction or distribution needs
    "the express prior written consent of Fiscal Service". It adds: "You should not assume anything on this site is
    necessarily in the public domain." So: no automated fetch, and no raw prices in published reports.
  - UK DMO gilt reference prices (https://www.dmo.gov.uk/data/gilt-market/gilt-reference-prices/): automated requests
    get an anti-bot challenge (ShieldSquare, validate.perfdrive.com), so the terms page could not be read by a script.
    robots.txt is 404. That counts as refusing automated use. A person must read the terms in a browser before any use.
  - Until a source is cleared, reports publish residuals and ranks only, never prices (spec: "Raw prices appear in the
    report only if the source's terms allow it").

  - Fiscal Data "Treasury Securities Auctions Data" (https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query),
    used only to mark on-the-run issues: the API documentation says the data "is offered free, without restriction", and the API
    "does not require a user account or registration". fiscaldata.treasury.gov/robots.txt allows all; the API host has none.
    Fetched once per run. TreasuryDirect's own auction service is not used (its robots.txt disallows all).

Calculation, all through the CLI, with no pricing in this file:
  1. Settlement T+1: core.calendar.add_business_days (USGS, GBLO).
  2. bond.yield.from_price on market clean -> market yield and dirty; errors are dropped and listed.
  3. bond.price.from_yield at the market yield -> modified duration D_mod; weights w = 1 / D_mod^2 (ruling R2-A5). US Treasury
     on-the-run and first off-the-run issues per auction tenor (2, 3, 5, 7, 10, 20, 30 years) get weight 0 but are still reported
     (R2-A6); no gilt is excluded. bond.fit.nelson_siegel on dirty prices, tau 2.5 -> betas, residuals (model minus market dirty).
  4. model_clean = market_clean + residual; bond.yield.from_price at model_clean -> model yield.
  5. yield_residual_bp = (market yield - model yield) x 10,000: positive is cheap. z-score against the bond's trailing 60
     published days in --history (earlier JSON reports), or null with fewer than 20 days.
  6. Rank within maturity buckets 1-3, 3-7, 7-15, 15+ years; mark the 5 cheapest and 5 richest per market.
Gilts inside their ex-dividend period (7 GBLO business days before the next coupon, edge register E9) are dropped.
"""
import argparse
import csv
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402

LABEL = "Fitted-curve residuals from end-of-day reference prices; not executable prices; tradability not established."
TAU = 2.5
AUCTIONS = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
            "?fields=cusip,security_type,original_security_term,auction_date,floating_rate,inflation_index_security"
            "&filter=security_type:in:(Note,Bond),auction_date:gte:{since},auction_date:lte:{until}&sort=-auction_date&page[size]=1000")
TENORS = ["2-Year", "3-Year", "5-Year", "7-Year", "10-Year", "20-Year", "30-Year"]
MARKETS = {"ust": {"name": "US Treasury", "calendar": "USGS"}, "gilt": {"name": "UK gilts", "calendar": "GBLO"}}
BUCKETS = [(1, 3), (3, 7), (7, 15), (15, 1000)]
BLOCKED = [
    ("US Treasury: TreasuryDirect FedInvest", "robots.txt disallows all automated clients; terms allow non-commercial personal use only; "
     "redistribution needs Fiscal Service's written consent"),
    ("UK gilts: DMO gilt reference prices", "automated requests get an anti-bot challenge; terms not readable by a script; robots.txt 404"),
]


def add_months(d, m):
    import calendar
    y, mo = divmod(d.month - 1 + m, 12)
    return dt.date(d.year + y, mo + 1, min(d.day, calendar.monthrange(d.year + y, mo + 1)[1]))


def next_coupon(maturity, after):
    """Semi-annual coupon dates step back from maturity in 6-month steps: the first one after `after` (date arithmetic only)."""
    d, k = maturity, 0
    while add_months(maturity, -6 * (k + 1)) > after:
        k += 1
        d = add_months(maturity, -6 * k)
    return d


def benchmark_issues(date, auctions_file=None):
    """{cusip: label} for the on-the-run and first off-the-run issue of each auction tenor, from auctions up to `date`."""
    if auctions_file:
        rows = json.loads(Path(auctions_file).read_text(encoding="utf-8"))["data"]
    else:
        since = (dt.date.fromisoformat(date) - dt.timedelta(days=3 * 366)).isoformat()
        rows = json.loads(c.fetch(AUCTIONS.format(since=since, until=date)))["data"]
    out = {}
    for tenor in TENORS:
        seen = []
        for r in sorted(rows, key=lambda r: r["auction_date"], reverse=True):
            if r["original_security_term"] != tenor or r.get("floating_rate") == "Yes" or r.get("inflation_index_security") == "Yes":
                continue
            if r["cusip"] not in seen:
                seen.append(r["cusip"])
            if len(seen) == 2:
                break
        for cusip, label in zip(seen, ("on-the-run", "first off-the-run")):
            out[cusip] = f"{tenor} {label}"
    return out


def read_prices(path):
    with open(path, encoding="utf-8", newline="") as f:
        return [{"id": r["id"], "type": r["type"].strip().lower(), "coupon": float(r["coupon"]),
                 "maturity": dt.date.fromisoformat(r["maturity"]), "clean": float(r["clean_price"])} for r in csv.DictReader(f)]


def history(hist_dir, market, before):
    """{id: [yield_residual_bp, ...]} from earlier reports, oldest first, up to 60 published days."""
    out = {}
    if not hist_dir:
        return out
    files = sorted(Path(hist_dir).glob(f"*/rich-cheap-{market}.json"))
    files = [f for f in files if f.parent.name < before][-60:]
    for f in files:
        for b in json.loads(f.read_text(encoding="utf-8")).get("bonds", []):
            out.setdefault(b["id"], []).append(b["yield_residual_bp"])
    return out


def screen(market, rows, date, impl, hist, benchmarks=None):
    m = MARKETS[market]
    dropped, keep = [], []
    settle = c.batch([c.case("s", "core.calendar.add_business_days", {"calendar": m["calendar"], "date": date, "days": 1})], impl)["s"]
    if settle["status"] != "ok":
        raise SystemExit(f"settlement date failed: {settle}")
    settlement = settle["outputs"]["date"]
    sdate = dt.date.fromisoformat(settlement)
    for r in rows:
        if r["type"] != "fixed":
            dropped.append((r["id"], f"type {r['type']}"))
        elif (r["maturity"] - sdate).days < 365:
            dropped.append((r["id"], "under 1 year to maturity"))
        else:
            keep.append(r)
    if market == "gilt" and keep:
        cases = [c.case(r["id"], "core.calendar.add_business_days", {"calendar": "GBLO", "date": next_coupon(r["maturity"], sdate).isoformat(), "days": -7})
                 for r in keep]
        exd = c.batch(cases, impl)
        still = []
        for r in keep:
            x = exd[r["id"]]
            if x["status"] == "ok" and dt.date.fromisoformat(x["outputs"]["date"]) <= sdate < next_coupon(r["maturity"], sdate):
                dropped.append((r["id"], "ex-dividend period (E9)"))
            else:
                still.append(r)
        keep = still

    def bond(r):
        return {"maturity": r["maturity"].isoformat(), "coupon": r["coupon"], "frequency": 2}

    ys = c.batch([c.case(r["id"], "bond.yield.from_price", {"bond": bond(r), "settlement": settlement, "clean_price": r["clean"]}) for r in keep], impl)
    good = []
    for r in keep:
        y = ys[r["id"]]
        if y["status"] != "ok":
            dropped.append((r["id"], f"bond.yield.from_price: {y['error']['code']}"))
        else:
            good.append({**r, "yield": y["outputs"]["yield"], "dirty": y["outputs"]["dirty"]})
    result = {"market": market, "settlement": settlement, "universe": len(good), "dropped": dropped, "bonds": []}
    if len(good) < 3:
        return result
    dur = c.batch([c.case(r["id"], "bond.price.from_yield", {"bond": bond(r), "settlement": settlement, "yield": r["yield"]}) for r in good], impl)
    benchmarks = benchmarks or {}
    weights = []
    for r in good:
        r["benchmark"] = benchmarks.get(r["id"], "") if market == "ust" else ""
        d = dur[r["id"]]
        r["d_mod"] = d["outputs"]["modified_duration"] if d["status"] == "ok" else None
        weights.append(0.0 if r["benchmark"] or not r["d_mod"] else 1.0 / r["d_mod"] ** 2)
    result["zero_weight"] = [(r["id"], r["benchmark"]) for r in good if r["benchmark"]]
    fit = c.batch([c.case("fit", "bond.fit.nelson_siegel", {"settlement": settlement, "tau": TAU, "weights": weights,
                   "bonds": [{**bond(r), "dirty_price": r["dirty"]} for r in good]})], impl)["fit"]
    if fit["status"] != "ok":
        result["fit_error"] = fit["error"]
        return result
    res = fit["outputs"]["residuals"]
    for r, e in zip(good, res):
        r["residual"], r["model_clean"] = e, r["clean"] + e
    my = c.batch([c.case(r["id"], "bond.yield.from_price", {"bond": bond(r), "settlement": settlement, "clean_price": r["model_clean"]}) for r in good], impl)
    for r in good:
        x = my[r["id"]]
        if x["status"] != "ok":
            dropped.append((r["id"], f"model yield: {x['error']['code']}"))
            continue
        ybp = (r["yield"] - x["outputs"]["yield"]) * 1e4
        past = hist.get(r["id"], [])
        z = (ybp - statistics.mean(past)) / statistics.stdev(past) if len(past) >= 20 and statistics.stdev(past) > 0 else None
        years = (r["maturity"] - sdate).days / 365.0
        bucket = next(f"{lo}-{hi}" if hi < 1000 else f"{lo}+" for lo, hi in BUCKETS if lo <= years < hi)
        result["bonds"].append({"id": r["id"], "coupon": r["coupon"], "maturity": r["maturity"].isoformat(), "years": years, "bucket": bucket,
                                "market_clean": r["clean"], "model_clean": r["model_clean"], "price_residual": r["residual"],
                                "yield_residual_bp": ybp, "zscore": z, "d_mod": r["d_mod"], "benchmark": r["benchmark"]})
    fitted = [e for r, e in zip(good, res) if not r["benchmark"]] or res
    rms = (sum(e * e for e in fitted) / len(fitted)) ** 0.5
    result["fit"] = {"betas": fit["outputs"]["betas"], "tau": TAU, "rms": rms, "worst": max(abs(e) for e in fitted), "weights": "1/D_mod^2"}
    order = sorted(result["bonds"], key=lambda b: b["yield_residual_bp"])
    rich, cheap = {b["id"] for b in order[:5]}, {b["id"] for b in order[-5:]}
    for bkt in {b["bucket"] for b in result["bonds"]}:
        inb = sorted((b for b in result["bonds"] if b["bucket"] == bkt), key=lambda b: -b["yield_residual_bp"])
        for i, b in enumerate(inb, 1):
            b["rank"] = i
    for b in result["bonds"]:
        b["mark"] = "cheapest 5" if b["id"] in cheap else "richest 5" if b["id"] in rich else ""
    return result


def write_market(market, date, res, out, impl, publish_prices):
    r = c.Report(f"Rich cheap {market}", date, out)
    m = MARKETS[market]
    r.p(f"**{LABEL}** {m['name']}, prices of {date}, settlement {res.get('settlement')}. Universe {res['universe']} bonds; "
        f"{len(res['dropped'])} dropped. Implementation {impl}. Raw prices are {'shown' if publish_prices else 'withheld (source terms not cleared)'}.")
    r.check("no CLI error", "fail", "fit_error" not in res, str(res.get("fit_error", "ok")))
    r.check("at least 20 bonds", "fail", res["universe"] >= 20, f"{res['universe']} bonds")
    if "fit" in res:
        f = res["fit"]
        r.check("fit RMS below 0.25 per 100", "warn", f["rms"] < 0.25, f"RMS {f['rms']:.4f}, worst {f['worst']:.4f}")
        r.h("Fit")
        if res.get("zero_weight"):
            r.p(f"Weight 0 (on-the-run and first off-the-run, reported but not fitted): {', '.join(f'{i} ({lbl})' for i, lbl in res['zero_weight'])}.")
        r.p(f"Weights 1/D_mod² (R2-A5). Nelson-Siegel, tau {f['tau']}: betas {', '.join(f'{b:.6f}' for b in f['betas'])}; RMS {f['rms']:.4f} and worst {f['worst']:.4f} per 100.")
        for bkt in sorted({b["bucket"] for b in res["bonds"]}, key=lambda s: float(s.split("-")[0].rstrip("+"))):
            r.h(f"{bkt} years", 3)
            head = ["Id", "Coupon", "Maturity"] + (["Market clean", "Model clean"] if publish_prices else []) + ["Yield residual (bp)", "z-score", "Rank", ""]
            rows = sorted((b for b in res["bonds"] if b["bucket"] == bkt), key=lambda b: b["rank"])
            r.table(head, [[b["id"], f"{b['coupon'] * 100:.3f}%", b["maturity"]] + ([f"{b['market_clean']:.4f}", f"{b['model_clean']:.4f}"] if publish_prices else [])
                           + [f"{b['yield_residual_bp']:+.1f}", "—" if b["zscore"] is None else f"{b['zscore']:+.2f}", b["rank"],
                              " ".join(x for x in (b["mark"], f"weight 0: {b['benchmark']}" if b["benchmark"] else "") if x)] for b in rows])
    if res["dropped"]:
        r.h("Dropped")
        r.table(["Id", "Reason"], res["dropped"])
    bonds = res["bonds"] if publish_prices else [{k: v for k, v in b.items() if k not in ("market_clean", "model_clean")} for b in res["bonds"]]
    r.data.update({"label": LABEL, "market": market, "settlement": res.get("settlement"), "fit": res.get("fit"), "bonds": bonds, "dropped": res["dropped"]})
    return r.write([])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", default="python")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--data")
    ap.add_argument("--history")
    ap.add_argument("--auctions", help="saved Fiscal Data auctions JSON, instead of fetching (tests, reruns)")
    ap.add_argument("--publish-prices", action="store_true", help="only when the source's terms allow it")
    ap.add_argument("--out", default=str(c.ROOT / "reports" / "workflows"))
    a = ap.parse_args()
    files = {mk: Path(a.data) / f"{mk}-{a.date}.csv" for mk in MARKETS} if a.data else {}
    present = {mk: p for mk, p in files.items() if p.is_file()}
    if not present:
        r = c.Report("Rich cheap", a.date, a.out)
        r.p(f"**BLOCKED: no price data.** {LABEL} Both free sources refuse automated use, so this job does not fetch. "
            "Place downloaded price files in --data to run the screen (layout in `tools/workflows/rich_cheap.py`).")
        r.table(["Source", "Why it is blocked (terms checked 2026-11-07)"], BLOCKED)
        r.check("price data available", "warn", False, "no source cleared for automated use")
        return r.write([])
    rc = 0
    bench = benchmark_issues(a.date, a.auctions) if "ust" in present else {}
    for mk, p in present.items():
        res = screen(mk, read_prices(p), a.date, a.impl, history(a.history, mk, a.date), bench)
        rc |= write_market(mk, a.date, res, a.out, a.impl, a.publish_prices)
    return rc


if __name__ == "__main__":
    sys.exit(main())
