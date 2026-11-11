"""Tutorial 8: SOFR and term curves, the joint solve, the turn, interpolation.

  uv run --project python python examples/tutorials/t8_multicurve.py         # Python
  python examples/tutorials/t8_multicurve.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-8-multicurve.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys
from datetime import date

from qf import runner

AS_OF = "2026-11-09"
SOFR = [("1M", 0.043), ("3M", 0.0425), ("6M", 0.0412), ("1Y", 0.039),
        ("2Y", 0.0365), ("3Y", 0.0355), ("5Y", 0.0352), ("10Y", 0.0364)]
TERM = [("DEPOSIT", 3, 0.0445), ("FRA", 3, 0.0432), ("FRA", 6, 0.0418),
        ("SWAP", 24, 0.0388), ("SWAP", 60, 0.0376), ("SWAP", 120, 0.0389)]
OIS_QUOTES = [{"tenor": t, "rate": r} for t, r in SOFR]
START, END = "2027-11-16", "2028-02-16"
PROBE = ["2028-05-15", "2033-11-15"]
METHODS = ("LOG_LINEAR_DF", "LINEAR_ZERO", "MONOTONE_CONVEX")


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return results


def curve(pillars, interpolation="LOG_LINEAR_DF"):
    return {"as_of": AS_OF, "interpolation": interpolation, "pillars": pillars}


def term_quote(kind, months, rate):
    key = "start_months" if kind == "FRA" else "months"
    return {"type": kind, key: months, "rate": rate}


def ois_bootstrap(case_id, method):
    return case(case_id, "rates.ois.bootstrap", {"convention": "SOFR", "as_of": AS_OF, "quotes": OIS_QUOTES,
                                                 "interpolation": method, "method": "SEQUENTIAL"})


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
    [disc] = batch(cli, [ois_bootstrap("t8-sofr", "LOG_LINEAR_DF")])
    disc_curve = curve(disc["outputs"]["pillars"])
    [proj] = batch(cli, [case("t8-term", "rates.projection.bootstrap", {
        "discount": disc_curve, "index": "USD-TERM-3M", "as_of": AS_OF,
        "quotes": [term_quote(*q) for q in TERM], "interpolation": "LOG_LINEAR_DF"})])
    proj_curve = curve(proj["outputs"]["pillars"])

    sofr_inst = [{"id": f"SOFR-{t}", "curve": "USD-SOFR", "type": "OIS", "tenor": t, "rate": r} for t, r in SOFR]
    term_inst = [{"id": f"T-{k}{m}", "curve": "USD-TERM-3M", **term_quote(k, m, r)} for k, m, r in TERM]
    turn_inst = [sofr_inst[0], {"id": "SOFR-2M", "curve": "USD-SOFR", "type": "OIS", "tenor": "2M",
                                "rate": 0.0428, "turn": True}, *sofr_inst[1:]]
    cases = [
        case("t8-fwd-ois", "rates.curve.forward", {"curve": disc_curve, "start": START, "end": END, "day_count": "ACT_360"}),
        case("t8-fwd-term", "rates.curve.forward", {"curve": proj_curve, "start": START, "end": END, "day_count": "ACT_360"}),
        case("t8-joint", "rates.curve.joint_solve", {"as_of": AS_OF, "curves": [
            {"name": "USD-SOFR", "type": "OIS", "convention": "SOFR", "interpolation": "LOG_LINEAR_DF"},
            {"name": "USD-TERM-3M", "type": "PROJECTION", "index": "USD-TERM-3M", "discount": "USD-SOFR",
             "interpolation": "LOG_LINEAR_DF"}], "instruments": sofr_inst + term_inst}),
        case("t8-zero-jac", "risk.curve.jacobian", {"as_of": AS_OF, "convention": "SOFR", "quotes": OIS_QUOTES,
                                                    "interpolation": "LOG_LINEAR_DF", "bump_bp": 1.0}),
        case("t8-turn", "rates.curve.joint_solve", {"as_of": AS_OF, "curves": [
            {"name": "USD-SOFR", "type": "OIS", "convention": "SOFR", "interpolation": "LOG_LINEAR_DF",
             "turns": [{"date": "2026-12-31"}]}], "instruments": turn_inst}),
        *[ois_bootstrap(f"t8-{m}", m) for m in METHODS],
    ]
    fwd_ois, fwd_term, joint, zero_jac, turned, *by_method = batch(cli, cases)
    f_ois, f_term = fwd_ois["outputs"]["forward"], fwd_term["outputs"]["forward"]
    err = max(disc["diagnostics"]["max_repricing_error"], proj["diagnostics"]["max_repricing_error"])
    print(f"SOFR curve {len(disc_curve['pillars'])} pillars, term curve {len(proj_curve['pillars'])}, "
          f"both reprice below 1e-13: {err < 1e-13}")
    print(f"SOFR 10Y discount factor {disc_curve['pillars'][-1]['discount_factor']:.12f}")
    print(f"TERM 10Y discount factor {proj_curve['pillars'][-1]['discount_factor']:.12f}")
    print(f"3M forward from {START}: SOFR {f_ois:.4%}  TERM {f_term:.4%}  basis {(f_term - f_ois) * 1e4:.2f} bp")

    solved = joint["outputs"]
    jac = solved["jacobian"]
    row = {u: k for k, u in enumerate(jac["unknowns"])}
    col = {q: k for k, q in enumerate(jac["quotes"])}

    def J(unknown, quote):
        return jac["matrix"][row[unknown]][col[quote]]

    term10, sofr10 = "USD-TERM-3M:pillar:2036-11-12", "USD-SOFR:pillar:2036-11-14"
    print(f"joint TERM 10Y discount factor {solved['curves'][1]['pillars'][-1]['discount_factor']:.12f}")
    print(f"J[TERM 10Y, T-SWAP120] {J(term10, 'T-SWAP120'):.4f}  J[TERM 10Y, SOFR-10Y] {J(term10, 'SOFR-10Y'):.4f}")
    print(f"J[SOFR 10Y, T-SWAP120] is exactly zero: {J(sofr10, 'T-SWAP120') == 0.0}")

    t10 = (date(2036, 11, 14) - date.fromisoformat(AS_OF)).days / 365
    print(f"dz(SOFR 10Y)/dq(SOFR-10Y): bump {zero_jac['outputs']['jacobian'][-1][-1]:.4f}  "
          f"joint -J/t {-J(sofr10, 'SOFR-10Y') / t10:.4f}")

    sens = turned["outputs"]["turn_sensitivity"][0]
    print(f"turn factor {turned['outputs']['turn_factors'][0]['factor']:.8f}")
    print(f"turn sensitivity: SOFR-1M zero {abs(sens[0]) < 1e-12}  SOFR-2M {sens[1]:.4f}  SOFR-3M {sens[2]:.4f}")

    batch_inspect = [case(f"t8-inspect-{m}", "rates.curve.inspect",
                          {"curve": curve(r["outputs"]["pillars"], m), "dates": PROBE})
                     for m, r in zip(METHODS, by_method)]
    for m, r, ins in zip(METHODS, by_method, batch(cli, batch_inspect)):
        fwd = ins["outputs"]["instantaneous_forwards"]
        print(f"{m:<16}10Y DF {r['outputs']['pillars'][-1]['discount_factor']:.6f}  "
              f"fwd {PROBE[0]} {fwd[0]:.4%}  fwd {PROBE[1]} {fwd[1]:.4%}")


if __name__ == "__main__":
    main(sys.argv[1:])
