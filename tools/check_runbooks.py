#!/usr/bin/env python3
"""Every command in a runbook names something that exists (plan 14.8 K-7, check RE3, ruling KR-224, confirmed 2026-11-20).

    python tools/check_runbooks.py              check docs/runbooks/*.md
    python tools/check_runbooks.py --self-test  planted faults must fail

Plain idea: a runbook is read when something is already wrong, so a command in it that names a missing script or
an option the script does not take costs time at the worst moment. This check reads every `bash` code block of
the runbooks and fails if, on any line that is not a comment:

- a repository path (a word starting with tools/, .github/, conformance/, research/, benchmarks/, docs/,
  specifications/, oracle/, python/, rust/, java25/, cpp26/ or examples/) does not exist; a word holding `<`, `*`
  or `$` is a placeholder and is skipped;
- a Python script under tools/, conformance/ or research/ is given an option (`--name`) that does not appear in
  that script's own text;
- `gh workflow run`, `gh workflow view` or `gh run list --workflow` names a workflow file that does not exist.

It does not run anything, so it cannot show that a command works; it shows that what a command names is there.
Standard library only.
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOKS = ROOT / "docs" / "runbooks"
PREFIXES = ("tools/", ".github/", "conformance/", "research/", "benchmarks/", "docs/", "specifications/", "oracle/",
            "python/", "rust/", "java25/", "cpp26/", "examples/")
BLOCK = re.compile(r"^[ \t]*```bash\n(.*?)^[ \t]*```", re.M | re.S)
SCRIPT = re.compile(r"(?:^|\s)((?:tools|conformance|research)/[\w./-]+\.py)\b")
WORKFLOW = re.compile(r"gh (?:workflow (?:run|view)|run list --workflow)[ =]([\w.-]+\.yml)")


def line_problems(line, root):
    out = []
    code = line.split(" #", 1)[0].strip()
    if not code or code.startswith("#"):
        return out
    for raw in re.split(r"[\s=:(),;'\"`|>]+", code):
        word = raw.rstrip(".")
        if not word.startswith(PREFIXES) or any(c in word for c in "<*$"):
            continue
        if not (root / word).exists():
            out.append(f"path {word} does not exist")
    for m in SCRIPT.finditer(code):
        script = root / m.group(1)
        if not script.is_file():
            continue  # reported above
        text = script.read_text(encoding="utf-8")
        rest = code[m.end():].split("|", 1)[0].split("&&", 1)[0].split(";", 1)[0]
        for opt in re.findall(r"(?:^|\s)(--[a-z][\w-]*)", rest):
            if opt not in text:
                out.append(f"{m.group(1)} has no option {opt}")
    for m in WORKFLOW.finditer(code):
        if not (root / ".github" / "workflows" / m.group(1)).is_file():
            out.append(f"workflow {m.group(1)} does not exist")
    return out


def problems(books, root=ROOT):
    out = []
    pages = sorted(Path(books).glob("*.md"))
    if not pages:
        return [f"no runbooks in {books}"]
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for block in BLOCK.findall(text):
            joined = re.sub(r"\\\n\s*", " ", block)
            for line in joined.splitlines():
                out += [f"{page.name}: {p}: {line.strip()}" for p in line_problems(line, root)]
    return out


def self_test():
    good = "```bash\npython tools/check_runbooks.py --self-test\ngh workflow run release.yml\n```\n"
    planted = {
        "a missing script": "```bash\npython tools/no_such_script.py\n```\n",
        "an option the script does not take": "```bash\npython tools/check_runbooks.py --" + "never-an" + "-option\n```\n",
        "a missing workflow": "```bash\ngh workflow run no-such.yml --ref main\n```\n",
        "a missing path on a continued line": "```bash\npython tools/check_runbooks.py \\\n    docs/no-such-page.md\n```\n",
    }
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "good.md").write_text(good, encoding="utf-8")
        if problems(d):
            failures.append(f"good runbook reported: {problems(d)}")
        for name, text in planted.items():
            (d / "good.md").unlink(missing_ok=True)
            for f in d.glob("*.md"):
                f.unlink()
            (d / "bad.md").write_text(text, encoding="utf-8")
            if not problems(d):
                failures.append(f"planted fault not caught: {name}")
    if failures:
        print("self-test FAILED:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"self-test: a good runbook passes and {len(planted)} planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    found = problems(BOOKS)
    for p in found:
        print(f"runbooks: {p}", file=sys.stderr)
    if not found:
        n = sum(len(BLOCK.findall(p.read_text(encoding='utf-8'))) for p in BOOKS.glob('*.md'))
        print(f"runbooks: {len(list(BOOKS.glob('*.md')))} pages, {n} command blocks, every named path, option and workflow exists")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
