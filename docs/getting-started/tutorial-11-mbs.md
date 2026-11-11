# Tutorial 11: mortgage-backed securities

The plain idea: a pass-through [MBS](../../GLOSSARY.md#stage-d-curves-and-fixed-income) passes the payments on a pool of mortgages to the investor, less a servicing and guarantee fee. Borrowers pay interest and scheduled principal every month, and some of them repay early, when they move house or refinance. Those prepayments make the cash flows uncertain: the faster the pool prepays, the sooner you get your money back. So an MBS price depends on two things, the yield you discount at and the prepayment speed you assume, and you look at both.

This tutorial projects a pool's cash flows under two prepayment assumptions (a flat CPR and the PSA ramp), prices the pool with its modified duration and weighted average life, then reprices it at bumped yields and bumped speeds. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 10 to 15 minutes. The pool is synthetic, the one in golden case `mbs_d-0005`; it is not market data.

One thing this tutorial does not do: option-adjusted spread (OAS). OAS needs a rate model and a prepayment model that depends on rates, so that cash flows change along each simulated rate path. QuantForge has no OAS operation; `specifications/name-map.json` lists only `mbs.cashflows` and `mbs.price`, and the prepayment speed is an input that does not move with rates. What you get here is price sensitivity to yield and, separately, to speed.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [tutorial 1](tutorial-1-swap.md).
- Knowing what a yield and a level-payment mortgage are.

Three terms, all in the [glossary](../../GLOSSARY.md#stage-d-curves-and-fixed-income): CPR, the conditional prepayment rate, is the fraction of the remaining balance prepaid over a year; SMM, the single monthly mortality, is the same per month, `1 − (1 − CPR)^(1/12)`; PSA is the standard ramp, CPR rising 0.2% a month with loan age to 6% at month 30, then flat, scaled by the speed (200 PSA is twice that). WAL, weighted average life, is the average time to repayment of principal, in years.

## Step 1: Python

```bash
uv sync --locked --project python
```

The script `examples/tutorials/t11_mbs.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t11_mbs.py -->
```python
"""Tutorial 11: prepayment (PSA against CPR), pass-through cash flows,
price, modified duration and WAL, and price at bumped yields and speeds.

  uv run --project python python examples/tutorials/t11_mbs.py         # Python
  python examples/tutorials/t11_mbs.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-11-mbs.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys

from qf import runner


def pool(model, speed):
    key = "speed" if model == "PSA" else "rate"
    return {"balance": 2_500_000.0, "wac": 0.0575, "net_coupon": 0.0525, "wam": 357, "age": 3,
            "prepayment": {"model": model, key: speed}}


def case(case_id, operation, inputs):
    return {"schema_version": "1.0", "case_id": case_id, "operation": operation, "inputs": inputs}


def price_case(case_id, model, speed, y):
    return case(case_id, "mbs.price", {"pool": pool(model, speed), "yield": y, "delay_days": 24})


def batch(run, cases):
    results = run(cases)
    for r in results:
        if r["status"] != "ok":
            raise SystemExit(f"{r['case_id']}: {r['error']}")
    return [r["outputs"] for r in results]


def main(cli):
    cli = runner(cli)  # the Python package with no arguments, else that build's batch command
    models = (("PSA", 100.0), ("CPR", 0.06))
    flows = batch(cli, [case(f"t11-flows-{m}", "mbs.cashflows", {"pool": pool(m, s)}) for m, s in models])
    for (model, speed), f in zip(models, flows):
        print(f"{model} {speed:g}: prepayment month 1 {f['prepayment'][0]:.2f}, "
              f"month 27 {f['prepayment'][26]:.2f}, WAL {f['wal']:.4f}")
    yields, speeds = (0.054, 0.064), (50.0, 200.0, 300.0)
    base, *rest = batch(cli, [price_case("t11-base", "PSA", 100.0, 0.059),
                              *(price_case(f"t11-y{y}", "PSA", 100.0, y) for y in yields),
                              *(price_case(f"t11-s{s}", "PSA", s, 0.059) for s in speeds)])
    print(f"price {base['price']:.6f} modified duration {base['modified_duration']:.6f} WAL {base['wal']:.6f}")
    for y, out in zip(yields, rest[:2]):
        print(f"yield {y:.3f}: price {out['price']:.6f}")
    for s, out in zip(speeds, rest[2:]):
        print(f"PSA {s:g}: price {out['price']:.6f} modified duration {out['modified_duration']:.6f} "
              f"WAL {out['wal']:.6f}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t11_mbs.py
```

Real output, 2026-11-11, Windows 11:

<!-- tutorial:expect -->
```text
PSA 100: prepayment month 1 1671.03, month 27 11587.64, WAL 11.0928
CPR 0.06: prepayment month 1 12843.87, month 27 10900.87, WAL 10.4804
price 94.902791 modified duration 7.387705 WAL 11.092817
yield 0.054: price 98.520632
yield 0.064: price 91.503514
PSA 50: price 93.977849 modified duration 8.854226 WAL 14.233421
PSA 200: price 96.097033 modified duration 5.516232 WAL 7.428231
PSA 300: price 96.809591 modified duration 4.407472 WAL 5.503413
```

### Reading the numbers

- **PSA against CPR, month 1.** The pool is 3 months old, so month 1 is loan age 4 and 100 PSA gives CPR = 4/30 × 6% = 0.8%, SMM = 1 − 0.992^(1/12) ≈ 0.000669. The balance after scheduled principal is just under 2.5 million, so prepayment ≈ 0.000669 × 2.497 million ≈ 1,671. At a flat 6% CPR, SMM ≈ 0.005143, and 0.005143 × 2.497 million ≈ 12,844.
- **Month 27.** Loan age 30: the PSA ramp has reached 6% CPR, the same rate as the flat model. PSA's prepayment is larger (11,588 against 10,901) only because more balance is left: the flat model has been prepaying at 6% since month 1.
- **WAL.** Faster early prepayment returns principal sooner: 10.48 years at 6% CPR against 11.09 at 100 PSA.
- **Price.** 94.90 per 100 of balance, below par, because the net coupon (5.25%) is below the yield (5.90%). This matches golden case `mbs_d-0005` (94.90279148565978).
- **Modified duration against a bump.** A 50bp move each way gives (98.520632 − 91.503514)/(2 × 94.902791 × 0.005) = 7.017118/0.949028 = 7.394, close to the analytic 7.388; the gap is convexity over a finite bump.
- **Speed.** At a discount price, faster prepayment hands back par sooner, so the price rises with speed: 93.98 at 50 PSA, 94.90 at 100, 96.10 at 200, 96.81 at 300. WAL and duration shorten with it: from 14.23 to 5.50 years and from 8.85 to 4.41. Each step adds less, because a pool can only be repaid once.

### The formal statement, checked against the spec

From `specifications/04-pricing/mbs.md`. Month `k = 1 .. wam`, beginning balance `B_k`, `r = wac/12`, `n = wam − k + 1`:

- `CPR_k = rate` for CPR, or `min((age + k)/30, 1) × 0.06 × speed/100` for PSA; `SMM_k = 1 − (1 − CPR_k)^(1/12)`.
- Scheduled payment `B_k r / (1 − (1 + r)^(−n))`; scheduled principal is that less `B_k r`; in the last month it is the whole balance. Prepayment `SMM_k (B_k − scheduled principal)`. Interest to the investor `B_k net_coupon/12`: the gross WAC sets amortisation, the net coupon sets the coupon.
- `wal = Σ (k/12)(scheduled_k + prepayment_k) / balance`.
- `mbs.price`: `CF_k = interest + scheduled + prepayment`, discounted at `v^(t_k)` with `v = 1/(1 + y/12)` (monthly compounding) and `t_k = k + delay_days/30`. `price = 100 Σ CF_k v^(t_k) / balance`, `modified_duration = Σ (t_k/12) CF_k v^(t_k + 1) / Σ CF_k v^(t_k)`.

No calendar enters: months are equal, and the delay is counted in 30-day months. The price is per 100 of the current balance, and as the spec defines it, there is no accrued interest to strip, so it is the full price at the start of month 1.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t11_mbs.py` sends the same cases (two `mbs.cashflows`, six `mbs.price`) to whichever CLI you name and prints the same lines. Given a command line, the same script sends each case to that build's `batch` command (`specifications/cli-contract.md`) instead of the Python package.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t11_mbs.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t11_mbs.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t11_mbs.py cpp26/build/quantforge
```

Each prints the eight lines of step 1, digit for digit at the precision shown. The full check is `python conformance/runner/runner.py --impl rust --suite mbs_d`.

## For practitioners

- **Static speed, no OAS.** The speed here is fixed whatever the yield, so modified duration is a static duration. Desk effective duration lets prepayments speed up when rates fall (refinancing), which shortens the bond as rates fall and gives the negative convexity MBS are known for. You can see the two ingredients separately here (the yield bump and the speed bump) but nothing joins them. OAS, which needs an interest-rate model and a rate-dependent prepayment model, is not in QuantForge.
- **Monthly compounding and delay.** The yield is monthly compounded, as MBS cash-flow yields are quoted; compare with a bond-equivalent yield only after converting. The 24 days in this example are the actual delay of a UMBS pass-through, issued by Fannie Mae or, since June 2019, by Freddie Mac: a 55-day stated delay, paid on the 25th of the month after the accrual month. Ginnie Mae I pays on the 15th (45-day stated, 14 days actual), Ginnie Mae II on the 20th (50-day stated, 19 actual), and legacy Freddie Mac Gold PCs, no longer issued, on the 15th (45-day stated, 14 actual). The stated delays and payment days are from SIFMA's *Uniform Practices*, chapter 3 (opened 2026-11-11). The stated delay counts from the first day of the accrual month and the actual delay from its end; SIFMA gives the stated figures, and the actual ones follow from the payment day. The spec counts the delay as `delay_days/30` months.
- **Simplified PSA.** The ramp follows the standard benchmark (0.2% CPR per month of age to 6% at month 30). Real pools are pools of loans with different rates, ages and balances; here one WAC and one age stand for the pool.
- **No settlement date.** Pricing is as of the start of month 1. A desk prices to a settlement date with accrued interest and a clean price; adjust for that before comparing.

## Common mistakes

- Giving a CPR as a percentage (6) instead of a fraction (0.06). The spec requires `rate` in [0, 1); 6 is `E_DOMAIN`.
- Forgetting `age`. A seasoned pool starts further along the PSA ramp; with `age` 0 the first months prepay more slowly.
- Reading a higher price at a faster speed as always true. It holds for a discount pool like this one. For a premium pool (coupon above yield) faster prepayment lowers the price; try a yield of 0.045.
- Treating modified duration as a hedge ratio for a real MBS. Without rate-dependent prepayment it overstates duration when rates fall.

## What you just did

You projected a pass-through pool's cash flows under 100 PSA and 6% CPR, priced it at 94.902791 with modified duration 7.388 and WAL 11.09 years, checked the duration with a ±50bp bump, and saw the price move from 93.98 to 96.81 as the speed went from 50 to 300 PSA. Four implementations printed the same lines.

## Try next

- Set the yield to 0.045, below the net coupon, and rerun the speed lines: the price now falls as speed rises.
- Set `age` to 30 and compare PSA 100 with CPR 0.06: the cash flows are the same.
- Plot `flows["balance"]` for 50, 100 and 300 PSA.
- The [Cookbook recipe](../../COOKBOOK.md#price-a-pass-through-mbs) prices golden case `mbs_d-0004` through the CLI.

## References and further reading

- Our spec: `specifications/04-pricing/mbs.md`; golden suite `datasets/golden/stage_d/mbs_d.json`.
- [LEARN: curves and fixed income](../../LEARN.md#curves-and-fixed-income) and [stage D status](../../LEARN.md#stage-d-curves-and-fixed-income); [Glossary, stage D terms](../../GLOSSARY.md#stage-d-curves-and-fixed-income) (CPR, SMM, PSA, MBS, WAL).
- SIFMA, *Uniform Practices for the Clearance and Settlement of Mortgage-Backed Securities and Other Related Securities*, Chapter SF, *Standard Formulas*: the PSA benchmark, SMM from CPR, level-pay amortisation. The spec marks it not opened. No stable public link: the SIFMA page we tried returned 404.
- SIFMA, *Uniform Practices for the Clearance and Settlement of Mortgage-Backed Securities and Other Related Securities*, 2019 edition, chapter 3, *Mortgage-Backed Securities*: <https://www.sifma.org/wp-content/uploads/2017/08/ch03.pdf>. Opened 2026-11-11: it gives the 55-day delay paid on the 25th for Fannie Mae and Freddie Mac UMBS, 45 days on the 15th for Ginnie Mae I and for Gold PCs (issuance ceased 3 June 2019), and 50 days on the 20th for Ginnie Mae II.
- Fabozzi, F. J. (ed.), *The Handbook of Mortgage-Backed Securities*, 7th ed., Oxford University Press, 2016. The spec marks it not opened; no stable link.
- QuantLib has no pass-through MBS pricer to cross-check against, and the spec runs no outside library: the goldens are analytic.

Links checked 2026-11-11.
