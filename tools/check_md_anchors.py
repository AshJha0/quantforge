#!/usr/bin/env python3
"""Checks relative links and their #anchors in every tracked Markdown file. Standard library only.

    python tools/check_md_anchors.py            # every tracked .md
    python tools/check_md_anchors.py --site DIR # also every relative href in a built site (tools/build_site.py --out DIR)

tools/build_site.py fails on a relative link to a missing file but does not look at anchors. This script adds
that: an anchor must match a heading slug of the target page, made the way Python-Markdown's toc extension
(used by the site build) makes it, or an explicit id/name attribute in the page. GitHub makes most slugs the
same way; where they differ (a heading with punctuation such as "H-9"), the site build is the one checked.
Fenced code is ignored. Exit status: 0 clean; 1 problems found.
"""
import argparse
import re
import subprocess
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[(?:[^\]]|\][^(])*?\]\(([^)\s]+)\)")
FENCE = re.compile(r"^(```|~~~).*?^\1\s*$", re.M | re.S)
HEAD = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
EXPLICIT = re.compile(r"""<a\s+(?:name|id)=["']([^"']+)["']""")


def slug(text):
    """Python-Markdown toc slugify: strip markup, NFKD to ASCII, drop non-word characters, spaces to hyphens."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text).replace("*", "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def anchors(text):
    body = FENCE.sub("", text)
    out, seen = set(EXPLICIT.findall(body)), {}
    for h in HEAD.findall(body):
        s = slug(h)
        n = seen.get(s, 0)
        out.add(s if n == 0 else f"{s}_{n}")
        seen[s] = n + 1
    return out


def tracked():
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if (ROOT / p).is_file()]


def check_markdown(pages):
    cache, problems = {}, []
    for page in pages:
        text = FENCE.sub("", (ROOT / page).read_text(encoding="utf-8"))
        here = PurePosixPath(page).parent
        for target in LINK.findall(text):
            if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                continue
            path, _, anchor = target.partition("#")
            dest = page if not path else str(PurePosixPath(*(here / path).parts))
            resolved = (ROOT / dest).resolve()
            if not resolved.exists():
                problems.append(f"{page}: missing file {target}")
                continue
            if anchor and resolved.suffix == ".md":
                if resolved not in cache:
                    cache[resolved] = anchors(resolved.read_text(encoding="utf-8"))
                if anchor not in cache[resolved]:
                    problems.append(f"{page}: missing anchor {target}")
    return problems


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        for k in ("href", "src"):
            if a.get(k) and tag in ("a", "link", "script", "img"):
                self.hrefs.append(a[k])


def check_site(site):
    site = Path(site)
    parsed, problems = {}, []

    def load(p):
        if p not in parsed:
            r = _Refs()
            r.feed(p.read_text(encoding="utf-8", errors="replace"))
            parsed[p] = r
        return parsed[p]

    for page in sorted(site.rglob("*.html")):
        for href in load(page).hrefs:
            if re.match(r"[a-z][a-z0-9+.-]*:|//", href, re.I):
                continue
            path, _, anchor = href.partition("#")
            dest = page if not path else (page.parent / path).resolve()
            if not dest.exists():
                problems.append(f"{page.relative_to(site)}: missing {href}")
            elif anchor and dest.suffix == ".html" and anchor not in load(dest).ids:
                problems.append(f"{page.relative_to(site)}: missing anchor {href}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="also check a built site directory")
    a = ap.parse_args(argv)
    pages = tracked()
    problems = check_markdown(pages)
    print(f"markdown: {len(pages)} files, {len(problems)} problems")
    if a.site:
        site_problems = check_site(a.site)
        print(f"site: {len(site_problems)} problems")
        problems += site_problems
    for p in problems:
        print("BROKEN", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
