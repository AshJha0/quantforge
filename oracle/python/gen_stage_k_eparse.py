#!/usr/bin/env python3
"""Stage K lane k-v1-eparse: golden cases for ruling KR-344 (specifications/stage-k-rulings-rev1.md).

    cd oracle/python && uv run python gen_stage_k_eparse.py

A decimal string inside a valid JSON input that is not a decimal (for example "é" or "1,5") is E_SCHEMA, not
E_PARSE: cli-contract.md reserves E_PARSE for input that is not valid JSON or has a duplicate key. Before
KR-344 all four builds said E_PARSE for it in every paper.* operation (program/stage_k_fuzz3/STOP_NOTE.md,
Open). The message is unchanged ("<name> is not a decimal").

Each case is an error case whose code follows from the rule alone, so no numerical oracle is involved.
Two-error cases name their steps in brackets (repo-wide order HR-66: E_SCHEMA, E_LIMIT, structural E_INPUT,
E_DOMAIN). Standard library only.
"""
import copy
import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[2] / "datasets" / "golden"
OUT = GOLDEN / "stage_k" / "eparse_k.json"


def seed(case_id):
    cases = json.loads((GOLDEN / "stage_h" / "pt_h.json").read_text(encoding="utf-8"))["cases"]
    return copy.deepcopy(next(c for c in cases if c["case_id"] == case_id))


def case(k, src, edit, code, tags, description):
    s = seed(src)
    inputs = s["inputs"]
    edit(inputs)
    return {"case_id": f"eparse_k-{k:04d}", "operation": s["operation"], "inputs": inputs,
            "expected": {"status": "error", "error_code": code}, "tolerance_class": "date_and_convention",
            "verified_by": ["reference-computed"], "tags": ["invalid", "paper", "malformed", *tags, "synthetic"],
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
DAY = "pt_h-0002"  # paper.book.end_of_day with two fills
PRE = "pt_h-0017"  # paper.pretrade.check, SELL LIMIT 2 @ 100
SES = "pt_h-0030"  # paper.session.run, first step a LIT BUY order
ORDER = ("script", 0, "order")
D19 = "1.0000000000000000001"  # 19 decimals: outside the HR-77 input range, E_LIMIT


def drop(*path):
    def edit(inputs):
        h = inputs
        for p in path[:-1]:
            h = h[p]
        h.pop(path[-1], None)
    return edit

CASES = [
    case(1, FILL, setter("fills", 0, "price", "\u00e9"), "E_SCHEMA", [],
         "apply_fill: fill price \"\u00e9\" is not a decimal (KR-344; was E_PARSE in all four builds)"),
    case(2, DAY, setter("close", "1,5"), "E_SCHEMA", [],
         "end_of_day: close \"1,5\" is not a decimal (KR-344; was E_PARSE)"),
    case(3, PRE, setter("order", "quantity", "two"), "E_SCHEMA", [],
         "pretrade: order quantity \"two\" is not a decimal (KR-344; was E_PARSE)"),
    case(4, SES, setter(*ORDER, "quantity", "\u00e9"), "E_SCHEMA", [],
         "session: order quantity \"\u00e9\" is not a decimal (KR-344; was E_PARSE)"),
    case(5, FILL, both(setter("fills", 0, "quantity", "0"), setter("fills", 1, "fee", "\u00e9")), "E_SCHEMA",
         ["two_errors"],
         "two errors: fill 0 quantity 0 [domain] and fill 1 fee \"\u00e9\" [schema]; E_SCHEMA first "
         "(was E_PARSE)"),
    case(6, FILL, both(setter("fills", 0, "side", "HOLD"), setter("fills", 1, "price", "1..0")), "E_SCHEMA",
         ["two_errors"],
         "two errors: fill 0 side HOLD [structural] and fill 1 price \"1..0\" [schema]; E_SCHEMA first "
         "(was E_PARSE)"),
    case(7, FILL, both(setter("cash", D19), setter("fills", 1, "price", "é")), "E_SCHEMA", ["two_errors"],
         "two errors: cash with 19 decimals [limit] and fill 1 price \"é\" [schema]; E_SCHEMA first "
         "(HR-66; was E_LIMIT in all four builds)"),
    case(8, DAY, both(setter("cash_open", D19), setter("close", "NaN")), "E_SCHEMA", ["two_errors"],
         "end_of_day, two errors: cash_open with 19 decimals [limit] and close \"NaN\" [schema]; E_SCHEMA "
         "first (HR-66; was E_LIMIT)"),
    case(9, DAY, both(setter("position_open", "1"), drop("prev_close"), setter("fills", 0, "quantity", "0")),
         "E_SCHEMA", ["two_errors"],
         "end_of_day, two errors: fill 0 quantity 0 [domain] and prev_close missing with an open position "
         "[schema]; E_SCHEMA first (HR-66; was E_DOMAIN)"),
    case(10, PRE, both(setter("cash", D19), setter("order", "limit_price", "é")), "E_SCHEMA",
         ["two_errors"],
         "pretrade, two errors: cash with 19 decimals [limit] and limit_price \"é\" [schema]; E_SCHEMA "
         "first (HR-66; was E_LIMIT)"),
    case(11, PRE, both(setter("limits", "max_notional", D19), setter("limits", "max_orders_per_day", "3")),
         "E_SCHEMA", ["two_errors"],
         "pretrade, two errors: max_notional with 19 decimals [limit] and max_orders_per_day a string "
         "[schema]; E_SCHEMA first (HR-66; was E_LIMIT)"),
    case(12, SES, both(setter("cash", D19), setter(*ORDER, "quantity", "é")), "E_SCHEMA", ["two_errors"],
         "session, two errors: cash with 19 decimals [limit] and order quantity \"é\" [schema]; "
         "E_SCHEMA first (HR-66; was E_LIMIT)"),
    case(13, SES, both(setter("cash", D19), drop("lit", "tick_size")), "E_SCHEMA", ["two_errors"],
         "session, two errors: cash with 19 decimals [limit] and lit/tick_size missing [schema]; E_SCHEMA "
         "first (HR-66; was E_LIMIT)"),
]


def main():
    doc = {"schema_version": "1.0", "suite": "eparse_k",
           "spec": "specifications/cli-contract.md; specifications/10-execution/paper-trading.md",
           "spec_version": "1.0.0", "generator": "oracle/python/gen_stage_k_eparse.py",
           "reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)", "cases": CASES}
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(CASES)} cases")


if __name__ == "__main__":
    main()
