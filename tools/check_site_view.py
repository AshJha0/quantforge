#!/usr/bin/env python3
"""G10 site check in a headless browser (plan 12.7 G10, plan 14.8 K-7 check RE9, ruling KR-227, confirmed 2026-11-20).

    uv run --no-project --with playwright==1.64.1 python tools/check_site_view.py --site site [--shard 1/4]
        every page of the built site at 1280 px (light), 375 px (light) and 375 px (dark); writes site-view*.json/.md
    uv run --no-project --with playwright==1.64.1 python tools/check_site_view.py --self-test
        a page with a 600 px element and a page with a broken Mermaid block must fail; a plain page must pass
    python tools/check_site_view.py --merge DIR       one table from the shard files in DIR (standard library only)
    python tools/check_site_view.py --dark-copy SRC DST   a copy of the site with the dark colours forced on, for
                                                          the pa11y AA run in dark mode (standard library only)

Plain idea: a page that is wider than a phone makes the reader scroll sideways. The check opens every page of the
built site the way a reader would, at desktop width and at phone width, in light and dark mode, and measures how
wide the page is. It also fails a page whose Mermaid diagram did not render, because a diagram that shows an
error box is a broken page too.

Formal statement. For every .html file under --site (or every n-th one for --shard i/n), served over HTTP from
127.0.0.1 and opened in Chromium through Playwright (`--channel chrome` uses the installed Google Chrome, so no
browser is downloaded), with each view in VIEWS:
- `document.documentElement.scrollWidth <= viewport width` (KR-227 states it for 375 px; it is also checked at
  1280 px, which is stricter than the ruling, not looser);
- every Mermaid box (`.mermaid`, built by tools/build_site.py from ```mermaid blocks) holds an <svg> and no
  "Syntax error" text once Mermaid has run (wait up to 20 s);
- the page loaded with HTTP status 200.
Exit 0 if and only if every page passes in every view. A failing page is never skipped or excluded: it is fixed
in the site templates or listed in docs/known-issues.md with its measured width.

The pa11y AA part of KR-227 is the existing pa11y-ci run of docs.yml (.pa11yci.json), run a second time on the
copy written by --dark-copy, where the site's `prefers-color-scheme: dark` rules are applied unconditionally and
Mermaid is told the page is dark. --dark-copy fails if it finds no dark rule to force, so a change to the CSS
cannot silently turn the dark run into a second light run.

Worked example: the self-test serves three pages. `plain.html` is 375 px wide at phone width and passes;
`wide.html` holds `<div style="width:600px">` and fails at 375 px with scrollWidth 600 (KR-227's planted fault);
`good-mermaid.html` holds a valid two-node flowchart and passes, which shows Mermaid loaded;
`broken-mermaid.html` holds a block that Mermaid cannot parse and fails in every view. The self-test needs
Mermaid from the CDN (network), like the site itself.

What it does not check: contrast and other WCAG rules (pa11y does that); how a page looks (screenshots of the
main pages are written with --screenshots for a person to look at). Evidence class of its output: measured.
"""
import argparse
import functools
import http.server
import json
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = (("desktop-light", 1280, 900, "light"), ("phone-light", 375, 812, "light"), ("phone-dark", 375, 812, "dark"))
SCREENSHOT_PAGES = ("index.html", "LEARN.html", "COOKBOOK.html", "docs/curves/README.html",
                    "docs/diagrams/README.html")
MERMAID_WAIT_MS = 20000
MEASURE = """() => {
  const vw = window.innerWidth;
  const sw = document.documentElement.scrollWidth;
  const wide = [];
  if (sw > vw) {
    for (const el of document.body.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.right > vw + 0.5 && el.offsetParent !== null) {
        let p = el.parentElement, clipped = false;
        while (p && p !== document.body) {
          const s = getComputedStyle(p);
          if (s.overflowX === 'auto' || s.overflowX === 'scroll' || s.overflowX === 'hidden') { clipped = true; break; }
          p = p.parentElement;
        }
        if (!clipped) {
          wide.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
                    (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '') +
                    ' right=' + Math.round(r.right));
          if (wide.length >= 3) break;
        }
      }
    }
  }
  const boxes = Array.from(document.querySelectorAll('.mermaid'));
  const badMermaid = boxes.filter(b => !b.querySelector('svg') || /Syntax error/i.test(b.textContent)).length;
  return {viewport: vw, scrollWidth: sw, wide: wide, mermaid: boxes.length, mermaidBad: badMermaid};
}"""
MERMAID_DONE = """() => Array.from(document.querySelectorAll('.mermaid'))
  .every(b => b.getAttribute('data-processed') || b.querySelector('svg'))"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(directory):
    """An HTTP server for `directory` on a free 127.0.0.1 port, in a daemon thread."""
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def pages(site, shard=None):
    found = sorted(p.relative_to(site).as_posix() for p in Path(site).rglob("*.html"))
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        if not 1 <= i <= n:
            raise SystemExit(f"--shard {shard}: need 1 <= i <= n")
        found = found[i - 1::n]
    return found


def check_pages(site, rel_pages, channel=None, screenshots=None):
    """{page: {view: result}} for every page and view; result has ok, scrollWidth, wide, mermaid, problems."""
    from playwright.sync_api import sync_playwright  # imported here so --merge and --dark-copy need no Playwright
    srv, base = serve(site)
    out = {p: {} for p in rel_pages}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel=channel) if channel else pw.chromium.launch()
            try:
                for view, w, h, scheme in VIEWS:
                    ctx = browser.new_context(viewport={"width": w, "height": h}, color_scheme=scheme,
                                              is_mobile=w < 768, has_touch=w < 768,
                                              device_scale_factor=1 if w >= 768 else 2)
                    page = ctx.new_page()
                    for rel in rel_pages:
                        problems = []
                        try:
                            resp = page.goto(f"{base}/{rel}", wait_until="load", timeout=60000)
                            if resp is None or resp.status != 200:
                                problems.append(f"HTTP {resp.status if resp else 'none'}")
                            if page.locator(".mermaid").count():
                                try:
                                    page.wait_for_function(MERMAID_DONE, timeout=MERMAID_WAIT_MS)
                                except Exception:
                                    problems.append(f"Mermaid did not finish in {MERMAID_WAIT_MS // 1000} s")
                            m = page.evaluate(MEASURE)
                        except Exception as e:  # a page that cannot be measured fails; it is not skipped
                            out[rel][view] = {"ok": False, "problems": [f"not measured: {str(e)[:200]}"]}
                            continue
                        if m["scrollWidth"] > w:
                            problems.append(f"scrollWidth {m['scrollWidth']} > {w}"
                                            + (f" (widest: {'; '.join(m['wide'])})" if m["wide"] else ""))
                        if m["mermaidBad"]:
                            problems.append(f"{m['mermaidBad']} of {m['mermaid']} Mermaid diagrams did not render")
                        out[rel][view] = {"ok": not problems, "scrollWidth": m["scrollWidth"],
                                          "mermaid": m["mermaid"], "problems": problems}
                        if screenshots and rel in SCREENSHOT_PAGES:
                            Path(screenshots).mkdir(parents=True, exist_ok=True)
                            page.screenshot(path=str(Path(screenshots) / f"{rel.replace('/', '_')[:-5]}-{view}.png"),
                                            full_page=False)
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    return out


def summary(results, label):
    """Markdown the release notes can quote: counts per view, then every failing page with its measurement."""
    n = len(results)
    lines = [f"### Site check (G10, KR-227): {label}", "",
             f"{n} pages; views: " + ", ".join(f"{v} {w} px" for v, w, _, _ in VIEWS) + ". "
             "Measured with tools/check_site_view.py (Playwright, Chromium); pass means "
             "`document.documentElement.scrollWidth <= viewport width` and every Mermaid diagram rendered.", "",
             "| View | Pages passing | Pages failing |", "|---|---:|---:|"]
    for v, *_ in VIEWS:
        ok = sum(1 for r in results.values() if r.get(v, {}).get("ok"))
        lines.append(f"| {v} | {ok} | {n - ok} |")
    bad = [(p, v, r[v]["problems"]) for p, r in sorted(results.items()) for v, *_ in VIEWS
           if not r.get(v, {}).get("ok")]
    lines += ["", "Failing pages: none." if not bad else "Failing pages:", ""]
    lines += [f"- `{p}` {v}: {'; '.join(pr) or 'not measured'}" for p, v, pr in bad]
    return "\n".join(lines) + "\n", not bad


def merge(directory):
    results = {}
    files = sorted(Path(directory).glob("site-view*.json"))
    for f in files:
        results.update(json.loads(f.read_text(encoding="utf-8"))["pages"])
    md, ok = summary(results, f"{len(files)} shard file(s) merged")
    (Path(directory) / "site-view.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if ok and results else 1


DARK_CSS = re.compile(r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)")
DARK_JS = 'window.matchMedia("(prefers-color-scheme: dark)").matches'


def dark_copy(src, dst):
    src, dst = Path(src), Path(dst)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    css = js = 0
    for p in list(dst.rglob("*.html")) + list(dst.rglob("*.css")):
        t = p.read_text(encoding="utf-8")
        t2, k = DARK_CSS.subn("@media all", t)
        css += k
        js += t2.count(DARK_JS)
        t2 = t2.replace(DARK_JS, "true")
        if t2 != t:
            p.write_text(t2, encoding="utf-8")
    home = (dst / "index.html").read_text(encoding="utf-8") if (dst / "index.html").is_file() else ""
    if css == 0 or "@media all" not in home:
        print(f"dark copy: no `prefers-color-scheme: dark` rule found to force (home page included: "
              f"{'@media all' in home}); the dark run would test light colours", file=sys.stderr)
        return 1
    print(f"dark copy written to {dst}: {css} dark rules forced on, {js} Mermaid theme switches set to dark")
    return 0


GOOD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>plain</title></head>
<body><p>Plain text that wraps at any width.</p>
<div style="overflow-x:auto"><table><tr><td>%s</td></tr></table></div></body></html>"""
WIDE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>wide</title></head>
<body style="margin:0"><div style="width:600px">planted 600 px element</div></body></html>"""


def self_test(channel=None):
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "plain.html").write_text(GOOD % ("x " * 400), encoding="utf-8")
        (t / "wide.html").write_text(WIDE, encoding="utf-8")
        site_page = (ROOT / "tools" / "build_site.py").read_text(encoding="utf-8")
        mermaid = re.search(r'MERMAID = """(.*?)"""', site_page, re.S)
        if not mermaid:
            failures.append("could not read the MERMAID loader from tools/build_site.py")
        else:
            for name, block in (("good-mermaid.html", "flowchart LR\n  A[one] --&gt; B[two]\n"),
                                ("broken-mermaid.html", "flowchart LR\n  A --&gt;&gt;&gt; [B\n")):
                (t / name).write_text(
                    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
                    "content=\"width=device-width, initial-scale=1\"><title>m</title></head><body>"
                    "<pre><code class=\"language-mermaid\">" + block + "</code></pre>"
                    + mermaid.group(1) + "</body></html>", encoding="utf-8")
        r = check_pages(t, pages(t), channel=channel)
        for v, w, *_ in VIEWS:
            if not r["plain.html"][v]["ok"]:
                failures.append(f"plain page failed {v}: {r['plain.html'][v]['problems']}")
        for v, w, *_ in VIEWS:
            got = r["wide.html"][v]
            if w < 600 and (got["ok"] or got.get("scrollWidth", 0) < 600):
                failures.append(f"planted fault not caught: a 600 px element at {v} gave {got}")
            if w >= 600 and not got["ok"]:
                failures.append(f"600 px element failed at {v} where it fits: {got}")
        if "good-mermaid.html" in r:
            for v, *_ in VIEWS:
                if not r["good-mermaid.html"][v]["ok"]:
                    failures.append(f"a valid Mermaid block failed at {v} (Mermaid not loaded?): "
                                    f"{r['good-mermaid.html'][v]['problems']}")
        if "broken-mermaid.html" in r:
            for v, *_ in VIEWS:
                if r["broken-mermaid.html"][v]["ok"]:
                    failures.append(f"planted fault not caught: a broken Mermaid block passed at {v}")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "src").mkdir()
        (t / "src" / "index.html").write_text("<style>a{color:red}</style>", encoding="utf-8")
        if dark_copy(t / "src", t / "dst") == 0:
            failures.append("planted fault not caught: --dark-copy accepted a site with no dark rules")
        (t / "src" / "index.html").write_text("<style>@media(prefers-color-scheme:dark){a{color:red}}</style>",
                                              encoding="utf-8")
        if dark_copy(t / "src", t / "dst") != 0 or "@media all" not in (t / "dst" / "index.html").read_text():
            failures.append("--dark-copy did not force a dark rule on")
    if failures:
        print("self-test FAILED:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print("self-test: a plain page passes in every view; the planted 600 px element fails at 375 px; "
          "a valid Mermaid block renders and a broken one fails; --dark-copy refuses a site with no dark rule")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="the built site (tools/build_site.py --out DIR)")
    ap.add_argument("--shard", help="i/n: check every n-th page starting at the i-th (1-based)")
    ap.add_argument("--channel", default="chrome", help="Playwright browser channel (default chrome: the installed "
                    "Google Chrome; 'msedge' for Edge; '' for Playwright's own Chromium)")
    ap.add_argument("--out", default="site-view", help="directory for site-view*.json and .md")
    ap.add_argument("--screenshots", help="directory for screenshots of the main pages")
    ap.add_argument("--page", action="append", help="check only this page (relative path; repeatable)")
    ap.add_argument("--merge", metavar="DIR")
    ap.add_argument("--dark-copy", nargs=2, metavar=("SRC", "DST"))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    channel = a.channel or None
    if a.self_test:
        return self_test(channel)
    if a.merge:
        return merge(a.merge)
    if a.dark_copy:
        return dark_copy(*a.dark_copy)
    if not a.site:
        ap.error("--site, --merge, --dark-copy or --self-test")
    site = Path(a.site)
    rel = a.page or pages(site, a.shard)
    start = time.monotonic()
    results = check_pages(site, rel, channel=channel, screenshots=a.screenshots)
    seconds = time.monotonic() - start
    label = (f"shard {a.shard}" if a.shard else "all pages") + f", {len(rel)} pages, {seconds:.0f} s"
    md, ok = summary(results, label)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = "-" + a.shard.replace("/", "of") if a.shard else ""
    (out / f"site-view{tag}.json").write_text(json.dumps({"label": label, "views": VIEWS, "pages": results},
                                                         indent=1) + "\n", encoding="utf-8")
    (out / f"site-view{tag}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
