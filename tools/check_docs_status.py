#!/usr/bin/env python3
"""Docs status check: stale "Planned" curves and stale "pending release" wording. Standard library only.

Two checks, run by `python tools/quality_gate.py --check-docs`:

1. The status table in docs/curves/README.md. A row marked Planned fails if its text names an operation that
   exists in specifications/name-map.json (the work was done but the table was not updated). A row marked
   Implemented fails if an operation it names in backticks is not in the name map. And every curve-building
   operation in the name map (`*.curve`, `*.curve.*`, `*.bootstrap`, outside `rates.curve.*`, `risk.*`, `calib.*`)
   must be named on an Implemented row or on a page such a row links to, so a new curve cannot stay "Planned".
2. Release wording. CHANGELOG headings `## X.Y.Z: stage L, ...` map each stage to a version. For every stage whose
   version has a git tag (`vX.Y.Z`, or `vX.Y` for X.Y.0), a tracked Markdown line, or tools/site_facts.json, fails if it calls that
   version or that stage pending, unreleased or not yet tagged.
3. Operation names. A backticked name in a tracked Markdown page (not CHANGELOG, specifications/, review/ or
   program/) that starts with a known domain prefix and has two or more dots must be in the name map.

Without git tags (a shallow CI checkout) check 2 has nothing to compare and passes; CI fetches tags for it.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OP = re.compile(r"`([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)`")
STALE = re.compile(r"\b(pending|unreleased|not yet tagged|not yet released)\b", re.I)
HEADING = re.compile(r"^## v?(\d+\.\d+(?:\.\d+)?): stage ([A-K])\b", re.M)


def operations(root=ROOT):
    return set(json.loads((root / "specifications" / "name-map.json").read_text(encoding="utf-8"))["operations"])


def table_rows(text):
    """Rows of the first Markdown table under "## Status of every curve", as lists of cells."""
    rows, inside = [], False
    for line in text.splitlines():
        if line.startswith("## Status of every curve"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.startswith("|") and not line.startswith("|---"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]  # drop the header


def curve_table_problems(text, ops):
    bad = []
    rows = table_rows(text)
    if not rows:
        return ["docs/curves/README.md: no status table found"]
    for cells in rows:
        if len(cells) < 4:
            bad.append(f"curve row {cells[0]!r}: expected 4 cells")
            continue
        name, status, evidence = cells[0], cells[1], " ".join(cells[2:])
        named = OP.findall(name + " " + evidence)
        if status.startswith("Planned"):
            done = [o for o in named if o in ops]
            if done:
                bad.append(f"curve row {name!r} is Planned but names implemented operation(s) {', '.join(done)}")
        elif status.startswith("Implemented"):
            missing = [o for o in named if o not in ops]
            if missing:
                bad.append(f"curve row {name!r} is Implemented but {', '.join(missing)} is not in specifications/name-map.json")
    return bad


# A curve-building operation: a `.curve` or `.bootstrap` operation that builds a curve, not one that reads one.
CURVE_BUILDER = re.compile(r"^(?!rates\.curve\.|risk\.|calib\.)[a-z]+\.(?:[a-z_]+\.)?(?:curve(?:\.[a-z_]+)?|bootstrap|[a-z_]*_bootstrap)$")


def unlisted_curve_operations(pages, ops):
    """Curve-building operations named on no Implemented gallery page or row: work done that the table does not show.
    pages: {name: text} of the gallery README and the pages its Implemented rows link to."""
    text = "\n".join(pages.values())
    return [f"curve operation {o} is implemented but no Implemented curve row or page names it"
            for o in sorted(ops) if CURVE_BUILDER.match(o) and f"`{o}`" not in text]


def implemented_pages(readme, folder):
    pages = {"README.md": readme}
    for cells in table_rows(readme):
        m = re.match(r"\[[^\]]+\]\(([\w.-]+\.md)\)", cells[0])
        if m and len(cells) > 1 and cells[1].startswith("Implemented") and (folder / m.group(1)).is_file():
            pages[m.group(1)] = (folder / m.group(1)).read_text(encoding="utf-8")
    return pages


def unknown_operations(files, ops):
    """Backticked names that look like operations (a known domain prefix and two or more dots) but are not in the name map."""
    prefixes = {o.split(".")[0] for o in ops}
    bad = []
    for path, text in files.items():
        if path == "CHANGELOG.md" or path.startswith(("specifications/", "review/", "program/")):
            continue  # history, and specs may name operations before they exist
        for n, line in enumerate(text.splitlines(), 1):
            for name in OP.findall(line):
                if name.count(".") >= 2 and name.split(".")[0] in prefixes and name not in ops:
                    bad.append(f"{path}:{n}: `{name}` is not an operation in specifications/name-map.json")
    return bad


def released_stages(changelog, tags):
    """{stage letter: version} for each CHANGELOG stage heading whose version is tagged."""
    tagged = {t.lstrip("v") for t in tags} | {t.lstrip("v") + ".0" for t in tags}  # tag v0.4 is release 0.4.0
    return {stage: ver for ver, stage in HEADING.findall(changelog) if ver in tagged}


def release_problems(files, released):
    """files: {path: text}. Flags lines calling a released version or stage pending or unreleased."""
    bad = []
    pats = []
    for stage, ver in released.items():
        pats.append(re.compile(rf"(?<![\d.])v?{re.escape(ver)}(?![\d.])"))
        pats.append(re.compile(rf"\bstage {stage}\b(?![-\w])"))
    heads = [re.compile(rf"^## v?{re.escape(ver)}:") for ver in released.values()]
    for path, text in files.items():
        for n, line in enumerate(text.splitlines(), 1):
            if path == "CHANGELOG.md" and not any(h.search(line) for h in heads):
                continue  # the changelog is history: only a released version's own heading must not say unreleased
            m = STALE.search(line)
            if m and any(p.search(line) for p in pats):
                bad.append(f"{path}:{n}: calls a released version or stage {m.group(1)!r}: {line.strip()[:120]}")
    return bad


def git(*args, root=ROOT):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.split("\n")


def docs_files(root=ROOT):
    names = [n for n in git("ls-files", "*.md", root=root) if n] + ["tools/site_facts.json"]
    return {n: (root / n).read_text(encoding="utf-8") for n in names if (root / n).is_file()}


def main():
    folder, ops = ROOT / "docs" / "curves", operations()
    readme = (folder / "README.md").read_text(encoding="utf-8")
    bad = curve_table_problems(readme, ops) + unlisted_curve_operations(implemented_pages(readme, folder), ops)
    tags = [t for t in git("tag", "-l", "v*") if t]
    released = released_stages((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), tags)
    files = docs_files()
    bad += release_problems(files, released) + unknown_operations(files, ops)
    for b in bad:
        print("BAD", b)
    print(f"docs status: curve table checked; {len(tags)} release tags, stages released {''.join(sorted(released)) or 'none found'}; {len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
