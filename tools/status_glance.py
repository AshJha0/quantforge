#!/usr/bin/env python3
"""Writes or checks the README "Status at a glance" block. Standard library only.

    python tools/status_glance.py --write   # replace the block between the status-glance markers in README.md
    python tools/status_glance.py --check   # exit 1 if README.md is stale (tools/build_site.py runs the same check)

The rows live in tools/site_facts.json ("status_glance"); numbers come from the tree (golden counts, the name
map, the runner's contract) or from site_facts.json, never typed into README. The site home renders the same
rows through the {{status_glance}} placeholder in tools/site_home.html.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_figures import GLANCE_BEGIN, GLANCE_END, ROOT, glance_markdown, glance_rows, home_figures, readme_glance_problem  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        problem = readme_glance_problem()
        print(problem or "README.md Status at a glance is current")
        return 1 if problem else 0
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    if GLANCE_BEGIN not in text:
        raise SystemExit("README.md: add the two status-glance marker lines where the block belongs")
    block = glance_markdown(glance_rows(home_figures()))
    text = text[: text.index(GLANCE_BEGIN)] + block + text[text.index(GLANCE_END) + len(GLANCE_END):]
    path.write_text(text, encoding="utf-8", newline="\n")
    print("README.md Status at a glance written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
