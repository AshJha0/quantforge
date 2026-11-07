"""Shared plumbing for the daily workflows. Neutral tooling: standard library, no financial logic.

Everything financial is a CLI call. This module fetches public data, sends cases through one
`quantforge batch` process, and writes dated reports. Its only sums are unit changes (percent to
decimal), curve time (date - as_of) / 365, and differences between numbers.
"""
import datetime as dt
import json
import math
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import resolve_command  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; quantforge-workflows/0.1)"
SOURCES = {s["id"]: s for s in json.loads((ROOT / "tools/recorder/sources.json").read_text(encoding="utf-8"))["sources"]}
# Batch entry point. When specifications/cli-contract.md names `--batch`, change this one line (plan 11.5.7).
BATCH_ARGS = ["batch"]


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def source_url(source_id, year):
    return SOURCES[source_id]["url"].replace("{year}", str(year))


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(cases, impl="python"):
    """One process for all cases. Returns results keyed by case_id; errors are returned, not raised."""
    impls = json.loads((ROOT / "conformance/runner/implementations.json").read_text(encoding="utf-8"))
    base, cwd = resolve_command(impls[impl])
    text = "".join(json.dumps(c, separators=(",", ":")) + "\n" for c in cases)
    p = subprocess.run(base + BATCH_ARGS, cwd=cwd, input=text.encode("utf-8"), capture_output=True, timeout=1800)
    if p.returncode != 0:
        raise SystemExit(f"{impl} batch exited {p.returncode}: {p.stderr.decode('utf-8', 'replace')[:500]}")
    rows = [json.loads(x) for x in p.stdout.decode("utf-8").splitlines() if x.strip()]
    if len(rows) != len(cases):
        raise SystemExit(f"{impl}: sent {len(cases)} cases, got {len(rows)} results")
    return {r["case_id"]: r for r in rows}


def years(date, as_of):
    return (dt.date.fromisoformat(date) - dt.date.fromisoformat(as_of)).days / 365.0


def zero_rate(df, t):
    """Continuously compounded zero from a discount factor: a unit change, used only for band checks and charts."""
    return -math.log(df) / t if t > 0 else float("nan")


class Report:
    """A dated Markdown report plus a JSON twin with every number in it."""

    def __init__(self, name, as_of, out_root):
        self.name, self.as_of = name, as_of
        self.dir = Path(out_root) / as_of
        self.lines, self.data, self.checks = [], {"workflow": name, "as_of": as_of}, []

    def h(self, text, level=2):
        self.lines += ["", "#" * level + " " + text, ""]

    def p(self, text):
        self.lines.append(text)

    def table(self, head, rows):
        self.lines.append("| " + " | ".join(head) + " |")
        self.lines.append("|" + "|".join("---" for _ in head) + "|")
        for r in rows:
            self.lines.append("| " + " | ".join(str(x) for x in r) + " |")
        self.lines.append("")

    def check(self, name, level, ok, detail):
        """level is 'fail' or 'warn'. A failed 'fail' check makes the workflow exit 1."""
        self.checks.append({"check": name, "level": level, "ok": bool(ok), "detail": detail})

    def write(self, notices):
        bad = [c for c in self.checks if not c["ok"] and c["level"] == "fail"]
        warn = [c for c in self.checks if not c["ok"] and c["level"] == "warn"]
        head = [f"# {self.name}: {self.as_of}", "",
                f"Result: **{'FAIL' if bad else 'PASS'}** ({len(self.checks)} checks, {len(bad)} failed, {len(warn)} warnings). "
                f"Generated {dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%MZ} by `tools/workflows/`.", ""]
        checks = ["", "## Checks", "", "| Check | Level | Result | Detail |", "|---|---|---|---|"]
        checks += [f"| {c['check']} | {c['level']} | {'ok' if c['ok'] else 'NOT OK'} | {c['detail']} |" for c in self.checks]
        tail = ["", "## Data notices", ""] + [f"- {n}" for n in notices] + [""]
        self.dir.mkdir(parents=True, exist_ok=True)
        slug = self.name.lower().replace(" ", "-")
        (self.dir / f"{slug}.md").write_text("\n".join(head + self.lines + checks + tail), encoding="utf-8")
        self.data["checks"] = self.checks
        (self.dir / f"{slug}.json").write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {self.dir / slug}.md: {'FAIL' if bad else 'PASS'}")
        return 1 if bad else 0
