#!/usr/bin/env python3
"""Sampled, module-scoped mutation testing for the Python build (no mutmut, runs on Windows).

Mutants are applied only inside scratch copies of `python/` (with `datasets/`, `specifications/`
and `conformance/` beside them, so tests that look for goldens find them); the checkout is never
written. Each mutant runs the selected tests in a fresh interpreter with the copy first on
PYTHONPATH. A mutant is killed when pytest fails (exit 1) or times out.

Operators (mutmut-like): arithmetic swaps (+ -, * /, ** -> *, // -> /, % -> /), comparison swaps
(< <=, > >=, == !=, in / not in, is / is not), and/or, removal of unary minus and `not`,
number + 1, string literal "XX...XX" (docstrings skipped), True/False.

The sample is `random.Random(seed).sample(sites, n)` over the sites of the modules in AST walk
order, so a run is reproducible for unchanged module sources. See README_python.md.

    python conformance/mutation/python_sampled_mutants.py --profile credit --sample 90 \\
        --seed 20261111 --workers 3 --work <scratch dir>
    python conformance/mutation/python_sampled_mutants.py --profile credit --sample 90 \\
        --seed 20261111 --list          # print the sampled mutants as diffs, run nothing
"""
import argparse
import ast
import difflib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROFILES = {
    "credit": {
        "modules": ["quantforge_core/credit.py", "quantforge_core/credit_options.py"],
        "full": ["tests/test_stage_g_credit_mutants.py", "tests/test_stage_e8.py",
                 "tests/test_credit_kills.py"],
        "filtered": ["tests/test_mutants_e.py", "tests/test_mutation_e.py", "tests/test_r1.py",
                     "tests/test_stage_d2.py", "tests/test_stage_d_rulings.py",
                     "tests/test_stage_e_qa.py", "tests/test_waves_2_3.py",
                     "tests/test_properties.py"],
        "keyword": "credit or cds or hazard or survival or e8 or Credit or mutants or kills",
    },
}
SWAP_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
            ast.Pow: ast.Mult, ast.FloorDiv: ast.Div, ast.Mod: ast.Div}
SWAP_CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq,
            ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot,
            ast.IsNot: ast.Is}


def _docstrings(tree: ast.AST) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def sites(tree: ast.AST):
    """(walk index, kind) of every mutation site, in AST walk order."""
    docs = _docstrings(tree)
    for idx, node in enumerate(ast.walk(tree)):
        if isinstance(node, ast.BinOp) and type(node.op) in SWAP_BIN:
            yield idx, "binop"
        elif isinstance(node, ast.Compare):
            for k, op in enumerate(node.ops):
                if type(op) in SWAP_CMP:
                    yield idx, f"cmp{k}"
        elif isinstance(node, ast.BoolOp):
            yield idx, "boolop"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.Not)):
            yield idx, "unary"
        elif isinstance(node, ast.Constant) and id(node) not in docs:
            v = node.value
            if isinstance(v, bool):
                yield idx, "bool"
            elif isinstance(v, (int, float)):
                yield idx, "num"
            elif isinstance(v, str) and v:
                yield idx, "str"


class _Apply(ast.NodeTransformer):
    def __init__(self, target: int, kind: str, order: dict[int, int]):
        self.target, self.kind, self.order = target, kind, order

    def generic_visit(self, node):
        node = super().generic_visit(node)
        if self.order.get(id(node)) != self.target:
            return node
        k = self.kind
        if k == "binop":
            node.op = SWAP_BIN[type(node.op)]()
        elif k.startswith("cmp"):
            j = int(k[3:])
            node.ops[j] = SWAP_CMP[type(node.ops[j])]()
        elif k == "boolop":
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        elif k == "unary":
            return node.operand
        elif k == "bool":
            node.value = not node.value
        elif k == "num":
            node.value = node.value + 1
        elif k == "str":
            node.value = "XX" + node.value + "XX"
        return node


def mutant_source(path: Path, target: int, kind: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    order = {id(n): i for i, n in enumerate(ast.walk(tree))}
    new = _Apply(target, kind, order).visit(tree)
    ast.fix_missing_locations(new)
    return ast.unparse(new)


def mutant_diff(src: Path, module: str, target: int, kind: str) -> str:
    base = ast.unparse(ast.parse((src / module).read_text(encoding="utf-8"))).splitlines()
    mut = mutant_source(src / module, target, kind).splitlines()
    return "\n".join(line for line in difflib.unified_diff(base, mut, lineterm="", n=0)
                     if not line.startswith(("---", "+++")))


def sample(src: Path, modules: list[str], n: int, seed: int) -> list[tuple[str, int, str]]:
    found = []
    for mod in modules:
        tree = ast.parse((src / mod).read_text(encoding="utf-8"))
        found += [(mod, i, k) for i, k in sites(tree)]
    return found, random.Random(seed).sample(found, min(n, len(found)))


def _copy(src: Path, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    for extra in ("datasets", "specifications", "conformance"):
        shutil.copytree(src.parent / extra, dest / extra,
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(src, dest / "python", ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", "*.egg-info", ".pytest_cache", ".hypothesis", ".mutmut-cache",
        "mutants"))
    return dest / "python"


def _run(python: str, cwd: Path, profile: dict, timeout: int) -> str:
    env = {**os.environ, "PYTHONPATH": str(cwd), "PYTHONDONTWRITEBYTECODE": "1"}
    tests = [t for t in profile["full"] + profile["filtered"] if (cwd / t).exists()]
    cmd = [python, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *tests,
           "-k", profile["keyword"]]
    try:
        p = subprocess.run(cmd, check=False, cwd=cwd, env=env, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout"
    return {0: "survived", 1: "killed"}.get(p.returncode, f"error{p.returncode}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="credit", choices=sorted(PROFILES))
    ap.add_argument("--sample", type=int, default=90)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--work", type=Path, default=None, help="scratch directory for the copies")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--list", action="store_true", help="print the sampled mutants and stop")
    ap.add_argument("--out", type=Path, default=None, help="write per-mutant results as JSON")
    args = ap.parse_args()
    profile = PROFILES[args.profile]
    src = REPO / "python"
    every, chosen = sample(src, profile["modules"], args.sample, args.seed)
    print(f"sites {len(every)} sample {len(chosen)} seed {args.seed}", flush=True)
    if args.list:
        for mod, idx, kind in chosen:
            print(f"## {mod} node {idx} {kind}\n{mutant_diff(src, mod, idx, kind)}")
        return
    work = args.work or Path(tempfile.mkdtemp(prefix="qf-mutants-"))
    copies = [_copy(src, work / f"w{k}") for k in range(args.workers)]
    base = _run(args.python, copies[0], profile, args.timeout)
    print("baseline", base, flush=True)
    if base != "survived":
        raise SystemExit("the unmutated copy must pass")
    free = list(copies)

    def one(item):
        mod, idx, kind = item
        c = free.pop()
        try:
            original = (c / mod).read_text(encoding="utf-8")
            (c / mod).write_text(mutant_source(src / mod, idx, kind), encoding="utf-8")
            t0 = time.time()
            status = _run(args.python, c, profile, args.timeout)
            (c / mod).write_text(original, encoding="utf-8")
            row = {"module": mod, "node": idx, "kind": kind, "status": status,
                   "secs": round(time.time() - t0)}
            print(json.dumps(row), flush=True)
            return row
        finally:
            free.append(c)

    with ThreadPoolExecutor(args.workers) as ex:
        rows = list(ex.map(one, chosen))
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    killed = sum(r["status"] in ("killed", "timeout") for r in rows)
    print(f"killed {killed} of {len(rows)}; survived "
          f"{sum(r['status'] == 'survived' for r in rows)}; score {killed / len(rows):.3f}",
          flush=True)


if __name__ == "__main__":
    main()
