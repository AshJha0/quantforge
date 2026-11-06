#!/usr/bin/env python3
"""Builds a plain static site from the repository's tracked Markdown. Run from anywhere:

    uv run --no-project --with markdown==3.11.2 python tools/build_site.py [--out site]

Every page keeps its repository path, with .html in place of .md. A relative link to a file that
does not exist fails the build. A link to a repository file that is not Markdown is not part of the
site, so it becomes plain code text. Exit status: 0 built; 1 broken links.
"""
import argparse
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import markdown

ROOT = Path(__file__).resolve().parents[1]
LEFT_OUT = (".github/",)
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
FENCE = re.compile(r"^(```|~~~).*?^\1\s*$", re.M | re.S)
CSS = """body{max-width:52rem;margin:0 auto;padding:1rem;font:16px/1.55 system-ui,sans-serif;color:#222}
pre{background:#f4f4f4;padding:.7rem;overflow-x:auto}code{font-size:.92em}
table{border-collapse:collapse;display:block;overflow-x:auto}th,td{border:1px solid #ccc;padding:.25rem .5rem}
nav{border-bottom:1px solid #ccc;padding-bottom:.5rem;margin-bottom:1rem}
@media(prefers-color-scheme:dark){body{background:#181818;color:#ddd}a{color:#8ab4f8}pre{background:#262626}}
"""
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - QuantForge</title><link rel="stylesheet" href="{up}style.css"></head>
<body><nav><a href="{up}index.html">Home</a> | <a href="{up}all-pages.html">All pages</a></nav>
{body}
</body></html>
"""


def tracked():
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if not p.startswith(LEFT_OUT) and (ROOT / p).is_file()]


MERMAID = """<script src="https://cdn.jsdelivr.net/npm/mermaid@12.3.0/dist/mermaid.min.js" integrity="sha384-HHW54r639fK42Ip0coGF3mz8oSiGn0eEoWNTLs75X7H63pLSDBa0Tqs0RwGmLlXE" crossorigin="anonymous"></script>
<script>
document.querySelectorAll("pre > code.language-mermaid").forEach(function (code) {
  var box = document.createElement("div");
  box.className = "mermaid";
  box.textContent = code.textContent;
  code.parentElement.replaceWith(box);
});
mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
mermaid.run();
</script>
"""


def fix_links(text, page, pages, broken):
    """Rewrites the links of one page, leaving fenced code alone."""
    here = PurePosixPath(page).parent

    def one(m):
        label, target = m.group(1), m.group(2)
        if re.match(r"[a-z][a-z0-9+.-]*:|#", target, re.I):
            return m.group(0)
        path, _, anchor = target.partition("#")
        parts = []
        for part in (here / path).parts:
            if part == "..":
                if not parts:
                    broken.append(f"{page}: {target} leaves the repository")
                    return m.group(0)
                parts.pop()
            elif part != ".":
                parts.append(part)
        resolved = "/".join(parts)
        if not (ROOT / resolved).exists():
            broken.append(f"{page}: {target}")
            return m.group(0)
        if resolved in pages:
            return f"[{label}]({path[:-3]}.html{'#' + anchor if anchor else ''})"
        return label if label.startswith("`") else f"`{label}`"

    out, at = [], 0
    for fence in FENCE.finditer(text):
        out += [LINK.sub(one, text[at:fence.start()]), fence.group(0)]
        at = fence.end()
    return "".join(out + [LINK.sub(one, text[at:])])


def title_of(text, fallback):
    m = re.search(r"^# (.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "site"))
    a = ap.parse_args()
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    (out / "style.css").write_text(CSS, encoding="utf-8")
    pages = tracked()
    known, broken, listing = set(pages), [], []
    for page in pages:
        text = (ROOT / page).read_text(encoding="utf-8")
        title = title_of(text, page)
        body = markdown.markdown(fix_links(text, page, known, broken), extensions=["tables", "fenced_code", "toc"])
        if "language-mermaid" in body:
            body += MERMAID
        target = out / (page[:-3] + ".html")
        target.parent.mkdir(parents=True, exist_ok=True)
        up = "../" * page.count("/")
        target.write_text(PAGE.format(title=html.escape(title), up=up, body=body), encoding="utf-8")
        listing.append((page, title))
    shutil.copy(out / "README.html", out / "index.html")
    rows = "\n".join(f'<li><a href="{p[:-3]}.html">{html.escape(p)}</a>: {html.escape(t)}</li>' for p, t in listing)
    (out / "all-pages.html").write_text(PAGE.format(title="All pages", up="", body=f"<h1>All pages</h1><ul>{rows}</ul>"),
                                        encoding="utf-8")
    print(f"{len(pages)} pages written to {out}; {len(broken)} broken links")
    for row in broken:
        print("BROKEN", row)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
