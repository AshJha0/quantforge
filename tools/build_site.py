#!/usr/bin/env python3
"""Builds a plain static site from the repository's tracked Markdown. Run from anywhere:

    uv run --no-project --with markdown==3.11.2 python tools/build_site.py [--out site]

Every page keeps its repository path, with .html in place of .md. A relative link to a file that
does not exist fails the build. A link to a repository file that is not Markdown is not part of the
site, so it becomes plain code text. Exit status: 0 built; 1 broken links.
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import markdown

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_figures import check_status, home_figures, render_home, roadmap_stages  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LEFT_OUT = (".github/",)
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
FENCE = re.compile(r"^(```|~~~).*?^\1\s*$", re.M | re.S)
# Colours meet WCAG 2.2 AA (plan 13.2 E6): white on --accent 5.1:1, white on --brand 6.3:1, --link on --bg 5.9:1,
# --c2 on --bg 5.4:1, dark --link on dark --bg 9.2:1.
CSS = """:root{--bg:#f7f8fa;--ink:#1a1a2e;--brand:#16697a;--accent:#0e7c66;--line:#d9dee3;--panel:#fff;--code:#eef1f4;--link:#16697a;--c1:#16697a;--c2:#a84a12;--focus:#c2571a}
@media(prefers-color-scheme:dark){:root{--bg:#14181d;--ink:#e3e6ea;--brand:#16697a;--accent:#0e7c66;--line:#333b44;--panel:#1d232a;--code:#232a32;--link:#6fc7d6;--c1:#6fc7d6;--c2:#e8935a;--focus:#f0b27a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 "Segoe UI",Arial,sans-serif}
a{color:var(--link)}.inner,.wrap{max-width:68rem;margin:0 auto;padding-left:2rem;padding-right:2rem}.wrap{padding-top:1.5rem;padding-bottom:3rem}
.hero{background:var(--brand);color:#fff;padding:3rem 0}.hero h1{font-size:2.2rem;margin:0 0 .75rem}.hero p{max-width:50rem;margin:0 0 1.25rem}
.buttons{display:flex;flex-wrap:wrap;gap:.6rem}.buttons a{background:var(--accent);color:#fff;padding:.55rem 1.1rem;border-radius:4px;text-decoration:none}
.buttons a.quiet{background:rgba(0,0,0,.28)}.buttons a:hover{filter:brightness(1.1)}
.bar{background:var(--brand);padding:.6rem 0}.bar .inner{display:flex;flex-wrap:wrap;gap:.3rem 1.2rem}.bar a{color:#fff;text-decoration:none}.bar a:first-child{font-weight:600;margin-right:auto}
h1,h2,h3{line-height:1.25}h2{color:var(--link);border-bottom:2px solid var(--line);padding-bottom:.3rem;margin-top:2rem}
.note{background:var(--panel);border-left:4px solid var(--accent);padding:.7rem 1rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(14rem,1fr));gap:1rem;margin:1rem 0}
.card{background:var(--panel);border-radius:6px;padding:1rem 1.2rem;box-shadow:0 1px 3px rgba(0,0,0,.12)}.card b{display:block}.card span{font-size:.92rem}
pre{background:var(--code);padding:.8rem;overflow-x:auto;border-radius:4px}code{font-size:.92em;overflow-wrap:anywhere}pre code{overflow-wrap:normal}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:1rem 0}th,td{border:1px solid var(--line);padding:.45rem .7rem;text-align:left}th{background:var(--code)}
.chart{max-width:42rem;margin:1.2rem 0}.chart svg{display:block;width:100%;height:auto}.chart p{font-size:.85rem;margin:.3rem 0 0}
.mermaid{background:var(--panel);border-radius:4px;padding:.5rem;overflow-x:auto;text-align:center}
.skip{position:absolute;left:-999px;top:.5rem;background:var(--panel);color:var(--link);padding:.5rem 1rem;z-index:10}.skip:focus{left:.5rem}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}.bar a[aria-current=page]{text-decoration:underline;text-underline-offset:.3em}
.search{position:relative;margin:0}.search input{font:inherit;padding:.1rem .5rem;border-radius:4px;border:1px solid var(--line);width:11rem;background:var(--panel);color:var(--ink)}
.search ul{position:absolute;right:0;top:2rem;z-index:5;list-style:none;margin:0;padding:.3rem 0;background:var(--panel);border:1px solid var(--line);border-radius:4px;width:24rem;max-width:90vw;max-height:60vh;overflow:auto}
.search li{padding:.3rem .8rem}.search li a{display:block;color:var(--link)}.search li small{display:block;color:var(--ink);font-size:.8rem}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
body{overflow-wrap:break-word}p,li,td,th,dd,.card{overflow-wrap:anywhere}.wrap{min-width:0}td code,li code,p code{word-break:break-all}
@media(max-width:48rem){.inner,.wrap{padding-left:1rem;padding-right:1rem}.hero{padding:2rem 0}table{display:block;overflow-x:auto}}
"""
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - QuantForge</title><link rel="stylesheet" href="{up}style.css"></head>
<body><a class="skip" href="#main">Skip to content</a>
{nav}
<main id="main" class="wrap">
{body}
</main>
<script src="{up}search.js" defer></script>
</body></html>
"""
NAV = (("index.html", "QuantForge"), ("LEARN.html", "Learn"), ("COOKBOOK.html", "Cookbook"),
       ("docs/curves/README.html", "Curves"), ("ARCHITECTURE.html", "Architecture"),
       ("docs/diagrams/README.html", "Diagrams"), ("all-pages.html", "All pages"))
SEARCH_FORM = ('<form class="search" role="search" onsubmit="return false"><label class="sr-only" for="q">Search the site</label>'
               '<input id="q" type="search" placeholder="Search" autocomplete="off" aria-controls="hits">'
               '<ul id="hits" aria-live="polite" hidden></ul></form>')


def nav(here, up):
    """The top bar for the page at site path `here`; the current page's link carries aria-current="page"."""
    links = "".join(f'<a href="{up}{href}"' + (' aria-current="page"' if href == here else "") + f">{name}</a>"
                    for href, name in NAV)
    return f'<nav class="bar" aria-label="Main"><div class="inner">{links}{SEARCH_FORM}</div></nav>'


# Client-side search (plan 13.2 E7): search.json holds url, title and plain text per page; search.js ranks pages
# by query words found, a title hit counting ten times a body hit. No server, no third-party service.
SEARCH_JS = r"""(function () {
  var q = document.getElementById("q"), hits = document.getElementById("hits");
  if (!q) return;
  var base = document.currentScript.src.replace(/search\.js$/, ""), index = null;
  function load(cb) {
    if (index) return cb();
    fetch(base + "search.json").then(function (r) { return r.json(); }).then(function (d) { index = d; cb(); });
  }
  function run() {
    var words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    hits.textContent = "";
    if (!words.length) { hits.hidden = true; return; }
    var scored = index.map(function (p) {
      var t = p.t.toLowerCase(), x = p.x.toLowerCase(), s = 0;
      words.forEach(function (w) { if (t.indexOf(w) >= 0) s += 10; if (x.indexOf(w) >= 0) s += 1; });
      return [s, p];
    }).filter(function (e) { return e[0] > 0; }).sort(function (a, b) { return b[0] - a[0]; }).slice(0, 12);
    scored.forEach(function (e) {
      var li = document.createElement("li"), a = document.createElement("a"), sm = document.createElement("small");
      a.href = base + e[1].u; a.textContent = e[1].t; sm.textContent = e[1].u;
      a.appendChild(sm); li.appendChild(a); hits.appendChild(li);
    });
    if (!scored.length) { var li = document.createElement("li"); li.textContent = "No match"; hits.appendChild(li); }
    hits.hidden = false;
  }
  q.addEventListener("input", function () { load(run); });
  q.addEventListener("keydown", function (e) { if (e.key === "Escape") { q.value = ""; hits.hidden = true; } });
})();
"""


def search_entry(url, title, text):
    plain = re.sub(r"```.*?```", " ", text, flags=re.S)
    plain = re.sub(r"<[^>]+>|[#*`|>\[\]()_]+", " ", plain)
    return {"u": url, "t": title, "x": re.sub(r"\s+", " ", plain).strip()[:6000]}


def search(index, query):
    """The ranking search.js uses, for tests: urls with any query word, best first."""
    words = query.lower().split()
    scored = [(-sum(10 * (w in p["t"].lower()) + (w in p["x"].lower()) for w in words), p["u"]) for p in index]
    return [u for s, u in sorted(scored) if s]


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
mermaid.initialize({ startOnLoad: false, securityLevel: "strict",
  theme: window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default" });
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
    known, broken, listing, index = set(pages), [], [], []
    for page in pages:
        text = (ROOT / page).read_text(encoding="utf-8")
        title = title_of(text, page)
        body = markdown.markdown(fix_links(text, page, known, broken), extensions=["tables", "fenced_code", "toc"])
        if "language-mermaid" in body:
            body += MERMAID
        target = out / (page[:-3] + ".html")
        target.parent.mkdir(parents=True, exist_ok=True)
        up = "../" * page.count("/")
        here = page[:-3] + ".html"
        target.write_text(PAGE.format(title=html.escape(title), up=up, body=body, nav=nav(here, up)), encoding="utf-8")
        listing.append((page, title))
        index.append(search_entry(here, title, text))
    figures = home_figures()
    stale = check_status(figures, roadmap_stages())  # plan 13.2 E7: home status must match ROADMAP
    home = render_home((ROOT / "tools" / "site_home.html").read_text(encoding="utf-8"), {**figures, "nav": nav("index.html", "")})
    (out / "index.html").write_text(home, encoding="utf-8")
    rows = "\n".join(f'<li><a href="{p[:-3]}.html">{html.escape(p)}</a>: {html.escape(t)}</li>' for p, t in listing)
    (out / "all-pages.html").write_text(PAGE.format(title="All pages", up="", body=f"<h1>All pages</h1><ul>{rows}</ul>",
                                                    nav=nav("all-pages.html", "")), encoding="utf-8")
    (out / "search.js").write_text(SEARCH_JS, encoding="utf-8")
    (out / "search.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    for row in stale:
        print("STATUS", row)
    print(f"{len(pages)} pages written to {out}; {len(broken)} broken links")
    for row in broken:
        print("BROKEN", row)
    return 1 if broken or stale else 0


if __name__ == "__main__":
    sys.exit(main())
