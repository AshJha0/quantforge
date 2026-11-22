"""Random-invalid-input differential for the xva operations (lane k-v1-fix, KR-258 sweep).

Usage: python program/stage_k_fix/fuzz.py N SEED out.jsonl (N requests per operation); then probe.py out.jsonl."""
import copy, json, random, sys
R = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 258)
G = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_g") + "/"
OPS = {"xva.exposure.collateralised": "collexp_g", "xva.adjustments.value": "xvaadj_g", "xva.sbim.ir_delta": "sbim_g",
       "xva.wwr.cva_hw": "wwr_g", "xva.exposure.portfolio_hw": "expsim_g", "xva.exposure.swap_ee_hw": "exposure_g"}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
def paths(o, pre=()):
    yield pre, o
    if isinstance(o, dict):
        for k, v in o.items(): yield from paths(v, pre + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from paths(v, pre + (i,))
def setp(o, p, v):
    for k in p[:-1]: o = o[k]
    if v is DEL:
        del o[p[-1]]
    else: o[p[-1]] = v
DEL = object()
VALS = [float("inf"), 0.0, -0.0, -1.0, -1e-300, 1e-310, 1.0, 1.5, 2.0, 700.0, 1e308, -1e308, 1e300, 0.5, -0.5, 1e-12, 10, -3, 0]
def mutate(inp):
    ps = [p for p, _ in paths(inp) if p]
    p = R.choice(ps)
    parent = inp
    for k in p[:-1]: parent = parent[k]
    cur = parent[p[-1]]
    r = R.random()
    if r < 0.12 and isinstance(parent, dict): setp(inp, p, DEL); return f"del {p}"
    if isinstance(cur, list):
        c = R.randrange(6)
        if c == 0: setp(inp, p, []); return f"empty {p}"
        if c == 1 and cur: setp(inp, p, cur[:-1]); return f"short {p}"
        if c == 2 and cur: setp(inp, p, cur + [cur[-1]]); return f"long {p}"
        if c == 3 and cur: setp(inp, p, list(reversed(cur))); return f"rev {p}"
        if c == 4 and cur and isinstance(cur[0], (int, float)): x = list(cur); x[0] = x[1] if len(x) > 1 else x[0]; setp(inp, p, x); return f"dup {p}"
        setp(inp, p, R.choice(["x", 1.0, None, {}])); return f"type {p}"
    if isinstance(cur, bool): setp(inp, p, R.choice([1, "true", None])); return f"type {p}"
    if isinstance(cur, (int, float)):
        v = R.choice(VALS) if R.random() < 0.8 else R.choice(["1", None, [1.0], True])
        setp(inp, p, v); return f"set {p}={v!r}"
    if isinstance(cur, str): setp(inp, p, R.choice(["", "zz", 1])); return f"str {p}"
    if isinstance(cur, dict): setp(inp, p, R.choice([{}, [], 1])); return f"obj {p}"
    setp(inp, p, None); return f"null {p}"
out = []
for op, suite in OPS.items():
    cases = [c for c in json.load(open(G + suite + ".json", encoding="utf-8"))["cases"] if c["operation"] == op and c["expected"]["status"] == "ok"]
    if not cases: print("no base for", op); continue
    for k in range(N):
        inp = copy.deepcopy(R.choice(cases)["inputs"])
        desc = [mutate(inp) for _ in range(1 if R.random() < 0.6 else 2)]
        if R.random() < 0.05: inp["unknown_key"] = 1; desc.append("extra key")
        out.append({"case_id": f"{op}#{k}", "operation": op, "inputs": inp, "_d": "; ".join(desc)})
    if op == "xva.sbim.ir_delta":
        for c in out[-N:]:
            out.append(dict(c, case_id=c["case_id"].replace("sbim", "simm"), operation="xva.simm.ir_delta"))
with open(sys.argv[3] if len(sys.argv) > 3 else "fuzz.jsonl", "w", encoding="utf-8") as f:
    for c in out: f.write(json.dumps(c) + "\n")
