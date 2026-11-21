#!/usr/bin/env python3
"""Stage K fuzz lane (k-v1-fuzz2): golden cases for the two findings of main fuzz run 44815591552 (seed 5), and
for the same fault class in the sibling handlers.

    cd oracle/python && uv run python gen_stage_k_fuzz.py

Finding 1 (Java, exit 70): rates.swaption.price_cube with a node expiry of 2^53 months reached LocalDate before
any range check (java.time.DateTimeException). Every month count in the rates operations runs from 1 to 1200, else
E_INPUT (specifications/02-curves/projection-and-fra.md line 7; rulings B19, D40, D59); C++ already checked the
node expiries and the trade expiry against that range. Python and Rust checked only `< 1`, so a count above 1200
fell through to the date arithmetic: E_DATE_RANGE in Python, and in Rust a year cast to i32 that could wrap into
the calendar's range. The cases below pin E_INPUT for node and trade months above 1200 in price_cube, and for
`expiry_months` / `start_months` above 1200 in rates.swaption.price, rates.cap.price and rates.cap.strip.

Finding 2 (Python, exit 70): exec.sor.allocate with a `lit_samples` row that is a number, not an array. A
mistyped input is E_SCHEMA (cli-contract.md, error table); C++ and Rust already said E_SCHEMA for such a row,
Java said E_INPUT. A `lit_samples` that is present, not null and not an array is E_SCHEMA in all four builds now
(C++, Rust and Java said E_INPUT when there was a LIT venue, and C++ and Rust accepted it when there was none); a
dark venue's `tail` that is not an array is E_SCHEMA (Python crashed; the other three already said E_SCHEMA).

Each case is an error case whose code follows from the rules above alone, so no numerical oracle is involved.
Two-error cases follow the repo-wide order (HR-66 / HR-122: E_SCHEMA, structural E_INPUT, E_DOMAIN, E_LIMIT).
Standard library only.
"""
import copy
import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[2] / "datasets" / "golden"
OUT = GOLDEN / "stage_k" / "fuzzfix_k.json"
BIG = 2 ** 53  # the largest integer magnitude the contract accepts (cli-contract.md, "Integer")


def seed(file, case_id):
    cases = json.loads((GOLDEN / file).read_text(encoding="utf-8"))["cases"]
    return copy.deepcopy(next(c for c in cases if c["case_id"] == case_id))


def case(k, src, edit, code, tags, description):
    s = seed(*src)
    inputs = s["inputs"]
    edit(inputs)
    return {"case_id": f"fuzzfix_k-{k:04d}", "operation": s["operation"], "inputs": inputs,
            "expected": {"status": "error", "error_code": code}, "tolerance_class": "date_and_convention",
            "verified_by": ["reference-computed"], "tags": ["invalid", "fuzz", *tags, "synthetic"],
            "description": description}


def setter(*path_and_value):
    *path, value = path_and_value

    def edit(inputs):
        h = inputs
        for p in path[:-1]:
            h = h[p]
        h[path[-1]] = value
    return edit


def both(*edits):
    def edit(inputs):
        for e in edits:
            e(inputs)
    return edit


CUBE = ("stage_e_b/ratesvol_e.json", "ratesvol_e-0003")  # expiries [6, 12, 24, 60], trade 12M x 60M
SWPT = ("stage_d/capswaption_d.json", "capswaption_d-0010")
CAP = ("stage_d/capswaption_d.json", "capswaption_d-0001")
STRIP = ("stage_e_b/ratesvol_e.json", "ratesvol_e-0049")
SOR = ("stage_h/sor_h.json", "sor_h-0002")  # one LIT venue, four rows
SOR_DARK = ("stage_h/sor_h.json", "sor_h-0005")  # a LIT and a DARK venue


def dark_only(inputs):
    inputs["venues"] = [v for v in inputs["venues"] if v["kind"] == "DARK"]
    inputs.pop("lit_samples", None)


CASES = [
    case(1, CUBE, setter("cube", "expiries_months", 3, BIG), "E_INPUT", ["ratesvol", "months"],
         "the fuzz input: last node expiry 2^53 months, above the 1 to 1200 range (Java overflowed LocalDate; "
         "fuzz run 44815591552, seed 5, ratesvol_e-0003)"),
    case(2, CUBE, setter("cube", "expiries_months", 0, -BIG), "E_INPUT", ["ratesvol", "months"],
         "first node expiry -2^53 months (still increasing), below the 1 to 1200 range"),
    case(3, CUBE, setter("cube", "expiries_months", 3, 1201), "E_INPUT", ["ratesvol", "months"],
         "last node expiry 1201 months, one above the range (was E_DATE_RANGE in Java, Python and Rust)"),
    case(4, CUBE, setter("trade", "expiry_months", 1201), "E_INPUT", ["ratesvol", "months"],
         "trade expiry 1201 months, one above the range (was E_DATE_RANGE in Python and Rust)"),
    case(5, CUBE, both(setter("cube", "expiries_months", 3, BIG), setter("cube", "alpha", 0, 0, -0.05)),
         "E_INPUT", ["ratesvol", "months", "two_errors"],
         "two errors: node expiry 2^53 (structural E_INPUT) and a negative alpha (E_DOMAIN); E_INPUT first"),
    case(6, SWPT, setter("trade", "expiry_months", 1201), "E_INPUT", ["swaption", "months"],
         "swaption expiry 1201 months, one above the range (was E_DATE_RANGE in Python and Rust)"),
    case(7, SWPT, setter("trade", "expiry_months", BIG), "E_INPUT", ["swaption", "months"],
         "swaption expiry 2^53 months (Rust cast the year to i32)"),
    case(8, CAP, setter("trade", "start_months", 1201), "E_INPUT", ["cap", "months"],
         "cap start 1201 months, one above the range (was E_DATE_RANGE in Python and Rust)"),
    case(9, CAP, setter("trade", "start_months", BIG), "E_INPUT", ["cap", "months"],
         "cap start 2^53 months"),
    case(10, STRIP, setter("start_months", 1201), "E_INPUT", ["strip", "months"],
         "strip start 1201 months, one above the range (was E_DATE_RANGE in Python and Rust)"),
    case(11, STRIP, setter("start_months", BIG), "E_INPUT", ["strip", "months"],
         "strip start 2^53 months"),
    case(12, SOR, setter("lit_samples", 2, 1), "E_SCHEMA", ["sor", "mistyped"],
         "the fuzz input: a lit_samples row that is a number (Python crashed, Java said E_INPUT; fuzz run "
         "44815591552, seed 5, sor_h-0002)"),
    case(13, SOR, setter("lit_samples", 5), "E_SCHEMA", ["sor", "mistyped"],
         "lit_samples a number with a LIT venue (was E_INPUT in C++, Java and Rust)"),
    case(14, SOR_DARK, both(dark_only, setter("lit_samples", "x")), "E_SCHEMA", ["sor", "mistyped"],
         "lit_samples a string with only a DARK venue (C++ and Rust ignored it; Python iterated the string)"),
    case(15, SOR_DARK, setter("venues", 1, "tail", 1), "E_SCHEMA", ["sor", "mistyped"],
         "a DARK venue's tail that is a number (Python crashed)"),
    case(16, SOR, setter("lit_samples", [["0", "1"], 1]), "E_SCHEMA", ["sor", "mistyped", "two_errors"],
         "two errors: a row of the wrong length (structural E_INPUT) then a row that is a number (E_SCHEMA); "
         "E_SCHEMA first"),
]


def main():
    doc = {"schema_version": "1.0", "suite": "fuzzfix_k",
           "spec": "specifications/cli-contract.md; specifications/02-curves/projection-and-fra.md; "
                   "specifications/10-execution/smart-order-router.md",
           "spec_version": "1.0.0", "generator": "oracle/python/gen_stage_k_fuzz.py",
           "reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)", "cases": CASES}
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(CASES)} cases")


if __name__ == "__main__":
    main()
