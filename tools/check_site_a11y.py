#!/usr/bin/env python3
"""pa11y AA on every page of the built site, light and dark (plan 14.8 K-7 check RE9, ruling KR-227 read strictly by
the coordinator on 2026-11-20). Standard library only; pa11y-ci itself runs in CI (docs.yml job docs-site-a11y).

    python tools/check_site_a11y.py --urls --site site --shard 2/6 --mode dark --base http://127.0.0.1:8001 --out DIR
        writes DIR/pa11y-<mode>-<i>of<n>.json (a pa11y-ci config for every page of the shard) and
        DIR/a11y-<mode>-<i>of<n>.expected.json (the pages the shard must report on, and the site's page count)
    python tools/check_site_a11y.py --plant DIR --base http://127.0.0.1:8002
        writes a two-page site (one clean page, one with a planted contrast failure) and its pa11y-ci config
    python tools/check_site_a11y.py --check-plant RESULTS.json --base http://127.0.0.1:8002
        exit 0 only if pa11y-ci reported a contrast error on the planted page and nothing on the clean page
    python tools/check_site_a11y.py --merge DIR --shards 6 [--modes light,dark]
        one table from every shard's pa11y-ci JSON; exit 1 if any page has an error, a shard is missing or a page
        of the site was not reported on; writes DIR/a11y-summary.md and DIR/a11y-summary.json (counts)
    python tools/check_site_a11y.py --static site
        a local pre-check of the built HTML for rules that need no browser (lang, title, alt text, link and
        button names, duplicate ids, empty headings and table headers, heading order, keyboard access to
        scrolling boxes, colour tokens); exit 1 on an error-level finding
    python tools/check_site_a11y.py --self-test
        planted faults must fail: a shard set that misses a page, a pa11y result with an error, a missing
        shard, unreadable JSON, a plant run that did not catch the contrast failure, and each static rule

Plain idea: the earlier accessibility run looked at four pages. A reader can land on any of the site's roughly 820
pages, so every page is checked, once with the light colours and once with the dark colours forced on
(`tools/check_site_view.py --dark-copy`). The pages are split into shards so that each CI job stays short; a
summary job then refuses the result unless every page of the site was reported on and none had an error.

Formal statement. Pages are every `*.html` under the built site in sorted order, shard i of n taking every n-th
page from the i-th (the same rule as tools/check_site_view.py). The pa11y-ci settings are those of `.pa11yci.json`
(standard WCAG2AA, runners axe and HTML_CodeSniffer, `wait` and Chrome flags) with two changes that do not loosen
the check: `timeout` is raised to 180 s so a long page (CHANGELOG, the known-issues register) is not reported as
a load failure, and `concurrency` is 1 (CI run 44791215797, 2026-11-20: at concurrency 2 the bundled
Chromium closed its connection on about a third of the pages, even on the two-page plant site). pa11y-ci counts errors only (warnings and notices are not reported), as in
the four-page run. A page passes if pa11y-ci lists no issue for it; a page whose load failed is listed with the
failure and fails. The merge fails unless, for each mode, the union of the shards' expected pages is the whole site
(the count every shard read), every expected page has a result, and no result has an issue.

Worked example: the plant site has `ok.html` (dark text on white) and `low-contrast.html` (`#aaaaaa` text on
white, contrast 2.32:1 against the 4.5:1 AA minimum). pa11y-ci must report `color-contrast` (axe) or
`...1_4_3.G18.Fail` (HTML_CodeSniffer) on the second page and nothing on the first; --check-plant fails otherwise,
so a pa11y run that silently checks nothing cannot pass.

The --static pass is a pre-check, not a substitute for pa11y: it cannot see computed colours, layout or script
output. Evidence class of its output: measured (on the built HTML).
"""
import argparse
import html.parser
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ("light", "dark")
TIMEOUT_MS = 180000
CONCURRENCY = 1
BATCH = 10
RETRIES = 2
PA11Y = ["npx", "--yes", "pa11y-ci@3.1.0"]


def pages(site, shard=None):
    """Every .html page under `site`, sorted; with shard "i/n" every n-th page from the i-th (1-based)."""
    found = sorted(p.relative_to(site).as_posix() for p in Path(site).rglob("*.html"))
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        if not 1 <= i <= n:
            raise SystemExit(f"--shard {shard}: need 1 <= i <= n")
        found = found[i - 1::n]
    return found


def tag(mode, shard):
    i, n = shard.split("/")
    return f"{mode}-{i}of{n}"


def base_config():
    cfg = json.loads((ROOT / ".pa11yci.json").read_text(encoding="utf-8"))
    d = dict(cfg["defaults"])
    d["timeout"] = max(int(d.get("timeout", 0)), TIMEOUT_MS)
    d["concurrency"] = CONCURRENCY
    if d.get("standard") != "WCAG2AA" or set(d.get("runners", [])) != {"axe", "htmlcs"}:
        raise SystemExit(".pa11yci.json no longer asks for WCAG2AA with axe and htmlcs; update this tool with it")
    return {"defaults": d}


def write_urls(site, shard, mode, base, out):
    if mode not in MODES:
        raise SystemExit(f"--mode {mode}: one of {', '.join(MODES)}")
    every = pages(site)
    mine = pages(site, shard)
    if not every:
        raise SystemExit(f"no .html page under {site}")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = base_config()
    cfg["urls"] = [f"{base.rstrip('/')}/{p}" for p in mine]
    t = tag(mode, shard)
    (out / f"pa11y-{t}.json").write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    (out / f"a11y-{t}.expected.json").write_text(json.dumps(
        {"mode": mode, "shard": shard, "base": base.rstrip("/"), "site_pages": len(every), "pages": mine},
        indent=1) + "\n", encoding="utf-8")
    print(f"{t}: {len(mine)} of {len(every)} pages -> {out / f'pa11y-{t}.json'}")
    return 0


def read_results(path):
    """pa11y-ci --json output as {url: [issues]}; None if the file is missing or not pa11y-ci JSON."""
    p = Path(path)
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    start = text.find("{")
    try:
        data = json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("results"), dict):
        return None
    return {u: (v if isinstance(v, list) else [v]) for u, v in data["results"].items()}


def rule_of(issue):
    if not isinstance(issue, dict):
        return "unknown"
    return str(issue.get("code") or ("load failure: " + str(issue.get("message", ""))[:80]))


def merge(directory, shards, modes=MODES):
    d = Path(directory)
    problems, rows, counts = [], [], {}
    by_rule = defaultdict(set)
    failing = []
    for mode in modes:
        site_pages, seen, reported, bad = set(), set(), 0, 0
        for i in range(1, shards + 1):
            t = tag(mode, f"{i}/{shards}")
            exp_f = d / f"a11y-{t}.expected.json"
            if not exp_f.is_file():
                problems.append(f"{t}: no expected-pages file (shard did not run or was not uploaded)")
                continue
            exp = json.loads(exp_f.read_text(encoding="utf-8"))
            site_pages.add(exp["site_pages"])
            res = read_results(d / f"a11y-{t}.results.json")
            if res is None:
                problems.append(f"{t}: no readable pa11y-ci JSON result")
                continue
            rc_f = d / f"a11y-{t}.rc"
            rc = rc_f.read_text(encoding="utf-8").strip() if rc_f.is_file() else "missing"
            shard_bad = 0
            for p in exp["pages"]:
                url = f"{exp['base']}/{p}"
                seen.add(p)
                if url not in res:
                    problems.append(f"{t}: no result for {p}")
                    continue
                reported += 1
                if res[url]:
                    bad += 1
                    shard_bad += 1
                    rules = sorted({rule_of(x) for x in res[url]})
                    for r in rules:
                        by_rule[(mode, r)].add(p)
                    failing.append(f"- `{p}` ({mode}): " + "; ".join(rules))
            if rc != "0" and shard_bad == 0:
                problems.append(f"{t}: pa11y-ci exit status {rc} but no page error in its JSON")
        if len(site_pages) != 1:
            problems.append(f"{mode}: shards read different site page counts {sorted(site_pages)}")
        total = max(site_pages) if site_pages else 0
        if total and len(seen) != total:
            problems.append(f"{mode}: shards cover {len(seen)} of {total} pages")
        counts[mode] = {"site_pages": total, "reported": reported, "failing": bad}
        rows.append(f"| {mode} | {total} | {reported} | {reported - bad} | {bad} |")
    ok = not problems and not failing and all(c["site_pages"] and c["reported"] == c["site_pages"]
                                              for c in counts.values())
    md = ["### pa11y AA on every page (KR-227)", "",
          f"pa11y-ci 3.1.0, standard WCAG2AA, runners axe and HTML_CodeSniffer, errors only; {shards} shards per "
          "mode; dark = the site with its `prefers-color-scheme: dark` rules forced on (tools/check_site_view.py "
          "--dark-copy). Measured with tools/check_site_a11y.py --merge.", "",
          "| Mode | Site pages | Pages reported | Pages passing | Pages failing |", "|---|---:|---:|---:|---:|"]
    md += rows
    if by_rule:
        md += ["", "| Mode | Rule | Pages |", "|---|---|---:|"]
        md += [f"| {m} | `{r}` | {len(ps)} |" for (m, r), ps in sorted(by_rule.items())]
    md += ["", "Result: " + ("PASS, every page in every mode, 0 errors." if ok else "FAIL."), ""]
    md += [f"- {p}" for p in problems] + failing
    text = "\n".join(md) + "\n"
    (d / "a11y-summary.md").write_text(text, encoding="utf-8")
    (d / "a11y-summary.json").write_text(json.dumps({"ok": ok, "shards": shards, "modes": counts,
                                                     "rules": {f"{m}:{r}": len(ps) for (m, r), ps in by_rule.items()},
                                                     "problems": problems}, indent=1) + "\n", encoding="utf-8")
    print(text)
    return 0 if ok else 1


OK_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Clean page</title></head>
<body><main><h1>Clean page</h1><p style="color:#1a1a2e;background:#ffffff">Dark text on white.</p></main></body></html>
"""
LOW_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Planted contrast failure</title></head>
<body><main><h1>Planted contrast failure</h1>
<p style="color:#aaaaaa;background:#ffffff">Grey text on white, contrast 2.32 to 1.</p></main></body></html>
"""
CONTRAST_CODES = ("color-contrast", "1_4_3.G18", "1_4_3.G145")


def plant(directory, base):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    (d / "ok.html").write_text(OK_PAGE, encoding="utf-8")
    (d / "low-contrast.html").write_text(LOW_PAGE, encoding="utf-8")
    cfg = base_config()
    cfg["urls"] = [f"{base.rstrip('/')}/ok.html", f"{base.rstrip('/')}/low-contrast.html"]
    (d / "pa11y-plant.json").write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    print(f"plant site and config written to {d}")
    return 0


def check_plant(results, base):
    res = read_results(results)
    b = base.rstrip("/")
    if res is None:
        print(f"plant check FAILED: {results} is not pa11y-ci JSON", file=sys.stderr)
        return 1
    low, ok = res.get(f"{b}/low-contrast.html"), res.get(f"{b}/ok.html")
    why = []
    if low is None or ok is None:
        why.append("a planted page has no result")
    else:
        if not any(any(c in rule_of(x) for c in CONTRAST_CODES) for x in low):
            why.append(f"no contrast error on the planted page (got {sorted({rule_of(x) for x in low})})")
        if ok:
            why.append(f"the clean page has errors: {sorted({rule_of(x) for x in ok})}")
    if why:
        print("plant check FAILED: " + "; ".join(why), file=sys.stderr)
        return 1
    print("plant check: pa11y-ci reported the planted contrast failure and nothing on the clean page")
    return 0


def is_load_failure(issues):
    """True if pa11y-ci could not check the page at all (browser or protocol error), as opposed to a WCAG error."""
    return bool(issues) and all(isinstance(x, dict) and not x.get("code") for x in issues)


def run_pa11y(config, results, raw, cmd=None, batch=BATCH, retries=RETRIES):
    """Runs pa11y-ci on the URLs of `config` in batches of `batch` (a fresh browser per batch), then runs each page
    whose result was a load failure again on its own, up to `retries` times. A page that is checked and has a
    WCAG error is never run again; a page that still cannot be loaded after the retries stays a load failure and
    fails. Writes the merged pa11y-ci JSON to `results` (with the retries listed under "retried") and every raw
    pa11y-ci output to `raw`. Exit status 0 only if every page was checked with no error.

    Why: in CI run 44791215797 one Chromium crash failed every later page of the same pa11y-ci run ("Protocol
    error: Connection closed"), so one bad moment cost a whole shard; batches bound that, and the retry separates
    a crash from a page fault without dropping any page."""
    import subprocess
    cmd = cmd or PA11Y
    cfg = json.loads(Path(config).read_text(encoding="utf-8"))
    raw = Path(raw)
    raw.mkdir(parents=True, exist_ok=True)
    merged, retried, k = {}, {}, 0

    def one(urls):
        nonlocal k
        k += 1
        c = dict(cfg, urls=urls)
        cf = raw / f"batch-{k:03d}.config.json"
        cf.write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8")
        p = subprocess.run(cmd + ["--config", str(cf), "--json"], capture_output=True, text=True)
        out = raw / f"batch-{k:03d}.json"
        out.write_text(p.stdout, encoding="utf-8")
        (raw / f"batch-{k:03d}.stderr.txt").write_text(p.stderr[-20000:], encoding="utf-8")
        got = read_results(out) or {}
        return {u: got.get(u, [{"message": f"no result from pa11y-ci (exit {p.returncode})"}]) for u in urls}

    urls = cfg["urls"]
    for i in range(0, len(urls), batch):
        merged.update(one(urls[i:i + batch]))
    for attempt in range(1, retries + 1):
        again = [u for u in urls if is_load_failure(merged[u])]
        for u in again:
            retried.setdefault(u, []).append(merged[u][0].get("message", "")[:120])
            merged[u] = one([u])[u]
    bad = sum(1 for u in urls if merged[u])
    Path(results).write_text(json.dumps({"total": len(urls), "errors": bad, "results": merged, "retried": retried},
                                        indent=1) + "\n", encoding="utf-8")
    print(f"pa11y-ci on {len(urls)} pages in {k} runs: {len(urls) - bad} pass, {bad} fail "
          f"({sum(1 for u in urls if is_load_failure(merged[u]))} still not loadable); {len(retried)} page(s) retried")
    return 0 if bad == 0 else 2


# ---------------------------------------------------------------- static pre-check (no browser)

def _lum(hexcol):
    h = hexcol.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# Text colour on background, as the site's CSS (tools/build_site.py CSS) pairs them.
TOKEN_PAIRS = (("ink", "bg"), ("ink", "panel"), ("ink", "code"), ("link", "bg"), ("link", "panel"),
               ("link", "code"), ("#fff", "brand"), ("#fff", "accent"))


def css_tokens(css):
    light = dict(re.findall(r"--([a-z0-9]+):(#[0-9a-fA-F]{3,6})", css.split("@media(prefers-color-scheme:dark)")[0]))
    m = re.search(r"@media\(prefers-color-scheme:dark\)\{:root\{([^}]*)\}", css)
    dark = dict(light, **dict(re.findall(r"--([a-z0-9]+):(#[0-9a-fA-F]{3,6})", m.group(1)))) if m else {}
    return {"light": light, "dark": dark}


def token_findings(css):
    out = []
    toks = css_tokens(css)
    if not toks["dark"]:
        out.append(("error", "css-dark-tokens", "style.css", "no prefers-color-scheme: dark token block"))
    for mode, t in toks.items():
        for fg, bg in TOKEN_PAIRS:
            f = fg if fg.startswith("#") else t.get(fg)
            b = t.get(bg)
            if f and b and contrast(f, b) < 4.5:
                out.append(("error", "color-contrast", "style.css",
                            f"{mode}: {fg} {f} on {bg} {b} is {contrast(f, b):.2f}:1 < 4.5:1"))
    return out


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SCROLLERS = {"pre"}


class _Scan(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.f = []          # (level, rule, detail)
        self.stack = []      # [tag, attrs, text parts, has_named_child]
        self.ids = Counter()
        self.lang = None
        self.title = None
        self.levels = []
        self.in_title = False
        self.labels = set()
        self.inputs = []

    def handle_starttag(self, t, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids[a["id"]] += 1
        if t == "html":
            self.lang = a.get("lang")
        if t == "title":
            self.in_title, self.title = True, ""
        if t == "label" and a.get("for"):
            self.labels.add(a["for"])
        if t == "img" and "alt" not in a and a.get("role") not in ("presentation", "none"):
            self.f.append(("error", "image-alt", f"<img src={a.get('src', '')[:60]!r}> without alt"))
        if t == "img" and (a.get("alt") or a.get("aria-label")):
            for s in self.stack:
                if s[0] in ("a", "button"):
                    s[3] = True
        if t == "svg" and a.get("role") == "img" and not (a.get("aria-label") or a.get("aria-labelledby")):
            self.f.append(("error", "svg-img-alt", "<svg role=img> without aria-label"))
        if t == "iframe" and not a.get("title"):
            self.f.append(("error", "frame-title", "<iframe> without title"))
        if t == "input" and a.get("type") not in ("hidden", "submit", "button", "reset", "image"):
            self.inputs.append((a.get("id"), a.get("aria-label") or a.get("aria-labelledby") or a.get("title")))
        if t in SCROLLERS and a.get("tabindex") is None:
            self.f.append(("error", "scrollable-region-focusable", f"<{t}> can scroll sideways but has no tabindex"))
        if t in VOID:
            return
        self.stack.append([t, a, [], bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title"))])

    def handle_startendtag(self, t, attrs):
        self.handle_starttag(t, attrs)
        if t not in VOID and self.stack and self.stack[-1][0] == t:
            self.handle_endtag(t)

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        for s in self.stack:
            s[2].append(data)

    def handle_endtag(self, t):
        if t == "title":
            self.in_title = False
        if t in VOID:
            return
        while self.stack:
            s = self.stack.pop()
            if s[0] == t:
                break
        else:
            return
        tg, a, parts, named = s
        text = "".join(parts).strip()
        if tg == "a" and a.get("href") is not None and not text and not named:
            self.f.append(("error", "link-name", f"<a href={a.get('href')[:60]!r}> with no text"))
        if tg == "button" and not text and not named:
            self.f.append(("error", "button-name", "<button> with no text"))
        if re.fullmatch(r"h[1-6]", tg):
            if not text and not named:
                self.f.append(("error", "empty-heading", f"empty <{tg}>"))
            lvl = int(tg[1])
            if self.levels and lvl > self.levels[-1] + 1:
                self.f.append(("warning", "heading-order", f"<{tg}> after <h{self.levels[-1]}>: {text[:50]!r}"))
            self.levels.append(lvl)
        if tg == "th" and not text and not named:
            self.f.append(("error", "empty-table-header", "empty <th>"))

    def finish(self):
        if not self.lang:
            self.f.append(("error", "html-has-lang", "<html> without lang"))
        if not (self.title or "").strip():
            self.f.append(("error", "document-title", "no <title> text"))
        for i, n in self.ids.items():
            if n > 1:
                self.f.append(("error", "duplicate-id", f"id {i!r} used {n} times"))
        for i, named in self.inputs:
            if not named and i not in self.labels:
                self.f.append(("error", "label", f"<input id={i!r}> without a label"))
        if 1 not in self.levels:
            self.f.append(("warning", "page-has-heading-one", "no <h1>"))
        return self.f


def scan_html(text):
    s = _Scan()
    s.feed(text)
    s.close()
    return s.finish()


def static(site, out=None):
    site = Path(site)
    rel = pages(site)
    if not rel:
        print(f"no .html page under {site}", file=sys.stderr)
        return 1
    by = defaultdict(set)
    first = {}
    css = site / "style.css"
    found = token_findings(css.read_text(encoding="utf-8")) if css.is_file() else []
    for lvl, rule, detail in found:
        by[(lvl, rule)].add("style.css")
        first.setdefault((lvl, rule), f"style.css: {detail}")
    for p in rel:
        for lvl, rule, detail in scan_html((site / p).read_text(encoding="utf-8", errors="replace")):
            by[(lvl, rule)].add(p)
            first.setdefault((lvl, rule), f"{p}: {detail}")
    lines = [f"static pre-check of {len(rel)} pages under {site}"]
    for (lvl, rule), ps in sorted(by.items()):
        lines.append(f"  {lvl:7} {rule:28} {len(ps):4} pages   e.g. {first[(lvl, rule)][:140]}")
    errors = sum(1 for (lvl, _) in by if lvl == "error")
    lines.append("result: " + ("no error-level finding" if not errors else f"{errors} error-level rule(s) failing"))
    print("\n".join(lines))
    if out:
        Path(out).write_text(json.dumps({"pages": len(rel), "findings": {f"{lvl}:{r}": sorted(ps)
                                         for (lvl, r), ps in sorted(by.items())}}, indent=1) + "\n",
                             encoding="utf-8")
    return 1 if errors else 0


# ---------------------------------------------------------------- local browser pass (no axe-core needed)

BROWSER_JS = r"""() => {
  const parse = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const blend = (t, b) => ({r: t.r * t.a + b.r * (1 - t.a), g: t.g * t.a + b.g * (1 - t.a), b: t.b * t.a + b.b * (1 - t.a), a: 1});
  const back = el => { const layers = [];
    for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e);
      if (s.backgroundImage !== 'none') return null;
      const c = parse(s.backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base = {r: 255, g: 255, b: 255, a: 1};
    for (let i = layers.length - 1; i >= 0; i--) base = blend(layers[i], base);
    return base; };
  const out = {contrast: [], scroll: [], svgText: 0, checked: 0};
  const seen = new Set();
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const el = w.currentNode.parentElement;
    if (!el || seen.has(el) || !w.currentNode.textContent.trim()) continue;
    seen.add(el);
    if (el.closest('svg')) { out.svgText++; continue; }
    if (el.closest('script,style,noscript,[hidden],.sr-only')) continue;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width <= 1 || r.height <= 1 || r.right < 0 || s.visibility === 'hidden' || +s.opacity === 0) continue;
    const fg = parse(s.color), bg = back(el); if (!fg || !bg) continue;
    const f = blend(fg, bg), L1 = lum(f), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const px = parseFloat(s.fontSize), bold = +s.fontWeight >= 700;
    const need = (px >= 24 || (bold && px >= 18.66)) ? 3 : 4.5;
    out.checked++;
    if (ratio < need) out.contrast.push(`${el.tagName.toLowerCase()}.${el.className || ''} ${ratio.toFixed(2)}:1 < ${need}: ${s.color} on rgb(${bg.r|0},${bg.g|0},${bg.b|0}) "${w.currentNode.textContent.trim().slice(0, 40)}"`);
  }
  document.querySelectorAll('body *').forEach(e => {
    const s = getComputedStyle(e);
    if (!/(auto|scroll)/.test(s.overflowX + s.overflowY)) return;
    if (e.scrollWidth <= e.clientWidth + 1 && e.scrollHeight <= e.clientHeight + 1) return;
    if (e.tabIndex >= 0 || e.querySelector('a[href],button,input,select,textarea,[tabindex]')) return;
    out.scroll.push(`${e.tagName.toLowerCase()}.${e.className || ''} ${e.scrollWidth}x${e.scrollHeight} in ${e.clientWidth}x${e.clientHeight}`);
  });
  // axe-core 4.2.4 (the copy pa11y 6.2.3 runs) puts every element into a grid of 200 px cells, with one sub-grid
  // per box that scrolls (lib/commons/dom/get-rect-stack.js createGrid). color-contrast then looks up the cell
  // under the middle of each element's bounding box (getElementStack) and reads .filter of it. A sub-grid holds
  // only the client rects of the elements inside that box, so the middle of a multi-line inline element there
  // (a <code> block in a <pre> that scrolls sideways) can fall in an empty cell: the rule throws "Cannot read
  // property 'filter' of undefined" and pa11y reports color-contrast on the page with no element (CI run
  // 44805977858, tutorials 36 and 39). This replays that lookup; display:none and visibility:hidden stand in for
  // axe's isVisible.
  const G = 200, scrolls = e => { const ox = e.scrollWidth > e.clientWidth, oy = e.scrollHeight > e.clientHeight;
    if (!(ox || oy)) return false; const s = getComputedStyle(e);
    return (ox && !['visible', 'hidden'].includes(s.overflowX)) || (oy && !['visible', 'hidden'].includes(s.overflowY)); };
  const gridOf = new Map(), subOf = new Map();
  const put = (grid, e) => { gridOf.set(e, grid); for (const q of e.getClientRects()) {
    const r0 = (q.top / G) | 0, r1 = ((q.top + q.height) / G) | 0, c0 = (q.left / G) | 0, c1 = ((q.left + q.width) / G) | 0;
    for (let a = r0; a <= r1; a++) { grid[a] = grid[a] || []; for (let b = c0; b <= c1; b++) grid[a][b] = true; } } };
  const rootGrid = [];
  put(rootGrid, document.documentElement);
  const g = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  for (let e = g.currentNode; e; e = g.nextNode()) {
    let q = e.parentElement; while (q && !scrolls(q)) q = q.parentElement;
    const grid = q ? subOf.get(q) : rootGrid;
    if (scrolls(e)) subOf.set(e, []);
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (r.width && r.height && s.display !== 'none' && s.visibility !== 'hidden' && grid) put(grid, e);
  }
  out.gridGap = [];
  for (const [e, grid] of gridOf) {
    if (e === document.documentElement || ![...e.childNodes].some(t => t.nodeType === 3 && t.textContent.trim())) continue;
    const r = e.getBoundingClientRect(), row = ((r.top + r.height / 2) / G) | 0, col = ((r.left + r.width / 2) / G) | 0;
    if (!grid[row] || !grid[row][col]) out.gridGap.push(`${e.tagName.toLowerCase()}.${e.className || ''} middle in empty cell ${row},${col} of a ${grid === rootGrid ? 'page' : 'scroll box'} grid: "${e.textContent.trim().slice(0, 40)}"`);
  }
  return out;
}"""


def browser_pass(site, channel="chrome", out=None, only=None):
    """Computed colour contrast of every visible HTML text element and keyboard access to every box that really
    scrolls, on every page at 1280 x 1024 (pa11y's default viewport), light and dark. Text inside SVG (Mermaid,
    charts) is counted but not judged: its background is drawn shapes, which this pass cannot see."""
    import importlib.util
    import time
    from playwright.sync_api import sync_playwright
    sp = importlib.util.spec_from_file_location("check_site_view", ROOT / "tools" / "check_site_view.py")
    sv = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(sv)
    rel = only or pages(site)
    srv, base = sv.serve(site)
    found = defaultdict(lambda: defaultdict(list))
    stats = Counter()
    t0 = time.monotonic()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel=channel) if channel else pw.chromium.launch()
            for mode in MODES:
                ctx = b.new_context(viewport={"width": 1280, "height": 1024}, color_scheme=mode)
                pg = ctx.new_page()
                for p in rel:
                    try:
                        pg.goto(f"{base}/{p}", wait_until="load", timeout=60000)
                        if pg.locator(".mermaid").count():
                            try:
                                pg.wait_for_function(sv.MERMAID_DONE, timeout=sv.MERMAID_WAIT_MS)
                            except Exception:
                                found[(mode, "mermaid-not-rendered")][p].append("timeout")
                        r = pg.evaluate(BROWSER_JS)
                    except Exception as e:
                        found[(mode, "not-measured")][p].append(str(e)[:120])
                        continue
                    stats[f"{mode} text elements"] += r["checked"]
                    stats[f"{mode} svg text (not judged)"] += r["svgText"]
                    if r["contrast"]:
                        found[(mode, "color-contrast")][p] += r["contrast"]
                    if r["scroll"]:
                        found[(mode, "scrollable-region-focusable")][p] += r["scroll"]
                    if r["gridGap"]:
                        found[(mode, "axe-4.2.4-grid-gap")][p] += r["gridGap"]
                ctx.close()
            b.close()
    finally:
        srv.shutdown()
    lines = [f"browser pass: {len(rel)} pages x {len(MODES)} modes in {time.monotonic() - t0:.0f} s; "
             + ", ".join(f"{k} {v}" for k, v in sorted(stats.items()))]
    for (mode, rule), ps in sorted(found.items()):
        ex = next(iter(ps.items()))
        lines.append(f"  {mode:5} {rule:28} {len(ps):4} pages   e.g. {ex[0]}: {ex[1][0][:150]}")
    lines.append("result: " + ("no finding" if not found else f"{len(found)} mode/rule pair(s) failing"))
    print("\n".join(lines))
    if out:
        Path(out).write_text(json.dumps({"pages": len(rel), "stats": stats,
                                         "findings": {f"{m}:{r}": ps for (m, r), ps in sorted(found.items())}},
                                        indent=1) + "\n", encoding="utf-8")
    return 1 if found else 0


# ---------------------------------------------------------------- self-test

def self_test():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        site = t / "site"
        (site / "sub").mkdir(parents=True)
        for i in range(7):
            (site / ("sub" if i % 2 else ".") / f"p{i}.html").write_text(OK_PAGE, encoding="utf-8")
        n = 3
        for mode in MODES:
            for i in range(1, n + 1):
                write_urls(site, f"{i}/{n}", mode, "http://h:1", t / "out")
        covered = set()
        for i in range(1, n + 1):
            covered |= set(json.loads((t / "out" / f"a11y-light-{i}of{n}.expected.json").read_text())["pages"])
        if covered != set(pages(site)):
            fails.append("the shards do not cover every page exactly")

        def results(mode, i, bad_page=None, drop=None, rc="0", raw=None):
            exp = json.loads((t / "out" / f"a11y-{tag(mode, f'{i}/{n}')}.expected.json").read_text())
            r = {f"{exp['base']}/{p}": ([{"code": "color-contrast", "type": "error"}] if p == bad_page else [])
                 for p in exp["pages"] if p != drop}
            f = t / "out" / f"a11y-{tag(mode, f'{i}/{n}')}.results.json"
            f.write_text(raw if raw is not None else json.dumps({"total": len(r), "results": r}), encoding="utf-8")
            (t / "out" / f"a11y-{tag(mode, f'{i}/{n}')}.rc").write_text(rc, encoding="utf-8")
            return exp["pages"]

        def all_clean():
            for mode in MODES:
                for i in range(1, n + 1):
                    results(mode, i)
        all_clean()
        if merge(t / "out", n) != 0:
            fails.append("a clean set of shards did not pass")
        summary = json.loads((t / "out" / "a11y-summary.json").read_text())
        if summary["modes"]["dark"]["reported"] != 7:
            fails.append(f"summary count wrong: {summary['modes']}")
        page = results("dark", 2, bad_page=json.loads((t / "out" / "a11y-dark-2of3.expected.json").read_text())["pages"][0], rc="2")
        if merge(t / "out", n) == 0:
            fails.append("planted fault not caught: a page with a contrast error passed the merge")
        all_clean()
        results("light", 1, drop=pages(site, "1/3")[0])
        if merge(t / "out", n) == 0:
            fails.append("planted fault not caught: a page with no result passed")
        all_clean()
        (t / "out" / "a11y-light-3of3.results.json").unlink()
        if merge(t / "out", n) == 0:
            fails.append("planted fault not caught: a missing shard result passed")
        all_clean()
        results("dark", 1, raw="Error: browser crashed")
        if merge(t / "out", n) == 0:
            fails.append("planted fault not caught: unreadable pa11y-ci output passed")
        all_clean()
        results("light", 2, rc="1")
        if merge(t / "out", n) == 0:
            fails.append("planted fault not caught: non-zero pa11y-ci exit with no reported error passed")
        all_clean()
        (t / "out" / "a11y-dark-3of3.expected.json").unlink()
        if merge(t / "out", n) == 0:
            fails.append("planted fault not caught: a shard that never ran passed")
        del page
        # plant check
        plant(t / "plant", "http://h:2")
        good = {"results": {"http://h:2/ok.html": [], "http://h:2/low-contrast.html": [
            {"code": "WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail", "type": "error"}]}}
        (t / "p.json").write_text(json.dumps(good), encoding="utf-8")
        if check_plant(t / "p.json", "http://h:2") != 0:
            fails.append("plant check refused a run that caught the planted contrast failure")
        miss = {"results": {"http://h:2/ok.html": [], "http://h:2/low-contrast.html": []}}
        (t / "p.json").write_text(json.dumps(miss), encoding="utf-8")
        if check_plant(t / "p.json", "http://h:2") == 0:
            fails.append("planted fault not caught: a pa11y run that missed the contrast failure passed")
        if contrast("#aaaaaa", "#ffffff") >= 4.5 or round(contrast("#aaaaaa", "#ffffff"), 2) != 2.32:
            fails.append(f"contrast formula: #aaa on #fff gave {contrast('#aaaaaa', '#ffffff'):.3f}, expected 2.32")
    # run_pa11y with a stand-in for pa11y-ci: page b crashes once then passes, page c always crashes,
    # page d has a WCAG error (never retried)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        fake = t / "fake.py"
        fake.write_text(
            "import json,sys,pathlib\n"
            "cfg=json.load(open(sys.argv[sys.argv.index('--config')+1]))\n"
            "st=pathlib.Path(sys.argv[0]).with_name('seen.txt');seen=st.read_text().split() if st.exists() else []\n"
            "r={}\n"
            "for u in cfg['urls']:\n"
            "  n=seen.count(u);seen.append(u)\n"
            "  if u.endswith('/c.html') or (u.endswith('/b.html') and n==0): r[u]=[{'message':'Protocol error: Connection closed.'}]\n"
            "  elif u.endswith('/d.html'): r[u]=[{'code':'color-contrast','type':'error'}]\n"
            "  else: r[u]=[]\n"
            "st.write_text(' '.join(seen));print(json.dumps({'results':r}));sys.exit(2 if any(r.values()) else 0)\n",
            encoding="utf-8")
        cfg = {"defaults": {}, "urls": [f"http://h/{p}.html" for p in "abcd"]}
        (t / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        rc = run_pa11y(t / "cfg.json", t / "res.json", t / "raw", cmd=[sys.executable, str(fake)], batch=3)
        res = json.loads((t / "res.json").read_text())
        r = res["results"]
        if rc == 0 or r["http://h/a.html"] or r["http://h/b.html"] or not is_load_failure(r["http://h/c.html"])                 or r["http://h/d.html"][0].get("code") != "color-contrast":
            fails.append(f"run_pa11y: wrong merge {rc} {r}")
        if sorted(res["retried"]) != ["http://h/b.html", "http://h/c.html"] or len(res["retried"]["http://h/c.html"]) != RETRIES:
            fails.append(f"run_pa11y: wrong retries {res['retried']}")
        if "http://h/d.html" in res["retried"]:
            fails.append("run_pa11y retried a page with a WCAG error")
    # static rules: each planted fault must be found, a clean page must give no error
    planted = {
        "html-has-lang": "<html><head><title>x</title></head><body><h1>x</h1></body></html>",
        "document-title": '<html lang="en"><head></head><body><h1>x</h1></body></html>',
        "image-alt": '<html lang="en"><title>x</title><h1>x</h1><img src="a.png"></html>',
        "link-name": '<html lang="en"><title>x</title><h1>x</h1><a href="b.html"></a></html>',
        "duplicate-id": '<html lang="en"><title>x</title><h1 id="a">x</h1><p id="a">y</p></html>',
        "empty-heading": '<html lang="en"><title>x</title><h1>x</h1><h2></h2></html>',
        "empty-table-header": '<html lang="en"><title>x</title><h1>x</h1><table><tr><th></th></tr></table></html>',
        "scrollable-region-focusable": '<html lang="en"><title>x</title><h1>x</h1><pre>long</pre></html>',
        "label": '<html lang="en"><title>x</title><h1>x</h1><input id="q" type="search"></html>',
        "heading-order": '<html lang="en"><title>x</title><h1>x</h1><h3>y</h3></html>',
    }
    for rule, text in planted.items():
        if rule not in {r for _, r, _ in scan_html(text)}:
            fails.append(f"planted fault not caught by the static pass: {rule}")
    clean = ('<html lang="en"><head><title>x</title></head><body><main><h1>x</h1><h2>y</h2>'
             '<a href="c.html"><img src="i.png" alt="icon"></a><pre tabindex="0">code</pre>'
             '<label for="q">Search</label><input id="q" type="search"><table><tr><th>h</th></tr></table>'
             '</main></body></html>')
    got = [x for x in scan_html(clean) if x[0] == "error"]
    if got:
        fails.append(f"the clean page gave static errors: {got}")
    bad_css = ":root{--bg:#ffffff;--ink:#aaaaaa}@media(prefers-color-scheme:dark){:root{--bg:#000000}}"
    if not any(r == "color-contrast" for _, r, _, _ in token_findings(bad_css)):
        fails.append("planted fault not caught: a grey-on-white ink token passed")
    if fails:
        print("self-test FAILED:\n" + "\n".join(fails), file=sys.stderr)
        return 1
    print("self-test: shards cover every page once; the merge refuses an error, a missing page, a missing or "
          "unreadable shard and an unexplained exit status; the plant check refuses a missed contrast failure; "
          "each static rule catches its planted fault and a clean page passes")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", action="store_true")
    ap.add_argument("--site")
    ap.add_argument("--shard")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--base")
    ap.add_argument("--out")
    ap.add_argument("--plant", metavar="DIR")
    ap.add_argument("--check-plant", metavar="RESULTS")
    ap.add_argument("--merge", metavar="DIR")
    ap.add_argument("--shards", type=int)
    ap.add_argument("--modes", default=",".join(MODES))
    ap.add_argument("--run", metavar="CONFIG", help="run pa11y-ci on CONFIG in batches; needs --results, --raw")
    ap.add_argument("--results")
    ap.add_argument("--raw")
    ap.add_argument("--static", metavar="SITE")
    ap.add_argument("--browser", metavar="SITE", help="local pass with Playwright and the installed Chrome")
    ap.add_argument("--channel", default="chrome")
    ap.add_argument("--page", action="append")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.urls:
        if not (a.site and a.shard and a.mode and a.base and a.out):
            ap.error("--urls needs --site, --shard, --mode, --base and --out")
        return write_urls(a.site, a.shard, a.mode, a.base, a.out)
    if a.run:
        if not (a.results and a.raw):
            ap.error("--run needs --results and --raw")
        rc = run_pa11y(a.run, a.results, a.raw)
        if a.out:
            Path(a.out).write_text(f"{rc}\n", encoding="utf-8")
        return rc
    if a.plant:
        return plant(a.plant, a.base or "http://127.0.0.1:8002")
    if a.check_plant:
        return check_plant(a.check_plant, a.base or "http://127.0.0.1:8002")
    if a.merge:
        if not a.shards:
            ap.error("--merge needs --shards")
        return merge(a.merge, a.shards, tuple(a.modes.split(",")))
    if a.static:
        return static(a.static, a.out)
    if a.browser:
        return browser_pass(a.browser, a.channel or None, a.out, a.page)
    ap.error("one of --urls, --plant, --check-plant, --merge, --static, --self-test")


if __name__ == "__main__":
    sys.exit(main())
