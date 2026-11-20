#!/usr/bin/env python3
"""End-of-day rehearsal (plan item K-6): one recorded date, from the recorder log to the dashboard pages.

  uv run --project python python tools/eod/rehearse.py --date YYYY-MM-DD --source synthetic
  uv run --project python python tools/eod/rehearse.py --date YYYY-MM-DD --source forward-log [--log-ref REF]
  ... [--plant GAP|HOLDOUT|HASH|EXPLAIN|DOMAIN|LABEL|WIDTH] [--out FILE]

Eight steps, E1 to E8, as proposed in specifications/12-platform/soak-eod-capacity.md section 3 (branch
k-w3-spec). Each step appends one checklist line {step, title, status, reason, evidence, seconds}. A failing step
stops the run and the steps after it are recorded as "not run". Exit 0 only when all eight pass; 1 otherwise.
tools/eod/CHECKLIST.md is the human-readable form of the same list.

Everything is a dry run inside a temporary folder: the rehearsal reads the recorder log with `git show` (or builds
a synthetic one), never fetches from a source, never writes to a ledger branch and never starts a workflow. The
output JSON holds hashes, counts and aggregates only, never a recorded row or a recorded value.

`--plant FAULT` injects exactly one fault; the step named beside it must fail:
  GAP (E1) the date's par-yield row removed from the copy of the log; HOLDOUT (E2) the date checked is the last
  day of a prereg holdout window; HASH (E3) one byte of the rebuilt source file changed; EXPLAIN (E4) one explain
  term of the date's paper row off by one cent, chain rebuilt; DOMAIN (E5) a position with a non-finite yield;
  LABEL (E6) the paper row label removed from its page; WIDTH (E7) a 600 px fixed-width element on a page.

Deviations from the proposed spec:
1. E1. The forward log keeps, per source row, the file's sha256 and size and, for public-domain sources, the
   parsed values; for Treasury par yields only five tenors (3 Mo, 2 Yr, 5 Yr, 10 Yr, 30 Yr). The raw file is not
   on the branch, so the source file for E3 is rebuilt in the temporary folder from the recorded values, and E1
   also replays every row's state_sha256 (as tools/recorder/gap_monitor.py recheck does). The copy of the log is
   cut at the paper ledger's on-time cut-off for the date, so a rerun on the same date reads the same rows.
2. E2. research/holdout_scan has no single "scan a date" call: the step checks the date against
   holdout_scan.windows() and runs holdout_scan.scan_log on the rows that carry the date.
3. E3. The scheduled curve run fits thirteen tenors from the Treasury file (daily-curve-run.md: a missing tenor
   is a failed fit, not a smaller fit). The rehearsal fits the five recorded tenors with a copy of
   tools/curve_daily/config.json whose tenor list is cut to those five; the page and the evidence say so. No
   Federal Reserve file is recorded, so the consistency comparison stays pending. The HASH fault is caught by
   comparing the source file with the sha256 that E1 wrote; on a clean run the date is also refitted from the
   file and must equal the row exactly (verify_chain.py rebuild allows 1e-6; same process here, so exact).
4. E4. Two paper runs (the previous business day, then the date), so the date's row carries positions and a
   non-trivial explain. The EXPLAIN fault is a re-chained copy (a forger without the anchors); the verifier's
   exact replay must refuse it. Anchors are not checked: a dry run has none.
5. E5. The "day's book" is the paper ledger's positions_close at the date, as zero-coupon positions at the
   constant-maturity par yields (notional = quantity times par price), for risk.intraday.delta_gamma_bound
   (1 bp shift); risk.curve.key_rate runs on each position as a BOND product on a curve of the E3 zero rates.
   The CLI contract cannot carry a non-finite number, so the DOMAIN fault comes back as E_PARSE ("NaN is not
   JSON"), not E_DOMAIN; the step fails either way. key_rate has no label output; the label checked is
   delta_gamma_bound's own.
6. E6. tools/dashboard/render.py does not exist yet. The curve page is tools/curve_daily/site_page.render (the
   KR-106 hook); the paper page is rendered here after dashboard.md section 2, with the label, ceiling and
   statement from tools/paper_daily/config.json (the statement is worded differently from the spec's draft);
   no model-reserve page (no report exists). The `markdown` package is not in the project environment, so a
   small converter writes the HTML inside tools/build_site.py's own PAGE template and CSS (read with ast).
7. E7. Internal links only: external links are counted, not fetched (tools/check_links.py needs the network).
   The G10 phone-width check is static: no CSS or inline width above 375 px and a viewport meta on every page;
   it is not a browser render at 375 px and does not check dark mode.
8. E8. When a step fails, E8 is recorded as not run, but the checklist JSON is still written, so a failed run is
   archived too. The default output name carries the source (and the planted fault).
"""

from __future__ import annotations

import argparse
import ast
import copy
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for sub in ("tools/curve_daily", "tools/paper_daily", "tools/forward-log", "research"):
    sys.path.insert(0, str(ROOT / sub))
import curve_core as cc
import forward_log as fl
import holdout_scan as hs
import paper_core as pc
import site_page

FORMAT = "qf-eod-rehearsal/1"
SPEC = "specifications/12-platform/soak-eod-capacity.md section 3 (proposed, branch k-w3-spec)"
DEFAULT_HOST = "local laptop, not the acceptance machine"
FAULTS = {"GAP": "E1", "HOLDOUT": "E2", "HASH": "E3", "EXPLAIN": "E4", "DOMAIN": "E5", "LABEL": "E6", "WIDTH": "E7"}
TITLES = {
    "E1": "read the day's recorded rows and verify the chain",
    "E2": "holdout check on the date",
    "E3": "daily curve run, dry run, for the date",
    "E4": "paper ledger run, dry run, for the date",
    "E5": "intraday risk on the day's book",
    "E6": "render the dashboards into a temporary site",
    "E7": "site checks on the rendered pages",
    "E8": "archive",
}
SYNTHETIC_LABEL = "synthetic recorded day: invented values, no market data"
FORWARD_LABEL = "recorded forward-log rows; hashes and aggregates only in this file"
FIVE_TENOR_NOTE = (
    "Rehearsal fit on the five tenors the recorder keeps (3 Mo, 2 Yr, 5 Yr, 10 Yr, 30 Yr), not the "
    "scheduled thirteen-tenor run."
)
FORBIDDEN = re.compile(r"return|sharpe|annualised|annualized|drawdown|outperform|alpha|profitab", re.IGNORECASE)
PHONE_PX = 375
SHIFT = 0.0001  # 1 bp parallel move for risk.intraday.delta_gamma_bound
Runner = Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]]


class StepFail(Exception):
    def __init__(self, reason: str, evidence: dict[str, Any] | None = None):
        super().__init__(reason)
        self.reason, self.evidence = reason, evidence or {}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(p: Path) -> str:
    return sha(p.read_bytes())


def make_runner() -> tuple[Runner, str]:
    """The library through its CLI contract: in process when quantforge_core imports, else one batch process."""
    try:
        from quantforge_core.cli.main import run_case

        def raw(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
            return {c["case_id"]: json.loads(json.dumps(run_case(json.dumps(c)))) for c in cases}

        return raw, "python, in process (quantforge_core.cli.main.run_case)"
    except ImportError:
        sys.path.insert(0, str(ROOT / "tools" / "workflows"))
        import common

        def batch(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
            out: dict[str, dict[str, Any]] = common.batch(cases, "python") if cases else {}
            return out

        return batch, "python, CLI batch (tools/workflows/common.py)"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)
    return r.stdout.decode("utf-8") if r.returncode == 0 else ""


def evening(d: dt.date) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(23, 45), dt.UTC)


def write(p: Path, data: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


# ------------------------------------------------------------------ synthetic recorded day


def _u(d: dt.date, salt: str) -> float:
    h = hashlib.sha256(f"{d.isoformat()}|{salt}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**31 - 1


def synthetic_value(d: dt.date, years: float) -> float:
    """Nelson-Siegel par yield in percent from a hash of the date: invented and repeatable."""
    b0, b1, b2, tau = (
        4.3 + 0.2 * _u(d, "b0"),
        -0.7 + 0.2 * _u(d, "b1"),
        0.8 + 0.4 * _u(d, "b2"),
        2.0 + 0.5 * _u(d, "tau"),
    )
    x = years / tau
    e = -math.expm1(-x) / x
    return round(b0 + b1 * e + b2 * (e - math.exp(-x)), 2)


def synthetic_log(date: dt.date, pcfg: dict[str, Any], cal: Any) -> str:
    """Eight business days ending at `date`, in the recorder's row format: one par-yield row (five tenors, the
    file's sha256 and size, the cumulative state_sha256) and one SOFR row (hash only) per day."""
    days = [date]
    while len(days) < 8:
        days.insert(0, max(cal.open_between(days[0] - dt.timedelta(days=10), days[0] - dt.timedelta(days=1))))
    fields = [(k["field"], float(k["years"])) for k in pcfg["knots"]]
    head, seq, state, out = fl.ZERO, 0, {}, []

    def add(series: str, when: str, payload: dict[str, Any]) -> None:
        nonlocal head, seq
        seq += 1
        rec = {
            "sequence": seq,
            "series_id": series,
            "event_time": when,
            "knowledge_time": when,
            "value": {"commit": "synthetic", "payload": payload},
        }
        head = fl.link(head, rec)
        out.append(json.dumps({"record": rec, "hash": head}, ensure_ascii=False, sort_keys=True))

    for d in days:
        obs = {f"{d.isoformat()}|{f}": synthetic_value(d, y) for f, y in fields}
        state.update(obs)
        raw = source_csv(
            {x.isoformat(): {f: repr(synthetic_value(x, y)) for f, y in fields} for x in days if x <= d},
            [f for f, _ in fields],
        )
        add(
            "recorder/us-treasury-par-yields",
            f"{d.isoformat()}T22:30:00Z",
            {
                "bytes": len(raw),
                "kind": "recording",
                "licence": "synthetic test data",
                "observations": obs,
                "sha256": sha(raw),
                "sources_sha256": sha(b"synthetic"),
                "state_sha256": sha(fl.canon(state).encode("utf-8")),
                "url": "synthetic:us-treasury-par-yields",
            },
        )
        sofr = f"synthetic sofr {d.isoformat()}".encode()
        add(
            "recorder/nyfed-sofr",
            f"{d.isoformat()}T22:30:10Z",
            {
                "bytes": len(sofr),
                "kind": "recording",
                "licence": "synthetic test data",
                "sha256": sha(sofr),
                "url": "synthetic:nyfed-sofr",
            },
        )
    return "".join(x + "\n" for x in out)


def source_csv(table: dict[str, dict[str, str]], fields: list[str]) -> bytes:
    """Treasury file layout: newest first, MM/DD/YYYY, values as recorded."""
    rows = ["Date," + ",".join(fields)]
    for d in sorted(table, reverse=True):
        rows.append(f"{d[5:7]}/{d[8:10]}/{d[:4]}," + ",".join(table[d][f] for f in fields))
    return ("\n".join(rows) + "\n").encode("ascii")


# ------------------------------------------------------------------ small Markdown to HTML (headings, tables, text)


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


def md_to_html(text: str) -> str:
    out: list[str] = []
    table: list[list[str]] = []

    def flush() -> None:
        if table:
            head, body = table[0], [r for r in table[2:]]
            out.append(
                "<table><thead><tr>"
                + "".join(f"<th>{_inline(c)}</th>" for c in head)
                + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
                + "</tbody></table>"
            )
            table.clear()

    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|"):
            table.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush()
        m = re.match(r"^(#{1,3}) (.+)$", s)
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif s:
            out.append(f"<p>{_inline(s)}</p>")
    flush()
    return "\n".join(out)


def site_template() -> tuple[str, str]:
    """CSS and PAGE from tools/build_site.py, read without importing it (it needs the markdown package)."""
    tree = ast.parse((ROOT / "tools" / "build_site.py").read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in ("CSS", "PAGE")
        ):
            found[node.targets[0].id] = ast.literal_eval(node.value)
    return found["CSS"], found["PAGE"]


# ------------------------------------------------------------------ the rehearsal


class Rehearsal:
    def __init__(self, date: dt.date, source: str, plant: str | None, tmp: Path, log_ref: str):
        self.date, self.ds, self.source, self.plant, self.tmp, self.log_ref = (
            date,
            date.isoformat(),
            source,
            plant,
            tmp,
            log_ref,
        )
        self.raw, self.runner_desc = make_runner()
        self.prun = lambda cases: pc.outputs(self.raw(cases).values())
        self.ccfg = cc.load_config()
        self.pcfg = pc.load_config()
        self.fields = [k["field"] for k in self.pcfg["knots"]]
        self.pcal = pc.Calendar(self.prun, self.pcfg["calendar"])
        self.commit = git("rev-parse", "HEAD").strip() or "unknown"
        self.inputs: dict[str, str] = {}
        self.outputs: dict[str, str] = {}
        self.ctx: dict[str, Any] = {}

    def rel(self, p: Path) -> str:
        try:
            return "tmp/" + p.relative_to(self.tmp).as_posix()
        except ValueError:
            return p.relative_to(ROOT).as_posix()

    def note_in(self, p: Path) -> str:
        self.inputs[self.rel(p)] = h = file_sha(p)
        return h

    def note_out(self, p: Path) -> str:
        self.outputs[self.rel(p)] = h = file_sha(p)
        return h

    # E1 ---------------------------------------------------------------------------------------------------------
    def e1(self) -> dict[str, Any]:
        for p in (ROOT / "tools/curve_daily/config.json", ROOT / "tools/paper_daily/config.json"):
            self.note_in(p)
        if self.source == "synthetic":
            text = synthetic_log(self.date, self.pcfg, self.pcal)
            origin = "synthetic log built in the temporary folder"
        else:
            text = git("show", f"{self.log_ref}:actions/log.jsonl")
            origin = f"git show {self.log_ref}:actions/log.jsonl"
            if not text.strip():
                raise StepFail("NO_LOG", {"origin": origin})
        full = [json.loads(x) for x in text.splitlines() if x.strip()]
        cut = pc.stamp(self.pcal.cutoff(self.date, self.pcfg))
        entries = [e for e in full if e["record"]["knowledge_time"] <= cut]
        series = self.pcfg["source_series"]

        def carries(e: dict[str, Any]) -> bool:
            obs = e["record"]["value"].get("payload", {}).get("observations") or {}
            return e["record"]["series_id"] == series and all(f"{self.ds}|{f}" in obs for f in self.fields)

        ev: dict[str, Any] = {"origin": origin, "rows_in_source": len(full), "rows_up_to_cutoff": len(entries)}
        if self.plant == "GAP":
            idx = [i for i, e in enumerate(entries) if carries(e)]
            if idx:
                del entries[idx[-1]]
                ev["planted"] = "the date's par-yield row removed from the copy"
        log = write(
            self.tmp / "forward-log/actions/log.jsonl",
            "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in entries).encode("utf-8"),
        )
        ev["log_copy_sha256"] = self.note_in(log)
        try:
            count, head = fl.verify(log)
        except ValueError as e:
            ev["detail"] = str(e)[:120]
            raise StepFail("CHAIN", ev) from e
        ev.update(chain_rows=count, chain_head=head)
        states: dict[str, dict[str, Any]] = {}
        checked, bad = 0, 0
        for row in entries:
            r = row["record"]
            pay = r["value"].get("payload", {})
            if r["series_id"].startswith("recorder/") and "state_sha256" in pay:
                st = states.setdefault(r["series_id"], {})
                st.update(pay.get("observations", {}))
                checked += 1
                bad += sha(fl.canon(st).encode("utf-8")) != pay["state_sha256"]
        ev.update(state_rows_rechecked=checked, state_mismatches=bad)
        if bad:
            raise StepFail("STATE", ev)
        rows = [e for e in entries if carries(e)]
        if not rows:
            raise StepFail("NO_PAR_ROW", ev)
        par = pc.par_state(entries, series, self.fields)
        year = {d: v for d, (v, _) in par.items() if d[:4] == self.ds[:4] and d <= self.ds}
        src = write(self.tmp / "source/treasury-par-yields.csv", source_csv(year, self.fields))
        self.ctx.update(entries=entries, log=log, par_row=rows[-1], source=src, source_sha=self.note_in(src))
        ev.update(
            par_row_hash=rows[-1]["hash"],
            tenors_for_date=len(self.fields),
            source_dates=len(year),
            source_sha256=self.ctx["source_sha"],
        )
        return ev

    # E2 ---------------------------------------------------------------------------------------------------------
    def e2(self) -> dict[str, Any]:
        w = hs.windows()
        checked = self.ds
        ev: dict[str, Any] = {"windows": len(w), "checked_date": "the run date"}
        if self.plant == "HOLDOUT":
            checked = w["R3-01"][1]
            ev["checked_date"] = ev["planted"] = "the last day of the R3-01 holdout window (not written here)"
        hits = cc.holdout_hit(checked, w)
        lines = [
            json.dumps(e)
            for e in self.ctx["entries"]
            if e["record"]["event_time"][:10] == self.ds
            or any(
                k.split("|")[0] == self.ds for k in (e["record"]["value"].get("payload", {}).get("observations") or {})
            )
        ]
        row_hits = hs.scan_log(lines, w)
        ev.update(date_hits=hits, rows_scanned=len(lines), row_hits=len(row_hits))
        if hits or row_hits:
            raise StepFail("HOLDOUT", ev)
        return ev

    # E3 ---------------------------------------------------------------------------------------------------------
    def e3(self) -> dict[str, Any]:
        src: Path = self.ctx["source"]
        ev: dict[str, Any] = {"note": FIVE_TENOR_NOTE}
        if self.plant == "HASH":
            changed = bytearray(src.read_bytes())
            i = len(changed) - 2  # a digit of the oldest row
            changed[i] = ord("0") if changed[i] != ord("0") else ord("1")
            src.write_bytes(bytes(changed))
            ev["planted"] = "one byte of the source file changed after E1"
        data = src.read_bytes()
        ev["source_sha256"] = sha(data)
        if sha(data) != self.ctx["source_sha"]:
            raise StepFail("INPUT_HASH", ev)
        cfg = copy.deepcopy(self.ccfg)
        cfg["tenors"] = [t for t in cfg["tenors"] if t["field"] in self.fields]
        cfgp = write(
            self.tmp / "curve-daily/config-five-tenors.json", json.dumps(cfg, indent=1, sort_keys=True).encode()
        )
        self.note_in(cfgp)
        url = cfg["treasury"]["url"].replace("{year}", self.ds[:4])

        def fetch(u: str) -> bytes:
            if u == url:
                return data
            raise OSError("not recorded: the rehearsal never fetches")

        now = evening(self.date)
        out, new, notes = cc.run(cfg, self.raw, "", now, fetch, self.commit, "rehearsal", "python")
        v = cc.verify(out, cfg, self.raw)
        day = next((r for r in new if r["kind"] == "DAY" and r["body"]["date"] == self.ds), None)
        ev.update(
            rows_built=len(new),
            kinds=[r["kind"] for r in new],
            verify_ok=v["ok"],
            verify_reason=v.get("reason", ""),
            notes=len(notes),
        )
        if not v["ok"]:
            raise StepFail("VERIFY", ev)
        if day is None or day["body"]["status"] != "ok":
            ev["status"] = day["body"]["status"] if day else "no DAY row"
            raise StepFail("NO_FIT", ev)
        labels = {r["label"] for r in cc.parse(out)}
        ev["labels_ok"] = labels == {cfg["label"]}
        if not ev["labels_ok"]:
            raise StepFail("LABEL", ev)
        refit = cc.fit_day(self.date, cc.treasury_rows(data)[self.ds], cfg, self.raw)
        ev["refit_exact"] = refit == day["body"]["fit"]
        if not ev["refit_exact"]:
            raise StepFail("REFIT_DIFFERS", ev)
        fit = day["body"]["fit"]
        ev.update(
            head=v["head"],
            timing=day["body"]["timing"],
            tau=fit["tau"],
            rmse_bp=fit["rmse_bp"],
            max_abs_bp=fit["max_abs_bp"],
            within_fit_flag=fit["within_fit_flag"],
            consistency="pending",
        )
        led = write(self.tmp / "curve-daily/ledger/curves.jsonl", out.encode("ascii"))
        summ = cc.summary(out, v)
        sp = write(
            self.tmp / "curve-daily/ledger/summary.json", (json.dumps(summ, indent=1, sort_keys=True) + "\n").encode()
        )
        ev.update(ledger_sha256=self.note_out(led), summary_sha256=self.note_out(sp))
        self.ctx.update(curve_summary=summ, curve_day=day)
        return ev

    # E4 ---------------------------------------------------------------------------------------------------------
    def e4(self) -> dict[str, Any]:
        entries = self.ctx["entries"]
        prev = max(self.pcal.open_between(self.date - dt.timedelta(days=10), self.date - dt.timedelta(days=1)))
        text, _, _ = pc.run(self.pcfg, self.prun, "", entries, evening(prev), self.commit, "python")
        text, _, notes = pc.run(self.pcfg, self.prun, text, entries, evening(self.date), self.commit, "python")
        rows = pc.parse(text)
        ev: dict[str, Any] = {
            "runs": 2,
            "kinds": [r["kind"] for r in rows],
            "problems": sum(n.startswith("PROBLEM") for n in notes),
        }
        day = next((r for r in rows if r["kind"] == "DAY" and r["body"]["date"] == self.ds), None)
        if day is None:
            raise StepFail("NO_DAY_ROW", ev)
        if self.plant == "EXPLAIN":
            ex = day["body"]["explain"]
            ex["roll_down"] = pc.plain(Decimal(ex["roll_down"]) + Decimal("0.01"))
            prevh = pc.GENESIS
            for r in rows:
                r.pop("hash", None)
                r["prev"] = prevh
                r["hash"] = prevh = pc.row_hash(r)
            text = "".join(pc.line(r) + "\n" for r in rows)
            ev["planted"] = "roll_down of the date's row plus one cent, chain rebuilt"
        v = pc.verify(text, self.pcfg, self.prun)
        ev.update(verify_ok=v["ok"], verify_reason=v.get("reason", ""))
        if not v["ok"]:
            raise StepFail(str(v.get("reason") or "VERIFY"), ev)
        b = day["body"]
        ex = b["explain"]
        stated = sum(Decimal(ex[k]) for k in ("carry", "roll_down", "curve_move", "fills_costs", "unexplained"))
        ev.update(
            explain_sums=stated == Decimal(b["pnl"]),
            unexplained=ex["unexplained"],
            timing=b["timing"],
            orders=len(b["orders"]),
            declared_on_time_days=v["declared_on_time_days"],
            head=v["head"],
        )
        if not ev["explain_sums"]:
            raise StepFail("EXPLAIN", ev)
        led = write(self.tmp / "paper-ledger/ledger/ledger.jsonl", text.encode("ascii"))
        ev["ledger_sha256"] = self.note_out(led)
        self.ctx.update(paper_rows=rows, paper_day=day, paper_verify=v)
        return ev

    # E5 ---------------------------------------------------------------------------------------------------------
    def e5(self) -> dict[str, Any]:
        b = self.ctx["paper_day"]["body"]
        par_px = float(self.pcfg["par_price"])
        book = []
        for inst in self.pcfg["instruments"]:
            q = float(b["positions_close"].get(inst["symbol"], "0"))
            if q:
                book.append((inst, q, float(Decimal(b["par_yields"][inst["field"]]) / 100)))
        positions: list[dict[str, Any]] = [
            {"notional": q * par_px, "maturity": float(i["years"]), "yield": y} for i, q, y in book
        ]
        ev: dict[str, Any] = {"positions": len(positions), "shift": SHIFT}
        if self.plant == "DOMAIN":
            positions.append({"notional": 1e6, "maturity": 5.0, "yield": float("nan")})
            ev["planted"] = "a position with a non-finite yield"
        if not positions:
            raise StepFail("EMPTY_BOOK", ev)
        dg = self.raw([cc.case("dg", "risk.intraday.delta_gamma_bound", {"positions": positions, "shift": SHIFT})])[
            "dg"
        ]
        if dg.get("status") != "ok":
            ev["error_code"] = (dg.get("error") or {}).get("code", "E_UNKNOWN")
            raise StepFail(ev["error_code"], ev)
        o = dg["outputs"]
        ev.update(estimate_pnl=o["estimate_pnl"], bound=o["bound"], label=o.get("label", ""))
        if not o.get("label"):
            raise StepFail("LABEL", ev)
        zeros = self.ctx["curve_summary"]["latest"]["zeros_pct"]
        pillars = []
        for k in sorted(zeros):
            m = cc.add_months(self.date, 12 * int(k))
            t = (m - self.date).days / 365
            pillars.append({"date": m.isoformat(), "discount_factor": math.exp(-float(zeros[k]) / 100 * t)})
        cases = [
            cc.case(
                i["symbol"],
                "risk.curve.key_rate",
                {
                    "curve": {"as_of": self.ds, "interpolation": "LOG_LINEAR_DF", "pillars": pillars},
                    "mode": "TRIANGULAR",
                    "key_dates": [p["date"] for p in pillars],
                    "bump_bp": 1.0,
                    "scheme": "CENTRAL",
                    "product": {
                        "kind": "BOND",
                        "settlement": self.ds,
                        "notional": q * par_px,
                        "bond": {
                            "maturity": cc.add_months(self.date, 12 * int(i["years"])).isoformat(),
                            "coupon": y,
                            "frequency": int(self.pcfg["coupon_frequency"]),
                        },
                    },
                },
            )
            for i, q, y in book
        ]
        kr = self.raw(cases)
        failed = sorted(k for k, r in kr.items() if r.get("status") != "ok")
        ev.update(key_rate_cases=len(kr), key_rate_failed=failed)
        if failed:
            raise StepFail("KEY_RATE", ev)
        ev["zero_dv01_sum"] = math.fsum(r["outputs"]["zero_dv01"] for r in kr.values())
        ev["key_rate_buckets"] = len(pillars)
        return ev

    # E6 ---------------------------------------------------------------------------------------------------------
    def paper_page(self) -> str:
        cfg, rows, v = self.pcfg, self.ctx["paper_rows"], self.ctx["paper_verify"]
        days = [r for r in rows if r["kind"] == "DAY"]
        on_time = sum(r["body"]["timing"] == "on_time" for r in days)
        out = [
            "# Paper ledger (rehearsal)",
            "",
            f"Label: {cfg['label']}.",
            "",
            cfg["ceiling"],
            "",
            cfg["statement"],
            "",
        ]
        if self.source == "synthetic":
            out += [f"Data: {SYNTHETIC_LABEL}.", ""]
        late, gaps = sum(r["body"]["timing"] != "on_time" for r in days), sum(r["kind"] == "GAP" for r in rows)
        out += [
            f"**{on_time} of 20** recorded trading days (on time). Late days: {late}. Gaps: {gaps}.",
            "",
            f"Chain head `{v['head'][:16]}`, last date {v['last_date']}, verifier: {'ok' if v['ok'] else 'failed'}.",
            "",
            "## Per day",
            "",
            "| date | timing | P&L | carry | roll-down | curve move | trading | fees | unexplained | nav close |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in reversed(days):
            b, ex = r["body"], r["body"]["explain"]
            out.append(
                f"| {b['date']} | {b['timing'].replace('_', ' ')} | {b['pnl']} | {ex['carry']} | {ex['roll_down']} | "
                f"{ex['curve_move']} | {ex['trading']} | {ex['fees']} | {ex['unexplained']} | {b['nav_close']} |"
            )
        out += [
            "",
            "## Orders",
            "",
            (
                f"| date | symbol | side | quantity | filled ({cfg['fill_label']}) | status ({cfg['fill_label']}) | "
                f"expected cost bp ({cfg['tca_pretrade_label']}) | TCA total bp ({cfg['fill_label']}) |"
            ),
            "|---|---|---|---:|---:|---|---:|---:|",
        ]
        for r in reversed(days):
            for o in r["body"]["orders"]:
                out.append(
                    f"| {r['body']['date']} | {o['symbol']} | {o['side']} | {o['quantity']} | {o['filled']} | "
                    f"{o['status']} | {o.get('tca_pretrade', {}).get('expected_cost_bps', '')} | "
                    f"{o.get('tca', {}).get('total_bps', '')} |"
                )
        return "\n".join(out) + "\n"

    def curve_page(self) -> str:
        extra = [FIVE_TENOR_NOTE, ""] + ([f"Data: {SYNTHETIC_LABEL}.", ""] if self.source == "synthetic" else [])
        return "# Daily curve (rehearsal)\n\n" + "\n".join(extra) + site_page.render(self.ctx["curve_summary"])

    def e6(self) -> dict[str, Any]:
        pcfg = self.pcfg
        pages = {"dashboard/paper.html": self.paper_page(), "dashboard/curve.html": self.curve_page()}
        ev: dict[str, Any] = {"pages": sorted(pages)}
        if self.plant == "LABEL":
            pages["dashboard/paper.html"] = pages["dashboard/paper.html"].replace(pcfg["label"], "")
            ev["planted"] = "the paper row label removed from its page"
        need = {
            "dashboard/paper.html": [
                pcfg["label"],
                pcfg["ceiling"],
                pcfg["statement"],
                pcfg["fill_label"],
                pcfg["tca_pretrade_label"],
            ],
            "dashboard/curve.html": [
                self.ccfg["label"],
                self.ccfg["consistency_label"],
                site_page.MISS_NOTE,
                FIVE_TENOR_NOTE,
            ],
        }
        if self.source == "synthetic":
            for labels in need.values():
                labels.append(SYNTHETIC_LABEL)
        missing = [
            f"{p}: label {i}" for p, labels in need.items() for i, lab in enumerate(labels) if lab not in pages[p]
        ]
        ev["labels_checked"] = sum(len(x) for x in need.values())
        if missing:
            ev["missing"] = missing
            raise StepFail("LABEL", ev)
        rows = self.ctx["paper_rows"]
        counted = sum(r["kind"] == "DAY" and r["body"]["timing"] == "on_time" for r in rows)
        ev.update(counter_rows=counted, counter_verifier=int(self.ctx["paper_verify"]["declared_on_time_days"]))
        if counted != ev["counter_verifier"] or f"**{counted} of 20**" not in pages["dashboard/paper.html"]:
            raise StepFail("COUNTER", ev)
        claims = [p for p, t in pages.items() if FORBIDDEN.search(t.replace(pcfg["ceiling"], ""))]
        ev["claim_lint"] = claims
        if claims:
            raise StepFail("CLAIM", ev)
        w = hs.windows()
        hits = [h for p, t in pages.items() for h in hs.scan_text(p, t, w)]
        ev["holdout_hits"] = len(hits)
        if hits:
            raise StepFail("HOLDOUT", ev)
        css, page = site_template()
        site = self.tmp / "site"
        write(site / "style.css", css.encode("utf-8"))
        write(site / "search.js", b"// rehearsal site: no search index\n")

        def nav(up: str) -> str:
            return (
                f'<nav class="bar"><div class="inner"><a href="{up}index.html">QuantForge rehearsal</a>'
                f'<a href="{up}dashboard/curve.html">Curve</a><a href="{up}dashboard/paper.html">Paper ledger</a></div></nav>'
            )

        index = "# End-of-day rehearsal\n\nStatic pages built by tools/eod/rehearse.py in a temporary folder.\n"
        for rel, text in {"index.html": index, **pages}.items():
            up = "../" * rel.count("/")
            title = re.search(r"^# (.+)$", text, re.MULTILINE)
            body = page.format(
                title=html.escape(title.group(1) if title else rel), up=up, nav=nav(up), body=md_to_html(text)
            )
            self.note_out(write(site / rel, body.encode("utf-8")))
        self.ctx["site"] = site
        return ev

    # E7 ---------------------------------------------------------------------------------------------------------
    def e7(self) -> dict[str, Any]:
        site: Path = self.ctx["site"]
        ev: dict[str, Any] = {}
        if self.plant == "WIDTH":
            p = site / "dashboard/curve.html"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    '<main id="main" class="wrap">',
                    '<main id="main" class="wrap"><div style="width:600px">planted</div>',
                ),
                encoding="utf-8",
            )
            ev["planted"] = "a 600 px fixed-width element on dashboard/curve.html"
        pages = sorted(site.rglob("*.html"))
        internal, external, broken, wide, no_viewport = 0, 0, [], [], []
        css = (site / "style.css").read_text(encoding="utf-8")
        for m in re.finditer(r"(?<![-\w])(?:min-)?width\s*:\s*(\d+(?:\.\d+)?)px", css):
            if float(m.group(1)) > PHONE_PX:
                wide.append(f"style.css: {m.group(0)}")
        for p in pages:
            t = p.read_text(encoding="utf-8")
            rel = p.relative_to(site).as_posix()
            if 'name="viewport"' not in t:
                no_viewport.append(rel)
            for m in re.finditer(r"(?<![-\w])(?:min-)?width\s*:\s*(\d+(?:\.\d+)?)px", t):
                if float(m.group(1)) > PHONE_PX:
                    wide.append(f"{rel}: {m.group(0)}")
            for m in re.finditer(r"(?<![-\w])width=\"(\d+)\"", t):
                if int(m.group(1)) > PHONE_PX and "<svg" not in t[max(0, m.start() - 200) : m.start()]:
                    wide.append(f"{rel}: {m.group(0)}")
            for m in re.finditer(r'(?:href|src)="([^"]+)"', t):
                u = m.group(1)
                if re.match(r"[a-z][a-z0-9+.-]*:", u, re.IGNORECASE):
                    external += 1
                    continue
                target = u.split("#")[0]
                if not target:
                    continue
                internal += 1
                if not (p.parent / target).resolve().is_file():
                    broken.append(f"{rel} -> {u}")
        ev.update(
            pages=len(pages),
            internal_links=internal,
            external_links_not_fetched=external,
            broken=broken,
            wider_than_phone=wide,
            no_viewport=no_viewport,
            phone_px=PHONE_PX,
        )
        if broken:
            raise StepFail("LINK", ev)
        if wide or no_viewport:
            raise StepFail("WIDTH", ev)
        return ev

    # E8 ---------------------------------------------------------------------------------------------------------
    def e8(self) -> dict[str, Any]:
        return {"inputs_hashed": len(self.inputs), "outputs_hashed": len(self.outputs)}


def run(
    date: dt.date,
    source: str,
    plant: str | None,
    out: Path,
    log_ref: str = "origin/forward-log",
    host: str | None = None,
) -> dict[str, Any]:
    host = host or os.environ.get("QF_HOST_LABEL") or DEFAULT_HOST
    steps: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="qf-eod-") as td:
        r = Rehearsal(date, source, plant, Path(td), log_ref)
        failed = None
        for sid in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"):
            line: dict[str, Any] = {"step": sid, "title": TITLES[sid]}
            if failed:
                steps.append({**line, "status": "not run", "reason": "", "evidence": {}, "seconds": 0.0})
                continue
            t0 = time.perf_counter()
            try:
                ev = getattr(r, sid.lower())()
                line.update(status="pass", reason="", evidence=ev)
            except StepFail as e:
                line.update(status="fail", reason=e.reason, evidence=e.evidence)
            except Exception as e:  # noqa: BLE001 - any other error is a failed step, recorded by type
                line.update(status="fail", reason="ERROR", evidence={"error": f"{type(e).__name__}: {str(e)[:160]}"})
            line["seconds"] = round(time.perf_counter() - t0, 3)
            steps.append(line)
            if line["status"] == "fail":
                failed = sid
        doc = {
            "format": FORMAT,
            "spec": SPEC,
            "date": r.ds,
            "source": source,
            "data_label": SYNTHETIC_LABEL if source == "synthetic" else FORWARD_LABEL,
            "log_ref": log_ref if source == "forward-log" else "",
            "plant": plant or "",
            "expected_failing_step": FAULTS.get(plant or "", ""),
            "host": host,
            "commit": r.commit,
            "runner": r.runner_desc,
            "dry_run": True,
            "result": "pass" if not failed else "fail",
            "failed_step": failed or "",
            "steps": steps,
            "inputs_sha256": dict(sorted(r.inputs.items())),
            "outputs_sha256": dict(sorted(r.outputs.items())),
            "deviations": "see the module docstring of tools/eod/rehearse.py, list 'Deviations from the proposed spec'",
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--date", required=True, type=dt.date.fromisoformat)
    ap.add_argument("--source", choices=("forward-log", "synthetic"), default="forward-log")
    ap.add_argument("--log-ref", default="origin/forward-log", help="git ref holding actions/log.jsonl")
    ap.add_argument("--plant", choices=sorted(FAULTS))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    name = f"eod-{a.date.isoformat()}-{a.source}" + (f"-plant-{a.plant}" if a.plant else "") + ".json"
    out = Path(a.out) if a.out else ROOT / "benchmarks" / "results" / "k6" / name
    doc = run(a.date, a.source, a.plant, out, a.log_ref)
    for s in doc["steps"]:
        print(f"{s['step']} {s['status']:7} {s['reason']:14} {s['seconds']:7.3f}s  {s['title']}")
    print(
        f"result: {doc['result']}"
        + (f" (failed at {doc['failed_step']})" if doc["failed_step"] else "")
        + f"; wrote {out}"
    )
    return 0 if doc["result"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
