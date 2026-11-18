"""Proven-equivalent mutants left out of the PR and weekly mutation samples.

A mutant that no input can tell apart from the original is not a gap in the tests, so counting it as a
survivor only lowers the score for good (owner decision 2026-11-18). Only mutants listed in
skip-equivalents.json are left out, and test_gates.py checks that every entry points at an
`Equivalent` row in equivalents-<lang>.md whose second-reviewer cell is signed. `Accepted` rows are
never skipped: they are not proven. Every sampler reports how many mutants it skipped.

Keys carry no line numbers, so they survive edits elsewhere in the file:
- cpp:    file, original line (stripped), mutated line (stripped), joined by SEP
- rust:   file, cargo-mutants description after line:col, source line (stripped), joined by SEP
- python: the mutmut mutant name
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP_FILE = HERE / "skip-equivalents.json"
SEP = " " + chr(9) + " "  # code lines contain | and ::, never a tab after strip()


def load(lang, path=SKIP_FILE):
    if not Path(path).exists():
        return set()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {e["key"] for e in data.get(lang, [])}


def cpp_key(file, original_line, mutated_line):
    return SEP.join((file, original_line.strip(), mutated_line.strip()))


def rust_key(mutant_id, repo_root):
    """mutant_id is cargo-mutants' "path:line:col: description"."""
    path, line, _col, desc = mutant_id.split(":", 3)
    src = (Path(repo_root) / "rust" / path).read_text(encoding="utf-8").splitlines()
    text = src[int(line) - 1].strip() if 0 < int(line) <= len(src) else ""
    return SEP.join((path, desc.strip(), text))
