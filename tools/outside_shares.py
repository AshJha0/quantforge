#!/usr/bin/env python3
"""Outside-check shares under the R6-13 rule (owner decision D6, review finding 6). Standard library only.

    python tools/outside_shares.py            write oracle/OUTSIDE_SHARES.json and oracle/OUTSIDE_SHARES.md
    python tools/outside_shares.py --check    regenerate in memory; exit 1 if the committed copy differs, if a
                                              register's suite totals differ from the goldens, or if a stage is
                                              under the 60% floor on value-checked cases, if a stage H or K
                                              plan item is under the 60% per-item floor (audit KF-19, no
                                              exemption list), or if a generated stage K block in the docs
                                              differs (audit KF-18; the blocks are rewritten without --check)

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
import re
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

STAGE_DIRS = {"D": ["stage_d"], "E": ["stage_e", "stage_e_b"], "F": ["stage_f"], "G": ["stage_g"], "I": ["stage_i"], "J": ["stage_j"], "H": ["stage_h"], "K": ["stage_k"]}

# Stage F convention rows naming a numpy or scipy primitive. Kupiec (SCIPY.BINOM) and Christoffersen (SCIPY.CHI2)
# cases rebuild the spec's likelihood-ratio formula around a distribution call: reimplementation (review finding 6).
# SCIPY.MLE (R6 oracle lane 2): Kupiec and Christoffersen likelihoods maximised numerically, not the closed form.
PRIMITIVE_ROWS = {"SCIPY.QUAD", "SCIPY.EIGH", "NUMPY.QUANTILE", "SCIPY.NORM", "SCIPY.LSTSQ", "SCIPY.MLE", "SCIPY.TOEPLITZ", "SCIPY.BRENTQ"}
REIMPL_ROWS = {"SCIPY.BINOM", "SCIPY.CHI2"}

# Suite-level rulings for registers that hold counts only (stage G, stage I). Reviewed 2026-11-12 by the R6
# evidence lane against each register's own rule text; no second review (owner decision, 2026-11-18).
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
        elif e.get("evidence_class") == "reimplementation":  # set by the register's generator (H-19 honesty pass)
            cls, lib = "reimplementation", f"{lib} {e.get('version', '')}".strip() + " plus spec arithmetic"
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


def load_percase_j():
    """{case_id: (class, library)} for stage J from oracle/OUTSIDE_J.json (oracle/python/outside_j.py; ruling J-19a).

    Each case carries its own class; a case counts only if it and every compared output passed."""
    p = ORACLE / "OUTSIDE_J.json"
    if not p.is_file():
        return {}
    doc = json.loads(p.read_text(encoding="utf-8"))
    return {c["case_id"]: (c["class"], v["library"]) for v in doc["suites"].values() for c in v["cases"]
            if c["pass"] and all(x["pass"] for x in c["checks"]) and c.get("class") in COUNTED}


# Stage H (plan 15 gate rule, decision DR-H2 of 2026-11-15): no free library implements Almgren-Chriss,
# Avellaneda-Stoikov, Perold shortfall or the impact formulas, so the stage H outside check is a blind
# re-derivation by a second lane that never saw the first lane's numbers (STAGE_H_BLIND_REDERIVATION.md), or a
# figure printed in the paper. It is the `independent-rederivation` class and is shown apart from library checks.
# A case counts only if its `verified_by` records the DR-H2 MATCH and does not say any output was not blind.
# Plan 15 applies the 60% floor per item: STAGE_H_ITEMS maps each golden suite to its plan item.
STAGE_H_ITEMS = {"sched_h": "H-3a", "ac_h": "H-3b", "tca_h": "H-3c", "imp_h": "H-15a", "as_h": "H-4a", "uc5_h": "H-6",
                 "ob_h": "H-2", "lit_h": "H-11", "dark_h": "H-12", "sor_h": "H-13",
                 "mest_h": "H-4b", "venue_h": "H-16", "pt_h": "H-21", "alg_h": "H-14", "tcx_h": "H-17",
                 "e1_h": None, "e1_h2": None, "e1_h3": None, "enum_h": None, "e1_hpt": None,  # E1 non-finite-input error cases only: no value cases, so no item share
                 "sorx_h": None,
                 "eqc_h": "H-22", "auc_h": "H-22", "fxc_h": "H-23", "fxv_h": "H-23", "rtc_h": "H-24",
                 "fut_h": "H-24", "ses_h": "H-22", "e1_h4": None,
                 "rule_h": None,  # audit rulings HR-121..HR-129: cross-item cases, most of them error cases
                 "acls_h": None}  # acls_h: asset-class routing, cross-item hand cases only  # cross-build agreement cases (Python build output), not outside-checked: no item
H_REDERIVE_SRC = "blind second-lane re-derivation or printed paper figure (DR-H2)"


def load_stage_h():
    out = {}
    for f in sorted((GOLDEN / "stage_h").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        for c in (doc["cases"] if isinstance(doc, dict) else doc):
            vb = " | ".join(c.get("verified_by", []))
            if "DR-H2" in vb and "MATCH" in vb and "not blind" not in vb:
                out[c["case_id"]] = (REDERIVED, H_REDERIVE_SRC)
    return out


# Stage K wave 1 (ruling KR-11, confirmed 2026-11-19): the only library check is SciPy on trig_k
# `false_alarm_rate`, one of four compared outputs, so no case counts as library-checked. Counted, as for stage H,
# is the DR-H2 blind re-derivation (program/STAGE_K_BLIND_W1.md), and only where every compared output was checked
# blind at the golden's tolerance: a case whose `verified_by` says "not blind" (gap-decided fields, oracle-only
# cases) or "only to 6 decimals" (idr_k-0001..0004 `bound`, compared at 1e-9 relative but blind-checked to 5e-7
# absolute) does not count. The mpmath values are our own oracle and never count (KR-11).
# Stage K wave 1b: a printed regulator figure ("published: ... MATCH", CRE99 and MAR99 Table 2) does NOT count on its own
# (ruling KR-250, audit KA-C18, program/STAGE_K_AUDIT_C18_RESPONSE.md). The integration of 2026-11-19 had counted it,
# citing stage H; but stage H never counts a printed figure alone (as_h-0005..0007 and ac_h-0005 count through their
# DR-H2 blind MATCH, the printed figure is an "extra check"; ob_h-0001's printed checksum is not counted), stage F
# classes the Cboe VIX worked example `none` (vix_f-0001..0003), and the D6 docstring above says a published worked
# example alone does not count. A printed figure checks some outputs at print precision, not every compared output
# at the golden's tolerance. `--count-printed` prints the shares under the withdrawn reading, for comparison only. SciPy `binom.cdf` checks on btk_k are not counted: the D6 precedent is stage F's
# REIMPL_ROWS ("SCIPY.BINOM"), under which risk_f4-0082 (`risk.backtest.traffic_light`, the same binomial sum) is
# `reimplementation`; a library primitive computing the same closed-form quantity is not a different formulation.
# K-5a: KR-234 redefined `bound`, so the version 1 packet (program/STAGE_K_BLIND_K5A.md) no longer covers it. The
# version 2 packet (program/STAGE_K_BLIND_K5A_V2.md, 2026-11-19) re-derived 11 cases at 1e-9 relative: 9 MATCH,
# counted; idr_k-0012 and idr_k-0013 MISMATCH on estimate_pnl and are NOT counted.
# trig_k: KR-232 redefined `false_alarm_rate`, so the wave-1 blind MATCH no longer covers every compared output and
# trig_k lost its blind credit (verified_by says "not blind"); the SciPy checks do not count (KR-11).
# K-4c version 2 packet (program/STAGE_K_BLIND_TRIG_V2.md, 2026-11-20): 14 of 14 MATCH, 13 counted (trig_k-0004's
# fire stays gap-decided by KR-13).
# The 28 printed-figure cases count through the blind pub packet (program/STAGE_K_BLIND_PUB.md, 28 of 28 MATCH at
# full tolerance), not through the printed figure (KR-250).
STAGE_K_ITEMS = {"bt_k": "K-4a", "inc_k": "K-4b", "trig_k": "K-4c", "idr_k": "K-5a", "rich_k": "K-8 guard",
                 "k8_k": "K-8", "e1_k": None, "e2_k": None,  # e1_k, e2_k: error cases only
                 "saccr_k": "K-8d", "btk_k": "K-8e", "tlk_k": "F (existing traffic_light)",
                 "sbim_alias_k": None,  # KR-153: the deprecated alias's invariance and error cases; no value case
                 "lim_k": None,  # KR-230/KR-231: size-limit error cases only (bitemporal_query, trigger.check)
                 "fuzzfix_k": None,  # fuzz run 44815591552 and siblings: error cases only (gen_stage_k_fuzz.py)
                 "drc_k": "K-8a", "ima_k": "K-8f", "cva_k": "K-8g", "sacva_k": "K-8g", "df_k": "K-8g",
                 "lev_k": "K-8i", "lex_k": "K-8i",
                 "cva_ke": None, "sacva_ke": None, "lev_ke": None, "lex_ke": None}  # wave 2 _ke: error cases only
K_PUBLISHED_SRC = "figure printed in the regulator text (Basel Framework CRE99, MAR99 Table 2)"


COUNT_PRINTED = False  # reporting switch for --count-printed only; never written to the committed files


def load_stage_k():
    out = {}
    for f in sorted((GOLDEN / "stage_k").glob("*.json")):
        for c in json.loads(f.read_text(encoding="utf-8"))["cases"]:
            vb = " | ".join(c.get("verified_by", []))
            if "DR-H2" in vb and "MATCH" in vb and "not blind" not in vb and "only to 6 decimals" not in vb:
                out[c["case_id"]] = (REDERIVED, H_REDERIVE_SRC)
            elif COUNT_PRINTED and any(v.startswith("published:") and "MATCH" in v for v in c.get("verified_by", [])):
                out[c["case_id"]] = (REDERIVED, K_PUBLISHED_SRC)
    return out


def stage_report(stage, problems):
    """Rows (suite, operation, class, sweep, library, value-checked)."""
    suites = golden_suites(stage)
    rows = []  # (suite, operation, class, sweep, library)
    if stage in ("H", "K"):
        reg, items = (load_stage_h(), STAGE_H_ITEMS) if stage == "H" else (load_stage_k(), STAGE_K_ITEMS)
        for suite, cases in suites.items():
            if suite not in items:
                problems.append(f"stage {stage}: golden suite {suite} has no plan item in STAGE_{stage}_ITEMS")
            for cid, op, st in cases:
                cls, lib = reg.get(cid, ("none", ""))
                rows.append((suite, op, cls, False, lib, st == "ok"))
        return rows
    if stage == "J":
        reg = load_percase_j()
        known = {cid for s in suites.values() for cid, _, _ in s}
        for cid in sorted(set(reg) - known):
            problems.append(f"stage J: outside case {cid} is not in the goldens")
        for suite, cases in suites.items():
            for cid, op, st in cases:
                cls, lib = reg.get(cid, ("none", ""))
                rows.append((suite, op, cls, is_sweep(stage, suite), lib, st == "ok"))
        return rows
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
    return {"cases": n, **{x: c[x] for x in CLASSES}, "counted": k, "share": round(k / n, 6) if n else None,
            "rederived_book_spec_only": sum(1 for r in rows if r[2] == REDERIVED and r[1].startswith("book.")),
            "counted_with_rederivation": kr, "share_with_rederivation": round(kr / n, 6) if n else None}


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
        if st in ("H", "K"):
            item_map = STAGE_H_ITEMS if st == "H" else STAGE_K_ITEMS
            items = defaultdict(list)
            for r in core:
                if item_map.get(r[0], "?") is not None:
                    items[item_map.get(r[0], "?")].append(r)
            entry["per_item"] = {}
            for it, rs in sorted(items.items()):
                v = vshare(rs)
                v["suites"] = sorted({r[0] for r in rs})
                v["meets_item_floor"] = (v["share_with_rederivation"] or 0.0) >= FLOOR
                entry["per_item"][it] = v
                # Audit KF-19 (2026-11-20): the plan 15 per-item rule is a gate, not a column. No exemption list.
                if not v["meets_item_floor"]:
                    problems.append(f"stage {st}: item {it} ({', '.join(v['suites'])}) is {v['counted_with_rederivation']} of "
                                    f"{v['cases']} ({(v['share_with_rederivation'] or 0):.1%}), under the {FLOOR:.0%} per-item floor")
            if st == "K":
                # Audit finding KA-C18 (2026-11-19, open): cases counted on a figure printed in the regulator text are
                # checked on part of their outputs and at print precision, so by the strict reading of the rule above
                # ("only if every compared output is checked") they do not count. Ruled by KR-250: the strict reading is the count.
                def strict(rs):
                    val = [r for r in rs if r[5]]
                    return {"cases": len(val), "counted": sum(r[2] == REDERIVED and r[4] != K_PUBLISHED_SRC for r in val)}
                # Ruling KR-250 made the strict reading the count. The note is emitted only if the two counts differ
                # again (for example if a printed-figure case regains credit), so the page never prints a stale review.
                st_counts = strict(core)
                if st_counts["counted"] != entry["without_sweeps"]["counted_with_rederivation"]:
                    entry["under_review"] = {
                        "finding": "KA-C18", "status": "reopened: the strict count differs from the count",
                        "strict_reading": "a case counted on a printed regulator figure does not count",
                        "stage": st_counts,
                        "per_item": {it: strict(rs) for it, rs in sorted(items.items())}}
        out["stages"][st] = entry
    return out


def under_review_text(u):
    s = u["stage"]
    low = [f"{it} {v['counted']} of {v['cases']} ({v['counted'] / v['cases']:.1%})" for it, v in u["per_item"].items()
           if v["cases"] and v["counted"] / v["cases"] < FLOOR]
    return (f"**Stage K shares are under review (audit finding {u['finding']}, {u['status']}; `docs/known-issues.md`).** The table above "
            "counts a case checked against a figure printed in the regulator text. Such a case is checked on part of its "
            "outputs and at print precision, which the rule at the top of this page (\"only if every compared output is "
            f"checked\") does not allow. By the strict reading stage K is {s['counted']} of {s['cases']} "
            f"({s['counted'] / s['cases']:.1%}); items under the floor by that reading: {'; '.join(low) or 'none'}. "
            "Neither figure is settled until a ruling says which reading holds.")


# Audit KF-18 (2026-11-20): the stage K figures that docs quote are generated into marked blocks,
#   <!-- generated:NAME -->TEXT<!-- /generated -->
# on one line, so a block can sit inside a sentence or a table cell. `--check` compares every block byte for byte.
BLOCK = re.compile(r"<!-- generated:(stage-k-[a-z-]+) -->(.*?)<!-- /generated -->")
# Docs that state stage K or per-item shares must carry the blocks (a doc may hold more than one copy).
BLOCK_DOCS = {"README.md": ("stage-k-total", "stage-k-items"), "LEARN.md": ("stage-k-total", "stage-k-items"), "CHANGELOG.md": ("stage-k-total",), "ROADMAP.md": ("stage-k-total", "stage-k-items"), "docs/known-issues.md": ("stage-k-total",),
              "docs/releases/v0.10.1.md": ("stage-k-total", "stage-k-items")}
ITEM_NAME = {"K-8": "K-8 method", "K-8d": "K-8d SA-CCR", "K-8e": "K-8e FRTB backtesting"}


def item_label(it, v):
    if it.startswith("K-"):
        return ITEM_NAME.get(it, it)
    return " ".join(f"`{x}`" for x in v["suites"])  # an item outside the K numbering, named by its suite


def doc_blocks(doc):
    k = doc["stages"]["K"]
    w = k["without_sweeps"]
    parts, low = [], []
    for it, v in sorted(k["per_item"].items(), key=lambda kv: (not kv[0].startswith("K-"), kv[0])):
        mark = "" if v["meets_item_floor"] else ", NOT MET"
        parts.append(f"{item_label(it, v)} {v['counted_with_rederivation']} of {v['cases']} "
                     f"({(v['share_with_rederivation'] or 0):.1%}{mark})")
        if not v["meets_item_floor"]:
            low.append(item_label(it, v) + ("" if it.startswith("K-") else " (the existing stage F traffic light)"))
    floor = ("every item meets the 60% per-item rule" if not low else
             "the 60% per-item rule is NOT MET by " + ", ".join(low) + ", recorded as a miss (`oracle/OUTSIDE_SHARES.md`)")
    return {"stage-k-total": f"{w['counted_with_rederivation']} of {w['cases']} value cases ({w['share_with_rederivation']:.1%})",
            "stage-k-items": ", ".join(parts) + "; " + floor}


def sync_blocks(blocks, write, problems):
    """Rewrite (or, with write False, compare) every generated block in the tracked Markdown files."""
    import subprocess
    files = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    seen = defaultdict(set)
    for rel in files:
        p = ROOT / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        if "<!-- generated:stage-k-" not in text:
            continue

        def sub(m, rel=rel):
            name = m.group(1)
            seen[rel].add(name)
            if name not in blocks:
                problems.append(f"{rel}: unknown generated block {name}")
                return m.group(0)
            if m.group(2) != blocks[name] and not write:
                problems.append(f"{rel}: generated block {name} differs from a fresh run; run tools/outside_shares.py and commit")
            return f"<!-- generated:{name} -->{blocks[name]}<!-- /generated -->"
        new = BLOCK.sub(sub, text)
        if write and new != text:
            p.write_text(new, encoding="utf-8", newline="\n")
    for rel, names in BLOCK_DOCS.items():
        for name in names:
            if name not in seen[rel]:
                problems.append(f"{rel}: has no generated block {name} (stage K shares must be quoted from the generator)")


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
    eh = doc["stages"].get("H")
    if eh:
        L += ["", "## Stage H per plan item (plan 15 gate rule: at least 60% of each item's value cases)", "",
              "Stage H has no free outside library (decision DR-H2): every counted case is `independent-rederivation`, a blind "
              "second-lane re-derivation or a figure printed in the paper, so the library-only share is 0%. Cases the blind lane "
              "did not see, or saw part of, do not count. An item under 60% moves to a point release unless it is re-derived blind first.", "",
              "| Item | Suites | Value cases | Blind or paper | Share | 60% per item |", "|---|---|---:|---:|---:|---|"]
        L += [f"| {it} | {', '.join('`' + s + '`' for s in v['suites'])} | {v['cases']} | {v['counted_with_rederivation']} | "
              f"{(v['share_with_rederivation'] or 0):.1%} | {'met' if v['meets_item_floor'] else 'NOT MET'} |" for it, v in eh["per_item"].items()]
    ek = doc["stages"].get("K")
    if ek:
        L += ["", "## Stage K per plan item (plan 15 gate rule: at least 60% of each item's value cases)", "",
              "Ruling KR-11: SciPy checks only trig_k `false_alarm_rate`, one of four compared outputs, so no case is "
              "library-checked. A case counts as `independent-rederivation` only if the wave-1 blind lane (DR-H2) checked "
              "every compared output at the golden's tolerance; gap-decided, oracle-only and 6-decimal bound cases do not count. "
              "A figure printed in the regulator text (CRE99 Examples 1 to 5, MAR99 Table 2) does not count on its own "
              "(ruling KR-250, audit KA-C18): it checks some outputs at print precision, not every compared output at the "
              "golden's tolerance; those 28 cases count through the blind packet that matched them 28 of 28 (program/STAGE_K_BLIND_PUB.md). "
              "Counted from wave 1b: the seven SA-CCR cases the wave-1b blind lane matched (program/STAGE_K_BLIND_W1B.md); SciPy binomial checks on "
              "btk_k are not counted. trig_k lost its wave-1 blind credit when KR-232 redefined false_alarm_rate (the SciPy check does not count); "
              "the K-4c version 2 packet re-derived its 14 value cases, 14 of 14 MATCH, 13 counted (trig_k-0004: fire gap-decided by KR-13; program/STAGE_K_BLIND_TRIG_V2.md). "
              "That K-4c credit checks a re-implementation of the stated algorithm (the packet gave the rule, the "
              "deriver wrote it again and matched): it shows the rule is unambiguous and the arithmetic right, not "
              "that the rule reads the source correctly (audit KF-7). "
              "Later blind packets, counted the same way: K-5a version 2, 9 of 11 (program/STAGE_K_BLIND_K5A_V2.md; "
              "idr_k-0012 and idr_k-0013 mismatched and are not counted), the K-8 ladder k8_k (program/STAGE_K_BLIND_K8.md) and eleven btk_k cases "
              "(program/STAGE_K_BLIND_BTK.md; btk_k-0017 matched and is not counted) and the KR-253 traffic-light goldens tlk_k-0012 to -0020 "
              "(program/STAGE_K_BLIND_TLK_V2.md; 9 of 9 matched, 6 counted: the three n = 1 cases tlk_k-0016 to -0018 have the answer in "
              "the rule text and are not counted; tlk_k-0021 was added later and has no blind re-derivation). The mpmath oracle is our own and never counts.", "",
              "| Item | Suites | Value cases | Blind | Share | 60% per item |", "|---|---|---:|---:|---:|---|"]
        L += [f"| {it} | {', '.join('`' + s + '`' for s in v['suites'])} | {v['cases']} | {v['counted_with_rederivation']} | "
              f"{(v['share_with_rederivation'] or 0):.1%} | {'met' if v['meets_item_floor'] else 'NOT MET'} |" for it, v in ek["per_item"].items()]
    if ek and ek.get("under_review"):
        L += ["", under_review_text(ek["under_review"])]
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
    ap.add_argument("--count-printed", action="store_true",
                    help="print stage K shares as if a printed regulator figure alone counted (withdrawn reading, KR-250); writes nothing")
    a = ap.parse_args(argv)
    global COUNT_PRINTED
    if a.count_printed:
        COUNT_PRINTED = True
        try:
            doc = build([])
        finally:
            COUNT_PRINTED = False
        ek = doc["stages"]["K"]
        w = ek["without_sweeps"]
        print(f"stage K (printed figure counted, withdrawn reading): {w['counted_with_rederivation']} of {w['cases']} = {w['share_with_rederivation']:.1%}")
        for it, v in ek["per_item"].items():
            print(f"  {it}: {v['counted_with_rederivation']} of {v['cases']} = {(v['share_with_rederivation'] or 0):.1%}")
        return 0
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
    sync_blocks(doc_blocks(doc), not a.check, problems)
    for st, e in doc["stages"].items():
        w = e["without_sweeps"]
        print(f"stage {st}: value {w['counted']} of {w['cases']} = {w['share']:.1%}, old all-case {w['all_cases_share']:.1%}, with sweeps {e['with_sweeps']['share']:.1%}"
              f"{'' if e['meets_floor'] else ' UNDER FLOOR'}")
    for p in problems:
        print("error:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
