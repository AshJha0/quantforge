"""Figures for the site home, tools/site_home.html, from one place. Standard library only.

Release facts come from tools/site_facts.json; the version and counts are read from the tree, so a
release edits site_facts.json and nothing else on the home page. Used by tools/build_site.py.
"""
import json
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def home_figures(root=ROOT):
    """Values for the site home: release facts from tools/site_facts.json, the rest counted from the tree."""
    facts = {k: v for k, v in json.loads((root / "tools" / "site_facts.json").read_text(encoding="utf-8")).items()
             if k not in ("note", "status_glance")}
    version = re.search(r'^version\s*=\s*"([^"]+)"', (root / "python" / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    operations = len(json.loads((root / "specifications" / "name-map.json").read_text(encoding="utf-8"))["operations"])
    contract = re.search(r'^CONTRACT\s*=\s*"([^"]+)"', (root / "conformance" / "runner" / "runner.py").read_text(encoding="utf-8"), re.M).group(1)
    suites = sorted((root / "datasets" / "golden").rglob("*.json"))
    cases = sum(len(json.loads(p.read_text(encoding="utf-8"))["cases"]) for p in suites)
    import case_figures
    by_class = case_figures.figures(root)
    sources = len(json.loads((root / "tools" / "recorder" / "sources.json").read_text(encoding="utf-8"))["sources"])
    stage_e = [c for p in sorted((root / "datasets" / "golden").glob("stage_e*/*.json")) for c in json.loads(p.read_text(encoding="utf-8"))["cases"]]
    counted = {"version": version, "stage_e_cases": f"{len(stage_e):,}", "stage_e_operations": str(len({c["operation"] for c in stage_e})),
               "operations": str(operations), "contract": contract}
    figures = {**counted, **facts, "golden_cases": f"{cases:,}", **by_class, "suite_files": str(len(suites)), "sources": str(sources),
               "stage_rows": stage_rows(roadmap_stages(root))}
    figures["status_glance"] = glance_html(glance_rows(figures, root))
    return figures


def glance_rows(figures, root=ROOT):
    """[(label, text)] for 'Status at a glance': rows from site_facts.json, {{name}} filled from the figures."""
    rows = json.loads((root / "tools" / "site_facts.json").read_text(encoding="utf-8"))["status_glance"]
    return [(label, render_home(text, figures)) for label, text in rows]


def glance_html(rows):
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    body = "\n".join(f"      <tr><th scope=\"row\">{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows)
    return f'<table class="glance">\n    <tbody>\n{body}\n    </tbody>\n  </table>'


GLANCE_BEGIN, GLANCE_END = "<!-- status-glance:begin -->", "<!-- status-glance:end -->"


def glance_markdown(rows):
    """The README block, between its markers. Generated: edit tools/site_facts.json, then tools/status_glance.py --write."""
    lines = [GLANCE_BEGIN, "",
             "Generated from `tools/site_facts.json` and counts from the tree by `tools/status_glance.py`; do not edit by hand.", "",
             "| | |", "|---|---|"]
    lines += [f"| **{k}** | {v.replace('|', '/')} |" for k, v in rows]
    return "\n".join(lines + ["", GLANCE_END])


def readme_glance_problem(root=ROOT):
    """'' if README.md carries the current block, else a one-line problem."""
    text = (root / "README.md").read_text(encoding="utf-8")
    if GLANCE_BEGIN not in text or GLANCE_END not in text:
        return "README.md has no Status at a glance block (run tools/status_glance.py --write)"
    have = text[text.index(GLANCE_BEGIN): text.index(GLANCE_END) + len(GLANCE_END)]
    want = glance_markdown(glance_rows(home_figures(root), root))
    return "" if have == want else "README.md Status at a glance is stale (run tools/status_glance.py --write)"


def roadmap_stages(root=ROOT):
    """[(stage, scope, status)] from the 'Stage status' table in ROADMAP.md, the single source for the home table."""
    text = (root / "ROADMAP.md").read_text(encoding="utf-8")
    sec = text.split("\n## Stage status", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in sec.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("Stage", "") or set(cells[0]) <= set("-: "):
            continue
        m = re.match(r"([A-Z][0-9]*(?:(?:, | to )[A-Z][0-9]*)*)\s*(.*)", cells[0])  # "B", "R6", "H, J, K"
        rows.append((m.group(1), m.group(2) or "", re.sub(r"`([^`]*)`", r"\1", cells[1])))
    if not rows:
        raise ValueError("ROADMAP.md: no rows in the Stage status table")
    return rows


def stage_rows(rows):
    """The home page's <tbody> rows (plan 13.2 E7: generated, so the home status cannot drift from ROADMAP)."""
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    return "\n".join(f'      <tr><td>{esc(st)}</td><td>{esc(scope)}</td><td>{esc(status)}. '
                     f'<a href="ROADMAP.html#stage-status">Details</a></td></tr>' for st, scope, status in rows)


def stage_span(done):
    """Done stages as runs of consecutive letters: ['A'..'G', 'I'] -> 'A to G and I'.

    Stages need not finish in letter order (stage I was built before H), so one 'first to
    last' range would claim a stage that is not done.
    """
    runs = []
    for st in sorted(done):
        if runs and ord(st) == ord(runs[-1][-1]) + 1:
            runs[-1].append(st)
        else:
            runs.append([st])
    parts = [r[0] if len(r) == 1 else f"{r[0]} to {r[-1]}" for r in runs]
    return " and ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else (parts[0] if parts else "")


def check_status(figures, rows):
    """Problems where site_facts.json disagrees with ROADMAP: implemented_stages must span the Done stages."""
    done = [st for st, _, status in rows if status.lower().startswith("done")]
    letters = [st for st in done if len(st) == 1]
    others = [st for st in done if len(st) > 1]  # repair rounds such as R6 have their own ROADMAP row
    want = stage_span(letters) + "".join(f", plus {st}" for st in others)
    have = figures.get("implemented_stages", "")
    return [] if have == want else [f"site_facts.json implemented_stages is '{have}', ROADMAP says '{want}'"]


def render_home(template, figures):
    """Fills {{name}} placeholders; an unknown name, or one left unfilled, is an error."""
    names = set(re.findall(r"\{\{(\w+)\}\}", template))
    missing = names - set(figures)
    if missing:
        raise ValueError(f"site_home.html: no value for {', '.join(sorted(missing))}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: figures[m.group(1)], template)
