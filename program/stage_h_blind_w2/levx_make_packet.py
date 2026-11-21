"""K-8i blind packet (DR-H2) for the uncounted value cases of lev_k and lex_k.

Cases: lev_k-0001..0005 (printed-figure cases, not yet blind), lev_k-0012, lev_k-0013, lex_k-0008, lex_k-0009.
Pattern: tlk_v2_make_packet.py (program/STAGE_K_BLIND_TLK_V2.md). Writes into <packet dir> (outside every
worktree, empty): README.md, specs/leverage-large-exposures.blind.md, rulings/k8i.blind.md,
tables/lev_leverage.json, tables/lex_large_exposures.json, inputs/k8i.inputs.json, output_template.json,
MANIFEST.sha256, then runs the leak check (every expected number searched in every packet file).
Source text: the "Formal statement" section of specifications/06-risk/leverage-large-exposures.md (the worked
examples, golden table and acceptance sections are not included) and rulings KR-51, KR-53, KR-65, KR-66, KR-319,
KR-320, KR-322 to KR-326 of specifications/stage-k-rulings-w2.md, with the cuts in CUTS (golden ids and blind-lane
history). Inputs are read from the goldens, `inputs` only. The leak check reads levx_expected.json only after
the packet is written and only to search the packet; the packet text never depends on it.

    python -I program/stage_h_blind_w2/levx_make_packet.py . C:/Work/Claude/qf-blind/k8i_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

CASES = [f"lev_k-{i:04d}" for i in (1, 2, 3, 4, 5, 12, 13)] + ["lex_k-0008", "lex_k-0009"]
SPEC = "specifications/06-risk/leverage-large-exposures.md"
RULINGS = "specifications/stage-k-rulings-w2.md"
KR = ["KR-51", "KR-53", "KR-65", "KR-66", "KR-319", "KR-320", "KR-322", "KR-323", "KR-324", "KR-325", "KR-326"]
CUTS = {
    "KR-320": [(r" and the lev_k-0004 and 0005 rows", "")],
    "KR-324": [(r" The blind lane assumed.*?depends on it\.", ""), (r"; the blind packet added the same field", "")],
    "KR-326": [(r"; the boundary goldens use Tier 1 1000, where both products are exact", "")],
}
LEV_OUT = ["on_balance", "derivatives", "derivative_netting_sets", "written_credit_derivatives", "sfts", "off_balance",
           "exposure", "ratio", "meets_minimum", "label"]
LEX_OUT = ["counterparties", "groups", "report", "label"]

README = """# K-8i blind re-derivation packet (DR-H2)

You are the blind lane. From the rules in this folder alone, compute the outputs of the 9 cases in `inputs/`
(7 of `risk.capital.leverage`, 2 of `risk.capital.large_exposures`). Nobody will tell you whether you are right
until your results are frozen.

## Hard rules

1. Read nothing outside this folder and your own working folder. No repository, no web page.
2. Write your reference yourself: plain Python, standard library only. Prefer exact arithmetic
   (`fractions.Fraction` of each binary64 input) and round once to binary64 at the end; comparisons stated in
   binary64 by the rules (the leverage minimum, `large`, `breach`) follow the rules as written.
3. Numbers as JSON numbers at full binary64 precision; booleans as JSON booleans; strings exactly.
4. Write `notes.md`: every ambiguity and assumption, with case ids and the file and section read.

## Output shape

- Leverage cases: an object with the fields of the spec "Outputs" line: `on_balance`, `derivatives`
  (netting sets plus effective notionals of written credit derivatives, KR-320), `derivative_netting_sets`,
  `written_credit_derivatives`, `sfts`, `off_balance`, `exposure`, `ratio`, `meets_minimum`, `label`.
- Large exposures cases: `counterparties`: one row per input counterparty, in input order, with `id`,
  `banking_book`, `off_balance` (converted), `trading_book_net_long`, `trading_book_net_short` (the net short,
  zero or negative), `protected`, `received`, `exposure`; `groups`: one row per group in label code-point order
  with `group`, `members` (ids in input order), `exposure`, `share`, `large`, `limit`, `breach`, `exempt`;
  `report`: the list of group labels (KR-326 order); `label`.

## What to produce (in your own working folder)

1. `blind_results.json`: `{"cases": {"<case_id>": {field: value}}}`, starting from `output_template.json`.
2. `blind_ref.py` and `notes.md`.
3. SHA-256 of `blind_results.json` into `blind_results.sha256`; report it as the first line of your hand-back.
   Never change `blind_results.json` after that.
"""


def cut(text, cuts, what):
    for pat, rep in cuts:
        text, k = re.subn(pat, rep, text, flags=re.S)
        if k != 1:
            raise SystemExit(f"cut not applied once in {what}: {pat}")
    return text


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield o


def forms(v):
    out = {repr(float(v)), f"{v:.6g}", f"{v:.4g}"}
    if float(v).is_integer():
        out |= {str(int(v)), f"{int(v):,}"}
    return {s for s in out if s not in ("0", "0.0", "1", "1.0", "-0.0")}


def leak_check(repo, out, inputs):
    exp = json.loads((repo / "program/stage_h_blind_w2/levx_expected.json").read_text(encoding="utf-8"))
    texts = {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8") for p in out.rglob("*")
             if p.is_file() and p.name != "MANIFEST.sha256" and not p.relative_to(out).as_posix().startswith("inputs/")}
    hits = []
    for cid, ex in exp.items():
        own = json.dumps(inputs[cid])
        for v in set(leaves(ex["outputs"])):
            for s in forms(v):
                pat = r"(?<![\d.])" + re.escape(s) + r"(?![\d])"
                if re.search(pat, own):
                    continue
                hits += [f"{cid} {s} in {name}" for name, t in texts.items() if re.search(pat, t)]
    print("leak check:", "no hit" if not hits else f"{len(set(hits))} hits")
    for h in sorted(set(hits)):
        print("  HIT", h)


def main(repo, out):
    repo, out = Path(repo), Path(out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit("packet dir not empty")
    spec = (repo / SPEC).read_text(encoding="utf-8")
    sec = re.search(r"^## Formal statement\n.*?(?=^## )", spec, re.S | re.M).group(0)
    rows = (repo / RULINGS).read_text(encoding="utf-8").splitlines()
    kr = []
    for k in KR:
        r = next(line for line in rows if line.startswith(f"| {k} "))
        kr.append(cut(r, CUTS.get(k, []), k))
    inputs = {}
    for suite in ("lev_k", "lex_k"):
        g = json.loads((repo / f"datasets/golden/stage_k/{suite}.json").read_text(encoding="utf-8"))
        inputs.update({c["case_id"]: {"operation": c["operation"], "inputs": c["inputs"]}
                       for c in g["cases"] if c["case_id"] in CASES})
    assert sorted(inputs) == sorted(CASES)
    skel = {k: {f: None for f in (LEV_OUT if k.startswith("lev") else LEX_OUT)} for k in CASES}
    tables = repo / "specifications/tables/stage_k"
    files = {
        "README.md": README,
        "specs/leverage-large-exposures.blind.md": "# Spec excerpt (stripped)\n\n" + sec,
        "rulings/k8i.blind.md": "# Rulings (stripped)\n\n| # | Point | Ruling |\n|---|---|---|\n" + "\n".join(kr) + "\n",
        "tables/lev_leverage.json": (tables / "lev_leverage.json").read_text(encoding="utf-8"),
        "tables/lex_large_exposures.json": (tables / "lex_large_exposures.json").read_text(encoding="utf-8"),
        "inputs/k8i.inputs.json": json.dumps({"cases": inputs}, indent=1) + "\n",
        "output_template.json": json.dumps({"results_skeleton": {"cases": skel}}, indent=1) + "\n",
    }
    lines = []
    for name, body in files.items():
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode("utf-8"))
        lines.append(f"{hashlib.sha256(body.encode('utf-8')).hexdigest()}  {name}")
    (out / "MANIFEST.sha256").write_bytes(("\n".join(lines) + "\n").encode())
    print("MANIFEST", hashlib.sha256((out / "MANIFEST.sha256").read_bytes()).hexdigest())
    leak_check(repo, out, inputs)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
