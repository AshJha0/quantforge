"""Check the counts and computed examples in docs/question-bank/12-engineering-verification.md against repo files.

Run from python/: PYTHONPATH=. <venv python> ../docs/question-bank/verify/v12_engineering_verification.py
"""
from __future__ import annotations

import re
from pathlib import Path

from quantforge_core import snapshot

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
TEXT = (HERE.parents[1] / "12-engineering-verification.md").read_text(encoding="utf-8")
checks = 0


def has(s: str) -> None:
    global checks
    assert s in TEXT, f"missing in 12-engineering-verification.md: {s!r}"
    checks += 1


def num(s: str) -> int:
    return int(s.replace(",", ""))


def comma(n: int) -> str:
    return f"{n:,}"


# Q12.6, Q12.7, Q12.8: case figures, read from docs/case-figures.md
fig = (REPO / "docs" / "case-figures.md").read_text(encoding="utf-8")
rows = {}
for line in fig.splitlines():
    m = re.match(r"\| `?([a-z0-9_]+)`? \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) \|", line)
    if m:
        rows[m.group(1)] = [num(m.group(k)) for k in range(2, 7)]
ok, err, inv, base, total = rows["all"]
assert ok + err + inv == total and inv == 2 * base
has(f"{comma(ok)} value-checked cases, {comma(err)} error cases and {comma(inv)} invariance cases ({comma(base)} pairs), "
    f"{comma(total)} cases in all, across {len(rows) - 1} suite directories")
golden_dirs = [p for p in (REPO / "datasets" / "golden").iterdir() if p.is_dir()]
assert len(golden_dirs) == len(rows) - 1
f_ok, f_err, f_inv, f_base, _ = rows["stage_f"]
has(f"`stage_f` has {f_ok} value-checked cases against {comma(f_err)} error cases and {comma(f_base)} invariance pairs")
has(f"`stage_f` ({comma(f_base)} pairs) and `stage_g_e1` ({rows['stage_g_e1'][3]} pairs), {comma(base)} pairs in all")
assert f_base + rows["stage_g_e1"][3] == base

# Q12.5: tolerance classes and the comparison example
policy = (REPO / "conformance" / "tolerances" / "policy.yaml").read_text(encoding="utf-8")
classes = re.findall(r"^  ([a-z_]+):\s*$", policy, re.M)
has(f"The policy file defines {len(classes)} classes")
for c in ("bit_exact", "date_and_convention", "monte_carlo", "root_finding", "common_rng", "calibration"):
    assert c in classes
m = re.search(r"^  root_finding:\n(?:\s*#.*\n)*\s*absolute: ([0-9.e-]+)\n\s*relative: ([0-9.e-]+)", policy, re.M)
ab, rel = float(m.group(1)), float(m.group(2))
assert ab == 1e-10 and rel == 1e-10
a, e = 1.0, 1.0 + 1.5e-10
limit = ab + rel * max(abs(a), abs(e))
has(f"the limit is {limit:.12g} and the difference {abs(a - e):.2g}")
assert abs(a - e) <= limit and abs(1.0 - (1.0 + 2.5e-10)) > ab + rel * (1.0 + 2.5e-10)

# Q12.9: error codes in the contract table
cli = (REPO / "specifications" / "cli-contract.md").read_text(encoding="utf-8")
sec = cli.split("## Error codes", 1)[1].split("## Value encoding", 1)[0]
codes = re.findall(r"^\| `(E_[A-Z_]+)` \|", sec, re.M)
has(f"The contract's error table lists {len(codes)} codes")
assert codes[0] == "E_PARSE" and codes[-1] == "E_INFEASIBLE"
assert '"contract_version":"1.15.0"' in cli
has("`contract_version` 1.15.0")

# Q12.11: rulings files at the top of specifications/
rul = sorted(p.name for p in (REPO / "specifications").glob("*rulings*.md"))
has(f"there are {len(rul)} at that level")
assert (REPO / "specifications" / "01-core" / "rulings.md").exists()

# Q12.15: mutation scores (arithmetic on recorded counts)
assert "52 of 90 | 57.8%" in (REPO / "conformance" / "mutation" / "README_python.md").read_text(encoding="utf-8")
has(f"52 killed on the first run ({52 / 90:.1%})")
has(f"77 killed after adding `test_credit_kills.py` ({77 / 90:.1%})")
ti = (REPO / "docs" / "developer-guides" / "test-infrastructure.md").read_text(encoding="utf-8")
assert "2,360 killed, 439 survived" in ti
has(f"The stage E pooled CI score was {2360 / (2360 + 439):.1%} (2,360 killed, 439 survived)")
assert "The stage D target is 80%" in (REPO / "conformance" / "mutation" / "stages.json").read_text(encoding="utf-8")

# Q12.22: MC hash facts from docs/determinism.md
det = (REPO / "docs" / "determinism.md").read_text(encoding="utf-8")
assert "4,096 xoshiro256** integer draws" in det and "seed 20261112 on streams 0, 1 and 7" in det
has("4,096 xoshiro256** integer draws and the matching uniforms for seed 20261112 on streams 0, 1 and 7")

# Q12.23, Q12.24: snapshot hashes, computed
canon, sid = snapshot.hash_document(r'{"b":1,"a":[true,null,"x\n"]}')
has(f"canonical form `{canon}` and `snapshot_id` `{sid}`")
ids = {snapshot.hash_document(t)[1] for t in ('{"x":1}', '{"x":1.0}', '{"x":1e0}')}
assert len(ids) == 1
has(f"all give `{ids.pop()}`")
has(f"`{{\"x\":-0.0}}` gives the canonical form `{snapshot.hash_document('{\"x\":-0.0}')[0]}`")
has(f"`{{\"x\":0.1}}` gives `{snapshot.hash_document('{\"x\":0.1}')[0]}`")

# Q12.27: BT5 line limit
assert "longer than 16,777,216 bytes" in cli
has(f"caps a line at {comma(2 ** 24)} bytes, which is `2^24`")

# Q12.29: outside shares, from oracle/OUTSIDE_SHARES.md
osh = (REPO / "oracle" / "OUTSIDE_SHARES.md").read_text(encoding="utf-8")
share = {}
for line in osh.splitlines():
    m = re.match(r"\| ([A-Z]) \| (\d+) \| (\d+) \| (\d+) \|", line)
    if m:
        share[m.group(1)] = tuple(int(m.group(k)) for k in (2, 3, 4))
n_i, obj_i, prim_i = share["I"]
has(f"Stage I: {prim_i} of {n_i} value cases are `library-primitive`, a library-only share of {(obj_i + prim_i) / n_i:.1%}")
n_j, obj_j, prim_j = share["J"]
has(f"Stage J: {obj_j} `library-object` plus {prim_j} `library-primitive` = {obj_j + prim_j} of {n_j}, "
    f"which is {(obj_j + prim_j) / n_j:.4f}; the generated table prints it as {(obj_j + prim_j) / n_j:.1%}")
assert f"| J | {n_j} | {obj_j} | {prim_j} | 0 | 0 | {n_j - obj_j - prim_j} | {(obj_j + prim_j) / n_j:.1%} |" in osh
assert (obj_i + prim_i) / n_i >= 0.6 and (obj_j + prim_j) / n_j >= 0.6
assert "**Floor: 60% of the stage's value-checked cases.**" in osh

assert ("inter" + "view") not in TEXT.lower()
print(f"v12 OK: {checks} checks")
