#!/usr/bin/env python3
"""Stage K fuzz lane (k-v1-fuzz3): golden cases for the finding of fuzz run 44937631714 (seed 8, on k-v1
5e4facc9), and for the same fault class in the sibling paper.* handlers.

    cd oracle/python && uv run python gen_stage_k_fuzz3.py

Finding (Python, exit 70): paper.book.apply_fill with a fill whose `side` is an array. The side lookup hashed
the value (TypeError: unhashable list) before any type check. A mistyped input is E_SCHEMA (cli-contract.md,
error table); an unlisted side string stays E_INPUT (paper-trading.md, Errors; rule_h-0040). C++, Java and
Rust said E_INPUT for a side of any wrong JSON type. Python also crashed on an array `side` in
paper.book.end_of_day and paper.pretrade.check, and on an array `symbol` in paper.session.run.

All four builds now: a fill's `side`, `quantity`, `price` and (when present) `fee` must be JSON strings, checked
for every fill before any other check of the case; `order/side` and `order/type` of paper.pretrade.check, and
`order_id`, `symbol`, `side`, `type` and a non-null `venue` of a paper.session.run order, must be strings, else
E_SCHEMA. The fills of paper.book.apply_fill and paper.book.end_of_day are then checked in the KR-230 order over
the whole list (HR-122: E_SCHEMA, E_LIMIT, structural E_INPUT, E_DOMAIN): decimals, then unknown sides, then
non-positive quantities or prices. Before, each fill was checked in turn, so an unknown side in fill 0 hid a
mistyped or out-of-range decimal in fill 1, and a non-positive quantity in fill 0 hid an unknown side in fill 1.

Each case is an error case whose code follows from the rules above alone, so no numerical oracle is involved.
Two-error cases name their steps in brackets (python/tests/test_stage_k_error_order.py). Standard library only.
"""
import copy
import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[2] / "datasets" / "golden"
OUT = GOLDEN / "stage_k" / "fuzzfix_k2.json"
D19 = "1.0000000000000000001"  # 19 decimals: outside the HR-77 input range, E_LIMIT


def seed(case_id):
    cases = json.loads((GOLDEN / "stage_h" / "pt_h.json").read_text(encoding="utf-8"))["cases"]
    return copy.deepcopy(next(c for c in cases if c["case_id"] == case_id))


def case(k, src, edit, code, tags, description):
    s = seed(src)
    inputs = s["inputs"]
    edit(inputs)
    return {"case_id": f"fuzzfix_k2-{k:04d}", "operation": s["operation"], "inputs": inputs,
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


FILL = "pt_h-0001"  # paper.book.apply_fill, fills BUY 2 @ 100 then SELL 1 @ 110
BIG = "pt_h-0050"  # paper.book.apply_fill, 31-digit cash, one fill
DAY = "pt_h-0002"  # paper.book.end_of_day with two fills
PRE = "pt_h-0017"  # paper.pretrade.check, SELL LIMIT 2 @ 100
SES = "pt_h-0030"  # paper.session.run, first step a LIT BUY order
ORDER = ("script", 0, "order")

CASES = [
    case(1, BIG, both(setter("fills", 0, "side", [0]), setter("fills", 0, "fee", "é")), "E_SCHEMA",
         ["paper", "mistyped"],
         "the fuzz input: a fill side that is an array, with a malformed fee as well (Python crashed hashing "
         "the side; C++, Java and Rust said E_INPUT; fuzz run 44937631714, seed 8, pt_h-0050)"),
    case(2, FILL, setter("fills", 0, "side", [0]), "E_SCHEMA", ["paper", "mistyped"],
         "fill side an array (Python crashed)"),
    case(3, FILL, setter("fills", 1, "side", 1), "E_SCHEMA", ["paper", "mistyped"],
         "fill side a number (was E_INPUT in all four builds)"),
    case(4, FILL, setter("fills", 0, "side", {"BUY": 1}), "E_SCHEMA", ["paper", "mistyped"],
         "fill side an object (Python crashed)"),
    case(5, FILL, setter("fills", 0, "side", True), "E_SCHEMA", ["paper", "mistyped"],
         "fill side a boolean (was E_INPUT in all four builds)"),
    case(6, FILL, both(setter("fills", 0, "side", "HOLD"), setter("fills", 1, "quantity", 1)), "E_SCHEMA",
         ["paper", "mistyped", "two_errors"],
         "two errors: fill 0 side HOLD [structural] and fill 1 quantity a JSON number [schema]; E_SCHEMA first "
         "(was E_INPUT)"),
    case(7, FILL, both(setter("fills", 0, "quantity", "0"), setter("fills", 1, "side", "HOLD")), "E_INPUT",
         ["paper", "two_errors"],
         "two errors: fill 0 quantity 0 [domain] and fill 1 side HOLD [structural]; E_INPUT first "
         "(was E_DOMAIN)"),
    case(8, FILL, both(setter("fills", 0, "side", "HOLD"), setter("fills", 1, "price", D19)), "E_LIMIT",
         ["paper", "two_errors"],
         "two errors: fill 0 side HOLD [structural] and fill 1 price with 19 decimals [limit]; E_LIMIT first "
         "(was E_INPUT)"),
    case(9, FILL, both(setter("cash", D19), setter("fills", 1, "side", [1])), "E_SCHEMA",
         ["paper", "mistyped", "two_errors"],
         "two errors: cash with 19 decimals [limit] and fill 1 side an array [schema]; E_SCHEMA first "
         "(was E_LIMIT)"),
    case(10, DAY, setter("fills", 0, "side", ["BUY"]), "E_SCHEMA", ["paper", "mistyped"],
         "end of day: fill side an array (Python crashed)"),
    case(11, DAY, both(setter("cash_open", D19), setter("fills", 1, "side", 2)), "E_SCHEMA",
         ["paper", "mistyped", "two_errors"],
         "end of day, two errors: cash_open with 19 decimals [limit] and fill 1 side a number [schema]; "
         "E_SCHEMA first (was E_LIMIT)"),
    case(12, PRE, setter("order", "side", ["SELL"]), "E_SCHEMA", ["paper", "mistyped"],
         "pretrade: order side an array (Python crashed)"),
    case(13, PRE, setter("order", "type", 5), "E_SCHEMA", ["paper", "mistyped"],
         "pretrade: order type a number (was E_INPUT in all four builds)"),
    case(14, PRE, both(setter("order", "side", 1), setter("order", "quantity", "0")), "E_SCHEMA",
         ["paper", "mistyped", "two_errors"],
         "pretrade, two errors: order side a number [schema] and quantity 0 [domain]; E_SCHEMA first "
         "(was E_INPUT)"),
    case(15, SES, setter(*ORDER, "symbol", ["BTC-USD"]), "E_SCHEMA", ["paper", "mistyped"],
         "session: order symbol an array (Python crashed adding it to the symbol set)"),
    case(16, SES, setter(*ORDER, "side", ["BUY"]), "E_SCHEMA", ["paper", "mistyped"],
         "session: order side an array (Python crashed)"),
    case(17, SES, setter(*ORDER, "type", 1), "E_SCHEMA", ["paper", "mistyped"],
         "session: order type a number (was E_INPUT)"),
    case(18, SES, setter(*ORDER, "venue", 1), "E_SCHEMA", ["paper", "mistyped"],
         "session: order venue a number (was E_INPUT in all four builds; a null venue stays E_INPUT)"),
    case(19, SES, setter(*ORDER, "order_id", 7), "E_SCHEMA", ["paper", "mistyped"],
         "session: order_id a number (Java said E_INPUT)"),
]


def main():
    doc = {"schema_version": "1.0", "suite": "fuzzfix_k2",
           "spec": "specifications/cli-contract.md; specifications/10-execution/paper-trading.md",
           "spec_version": "1.0.0", "generator": "oracle/python/gen_stage_k_fuzz3.py",
           "reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)", "cases": CASES}
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(CASES)} cases")


if __name__ == "__main__":
    main()
