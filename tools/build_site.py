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
CSS = """:root{--bg:#f7f8fa;--ink:#1a1a2e;--brand:#16697a;--accent:#16a085;--line:#d9dee3;--panel:#fff;--code:#eef1f4;--link:#16697a}
@media(prefers-color-scheme:dark){:root{--bg:#14181d;--ink:#e3e6ea;--brand:#16697a;--accent:#16a085;--line:#333b44;--panel:#1d232a;--code:#232a32;--link:#6fc7d6}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 "Segoe UI",Arial,sans-serif}
a{color:var(--link)}.wrap{max-width:60rem;margin:0 auto;padding:1.5rem 1rem 3rem}
.hero{background:var(--brand);color:#fff;padding:3rem 2rem}.hero h1{font-size:2.2rem;margin:0 0 .75rem}.hero p{max-width:50rem;margin:0 0 1.25rem}
.buttons{display:flex;flex-wrap:wrap;gap:.6rem}.buttons a{background:var(--accent);color:#fff;padding:.55rem 1.1rem;border-radius:4px;text-decoration:none}
.buttons a.quiet{background:rgba(255,255,255,.18)}.buttons a:hover{filter:brightness(1.1)}
.bar{background:var(--brand);padding:.6rem 1rem;display:flex;flex-wrap:wrap;gap:1rem}.bar a{color:#fff;text-decoration:none}.bar a:first-child{font-weight:600}
h1,h2,h3{line-height:1.25}h2{color:var(--link);border-bottom:2px solid var(--line);padding-bottom:.3rem;margin-top:2rem}
.note{background:var(--panel);border-left:4px solid var(--accent);padding:.7rem 1rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.8rem}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:.8rem 1rem}.card b{display:block}.card span{font-size:.92rem}
pre{background:var(--code);padding:.8rem;overflow-x:auto;border-radius:4px}code{font-size:.92em}
table{border-collapse:collapse;display:block;overflow-x:auto;font-size:.9rem;margin:1rem 0}th,td{border:1px solid var(--line);padding:.45rem .7rem;text-align:left}th{background:var(--code)}
.mermaid{background:#fff;border-radius:4px;padding:.5rem;overflow-x:auto}
"""
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - QuantForge</title><link rel="stylesheet" href="{up}style.css"></head>
<body><nav class="bar"><a href="{up}index.html">QuantForge</a><a href="{up}LEARN.html">Learn</a><a href="{up}COOKBOOK.html">Cookbook</a><a href="{up}ARCHITECTURE.html">Architecture</a><a href="{up}docs/diagrams/README.html">Diagrams</a><a href="{up}all-pages.html">All pages</a></nav>
<div class="wrap">
{body}
</div>
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
    shutil.copy(ROOT / "tools" / "site_home.html", out / "index.html")
    rows = "\n".join(f'<li><a href="{p[:-3]}.html">{html.escape(p)}</a>: {html.escape(t)}</li>' for p, t in listing)
    (out / "all-pages.html").write_text(PAGE.format(title="All pages", up="", body=f"<h1>All pages</h1><ul>{rows}</ul>"),
                                        encoding="utf-8")
    print(f"{len(pages)} pages written to {out}; {len(broken)} broken links")
    for row in broken:
        print("BROKEN", row)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
