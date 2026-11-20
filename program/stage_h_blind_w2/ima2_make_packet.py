"""Second K-8f blind packet (DR-H2): the 8 ima_k value cases whose only outside check was SciPy.

pla_k-0001 to 0006 (Spearman, KS statistic, zone, asymptotic KS p-value; SciPy spearmanr, ks_2samp, kstwobign) and
es_k-0001, 0002 (normal ES in sigma mode; SciPy integrate.quad). Under the D6 precedent (integration commit 2cef4f98)
a library primitive computing the same quantity does not count, so K-8f stood at 19 of 33 (program/STAGE_K_BLIND_W2.md).

Writes, into <packet dir> (which must lie outside every repository worktree):
  README.md                          the deriver's rules: read only this folder, standard-library Python (no SciPy, no
                                     NumPy, no `statistics` module), outputs, freeze-by-hash
  specs/frtb-ima.blind.md            from specifications/06-risk/frtb-ima.md: title, plain idea, Sources without the
                                     SciPy row, and of the Formal statement only `risk.frtb.pla` and
                                     `risk.frtb.ima.es_lh`; the `risk.frtb.pla.ks_pvalue` paragraph (it names the KS
                                     values of the printed p-values) and the es_k-0005 parenthetical cut; Errors, Limits
  specs/var-es-historical.excerpt.md not included: no case here uses the P&L-list mode
  rulings/stage-k-rulings-w2.blind.md  KR-56, KR-57, KR-67, KR-117 only; the printed p-values sentence of KR-56, the
                                     normal ES factor of KR-57 (it is es_k-0001's answer), the SciPy sentence and the
                                     error-case id of KR-117 cut
  inputs/ima2.inputs.json            per case: case_id, operation, inputs (CASES below; nothing else)
  output_template.json               field definitions and a results skeleton (every field null)
  MANIFEST.sha256                    SHA-256 of every file above
Never reads ima2_expected.json or the golden file. The 250-day series are generated here from the integer formulas
printed in the spec's golden-case section; ima2_compare.py --self-test checks them against the golden on the
hidden side.

    python -I program/stage_h_blind_w2/ima2_make_packet.py <checkout> C:/Work/Claude/qf-blind/ima2_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

SPEC = "specifications/06-risk/frtb-ima.md"
RULINGS = "specifications/stage-k-rulings-w2.md"
KEEP_RULINGS = ("KR-56", "KR-57", "KR-67", "KR-117")
KEEP_FORMAL = ("### `risk.frtb.pla` and `risk.frtb.pla.ks_pvalue`", "### `risk.frtb.ima.es_lh`")

P, E = "risk.frtb.pla", "risk.frtb.ima.es_lh"


def _h():
    return [((7919 * t + 13) % 1009) - 504 for t in range(250)]


def _series(name):
    h = _h()
    return {
        "A": [h[t] + ((37 * t) % 101) - 50 for t in range(250)],
        "B": [h[t] + 4 * (((53 * t) % 211) - 105) for t in range(250)],
        "C": [2 * h[t] + 300 for t in range(250)],
        "D": [((433 * t + 7) % 1009) - 504 for t in range(250)],
        "E": [h[t] + 6 * (((53 * t) % 211) - 105) for t in range(250)],
    }[name]


CASES = [
    ("pla_k-0001", P, {"hpl": [-3, 1, 4, -1, 2], "rtpl": [-2, 0, 5, 1, 3]}),
    ("pla_k-0002", P, {"hpl": _h(), "rtpl": _series("A")}),
    ("pla_k-0003", P, {"hpl": _h(), "rtpl": _series("B")}),
    ("pla_k-0004", P, {"hpl": _h(), "rtpl": _series("C")}),
    ("pla_k-0005", P, {"hpl": _h(), "rtpl": _series("D")}),
    ("pla_k-0006", P, {"hpl": _h(), "rtpl": _series("E")}),
    ("es_k-0001", E, {"sigma": [1, 0, 0, 0, 0]}),
    ("es_k-0002", E, {"sigma": [1, 1, 1, 1, 1]}),
]

FIELDS = {
    P: {"spearman": "real in [-1, 1], r_S",
        "ks": "real in [0, 1], the two-sample KS statistic D = d / n",
        "ks_count": "integer d, the largest absolute difference of the two counts",
        "zone": "string, one of GREEN, AMBER, RED",
        "ks_pvalue_asymptotic": "real in [0, 1], Q_KS(ks sqrt(n/2))"},
    E: {"es_by_horizon": "list of five reals, ES_j for j = 1..5 in list order (currency units, losses positive)",
        "es": "real, the liquidity-horizon-adjusted ES"},
}


def skeleton(op):
    d = dict.fromkeys(FIELDS[op])
    if op == E:
        d["es_by_horizon"] = [None] * 5
    return d


README = """# K-8f second blind re-derivation packet (DR-H2): PLA test statistics and normal expected shortfall

You are the deriver. From the rules in this folder alone, write your own small reference implementation and
compute the outputs of the {n} cases in `inputs/ima2.inputs.json`. Nobody will tell you whether you are right until
your results are frozen.

## Hard rules

1. Read nothing outside this folder, except your own working folder `C:/Work/Claude/qf-blind/ima2_blind/`, where
   everything you write goes. No repository, no other folder on this machine (not even a listing of the parent
   folder), no web page, no earlier conversation about these operations. If a rule here is unclear, decide, write
   the decision down (rule 4) and go on.
2. Write your reference yourself in Python using the standard library only, from the definitions in this folder.
   Not allowed: SciPy, NumPy, mpmath, pandas or any other package; the standard-library `statistics` module (it has
   ranked correlation and a normal distribution object, which would compute the quantities for you); imports from
   any repository. Allowed: `math` (for example `exp`, `sqrt`, `erf`, `erfc`, `pi`, `fsum`), `fractions`, `decimal`,
   `bisect`, `json`, `hashlib` and the like. You compute the normal quantile `Phi^-1(0.975)` yourself (for example
   by bisection or Newton on `math.erfc`); state the method in `notes.md`.
3. Do not round. Report every real as a JSON number at full binary64 precision (Python `json.dumps` of the float).
   Comparison, fixed before you started (ruling KR-67): reals agree when |blind - expected| <= max(1e-12 x
   |expected|, 1e-15); integers and zones exactly; list elements one by one. Every reported field of a case must
   agree for the case to agree.
4. Write `notes.md`: every ambiguity you met and every assumption you made, each with the case ids it affects and
   the file and section of the rule you read. Write it while you work, not afterwards from memory.

## What to produce (in `C:/Work/Claude/qf-blind/ima2_blind/`)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` object (it has the form
   `{{"cases": {{"<case_id>": {{...}}}}}}`) and replace every null with your value. Keep the nesting exactly as in the
   skeleton: the case object holds the output fields directly (no extra "outputs" wrapper); `es_by_horizon` stays a
   list of five numbers. Field meanings are in `output_template.json` under `fields`.
2. `blind_ref.py` (your reference) and `notes.md`.
3. Then, and before you see or ask for anything else: compute the SHA-256 of `blind_results.json`
   (`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" blind_results.json`),
   write it to `blind_results.sha256`, and report that hash as the first line of your hand-back. After that,
   never change `blind_results.json`; a later correction goes in a separate file with its reason.

## What is here

- `specs/frtb-ima.blind.md`: the parts of the spec these operations use (title, plain idea, sources, the formal
  statement of `risk.frtb.pla` and `risk.frtb.ima.es_lh`, errors, limits). Worked examples, case tables, acceptance
  and the other operations are removed.
- `rulings/stage-k-rulings-w2.blind.md`: the rulings that decide the choices the spec leaves open (KR-56, KR-57,
  KR-67, KR-117).
- `inputs/ima2.inputs.json`: per case the case id, the operation and its inputs. Every case is a value case; errors
  are out of scope. `risk.frtb.ima.es_lh` cases use the `sigma` mode only.
- `output_template.json`: what to report per operation and per case.
- `MANIFEST.sha256`: hashes of every file here. Check them first (`sha256sum -c MANIFEST.sha256` or Python) and
  say in `notes.md` whether they matched.
"""


def sub1(pattern, repl, text, what, flags=0):
    text, n = re.subn(pattern, repl, text, flags=flags)
    if n != 1:
        raise SystemExit(f"{what}: pattern found {n} times, expected 1")
    return text


def section(text, head, level="## "):
    m = re.search(r"^" + re.escape(head) + r".*?(?=^" + level.strip() + r" |\Z)", text, flags=re.S | re.M)
    if not m:
        raise SystemExit(f"section {head!r} not found")
    return m.group(0)


def strip_spec(text):
    title = text.splitlines()[0]
    plain = re.search(r"^\*\*Plain idea\.\*\*.*$", text, flags=re.M).group(0)
    sources = section(text, "## Sources")
    sources = sub1(r"^\| \[SciPy\] .*\n", "", sources, "SciPy source row", re.M)
    formal = section(text, "## Formal statement")
    subs = [section(formal, h, "### ") for h in KEEP_FORMAL]
    pla, es = subs
    pla = sub1(r"^`risk\.frtb\.pla\.ks_pvalue`:.*\n", "", pla, "ks_pvalue paragraph", re.M)
    pla = sub1(r"^### `risk\.frtb\.pla` and `risk\.frtb\.pla\.ks_pvalue`", "### `risk.frtb.pla`", pla, "pla heading", re.M)
    pla = sub1(r" Measured 2026-11-19 \(packet builder.*?as well\.", "", pla, "measured note")
    es = sub1(r" \(es_k-0005: lists 2 to 5 empty, es equals ES_1 = [0-9.]+; inferred from the expected values; blind "
              r"lane note, stage_k_blind/w2/notes\.md\)", "", es, "es_k-0005 parenthetical")
    errors = section(text, "## Errors")
    limits = section(text, "## Limits")
    head = (f"{title}\n\nBlind-packet excerpt of `specifications/06-risk/frtb-ima.md` (PROPOSED spec, stage K wave 2, "
            "item K-8f). Kept: plain idea, sources, the formal statement of the two operations used here, errors, "
            "limits. Cut: worked examples, golden cases, acceptance, the other operations, one parenthetical that "
            "quoted a test value. Every output also carries a fixed `label` string (KR-69), not asked for here.\n\n")
    out = head + plain + "\n\n" + sources + "## Formal statement\n\n" + pla + es + errors + limits
    return out.rstrip() + "\n"


def strip_rulings(text):
    lines = text.splitlines()
    head = [ln for ln in lines[:12] if ln.startswith("| # |") or ln.startswith("|---|")][:2]
    rows = []
    for r in KEEP_RULINGS:
        row = [ln for ln in lines if ln.startswith(f"| {r} |")]
        if len(row) != 1:
            raise SystemExit(f"ruling {r} found {len(row)} times")
        row = row[0]
        if r == "KR-56":
            row = sub1(r", which reproduces the printed p-values of MAR32\.42 \([^)]*\)", "", row, "KR-56 p-values")
        if r == "KR-57":
            row = sub1(r", factor [0-9]+\.[0-9]+\.", ".", row, "KR-57 factor")
        if r == "KR-117":
            row = sub1(r" Agreement with SciPy `kstwobign\.sf` within 1e-12 relative is tested on a grid from 0\.05 to 4\.",
                       "", row, "KR-117 SciPy sentence")
            row = sub1(r" \(`E_DOMAIN`, pla_ke-0010\)", " (`E_DOMAIN`)", row, "KR-117 case id")
        rows.append(row)
    return ("# Stage K rulings wave 2: excerpt for the PLA statistics and the normal ES (K-8f)\n\n"
            "From `specifications/stage-k-rulings-w2.md` (PROPOSED). Only the rulings these operations use. Cut from "
            "the rows kept: the KR-56 clause quoting the MAR32.42 printed p-values with our values, the numeric "
            "normal ES factor of KR-57, the KR-117 sentence on the library comparison and an error-case id. The "
            "`risk.var.historical` estimator named in KR-57 is for the P&L-list mode, which no case here uses.\n\n"
            + "\n".join(head + rows) + "\n")


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if (pk / ".git").exists() or any((q / ".git").exists() for q in pk.parents):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit(f"{pk} is not empty; remove it first so no stale file survives")
    write(pk, "specs/frtb-ima.blind.md", strip_spec((root / SPEC).read_text(encoding="utf-8")))
    write(pk, "rulings/stage-k-rulings-w2.blind.md", strip_rulings((root / RULINGS).read_text(encoding="utf-8")))
    rows = [{"case_id": cid, "operation": op, "inputs": inp} for cid, op, inp in CASES]
    write(pk, "inputs/ima2.inputs.json", json.dumps({"item": "K-8f", "cases": rows}, indent=1) + "\n")
    tmpl = {"fields": FIELDS, "results_skeleton": {"cases": {cid: skeleton(op) for cid, op, _ in CASES}}}
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(CASES)))
    files = sorted(p.relative_to(pk).as_posix() for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    man = "".join(f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
    write(pk, "MANIFEST.sha256", man)
    print(f"packet {pk}: {len(files)} files; MANIFEST.sha256 {hashlib.sha256(man.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
