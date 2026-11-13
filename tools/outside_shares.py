#!/usr/bin/env python3
"""Outside-check shares under the R6-13 rule (owner decision D6, review finding 6). Standard library only.

    python tools/outside_shares.py            write oracle/OUTSIDE_SHARES.json and oracle/OUTSIDE_SHARES.md
    python tools/outside_shares.py --check    regenerate in memory; exit 1 if the committed copy differs, if a
                                              register's suite totals differ from the goldens, or if a stage is
                                              under the 60% floor on value-checked cases

Evidence classes (D6). A case counts towards the outside share only as `library-object` or `library-primitive`,
and only if every compared output of the case is checked:
  library-object     a library's own pricing or estimation object (QuantLib engine, ORE simulation, arch model)
  library-primitive  numpy or scipy numerics applied to a different formulation of the same problem
  reimplementation   the spec formula written again around a library call (does not count)
  none               no outside check, or a published worked example only (does not count)

Floor (owner, 2026-11-12, second decision): measured on VALUE-CHECKED cases only (`expected.status` "ok"). Error
and invariance cases (`error`, `any`, `same_as`) are a separate evidence class and leave the denominator. The old
all-case figure (ruling I-2, error cases in the denominator) is reported beside it. There is no dated-plan fallback:
a stage under 60% fails. Generated sweeps (stage F `e1_*` edge suites, stage I wave 5 seeded variants `*5_i`) are
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
REDERIVED = "independent-rederivation"
CLASSES = COUNTED + (REDERIVED, "reimplementation", "none")

# Owner decision 2026-11-12 (plan R6-13): `independent-rederivation` (a different model, blind to the goldens,
# judged at each golden's own tolerance by oracle/python/compare_rederivation.py, which writes
# oracle/REDERIVATION_REGISTER.json) counts toward the floor ONLY for the four value classes with no free outside
# library. A re-derivation entry for any other operation is reported as a problem and not counted.
REDERIVE_OPS = ("credit.cdsindex.option_price", "risk.frtb.", "book.lifecycle.apply", "book.marks.resolve",
                "risk.backtest.traffic_light")


def rederive_allowed(op):
    return any(op == p or (p.endswith(".") and op.startswith(p)) for p in REDERIVE_OPS)


def load_rederivation():
    p = ORACLE / "REDERIVATION_REGISTER.json"
    if not p.is_file():
        return {}, ""
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {c["case_id"]: c["operation"] for c in doc["cases"] if c["pass"]}, doc.get("source", "independent re-derivation")

STAGE_DIRS = {"D": ["stage_d"], "E": ["stage_e", "stage_e_b"], "F": ["stage_f"], "G": ["stage_g"], "I": ["stage_i"]}

# Stage F convention rows naming a numpy or scipy primitive. Kupiec (SCIPY.BINOM) and Christoffersen (SCIPY.CHI2)
# cases rebuild the spec's likelihood-ratio formula around a distribution call: reimplementation (review finding 6).
# SCIPY.MLE (R6 oracle lane 2): Kupiec and Christoffersen likelihoods maximised numerically, not the closed form.
PRIMITIVE_ROWS = {"SCIPY.QUAD", "SCIPY.EIGH", "NUMPY.QUANTILE", "SCIPY.NORM", "SCIPY.LSTSQ", "SCIPY.MLE", "SCIPY.TOEPLITZ", "SCIPY.BRENTQ"}
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

# Value classes with no free outside reference (owner 2026-11-12): named with the reason. They stay in the
# denominator; the list explains a gap, it does not excuse it.
NO_REFERENCE = {
    "hedgeint_i": "integer lots: no free library solves integer least squares with these constraints; exact rational enumeration is the oracle",
    "hedgebeta_i": "beta futures hedge: arithmetic on given betas; no library object computes it (Hull's worked example is a textbook check)",
    "hedgeres_i": "residual risk report: arithmetic on the hedge solve's own outputs; no library object",
    "hedgeslip_i": "implementation shortfall: no free library computes it; exact rational arithmetic",
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


# Stage G suites with a per-case outside register (oracle/OUTSIDE_G_R6.json, written by oracle/python/outside_g_r6.py;
# R6 oracle lane 2). A case counts only if every compared output passed its stated tolerance.
PERCASE_G_CLASS = {"bermudan_g": "library-object", "aadladder_g": "library-object", "callable_g": "library-object",
                   "hwcal_g": "library-primitive", "barrier_g": "library-object"}


def load_percase_g():
    p = ORACLE / "OUTSIDE_G_R6.json"
    if not p.is_file():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {s: (PERCASE_G_CLASS[s], v["library"], {c["case_id"] for c in v["cases"] if c["pass"] and all(x["pass"] for x in c["checks"])})
            for s, v in doc["suites"].items() if s in PERCASE_G_CLASS}


def stage_report(stage, problems):
    """Rows (suite, operation, class, sweep, library, value-checked)."""
    suites = golden_suites(stage)
    rows = []  # (suite, operation, class, sweep, library)
    if stage in ("D", "E", "F"):
        reg = load_case_registers(stage)
        known = {cid for s in suites.values() for cid, _, _ in s}
        for cid in sorted(set(reg) - known):
            problems.append(f"stage {stage}: register case {cid} is not in the goldens")
        red, red_src = load_rederivation() if stage == "F" else ({}, "")
        for cid in sorted(set(red) - known):
            problems.append(f"stage {stage}: re-derivation case {cid} is not in the goldens")
        for suite, cases in suites.items():
            for cid, op, st in cases:
                cls, lib = reg.get(cid, ("none", ""))
                if cid in red and not rederive_allowed(op):
                    problems.append(f"stage {stage}: re-derivation for {cid} ({op}) is outside the four allowed classes")
                elif cid in red and cls not in COUNTED:
                    cls, lib = REDERIVED, red_src
                rows.append((suite, op, cls, is_sweep(stage, suite), lib, st == "ok"))
    else:
        reg = load_suite_register(stage)
        merged = defaultdict(lambda: [0, 0])
        for k, v in reg.items():
            base = k.replace("_r5", "_g")
            merged[base][0] += v["counted"]
            merged[base][1] += v["total"]
            if v["counted"] and k not in SUITE_CLASS:
                problems.append(f"stage {stage}: register suite {k} has counted cases but no ruling in SUITE_CLASS")
        percase = load_percase_g() if stage == "G" else {}
        for suite, cases in suites.items():
            if suite in percase:
                cls0, lib0, passed = percase[suite]
                for cid, op, st in cases:
                    ok = cid in passed
                    rows.append((suite, op, cls0 if ok else "none", is_sweep(stage, suite), lib0 if ok else "", st == "ok"))
                continue
            counted, total = merged.get(suite, (0, 0))
            if suite in merged and total != len(cases):
                problems.append(f"stage {stage}: register says {suite} has {total} cases, the golden has {len(cases)}")
            if suite not in merged:
                problems.append(f"stage {stage}: golden suite {suite} is missing from the register")
            cls, lib = SUITE_CLASS.get(suite, ("none", ""))
            # Suite counts carry no case ids: outside checks compare values, so they are assigned to value cases first.
            order = sorted(cases, key=lambda c: c[2] != "ok")
            for i, (cid, op, st) in enumerate(order):
                rows.append((suite, op, cls if i < counted else "none", is_sweep(stage, suite), lib if i < counted else "", st == "ok"))
    return rows


def vshare(rows):
    """Value-checked share (the floor measure) with the old all-case share beside it."""
    v = share([r for r in rows if r[5]])
    v["all_cases_share"] = share(rows)["share"]
    v["error_and_invariance_cases"] = sum(1 for r in rows if not r[5])
    return v


def share(rows):
    n = len(rows)
    c = Counter(r[2] for r in rows)
    k = sum(c[x] for x in COUNTED)
    kr = k + c[REDERIVED]
    return {"cases": n, **{x: c[x] for x in CLASSES}, "counted": k, "share": round(k / n, 4) if n else None,
            "rederived_book_spec_only": sum(1 for r in rows if r[2] == REDERIVED and r[1].startswith("book.")),
            "counted_with_rederivation": kr, "share_with_rederivation": round(kr / n, 4) if n else None}


def build(problems):
    out = {"rule": "R6-13 (D6, owner 2026-11-12): library-object + library-primitive over the stage's value-checked cases; old all-case share beside it",
           "floor": FLOOR, "stages": {}}
    for st in STAGE_DIRS:
        rows = stage_report(st, problems)
        core = [r for r in rows if not r[3]]
        ops = defaultdict(list)
        for r in core:
            ops[r[1]].append(r)
        libs = Counter(r[4] for r in rows if r[2] in COUNTED)
        entry = {"without_sweeps": vshare(core), "with_sweeps": vshare(rows),
                 "sweeps": vshare([r for r in rows if r[3]]) if any(r[3] for r in rows) else None,
                 "libraries": dict(sorted(libs.items())),
                 "no_outside_reference": {k: v for k, v in NO_REFERENCE.items() if any(r[0] == k for r in rows)},
                 "per_operation": {op: vshare(rs) for op, rs in sorted(ops.items())}}
        s = entry["without_sweeps"]["share_with_rederivation"] or 0.0
        entry["meets_floor"] = s >= FLOOR
        if not entry["meets_floor"]:
            problems.append(f"stage {st}: {s:.1%} of value-checked cases (library plus re-derivation) is under the {FLOOR:.0%} floor")
        out["stages"][st] = entry
    return out


def markdown(doc):
    L = ["# Outside-check shares (R6-13, decision D6, owner 2026-11-12)", "",
         "Generated by `tools/outside_shares.py`; do not edit. A case counts only as `library-object` or "
         "`library-primitive`, and only if every compared output is checked. **Floor: 60% of the stage's value-checked "
         "cases.** Error and invariance cases are a separate evidence class, outside the denominator; the old all-case "
         "share is shown beside the new one. Generated sweeps (F `e1_*`, I `*5_i`) are shown separately; the floor applies without them.", "",
         "| Stage | Value cases (no sweeps) | library-object | library-primitive | independent-rederivation | reimplementation | none | Library-only share | Library plus re-derivation (floor) | Old all-case share | With sweeps (value) | Error and invariance cases | Floor 60% |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for st, e in doc["stages"].items():
        w, a = e["without_sweeps"], e["with_sweeps"]
        L.append(f"| {st} | {w['cases']} | {w['library-object']} | {w['library-primitive']} | {w[REDERIVED]} | {w['reimplementation']} | "
                 f"{w['none']} | {w['share']:.1%} | {w['share_with_rederivation']:.1%} | {w['all_cases_share']:.1%} | {a['share']:.1%} ({a['counted']} of {a['cases']}) | "
                 f"{w['error_and_invariance_cases']} | {'met' if e['meets_floor'] else 'NOT MET'} |")
    wf = doc["stages"]["F"]["without_sweeps"]
    L += ["", f"Stage F re-derivation sub-count: {wf[REDERIVED]} cases, of which {wf['rederived_book_spec_only']} are spec-only book lifecycle and marks "
          "(no source outside the spec, so the re-derivation checks the spec against itself; shown separately for that reason). "
          f"Library plus re-derivation without them: {(wf['counted_with_rederivation'] - wf['rederived_book_spec_only'])} of {wf['cases']} = "
          f"{(wf['counted_with_rederivation'] - wf['rederived_book_spec_only']) / wf['cases']:.1%}."]
    L += ["", "## Value classes with no free outside reference", "", "| Suite | Reason |", "|---|---|"]
    for e in doc["stages"].values():
        L += [f"| `{k}` | {v} |" for k, v in e["no_outside_reference"].items()]
    for st, e in doc["stages"].items():
        L += ["", f"## Stage {st} per operation (no sweeps)", "", "| Operation | Value cases | Library | Library share | Plus re-derivation | Old all-case share |", "|---|---:|---:|---:|---:|---:|"]
        L += [f"| `{op}` | {s['cases']} | {s['counted']} | {(s['share'] or 0):.0%} | {(s['share_with_rederivation'] or 0):.0%} | {(s['all_cases_share'] or 0):.0%} |" for op, s in e["per_operation"].items()]
        L += ["", "Libraries (counted cases, sweeps included): " + "; ".join(f"{k} {v}" for k, v in e["libraries"].items())]
    return chr(10).join(L) + chr(10)


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
        print(f"stage {st}: value {w['counted']} of {w['cases']} = {w['share']:.1%}, old all-case {w['all_cases_share']:.1%}, with sweeps {e['with_sweeps']['share']:.1%}"
              f"{'' if e['meets_floor'] else ' UNDER FLOOR'}")
    for p in problems:
        print("error:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
