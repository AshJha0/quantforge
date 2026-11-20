#!/usr/bin/env python3
"""Clean-machine run of every example (plan 14.8 K-7, check RE1, ruling KR-222, confirmed 2026-11-20).

    python tools/check_examples.py --lang python          every examples/*.json and batch.jsonl case through a CLI,
                                                          then every example script no tutorial page runs
    python tools/check_examples.py --cli "<command>"       the same with any CLI command
    python tools/check_examples.py --static               listing checks only (no CLI)
    python tools/check_examples.py --self-test            planted faults must fail

Plain idea: the tutorial workflow already runs every tutorial page's code in each language on a fresh runner
(tools/check_tutorial.py). This script covers what it does not: the single-case example files and the example
scripts that no tutorial block runs. It also fails if a tutorial page is listed nowhere (UNLISTED).

Formal statement. Exit 0 if and only if:
- every docs/getting-started/tutorial-*.md is linked from docs/getting-started/README.md (else UNLISTED);
- every .py file under examples/ with a `__main__` guard (helpers such as examples/tutorials/qf.py have none) is either inside a `tutorial:run` block of some tutorial page (run by
  check_tutorial.py) or run here with the CLI as its arguments and exits 0 (else NOT RUN);
- (unless --static) sending every case of examples/*.json and examples/batch.jsonl to `<cli> batch` in one stream
  exits 0, gives one result per case with the same case_id, and the status is `error` for files named error_*.json
  and `ok` for every other case (CLI contract: `batch` exits 0 whatever each case's status; a result per line).

What it does not check: output values. The example inputs are illustrations, not test evidence (examples/README.md);
values are checked by the golden cases. Standard library only.
"""
import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIS = {"python": ["uv", "run", "--locked", "--project", "python", "quantforge"],
        "rust": ["rust/target/release/quantforge"],
        "java": ["java", "-jar", "java25/target/quantforge-cli.jar"],
        "cpp": ["cpp26/build/quantforge"]}


def static_problems(root=ROOT):
    root = Path(root)
    gs = root / "docs" / "getting-started"
    index = (gs / "README.md").read_text(encoding="utf-8") if (gs / "README.md").is_file() else ""
    pages = sorted(gs.glob("tutorial-*.md"))
    out = [f"UNLISTED: {p.name} is not linked from docs/getting-started/README.md" for p in pages
           if f"({p.name})" not in index and f"({p.name}#" not in index]
    return out


def scripts_not_run(root=ROOT):
    root = Path(root)
    run_text = ""
    for p in (root / "docs" / "getting-started").glob("tutorial-*.md"):
        for _lang, body in re.findall(r"<!-- tutorial:run (\w+) -->\s*```\w+\n(.*?)```", p.read_text(encoding="utf-8"), re.S):
            run_text += body
    return sorted(p.relative_to(root).as_posix() for p in (root / "examples").rglob("*.py")
                  if p.relative_to(root).as_posix() not in run_text and p.name != "__init__.py"
                  and not p.name.startswith("_") and "__main__" in p.read_text(encoding="utf-8"))


def cases(root=ROOT):
    root = Path(root)
    out = []
    for p in sorted((root / "examples").glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        out.append((p.name, c, "error" if p.name.startswith("error_") else "ok"))
    bl = root / "examples" / "batch.jsonl"
    if bl.is_file():
        for line in bl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                out.append(("batch.jsonl", c, "error" if c.get("case_id", "").endswith("-error") else "ok"))
    return out


def run_problems(cli, root=ROOT, scripts=None):
    root = Path(root)
    out = []
    cs = cases(root)
    text = "".join(json.dumps(c) + "\n" for _, c, _ in cs)
    p = subprocess.run(cli + ["batch"], input=text, capture_output=True, text=True, cwd=root)
    if p.returncode != 0:
        return [f"`{' '.join(cli)} batch` exited {p.returncode}: {p.stderr[-400:]}"]
    results = [json.loads(x) for x in p.stdout.splitlines() if x.strip().startswith("{")]
    if len(results) != len(cs):
        out.append(f"{len(cs)} cases sent, {len(results)} results back")
    for (name, c, want), r in zip(cs, results):
        if r.get("case_id") != c.get("case_id"):
            out.append(f"{name}: result case_id {r.get('case_id')!r}, sent {c.get('case_id')!r}")
        elif r.get("status") != want:
            out.append(f"{name}: status {r.get('status')!r}, expected {want!r}: {json.dumps(r.get('error'))}")
    for s in scripts if scripts is not None else scripts_not_run(root):
        q = subprocess.run([sys.executable, s] + cli, capture_output=True, text=True, cwd=root)
        if q.returncode != 0:
            out.append(f"NOT RUN OK: {s} exited {q.returncode}: {(q.stderr or q.stdout)[-300:]}")
    print(f"{len(cs)} example cases sent; {len(scripts if scripts is not None else scripts_not_run(root))} scripts run")
    return out


STUB = """import json, sys
for line in sys.stdin:
    c = json.loads(line)
    bad = c["case_id"].endswith("error") or "FAIL" in c["case_id"]
    print(json.dumps({"case_id": c["case_id"], "status": "error" if bad else "ok"}))
"""


def self_test():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        gs = t / "docs" / "getting-started"
        gs.mkdir(parents=True)
        (t / "examples").mkdir()
        (gs / "tutorial-1-a.md").write_text("x\n", encoding="utf-8")
        (gs / "README.md").write_text("[one](tutorial-1-a.md)\n", encoding="utf-8")
        (t / "examples" / "a.json").write_text(json.dumps({"case_id": "ex-a"}), encoding="utf-8")
        (t / "examples" / "error_b.json").write_text(json.dumps({"case_id": "ex-b-error"}), encoding="utf-8")
        (t / "stub.py").write_text(STUB.replace("batch", ""), encoding="utf-8")
        cli = [sys.executable, str(t / "stub.py")]
        if static_problems(t) or run_problems(cli, t, scripts=[]):
            failures.append(f"good tree reported: {static_problems(t)} {run_problems(cli, t, scripts=[])}")
        (gs / "tutorial-2-b.md").write_text("x\n", encoding="utf-8")
        if not static_problems(t):
            failures.append("planted fault not caught: a tutorial page listed nowhere")
        (gs / "tutorial-2-b.md").unlink()
        (t / "examples" / "c.json").write_text(json.dumps({"case_id": "ex-c-FAIL"}), encoding="utf-8")
        if not run_problems(cli, t, scripts=[]):
            failures.append("planted fault not caught: an example that answers error")
        (t / "examples" / "c.json").unlink()
        (t / "examples" / "s.py").write_text("import sys\nif __name__ == '__main__':\n    sys.exit(3)\n", encoding="utf-8")
        if "examples/s.py" not in scripts_not_run(t) or not run_problems(cli, t, scripts=["examples/s.py"]):
            failures.append("planted fault not caught: an example script no page runs, which fails")
    if failures:
        print("self-test FAILED:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print("self-test: a good tree passes and 3 planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=sorted(CLIS))
    ap.add_argument("--cli", help="CLI command, quoted (default: the --lang command)")
    ap.add_argument("--static", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    found = static_problems()
    if not a.static:
        if not (a.cli or a.lang):
            ap.error("--lang, --cli, --static or --self-test")
        cli = shlex.split(a.cli) if a.cli else list(CLIS[a.lang])
        exe = shutil.which(cli[0]) or (str(ROOT / cli[0]) if (ROOT / cli[0]).exists() else None)
        if exe is None and not (ROOT / (cli[0] + ".exe")).exists():
            found.append(f"CLI {cli[0]} not found: build it first (CONTRIBUTING.md)")
        else:
            found += run_problems(cli)
    else:
        print(f"example scripts no tutorial page runs: {', '.join(scripts_not_run()) or 'none'}")
    for p in found:
        print(f"examples: {p}", file=sys.stderr)
    if not found:
        print("examples: every tutorial listed" + ("" if a.static else "; every example case and script ran as expected"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
