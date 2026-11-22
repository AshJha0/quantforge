"""Send probe cases to the four CLIs and print each build answer side by side (lane k-v1-fix, KR-258 sweep).

Usage: python program/stage_k_fix/probe.py cases.jsonl [width]; env CODEONLY=1 compares error codes only, ONLYDIFF=1
prints only disagreements, BUILDS=py,java limits the builds. The C++ and Rust paths are the lane build directories
in WSL on the local laptop (not the acceptance machine); edit CMDS for another machine."""
import json, subprocess, sys
ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[2])
cases = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
text = "".join(json.dumps({"schema_version": "1.0", **{k: v for k, v in c.items() if k != "_d"}}) + "\n" for c in cases).replace("Infinity", "1e400").encode()
CMDS = {
    "py": ["uv", "run", "--project", "python", "python", "-c", "import sys; sys.argv=[\"quantforge\",\"batch\"]; from quantforge_core.cli.main import main; sys.exit(main())"],
    "java": ["java", "-jar", "java25/target/quantforge-cli.jar", "batch"],
    "cpp": ["wsl", "-e", "/home/ashish/kfix-plain/quantforge", "batch"],
    "rust": ["wsl", "-e", "/home/ashish/kfix-target/release/quantforge", "batch"],
}
import os
if os.environ.get("BUILDS"): CMDS = {k: v for k, v in CMDS.items() if k in os.environ["BUILDS"].split(",")}
res = {}
for k, cmd in CMDS.items():
    p = subprocess.run(cmd, cwd=ROOT, input=text, capture_output=True, timeout=600)
    out = [json.loads(l) for l in p.stdout.decode("utf-8", "replace").splitlines() if l.strip().startswith("{")]
    res[k] = {o.get("case_id"): o for o in out}
    if len(out) != len(cases):
        print(k, "returned", len(out), "of", len(cases), p.stderr.decode("utf-8", "replace")[-300:])
def short(o):
    if o is None: return "MISSING"
    if o.get("status") == "error": return o["error"].get("code", "?") + ("" if os.environ.get("CODEONLY") else "@" + str(o["error"].get("field")))
    return json.dumps(json.loads(json.dumps(o.get("outputs")), parse_float=lambda t: float(t) + 0.0, parse_int=float), sort_keys=True)[:int(sys.argv[2]) if len(sys.argv) > 2 else 160]
for c in cases:
    r = {k: short(res[k].get(c["case_id"])) for k in CMDS}
    same = len(set(r.values())) == 1
    if same and os.environ.get("ONLYDIFF"): continue
    print(("SAME " if same else "DIFF ") + c["case_id"], "|", next(iter(r.values())) if same else json.dumps(r), "|", c.get("_d", ""))
