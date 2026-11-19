"""Stage K wave 2 blind packet (DR-H2) for the 58 hand value cases of K-8a, K-8f, K-8g, K-8i.

Writes, into <packet dir> (which must lie outside every repository worktree):
  README.md                         what the blind lane must produce, and the read-nothing-else rule
  specs/<item>.blind.md             the four PROPOSED specs with the sections "Worked example(s)", "Golden cases" and
                                    "Acceptance" cut (they print expected values, intermediates and hand arithmetic);
                                    Sources, plain idea, Formal statement (rules, formulas, schemas), Errors, Limits stay
  specs/var-es-historical.excerpt.md  the ES estimator that KR-57 points to (var-es-and-backtests.md: units line,
                                    order statistic rule, risk.var.historical); the "why it changed" history is cut
  rulings/stage-k-rulings-w2.blind.md  rulings with KR-56 (PLA only; prints p-values) and KR-68 (gate classes) cut
  tables/*.json                     the nine stage K wave 2 parameter tables, byte for byte
  inputs/<item>.inputs.json         per case: case_id, operation, inputs (from k2_cases.py; nothing else)
  output_template.json              field definitions and units per operation, and a results skeleton (every field
                                    to report, set to null)
  MANIFEST.sha256                   SHA-256 of every file above
Never reads k2_expected.json.

    python -I program/stage_h_blind_w2/k2_make_packet.py <checkout> C:/Work/Claude/qf-blind/k2_packet
"""
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from k2_cases import CASES, ITEMS, by_item  # noqa: E402

SPECS = {item: f"specifications/06-risk/{name}.md" for item, name in ITEMS.items()}
CUT = ("Worked example", "Golden cases", "Acceptance")
TABLES = ["cre53_imm", "lev_leverage", "lex_large_exposures", "mar22_drc", "mar23_rrao", "mar31_rfet",
          "mar32_pla", "mar33_ima", "mar50_cva"]
CUT_RULINGS = ("KR-56", "KR-68")

FIELDS = {
    "risk.frtb.drc_nonsec": {
        "positions[<id>].gross_jtd": "currency units, signed (long > 0, short < 0); before the maturity weight",
        "positions[<id>].weight": "maturity weight, dimensionless",
        "positions[<id>].scaled_jtd": "currency units, signed; weight x gross_jtd",
        "obligors[<obligor>].net_long": "currency units, >= 0, after the offsetting within the obligor",
        "obligors[<obligor>].net_short": "currency units, <= 0, after the offsetting within the obligor",
        "obligors[<obligor>].rw": "risk weight as a fraction (0.06 means 6%)",
        "buckets[<bucket>].hbr": "hedge benefit ratio as a fraction; null when not defined",
        "buckets[<bucket>].wtd_long": "currency units, sum of rw x net_long over the bucket (>= 0)",
        "buckets[<bucket>].wtd_short": "currency units, sum of rw x |net_short| over the bucket (>= 0, absolute value)",
        "buckets[<bucket>].drc": "currency units",
        "drc": "currency units, total",
    },
    "risk.frtb.drc_ctp": {
        "hbr_ctp": "fraction (positions mode only; omit the key in bucket_drc mode)",
        "buckets[<index>].drc": "currency units, signed DRC_b before the MAR22.45 aggregation (positions mode only)",
        "drc": "currency units, DRC_CTP",
    },
    "risk.frtb.drc_sec_nonctp": {
        "buckets[<bucket>].hbr": "fraction",
        "buckets[<bucket>].drc": "currency units",
        "drc": "currency units, total",
    },
    "risk.frtb.rrao": {"rrao": "currency units"},
    "risk.frtb.ima.es_lh": {
        "es_by_horizon[0..4]": "ES_T(P,j) for j = 1..5 in list order, currency units (losses positive)",
        "es": "currency units, liquidity-horizon-adjusted ES",
    },
    "risk.frtb.ima.es_stressed": {
        "ratio": "ES_F,C / ES_R,C before any floor, dimensionless",
        "ratio_floored": "boolean, true when the floor at 1 binds",
        "es": "currency units, stressed ES",
    },
    "risk.frtb.ima.imcc": {
        "imcc_c": "currency units, IMCC(C) of the portfolio",
        "classes[<class>]": "currency units, IMCC(C_i) of that risk class (a number, not an object)",
        "imcc": "currency units, aggregate IMCC",
    },
    "risk.frtb.ima.ses": {"ses": "currency units"},
    "risk.frtb.ima.capital": {
        "m_c": "multiplier, dimensionless", "c_a": "currency units", "ima_ga": "currency units, IMA_G,A",
        "sa_ga": "currency units, SA_G,A", "k": "dimensionless", "surcharge": "currency units",
        "acr_total": "currency units",
    },
    "risk.frtb.rfet": {
        "distinct_days": "integer, distinct observation days inside the 12-month window",
        "crit1": "boolean", "crit2": "boolean", "pass": "boolean",
        "min_window_count": "integer, smallest count of distinct observation days over all 90-day windows lying wholly inside the 12 months",
        "first_failing_window_start": "ISO date (YYYY-MM-DD) of the earliest-starting such 90-day window with fewer than 4 distinct days; null if none",
        "first_failing_window_count": "integer, the count in that window; null if none",
    },
    "risk.cva.ba": {
        "counterparties[<id>].scva": "currency units",
        "counterparties[<id>].snh": "currency units (FULL only; omit for REDUCED)",
        "counterparties[<id>].hma": "currency units squared, as the formula gives it (FULL only)",
        "ih": "currency units (FULL only)", "k_reduced": "currency units",
        "k_hedged": "currency units (FULL only)", "k_full": "currency units (FULL only)",
        "capital": "currency units", "rwa": "currency units",
    },
    "risk.cva.sa": {
        "classes[<CLASS.KIND>].buckets[<bucket>].k_b": "currency units",
        "classes[<CLASS.KIND>].buckets[<bucket>].s_b": "currency units, signed",
        "classes[<CLASS.KIND>].buckets[<bucket>].sum_ws": "currency units, signed sum of WS_k in the bucket before clipping",
        "classes[<CLASS.KIND>].buckets[<bucket>].floored": "boolean, true when a radicand was floored at 0",
        "classes[<CLASS.KIND>].k": "currency units, capital of that class and kind (m_cva applied)",
        "total": "currency units, sum over every class and kind", "rwa": "currency units",
    },
    "risk.capital.leverage": {
        "on_balance": "currency units", "derivatives": "currency units", "written_credit_derivatives": "currency units",
        "sfts": "currency units", "off_balance": "currency units", "exposure": "currency units, total exposure measure",
        "ratio": "fraction (0.05 means 5%), tier1 / exposure", "meets_minimum": "boolean",
    },
    "risk.capital.large_exposures": {
        "groups[<group>].exposure": "currency units",
        "groups[<group>].share": "fraction of tier1 (0.05 means 5%)",
        "groups[<group>].large": "boolean", "groups[<group>].limit": "currency units", "groups[<group>].breach": "boolean",
    },
}


def skeleton(op, inp):
    """Every field to report for this case, set to null, in the nested shape the compare script reads."""
    if op == "risk.frtb.drc_nonsec":
        P = inp["positions"]
        return {"positions": {p["id"]: dict.fromkeys(("gross_jtd", "weight", "scaled_jtd")) for p in P},
                "obligors": {o: dict.fromkeys(("net_long", "net_short", "rw")) for o in dict.fromkeys(p["obligor"] for p in P)},
                "buckets": {b: dict.fromkeys(("hbr", "wtd_long", "wtd_short", "drc")) for b in dict.fromkeys(p["bucket"] for p in P)},
                "drc": None}
    if op == "risk.frtb.drc_ctp":
        if "bucket_drc" in inp:
            return {"drc": None}
        return {"hbr_ctp": None, "buckets": {i: {"drc": None} for i in dict.fromkeys(p["index"] for p in inp["positions"])}, "drc": None}
    if op == "risk.frtb.drc_sec_nonctp":
        return {"buckets": {b: {"hbr": None, "drc": None} for b in dict.fromkeys(p["bucket"] for p in inp["positions"])}, "drc": None}
    if op == "risk.frtb.rrao":
        return {"rrao": None}
    if op == "risk.frtb.ima.es_lh":
        return {"es_by_horizon": [None] * 5, "es": None}
    if op == "risk.frtb.ima.es_stressed":
        return {"ratio": None, "ratio_floored": None, "es": None}
    if op == "risk.frtb.ima.imcc":
        return {"imcc_c": None, "classes": dict.fromkeys(inp["classes"]), "imcc": None}
    if op == "risk.frtb.ima.ses":
        return {"ses": None}
    if op == "risk.frtb.ima.capital":
        return dict.fromkeys(("m_c", "c_a", "ima_ga", "sa_ga", "k", "surcharge", "acr_total"))
    if op == "risk.frtb.rfet":
        return dict.fromkeys(("distinct_days", "crit1", "min_window_count", "first_failing_window_start",
                              "first_failing_window_count", "crit2", "pass"))
    if op == "risk.cva.ba":
        full = inp["version"] == "FULL"
        per = ("scva", "snh", "hma") if full else ("scva",)
        d = {"counterparties": {c["id"]: dict.fromkeys(per) for c in inp["counterparties"]}}
        d.update(dict.fromkeys(("ih", "k_reduced", "k_hedged", "k_full", "capital", "rwa") if full else ("k_reduced", "capital", "rwa")))
        return d
    if op == "risk.cva.sa":
        cl = {}
        for ck, sens in inp["classes"].items():
            cl[ck] = {"buckets": {s["bucket"]: dict.fromkeys(("k_b", "s_b", "sum_ws", "floored")) for s in sens}, "k": None}
        return {"classes": cl, "total": None, "rwa": None}
    if op == "risk.capital.leverage":
        return dict.fromkeys(("on_balance", "derivatives", "written_credit_derivatives", "sfts", "off_balance", "exposure", "ratio", "meets_minimum"))
    if op == "risk.capital.large_exposures":
        gs = dict.fromkeys(c.get("group", c["id"]) for c in inp["counterparties"])
        return {"groups": {g: dict.fromkeys(("exposure", "share", "large", "limit", "breach")) for g in gs}}
    raise KeyError(op)


README = """# Stage K wave 2 blind re-derivation packet (DR-H2)

You are the blind lane. Your job: from the rules in this folder alone, write your own small reference
implementation and compute the outputs of the {n} cases in `inputs/`. Nobody will tell you whether you are right
until your results are frozen.

## Hard rules

1. Read nothing outside this folder. No repository, no other folder on this machine, no web page, no earlier
   conversation about these specs. If a rule here is unclear, decide, write the decision down (rule 4) and go on.
2. Write your reference yourself: plain Python (standard library only is fine), no imports from any repository.
   Keep it in your own working folder next to (not inside) this packet, for example `../k2_blind/`.
3. Do not round. Report every number as a JSON number at full binary64 precision (Python `json.dumps` of the float).
   The rulings (KR-67) fix the comparison tolerance at 1e-12 relative (1e-15 absolute at 0); you do not need to
   aim for it, just compute in binary64.
4. Write `notes.md`: every ambiguity you met and every assumption you made, each with the case ids it affects and
   the file and section of the rule you read. Write it while you work, not afterwards from memory.

## What to produce (in your own working folder)

1. `blind_results.json`: copy `output_template.json`'s `results_skeleton` object (it has the form
   `{{"cases": {{"<case_id>": {{...}}}}}}`) and replace every null with your value. Keep the nesting exactly as in the
   skeleton: the case object holds the output fields directly (no extra "outputs" wrapper), keyed objects stay
   objects, lists stay lists. A field that the rules say does not exist for that case stays null. Field meanings and
   units are in `output_template.json` under `fields`: amounts in the currency units of the inputs, ratios and
   shares as fractions (0.05, not 5), dates as `YYYY-MM-DD` strings.
2. `blind_ref.py` (your reference) and `notes.md`.
3. Then, and before you see or ask for anything else: compute the SHA-256 of `blind_results.json`
   (`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" blind_results.json`),
   write it to `blind_results.sha256`, and report that hash as the first line of your hand-back. After that,
   never change `blind_results.json`; a later correction goes in a separate file with its reason.

## What is here

- `specs/*.blind.md`: the four draft specs with their worked examples, case tables and acceptance sections removed.
  Rules, formulas, input and output schemas, errors and limits are complete. `specs/var-es-historical.excerpt.md`
  is the ES estimator ruling KR-57 refers to.
- `rulings/stage-k-rulings-w2.blind.md`: the rulings that decide the choices the texts leave open.
- `tables/*.json`: the parameter tables (decimal strings; percentages as fractions).
- `inputs/K-8a.inputs.json` (DRC, RRAO), `K-8f` (IMA), `K-8g` (CVA), `K-8i` (leverage, large exposures): per case
  the case id, the operation and its inputs. Each input object is complete; where a spec field is optional and
  absent, its stated default applies.
- `output_template.json`: what to report per operation and per case.
- `MANIFEST.sha256`: hashes of every file here. Check them first (`sha256sum -c MANIFEST.sha256` or Python) and
  say in `notes.md` whether they matched.

Input conventions you will need: `inputs` for `risk.cva.sa` key the class lists as `<CLASS>.<KIND>` (for example
`IR.DELTA`, `CCS.DELTA`, `IR.VEGA`); for `risk.cva.ba` the `sector` values are the keys of `ba.rw` in
`tables/mar50_cva.json` and the risk weight pair there is (IG, HY_NR). For `risk.capital.large_exposures` the
input `bank_gsib` says whether the reporting bank itself is a G-SIB. Errors are out of scope: every case here is
a value case.
"""


def strip_spec(text, name):
    for sec in CUT:
        text, n = re.subn(r"^## " + sec + r".*?(?=^## |\Z)", "", text, flags=re.S | re.M)
        if n != 1:
            raise SystemExit(f"{name}: section '{sec}' found {n} times, expected 1")
    return text


def es_excerpt(text):
    lines = text.splitlines()
    keep = [lines[6]]  # losses positive line
    i = lines.index("## Order statistic rule (ruling F-31)")
    j = next(k for k in range(i, len(lines)) if lines[k].startswith("Why it changed"))
    keep += [""] + lines[i:j]
    h = lines.index("## `risk.var.historical`")
    keep += lines[h:h + 3]
    return ("# Excerpt: expected shortfall estimator (`risk.var.historical`)\n\n"
            "From `specifications/06-risk/var-es-and-backtests.md` (spec version 1.0.0): the units line, the order "
            "statistic rule and the operation. Ruling KR-57 uses this estimator with confidence 0.975.\n\n"
            + "\n".join(keep).rstrip() + "\n")


def strip_rulings(text):
    out = []
    for ln in text.splitlines():
        if any(ln.startswith(f"| {r} |") for r in CUT_RULINGS):
            continue
        out.append(ln)
    return "\n".join(out) + "\n" + "\nCut from this copy: " + ", ".join(CUT_RULINGS) + " (not used by these cases).\n"


def write(pk, rel, data):
    p = pk / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    p.write_bytes(data)


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if (pk / ".git").exists() or any((q / ".git").exists() for q in pk.parents):
        raise SystemExit("packet dir is inside a git worktree; refusing")
    if pk.exists() and any(pk.iterdir()):
        raise SystemExit(f"{pk} is not empty; remove it first so no stale file survives")
    for item, rel in SPECS.items():
        name = Path(rel).stem
        write(pk, f"specs/{name}.blind.md", strip_spec((root / rel).read_text(encoding="utf-8"), name))
    write(pk, "specs/var-es-historical.excerpt.md", es_excerpt((root / "specifications/06-risk/var-es-and-backtests.md").read_text(encoding="utf-8")))
    write(pk, "rulings/stage-k-rulings-w2.blind.md", strip_rulings((root / "specifications/stage-k-rulings-w2.md").read_text(encoding="utf-8")))
    for t in TABLES:
        write(pk, f"tables/{t}.json", (root / f"specifications/tables/stage_k/{t}.json").read_bytes())
    for item, rows in by_item().items():
        write(pk, f"inputs/{item}.inputs.json", json.dumps({"item": item, "cases": rows}, indent=1) + "\n")
    tmpl = {"fields": FIELDS,
            "path_notation": "a[<key>].b means object a, member <key>, member b; [0..4] are list positions",
            "results_skeleton": {"cases": {cid: skeleton(op, inp) for cid, _, op, inp in CASES}}}
    write(pk, "output_template.json", json.dumps(tmpl, indent=1) + "\n")
    write(pk, "README.md", README.format(n=len(CASES)))
    files = sorted(p.relative_to(pk).as_posix() for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    man = "".join(f"{hashlib.sha256((pk / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
    write(pk, "MANIFEST.sha256", man)
    print(f"packet {pk}: {len(files)} files; MANIFEST.sha256 {hashlib.sha256(man.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
