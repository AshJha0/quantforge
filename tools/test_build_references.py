#!/usr/bin/env python3
"""Planted-fault test for tools/build_references.py (R6-17). Standard library only.

A spec that lists its sources as a "Sources:" paragraph (the stage G and I form) must reach the page, and
`--check` must fail when the page lacks a spec that has sources.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_references as br  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as d:
        specs = Path(d) / "specifications"
        (specs / "08-hedging").mkdir(parents=True)
        (specs / "08-hedging" / "para.md").write_text(
            "# P\n\nSources:\n- [X1] A. Author, *A planted book*, 2001 (not opened).\n\n## Rules\n\n- not a source\n", encoding="utf-8")
        (specs / "08-hedging" / "head.md").write_text(
            "# H\n\n## Sources\n\n- [Y1] B. Author, *A heading-form source*, 2002.\n", encoding="utf-8")
        found = br.collect(specs)
        entries = {e for _, e in found}
        assert any("planted book" in e for e in entries), "paragraph-form source not read"
        assert any("heading-form" in e for e in entries), "heading-form source not read"
        assert not any("not a source" in e for e in entries), "bullet after the sources paragraph was read"
        page = br.render(found)
        assert br.missing_specs(found, page) == [], "full page reported as lacking"
        planted = "\n".join(l for l in page.splitlines() if "para.md" not in l)
        assert br.missing_specs(found, planted) == ["specifications/08-hedging/para.md"], "planted omission not caught"
    print("build_references: planted omission caught; both source formats read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
