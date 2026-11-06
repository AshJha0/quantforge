"""Data and solution tables for exercises EX-001 to EX-003. Numbers come from the oracle, never from an implementation."""
from datetime import date

import mpmath as mp

from qf_oracle.common import ROOT
from qf_oracle.dates import yf

OUT = ROOT / "program" / "exercises"
PAIRS = [("2024-01-01", "2024-07-01"), ("2023-12-31", "2024-01-01"), ("2024-02-28", "2024-03-01"), ("2023-02-28", "2023-03-01"),
         ("2024-01-31", "2024-03-31"), ("2003-11-01", "2004-05-01"), ("2024-02-29", "2025-02-28")]
CONVS = ["ACT_360", "ACT_365F", "ACT_ACT_ISDA", "THIRTY_360_BOND", "THIRTY_E_360"]
RATES = [(0.05, 2.0), (0.0, 5.0), (-0.005, 3.0), (0.25, 0.5)]
ROOTS = [("cubic_wallis", 2, 3, lambda x: x ** 3 - 2 * x - 5), ("cos_minus_x", 0, 1, lambda x: mp.cos(x) - x), ("exp_minus_two", 0, 2, lambda x: mp.exp(x) - 2)]


def stage_b():
    import numpy as np

    from gen_stage_b import AS_OF, SONIA_Q, dv01_replay, solve_l1
    from qf_oracle.rates import bootstrap_ois, ois_legs, ois_par, ois_periods
    D = OUT / "data"
    Sn = OUT / "solutions"
    rows = [(1.28, 0.04, 0.037, 1.0), (1.28, 0.04, 0.04, 1.0), (150.0, 0.045, 0.005, 0.5)]
    (D / "ex-005-fx.csv").write_text("spot,quote_rate,base_rate,t\n" + "".join(f"{a},{b},{c},{d}\n" for a, b, c, d in rows), newline="\n")
    t = ["# Solution: FX forward", "", "Synthetic data. Continuous rates, `F = S exp((r_quote - r_base) t)`. Values from `oracle/python/gen_exercises.py`.", "", "| Spot | Quote rate | Base rate | t | Forward | Forward minus spot |", "|---|---|---|---|---|---|"]
    for a, b, c, d in rows:
        F = float(a * mp.exp((mp.mpf(b) - c) * d))
        t.append(f"| {a} | {b} | {c} | {d} | {F:.8f} | {F - a:.8f} |")
    t += ["", "## Answers", "", "1. Quoting USDGBP in place of GBPUSD inverts the rate, and swaps which curve is on top. Name base and quote in the type.", "2. With equal rates the forward equals spot, as in row 2.", "3. As a signed number of pips, with `pip` from the pair's record: `(F - S)/pip`. Never as a bare difference.", "", "Explanation: `specifications/02-curves/fx.md`.", ""]
    (Sn / "EX-005.md").write_text("\n".join(t), encoding="utf-8", newline="\n")

    (D / "ex-006-quotes.csv").write_text("tenor,rate\n" + "".join(f"{a},{b}\n" for a, b in SONIA_Q), newline="\n")
    cv, dfs, per = bootstrap_ois("SONIA", AS_OF, SONIA_Q)
    t = ["# Solution: curve bootstrap", "", f"Synthetic SONIA quotes, as of {AS_OF}, log-linear discount factors. Checked against QuantLib within 5e-12.", "", "| Tenor | Pillar | Discount factor | Repricing error |", "|---|---|---|---|"]
    for (ten, r), v, p in zip(SONIA_Q, dfs, per):
        t.append(f"| {ten} | {p[-1][2]} | {v:.10f} | {abs(ois_par('SONIA', p, cv) - r):.1e} |")
    t += ["", "## Answers", "", "1. Then the right answer is known, so an error in the build can be told from noise in the data.", "2. Reprice each input from the finished curve, and report model minus quote, per instrument and as a maximum.", "3. More pillars than quotes, or two quotes that land on one pillar. Then no single curve fits, and the fit must add a rule such as smoothness.", "", "Explanation: `specifications/02-curves/ois-curves.md`.", ""]
    (Sn / "EX-006.md").write_text("\n".join(t), encoding="utf-8", newline="\n")

    tr = {"tenor": "5Y", "fixed_rate": 0.034, "notional": 1e6, "side": "PAY"}
    par, keys = dv01_replay("SONIA", SONIA_Q, "LOG_LINEAR_DF", tr)
    a, _ = ois_legs("SONIA", ois_periods("SONIA", AS_OF, "5Y"), cv)
    t = ["# Solution: DV01", "", "Synthetic. PAY fixed 3.4% on a 5Y SONIA swap, notional 1,000,000, the quotes of EX-006.", "", f"Parallel DV01: {par:.4f}. Approximation `notional x annuity x 1 bp`: {1e6 * a * 1e-4:.4f}, close because the swap is near par.", f"Sum of key rates: {sum(keys):.4f}.", "", "| Tenor | Key-rate DV01 |", "|---|---|"]
    t += [f"| {q[0]} | {k:.4f} |" for q, k in zip(SONIA_Q, keys)]
    t += ["", "## Answers", "", "1. Here DV01 is the change in PV for rates up 1 bp, signed. A payer gains, so it is positive.", "2. Too large a bump picks up convexity; too small a bump drowns in solver and rounding noise.", "3. Parallel moves all quotes at once. Key-rate moves one, showing where on the curve the risk sits. They sum to parallel to first order only.", "", "Explanation: `specifications/06-risk/rates-sensitivities.md`.", ""]
    (Sn / "EX-008.md").write_text("\n".join(t), encoding="utf-8", newline="\n")

    A = [[1.0, 0.2], [0.3, 1.0], [0.0, 0.3]]
    b = [10.0, -4.0, 6.0]
    (D / "ex-009-hedge.csv").write_text("a1,a2,b\n" + "".join(f"{r[0]},{r[1]},{v}\n" for r, v in zip(A, b)), newline="\n")
    t = ["# Solution: hedge with cost", "", "Synthetic. Unit weights, costs 1 per unit on each instrument. Exact by enumeration, and checked against the first-order conditions.", "", "| lambda | x1 | x2 | Residual norm | Objective |", "|---|---|---|---|---|"]
    for lam in (0.0, 2.0, 10.0, 40.0):
        x, r, o = solve_l1(A, b, [1.0] * 3, [1.0, 1.0], lam)
        t.append(f"| {lam} | {x[0]:.6f} | {x[1]:.6f} | {float(np.linalg.norm(r)):.6f} | {float(o):.6f} |")
    t += ["", "## Answers", "", "1. The stage B form has no hard constraints, so it is always feasible. With constraints in stage I, a phase-one solve or an empty active set shows infeasibility.", "2. A cost penalty shrinks positions, and can set one to exactly zero. Ridge regularisation shrinks without zeros.", "3. As the residual per risk factor, in the same units as the risk, beside the unhedged figure.", "", "Explanation: `specifications/08-hedging/stage-b-hedges.md`.", ""]
    (Sn / "EX-009.md").write_text("\n".join(t), encoding="utf-8", newline="\n")


def main():
    (OUT / "data").mkdir(exist_ok=True)
    (OUT / "solutions").mkdir(exist_ok=True)
    (OUT / "data" / "ex-001-dates.csv").write_text("start,end\n" + "".join(f"{a},{b}\n" for a, b in PAIRS), newline="\n")
    (OUT / "data" / "ex-002-rates.csv").write_text("rate,t\n" + "".join(f"{r},{t}\n" for r, t in RATES), newline="\n")
    (OUT / "data" / "ex-003-functions.csv").write_text("function,a,b\n" + "".join(f"{n},{a},{b}\n" for n, a, b, _ in ROOTS), newline="\n")

    t = ["# Solution: day counts", "", "Values from `oracle/python/gen_exercises.py`, exact rationals rounded once.", "",
         "| Start | End | " + " | ".join(CONVS) + " |", "|---|---|" + "---|" * len(CONVS)]
    for a, b in PAIRS:
        vals = [f"{float(yf(c, date.fromisoformat(a), date.fromisoformat(b))):.10f}" for c in CONVS]
        t.append(f"| {a} | {b} | " + " | ".join(vals) + " |")
    t += ["", "## Answers", "",
          "1. ACT/365F always divides by 365, so a leap year gives slightly more than 1. ACT/ACT ISDA divides each part of the period by the length of its own year, so a whole calendar year is exactly 1.",
          "2. The variants differ at month ends: see 2024-01-31 to 2024-03-31 and the February rows. \"30/360\" alone does not say which result is right.",
          "3. Test a pair either side of 31 December, as in row 2, and a pair spanning a leap year and a normal year, as in row 6. Compare with a hand calculation. Include `start = end` and a reversed pair, which must give `E_DATE_ORDER`.",
          "", "Explanation: `specifications/01-core/daycount.md`.", ""]
    (OUT / "solutions" / "EX-001.md").write_text("\n".join(t), encoding="utf-8", newline="\n")

    t = ["# Solution: discount factors", "", "Values from `oracle/python/gen_exercises.py`, mpmath at 50 digits.", "",
         "| Rate | t | Simple | Annual | Semi-annual | Continuous |", "|---|---|---|---|---|---|"]
    for r, x in RATES:
        R, X = mp.mpf(r), mp.mpf(x)
        v = [1 / (1 + R * X), (1 + R) ** -X, (1 + R / 2) ** (-2 * X), mp.exp(-R * X)]
        t.append(f"| {r} | {x} | " + " | ".join(f"{float(a):.12f}" for a in v) + " |")
    lim = [float(12 * 0 + (1 + mp.mpf("0.05") / n) ** (-n * 2)) for n in (1, 12, 365, 100000)]
    t += ["", f"Limit check at rate 0.05, t = 2: frequency 1, 12, 365 and 100000 give {lim[0]:.10f}, {lim[1]:.10f}, {lim[2]:.10f}, {lim[3]:.10f}, tending to exp(-0.1) = {float(mp.exp(-0.1)):.10f}.", "",
          "Inverse identity: converting a rate to a discount factor and back returns the rate, for every row with `t > 0`.", "", "## Answers", "",
          "1. A negative rate gives a discount factor above 1: money later is worth more than money now. It is valid; only `1 + r t <= 0` or `1 + r/n <= 0` is an error.",
          "2. Decimals at every boundary: 0.05 means 5%.",
          "3. Convert once, at the edge, and name the unit in the field or type. One basis point is 0.0001. Never pass a bare number whose unit depends on who wrote it.",
          "", "Explanation: `specifications/01-core/compounding.md`.", ""]
    (OUT / "solutions" / "EX-002.md").write_text("\n".join(t), encoding="utf-8", newline="\n")

    t = ["# Solution: root finding", "", "Values from `oracle/python/gen_exercises.py`, mpmath at 50 digits. Bisection steps are for `x_tol = 1e-12`.", "",
         "| Function | Bracket | Root | Bisection steps |", "|---|---|---|---|"]
    for n, a, b, fn in ROOTS:
        root = mp.findroot(fn, (mp.mpf(a), mp.mpf(b)), solver="anderson", tol=1e-40, verify=False)
        steps = int(mp.ceil(mp.log((b - a) / mp.mpf("1e-12"), 2))) - 1
        t.append(f"| `{n}` | [{a}, {b}] | {float(root):.15f} | about {steps} |")
    t += ["", "## Answers", "",
          "1. Newton can diverge or cycle when the derivative is near zero, when the start is far from the root, or near a function with a flat region. `x^2 + 1` from 0 stops at once on a zero derivative.",
          "2. A bracket guarantees a root stays inside. When a Newton step leaves it, the midpoint replaces the step, so progress is never lost.",
          "3. Stop with `E_NON_FINITE`. A NaN compares false with everything, so carrying on makes the sign logic silently wrong.",
          "", "Explanation: `specifications/01-core/root-finders.md`.", ""]
    (OUT / "solutions" / "EX-003.md").write_text("\n".join(t), encoding="utf-8", newline="\n")
    stage_b()


if __name__ == "__main__":
    main()
