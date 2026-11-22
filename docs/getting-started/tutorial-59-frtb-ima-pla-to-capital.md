# Tutorial 59: FRTB internal models, from P&L attribution to the capital charge

<!-- tutorial:only python -->

The plain idea: a bank allowed to use its own model for market risk capital still follows a fixed recipe around that model. Each desk first has to show that the risk model's P&L tracks the front office's (the P&L attribution test, PLA). The model's expected shortfall (ES) is then stretched for risk factors that take longer than 10 days to exit, scaled up to a stress period, topped up with a separate charge for factors without enough real prices (the stress scenario charge, SES), and finally added up with a multiplier that grows with backtesting exceptions and a surcharge for desks that only just pass PLA.

You will compute each of those pieces by hand on the golden inputs, see how model noise moves a desk from green to amber on 250 synthetic days, and then get the same lines from the library. Budget 15 minutes.

<p class="note">Stage K wave 2. The operations <code>risk.frtb.pla</code>, <code>risk.frtb.pla.ks_pvalue</code>, <code>risk.frtb.ima.es_lh</code>, <code>.es_stressed</code>, <code>.imcc</code>, <code>.ses</code> and <code>.capital</code> are merged to <code>main</code> in all four builds (2026-11-20, merge 37292e4f; not in a tag; spec <code>specifications/06-risk/frtb-ima.md</code> 0.1.0; rulings KR-50, KR-56 to KR-61 and KR-67 to KR-69 in <code>specifications/stage-k-rulings-w2.md</code>, most still PROPOSED). Outside share of <code>ima_k</code>: 23 of 33 value cases (69.7%; <code>oracle/OUTSIDE_SHARES.md</code>, read 2026-11-21). Every output carries the label "regulatory formula on caller inputs; not a regulatory return". Step 1 uses the standard library; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. **HPL** (hypothetical P&L) is the front office's revaluation of the start-of-day positions; **RTPL** (risk-theoretical P&L) is the same P&L as the risk model sees it. **ES** is the average loss in the worst 2.5% of outcomes. A **liquidity horizon** (LH) is the number of days a risk factor is assumed to take to exit: 10, 20, 40, 60 or 120. **IMCC** is the capital from modellable risk factors; **SES** the charge for non-modellable ones; **DRC** the default risk charge, an input here.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: every piece by hand

```python
# FRTB IMA pieces (MAR32, MAR33) restated with the standard library on golden inputs.
import math
import random
from statistics import NormalDist


def ranks(xs):  # average ranks for ties (KR-56)
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r, i = [0.0] * len(xs), 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pla(hpl, rtpl):
    n, a, b = len(hpl), ranks(hpl), ranks(rtpl)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    rs = cov / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    d = max(abs(sum(v <= x for v in rtpl) - sum(v <= x for v in hpl)) for x in hpl + rtpl)
    zone = "GREEN" if rs > 0.80 and 100 * d < 9 * n else "RED" if rs < 0.70 or 100 * d > 12 * n else "AMBER"
    return rs, d / n, zone


def q_ks(x):  # Kolmogorov survival function, alternating series (x >= 1 here)
    return 2 * sum((-1) ** (k - 1) * math.exp(-2 * k * k * x * x) for k in range(1, 101))


rs, ks, zone = pla([-3, 1, 4, -1, 2], [-2, 0, 5, 1, 3])
print(f"PLA, 5 days (pla_k-0001): spearman {rs:.6f} ks {ks:.2f} zone {zone}")
rng = random.Random(59)
hpl = [sum(rng.random() for _ in range(12)) - 6 for _ in range(250)]  # synthetic desk P&L, not market data
for noise in (0.2, 0.5, 0.65, 0.8):
    rtpl = [h + noise * (sum(rng.random() for _ in range(12)) - 6) for h in hpl]
    rs, ks, zone = pla(hpl, rtpl)
    print(f"PLA, 250 synthetic days, model noise {noise}: spearman {rs:.4f} ks {ks:.3f} zone {zone}")
for d in (0.09, 0.12):
    print(f"KS p-value at D = {d}, n = 250: {q_ks(d * math.sqrt(125)):.4f}")

w = [1, 1, 2, 2, 6]  # (LH_j - LH_{j-1}) / 10 for LH = 10, 20, 40, 60, 120
es_t = [10, 8, 6, 4, 2]
print(f"ES with liquidity horizons (es_k-0003): {math.sqrt(sum(wj * e * e for wj, e in zip(w, es_t))):.10f}")
z = NormalDist().inv_cdf(0.975)
print(f"normal ES at 97.5%, sigma 1 (es_k-0001): {NormalDist().pdf(z) / 0.025:.10f}")


def stressed(rs_, fc, rc):  # MAR33.6: ES_R,S x max(1, ES_F,C / ES_R,C)
    return rs_ * max(1, fc / rc)


imcc_c = stressed(12, 10, 8)
classes = {"IR": stressed(6, 5, 4), "EQ": stressed(5, 4, 5)}
print(f"stressed ES, portfolio {imcc_c:.2f}, IR {classes['IR']:.2f}, EQ {classes['EQ']:.2f}; IMCC {0.5 * imcc_c + 0.5 * sum(classes.values()):.4f}")

other = [1, 2, 2]
ses = math.hypot(3, 4) + math.hypot(5, 12) + math.sqrt((0.6 * sum(other)) ** 2 + 0.64 * sum(x * x for x in other))
print(f"SES (ses_k-0001): {ses:.10f}")

MULT = {5: 1.70, 6: 1.76, 7: 1.83, 8: 1.88, 9: 1.92}  # MAR32.9; 1.50 below 5, 2.00 from 10
m_c = MULT.get(6, 1.50)
c_a = max(100 + 20, m_c * 90 + 15)
ima = c_a + 30
sa = 150 + 100
k = 0.5 * 100 / sa
surcharge = k * max(0, sa - ima)
acr = min(ima + surcharge + 40, 300) + max(0, ima - sa)
print(f"capital (cap_k-0002): m_c {m_c} C_A {c_a:.2f} IMA {ima:.2f} k {k:.2f} surcharge {surcharge:.2f} ACR {acr:.2f}")
```

Output (CI checks that Step 2 prints these lines; measured 2026-11-21 on branch `k-v1-docs-a`, Python 3.15.2 through `uv`, local laptop, not the acceptance machine):

<!-- tutorial:expect -->
```text
PLA, 5 days (pla_k-0001): spearman 0.900000 ks 0.20 zone RED
PLA, 250 synthetic days, model noise 0.2: spearman 0.9776 ks 0.032 zone GREEN
PLA, 250 synthetic days, model noise 0.5: spearman 0.8581 ks 0.068 zone GREEN
PLA, 250 synthetic days, model noise 0.65: spearman 0.8253 ks 0.108 zone AMBER
PLA, 250 synthetic days, model noise 0.8: spearman 0.7384 ks 0.096 zone AMBER
KS p-value at D = 0.09, n = 250: 0.2634
KS p-value at D = 0.12, n = 250: 0.0546
ES with liquidity horizons (es_k-0003): 17.0880074906
normal ES at 97.5%, sigma 1 (es_k-0001): 2.3378027922
stressed ES, portfolio 15.00, IR 7.50, EQ 5.00; IMCC 13.7500
SES (ses_k-0001): 21.8418745425
capital (cap_k-0002): m_c 1.76 C_A 173.40 IMA 203.40 k 0.20 surcharge 9.32 ACR 252.72
```

### Reading the numbers

- **PLA on five days (golden `pla_k-0001`).** HPL (-3, 1, 4, -1, 2) has ranks (1, 3, 5, 2, 4); RTPL (-2, 0, 5, 1, 3) has ranks (1, 2, 5, 3, 4). The rank differences are (0, 1, 0, -1, 0), so `r_S = 1 - 6 x 2 / (5 x 24) = 0.9`. The two empirical distributions differ by at most one count in five, so `ks = 0.2`. The correlation passes (above 0.80) but `ks` is above 0.12, so the desk is red: getting the order of the days right is not enough, the sizes must match too.
- **PLA on 250 synthetic days.** The RTPL is the HPL plus independent noise of growing size (seed 59; synthetic, not market data). At noise 0.2 and 0.5 the desk is green. At 0.65 the correlation (0.825) still passes, but the noise widens the RTPL distribution so that `ks` is 0.108, between 0.09 and 0.12: amber. At 0.8 the KS distance happens to be smaller (0.096, still amber), and the correlation, 0.738, is now between 0.70 and 0.80. Two tests, two ways to fail.
- **The printed p-values.** MAR32.42 quotes p-values of 0.264 and 0.055 for the KS thresholds 0.09 and 0.12 at 250 days. The asymptotic Kolmogorov distribution gives 0.2634 and 0.0546 (goldens `pla_k-0007` and `pla_k-0008`; the printed 0.264 is 0.0006 above the asymptotic value, which the spec records rather than hides).
- **Liquidity horizons (golden `es_k-0003`).** The five ES values are those of the portfolio shocked only in the factors with LH of at least 10, 20, 40, 60 and 120 days. Each is weighted by the extra time over the previous horizon, in units of 10 days: weights 1, 1, 2, 2, 6. `ES^2 = 100 + 64 + 2 x 36 + 2 x 16 + 6 x 4 = 292`, `ES = 17.088`. If every factor had LH 120, all five ES values would be equal and `ES = E sqrt(12) = E sqrt(120/10)`: square-root-of-time scaling is the special case.
- **Normal ES (golden `es_k-0001`).** For a normal P&L with standard deviation 1, `ES = phi(z) / 0.025` with `z = 1.959964`: 2.3378. This is the check against a closed form.
- **Stress calibration (golden `imcc_k-0001`).** The model is run on a reduced set of factors in the stress period and in the current period, and the stressed ES on the reduced set is scaled by the ratio of full to reduced current ES, never by less than 1: `12 x max(1, 10/8) = 15`. For the equity class the ratio is `4/5 < 1`, so it is floored and the class figure stays 5. IMCC averages the diversified and the undiversified figures: `0.5 x 15 + 0.5 x (7.5 + 5) = 13.75`.
- **SES (golden `ses_k-0001`).** Idiosyncratic credit and equity charges each add as the square root of a sum of squares, 5 and 13; the others are aggregated with a correlation of 0.6: `sqrt((0.6 x 5)^2 + 0.64 x 9) = 3.842`. Total 21.842.
- **Capital (golden `cap_k-0002`).** Six backtesting exceptions give the multiplier 1.76. `C_A = max(100 + 20, 1.76 x 90 + 15) = 173.4`: the 60-day average times the multiplier is the binding term. Adding DRC 30 gives the IMA figure 203.4. The amber desk carries standardised capital 100 of a total 250, so `k = 0.5 x 100 / 250 = 0.2` and the surcharge is `0.2 x (250 - 203.4) = 9.32`. With 40 of capital for desks outside the model, `ACR = min(203.4 + 9.32 + 40, 300) = 252.72`.

### The formal statement, checked against the spec

From `specifications/06-risk/frtb-ima.md` 0.1.0 (MAR31 to MAR33 of the Basel Framework PDF of 11/11/2026, read by the spec lane 2026-11-19).

- PLA (MAR32.36 to 32.42, KR-56): `r_S` is the Pearson correlation of the rank series, with average ranks for ties; `d` is the largest difference of counts at or below any pooled value, `ks = d / n`. Green iff `r_S > 0.80` and `100 d < 9 n`; red iff `r_S < 0.70` or `100 d > 12 n`; amber otherwise. The p-value is `Q_KS(ks sqrt(n/2))`.
- ES with liquidity horizons (MAR33.4): `ES = sqrt(ES_1^2 + sum_{j=2..5} (ES_j sqrt((LH_j - LH_{j-1}) / 10))^2)`.
- Stress calibration (MAR33.6, KR-58): `ES = ES_R,S max(1, ES_F,C / ES_R,C)`; `IMCC = 0.5 IMCC(C) + 0.5 sum_i IMCC(C_i)` (MAR33.15).
- SES (MAR33.17): `sqrt(sum ISES_i^2) + sqrt(sum ISES_j^2) + sqrt((0.6 sum SES_k)^2 + 0.64 sum SES_k^2)`.
- Capital (MAR33.41 to 33.45, KR-61): `C_A = max(IMCC_prev + SES_prev, m_c IMCC_avg + SES_avg)`; `IMA = C_A + DRC`; `k = 0.5 sum_amber SA / sum SA`; `surcharge = k max(0, SA - IMA)`; `ACR = min(IMA + surcharge + C_U, SA_all) + max(0, IMA - SA)`.
- Acceptance (fixed before any run): all value goldens in all four builds to 1e-12 relative; SciPy agreement for every PLA golden and the normal ES goldens; 10,000-case properties (for example, `spearman` unchanged by a strictly increasing transform of either series). The outside-share gate of 60% is met at 23 of 33 (measured 2026-11-20 after the second blind lane, `program/STAGE_K_BLIND_W2.md`).

## Step 2: the same questions through the library

<!-- tutorial:run python -->
```python
# The same questions through the library: risk.frtb.pla, .pla.ks_pvalue, .ima.es_lh, .ima.es_stressed, .ima.imcc,
# .ima.ses and .ima.capital, on the golden inputs of datasets/golden/stage_k/ima_k.json and one synthetic desk.
import json
import random

from quantforge_core.cli.main import run_case


def call(op, inputs):
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "t59", "operation": op, "inputs": inputs}))
    return r["outputs"]


o = call("risk.frtb.pla", {"hpl": [-3, 1, 4, -1, 2], "rtpl": [-2, 0, 5, 1, 3]})
print(f"PLA, 5 days (pla_k-0001): spearman {o['spearman']:.6f} ks {o['ks']:.2f} zone {o['zone']}")
rng = random.Random(59)
hpl = [sum(rng.random() for _ in range(12)) - 6 for _ in range(250)]  # synthetic desk P&L, not market data
for noise in (0.2, 0.5, 0.65, 0.8):
    rtpl = [h + noise * (sum(rng.random() for _ in range(12)) - 6) for h in hpl]
    o = call("risk.frtb.pla", {"hpl": hpl, "rtpl": rtpl})
    print(f"PLA, 250 synthetic days, model noise {noise}: spearman {o['spearman']:.4f} ks {o['ks']:.3f} zone {o['zone']}")
for d in (0.09, 0.12):
    print(f"KS p-value at D = {d}, n = 250: {call('risk.frtb.pla.ks_pvalue', {'ks': d, 'n': 250})['pvalue']:.4f}")

print(f"ES with liquidity horizons (es_k-0003): {call('risk.frtb.ima.es_lh', {'es_t': [10, 8, 6, 4, 2]})['es']:.10f}")
print(f"normal ES at 97.5%, sigma 1 (es_k-0001): {call('risk.frtb.ima.es_lh', {'sigma': [1, 0, 0, 0, 0]})['es']:.10f}")

o = call("risk.frtb.ima.imcc", {"portfolio": {"es_rs": 12, "es_fc": 10, "es_rc": 8},
                                "classes": {"IR": {"es_rs": 6, "es_fc": 5, "es_rc": 4}, "EQ": {"es_rs": 5, "es_fc": 4, "es_rc": 5}}})
print(f"stressed ES, portfolio {o['imcc_c']:.2f}, IR {o['classes']['IR']:.2f}, EQ {o['classes']['EQ']:.2f}; IMCC {o['imcc']:.4f}")

o = call("risk.frtb.ima.ses", {"idio_credit": [3, 4], "idio_equity": [5, 12], "other": [1, 2, 2]})
print(f"SES (ses_k-0001): {o['ses']:.10f}")

o = call("risk.frtb.ima.capital", {"imcc_prev": 100, "ses_prev": 20, "imcc_avg": 90, "ses_avg": 15, "exceptions": 6,
                                   "qualitative_addon": 0, "drc": 30, "c_u": 40, "sa_all": 300,
                                   "desks": [{"zone": "GREEN", "sa": 150}, {"zone": "AMBER", "sa": 100}]})
print(f"capital (cap_k-0002): m_c {o['m_c']} C_A {o['c_a']:.2f} IMA {o['ima_ga']:.2f} k {o['k']:.2f} "
      f"surcharge {o['surcharge']:.2f} ACR {o['acr_total']:.2f}")
```

## For practitioners

- **PLA is a desk-level gate with two tests.** A model that ranks days correctly but gets the size of moves wrong fails on KS; a model with the right distribution but the wrong days fails on correlation. Find out which one before changing the model.
- **The library has no ES model.** The caller supplies the five P&L lists or ES values per horizon, the stress period, the reduced factor set and the stress scenarios; the operations aggregate. The 60-day and 12-week averages are inputs too (spec, Limits).
- **The surcharge is small unless the IMA figure is well below SA.** In the example 40% of SA sits on an amber desk, and the surcharge is still 9.32 of 252.72.

## Common mistakes

- **Applying square-root-of-time to the whole ES.** Only the factors still held at each longer horizon are scaled; applying `sqrt(12)` to everything overstates capital unless every factor has LH 120.
- **Letting the stress ratio fall below 1.** MAR33.6 floors it at 1; a class whose full current ES is below its reduced current ES keeps its stressed reduced ES.
- **Reading a green PLA as a validated model.** PLA compares two P&Ls on the same days; the backtesting traffic light ([Tutorial 57](tutorial-57-backtesting-traffic-light.md)) compares the VaR with losses. Both are needed.

## What you just did

You ran the P&L attribution test on a five-day golden and on four synthetic desks, checked the printed KS p-values, built ES with liquidity horizons, stress-calibrated it, aggregated stress scenario charges and assembled the capital requirement with its multiplier and surcharge.

## Try next

- Change the exceptions in the capital case from 6 to 4. By hand `m_c` is 1.50 and `C_A = max(120, 1.5 x 90 + 15) = 150`.
- Look up a liquidity horizon with `risk.frtb.ima.lh`: golden `lh_k-0001` gives an interest-rate volatility factor of 30 days' maturity an LH of 40, not the table's 60, under the maturity rule.
- The default risk charge that enters as `drc` is in the [Cookbook](../../COOKBOOK.md#default-risk-charge-a-short-bond-does-not-offset-a-long-stock-wave-2-golden-drc_k-0007).

## References and further reading

- This project: `specifications/06-risk/frtb-ima.md`, `specifications/stage-k-rulings-w2.md`, `specifications/tables/stage_k/mar32_pla.json` and `mar33_ima.json`, goldens `datasets/golden/stage_k/ima_k.json`.
- Basel Committee on Banking Supervision, *The Basel Framework*, MAR31 (risk factor eligibility), MAR32 (backtesting and P&L attribution) and MAR33 (internal models capital), consolidated PDF generated 11/11/2026 (read by the spec lane, 2026-11-19).
