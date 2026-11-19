"""Daily curve run (specifications/12-platform/daily-curve-run.md, rulings KR-90 onwards).

Standard library only. Every number that describes the curve comes from a CLI operation: the business-day
calendar (`core.calendar.is_business_day`), the par bond prices (`bond.price.from_yield`), the Nelson-Siegel fit
(`bond.fit.nelson_siegel`) and the fitted yields (`bond.yield.from_price`). This file arranges the calls, reads
the published files, changes units (percent, basis points, price to continuous zero rate), takes the RMSE and
largest absolute value of differences, writes rows and checks them. It holds no fitting or pricing logic.
"""
import calendar as _calendar
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GENESIS = "0" * 64
KINDS = ("GENESIS", "DAY", "GAP", "CONSISTENCY")
FINAL = ("ok", "fit_failed", "holdout_blocked")  # a DAY row with one of these settles its date
NON_FINAL = ("stale_input", "fetch_failed")  # retried by a later run until the late window closes
STATUSES = FINAL + NON_FINAL
GAP_CAUSES = ("late_window", "not_published")  # KR-203: why a date was closed without a fit
REBUILD_TOL = 1e-6  # KR-207: a refit on another platform may differ in the last bits of exp, log and pow
CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")

Runner = Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]]


class CurveError(Exception):
    """A refusal: the run writes nothing."""


def load_config(path: Any = None) -> dict[str, Any]:
    return json.loads(Path(path or HERE / "config.json").read_text(encoding="utf-8"))


def config_sha(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


# ------------------------------------------------------------------ numbers and canonical rows


def fstr(x: float) -> str:
    """A binary64 value as the shortest decimal string that reads back to the same bits."""
    if not math.isfinite(x):
        raise CurveError(f"non-finite value {x!r}")
    s = repr(float(x))
    return "0.0" if s == "-0.0" else s


def canonical(record: dict[str, Any]) -> bytes:
    """Row bytes without `hash`: keys sorted, `,` and `:` separators, ASCII. Every scalar is a string except
    `seq` (the HR-45 rule of paper-trading.md, reused as the paper ledger does)."""

    def check(v: Any, path: str) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                check(x, f"{path}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                check(x, f"{path}[{i}]")
        elif not isinstance(v, str) and not (type(v) is int and path == ".seq"):
            raise CurveError(f"{path} must be a string (only seq is an integer)")

    body = {k: v for k, v in record.items() if k != "hash"}
    check(body, "")
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def row_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(record)).hexdigest()


def make_row(seq: int, ts: str, kind: str, cfg: dict[str, Any], body: dict[str, Any], prev: str) -> dict[str, Any]:
    rec = {"seq": seq, "ts": ts, "kind": kind, "format": cfg["format"], "label": cfg["label"], "body": body,
           "prev": prev}
    rec["hash"] = row_hash(rec)
    return rec


def line(rec: dict[str, Any]) -> str:
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def read_ledger(path: Any) -> str:
    """The ledger file as text, byte for byte: ASCII, no newline translation (KR-208). A missing file is ""."""
    p = Path(path)
    return p.read_bytes().decode("ascii") if p.exists() else ""


def lines_of(text: str) -> list[str]:
    """The lines of a ledger: each ends with one line feed and the file holds nothing else (KR-208)."""
    if text == "":
        return []
    if not text.endswith("\n"):
        raise ValueError("the ledger does not end with a line feed")
    return text[:-1].split("\n")


def parse(text: str) -> list[dict[str, Any]]:
    rows = []
    for n, ln in enumerate(lines_of(text)):
        rec = json.loads(ln, object_pairs_hook=_no_duplicates)
        if not isinstance(rec, dict):
            raise ValueError(f"line {n} is not an object")
        rows.append(rec)
    return rows


# ------------------------------------------------------------------ dates and the library calendar


def iso(d: dt.date) -> str:
    return d.isoformat()


def day(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


INSTANT = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z", re.ASCII)


def instant(s: str) -> dt.datetime:
    """A row time: exactly `YYYY-MM-DDTHH:MM:SSZ`, UTC. Anything else is a ValueError."""
    m = INSTANT.fullmatch(s) if isinstance(s, str) else None
    if m is None:
        raise ValueError(f"{s!r} is not YYYY-MM-DDTHH:MM:SSZ")
    y, mo, d, h, mi, sec = (int(x) for x in m.groups())
    return dt.datetime(y, mo, d, h, mi, sec, tzinfo=dt.timezone.utc)


def stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_months(d: dt.date, months: int) -> dt.date:
    """Calendar month arithmetic with the day clamped to the month's end (29 February plus 12 months is 28
    February). Date arithmetic only: no business-day rule, as the bond object (ruling D13)."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(d.day, _calendar.monthrange(y, m)[1]))


def case(cid: str, op: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": "1.0", "case_id": cid, "operation": op, "inputs": inputs}


def outputs(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for cid, r in results.items():
        if r.get("status") != "ok":
            raise CurveError(f"CLI case {cid} failed: {json.dumps(r.get('error'))}")
        out[cid] = r["outputs"]
    return out


def _time(s: str) -> dt.time:
    h, m, sec = (int(x) for x in s.split(":"))
    return dt.time(h, m, sec)


class Calendar:
    """Business days from `core.calendar.is_business_day` (the library calendar decides, KR-93)."""

    def __init__(self, runner: Runner, name: str):
        self.runner, self.name, self.known = runner, name, {}  # type: ignore[var-annotated]

    def load(self, start: dt.date, end: dt.date) -> None:
        need = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
        need = [d for d in need if d not in self.known]
        if need:
            out = outputs(self.runner([case(iso(d), "core.calendar.is_business_day",
                                             {"calendar": self.name, "date": iso(d)}) for d in need]))
            for d in need:
                self.known[d] = bool(out[iso(d)]["is_business_day"])

    def is_open(self, d: dt.date) -> bool:
        self.load(d, d)
        return bool(self.known[d])

    def next_open(self, d: dt.date) -> dt.date:
        n = d + dt.timedelta(days=1)
        while True:
            if n not in self.known:
                self.load(n, n + dt.timedelta(days=12))
            if self.known[n]:
                return n
            n += dt.timedelta(days=1)

    def open_between(self, after: dt.date, upto: dt.date) -> list[dt.date]:
        """Business days d with after < d <= upto."""
        if upto <= after:
            return []
        self.load(after, upto)
        return [d for d in (after + dt.timedelta(days=i) for i in range(1, (upto - after).days + 1)) if self.known[d]]


def due_instant(d: dt.date, cfg: dict[str, Any]) -> dt.datetime:
    """When business day d's par curve is expected to be published (KR-94)."""
    return dt.datetime.combine(d, _time(cfg["due_after_utc"]), dt.timezone.utc)


def cutoff(d: dt.date, cal: Calendar, cfg: dict[str, Any]) -> dt.datetime:
    """First late instant for business day d: the cut-off time on the next business day (KR-95 as amended by KR-111:
    on time strictly before it)."""
    return dt.datetime.combine(cal.next_open(d), _time(cfg["on_time_cutoff_utc"]), dt.timezone.utc)


def late_limit(d: dt.date, cal: Calendar, cfg: dict[str, Any]) -> dt.datetime:
    """After this instant business day d can only be a GAP (KR-96): the cut-off time on the business day that
    is `late_max_business_days` after d's next business day."""
    n = cal.next_open(d)
    for _ in range(int(cfg["late_max_business_days"])):
        n = cal.next_open(n)
    return dt.datetime.combine(n, _time(cfg["on_time_cutoff_utc"]), dt.timezone.utc)


def latest_due(now: dt.datetime, cal: Calendar, cfg: dict[str, Any]) -> dt.date:
    d = now.date()
    while not (cal.is_open(d) and due_instant(d, cfg) <= now):
        d -= dt.timedelta(days=1)
    return d


# ------------------------------------------------------------------ holdout guard (plan 14.10 rule 6)


def holdout_windows() -> dict[str, tuple[str, str]]:
    import sys
    sys.path.insert(0, str(ROOT / "research"))
    import holdout_scan  # type: ignore[import-not-found]
    return dict(holdout_scan.windows())


def holdout_hit(date: str, windows: dict[str, tuple[str, str]]) -> list[str]:
    return sorted(k for k, (lo, hi) in windows.items() if lo <= date <= hi)


# ------------------------------------------------------------------ published files


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NotTheFile(Exception):
    """The bytes fetched are not the Treasury CSV (an error page served with HTTP 200, a cut-off download).
    Recorded as `fetch_failed` and retried (KR-204); it says nothing about the day's yields."""


def treasury_rows(data: bytes) -> dict[str, dict[str, str]]:
    """Rows of a Treasury daily par yield CSV keyed by ISO date. Dates are MM/DD/YYYY in the file. A file with
    no `Date` column, or with a date that does not read, raises NotTheFile."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise NotTheFile("not UTF-8 text") from e
    reader = csv.DictReader(io.StringIO(text))
    if "Date" not in [(f or "").strip() for f in (reader.fieldnames or [])]:
        raise NotTheFile("no Date column in the first line")
    out = {}
    for r in reader:
        raw = next(((v or "").strip() for k, v in r.items() if k and k.strip() == "Date"), "")
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", raw)
        if not m:
            raise NotTheFile(f"date {raw[:20]!r} is not MM/DD/YYYY")
        try:
            dt.date(int(m[3]), int(m[1]), int(m[2]))
        except ValueError as e:
            raise NotTheFile(f"date {raw!r} is not a calendar date") from e
        out[f"{m[3]}-{m[1]}-{m[2]}"] = {k.strip(): (v or "").strip() for k, v in r.items() if k}
    return out


def gsw_rows(data: bytes) -> dict[str, dict[str, str]]:
    """Rows of the Fed's feds200628.csv keyed by date. The file starts with notes; the header line starts
    with `Date,`."""
    lines = data.decode("utf-8-sig").splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("Date,"):
            return {r["Date"].strip(): {k.strip(): (v or "").strip() for k, v in r.items() if k}
                    for r in csv.DictReader(io.StringIO("\n".join(lines[i:])))}
    raise CurveError("GSW file: no header line starting with 'Date,'")


def input_line(row: dict[str, str], cfg: dict[str, Any]) -> str:
    """The day's configured values as one text line, hashed so a copy of the file can be checked later."""
    return ",".join(f"{t['field']}={row.get(t['field'], '')}" for t in cfg["tenors"])


# ------------------------------------------------------------------ the fit (KR-97 to KR-100)


class FitFailed(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code, self.detail = code, detail


def _ok(results: dict[str, dict[str, Any]], cid: str) -> dict[str, Any]:
    r = results[cid]
    if r.get("status") != "ok":
        err = r.get("error") or {}
        raise FitFailed(str(err.get("code") or "E_UNKNOWN"), f"{cid}: {err.get('message', '')}")
    out: dict[str, Any] = r["outputs"]
    return out


def par_bonds(d: dt.date, row: dict[str, str], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """One semi-annual par bond per configured tenor: coupon the published par yield, maturity d plus the
    tenor, settlement d."""
    freq = int(cfg["fit"]["frequency"])
    out = []
    for t in cfg["tenors"]:
        v = row.get(t["field"], "")
        if v in ("", "N/A"):
            raise FitFailed("E_MISSING_TENOR", f"no value for {t['field']}")
        try:
            y = float(Decimal(v) / 100)
        except Exception as e:  # noqa: BLE001 - any unreadable cell is a recorded failure
            raise FitFailed("E_PARSE", f"{t['field']}={v!r}") from e
        out.append({"field": t["field"], "par_pct": v, "yield": y,
                    "bond": {"maturity": iso(add_months(d, int(t["months"]))), "coupon": y, "frequency": freq}})
    return out


def fit_day(d: dt.date, row: dict[str, str], cfg: dict[str, Any], runner: Runner) -> dict[str, Any]:
    """Fit body for one day, or raise FitFailed with the first error code. A non-finite number anywhere is
    `E_NONFINITE`: a recorded failed fit, not a refused run (a refusal would repeat on every later run)."""
    try:
        return _fit_day(d, row, cfg, runner)
    except CurveError as e:
        raise FitFailed("E_NONFINITE", str(e)) from e
    except (ZeroDivisionError, OverflowError, ValueError) as e:
        raise FitFailed("E_NONFINITE", f"{type(e).__name__}: {e}") from e


def _fit_day(d: dt.date, row: dict[str, str], cfg: dict[str, Any], runner: Runner) -> dict[str, Any]:
    settle = iso(d)
    bonds = par_bonds(d, row, cfg)
    r = runner([case(b["field"], "bond.price.from_yield", {"bond": b["bond"], "settlement": settle,
                                                            "yield": b["yield"]}) for b in bonds])
    for b in bonds:
        o = _ok(r, b["field"])
        b["dirty"], b["accrued"] = o["dirty"], o["accrued"]
        # KR-98: weight 1/D^2 (D the modified duration from the same operation), so the price objective is close
        # to the sum of squared yield errors; unweighted, the bills' tiny price errors hide large yield errors.
        b["weight"] = 1.0 / (o["modified_duration"] * o["modified_duration"])
    fit_bonds = [{**b["bond"], "dirty_price": b["dirty"]} for b in bonds]
    w = [b["weight"] for b in bonds]
    taus = cfg["fit"]["tau_grid"]
    r = runner([case(f"tau={t}", cfg["fit"]["operation"], {"settlement": settle, "tau": float(t), "bonds": fit_bonds,
                                                         "weights": w}) for t in taus])
    tried, failed = [], []
    for t in taus:
        res = r[f"tau={t}"]
        if res.get("status") != "ok":
            failed.append({"tau": t, "code": str((res.get("error") or {}).get("code") or "E_UNKNOWN")})
            continue
        resid = res["outputs"]["residuals"]
        sse = math.fsum(wi * x * x for wi, x in zip(w, resid))  # the operation's own objective
        if not math.isfinite(sse):
            failed.append({"tau": t, "code": "E_NONFINITE"})
            continue
        tried.append((sse, float(t), t, res["outputs"]))
    if not tried:
        raise FitFailed(failed[0]["code"], f"every tau failed ({len(failed)})")
    sse, _, tau, best = min(tried, key=lambda x: (x[0], x[1]))  # ties: the smaller tau
    # Zero rates read through the same operation: zero-coupon probe bonds with weight 0 do not move the fit
    # (bonds.md: "a bond with weight 0 shows its richness"); their residual is model minus the dummy 100.
    probes = [{"maturity": iso(add_months(d, 12 * int(n))), "coupon": 0.0, "frequency": 1, "dirty_price": 100.0}
              for n in cfg["fit"]["probe_years"]]
    weights = w + [0.0] * len(probes)
    o = _ok(runner([case("probe", cfg["fit"]["operation"], {"settlement": settle, "tau": float(tau),
                                                            "bonds": fit_bonds + probes, "weights": weights})]), "probe")
    if o["betas"] != best["betas"] or o["residuals"][:len(fit_bonds)] != best["residuals"]:
        raise FitFailed("E_PROBE_MISMATCH", "weight-0 probes changed the fit")
    zeros = {}
    for n, p, res in zip(cfg["fit"]["probe_years"], probes, o["residuals"][len(fit_bonds):]):
        t = (day(p["maturity"]) - d).days / 365  # curve time of bonds.md
        model = 100.0 + res
        if not model > 0:
            raise FitFailed("E_DOMAIN", f"probe {n}y price {model!r}")
        zeros[f"{int(n):02d}"] = fstr(-math.log(model / 100.0) / t * 100)  # continuous, percent
    # Fitted yields: each par bond's model price back to a yield.
    r = runner([case(b["field"], "bond.yield.from_price",
                     {"bond": b["bond"], "settlement": settle, "clean_price": b["dirty"] + res - b["accrued"]})
                for b, res in zip(bonds, best["residuals"])])
    errors = {}
    for b in bonds:
        y = _ok(r, b["field"])["yield"]
        errors[b["field"]] = fstr((y - b["yield"]) * 1e4)
    rmse, mx, at = diagnostics(errors)
    flag = cfg["fit_flag_bp"]
    return {
        "operation": cfg["fit"]["operation"], "tau": tau, "betas": [fstr(x) for x in best["betas"]],
        "objective": fstr(sse), "weighting": cfg["fit"]["weighting"], "taus_ok": str(len(tried)), "taus_failed": failed,
        "errors_bp": errors, "rmse_bp": rmse, "max_abs_bp": mx, "max_at": at,
        "within_fit_flag": "true" if float(rmse) <= float(flag["rmse"]) and float(mx) <= float(flag["max_abs"]) else "false",
        "zeros_pct": zeros,
    }


def diagnostics(errors: dict[str, str]) -> tuple[str, str, str]:
    """RMSE, largest absolute value and where it is, of a set of differences in bp (strings), in key order."""
    keys = list(errors)
    vals = [float(errors[k]) for k in keys]
    rmse = math.sqrt(math.fsum(v * v for v in vals) / len(vals))
    i = max(range(len(vals)), key=lambda j: (abs(vals[j]), -j))
    return fstr(rmse), fstr(abs(vals[i])), keys[i]


def within(rmse: str, mx: str, tol: dict[str, str]) -> bool:
    return float(rmse) <= float(tol["rmse"]) and float(mx) <= float(tol["max_abs"])


# ------------------------------------------------------------------ consistency with the Fed's curve (KR-101)


def consistency_body(day_row: dict[str, Any], gsw: dict[str, dict[str, str]], gsw_meta: dict[str, str],
                     cfg: dict[str, Any]) -> dict[str, Any] | None:
    """CONSISTENCY body for an ok DAY row, or None while the Fed has not yet published that date."""
    b = day_row["body"]
    date = b["date"]
    base = {"date": date, "day_row": day_row["hash"], "label": cfg["consistency_label"], "gsw": gsw_meta,
            "tolerance_bp": cfg["consistency_tolerance_bp"]}
    last = gsw_meta.get("last_date", "")
    row = gsw.get(date)
    if row is None:
        waited = (day(gsw_meta["fetched_at"][:10]) - day(date)).days
        if last and last > date:
            return {**base, "status": "unavailable", "reason": "the Fed file has later dates but not this one"}
        if waited > int(cfg["consistency_wait_days"]):
            return {**base, "status": "unavailable", "reason": f"not published within {cfg['consistency_wait_days']} days"}
        return None
    diffs = {}
    for nn, z in b["fit"]["zeros_pct"].items():
        v = row.get(cfg["gsw"]["column"].replace("{nn}", nn), "")
        if v in ("", "NA", "N/A"):
            continue
        diffs[nn] = fstr((float(z) - float(v)) * 100)  # percent to bp
    if not diffs:
        return {**base, "status": "unavailable", "reason": "no published zero yields on this date"}
    rmse, mx, at = diagnostics(diffs)
    status = "within" if within(rmse, mx, cfg["consistency_tolerance_bp"]) else "outside"
    return {**base, "status": status, "diffs_bp": diffs, "rmse_bp": rmse, "max_abs_bp": mx, "max_at": at}


# ------------------------------------------------------------------ one run (KR-102)


Fetcher = Callable[[str], bytes]


def run(cfg: dict[str, Any], runner: Runner, ledger_text: str, now: dt.datetime, fetch: Fetcher,
        commit: str = "unknown", contract: str = "unknown", impl: str = "python",
        windows: dict[str, tuple[str, str]] | None = None) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Rows due at `now`, appended to the ledger. Returns (new ledger text, new rows, notes). `fetch(url)`
    returns the bytes at a URL or raises. Nothing is written by this function."""
    windows = holdout_windows() if windows is None else windows
    rows = parse(ledger_text) if ledger_text.strip() else []
    if rows:
        v = verify(ledger_text, cfg, runner, windows)
        if not v["ok"]:
            raise CurveError(f"the ledger does not verify before the run: seq {v['first_bad_seq']} {v['reason']} {v['detail']}")
    cal = Calendar(runner, cfg["calendar"])
    ts = stamp(now)
    new: list[dict[str, Any]] = []
    notes: list[str] = []
    run_info = {"commit": commit, "contract_version": contract, "impl": impl}

    def add(kind: str, body: dict[str, Any]) -> None:
        prev = (new or rows)[-1]["hash"] if (new or rows) else GENESIS
        new.append(make_row(len(rows) + len(new), ts, kind, cfg, body, prev))

    if rows and now < instant(rows[-1]["ts"]):
        raise CurveError(f"the clock ({ts}) is before the last row ({rows[-1]['ts']}); nothing written")
    if not rows:
        add("GENESIS", {"config": cfg, "config_sha256": config_sha(cfg)})
    # KR-203: dates are handled strictly in order and a run stops at the first date it cannot settle, so at
    # most one date (the last one with a row) is ever unsettled and no later date gets a row before it.
    settled = {r["body"]["date"] for r in rows if r["kind"] == "GAP" or
               (r["kind"] == "DAY" and r["body"]["status"] in FINAL)}
    dated = [r["body"]["date"] for r in rows if r["kind"] in ("DAY", "GAP")]
    target = latest_due(now, cal, cfg)
    if dated:
        last = day(dated[-1])
        due = ([] if dated[-1] in settled else [last]) + cal.open_between(last, target)
    else:
        due = [target]  # the first run starts at the latest due day; nothing is back-filled
    files: dict[int, tuple[bytes | None, str]] = {}

    def treasury(year: int) -> tuple[bytes | None, str]:
        if year not in files:
            url = cfg["treasury"]["url"].replace("{year}", str(year))
            try:
                files[year] = (fetch(url), url)
            except Exception as e:  # noqa: BLE001 - recorded as fetch_failed
                notes.append(f"treasury {year}: fetch failed: {e}")
                files[year] = (None, url)
        return files[year]

    def file_input(data: bytes, url: str, latest: str) -> dict[str, str]:
        return {"url": url, "sha256": sha256(data), "bytes": str(len(data)), "latest_date": latest,
                "attribution": cfg["treasury"]["attribution"]}

    for d in due:
        ds = iso(d)
        hit = holdout_hit(ds, windows)
        if hit:
            add("DAY", {"date": ds, "status": "holdout_blocked", "studies": hit, "run": run_info,
                        "timing": "on_time" if now < cutoff(d, cal, cfg) else "late"})
            notes.append(f"{ds}: holdout_blocked ({', '.join(hit)}); no input read")
            continue
        if now > late_limit(d, cal, cfg):
            add("GAP", {"date": ds, "cause": "late_window", "reason": "no settled row before the late window closed",
                        "run": run_info})
            notes.append(f"{ds}: GAP (late window closed)")
            continue
        timing = "on_time" if now < cutoff(d, cal, cfg) else "late"
        data, url = treasury(d.year)
        base = {"date": ds, "timing": timing, "run": run_info}
        if data is None:
            add("DAY", {**base, "status": "fetch_failed", "input": {"url": url}})
            notes.append(f"{ds}: fetch_failed; stopping here, a later run tries again")
            break
        try:
            table = treasury_rows(data)
        except NotTheFile as e:  # KR-204: retried, never a settled failed fit
            add("DAY", {**base, "status": "fetch_failed", "error": {"code": "E_NOT_THE_FILE", "detail": str(e)},
                        "input": {"url": url, "sha256": sha256(data), "bytes": str(len(data))}})
            notes.append(f"{ds}: fetch_failed (the download is not the Treasury CSV: {e}); stopping here")
            break
        latest = max(table) if table else ""
        inp = file_input(data, url, latest)
        if ds not in table:
            # Treasury moved past this date without publishing it: closed now, with the evidence (KR-203).
            evidence = inp if latest > ds else None
            for year in range(d.year + 1, now.year + 1):  # a year end: the later date is in the next file
                if evidence is not None:
                    break
                data2, url2 = treasury(year)
                try:
                    table2 = treasury_rows(data2) if data2 is not None else {}
                except NotTheFile:
                    table2 = {}
                if data2 is not None and table2:
                    evidence = file_input(data2, url2, max(table2))
            if evidence is not None:
                add("GAP", {"date": ds, "cause": "not_published", "input": evidence, "run": run_info,
                            "reason": "the Treasury file holds a later date and not this one"})
                notes.append(f"{ds}: GAP (not published; the file is at {evidence['latest_date']})")
                continue
            add("DAY", {**base, "status": "stale_input", "input": inp})
            notes.append(f"{ds}: stale_input (latest in file {latest or 'none'}); stopping here, a later run tries again")
            break
        inp["row_date"] = ds
        inp["row_sha256"] = sha256(input_line(table[ds], cfg).encode("ascii"))
        try:
            fit = fit_day(d, table[ds], cfg, runner)
        except FitFailed as e:
            add("DAY", {**base, "status": "fit_failed", "error": {"code": e.code, "detail": e.detail}, "input": inp})
            notes.append(f"{ds}: fit_failed {e.code}")
            continue
        add("DAY", {**base, "status": "ok", "input": inp, "fit": fit})
        notes.append(f"{ds}: ok {timing} tau {fit['tau']} rmse {float(fit['rmse_bp']):.2f} bp max "
                     f"{float(fit['max_abs_bp']):.2f} bp at {fit['max_at']}")

    # Consistency rows for ok days not yet compared (the Fed posts weekly, days behind).
    done = {r["body"]["day_row"] for r in rows + new if r["kind"] == "CONSISTENCY"}
    pending = [r for r in rows + new if r["kind"] == "DAY" and r["body"]["status"] == "ok" and r["hash"] not in done]
    if pending:
        try:
            gdata = fetch(cfg["gsw"]["url"])
            gsw = gsw_rows(gdata)
            meta = {"url": cfg["gsw"]["url"], "sha256": sha256(gdata), "bytes": str(len(gdata)),
                    "last_date": max(gsw) if gsw else "", "fetched_at": ts, "attribution": cfg["gsw"]["attribution"]}
        except Exception as e:  # noqa: BLE001 - no row; the next run tries again
            notes.append(f"gsw: fetch or parse failed, consistency left pending: {e}")
        else:
            for r in pending:
                body = consistency_body(r, gsw, meta, cfg)
                if body is None:
                    notes.append(f"{r['body']['date']}: consistency pending (Fed file ends {meta['last_date']})")
                    continue
                add("CONSISTENCY", body)
                notes.append(f"{r['body']['date']}: consistency {body['status']}"
                             + (f" rmse {float(body['rmse_bp']):.2f} bp" if "rmse_bp" in body else ""))
    out = ledger_text + "".join(line(r) + "\n" for r in new)
    return out, new, notes


# ------------------------------------------------------------------ verification (KR-103)


def bad(seq: int, reason: str, detail: str = "") -> dict[str, Any]:
    return {"ok": False, "first_bad_seq": seq, "reason": reason, "detail": detail}


def _check_rows(rows: list[dict[str, Any]], cfg: dict[str, Any], cal: Calendar | None,
                windows: dict[str, tuple[str, str]]) -> dict[str, Any] | None:
    """The row rules after the chain and the configuration: the first fault, or None.

    Dates (KR-203): the rows walk the business days strictly in order. At any point at most one date is
    unsettled, and it is the last one with a row; until it is settled no other date may have a row. A settled
    date never gets another row, and (with the calendar) the next date is the next business day, so none is
    skipped. This is the rule the writer follows, which is why any ledger the writer can reach verifies."""
    open_date = ""  # the one unsettled date, or ""
    last_settled = ""
    last_ts = rows[0]["ts"]
    instant(last_ts)
    by_hash = {r["hash"]: r for r in rows}
    compared: set[str] = set()
    first_dated = True
    for r in rows[1:]:
        n, b, kind = r["seq"], r["body"], r["kind"]
        if instant(r["ts"]) < instant(last_ts):
            return bad(n, "TS", f"{r['ts']} is before the previous row's {last_ts}")
        last_ts = r["ts"]
        if kind in ("DAY", "GAP"):
            ds = b.get("date", "")
            d = day(ds)
            if open_date:
                if ds != open_date:
                    return bad(n, "ORDER", f"a row for {ds} while {open_date} is unsettled")
            elif ds == last_settled:
                return bad(n, "DUP", f"{ds} is already settled")
            elif ds < last_settled:
                return bad(n, "ORDER", f"{ds} after {last_settled}")
            elif cal is not None and last_settled and d != cal.next_open(day(last_settled)):
                return bad(n, "MISSING", f"business day {iso(cal.next_open(day(last_settled)))} has no row")
            status = b.get("status") if kind == "DAY" else "gap"
            if kind == "DAY" and status not in STATUSES:
                return bad(n, "STATUS", str(status))
            hit = holdout_hit(ds, windows)
            if status == "holdout_blocked":
                if not hit or b.get("studies") != hit or "input" in b or "fit" in b:
                    return bad(n, "HOLDOUT", f"{ds}: a holdout_blocked row must name the windows and read nothing")
            elif hit:
                return bad(n, "HOLDOUT", f"{ds} is inside the holdout window of {', '.join(hit)}")
            t = instant(r["ts"])
            if first_dated and (n != 1 or kind != "DAY" or r["ts"] != rows[0]["ts"]):
                return bad(n, "START", "the first dated row is a DAY row written by the run that wrote GENESIS")
            if cal is not None:
                if not cal.is_open(d):
                    return bad(n, "DATE", f"{ds} is not a {cfg['calendar']} business day")
                if t < due_instant(d, cfg):
                    return bad(n, "EARLY", f"{ds} written at {r['ts']}, before it was due")
                if first_dated and d != latest_due(t, cal, cfg):
                    return bad(n, "START", f"the ledger starts at {ds}, not at the latest day due at {r['ts']}")
                if kind == "DAY" and b.get("timing") != ("on_time" if t < cutoff(d, cal, cfg) else "late"):
                    return bad(n, "TIMING", f"{ds} labelled {b.get('timing')}")
                if kind == "DAY" and status != "holdout_blocked" and t > late_limit(d, cal, cfg):
                    return bad(n, "TIMING", f"{ds}: a DAY row after the late window must be a GAP")
            first_dated = False
            if kind == "GAP":
                cause = b.get("cause")
                if cause == "not_published":
                    if not str((b.get("input") or {}).get("latest_date", "")) > ds:
                        return bad(n, "GAPRULE", f"{ds}: a not_published gap needs a file dated after it")
                elif cause == "late_window":
                    if cal is not None and not t > late_limit(d, cal, cfg):
                        return bad(n, "GAPRULE", f"{ds}: gap declared inside the late window")
                else:
                    return bad(n, "GAPRULE", f"{ds}: unknown gap cause {cause!r}")
            if status == "fit_failed":
                e = b.get("error") or {}
                if not CODE.match(str(e.get("code", ""))) or "fit" in b:
                    return bad(n, "FAILCODE", f"{ds}: a failed fit needs an error code and no fit")
            if status in NON_FINAL and "fit" in b:
                return bad(n, "FAILCODE", f"{ds}: a {status} row has no fit")
            if status == "stale_input" and not str((b.get("input") or {}).get("latest_date", "")) < ds:
                return bad(n, "STALE", f"{ds}: a stale_input row needs a file that ends before {ds}")
            if status == "ok":
                inp, fit = b.get("input") or {}, b.get("fit") or {}
                if inp.get("row_date") != ds or not inp.get("latest_date", "") >= ds or "error" in b:
                    return bad(n, "STALE", f"{ds}: the fit did not use a row dated {ds}")
                try:
                    rmse, mx, at = diagnostics(fit["errors_bp"])
                    flag = "true" if within(rmse, mx, cfg["fit_flag_bp"]) else "false"
                except (KeyError, ValueError, ZeroDivisionError) as e:
                    return bad(n, "DIAG", str(e))
                if (rmse, mx, at, flag) != (fit.get("rmse_bp"), fit.get("max_abs_bp"), fit.get("max_at"),
                                            fit.get("within_fit_flag")):
                    return bad(n, "DIAG", f"{ds}: RMSE, max or flag do not follow from errors_bp")
            if kind == "GAP" or status in FINAL:
                last_settled, open_date = ds, ""
            else:
                open_date = ds
        else:  # CONSISTENCY
            ref = by_hash.get(b.get("day_row", ""))
            if ref is None or ref["seq"] >= n or ref["kind"] != "DAY" or ref["body"].get("status") != "ok" \
                    or ref["body"]["date"] != b.get("date"):
                return bad(n, "REF", "a consistency row must name an earlier ok DAY row of its date")
            if b["day_row"] in compared:
                return bad(n, "DUP", "a second consistency row for one DAY row")
            compared.add(b["day_row"])
            if b.get("label") != cfg["consistency_label"] or b.get("tolerance_bp") != cfg["consistency_tolerance_bp"]:
                return bad(n, "LABEL", "consistency label or tolerance differs from the configuration")
            if b.get("status") in ("within", "outside"):
                rmse, mx, at = diagnostics(b["diffs_bp"])
                st = "within" if within(rmse, mx, cfg["consistency_tolerance_bp"]) else "outside"
                if (rmse, mx, at, st) != (b.get("rmse_bp"), b.get("max_abs_bp"), b.get("max_at"), b["status"]):
                    return bad(n, "VERDICT", f"{b['date']}: the verdict does not follow from diffs_bp")
            elif b.get("status") != "unavailable":
                return bad(n, "STATUS", str(b.get("status")))
    return None


def verify(text: str, cfg: dict[str, Any] | None = None, runner: Runner | None = None,
           windows: dict[str, tuple[str, str]] | None = None) -> dict[str, Any]:
    """Every check, in order; stops at the first failure and never repairs. Without a runner the calendar
    checks (business days, timing, missing days) are skipped and the result says so."""
    cfg = cfg or load_config()
    windows = holdout_windows() if windows is None else windows
    cal = Calendar(runner, cfg["calendar"]) if runner else None
    prev = GENESIS
    rows: list[dict[str, Any]] = []
    try:
        lines = lines_of(text)
    except ValueError as e:
        return bad(text.count("\n"), "BYTES", str(e))
    for n, ln in enumerate(lines):
        try:
            rec = json.loads(ln, object_pairs_hook=_no_duplicates)
            if not isinstance(rec, dict):
                return bad(n, "PARSE")
            computed = row_hash(rec)
            stored = rec["hash"]
        except (ValueError, KeyError, CurveError) as e:
            return bad(n, "PARSE", str(e))
        if rec.get("seq") != n:
            return bad(n, "SEQ")
        if computed != stored:
            return bad(n, "HASH")
        if ln != line(rec):  # KR-208: one serialisation only, so the file's bytes follow from its rows
            return bad(n, "BYTES", "the line is not the canonical serialisation of its row")
        if rec.get("prev") != prev:
            return bad(n, "LINK")
        if rec.get("format") != cfg["format"]:
            return bad(n, "FORMAT")
        if rec.get("label") != cfg["label"]:
            return bad(n, "LABEL")
        if rec.get("kind") not in KINDS or (rec["kind"] == "GENESIS") != (n == 0):
            return bad(n, "KIND")
        prev = stored
        rows.append(rec)
    if not rows:
        return bad(0, "EMPTY")
    g = rows[0]["body"]
    if g.get("config") != cfg or g.get("config_sha256") != config_sha(cfg):
        return bad(0, "CONFIG", "the genesis configuration differs from config.json")
    try:
        fault = _check_rows(rows, cfg, cal, windows)
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        return bad(len(rows), "SCHEMA", f"{type(e).__name__}: {e}")
    if fault:
        return fault
    last_date = next((r["body"]["date"] for r in reversed(rows) if r["kind"] in ("DAY", "GAP")), "")
    counts = {s: 0 for s in (*STATUSES, "gap", "late", "within", "outside", "unavailable")}
    for r in rows:
        if r["kind"] == "DAY":
            counts[r["body"]["status"]] += 1
            counts["late"] += r["body"].get("timing") == "late"
        elif r["kind"] == "GAP":
            counts["gap"] += 1
        elif r["kind"] == "CONSISTENCY":
            counts[r["body"]["status"]] += 1
    return {"ok": True, "records": len(rows), "head": rows[-1]["hash"], "last_date": last_date or None,
            "calendar_checked": cal is not None, "counts": counts}


def check_anchors(text: str, anchors: list[dict[str, Any]]) -> dict[str, Any]:
    """Each anchor (`count`, `head`) must match line count-1 of the ledger (KR-104)."""
    rows = parse(text)
    for a in anchors:
        c = int(a.get("count", 0))
        if c < 1 or c > len(rows) or rows[c - 1]["hash"] != a.get("head"):
            return bad(c - 1, "ANCHOR", f"anchor {a.get('name', '?')} does not match the ledger")
    return {"ok": True, "anchors": len(anchors)}


def make_anchor(text: str, cfg: dict[str, Any]) -> dict[str, Any]:
    rows = parse(text)
    return {"count": str(len(rows)), "head": rows[-1]["hash"], "format": cfg["format"], "config_sha256": config_sha(cfg)}


def summary(text: str, v: dict[str, Any]) -> dict[str, Any]:
    """Latest settled fit for the dashboard and gallery stub (site_page.py)."""
    rows = parse(text)
    last_ok = next((r for r in reversed(rows) if r["kind"] == "DAY" and r["body"]["status"] == "ok"), None)
    cons = {r["body"]["day_row"]: r["body"] for r in rows if r["kind"] == "CONSISTENCY"}
    out: dict[str, Any] = {"ok": v["ok"], "records": len(rows), "head": rows[-1]["hash"], "counts": v.get("counts"),
                           "label": rows[0]["label"], "latest": None}
    if last_ok:
        b = last_ok["body"]
        c = cons.get(last_ok["hash"])
        out["latest"] = {"date": b["date"], "timing": b["timing"], "tau": b["fit"]["tau"], "betas": b["fit"]["betas"],
                         "rmse_bp": b["fit"]["rmse_bp"], "max_abs_bp": b["fit"]["max_abs_bp"],
                         "zeros_pct": b["fit"]["zeros_pct"], "row": last_ok["hash"],
                         "consistency": ({k: c[k] for k in ("status", "label") if k in c} | (
                             {"rmse_bp": c["rmse_bp"], "max_abs_bp": c["max_abs_bp"]} if "rmse_bp" in c else {}))
                         if c else {"status": "pending"}}
    return out
