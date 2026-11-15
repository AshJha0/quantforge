#!/usr/bin/env python3
"""Keep only the paths whose code really changed between two commits. Standard library only.

    semantic_changes.py BASE HEAD [--in changed.txt] > real.txt

The PR mutation sample (plan_matrix.py --changed) picks modules by the files a pull request touches. A
formatting-only commit (for example `ruff format` over all of python/) would otherwise pull every module in.
This filter drops a path when base and head are the same code:

  * Python (.py): `ast.dump(ast.parse(src))` is equal, so whitespace, comments and line breaks do not count.
    Docstrings are part of the AST and still count as a change.
  * Rust, C++, Java (.rs .cpp .cc .cxx .hpp .h .hh .java): the token stream with whitespace and comments
    removed is equal. String and character literals are kept whole.

It is conservative: a new, deleted or renamed file, any other extension, a parse error, or a git error all
count as changed. With no --in, the list comes from `git diff --name-only BASE...HEAD`.
"""
import argparse
import ast
import re
import subprocess
import sys

C_LIKE = (".rs", ".cpp", ".cc", ".cxx", ".hpp", ".h", ".hh", ".java")

# Order matters: comments and literals before single characters. Raw strings (Rust r#"..."#, C++ R"(...)")
# are not parsed specially; a comment marker inside one can only make the streams differ, which is safe.
_TOKEN = re.compile(
    r'(?P<lc>//[^\n]*)'
    r'|(?P<bc>/\*.*?\*/)'
    r'|(?P<str>"(?:\\.|[^"\\])*")'
    r"|(?P<chr>'(?:\\.|[^'\\\n])')"
    r'|(?P<ws>\s+)'
    r'|(?P<word>\w+)'
    r'|(?P<op>.)',
    re.DOTALL,
)


def c_tokens(src):
    """Token list of C-like source without whitespace and comments. None if a block comment is unclosed."""
    out = []
    for m in _TOKEN.finditer(src):
        kind = m.lastgroup
        if kind in ("lc", "bc", "ws"):
            continue
        if kind == "op" and src.startswith("/*", m.start()):
            return None
        out.append(m.group())
    return out


def same_code(path, old, new):
    """True only when old and new are certainly the same code; any doubt returns False."""
    if old is None or new is None:
        return False
    if old == new:
        return True
    try:
        if path.endswith(".py"):
            return ast.dump(ast.parse(old)) == ast.dump(ast.parse(new))
        if path.endswith(C_LIKE):
            a, b = c_tokens(old), c_tokens(new)
            return a is not None and a == b
    except (SyntaxError, ValueError, RecursionError):
        return False
    return False


def git_show(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, check=False)
    if r.returncode != 0:
        return None
    try:
        return r.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def filter_paths(paths, base, head, show=git_show):
    return [p for p in paths if not same_code(p, show(base, p), show(head, p))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base")
    ap.add_argument("head")
    ap.add_argument("--in", dest="inp")
    a = ap.parse_args(argv)
    if a.inp:
        with open(a.inp, encoding="utf-8") as f:
            paths = [x.strip() for x in f if x.strip()]
    else:
        merge_base = subprocess.run(["git", "merge-base", a.base, a.head], capture_output=True, text=True,
                                    check=True).stdout.strip()
        a.base = merge_base
        paths = subprocess.run(["git", "diff", "--name-only", f"{merge_base}...{a.head}"], capture_output=True,
                               text=True, check=True).stdout.split()
    kept = filter_paths(paths, a.base, a.head)
    print(f"semantic_changes: {len(paths)} touched, {len(kept)} with real code change", file=sys.stderr)
    sys.stdout.write("".join(p + "\n" for p in kept))


if __name__ == "__main__":
    main()
