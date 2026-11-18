#!/usr/bin/env python3
"""Write one evidence checklist per curve in the gallery curve table (docs/validation/<slug>.md).

Standard library only. Facts are read, not typed: the row and stage from docs/curves/README.md, the golden counts
and `verified_by` sources from docs/curves/data/<slug>.json (written by tools/build_gallery.py from the goldens), the
spec and rulings files from the curve page, the oracle paragraph from the page's "Oracle evidence and limits" section,
and the real-data result from docs/validation/data/real-data.json (tools/validation/reconcile_official.py). The only
hand-written text is NOTES below: the real-data status, open questions and the before figures of the pack.

    python tools/validation/build_checklists.py           write the pages
    python tools/validation/build_checklists.py --check   exit 1 if a committed page differs from a fresh build
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURVES = ROOT / "docs" / "curves"
OUT = ROOT / "docs" / "validation"
REAL = json.loads((OUT / "data" / "real-data.json").read_text(encoding="utf-8"))

NO_FREE = "No free data: the stage C/D data surveys (LEARN.md) found no free {what}. No reconciliation is possible without paid data, which the project does not buy."


def rd(key):
    e = REAL["curves"][key]
    tiers = ", ".join(f"{t}: {'pass' if ok else 'fail'}" for t, ok in e["tiers"].items())
    return (f"`{key}` ({e['source']}, as of {e['as_of']}, {len(e['tenors'])} tenors, par rates by {e['par_pricer']}): "
            f"**{'pass' if e['pass'] else 'FAIL'}** at the stated {REAL['tolerance_bp']} bp on all {e['pillars']} pillars ({tiers}). "
            f"Between pillars within 5 bp: {'yes' if e['between_pillars_within_5bp'] else 'no'} (information only).")


SOFR_RD = [rd("SOFR"), rd("SOFR-EVERY-YEAR"),
           "Method (derived): the GSW curve is a Treasury curve, not a SOFR curve, so this tests the bootstrap's mechanics on a real curve shape, not SOFR levels. "
           "The every-year set misses the 0.1 bp tier because no quote covers as_of to spot (2 business days): QuantForge interpolates that stub log-linearly from D(as_of) = 1, while the published curve has its own front-end shape. "
           "The standard set's residual comes from coupon dates between sparse pillars (7Y, 10Y, ...), where log-linear and Svensson differ."]
SONIA_RD = [rd("SONIA"), rd("SONIA-EVERY-YEAR"),
            "Method (derived): with a pillar every year SONIA's coupon dates sit on pillars (no spot or payment lag), and the round trip closes to rounding. The standard set's residual comes from coupon dates between sparse pillars. "
            "BoE values are Bank copyright for internal use, so only pass or fail is published (tools/workflows/boe_curves.py)."]

ESTR_RD = [rd("ESTR"), rd("ESTR-EVERY-YEAR"),
           "Method (derived): the ECB curve is the euro area AAA government curve (Svensson parameters, ECB Data Portal; reproduces the published 1Y and 10Y spot rates to 1e-10 %), not an ESTR curve, so this tests the bootstrap on a real curve shape, not ESTR levels. "
           "As for SOFR, the two-day stub from as_of to spot has no quote; with short tenors in the every-year set its effect lands on the 1M pillar, which is why that set is closer to the 0.5 bp tolerance than the standard set."]
NOTES = {
    "sonia-ois": {"real": SONIA_RD, "open": ["One of 18 cases (`rulings_b`) has replay only; confirm it needs no outside check."]},
    "sofr-ois": {"real": SOFR_RD, "open": ["No free SOFR swap quotes exist, so level checks against a SOFR market curve stay open."]},
    "usd-term-3m": {"real": [NO_FREE.format(what="term-rate swap or FRA quotes")],
                    "open": ["USD-TERM-3M is a synthetic index (no live USD term IBOR), so only the method can be tested.",
                             "One case (`rulings_b`) has replay only."]},
    "gbpusd-fx-forward": {"before": "0 of 11", "real": [NO_FREE.format(what="FX forward points")],
                          "open": ["QuantLib's `FxForward` uses the same spot-normalised forward as the spec (both cite covered interest parity); it is an outside implementation of the same formula, not an independent model."]},
    "equity-forward": {"before": "0 of 4", "real": [NO_FREE.format(what="dividend or borrow history")],
                       "open": ["**Settled by ruling C18 (owner, 2026-11-18)** (`equity_forward-0012`): the spec ignores a dividend with `ex_date <= as_of` (`specifications/02-curves/equity-forward.md`); QuantLib's `AnalyticDividendEuropeanEngine` counts one dated on the evaluation date. With that dividend removed, QuantLib agrees on all four outputs. The golden was not changed. Is the spec's rule (ex on as_of means already ex) the one the reviewer accepts?",
                                "`equity_forward-0014` (expiry on as_of) has no outside check: there is no option for the engine to price."]},
    "svi-smile": {"before": "1 of 2", "real": [NO_FREE.format(what="option quotes or vol surfaces")],
                  "open": ["`g` and `min_g` on the counterexample are checked by central differences on QuantLib's variance at 1e-6, not at the case's own tolerance; QuantLib has no Durrleman `g`."]},
    "ssvi-surface": {"before": "0 of 3", "real": [NO_FREE.format(what="option quotes or vol surfaces")],
                     "open": ["No library has an SSVI object. Total variance is checked through the raw-SVI form of each slice (Gatheral and Jacquier 2014, Lemma 3.3) with QuantLib `SviSmileSection`; the mapping itself is arithmetic.",
                              "`butterfly_free` and `calendar_free` are sufficient conditions on the parameters (G-J 2014 Theorem 4.2, Corollary 4.1), recomputed as arithmetic: no library checks them. A surface can fail them and still be free of arbitrage."]},
    "sabr": {"real": [NO_FREE.format(what="option quotes or vol surfaces")],
             "open": ["Arbitrage-free SABR at `nu > 0` has no tight outside source (oracle README)."]},
    "ois-full": {"real": SOFR_RD + SONIA_RD + ESTR_RD,
                 "open": ["The ESTR every-year set passes the stated 0.5 bp with a thin margin (worst pillar 1M). Accept, or ask for a front-end pillar check against published ESTR fixings?"]},
    "bond-fit": {"real": ["Not run in this pack. Free data exists (US Treasury par yields; Fed GSW parameters), but a Nelson-Siegel fit against a Svensson fit to different bonds is a method comparison with no tight tolerance to state up front."],
                 "open": ["Agree a tolerance for a Nelson-Siegel fit to published Treasury yields before running it."]},
    "repo": {"real": [NO_FREE.format(what="general or special repo rates by term")]},
    "cross-currency": {"real": [NO_FREE.format(what="cross-currency basis quotes")]},
    "cds": {"real": [NO_FREE.format(what="CDS spreads")]},
    "dividend-borrow": {"real": [NO_FREE.format(what="dividend or borrow history")]},
    "inflation": {"real": ["Not run in this pack. Free data exists (UK CPI from ONS; BoE GLC inflation curves, internal use only), but no free zero-coupon inflation swap quotes, so the curve's inputs cannot be rebuilt from published data."],
                  "open": ["Decide whether a CPI-index-only check (published index against the curve's base fixing) is worth adding."]},
    "caps-swaptions": {"real": [NO_FREE.format(what="cap or swaption volatilities")]},
    "commodities": {"real": [NO_FREE.format(what="commodity forward curves")]},
    "sector-rating": {"real": [NO_FREE.format(what="CDS spreads by sector or rating")]},
    "funding": {"before": "0 of 3", "real": [NO_FREE.format(what="funding spreads")],
                "open": ["QuantLib has no funding-curve object. Round 2 (2026-11-18) builds it from QuantLib objects: the OIS `DiscountCurve`, `InterestRate(rate, Actual360, Simple)` for the funding discount factors, and a log-linear ratio curve P_f / D_ois whose continuous forwards are the spreads (`oracle/python/outside_f.py`, row FUND.RATIO, classed library-object by `tools/outside_shares.py`). All 3 cases agree at their own tolerance. The decomposition follows the spec's own formula, so this checks the arithmetic and the conventions (ACT/360 simple quotes, piecewise-flat spread, last spread held), not an independent model. Accept?"]},
    "financing-term": {"before": "0 of 13", "real": [NO_FREE.format(what="term repo or stock borrow quotes")],
                       "open": ["No library builds this curve. Round 2 (2026-11-18) reads the cumulative funding, spread and fee with QuantLib `LinearInterpolation` and the repo discount factors with `InterestRate(Simple)`; every output is arithmetic on those (`oracle/python/outside_j.py` wave 4, class library-primitive, the class numpy interp earned for scenario replay). All 13 cases agree. It is a check of the interpolation rule and the arithmetic, not an independent model.",
                                "The time inputs are year fractions, not dates, so QuantLib's date-based dividend engine could not price `eq.forward.term_financed` directly without rounding the times."]},
    "liquidity": {"real": ["No official liquidity curve exists to reconcile against. The recorder keeps free crypto order-book snapshots (tools/recorder), which could feed a method test but not a reconciliation."],
                  "open": ["The square-root impact law has no library implementation with the same conventions. Round 2 (2026-11-18) finds the optimal horizon numerically (scipy `brentq` on dc/dh, not the closed form): it agrees on `optimal_horizon` and `min_cost` for all 7 cases, but the other outputs are the spec's arithmetic, so the check is recorded and NOT counted (`oracle/OUTSIDE_J.json`, `liqcurve_j` not_checked), as for scenario historical shocks. The outside share stays 0 of 7; is a hand or published-example check enough for this curve?"]},
    "mbs": {"real": [NO_FREE.format(what="MBS pool factors")]},
    "vol-surface": {"real": [NO_FREE.format(what="option quotes or vol surfaces")]},
    "local-vol": {"real": [NO_FREE.format(what="option quotes or vol surfaces")]},
    "swaption-cube": {"real": [NO_FREE.format(what="swaption volatilities")]},
    "vol-term-structure": {"real": [NO_FREE.format(what="option quotes or vol surfaces")]},
    "interpolation-methods": {"real": ["Not applicable: these are interpolation methods on given pillars, not a market curve."],
                              "open": ["Tension spline and hybrid cases have mpmath replay and properties only (oracle README)."]},
    "hedging-costs": {"real": ["Not applicable: an optimisation on given inputs, not a market curve."]},
    "research-workflow": {"real": ["Not applicable: synthetic prices, a teaching example."]},
    "ac-frontier": {"real": ["Not applicable: a model curve on assumed parameters, not a market curve (HR-10)."],
                    "open": ["No free library implements Almgren-Chriss; the outside check is a blind second-lane re-derivation or [AC00]'s printed kappa (DR-H2), 3 of 5 value cases in `ac_h` (`oracle/OUTSIDE_SHARES.md`). Is a blind re-derivation from the same paper independent enough?"]},
    "impact-curves": {"real": ["Not calibrated: the impact coefficient Y is an input. The crypto calibration (H-1) is a pilot on partial recorded days with no conclusions in v0.10.0."],
                      "open": ["No free library implements the square-root law or Obizhaeva-Wang; all 4 value cases in `imp_h` are blind re-derived (DR-H2), and imp_h-0001 and -0002 check arithmetic on the stated form only."]},
    "volume-profile": {"real": ["Not applicable: the profile is an input; no free intraday equity volume data is used (crypto venue only, aggregates)."],
                       "open": ["Schedule cases are integer and rational arithmetic; blind re-derived (DR-H2), 6 of 8 value cases in `sched_h`."]},
    "walk-the-book": {"real": ["Recorded crypto venue order-book snapshots only (forward-log), labelled \"crypto venue; not equities or rates\"; H-1 is a pilot on partial days 2026-11-12..18 with no conclusions."],
                      "open": ["No result yet: the curve waits for the H-1 pilot run; no golden suite."]},
}


# Everything from this line down in a checklist is hand-filled (AI review sections, notes) and is kept on rebuild;
# --check compares only the part above it.
MARK = "<!-- Hand-filled below this line: the generator keeps it. Any AI review sections go here. -->"

RULINGS = {"B": ["stage-b-rulings.md"], "C": ["stage-c-rulings.md"], "D": ["stage-d-rulings.md", "r1-rulings.md"],
           "E": ["stage-e-rulings.md", "stage-e-rulings-b.md"], "F": ["stage-f-rulings.md"], "I": ["stage-i-rulings.md"],
           "J": ["stage-j-rulings.md", "stage-j-rulings-curves.md", "stage-j-rulings-w1.md", "stage-j-rulings-w2.md", "stage-j-rulings-w3.md"],
           "H": ["stage-h-rulings-w1.md", "stage-h-rulings-w1b.md"]}
GOLDEN = {}
for _p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
    _d = json.loads(_p.read_text(encoding="utf-8"))
    GOLDEN[_p.stem] = (_d.get("spec"), {c["operation"] for c in _d.get("cases", []) if c["expected"]["status"] == "ok"})


def golden_specs(slug):
    """Spec files named by the golden suites that hold this curve's operations (or suites)."""
    p = CURVES / "data" / f"{slug}.json"
    ev = (json.loads(p.read_text(encoding="utf-8")).get("evidence") or {}) if p.exists() else {}
    ops = set(ev.get("operations", [])) | ({ev["operation"]} if "operation" in ev else set())
    suites = {s["suite"] for s in ev.get("suites", [])}
    return sorted({sp for stem, (sp, o) in GOLDEN.items() if sp and (o & ops or stem in suites)})


def rows():
    out = []
    for line in (CURVES / "README.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\| \[(.+?)\]\((.+?)\.md\) \| (\w) \| (.+) \|$", line)
        if m:
            out.append(dict(zip(("name", "slug", "stage", "evidence"), m.groups())))
    return out


def section(text, head):
    m = re.search(rf"^## {re.escape(head)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def outside(src):
    return "quantlib" in src or "strata" in src


def evidence(slug):
    p = CURVES / "data" / f"{slug}.json"
    ev = json.loads(p.read_text(encoding="utf-8")).get("evidence") if p.exists() else None
    if not ev:
        return None, []
    if "by_source" in ev:
        n = ev["cases"]
        k = sum(v for s, v in ev["by_source"].items() if outside(s))
        return (n, k), [f"| {s.split(': ', 1)[0]} | {s.split(': ', 1)[1]} | {v} | {'yes' if outside(s) else 'no'} |" for s, v in ev["by_source"].items()]
    if "suites" in ev:
        n = sum(s["cases"] for s in ev["suites"])
        k = sum(s["outside"] for s in ev["suites"])
        return (n, k), [f"| {s['suite']} | per-case register | {s['cases']} | {s['outside']} reproduced |" for s in ev["suites"]]
    if "outside" in ev:
        return (ev["cases"], ev["outside"]), [f"| {ev['operation']} | {m} | {a} | {b} reproduced |" for m, (a, b) in ev.get("by_method", {}).items()]
    return None, []


def page(r):
    slug = r["slug"]
    text = (CURVES / f"{slug}.md").read_text(encoding="utf-8")
    specs = [s if s.startswith("specifications/") else "specifications/" + s for s in golden_specs(slug)]
    rulings = ["specifications/" + f for f in RULINGS[r["stage"]]]
    oracle = section(text, "Oracle evidence and limits") or section(text, "Limits")
    counts, table = evidence(slug)
    n = NOTES.get(slug, {})
    share = f"{counts[1]} of {counts[0]} ({100 * counts[1] / counts[0]:.0f}%)" if counts else "not counted per case on the gallery page"
    L = [f"# Evidence checklist: {r['name']}", "",
         f"Generated by `tools/validation/build_checklists.py` from the gallery data and the goldens; do not edit by hand. Process: [README](README.md).", "",
         "| Item | Value | Evidence class |", "|---|---|---|",
         f"| Gallery page | [{r['name']}](../curves/{slug}.md) | observed |",
         f"| Stage | {r['stage']} | observed |",
         f"| Spec (named by the golden suites) | {', '.join('`' + s + '`' for s in specs) or 'see gallery page'} | observed |",
         f"| Rulings (the stage's rulings files) | {', '.join('`' + s + '`' for s in rulings)} | derived from the stage |",
         f"| Golden value cases | {counts[0] if counts else 'see gallery page'} | observed |",
         f"| Outside library in `verified_by` (QuantLib or Strata) | {share} | observed |"]
    if n.get("before"):
        L.append(f"| Before this pack (v0.9.0) | {n['before']} | observed (git `5b73a180`) |")
    L += ["", "## Golden cases by source", "", "| Operation or suite | Sources | Cases | Outside |", "|---|---|---:|---|"] + (table or ["| see gallery page | | | |"])
    L += ["", "## Oracle evidence and limits (from the gallery page)", "", oracle or "None stated on the page.", "",
          "## Real-data reconciliation", ""] + [f"- {x}" for x in n.get("real", ["Not assessed in this pack."])]
    L += ["", "## Open questions", ""] + [f"- {x}" for x in n.get("open", ["None raised by the pack."])]
    L += ["", "## What to check", "",
          "- [ ] Spec read; formula and conventions match the cited sources",
          "- [ ] Rulings read; each one is a decision you accept",
          "- [ ] Golden sources: the hand or replay cases are believable for what they cover",
          "- [ ] Outside checks: the library object really computes the same quantity",
          "- [ ] Real data: result and stated method differences accepted, or absence of free data accepted",
          "- [ ] Open questions answered",
          "", MARK, ""]
    return "\n".join(L)


AI = OUT / "ai-review"
LIMIT = 30000
QUESTIONS = [
    "Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.",
    "Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?",
    "Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?",
    "Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.",
    "Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.",
    "Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?",
    "Anything that looks wrong, inconsistent or missing.",
]


def golden_cases(slug):
    p = CURVES / "data" / f"{slug}.json"
    ev = (json.loads(p.read_text(encoding="utf-8")).get("evidence") or {}) if p.exists() else {}
    ops = set(ev.get("operations", [])) | ({ev["operation"]} if "operation" in ev else set())
    suites = {s["suite"] for s in ev.get("suites", [])}
    out = []
    for f in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for c in d.get("cases", []):
            if c["expected"]["status"] == "ok" and (c["operation"] in ops or f.stem in suites):
                out.append({k: c.get(k) for k in ("case_id", "operation", "inputs", "expected", "tolerance_class", "tolerance_limit", "verified_by")})
    return out


def spec_text(paths, budget):
    parts = []
    for sp in paths:
        f = ROOT / sp
        if f.exists():
            t = f.read_text(encoding="utf-8")
            if len(t) > budget:
                t = t[:budget] + "\n\n[... truncated to fit one chat; the rest of this file is not included, so answer \"cannot check\" for anything that depends on it]"
            parts.append(f"### `{sp}`\n\n" + t)
    return "\n\n".join(parts)


def ruling_lines(stage, ops):
    lines = []
    for f in RULINGS[stage]:
        fp = ROOT / "specifications" / f
        if fp.exists():
            lines += [f"- ({f}) {x.strip()}" for x in fp.read_text(encoding="utf-8").splitlines() if any(o in x for o in ops)]
    return lines


def ai_page(r):
    slug = r["slug"]
    text = (CURVES / f"{slug}.md").read_text(encoding="utf-8")
    n = NOTES.get(slug, {})
    cases = golden_cases(slug)
    ops = sorted({c["operation"] for c in cases})
    specs = [s if s.startswith("specifications/") else "specifications/" + s for s in golden_specs(slug)]
    specs = [s for s in specs if "ruling" not in s and "targets" not in s] or specs
    oracle = section(text, "Oracle evidence and limits") or section(text, "Limits")
    head = "\n".join([
        f"# Review request: {r['name']} (QuantForge curve)", "",
        "You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.",
        "", "Rules for your answer:",
        "- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write \"cannot check\" rather than guess.",
        "- Quote the spec line or the exact number you question.",
        "- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).",
        "- After the table, list the questions you answered \"cannot check\", and why.",
        "- Your review is filed under a labelled \"AI review\" section of the curve's evidence checklist and checked against the repository before anything is acted on.",
        "", f"Stage: {r['stage']}. Evidence line from the project's curve table: {r['evidence']}.",
        "", "## Questions", ""] + [f"{i}. {q}" for i, q in enumerate(QUESTIONS + n.get("open", []), 1)])
    rul = ruling_lines(r["stage"], ops)
    rest = "\n".join(["", "## Outside-library evidence and limits (from the project's own page)", "", oracle or "None stated.", "",
                      "## Real-data reconciliation", ""] + [f"- {x}" for x in n.get("real", ["Not assessed."])] +
                     ["", "## Rulings that name this curve's operations", ""] + (rul[:40] or ["None found by operation name."]))
    budget = LIMIT - len(head) - len(rest) - 1500
    sp = spec_text(specs, max(3000, budget // 2 // max(1, len(specs))))
    budget -= len(sp)
    shown, body = [], ""
    for c in cases:
        t = json.dumps(c, separators=(",", ":"))
        if len(body) + len(t) > max(1500, budget):
            continue  # too large for the remaining space; a smaller case may still fit
        shown.append(c)
        body += t + "\n"
    if cases:
        gc = "\n".join(["", f"## Golden cases ({len(shown)} of {len(cases)} value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)",
                        "", "```json", body.rstrip(), "```"])
    else:
        gc = "\n## Golden cases\n\nNone found by operation name: answer \"cannot check\" for values."
    return head + "\n\n## Spec\n\n" + sp + "\n" + gc + "\n" + rest + "\n"


AI_README = """# AI review packet

An optional outside reading of each curve by an AI model (for example ChatGPT or Gemini). It is a source of findings to check, not a verdict on the curve (see [the evidence pack](../README.md)).

## How to run it

1. Open a new conversation for each curve and paste one file from this folder, whole. Each file is self-contained and kept to about 30,000 characters: spec text, rulings that name the curve's operations, golden cases with inputs and expected outputs (a subset when there are many, with the total stated), the outside-library and real-data results, known limits and the questions.
2. The model must quote the spec line or the number it questions, and say "cannot check" rather than guess.
3. Findings come back as one table: curve, claim, issue, severity, evidence.
4. File the answer in that curve's checklist (`docs/validation/<curve>.md`), anywhere below the line `<!-- Hand-filled below this line ... -->`, under a section headed "AI review (model, date)", naming the model and version. The generator keeps everything below that line. Check each finding against the repository before acting on it: a model can be confidently wrong.
5. An AI review does not change any page or count: a finding matters only once it is checked against the spec or golden it quotes.

The files are generated by `tools/validation/build_checklists.py` from the specs, rulings, goldens and gallery data, and contain nothing beyond what that evidence shows. Where a spec is too long it is truncated, and the file says so.
"""


def split_hand(path):
    """(generated part, hand part) of a checklist. The hand part starts at MARK and is kept on every rebuild."""
    if not path.exists():
        return None, None
    t = path.read_text(encoding="utf-8")
    i = t.find(MARK)
    return (t, None) if i < 0 else (t[:i], t[i:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = []
    rs = rows()
    missing = [r["slug"] for r in rs if r["slug"] not in NOTES]
    if missing:
        print("no NOTES entry for:", missing)
        return 1
    for r in rs:
        p, t = OUT / f"{r['slug']}.md", page(r)
        gen, hand = split_hand(p)
        cut = t.find(MARK)
        if a.check:
            if gen != t[:cut]:
                bad.append(r["slug"])
        else:
            p.write_text(t[:cut] + (hand if hand else t[cut:]), encoding="utf-8", newline="\n")
    AI.mkdir(exist_ok=True)
    for r in rs:
        p, t = AI / f"{r['slug']}.md", ai_page(r)
        if len(t) > LIMIT + 2000:
            print(f"warning: ai-review/{r['slug']}.md is {len(t)} characters")
        if a.check:
            if not p.exists() or p.read_text(encoding="utf-8") != t:
                bad.append("ai-review/" + r["slug"])
        else:
            p.write_text(t, encoding="utf-8", newline="\n")
    if a.check:
        if (AI / "README.md").read_text(encoding="utf-8") != AI_README:
            bad.append("ai-review/README")
    else:
        (AI / "README.md").write_text(AI_README, encoding="utf-8", newline="\n")
    print(f"{len(rs)} checklists" + (f"; stale: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
