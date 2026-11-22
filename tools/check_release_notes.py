#!/usr/bin/env python3
"""Published release notes carry no draft placeholder (audit PT-4, 2026-11-22).

    python tools/check_release_notes.py notes.md docs/releases/v1.0.0.md   exit 1 if any file holds a marker
    python tools/check_release_notes.py --self-test                         planted faults must fail

Plain idea: the release draft is written with `{{generated: ...}}` fill-in markers, a DRAFT banner and
"confirm at merge" notes. The release job builds `notes.md` from the CHANGELOG section and publishes it, so one
marker left behind would be published. This check runs in the release job on `notes.md` and on the version's
`docs/releases/vX.Y.Z.md` (when that file exists), before anything is published. A missing file named on the
command line is an error, so a renamed file cannot pass by being absent. Standard library only.
"""
import argparse
import sys
from pathlib import Path

MARKERS = ("{{generated", "DRAFT", "confirm at merge")


def problems(name, text):
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for m in MARKERS:
            if m in line:
                out.append(f"{name}:{no}: draft marker {m!r}")
    return out


def self_test():
    clean = "## 1.0.0: 2026-11-30\n\n- 16,695 cases.\n"
    planted = {"generated marker": clean + "- {{generated: case total}} cases\n",
               "draft banner": "DRAFT\n" + clean,
               "merge note": clean + "- figure (confirm at merge)\n"}
    missed = [k for k, v in planted.items() if not problems(k, v)]
    if problems("clean", clean) or missed:
        print(f"self-test FAILED: clean flagged {problems('clean', clean)}, not caught: {missed}", file=sys.stderr)
        return 1
    print(f"self-test: clean notes pass and {len(planted)} planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    bad = []
    for f in a.files:
        p = Path(f)
        if not p.is_file():
            bad.append(f"{f}: missing")
            continue
        bad += problems(f, p.read_text(encoding="utf-8"))
    for b in bad:
        print(f"release notes: {b}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
