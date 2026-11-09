"""Governance checks for tools/quality_gate.py: the model register (plan 12.2 A2) and the convergence rule
(plan 12.2 Q5b, spec template rule F-6). Standard library only.

Both are ratchets. Gaps that existed when the rule came in sit in conformance/quality/governance_baseline.json
and only warn. A new gap fails. A baseline entry that has since been fixed warns as stale (tolerant while the
spec lane back-fills the A2 fields); remove it then. `quality_gate.py --write-baseline` rewrites it from the current tree.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "model-inventory.md"
SPECS = ROOT / "specifications"
BASELINE = ROOT / "conformance" / "quality" / "governance_baseline.json"

# Plan 12.2 A2, in the order the plan lists them. Written in an entry as bold labels, e.g. "- **Tier:** 2".
A2_FIELDS = ("Tier", "Challenger", "Monitoring thresholds", "Data lineage hash", "Retirement trigger", "Validation report")

# Spec pages that are not a model: rulings, targets, handovers, follow-up lists, source lists, READMEs.
NOT_MODEL_PAGE = re.compile(r"(^|[-_])(readme|rulings?|targets?|handover|followups?|sources|questions)([-_]|$)", re.I)

# Words that mark a page as defining a numerical method (iterative solve, grid, quadrature, tree, MC, optimiser).
NUMERICAL = re.compile(
    r"\b(newton|bisection|brent|secant|iterat\w*|root[- ]find\w*|quadrature|monte carlo|finite[- ]difference|"
    r"pde|crank[- ]nicolson|lattice|binomial tree|trinomial|optimi[sz]\w*|levenberg|gauss[- ]newton)\b", re.I)
CONV_HEAD = re.compile(r"^##\s+Convergence and limit cases\s*$", re.I | re.M)


def has_field(text, name):
    """True if the entry text carries a filled label `name` (bold label, bullet label or table row)."""
    words = r"[\s_-]+".join(map(re.escape, name.split()))
    pat = rf"(?:\*\*\s*{words}\s*:?\s*\*\*\s*:?|^\s*[-*]\s*{words}\s*:|^\|\s*{words}\s*\|)(.*)$"
    for m in re.finditer(pat, text, re.I | re.M):
        val = m.group(1).strip(" |*\t")
        if val and not val.upper().startswith("TODO"):
            return True
    return False


def inventory_entries(text):
    """{id: entry text} for every '### <ID> title' heading (IDs such as M1, ME-A4, EB12); an entry ends at the next heading."""
    out = {}
    for m in re.finditer(r"^### ([A-Z][A-Z0-9-]*\d)\b(.*?)(?=^#{1,3} |\Z)", text, re.M | re.S):
        out[m.group(1)] = m.group(2)
    return out


def inventory_specs(text):
    """Basenames of the spec pages the inventory names in backticks."""
    return {Path(x).name for x in re.findall(r"`([\w./-]+\.md)`", text)}


def model_pages(root=SPECS):
    """Spec pages in domains 02 to 11, as 'domain/page.md'."""
    return [f"{p.parent.name}/{p.name}" for p in sorted(root.glob("*/*.md"))
            if re.match(r"(0[2-9]|1[01])-", p.parent.name) and not NOT_MODEL_PAGE.search(p.stem)]


def register_gaps(inv_text, pages):
    gaps = []
    for eid, body in inventory_entries(inv_text).items():
        miss = [f for f in A2_FIELDS if not has_field(body, f)]
        if miss:
            gaps.append(f"entry {eid}: missing {', '.join(miss)}")
    named = inventory_specs(inv_text)
    gaps += [f"spec {p}: no inventory entry" for p in pages if Path(p).name not in named]
    return gaps


def convergence_gap(text):
    """None when the page passes; otherwise the reason. Pages without a numerical method always pass."""
    if not NUMERICAL.search(text):
        return None
    m = CONV_HEAD.search(text)
    if not m:
        return "numerical method without a '## Convergence and limit cases' section"
    sec = re.split(r"^#{1,2}\s", text[m.end():], maxsplit=1, flags=re.M)[0]
    rows = [r.strip() for r in sec.splitlines() if r.strip().startswith("|")]
    rows = [r for r in rows if not re.fullmatch(r"\|[\s|:-]+\|", r)][1:]  # drop the separator and the header
    filled = [r for r in rows if all(c.strip() and not c.strip().startswith("<") for c in r.strip("|").split("|"))]
    return None if filled else "'## Convergence and limit cases' has no filled table row"


def spec_gaps(root=SPECS):
    gaps = []
    for rel in model_pages(root):
        why = convergence_gap((root / rel).read_text(encoding="utf-8"))
        if why:
            gaps.append(f"spec {rel}: {why}")
    return gaps


def ratchet(gaps, legacy):
    """(new gaps, which fail; baseline gaps still present, which warn; stale baseline entries, which warn)."""
    g, l = set(gaps), set(legacy)
    return sorted(g - l), sorted(g & l), sorted(l - g)


def current(inventory=INVENTORY, specs=SPECS):
    return {"register": register_gaps(inventory.read_text(encoding="utf-8"), model_pages(specs)),
            "specs": spec_gaps(specs)}
