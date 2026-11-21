# Tutorial 60: is the process leaking? Read a soak run

<!-- tutorial:only python -->

The plain idea: a pricing or risk service that runs all day must not grow. A soak test feeds one long-lived `quantforge batch` process every golden case in a loop for about two hours, reads its memory every 10 seconds, and checks that every later answer is byte-identical to the first. The verdict then asks two questions of the memory series after a warm-up: does it climb (slope), and does it wander (range)?

You will apply the frozen K-6 rule by hand to the three Python soak runs recorded on 2026-11-20, see why the main run is a recorded miss, why one planted leak was missed and the other caught, and get the same lines from the project's analyser. Budget 10 minutes. Nothing is run against a build: the inputs are the committed CSV files.

<p class="note">Stage K, item K-6, merged to <code>main</code> 2026-11-20 (merge 62d77666; not in a tag). Spec <code>specifications/12-platform/soak-eod-capacity.md</code> 0.2.0, rulings KR-217 to KR-221 (<code>specifications/stage-k-rulings-k6.md</code>, confirmed 2026-11-20). The rule was committed before the runs it judges (1ce167bf, per <a href="../capacity.md">Capacity and operations</a>). The runs are on the local laptop, not the acceptance machine. <strong>The Python soak is a recorded MISS on slope, and the first planted leak is a recorded miss</strong> (<code>docs/known-issues.md</code>, read 2026-11-21); this page explains the misses and changes nothing. Step 1 uses the standard library; Step 2 calls <code>benchmarks/soak/analyse.py</code>, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. The **judged series** is, for Python, the smallest committed-private-bytes reading in each 10 s window (Windows). **Warm-up** is discarded: samples before 600 s or the end of the first full pass over the golden set, whichever is later. The **slope** is the least-squares slope of the judged series against time, in MiB per hour. The **range** is maximum minus minimum. A **planted leak** is a fault switched on deliberately (`QF_SOAK_LEAK=1`) to show that the rule can see one.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Both steps use the Python standard library only; the CSV files are in `benchmarks/results/k6/`.

## Step 1: the rule by hand

```python
# The K-6 soak rule (KR-218) restated with the standard library on the three recorded Python runs of 2026-11-20.
import csv
import statistics

MIB, K6 = 1024 * 1024, "benchmarks/results/k6/"
T975 = {4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160}


def line(xs, ys):  # least-squares slope and intercept
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return b, my - b * mx


def judge(name, planted):
    rows = list(csv.DictReader(open(K6 + name + ".csv", encoding="utf-8")))
    first_pass = next(float(r["t_s"]) for r in rows if int(r["passes"]) >= 1)
    warmup = max(600.0, first_pass)  # every case has run once before memory is judged
    pts = [(float(r["t_s"]) / 3600, float(r["judged_bytes"]) / MIB) for r in rows if float(r["t_s"]) >= warmup]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    slope, _ = line(xs, ys)
    med, rng = statistics.median(ys), max(ys) - min(ys)
    blocks = {}  # 10-minute block means for the interval (evidence, not a pass condition)
    for x, y in pts:
        blocks.setdefault(int((x - xs[0]) // (600 / 3600)), []).append((x, y))
    bm = [(statistics.fmean(p[0] for p in v), statistics.fmean(p[1] for p in v)) for v in blocks.values()]
    ci = "n/a"
    if len(bm) >= 3 and len(bm) - 2 in T975:
        bx, by = [p[0] for p in bm], [p[1] for p in bm]
        b, a = line(bx, by)
        mx = statistics.fmean(bx)
        se = (sum((y - a - b * x) ** 2 for x, y in zip(bx, by)) / (len(bm) - 2) / sum((x - mx) ** 2 for x in bx)) ** 0.5
        ci = f"[{b - T975[len(bm) - 2] * se:.2f}, {b + T975[len(bm) - 2] * se:.2f}]"
    reasons = []
    if not planted and len(ys) < 660:
        reasons.append("FEW_SAMPLES")
    if not planted and float(rows[-1]["t_s"]) < 7200:
        reasons.append("SHORT")
    if slope > 1.0:
        reasons.append("SLOPE")
    if rng > 0.05 * med:
        reasons.append("RANGE")
    if planted:
        verdict = "LEAK CAUGHT" if "SLOPE" in reasons else "LEAK MISSED"
    else:
        verdict = "MISS" if reasons else "PASS"
    print(f"{name}: warm-up {warmup:.0f} s, {len(ys)} samples, slope {slope:.2f} MiB/h, 95% CI {ci}, "
          f"range {100 * rng / med:.1f}% of median {med:.1f} MiB, reasons {reasons or 'none'}: {verdict}")


judge("soak-python-2026-11-20", planted=False)
judge("soak-python-2026-11-20-planted-leak", planted=True)
judge("soak-python-2026-11-20-planted-leak-every-1", planted=True)
```

Output (CI checks that Step 2 prints these lines; measured 2026-11-21 on branch `k-v1-docs-a` from the committed files):

<!-- tutorial:expect -->
```text
soak-python-2026-11-20: warm-up 2037 s, 671 samples, slope 2.32 MiB/h, 95% CI [1.70, 3.80], range 3.0% of median 432.6 MiB, reasons ['SLOPE']: MISS
soak-python-2026-11-20-planted-leak: warm-up 826 s, 43 samples, slope -46.97 MiB/h, 95% CI n/a, range 1.5% of median 429.4 MiB, reasons none: LEAK MISSED
soak-python-2026-11-20-planted-leak-every-1: warm-up 600 s, 61 samples, slope 171.90 MiB/h, 95% CI n/a, range 6.0% of median 475.6 MiB, reasons ['SLOPE', 'RANGE']: LEAK CAUGHT
```

### Reading the numbers

- **The main run is a miss.** After a warm-up of 2,037 s (the first full pass over the golden set took that long) there are 671 samples. The memory sits near 432.6 MiB and moves by only 3.0% of that, well inside the 5% range bound. But the least-squares line climbs 2.32 MiB an hour against a bound of 1 MiB an hour, and the 95% interval from 10-minute block means, 1.70 to 3.80, lies wholly above the bound. Over a 24-hour day that would be about 56 MiB. The cause was not found (`docs/known-issues.md`); the next steps recorded there are a runner soak, where Linux reports VmRSS, and a heap profile of the Python process. The bound was not moved after the run.
- **The first planted leak was missed.** It added 1 KiB per 100 cases. At the soak's Python rate of about 23 cases a second that is `23 x 3600 / 100 = 828` KiB an hour, about 0.8 MiB an hour: under the bound, so the rule could not have flagged it even with a perfectly quiet machine. In a 20-minute planted run the noise is larger still: the fitted slope over 43 samples is -47 MiB an hour, which says more about 7 minutes of a busy laptop than about the process. The verdict `LEAK MISSED` stands as recorded.
- **The second planted leak was caught.** Declared before it ran, it added 1 KiB per case: the slope is 172 MiB an hour and the range 6.0% of the median, so both SLOPE and RANGE fire and the verdict is `LEAK CAUGHT`. That shows the rule sees a leak of that size in 20 minutes; it does not show it would see a slow one.
- **Why there is no interval for the planted runs.** The interval uses one mean per 10 minutes, and a planted run after warm-up has fewer than three blocks. The interval is evidence beside the verdict, never a pass condition.

### The formal statement, checked against the code

From `benchmarks/soak/analyse.py` (`RULES`, the single source the docs quote; read 2026-11-21) and `specifications/12-platform/soak-eod-capacity.md` section 5.

- Warm-up `w = max(600 s, first full pass)`; judged points `(t_i, m_i)` with `t_i >= w`.
- SLOPE fires when `b > 1` MiB/h, with `b = sum (t_i - t_bar)(m_i - m_bar) / sum (t_i - t_bar)^2`.
- RANGE fires when `max m_i - min m_i > 0.05 median(m)`.
- FEW_SAMPLES (fewer than 660 judged samples) and SHORT (under 7,200 s) are not applied to a planted run, which lasts 20 minutes by design. A planted run passes its own test when SLOPE fires.
- The full rule also has DRIFT, GOLDEN, ERRORS, STDERR, EXIT, DIED, STALL and NO_FULL_PASS; Step 1 restates only the memory part, because the three recorded runs have no drift, no golden failures and no errors (their summary files, read).

## Step 2: the same runs through the analyser

<!-- tutorial:run python -->
```python
# The same three runs through the frozen analyser, benchmarks/soak/analyse.py (the only source of a soak verdict).
import csv
import json
import sys

sys.path.insert(0, "benchmarks/soak")
import analyse  # noqa: E402

K6 = "benchmarks/results/k6/"
for name, planted in (("soak-python-2026-11-20", False), ("soak-python-2026-11-20-planted-leak", True),
                      ("soak-python-2026-11-20-planted-leak-every-1", True)):
    rows = list(csv.DictReader(open(K6 + name + ".csv", encoding="utf-8")))
    summary = json.load(open(K6 + name + ".summary.json", encoding="utf-8"))
    v = analyse.analyse(rows, summary, planted=planted)
    ci = "n/a" if v["slope_ci95_mib_per_h"] is None else "[{:.2f}, {:.2f}]".format(*v["slope_ci95_mib_per_h"])
    print(f"{name}: warm-up {v['warmup_end_s']:.0f} s, {v['samples_after_warmup']} samples, "
          f"slope {v['slope_mib_per_h']:.2f} MiB/h, 95% CI {ci}, range {100 * v['range_fraction_of_median']:.1f}% "
          f"of median {v['median_mib']:.1f} MiB, reasons {v['reasons'] or 'none'}: {v['verdict']}")
```

## For practitioners

- **Size the planted fault against the bound before you run it.** A planted fault the rule cannot see by arithmetic tests nothing. Rate times leak per case gives the expected slope in a line.
- **Two hours rules out a fast leak only.** A slope of 1 MiB an hour is 24 MiB a day; whether that matters depends on how long the process lives and how often it restarts.
- **Separate a leak from a cache.** A cache that fills late shows as a step in the series; a leak shows as a steady climb per case. Plot `judged_bytes` against `cases_total` from the CSV before reading the slope.
- **Running a soak.** The commands, and how to read each reason, are in the runbook [Soak, capacity and end-of-day rehearsal](../runbooks/soak-and-eod.md); measured capacity figures are on [Capacity and operations](../capacity.md).

## Common mistakes

- **Moving the bound after a miss.** The bound is fixed before the run that it judges; a miss is written down as a miss.
- **Reading a short window.** Over minutes, paging and garbage collection dominate; the planted run's -47 MiB an hour is noise, not a process that shrinks.

## What you just did

You applied the frozen soak rule by hand to three recorded runs, recomputed a slope and its block-mean interval, saw why the main Python run misses and why one planted leak could not be caught, and confirmed the same verdicts with the project's analyser.

## Try next

- Count the cases per hour in the main run from `cases_total` and the timestamps, then work out the leak per case that would just reach 1 MiB an hour.
- Read `benchmarks/results/k6/eod-2026-11-19-synthetic-plant-EXPLAIN.json` and find the step that failed and the steps recorded as "not run".

## References and further reading

- This project: `specifications/12-platform/soak-eod-capacity.md`, `specifications/stage-k-rulings-k6.md`, `benchmarks/soak/analyse.py`, `benchmarks/soak/soak.py`, `docs/known-issues.md` (K-6 rows), [Capacity and operations](../capacity.md).
