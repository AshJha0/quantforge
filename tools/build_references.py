#!/usr/bin/env python3
"""Builds docs/references.md, the bibliography, from the specs' own source lists. Standard library only.

    python tools/build_references.py           # write docs/references.md
    python tools/build_references.py --check   # fail if the committed page differs from the specs

Inputs are the "## Sources" section of every spec under specifications/ (bullets) and the source tables in
specifications/stage-e-sources.md. Each entry is copied as the spec writes it, status words included
("not opened", "licensed", "Read"), so this page never says more than the specs do. Identical entries cited
by several specs are merged, and each entry links to every spec that cites it. DOIs, arXiv ids and bare URLs
become links; nothing is looked up. tools/check_links.py checks the links' HTTP status.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specifications"
OUT = ROOT / "docs" / "references.md"
TOPICS = {
    "01-core": "Core: dates, calendars, numerics", "02-curves": "Curves", "03-calibration": "Calibration",
    "04-pricing": "Pricing", "05-volatility": "Volatility", "06-risk": "Risk and xVA", "07-portfolio": "Portfolio",
    "08-hedging": "Hedging", "09-microstructure": "Microstructure", "10-execution": "Execution",
    "11-research": "Research", "12-platform": "Platform", "": "Rulings and cross-cutting specs",
}
PAYWALL = re.compile(r"licen[cs]ed|paywall", re.I)
NOT_OPENED = re.compile(r"not opened", re.I)


def section(text, head="## Sources"):
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.strip() == head
            continue
        if inside:
            out.append(line)
    return out


def bullets(lines):
    """Top-level bullets, joining wrapped continuation lines."""
    items = []
    for line in lines:
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items and line.startswith("  ") and line.strip():
            items[-1] += " " + line.strip()
    return items


def e_rows(text):
    """Rows of the stage E source tables as 'Source. Cite. Status'."""
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 4 and cells[0] not in ("Model", "") and not set(cells[0]) <= set("-"):
            rows.append(f"{cells[1]}. Use: {cells[0]}. {cells[2]}. Status: {cells[3]}")
    return rows


def linkify(text):
    def doi(m):  # DOIs may hold balanced parentheses, e.g. 10.1016/0304-405X(76)90022-2
        d = m.group(1)
        while d and (d[-1] in ".;:" or (d[-1] == ")" and d.count(")") > d.count("("))):
            d = d[:-1]
        return f"[doi:{d}](https://doi.org/{d.replace('(', '%28').replace(')', '%29')})" + m.group(1)[len(d):]
    text = re.sub(r"(?<![\w/(\[])doi:\s?(10\.\d{4,9}/[^\s;,]+)", doi, text)
    text = re.sub(r"(?<![\w/(\[])arXiv:\s?(\d{4}\.\d{4,5}(?:v\d+)?)", r"[arXiv:\1](https://arxiv.org/abs/\1)", text)
    return re.sub(r"(?<![(<\[/])\b(https?://[^\s)>\]]+[^\s)>\].,;])", r"<\1>", text)


def strip_tag(entry):
    return re.sub(r"^\[[A-Z]?\d+[a-z]?\]\s*", "", entry).strip()


def collect():
    found = {}  # (topic, entry) -> set of spec paths
    for path in sorted(SPECS.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        parts = path.relative_to(SPECS).parts
        topic = parts[0] if len(parts) > 1 else ""
        entries = [strip_tag(b) for b in bullets(section(text))]
        if path.name == "stage-e-sources.md":
            entries += e_rows(text)
        for e in entries:
            if len(e) > 12:
                found.setdefault((topic, e), set()).add(rel)
    return found


def render(found):
    by_topic = {}
    for (topic, entry), used in found.items():
        by_topic.setdefault(topic, []).append((entry, sorted(used)))
    n = len(found)
    paid = sum(1 for _, e in found if PAYWALL.search(e))
    unopened = sum(1 for _, e in found if NOT_OPENED.search(e))
    out = ["# References", "",
           "Every source the specifications cite, grouped by topic. Each entry is copied from the spec that cites it, with that "
           "spec's own status words, and links back to every spec that relies on it. Nothing here is added from memory.", "",
           "How to read the marks:", "",
           '- **Not opened** means the spec gives the usual citation from memory, and nobody has re-read the source for this project. '
           "Confirm it before relying on it.",
           "- **Paywalled** marks an entry the spec calls licensed: a person with access must confirm section or equation numbers.",
           "- DOI and arXiv links are formed from the identifiers the specs give. `tools/check_links.py` checks their HTTP status; "
           "run it by hand, as it needs the network (see `tools/README.md`).", "",
           f"{n} entries: {unopened} marked Not opened, {paid} marked Paywalled (the spec calls them licensed or paywalled). "
           "Built by `python tools/build_references.py` from `specifications/`; CI fails if this page is out of date.", ""]
    for topic in sorted(by_topic, key=lambda t: (t == "", t)):
        out += [f"## {TOPICS.get(topic, topic)}", ""]
        for entry, used in sorted(by_topic[topic], key=lambda x: x[0].lower()):
            marks = []
            if NOT_OPENED.search(entry):
                marks.append("**Not opened.**")
            if PAYWALL.search(entry):
                marks.append("**Paywalled.**")
            if marks and entry.endswith(" (not opened)"):  # the bold mark already says it
                entry = entry.removesuffix(" (not opened)")
            refs = ", ".join(f"[`{u.removeprefix('specifications/')}`](../{u})" for u in used)
            out.append(f"- {' '.join(marks) + ' ' if marks else ''}{linkify(entry).rstrip('.')}. Cited by {refs}.")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = render(collect())
    if a.check:
        ok = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("references: up to date" if ok else "references: docs/references.md differs; run python tools/build_references.py")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"references: {text.count(chr(10) + '- ')} entries written to {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
