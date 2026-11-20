# Tutorial 53: when should a model be recalibrated?

<!-- tutorial:only python -->

The plain idea: recalibrating on every tick wastes effort and adds noise; never recalibrating lets a model drift. A trigger compares how far a monitored input has moved since the last calibration with how much it normally moves, and fires only when the move is too large to be noise at a stated false-alarm rate.

You will run the trigger on five golden cases, see that a move exactly at the threshold does not fire, and check the acceptance simulation's fire counts against their binomial interval. Budget 10 minutes.

<p class="note">Stage K. The operation <code>calib.trigger.check</code> is merged to <code>main</code> in all four builds (2026-11-19; not in a tag) (spec <code>specifications/03-calibration/recalibration-triggers.md</code> 1.1.0, rulings KR-6, KR-13, and from the different-model audit KR-232 and KR-233). Acceptance evidence files: Python and Java; C++ and Rust run the same properties in their unit tests without writing evidence files (<code>program/STAGE_K_W1_HANDOVER.md</code>). Outside share: see <code>oracle/OUTSIDE_SHARES.md</code>; the blind matches of trig_k-0001 to 0005 now cover <code>nominal_rate</code>, not the redefined <code>false_alarm_rate</code> (KR-232). Step 1 restates the rule with the standard library on the golden inputs; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. `c_1..c_n` are past one-day changes of the monitored input; `sigma` is their sample standard deviation (divisor `n - 1`). `x_ref` is the value at the last calibration, `x_now` the value today, `d` the days since. The **level** `k` sets the **false-alarm rate** `alpha`, the share of pure-noise days on which the trigger would still fire. Because `sigma` is estimated from the window, `alpha` is a Student-t tail with `n - 1` degrees of freedom (`false_alarm_rate`, KR-232); the normal tail `2 (1 - Phi(k))`, which would hold only if `sigma` were known, is reported as `nominal_rate`.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: five cases and the simulation's interval

```python
# The recalibration trigger of calib.trigger.check, goldens trig_k-0001 to 0005, restated with the standard library.
import math
import statistics


def t_two_sided(k, nu):  # P(|T_nu| > k) by the finite sums of Abramowitz and Stegun 26.7.3 and 26.7.4
    th = math.atan(k / math.sqrt(nu))
    c, s = math.cos(th), math.sin(th)
    if nu % 2:
        term, tot = c, (c if nu > 1 else 0.0)
        for j in range(3, nu - 1, 2):
            term *= (j - 1) / j * c * c
            tot += term
        return 1 - 2 / math.pi * (th + s * tot)
    term, tot = 1.0, 1.0
    for j in range(2, nu - 1, 2):
        term *= (j - 1) / j * c * c
        tot += term
    return 1 - s * tot


def trigger(changes, x_ref, x_now, days, k):
    sigma = statistics.stdev(changes)  # n - 1 in the denominator
    threshold = k * sigma * math.sqrt(days)
    alpha = t_two_sided(k, len(changes) - 1)  # false_alarm_rate (KR-232)
    nominal = math.erfc(k / math.sqrt(2))  # nominal_rate, 2 (1 - Phi(k))
    return abs(x_now - x_ref) > threshold, sigma, threshold, alpha, nominal


a, b = [1, -1, 1, -1], [0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0]
for case, args, fire in (("trig_k-0001", (a, 100, 105, 1, 3), True), ("trig_k-0002", (a, 100, 102, 1, 3), False),
                         ("trig_k-0003", (a, 100, 105, 4, 3), False), ("trig_k-0004", (b, 0, 2.5, 1, 2.5), False),
                         ("trig_k-0005", (b, 0, -2.5000001, 1, 2.5), True)):
    f, s, th, alpha, nominal = trigger(*args)
    assert f == fire, case
    print(f"{case} move {abs(args[2] - args[1]):.8g} sigma {s:.10f} threshold {th:.10f} fire {f} alpha {alpha:.6f} nominal {nominal:.6f}")


def binom_interval(n, p, level=0.99):  # smallest a, b with cdf(a) >= (1-level)/2 and cdf(b) >= (1+level)/2
    lo, hi, cdf, a = (1 - level) / 2, (1 + level) / 2, 0.0, None
    for x in range(n + 1):
        cdf += math.exp(math.lgamma(n + 1) - math.lgamma(x + 1) - math.lgamma(n - x + 1) + x * math.log(p) + (n - x) * math.log1p(-p))
        if a is None and cdf >= lo:
            a = x
        if cdf >= hi:
            return a, x


lo, hi = binom_interval(100_000, 0.0030306)
print(f"99% interval for 100,000 noise paths at rate 0.0030306: [{lo}, {hi}]; Python 291 and Java 287 fires inside: {lo <= 291 <= hi and lo <= 287 <= hi}")
```

Output (CI checks that Step 2 prints these lines):

<!-- tutorial:expect -->
```text
trig_k-0001 move 5 sigma 1.1547005384 threshold 3.4641016151 fire True alpha 0.057669 nominal 0.002700
trig_k-0002 move 2 sigma 1.1547005384 threshold 3.4641016151 fire False alpha 0.057669 nominal 0.002700
trig_k-0003 move 5 sigma 1.1547005384 threshold 6.9282032303 fire False alpha 0.057669 nominal 0.002700
trig_k-0004 move 2.5 sigma 1.0000000000 threshold 2.5000000000 fire False alpha 0.040992 nominal 0.012419
trig_k-0005 move 2.5000001 sigma 1.0000000000 threshold 2.5000000000 fire True alpha 0.040992 nominal 0.012419
99% interval for 100,000 noise paths at rate 0.0030306: [259, 349]; Python 291 and Java 287 fires inside: True
```

### Reading the numbers

- **A planted move and noise.** Changes `+1, -1, +1, -1` have mean 0 and `sigma = sqrt(4/3) = 2/sqrt 3 = 1.1547`. At `k = 3` the threshold is 3.4641: a move of 5 fires, a move of 2 does not (`trig_k-0001`, `0002`).
- **Time widens the band.** Four days after calibration the threshold is `3 x 1.1547 x sqrt 4 = 6.928`, so the same move of 5 no longer fires (`trig_k-0003`): over four days a random walk with that scale moves that far often enough.
- **Equality does not fire.** With `sigma` exactly 1 and `k = 2.5`, a move of exactly 2.5 stays quiet and 2.5000001 fires (`trig_k-0004`, `0005`, ruling KR-13: "strictly greater").
- **The false-alarm rate.** With four changes `sigma` is itself noisy, so `alpha = P(abs(T_3) > 3) = 0.0577` at `k = 3` (`trig_k-0001`), and with eight changes `P(abs(T_7) > 2.5) = 0.0410` (`trig_k-0004`). The normal tail `2 (1 - Phi(k))` gives 0.0027 and 0.0124; it is kept as `nominal_rate` and is 21 times too low for the four-change window. The audit measured 22,977 fires in 400,000 simulated noise paths at n = 4, k = 3, a rate of 5.7% (KA-A4, measured; spec 1.1.0). Outside checks: SciPy `2*norm.sf(k)` for `nominal_rate` and `scipy.stats.t.sf` for `false_alarm_rate` (read from the spec).
- **The 1.0.0 simulation (kept as history).** In 100,000 noise-only paths (window 250, `k = 3`, `d = 1`) the Python build fired 291 times and the Java build 287 (measured by the k-w1 lane). With `sigma` estimated from 250 points the expected rate is a little above 0.0027: the spec centres the test on the Student-t predictive rate 0.0030306 (computed by SciPy). Both counts sit inside its 99% binomial interval [259, 349], which the block above recomputes. A planted 6-sigma move fired on all 100,000 paths in both builds. At a window of 250 the two rates are close, which is why this test did not catch the fault; spec 1.1.0 replaces it with simulations at n = 2, 4, 30 and 250 centred on the operation's own `false_alarm_rate`.

### The formal statement, checked against the spec

From `specifications/03-calibration/recalibration-triggers.md` 1.1.0 (rulings KR-6, KR-13, KR-232, KR-233; read 2026-11-20).

- `sigma = sqrt(sum (c_i - c_bar)^2 / (n - 1))`, `n >= 2`. The trigger fires iff `|x_now - x_ref| > k sigma sqrt(d)`, `d >= 1`, `k > 0`. Under independent normal changes with that scale and `sigma` known, the rate is `2 (1 - Phi(k))` (`nominal_rate`); with `sigma` estimated from the window it is `P(abs(T_(n-1)) > k)` (`false_alarm_rate`, KR-232, compared in class `tail_probability`, 1e-11 relative). Page (1954) is cited for the control-chart idea (not opened, recalled in the spec).
- Errors: one change only is `E_INPUT` (`trig_k-0006`); `k = 0` is `E_DOMAIN` (`trig_k-0007`); constant changes, or any window whose binary64 `sigma` is at most `2^-26 max abs(c_i)`, give `E_DOMAIN` (`trig_k-0008`; KR-233, goldens trig_k-0017 to 0021); more than 100,000 changes `E_LIMIT`.
- Acceptance 1.0.0 (fixed before the run): the goldens in four languages, sigma and threshold to 1e-14 relative; the noise simulation inside the 99% interval; a planted 6-sigma move firing on at least 99.9% of paths. Evidence: `program/stage_k_w1/acceptance_python.json` and `acceptance_java.jsonl`, key `trigger_simulation`. C++ and Rust run the same simulation in their unit tests without writing an evidence file. `false_alarm_rate` is computed as `2 Phi(-k)` with a tail-accurate normal CDF in all four builds; golden `trig_k-0009` (k = 30) checks the far tail. Acceptance 1.1.0 (KR-232, written after the audit and shown failing on the 1.0.0 code): simulations at n = 2, 4, 30 and 250 centred on the operation's own `false_alarm_rate`.

## Step 2: the same cases through the library

This block calls the library on the goldens in `datasets/golden/stage_k/`. It was turned on at integration (2026-11-19) and printed the same lines as Step 1; CI now checks them.

<!-- tutorial:run python -->
```python
# Goldens trig_k-0001 to 0005 through calib.trigger.check; the binomial interval as in Step 1.
import json
import math

from quantforge_core.cli.main import run_case

cases = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_k/trig_k.json", encoding="utf-8"))["cases"]}
for n in range(1, 6):
    c = cases[f"trig_k-{n:04d}"]
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"], "inputs": c["inputs"]}))
    out, want, i = r["outputs"], c["expected"]["outputs"], c["inputs"]
    assert out["fire"] == want["fire"] and all(abs(out[k] - want[k]) <= 1e-14 * abs(want[k]) for k in ("sigma", "threshold", "nominal_rate"))
    assert abs(out["false_alarm_rate"] - want["false_alarm_rate"]) <= 1e-11 * abs(want["false_alarm_rate"])  # class tail_probability
    print(f"{c['case_id']} move {abs(i['x_now'] - i['x_ref']):.8g} sigma {out['sigma']:.10f} threshold {out['threshold']:.10f} "
          f"fire {out['fire']} alpha {out['false_alarm_rate']:.6f} nominal {out['nominal_rate']:.6f}")


def binom_interval(n, p, level=0.99):
    lo, hi, cdf, a = (1 - level) / 2, (1 + level) / 2, 0.0, None
    for x in range(n + 1):
        cdf += math.exp(math.lgamma(n + 1) - math.lgamma(x + 1) - math.lgamma(n - x + 1) + x * math.log(p) + (n - x) * math.log1p(-p))
        if a is None and cdf >= lo:
            a = x
        if cdf >= hi:
            return a, x


lo, hi = binom_interval(100_000, 0.0030306)
print(f"99% interval for 100,000 noise paths at rate 0.0030306: [{lo}, {hi}]; Python 291 and Java 287 fires inside: {lo <= 291 <= hi and lo <= 287 <= hi}")
```

## For practitioners

- **Pick `k` from the false alarms you can afford.** At `k = 3`, a long window (where `alpha` is close to 0.0027) and one check a day, about one false trigger every 370 days per monitored input; with a short window it is far more often (one in 17 days at four changes); with 50 inputs that is one every week or so. The level is a cost decision, written down before use.
- **The normal tail is optimistic for fat-tailed inputs.** Real daily changes have fatter tails than the normal, so the realised false-alarm rate will be higher than `alpha`, which assumes normal changes. CUSUM and EWMA variants are out of wave 1.
- **`sigma` from the same window as the move is circular.** The window must end before the move being judged, or a big move inflates its own threshold.

## Common mistakes

- **Using the population standard deviation.** The spec divides by `n - 1`; with four changes that is the difference between 1.0 and 1.1547.
- **Forgetting `sqrt(d)`.** A move accumulated over several days must be judged against several days of noise (`trig_k-0003`).

## What you just did

You ran a recalibration trigger on five golden cases, saw the threshold widen with time and refuse to fire at equality, and checked that the acceptance simulation's fire counts sit inside their stated binomial interval.

## Try next

- With the changes of `trig_k-0001` and `k = 3`, find the smallest move that fires after 9 days, by hand first.

## References and further reading

- This project: `specifications/03-calibration/recalibration-triggers.md`, `specifications/stage-k-rulings-w1.md`; drift detectors in [Tutorial 33](tutorial-33-stress-test-and-watch-for-drift.md).
- E. S. Page, "Continuous inspection schemes", *Biometrika* 41 (1954) (cited in the spec; not opened, recalled).
