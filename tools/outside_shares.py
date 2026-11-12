#!/usr/bin/env python3
"""Outside-check shares under the R6-13 rule (owner decision D6, review finding 6). Standard library only.

    python tools/outside_shares.py            write oracle/OUTSIDE_SHARES.json and oracle/OUTSIDE_SHARES.md
    python tools/outside_shares.py --check    regenerate in memory; exit 1 if the committed copy differs, if a
                                              register's suite totals differ from the goldens, or if a stage is
                                              under the floor without a dated plan in PLANS below

Evidence classes (D6). A case counts towards the outside share only as `library-object` or `library-primitive`,
and only if every compared output of the case is checked:
  library-object     a library's own pricing or estimation object (QuantLib engine, ORE simulation, arch model)
  library-primitive  numpy or scipy numerics applied to a different formulation of the same problem
  reimplementation   the spec formula written again around a library call (does not count)
  none               no outside check, or a published worked example only (does not count)

Denominator: every case of the stage, error cases included (ruling I-2), so a stage cannot raise its share by
adding error cases. Generated sweeps (stage F `e1_*` edge suites, stage I wave 5 seeded variants `*5_i`) are
shown separately and the floor is applied without them (plan 14.10 rule 3: report with and without added cases).
Per-case registers (D, E, F) are classified case by case; stage G and I registers hold suite counts only, so the
class is ruled per suite in SUITE_CLASS and the per-case regeneration of those registers is an open R6-13 item.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "oracle"
GOLDEN = ROOT / "datasets" / "golden"
FLOOR = 0.60
COUNTED = ("library-object", "library-primitive")
CLASSES = COUNTED + ("reimplementation", "none")

STAGE_DIRS = {"D": ["stage_d"], "E": ["stage_e", "stage_e_b"], "F": ["stage_f"], "G": ["stage_g"], "I": ["stage_i"]}

# Stage F convention rows naming a numpy or scipy primitive. Kupiec (SCIPY.BINOM) and Christoffersen (SCIPY.CHI2)
# cases rebuild the spec's likelihood-ratio formula around a distribution call: reimplementation (review finding 6).
PRIMITIVE_ROWS = {"SCIPY.QUAD", "SCIPY.EIGH", "NUMPY.QUANTILE", "SCIPY.NORM", "SCIPY.LSTSQ"}
REIMPL_ROWS = {"SCIPY.BINOM", "SCIPY.CHI2"}

# Suite-level rulings for registers that hold counts only (stage G, stage I). Reviewed 2026-11-12 by the R6
# evidence lane against each register's own rule text; second review open.
SUITE_CLASS = {
    # stage G
    "shortrate_g": ("library-object", "QuantLib 1.44 short-rate model discountBond and discountBondOption"),
    "shortrate_r5": ("library-object", "QuantLib CoxIngersollRoss discountBondOption (rows of shortrate_g)"),
    "g2pp_g": ("library-object", "QuantLib 1.44 G2 discountBond and discountBondOption"),
    "g2pp_r5": ("library-object", "QuantLib G2 (rows of g2pp_g)"),
    "capfloor_g": ("library-object", "QuantLib 1.44 discountBondOption per caplet; (1 + K tau) scaling is the identity"),
    "swaption_g": ("library-object", "QuantLib 1.44 JamshidianSwaptionEngine"),
    "swaption_affine_g": ("library-object", "QuantLib 1.44 JamshidianSwaptionEngine"),
    "barrier_g": ("library-object", "QuantLib 1.44 analytic barrier engine, continuous-monitoring rows only"),
    "expsim_g": ("library-object", "ORE 1.8.17 LGM simulation, within 3 MC standard errors"),
    "exposure_g": ("reimplementation", "CVA by G-16 bucket arithmetic on QuantLib engine exposures"),
    "lmmcap_g": ("library-primitive", "QuantLib AbcdFunction.covariance and blackFormula assembled per caplet"),
    "lmmswn_g": ("library-primitive", "QuantLib AbcdFunction.covariance and blackFormula assembled per swaption"),
    # stage I
    "hedgeqp_i": ("library-primitive", "scipy 1.18 lsq_linear, lstsq, SLSQP"),
    "hedgeqp5_i": ("library-primitive", "scipy 1.18, as hedgeqp_i (wave 5 seeded)"),
    "hedgecost_i": ("library-primitive", "scipy 1.18 solvers"),
    "hedgefrontier_i": ("library-primitive", "scipy 1.18 solvers at each frontier point"),
    "hedgeselect_i": ("library-primitive", "scipy 1.18 per subset"),
    "hedgemv_i": ("library-primitive", "numpy 2.5 solve, lstsq"),
    "hedgemv5_i": ("library-primitive", "numpy 2.5, as hedgemv_i (wave 5 seeded)"),
    "hedgeeff_i": ("library-primitive", "numpy 2.5 polyfit, corrcoef, var"),
    "hedgeeff5_i": ("library-primitive", "numpy 2.5, as hedgeeff_i (wave 5 seeded)"),
    "hedgegreeks_i": ("library-primitive", "QuantLib Greeks, hedge quantities by numpy solve"),
    "hedgegreeks5_i": ("library-primitive", "as hedgegreeks_i (wave 5 seeded)"),
    "hedgecorr_i": ("library-primitive", "QuantLib Margrabe Greeks, quantities by numpy solve"),
    "hedgecorr5_i": ("library-primitive", "as hedgecorr_i (wave 5 seeded)"),
    "hedgecredit_i": ("library-primitive", "QuantLib IsdaCdsEngine NPVs, quantities by numpy solve"),
    "hedgexa_i": ("library-primitive", "QuantLib ZeroCurve and engine values, numpy lstsq"),
    "hedgebt_i": ("reimplementation", "QuantLib values per date, then the spec's cash-account arithmetic"),
    "hedgebtcost_i": ("reimplementation", "as hedgebt_i, with costs"),
}

# Dated plans for stages under the floor (R6-13 acceptance: reach 60% or publish the true figure with a dated plan).
PLANS = {
    "F": "2027-01-31: per-case outside checks for risk_f4 (QuantLib-free Kupiec and Christoffersen need a library "
         "backtest object or stay reimplementation), book_f, cdsidx_f (QuantLib IsdaCdsEngine), frtb_f* (no outside "
         "library exists: published as none); owner of record: spec and oracle lane, stage J close-out (J-10)",
    "G": "2027-01-31: per-case register for G (regenerated in oracle-coverage.yml); QuantLib FD and tree for "
         "bermudan_g and callable_g at a tolerance fixed before the run; stage J close-out (J-10)",
    "I": "2027-01-31: per-case register for I; outside checks for hedgeint_i (none exists: stays none), "
         "hedgebt_i through a library cash-account object if one exists; stage J close-out (J-10)",
}


def is_sweep(stage, suite):
    return (stage == "F" and suite.startswith("e1_")) or (stage == "I" and suite.endswith("5_i"))


def golden_suites(stage):
    out = {}
    for d in STAGE_DIRS[stage]:
        for f in sorted((GOLDEN / d).glob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            cases = doc["cases"] if isinstance(doc, dict) else doc
            out[f.stem] = [(c["case_id"], c.get("operation", "?"), c.get("expected", {}).get("status", "?")) for c in cases]
    return out


def classify_case_register(entries, partly):
    """{case_id: (class, library)} from a per-case register."""
    out = {}
    for e in entries:
        rows = set(e.get("convention_rows", []))
        lib = e.get("library") or "none"
        if e["case_id"] in partly:
            cls = "none"
        elif e.get("library") is None:
            cls, lib = "none", e.get("source", "published example")
        elif rows & REIMPL_ROWS:
            cls, lib = "reimplementation", "scipy (" + ", ".join(sorted(rows & REIMPL_ROWS)) + ")"
        elif rows & PRIMITIVE_ROWS:
            prim = sorted(rows & PRIMITIVE_ROWS)
            cls = "library-primitive"
            lib = ("numpy" if all(p.startswith("NUMPY") for p in prim) else "scipy") + " (" + ", ".join(prim) + ")"
        else:
            cls = "library-object"
            lib = f"{lib} {e.get('version', '')}".strip()
        out[e["case_id"]] = (cls, lib)
    return out


def load_case_registers(stage):
    names = {"D": ["outside_register.json"], "E": ["outside_register_e_a.json", "outside_register_e_b.json"],
             "F": ["outside_register_f.json"]}[stage]
    out = {}
    for n in names:
        doc = json.loads((ORACLE / n).read_text(encoding="utf-8"))
        out.update(classify_case_register(doc["cases"], {p if isinstance(p, str) else p["case_id"] for p in doc.get("partly_outside_not_counted", [])}))
    return out


def load_suite_register(stage):
    doc = json.loads((ORACLE / f"outside_register_{stage.lower()}.json").read_text(encoding="utf-8"))
    out = {}
    if stage == "G":
        out["shortrate_g"] = {"counted": doc["counted"], "total": doc["total"]}
    for k, v in doc.items():
        if isinstance(v, dict) and "counted" in v and not k.startswith("_"):
            out[k] = v
    return out


def stage_report(stage, problems):
    suites = golden_suites(stage)
    rows = []  # (suite, operation, class, sweep, library)
    if stage in ("D", "E", "F"):
        reg = load_case_registers(stage)
        known = {cid for s in suites.values() for cid, _, _ in s}
        for cid in sorted(set(reg) - known):
            problems.append(f"stage {stage}: register case {cid} is not in the goldens")
        for suite, cases in suites.items():
            for cid, op, _ in cases:
                cls, lib = reg.get(cid, ("none", ""))
                rows.append((suite, op, cls, is_sweep(stage, suite), lib))
    else:
        reg = load_suite_register(stage)
        merged = defaultdict(lambda: [0, 0])
        for k, v in reg.items():
            base = k.replace("_r5", "_g")
            merged[base][0] += v["counted"]
            merged[base][1] += v["total"]
            if v["counted"] and k not in SUITE_CLASS:
                problems.append(f"stage {stage}: register suite {k} has counted cases but no ruling in SUITE_CLASS")
        for suite, cases in suites.items():
            counted, total = merged.get(suite, (0, 0))
            if suite in merged and total != len(cases):
                problems.append(f"stage {stage}: register says {suite} has {total} cases, the golden has {len(cases)}")
            if suite not in merged:
                problems.append(f"stage {stage}: golden suite {suite} is missing from the register")
            cls, lib = SUITE_CLASS.get(suite, ("none", ""))
            for i, (cid, op, _) in enumerate(cases):
                rows.append((suite, op, cls if i < counted else "none", is_sweep(stage, suite), lib if i < counted else ""))
    return rows


def share(rows):
    n = len(rows)
    c = Counter(r[2] for r in rows)
    k = sum(c[x] for x in COUNTED)
    return {"cases": n, **{x: c[x] for x in CLASSES}, "counted": k, "share": round(k / n, 4) if n else None}


def build(problems):
    out = {"rule": "R6-13 (D6): library-object + library-primitive over every case of the stage, error cases included",
           "floor": FLOOR, "stages": {}}
    for st in STAGE_DIRS:
        rows = stage_report(st, problems)
        core = [r for r in rows if not r[3]]
        ops = defaultdict(list)
        for r in core:
            ops[r[1]].append(r)
        libs = Counter(r[4] for r in rows if r[2] in COUNTED)
        entry = {"without_sweeps": share(core), "with_sweeps": share(rows),
                 "sweeps": share([r for r in rows if r[3]]) if any(r[3] for r in rows) else None,
                 "libraries": dict(sorted(libs.items())),
                 "per_operation": {op: share(rs) for op, rs in sorted(ops.items())}}
        s = entry["without_sweeps"]["share"] or 0.0
        entry["meets_floor"] = s >= FLOOR
        if not entry["meets_floor"]:
            entry["plan"] = PLANS.get(st)
            if not entry["plan"]:
                problems.append(f"stage {st}: {s:.1%} is under the {FLOOR:.0%} floor and has no dated plan")
        out["stages"][st] = entry
    return out


def markdown(doc):
    L = ["# Outside-check shares (R6-13, decision D6)", "",
         "Generated by `tools/outside_shares.py`; do not edit. A case counts only as `library-object` or "
         "`library-primitive`, and only if every compared output is checked. Denominator: every case of the stage, "
         "error cases included. Generated sweeps (F `e1_*`, I `*5_i`) are shown separately; the floor applies without them.", "",
         "| Stage | Cases (no sweeps) | library-object | library-primitive | reimplementation | none | Share | With sweeps | Floor 60% |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for st, e in doc["stages"].items():
        w, a = e["without_sweeps"], e["with_sweeps"]
        L.append(f"| {st} | {w['cases']} | {w['library-object']} | {w['library-primitive']} | {w['reimplementation']} | "
                 f"{w['none']} | {w['share']:.1%} | {a['share']:.1%} ({a['counted']} of {a['cases']}) | "
                 f"{'met' if e['meets_floor'] else 'not met'} |")
    L.append("")
    for st, e in doc["stages"].items():
        if e.get("plan"):
            L.append(f"- Stage {st} plan: {e['plan']}")
    for st, e in doc["stages"].items():
        L += ["", f"## Stage {st} per operation (no sweeps)", "", "| Operation | Cases | Counted | Share |", "|---|---:|---:|---:|"]
        L += [f"| `{op}` | {s['cases']} | {s['counted']} | {s['share']:.0%} |" for op, s in e["per_operation"].items()]
        L += ["", "Libraries (counted cases, sweeps included): " + "; ".join(f"{k} {v}" for k, v in e["libraries"].items())]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    problems = []
    doc = build(problems)
    js = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    md = markdown(doc)
    jp, mp = ORACLE / "OUTSIDE_SHARES.json", ORACLE / "OUTSIDE_SHARES.md"
    if a.check:
        for p, text in ((jp, js), (mp, md)):
            if not p.is_file() or p.read_text(encoding="utf-8") != text:
                problems.append(f"{p.relative_to(ROOT).as_posix()} differs from a fresh run; run tools/outside_shares.py and commit")
    else:
        jp.write_text(js, encoding="utf-8", newline="\n")
        mp.write_text(md, encoding="utf-8", newline="\n")
    for st, e in doc["stages"].items():
        w = e["without_sweeps"]
        print(f"stage {st}: {w['counted']} of {w['cases']} = {w['share']:.1%} (with sweeps {e['with_sweeps']['share']:.1%})"
              f"{'' if e['meets_floor'] else ' UNDER FLOOR'}")
    for p in problems:
        print("error:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
