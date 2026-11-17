#!/usr/bin/env python3
"""Write one reviewer checklist per curve in the gallery status table (docs/validation/<slug>.md).

Standard library only. Facts are read, not typed: the row and status from docs/curves/README.md, the golden counts
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

NOTES = {
    "sonia-ois": {"real": SONIA_RD, "open": ["One of 18 cases (`rulings_b`) has replay only; confirm it needs no outside check."]},
    "sofr-ois": {"real": SOFR_RD, "open": ["No free SOFR swap quotes exist, so level checks against a SOFR market curve stay open."]},
    "usd-term-3m": {"real": [NO_FREE.format(what="term-rate swap or FRA quotes")],
                    "open": ["USD-TERM-3M is a synthetic index (no live USD term IBOR); confirm the reviewer accepts a method-only test.",
                             "One case (`rulings_b`) has replay only."]},
    "gbpusd-fx-forward": {"before": "0 of 11", "real": [NO_FREE.format(what="FX forward points")],
                          "open": ["QuantLib's `FxForward` uses the same spot-normalised forward as the spec (both cite covered interest parity); it is an outside implementation of the same formula, not an independent model."]},
    "equity-forward": {"before": "0 of 4", "real": [NO_FREE.format(what="dividend or borrow history")],
                       "open": ["**Disagreement for ruling** (`equity_forward-0012`): the spec ignores a dividend with `ex_date <= as_of` (`specifications/02-curves/equity-forward.md`); QuantLib's `AnalyticDividendEuropeanEngine` counts one dated on the evaluation date. With that dividend removed, QuantLib agrees on all four outputs. The golden was not changed. Is the spec's rule (ex on as_of means already ex) the one the reviewer accepts?",
                                "`equity_forward-0014` (expiry on as_of) has no outside check: there is no option for the engine to price."]},
    "svi-smile": {"before": "1 of 2", "real": [NO_FREE.format(what="option quotes or vol surfaces")],
                  "open": ["`g` and `min_g` on the counterexample are checked by central differences on QuantLib's variance at 1e-6, not at the case's own tolerance; QuantLib has no Durrleman `g`."]},
    "ssvi-surface": {"before": "0 of 3", "real": [NO_FREE.format(what="option quotes or vol surfaces")],
                     "open": ["No library has an SSVI object. Total variance is checked through the raw-SVI form of each slice (Gatheral and Jacquier 2014, Lemma 3.3) with QuantLib `SviSmileSection`; the mapping itself is arithmetic.",
                              "`butterfly_free` and `calendar_free` are sufficient conditions on the parameters (G-J 2014 Theorem 4.2, Corollary 4.1), recomputed as arithmetic: no library checks them. A surface can fail them and still be free of arbitrage."]},
    "sabr": {"real": [NO_FREE.format(what="option quotes or vol surfaces")],
             "open": ["Arbitrage-free SABR at `nu > 0` has no tight outside source (oracle README)."]},
    "ois-full": {"real": SOFR_RD + SONIA_RD + ["ESTR: not run in this pack. Free data exists (ECB euro area yield curves, Svensson parameters); the same round trip would apply."],
                 "open": ["ESTR real-data round trip not run (open)."]},
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
    "funding": {"real": [NO_FREE.format(what="funding spreads")],
                "open": ["No outside library builds this curve; QuantLib's spreaded term structures could check the spread arithmetic (library-primitive at best). Not done in this pack."]},
    "financing-term": {"real": [NO_FREE.format(what="term repo or stock borrow quotes")],
                       "open": ["No outside library builds this curve. `eq.forward.term_financed` could be checked with QuantLib's dividend engine as `eq.forward.outright` now is. Not done in this pack."]},
    "liquidity": {"real": ["No official liquidity curve exists to reconcile against. The recorder keeps free crypto order-book snapshots (tools/recorder), which could feed a method test but not a reconciliation."],
                  "open": ["The square-root impact law has no library implementation with the same conventions."]},
    "mbs": {"real": [NO_FREE.format(what="MBS pool factors")]},
    "vol-surface": {"real": [NO_FREE.format(what="option quotes or vol surfaces")]},
    "local-vol": {"real": [NO_FREE.format(what="option quotes or vol surfaces")]},
    "swaption-cube": {"real": [NO_FREE.format(what="swaption volatilities")]},
    "vol-term-structure": {"real": [NO_FREE.format(what="option quotes or vol surfaces")]},
    "interpolation-methods": {"real": ["Not applicable: these are interpolation methods on given pillars, not a market curve."],
                              "open": ["Tension spline and hybrid cases have mpmath replay and properties only (oracle README)."]},
    "hedging-costs": {"real": ["Not applicable: an optimisation on given inputs, not a market curve."]},
    "research-workflow": {"real": ["Not applicable: synthetic prices, a teaching example."]},
}


RULINGS = {"B": ["stage-b-rulings.md"], "C": ["stage-c-rulings.md"], "D": ["stage-d-rulings.md", "r1-rulings.md"],
           "E": ["stage-e-rulings.md", "stage-e-rulings-b.md"], "F": ["stage-f-rulings.md"], "I": ["stage-i-rulings.md"],
           "J": ["stage-j-rulings.md", "stage-j-rulings-curves.md", "stage-j-rulings-w1.md", "stage-j-rulings-w2.md", "stage-j-rulings-w3.md"]}
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
        m = re.match(r"\| \[(.+?)\]\((.+?)\.md\) \| (.+?) \| (\w) \| (.+) \|$", line)
        if m:
            out.append(dict(zip(("name", "slug", "status", "stage", "evidence"), m.groups())))
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
    L = [f"# Reviewer checklist: {r['name']}", "",
         f"Generated by `tools/validation/build_checklists.py` from the gallery data and the goldens; do not edit by hand. Process: [README](README.md).", "",
         "| Item | Value | Evidence class |", "|---|---|---|",
         f"| Gallery page | [{r['name']}](../curves/{slug}.md) | observed |",
         f"| Status | {r['status']} (stage {r['stage']}) | observed |",
         f"| Spec (named by the golden suites) | {', '.join('`' + s + '`' for s in specs) or 'see gallery page'} | observed |",
         f"| Rulings (the stage's rulings files) | {', '.join('`' + s + '`' for s in rulings)} | derived from the stage |",
         f"| Golden value cases | {counts[0] if counts else 'see gallery page'} | observed |",
         f"| Outside library in `verified_by` (QuantLib or Strata) | {share} | observed |"]
    if n.get("before"):
        L.append(f"| Before this pack (v0.9.0) | {n['before']} | observed (git `5b73a180`) |")
    L += ["", "## Golden cases by source", "", "| Operation or suite | Sources | Cases | Outside |", "|---|---|---:|---|"] + (table or ["| see gallery page | | | |"])
    L += ["", "## Oracle evidence and limits (from the gallery page)", "", oracle or "None stated on the page.", "",
          "## Real-data reconciliation", ""] + [f"- {x}" for x in n.get("real", ["Not assessed in this pack."])]
    L += ["", "## Open questions for the reviewer", ""] + [f"- {x}" for x in n.get("open", ["None raised by the pack."])]
    L += ["", "## What to check", "",
          "- [ ] Spec read; formula and conventions match the cited sources",
          "- [ ] Rulings read; each one is a decision you accept",
          "- [ ] Golden sources: the hand or replay cases are believable for what they cover",
          "- [ ] Outside checks: the library object really computes the same quantity",
          "- [ ] Real data: result and stated method differences accepted, or absence of free data accepted",
          "- [ ] Open questions answered",
          "", "## Reviewer sign-off", "",
          "Only a named human reviewer's sign-off moves the status row to Validated (ROADMAP.md). An AI review may be attached below it, labelled as such; it is not the sign-off.", "",
          "| Field | Entry |", "|---|---|", "| Reviewer name | |", "| Date | |",
          "| Verdict (Validated / Validated with conditions / Not validated) | |", "| Conditions or findings | |", ""]
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
        "- Your review is a second opinion. It is filed under a labelled \"AI review\" section and never counts as the human sign-off.",
        "", f"Status: {r['status']} (stage {r['stage']}). Evidence line from the project's status table: {r['evidence']}.",
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

A second opinion on each curve from an outside AI model (for example ChatGPT or Gemini), prepared before the human sign-off. It is not the sign-off and never moves a status row (see [the process](../README.md)).

## How to run it

1. Open a new conversation for each curve and paste one file from this folder, whole. Each file is self-contained and kept to about 30,000 characters: spec text, rulings that name the curve's operations, golden cases with inputs and expected outputs (a subset when there are many, with the total stated), the outside-library and real-data results, known limits and the questions.
2. The reviewer must quote the spec line or the number it questions, and say "cannot check" rather than guess.
3. Findings come back as one table: curve, claim, issue, severity, evidence.
4. File the answer in that curve's checklist (`docs/validation/<curve>.md`) under a section headed "AI review (model, date)", naming the model and version. Check each finding against the repository before acting on it: a model can be confidently wrong.
5. The AI review never counts as the sign-off. Only a named human reviewer's verdict moves a row to Validated.

The files are generated by `tools/validation/build_checklists.py` from the specs, rulings, goldens and gallery data, and contain nothing beyond what that evidence shows. Where a spec is too long it is truncated, and the file says so.
"""


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
        if a.check:
            if not p.exists() or p.read_text(encoding="utf-8") != t:
                bad.append(r["slug"])
        else:
            p.write_text(t, encoding="utf-8", newline="\n")
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
