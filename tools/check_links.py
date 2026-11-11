#!/usr/bin/env python3
"""Checks the HTTP status of external links in the docs. Standard library only; tolerates being offline.

    python tools/check_links.py                    # docs/references.md and the top-level pages
    python tools/check_links.py FILE.md ...        # chosen files

Each http(s) link is fetched (HEAD, then GET if HEAD is refused) with a 15 s timeout. Exit 1 only when a link
answers 404 or 410, which means it is gone. 401, 403 and 429 are reported as "refused": publishers often block
automated clients, which says nothing about the link. Network errors are reported as "unreachable". With no
network at all (every link unreachable), it prints "offline: skipped" and exits 0, so it is safe in any CI job.
The site build (tools/build_site.py) checks internal links; this script is separate because it needs the network.
"""
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ["docs/references.md", "README.md", "LEARN.md", "COOKBOOK.md", "ARCHITECTURE.md", "ROADMAP.md", "GLOSSARY.md"]
URL = re.compile(r"https?://[^\s<>()\[\]`\"']+(?:\([^\s()]*\)[^\s<>()\[\]`\"']*)*")
GONE, REFUSED = {404, 410}, {401, 403, 405, 429}
AGENT = "quantforge-link-check/1.0 (documentation link checker)"


def links(text):
    out = []
    for u in URL.findall(text):
        u = u.rstrip(".,;:*_")
        if u.count(")") > u.count("("):
            u = u[: u.rfind(")")]
        out.append(u)
    return out


def status(url, opener=urllib.request.urlopen):
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": AGENT})
        try:
            with opener(req, timeout=15) as r:
                return r.status
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in REFUSED | {400, 501}:
                continue
            return e.code
        except Exception:  # DNS, TLS, timeout: no answer
            return None
    return None


def classify(code):
    if code is None:
        return "unreachable"
    if code in GONE:
        return "gone"
    if code in REFUSED:
        return "refused"
    return "ok" if code < 400 else "error"


def run(files, check=status):
    found = {}
    for f in files:
        for u in links((ROOT / f).read_text(encoding="utf-8")):
            if "github.com/AshJha0/quantforge" not in u and "ashjha0.github.io" not in u:
                found.setdefault(u, f)
    with ThreadPoolExecutor(8) as pool:
        codes = dict(zip(found, pool.map(check, found)))
    kinds = {u: classify(c) for u, c in codes.items()}
    if found and all(k == "unreachable" for k in kinds.values()):
        print(f"offline: skipped {len(found)} links")
        return 0, kinds
    for u, k in sorted(kinds.items(), key=lambda x: (x[1], x[0])):
        if k != "ok":
            print(f"{k.upper():12} {codes[u] or '-'} {u} ({found[u]})")
    counts = {k: list(kinds.values()).count(k) for k in ("ok", "refused", "unreachable", "error", "gone")}
    print(f"links: {len(found)} checked; " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    return (1 if counts["gone"] else 0), kinds


def main(argv):
    return run(argv or DEFAULT)[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
