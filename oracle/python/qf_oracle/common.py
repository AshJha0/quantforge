"""Golden-file writer shared by the generators."""
import json
from pathlib import Path

import mpmath as mp

mp.mp.dps = 50
ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "datasets" / "golden" / "core"
REPORT = []


def note(line):
    REPORT.append(line)
    print(line)


def f(x):
    """Round a high-precision value once, to the nearest binary64."""
    return float(x)


class Suite:
    def __init__(self, name, spec, generator):
        self.name, self.spec, self.generator, self.cases = name, spec, generator, []

    def add(self, op, inputs, outputs=None, error=None, cls="simple_analytic", verified=("hand",),
            tags=(), output_classes=None, extra_checks=None, limit=None, description=None):
        cid = f"{self.name}-{len(self.cases) + 1:04d}"
        expected = {"status": "error", "error_code": error} if error else {"status": "ok", "outputs": outputs}
        c = {"case_id": cid, "operation": op, "inputs": inputs, "expected": expected, "tolerance_class": cls,
             "verified_by": list(verified), "tags": list(tags)}
        if description:
            c["description"] = description
        if output_classes:
            c["output_classes"] = output_classes
        if extra_checks:
            c["extra_checks"] = extra_checks
        if limit:
            c["tolerance_limit"] = limit
        self.cases.append(c)

    def write(self):
        GOLDEN.mkdir(parents=True, exist_ok=True)
        doc = {"schema_version": "1.0", "suite": self.name, "spec": self.spec, "spec_version": "1.0.0",
               "generator": self.generator, "reviewer": "none: self-assessment until the end-of-project human review",
               "cases": self.cases}
        (GOLDEN / f"{self.name}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        note(f"suite {self.name}: {len(self.cases)} cases")
