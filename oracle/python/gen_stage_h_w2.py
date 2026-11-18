"""Stage H wave 2 goldens: MBP book rebuild (ob_h) and the simulated lit matching engine (lit_h).

Specs: specifications/09-microstructure/order-book.md, specifications/10-execution/lit-matching.md,
section "Golden value cases (stage H wave 2, DR-H2 blind lane)". The inputs and expected outputs are
read from those tables exactly as written by the spec lane; no value is taken from an implementation.
The blind lane (program/STAGE_H_BLIND_WAVE2.md) re-derived 20/20 of them independently; ob_h-0001 and
lit_h-0001 were not blind (the source note prints the checksum; the case text hints at the fill).
As an extra independent check, every ob_h crc32 (and checksum_string, where emitted) is recomputed
here with zlib from the expected book, per [KR-CRC]. Synthetic message lists only (HR-41).

Also the simulated dark pool (dark_h, specifications/10-execution/dark-pool.md, H-12) and the smart
order router (sor_h, specifications/10-execution/smart-order-router.md, H-13), from the same kind of
table; blind record program/STAGE_H_BLIND_WAVE2B.md (dark_h-0003, sor_h-0001 and 0002 not blind).
dark_h-0005/0006 and sor_h-0004 are outside-checked by tools and are not in these tables.

    cd oracle/python && uv run python -W ignore gen_stage_h_w2.py
"""
import json
import zlib
from decimal import Context, Decimal

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_stage_h_w2.py"
FOLDER = "stage_h"
SPEC_OB = "specifications/09-microstructure/order-book.md"
SPEC_LIT = "specifications/10-execution/lit-matching.md"
BLIND = "blind-rederivation (DR-H2, program/STAGE_H_BLIND_WAVE2.md): MATCH"
NOT_BLIND = {  # verdicts from program/STAGE_H_BLIND_WAVE2.md; only a blind MATCH counts in tools/outside_shares.py
    "ob_h-0001": ["hand", "outside: [KR-CRC] printed checksum 3310070434"],
    "lit_h-0001": ["hand"],
    "lit_h-0010": ["hand", "blind-rederivation (DR-H2, program/STAGE_H_BLIND_WAVE2.md): MISMATCH; spec lane wrong, "
                   "golden fixed, blind lane not rerun"],
}
OPS = {"ob_h": "micro.book.rebuild", "lit_h": "exec.sim.lit.run"}
SPEC_DARK = "specifications/10-execution/dark-pool.md"
SPEC_SOR = "specifications/10-execution/smart-order-router.md"
BLIND_2B = "blind-rederivation (DR-H2, program/STAGE_H_BLIND_WAVE2B.md): MATCH"
SHAPE_ONLY_2B = {"dark_h-0007": "blind-rederivation (DR-H2, program/STAGE_H_BLIND_WAVE2B.md): SHAPE-ONLY, values identical"}
NOT_BLIND_2B = {"dark_h-0003", "sor_h-0001", "sor_h-0002"}
DARK_LABEL = "simulated venue; not a real dark pool"


def table(rel):
    rows, intable = [], False
    for line in (common.ROOT / rel).read_text(encoding="utf-8").splitlines():
        if line.startswith("| Case | Input | Expected |"):
            intable = True
            continue
        if intable and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells[0].startswith(("ob_h-", "lit_h-", "dark_h-", "sor_h-")):
                rows.append((cells[0], json.loads(cells[1]), json.loads(cells[2])))
        elif intable:
            intable = False
    return rows


def component(text, decimals):
    v = Decimal(text)
    q = v.quantize(Decimal(1).scaleb(-decimals), context=Context(prec=200))
    assert q == v, text
    return format(q, "f").replace(".", "").lstrip("0") or "0"


def ob_check(cid, inp, exp):
    book = exp["book"]
    s = "".join(component(p, inp["price_decimals"]) + component(q, inp["qty_decimals"])
                for side in (book["asks"][:10], book["bids"][:10]) for p, q in side)
    assert (zlib.crc32(s.encode("ascii")) & 0xFFFFFFFF) == exp["crc32"], cid
    if "checksum_string" in exp:
        assert exp["checksum_string"] == s, cid


def lit_check(cid, exp):
    assert exp["label"] == "simulated venue; not a real exchange", cid
    for oid, c in exp["conservation"].items():
        out = sum(Decimal(c[k]) for k in ("filled", "resting", "cancelled", "rejected"))
        assert out == Decimal(c["submitted"]), (cid, oid)


def build():
    suites = []
    for name, spec in (("ob_h", SPEC_OB), ("lit_h", SPEC_LIT)):
        s = Suite(name, spec, G)
        for cid, inp, exp in table(spec):
            assert cid.startswith(name + "-")
            if name == "ob_h":
                ob_check(cid, inp, exp)
            else:
                lit_check(cid, exp)
            verified = NOT_BLIND.get(cid, ["hand", BLIND])
            s.add(OPS[name], inp, exp, cls="date_and_convention", verified=verified,
                  tags=["stage_h", "simulated" if name == "lit_h" else "microstructure"],
                  description=f"{cid} from the spec table" + ("; not blind" if cid in NOT_BLIND else ""))
            s.cases[-1]["case_id"] = cid  # spec ids (ob_h-0009 left the goldens, HR-41)
        add_errors(s, name)
        add_boundaries(s, name)
        suites.append(s)
    suites += build_w2b()
    suites.append(e1_suite(suites))
    return suites


def _first_number(v, path=()):
    """Path to the first numeric leaf: a JSON float, or a decimal string (HR-12) that parses as a finite number."""
    if isinstance(v, dict):
        for k in sorted(v):
            p = _first_number(v[k], path + (k,))
            if p is not None:
                return p
    elif isinstance(v, list):
        for i, x in enumerate(v):
            p = _first_number(x, path + (i,))
            if p is not None:
                return p
    elif isinstance(v, float):
        return path
    elif isinstance(v, str) and path and path[-1] not in ("id", "t", "seed"):
        try:
            if Decimal(v).is_finite() and any(ch.isdigit() for ch in v):
                return path
        except ArithmeticError:
            return None
    return None


def e1_suite(suites):
    """Non-finite input per wave 2 operation, from its first value case. These operations take no Real input: every
    number is a decimal string (HR-12), so "NaN" there is a malformed decimal and the answer is E_SCHEMA, which comes
    before F-2's E_DOMAIN. The operations are listed in conformance/E1_EXEMPT.json; these cases pin that all four
    builds reject the string rather than read it as a number."""
    e = Suite("e1_h2", SPEC_LIT, G)
    seen = set()
    for su in suites:
        for c in su.cases:
            op = c["operation"]
            if op in seen or c["expected"]["status"] != "ok":
                continue
            path = _first_number(c["inputs"])
            if path is None:
                continue
            seen.add(op)
            inp = json.loads(json.dumps(c["inputs"]))
            node = inp
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = "NaN"
            where = "/".join(str(k) for k in path)
            e.add(op, inp, error="E_SCHEMA", cls=c["tolerance_class"], verified=["hand"],
                  tags=["stage_h", "e1", "non-finite-input"],
                  description=f"HR-12: NaN decimal string at {where} is E_SCHEMA (from {c['case_id']})")
    assert seen == {c["operation"] for su in suites for c in su.cases}, "an operation has no E1 case"
    # exec.sor.allocate has one Real input, `step` (STOCHASTIC_APPROX): F-2 applies, so NaN there is E_DOMAIN.
    e.add("exec.sor.allocate", dict(SOR, method="STOCHASTIC_APPROX", iterations=10, seed=1, step="NaN"),
          error="E_DOMAIN", cls="date_and_convention", verified=["hand"], tags=["stage_h", "e1", "non-finite-input"],
          description="F-2: NaN at step, the router's one Real input")
    return e


def dark_check(cid, exp):
    runs = exp.get("scenarios", [exp])
    for r in runs:
        items = r["fills"] if "markouts_bp" in json.dumps(r) else [r]
        for item in items:
            assert item["label"] == DARK_LABEL, cid


def build_w2b():
    out = []
    for name, spec in (("dark_h", SPEC_DARK), ("sor_h", SPEC_SOR)):
        s = Suite(name, spec, G)
        for cid, inp, exp in table(spec):
            if name == "dark_h":
                dark_check(cid, exp)
                op = "exec.sim.dark.markouts" if "config" not in json.dumps(inp) else "exec.sim.dark.run"
            else:
                op = "exec.sor.allocate"
                assert ("ranking" in exp) == (inp.get("ranking") is True), cid
            blind = cid not in NOT_BLIND_2B
            s.add(op, inp, exp, cls="date_and_convention",
                  verified=(["hand", SHAPE_ONLY_2B[cid]] if cid in SHAPE_ONLY_2B
                            else ["hand", BLIND_2B] if blind else ["hand"]),
                  tags=["stage_h", "simulated"],
                  description=f"{cid} from the spec table" + ("" if blind else "; not blind"))
            s.cases[-1]["case_id"] = cid
        errs = {
            "dark_h": [
                ("p_firm above 1", {"config": dict(DCFG, p_firm="1.5"), "events": []}, "E_DOMAIN"),
                ("min_qty above qty", {"config": DCFG, "events": [dict(DNEW, min_qty="200")]}, "E_DOMAIN"),
                ("non-positive qty", {"config": DCFG, "events": [dict(DNEW, qty="0")]}, "E_DOMAIN"),
            ],
            "sor_h": [
                ("S not positive", dict(SOR, S="0"), "E_DOMAIN"),
                ("negative penalty", dict(SOR, lambda_u="-1"), "E_DOMAIN"),
                ("empty sample", dict(SOR, lit_samples=[]), "E_INPUT"),
            ],
        }[name]
        first = {"dark_h": 8, "sor_h": 7}[name]
        for k, (desc, inp, code) in enumerate(errs):
            s.add("exec.sim.dark.run" if name == "dark_h" else "exec.sor.allocate", inp, error=code,
                  cls="date_and_convention", verified=["hand"], tags=["stage_h", "error"],
                  description=f"hand: {desc}")
            s.cases[-1]["case_id"] = f"{name}-{first + k:04d}"
        if name == "sor_h":
            add_sor_range(s)
        out.append(s)
    return out


SOR_SE = {"S": "4", "f": "0.3", "h": "0.5", "lambda_o": "1", "lambda_u": "1", "theta": "0.01", "report_se": True,
          "lit_samples": [["0"], ["1"], ["3"], ["4"]],
          "venues": [{"Q": "0", "as": "0", "kind": "LIT", "r": "0.2"},
                     {"as": "0.1", "kind": "DARK", "r": "0", "tail": ["0.7", "0.4", "0.2", "0"]}]}


def add_sor_range(s):
    """HR-57 boundary cases for the router, and one standard error under the binary64 rule of HR-40
    (sor.py `_se`). Hand: the theta term is theta (M + sum L + (S - A)_+) <= 30 theta here, so 10^33 keeps
    every step inside 36 digits and 10^35 does not (10 x 10^35 already at (0, 0)). The expected values
    of 0011 and 0012 are the Python build's output (cross-language agreement checks, not outside-checked):
    0011 = (0.5 + 0.3) 10 + 10^33 x 10 at (M, L) = (10, 0); 0012 pins expected_cost_se to 6 decimals."""
    big = dict(SOR, lit_samples=[["0"], ["2"]], lambda_u="4")
    rows = [
        ("theta 10^35: theta x 10 has 37 digits (HR-57)", dict(big, theta="1" + "0" * 35), None, "E_LIMIT"),
        ("theta 10^33: every step inside 36 digits", dict(big, theta="1" + "0" * 33),
         {"L": ["0"], "M": "10", "expected_cost": "1" + "0" * 33 + "8", "expected_fill": "10", "p_underfill": "0"},
         None),
        ("report_se: the binary64 standard error rule", SOR_SE,
         {"L": ["4", "3"], "M": "0", "expected_cost": "-0.18825", "expected_cost_se": "1.04492",
          "expected_fill": "2.825", "label": "simulated venues; router scored in simulation only",
          "p_underfill": "0.525"}, None),
    ]
    first = 10
    for k, (desc, inp, exp, code) in enumerate(rows):
        if code:
            s.add("exec.sor.allocate", inp, error=code, cls="date_and_convention", verified=["hand"],
                  tags=["stage_h", "error", "boundary"], description=f"hand: {desc}")
        else:
            s.add("exec.sor.allocate", inp, exp, cls="date_and_convention",
                  verified=["python build; agreement check across the four builds"],
                  tags=["stage_h", "boundary"], description=desc)
        s.cases[-1]["case_id"] = f"sor_h-{first + k:04d}"


DCFG = {"firm_delay": 0, "lot_size": "1", "p_firm": "1", "penalty_events": 2, "seed": 20261118,
        "tick_size": "0.01"}
DNEW = {"id": "B1", "kind": "FIRM", "op": "NEW", "qty": "100", "side": "BUY"}
SOR = {"S": "10", "f": "0.3", "h": "0.5", "lambda_o": "1", "lambda_u": "4", "theta": "0",
       "lit_samples": [["0"], ["2"]], "venues": [{"Q": "2", "as": "0", "kind": "LIT", "r": "0.2"}]}


def add_errors(s, name):
    """Error cases from the spec's Errors line (hand; not part of the blind lane)."""
    snap = {"type": "snapshot", "bids": [["100.0", "1.00000000"]], "asks": [], "checksum": None,
            "t": "2026-01-01T00:00:00Z"}
    ob = {"messages": [snap], "depth": 10, "price_decimals": 1, "qty_decimals": 8}
    lit = {"tick_size": "1", "lot_size": "1", "fee_schedule": {"maker_rebate": "0", "taker_fee": "0"}}
    buy = {"op": "NEW", "id": "B1", "trader": "T1", "side": "BUY", "type": "LIMIT", "price": "100", "qty": "10"}
    cases = {
        "ob_h": [
            ("depth not in the list", dict(ob, depth=20), "E_DOMAIN"),
            ("negative quantity", dict(ob, messages=[dict(snap, bids=[["100.0", "-1"]])]), "E_DOMAIN"),
            ("non-positive price", dict(ob, messages=[dict(snap, bids=[["0", "1"]])]), "E_DOMAIN"),
            ("price as a number, not a decimal string (HR-12)", dict(ob, messages=[dict(snap, bids=[[100.0, "1"]])]), "E_SCHEMA"),
            ("unknown message type", dict(ob, messages=[dict(snap, type="trade")]), "E_SCHEMA"),
        ],
        "lit_h": [
            ("price off the tick grid", dict(lit, events=[dict(buy, price="100.5")]), "E_DOMAIN"),
            ("non-positive quantity", dict(lit, events=[dict(buy, qty="0")]), "E_DOMAIN"),
            ("display_qty above quantity", dict(lit, events=[dict(buy, type="ICEBERG", display_qty="11")]), "E_DOMAIN"),
            ("duplicate id", dict(lit, events=[buy, dict(buy, price="99")]), "E_INPUT"),
        ],
    }[name]
    first = len(s.cases) + (2 if name == "ob_h" else 1)  # ob_h-0009 is retired (HR-41)
    for k, (desc, inp, code) in enumerate(cases):
        s.add(OPS[name], inp, error=code, cls="date_and_convention", verified=["hand"],
              tags=["stage_h", "error"], description=f"hand: {desc}")
        s.cases[-1]["case_id"] = f"{name}-{first + k:04d}"


def _cons(filled, resting, submitted):
    return {"cancelled": "0", "filled": filled, "rejected": "0", "resting": resting, "submitted": submitted}


def _lit_out(fills, bids, mbp_bids, cons, fees):
    return {"book": {"asks": [], "bids": bids}, "cancelled": [], "conservation": cons, "fees": fees,
            "fills": fills, "label": "simulated venue; not a real exchange",
            "mbp": {"asks": [], "bids": mbp_bids}, "rejects": []}


def _cross(price, qty):
    return [{"id": "S1", "op": "NEW", "price": price, "qty": qty, "side": "SELL", "trader": "T1", "type": "LIMIT"},
            {"id": "B1", "op": "NEW", "price": price, "qty": qty, "side": "BUY", "trader": "T2", "type": "LIMIT"}]


def add_boundaries(s, name):
    """HR-57/HR-58 range boundaries (hand). A value c * 10^-s is in range when |c| < 10^36 and s <= 36;
    an input string also needs s <= 18; outside is E_LIMIT in every language, never a rounded value.
    Expected outputs are written out by hand below; crc32 is recomputed with zlib per [KR-CRC]."""
    stats = {k: 0 for k in ("checkpoint_checked", "checkpoint_failed", "checksum_checked", "checksum_failed",
                            "crossed", "deletes_of_absent_level", "gaps", "level_changes", "locked",
                            "resyncs", "truncated_levels", "updates")}
    stats = dict(sorted({**stats, "messages": 1, "snapshots": 1}.items()))

    def snap(bids):
        return {"type": "snapshot", "bids": bids, "asks": [], "checksum": None, "t": "2026-01-01T00:00:00Z"}

    big = "123456789012345678.123456789012345678"  # 36 digits, 18 decimals: the largest input shape
    zeros = "1." + "0" * 21  # trailing zeros are not counted (21 written, value 1)
    fine = {"tick_size": "0.000000000000000001", "lot_size": "0.000000000000000001",
            "fee_schedule": {"maker_rebate": "0.0001", "taker_fee": "0.001"}}
    # 5^50 * 10^-18 times 2^50 * 10^-18 = 10^14 exactly; the raw coefficient product (10^50)
    # overflows 128 bits, so C++ and Rust must cancel factors of ten before multiplying (HR-58).
    p5, q2 = "88817841970012523.233890533447265625", "0.001125899906842624"
    assert Decimal(f"{5**50}E-18") == Decimal(p5) and Decimal(f"{2**50}E-18") == Decimal(q2)  # exact
    unit = {"tick_size": "1", "lot_size": "1", "fee_schedule": {"maker_rebate": "0", "taker_fee": "0"}}
    nines = "9" * 35  # notional 35 nines then 0: 36 digits, in range
    e30 = "1" + "0" * 30
    cases = {
        "ob_h": [
            ("36 digits at 18 decimals, quantity with 21 written zeros: in range (HR-57)",
             {"messages": [snap([[big, zeros]])], "depth": 10, "price_decimals": 18, "qty_decimals": 8},
             {"book": {"asks": [], "bids": [[big, zeros]]},
              "crc32": zlib.crc32((component(big, 18) + component(zeros, 8)).encode("ascii")) & 0xFFFFFFFF,
              "events": [], "stats": stats}, None),
            ("price with 19 decimals (HR-57)",
             {"messages": [snap([["0.0000000000000000001", "1"]])], "depth": 10, "price_decimals": 1,
              "qty_decimals": 8}, None, "E_LIMIT"),
            ("quantity with 37 digits (HR-57)",
             {"messages": [snap([["100.0", "1" + "0" * 36]])], "depth": 10, "price_decimals": 1,
              "qty_decimals": 8}, None, "E_LIMIT"),
        ],
        "lit_h": [
            ("product whose raw coefficients overflow 128 bits but whose value is in range (HR-58)",
             dict(fine, events=_cross(p5, q2)),
             _lit_out([{"maker_id": "S1", "price": p5, "qty": q2, "seq": 1, "taker_id": "B1"}], [], [],
                      {"B1": _cons(q2, "0", q2), "S1": _cons(q2, "0", q2)},
                      {"T1": "-10000000000", "T2": "100000000000"}), None),
            ("31-digit price on an 18-decimal tick grid (HR-58: grid checks never overflow)",
             dict(fine, events=_cross(e30, "1")[1:]),
             _lit_out([], [{"display_qty": "1", "hidden_qty": "0", "id": "B1", "price": e30, "seq": 1}],
                      [[e30, "1"]], {"B1": _cons("0", "1", "1")}, {}), None),
            ("notional of 36 digits: in range (HR-57)",
             dict(unit, events=_cross(nines, "10")),
             _lit_out([{"maker_id": "S1", "price": nines, "qty": "10", "seq": 1, "taker_id": "B1"}], [], [],
                      {"B1": _cons("10", "0", "10"), "S1": _cons("10", "0", "10")}, {"T1": "0", "T2": "0"}), None),
            ("notional of 37 digits (HR-57)", dict(unit, events=_cross("1" + "0" * 35, "10")), None, "E_LIMIT"),
            ("price with 19 decimals (HR-57)",
             dict(fine, events=_cross("100.0000000000000000001", "1")), None, "E_LIMIT"),
        ],
    }[name]
    first = int(s.cases[-1]["case_id"].split("-")[1]) + 1
    for k, (desc, inp, exp, code) in enumerate(cases):
        if code is None:
            s.add(OPS[name], inp, exp, cls="date_and_convention", verified=["hand"],
                  tags=["stage_h", "boundary"], description=f"hand: {desc}")
        else:
            s.add(OPS[name], inp, error=code, cls="date_and_convention", verified=["hand"],
                  tags=["stage_h", "error", "boundary"], description=f"hand: {desc}")
        s.cases[-1]["case_id"] = f"{name}-{first + k:04d}"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    for s in build():
        s.write()
    common.GOLDEN = keep


if __name__ == "__main__":
    main()
