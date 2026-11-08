"""Figures for the site home, tools/site_home.html, from one place. Standard library only.

Release facts come from tools/site_facts.json; the version and counts are read from the tree, so a
release edits site_facts.json and nothing else on the home page. Used by tools/build_site.py.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def home_figures(root=ROOT):
    """Values for the site home: release facts from tools/site_facts.json, the rest counted from the tree."""
    facts = {k: v for k, v in json.loads((root / "tools" / "site_facts.json").read_text(encoding="utf-8")).items() if k != "note"}
    version = re.search(r'^version\s*=\s*"([^"]+)"', (root / "python" / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    suites = sorted((root / "datasets" / "golden").rglob("*.json"))
    cases = sum(len(json.loads(p.read_text(encoding="utf-8"))["cases"]) for p in suites)
    sources = len(json.loads((root / "tools" / "recorder" / "sources.json").read_text(encoding="utf-8"))["sources"])
    return {**facts, "version": version, "golden_cases": f"{cases:,}", "suite_files": str(len(suites)), "sources": str(sources)}


def render_home(template, figures):
    """Fills {{name}} placeholders; an unknown name, or one left unfilled, is an error."""
    names = set(re.findall(r"\{\{(\w+)\}\}", template))
    missing = names - set(figures)
    if missing:
        raise ValueError(f"site_home.html: no value for {', '.join(sorted(missing))}")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: figures[m.group(1)], template)
