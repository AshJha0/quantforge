"""Stage K blind packet (DR-H2) for the seven K-8 value cases (`CN_RANNACHER_SMOOTHED`, suite k8_k).

Writes, into <packet dir> (which must lie outside every repository worktree):
  README.md                           what the blind lane must produce, and the read-nothing-else rule
  specs/bermudan-ladder-k8.blind.md   the method section of specifications/06-risk/bermudan-ladder-k8.md (steps 1
                                      to 8 and the binary64 and tolerance paragraph); cut: the plain idea, the R6
                                      grid table, the history paragraph of version 0.1.0, the worked example, the
                                      `num.richardson.check` section, convergence, limits and acceptance
  specs/short-rate-models.excerpt.md  the curve conventions, the swaption input and convention lines (G-12) and the
                                      Bermudan section steps (G-18) of specifications/04-pricing/short-rate-models.md;
                                      cut: validation, convergence, evidence and every other operation
  specs/aad-core.excerpt.md           the ladder convention and output list of specifications/06-risk/aad-core.md;
                                      cut: worked example, grid numbers, use restriction, bump reference, performance
  specs/cli-contract.excerpt.md       the two sentences of specifications/cli-contract.md that define the `method` input
  rulings/stage-k-rulings-k8.blind.md KR-8 (with its confirmation note), KR-18 with its "Cause" sentences and
                                      measurements cut, KR-19
  inputs/K-8.inputs.json              per value case: case_id, operation, inputs (read from the golden; nothing else)
  output_template.json                field definitions and a results skeleton (every field null)
  MANIFEST.sha256                     SHA-256 of every file above
Every excerpt is cut by exact anchors (a start anchor must occur exactly once, its end anchor after it); otherwise the build stops, so a changed
source cannot silently pass through. Never reads k8_expected.json; reads only `inputs` from the golden.

    python -I program/stage_h_blind_w2/k8_make_packet.py <checkout> C:/Work/Claude/qf-blind/k8_packet
"""
import hashlib
import json
import sys
from pathlib import Path

GOLDEN = "datasets/golden/stage_k/k8_k.json"
K8 = "specifications/06-risk/bermudan-ladder-k8.md"
SRM = "specifications/04-pricing/short-rate-models.md"
AAD = "specifications/06-risk/aad-core.md"
CLI = "specifications/cli-contract.md"
RUL = "specifications/stage-k-rulings-w1.md"

LADDER = "rates.shortrate.bermudan_ladder"
PRICE = "rates.shortrate.bermudan_swaption"


def one(text, needle, name):
    n = text.count(needle)
    if n != 1:
        raise SystemExit(f"{name}: anchor {needle[:60]!r} found {n} times, expected 1")
    return text.index(needle)


def first(text, needle, start, name):
    """First occurrence of an end anchor after `start`; it must exist."""
    j = text.find(needle, start)
    if j < 0:
        raise SystemExit(f"{name}: end anchor {needle[:60]!r} not found after its start anchor")
    return j


def between(text, start, end, name, include_end=False):
    i = one(text, start, name)
    j = first(text, end, i + len(start), name)
    return text[i:j + (len(end) if include_end else 0)]


def cut(text, start, end, name, repl=""):
    """Remove text[start .. end) (end excluded), each anchor exactly once."""
    i = one(text, start, name)
    j = first(text, end, i + len(start), name)
    return text[:i] + repl + text[j:]


def value_cases(root):
    doc = json.loads((root / GOLDEN).read_text(encoding="utf-8"))
    return [{"case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]}
            for c in doc["cases"] if c["expected"]["status"] == "ok"]


def k8_spec(root):
    t = (root / K8).read_text(encoding="utf-8")
    head = t.splitlines()[0] + "\n\n" + t.splitlines()[2] + "\n\n"
    sec = between(t, "## Method `CN_RANNACHER_SMOOTHED`", "**Worked example.**", K8)
    sec = cut(sec, "Version 0.1.0 of this method", "This section is the full definition.", K8)
    sec = sec.replace("(KR-8 as revised by KR-18)\n\n\n", "(KR-8 as revised by KR-18)\n\n")
    note = ("> Packet note (builder): this file is the method section of the spec only. The plain idea, a table of "
            "grid results, the history of the first definition, a worked example, the guard helper "
            "`num.richardson.check`, the convergence table, the limits and the acceptance tests are cut. References "
            "to files under `program/`, `oracle/` and `conformance/` are to repository files you do not have and "
            "do not need.\n\n")
    return head + note + sec.rstrip() + "\n"


def srm_excerpt(root):
    t = (root / SRM).read_text(encoding="utf-8")
    conv = between(t, "## Conventions", "## `rates.shortrate.zcb`", SRM)
    sw_in = between(t, "Inputs: `curve`, `mean_reversion`, `sigma` (Hull-White, as above; no `short_rate`",
                    "\n", SRM, include_end=True)
    sw_conv = between(t, "Conventions (ruling G-12):", "\n", SRM, include_end=True)
    berm = between(t, "## `rates.shortrate.bermudan_swaption` (stage G wave 2d)", "Output: `price`. Class", SRM)
    return ("# Excerpt: one-factor short-rate models (`04-pricing/short-rate-models.md`, spec version 1.0.0)\n\n"
            "> Packet note (builder): only the parts the K-8 method depends on: the curve conventions, the input "
            "and convention lines of `rates.shortrate.swaption` (which the Bermudan inputs refer to), and the "
            "Bermudan section with the G-18 reference scheme. The K-8 method replaces G-18 steps 1, 4, 5 and 6 "
            "(see `bermudan-ladder-k8.blind.md`); you do not need to implement G-18 itself. Validation, "
            "convergence and evidence paragraphs, and every other operation, are cut.\n\n"
            + conv.rstrip() + "\n\n## `rates.shortrate.swaption` (input and convention lines only)\n\n"
            + sw_in + "\n" + sw_conv + "\n" + berm.rstrip() + "\n\nOutput: `price`.\n")


def aad_excerpt(root):
    t = (root / AAD).read_text(encoding="utf-8")
    formal = between(t, "Formal statement. Let `V(theta)`", " It is not the derivative of the continuous", AAD)
    outs = between(t, "## `rates.shortrate.bermudan_ladder`", "**Use restriction", AAD)
    return ("# Excerpt: AAD core on the rates models (`06-risk/aad-core.md`, spec version 1.0.0)\n\n"
            "> Packet note (builder): the ladder convention and the output list only. Written for the G-18 scheme; "
            "with `method` `CN_RANNACHER_SMOOTHED` read \"the scheme\" as the K-8 scheme (`bermudan-ladder-k8.blind.md` "
            "steps 6 and 7). The worked example, grid results, the use restriction, the bump reference of the stage G "
            "goldens and the performance test are cut.\n\n"
            + formal.rstrip() + "\n\n" + outs.rstrip() + "\n")


def cli_excerpt(root):
    t = (root / CLI).read_text(encoding="utf-8")
    s = between(t, "New optional input `method` on `rates.shortrate.bermudan_swaption`", "Outputs are the G-18 fields.",
                CLI, include_end=True)
    return ("# Excerpt: CLI contract (`specifications/cli-contract.md`, contract 1.17.0)\n\n" + s + "\n\n"
            "> Packet note (builder): the rest of the paragraph (error order, builds, goldens, acceptance status) is "
            "cut; every case in this packet is a value case.\n")


def rulings(root):
    t = (root / RUL).read_text(encoding="utf-8")
    rows = {}
    for r in ("KR-8", "KR-18", "KR-19"):
        rows[r] = between(t, f"| {r} | ", "\n", RUL, include_end=True) if r != "KR-8" else None
    kr8 = between(t, "| KR-8 | Bermudan ladder (K-8, R6-27) |", "\n", RUL, include_end=True)
    kr8c = between(t, "| KR-8 | Superseded in part by KR-18", "\n", RUL, include_end=True)
    kr18 = rows["KR-18"]
    kr18 = kr18.replace("Three changes to the KR-8 method, each with its measured cause and its source.",
                        "Three changes to the KR-8 method, each with its source.", 1)
    kr18 = cut(kr18, " Cause: with `alpha` sampled at step ends", " Source: the factor", RUL)
    kr18 = cut(kr18, " Cause: a ladder entry is an exercise probability", " The end correction removes", RUL)
    kr18 = cut(kr18, "(derived here; measured: space-only refinement", " (c) **Four implicit half steps**", RUL,
               repl="(derived here).")
    kr18 = cut(kr18, " The formulas are in `06-risk/bermudan-ladder-k8.md`", " |\n", RUL,
               repl=" The formulas are in `06-risk/bermudan-ladder-k8.md` version 0.2.0.")
    for bad in ("measured", "18 entries", "1.00", "2.00"):
        if bad in kr18:
            raise SystemExit(f"KR-18 strip left {bad!r}")
    return ("# Stage K rulings used by the K-8 method (excerpt of `specifications/stage-k-rulings-w1.md`)\n\n"
            "> Packet note (builder): KR-8 as drafted, its confirmation note (which says KR-18 replaces its method "
            "definition), KR-18 with its \"Cause\" sentences and measurements cut, and KR-19 (the outside reference "
            "grid; it does not change the method). Other rulings are not used by these cases.\n\n"
            "| # | Point | Ruling |\n|---|---|---|\n" + kr8 + kr18 + rows["KR-19"] +
            "\nConfirmation of KR-8 (stage K coordinator lane, 2026-11-19):\n\n| # | Result | Note |\n|---|---|---|\n" + kr8c)


FIELDS = {
    LADDER: {
        "price": "price of the swaption, currency units (notional x U at the centre node at t = 0)",
        "d_price_d_discount_factors[0..P-1]": "derivative of price per unit absolute change of each input discount "
                                              "factor, in curve order (P = number of curve pillars)",
        "d_price_d_mean_reversion": "derivative of price per unit change of `mean_reversion`",
        "d_price_d_sigma": "derivative of price per unit change of `sigma`",
    },
    PRICE: {"price": "price of the swaption, currency units"},
}


def skeleton(op, inp):
    if op == LADDER:
        return {"price": None, "d_price_d_discount_factors": [None] * len(inp["curve"]["discount_factors"]),
                "d_price_d_mean_reversion": None, "d_price_d_sigma": None}
    if op == PRICE:
        return {"price": None}
    raise KeyError(op)


README = """# Stage K blind re-derivation packet: K-8 Bermudan method `CN_RANNACHER_SMOOTHED` (DR-H2)

You are the blind lane. Your job: from the rules in this folder alone, write your own implementation of the
Bermudan swaption scheme `CN_RANNACHER_SMOOTHED` and of its exact derivative (the "ladder"), and compute the
outputs of the {n} cases in `inputs/K-8.inputs.json`. Nobody will tell you whether you are right until your results
are frozen.

## Hard rules

1. Read nothing outside this folder and your own working folder `C:/Work/Claude/qf-blind/k8_blind/`. No
   repository, no other folder on this machine (not even a listing of the parent folder), no web page, no
   earlier conversation about this method. If a rule here is unclear, decide, write the decision down (rule 4) and
   go on.
2. Write the implementation yourself in Python 3. Allowed: the Python standard library and numpy (any 2.x).
   Not allowed: scipy, QuantLib, any automatic-differentiation library (jax, torch, autograd and the like), and
   any import from a repository. Write the derivative yourself (for example dual numbers carried forward, or a
   reverse sweep). Keep your files in `C:/Work/Claude/qf-blind/k8_blind/`, never inside this packet.
3. Do not round. Report every number as a JSON number at full binary64 precision (Python `json.dumps` of the
   float). The comparison tolerance is stated in `specs/bermudan-ladder-k8.blind.md` (paragraph "Binary64 and
   tolerance"): relative 1e-8 on every output of a `rates.shortrate.bermudan_ladder` case and relative 1e-10 on
   the price of a `rates.shortrate.bermudan_swaption` case. A finite-difference ladder will not reach 1e-8; the
   ladder must be the exact derivative of your discrete scheme.
4. Write `notes.md` while you work: every ambiguity you met and every assumption you made, each with the case ids
   it affects and the file and section of the rule you read; and every discrete choice you had to make that the
   rules did not fix. This list is the main value of the exercise: a gap in the rules is a defect we fix.

## What to produce (in `C:/Work/Claude/qf-blind/k8_blind/`)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` object (form
   `{{"cases": {{"<case_id>": {{...}}}}}}`) and replace every null with your value. Keep the nesting exactly as in the
   skeleton: the case object holds the output fields directly (no extra wrapper), lists stay lists of the same
   length, in curve order.
2. `blind_ref.py` (your implementation, runnable as `python blind_ref.py` to rewrite `blind_results.json`) and
   `notes.md`.
3. Then, and before you see or ask for anything else: compute the SHA-256 of `blind_results.json`
   (`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" blind_results.json`),
   write it to `blind_results.sha256`, and report that hash as the first line of your hand-back. After that,
   never change `blind_results.json`; a later correction goes in a separate file with its reason.

## What is here

- `specs/bermudan-ladder-k8.blind.md`: the method, steps 1 to 8, and the binary64 and tolerance paragraph. Start here.
- `specs/short-rate-models.excerpt.md`: the curve conventions, the swaption conventions and the G-18 Bermudan
  section the method builds on (inputs, grid, exercise rule, boundary rows).
- `specs/aad-core.excerpt.md`: what the ladder outputs mean (derivative of the discrete scheme at the case's grid,
  per unit absolute change of each input discount factor).
- `specs/cli-contract.excerpt.md`: the `method` input.
- `rulings/stage-k-rulings-k8.blind.md`: KR-8, KR-18 (the binding definition), KR-19.
- `inputs/K-8.inputs.json`: per case the case id, the operation (`rates.shortrate.bermudan_ladder` or
  `rates.shortrate.bermudan_swaption`) and its inputs. Every case has `method` `CN_RANNACHER_SMOOTHED`.
- `output_template.json`: what to report per operation and per case.
- `MANIFEST.sha256`: hashes of every file here. Check them first and say in `notes.md` whether they matched.

Errors are out of scope: every case here is a value case with valid inputs. Runtime: a ladder at 201 nodes and
100 steps a year is about 500 time steps; plain Python with dual numbers is fast enough (minutes, not hours).
"""


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


def build(root, pk):
    cases = value_cases(root)
    write(pk, "specs/bermudan-ladder-k8.blind.md", k8_spec(root))
    write(pk, "specs/short-rate-models.excerpt.md", srm_excerpt(root))
    write(pk, "specs/aad-core.excerpt.md", aad_excerpt(root))
    write(pk, "specs/cli-contract.excerpt.md", cli_excerpt(root))
    write(pk, "rulings/stage-k-rulings-k8.blind.md", rulings(root))
    write(pk, "inputs/K-8.inputs.json", json.dumps({"item": "K-8", "cases": cases}, indent=1) + "\n")
    tmpl = {"fields": FIELDS,
            "path_notation": "a[0..P-1] means list a, positions 0 to P-1",
            "results_skeleton": {"cases": {c["case_id"]: skeleton(c["operation"], c["inputs"]) for c in cases}}}
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(cases)))
    files = sorted(p.relative_to(pk).as_posix() for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    man = "".join(f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
    write(pk, "MANIFEST.sha256", man)
    return len(files), hashlib.sha256(man.encode()).hexdigest()


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if (pk / ".git").exists() or any((q / ".git").exists() for q in pk.parents):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit(f"{pk} is not empty; remove it first so no stale file survives")
    n, h = build(root, pk)
    print(f"packet {pk}: {n} files; MANIFEST.sha256 {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
