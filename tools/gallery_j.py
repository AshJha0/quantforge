"""Stage J page for the gallery: a research workflow from backtest to PBO (tools/build_gallery.py).

A teaching example on a synthetic, driftless price series (`examples/research_workflow_j.json`, made by
`make_example` below with a fixed seed), so any rule that looks good on it is luck by construction. It sends
twelve rules through `research.backtest.run`, a purged k-fold split through `research.cv.purged_kfold`, and the
trial set through `research.stats.psr`, `research.stats.dsr` and `research.stats.pbo`.

Financial logic held here, stated because the gallery otherwise holds none: the twelve rule targets (the sign of
a past price change, or its negative), and the sample moments of each rule's daily P&L (mean, standard
deviation with divisor n - 1, skew and non-excess kurtosis with divisor n), because no CLI operation returns
moments yet (program/DOCS_PLUS_NOTES.md). Everything else is a CLI output or a difference between outputs.
"""
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = "research-workflow"
EXAMPLE = "research_workflow_j.json"
SEED, BARS, WARMUP, LAG, HALF_SPREAD_BPS = 20261114, 502, 100, 1, 1.0
FIRST = WARMUP + LAG + 1  # first bar whose P&L can be non-zero for every rule
MOMENTUM = (2, 3, 5, 10, 20, 40, 60, 100)
REVERSAL = (2, 5, 10, 20)
FOLDS, EMBARGO, PARTITIONS = 5, 0.01, 8


def make_example():
    """The committed example: a seeded driftless log-normal walk, 1 % daily volatility, and rule 0's targets."""
    rng = random.Random(SEED)
    logp, prices = math.log(100.0), []
    for _ in range(BARS):
        prices.append(round(math.exp(logp), 4))
        logp += rng.gauss(0.0, 0.01)
    return {"schema_version": "1.0", "case_id": "example-research-workflow-j", "operation": "research.backtest.run",
            "inputs": {"prices": prices, "targets": targets(prices, MOMENTUM[0], 1.0), "lag": LAG,
                       "half_spread_bps": HALF_SPREAD_BPS}}


def targets(prices, lookback, side):
    """+side when the close is above the close `lookback` bars earlier, -side when below; 0 in the warm-up."""
    out = []
    for t, p in enumerate(prices):
        if t < WARMUP:
            out.append(0.0)
        else:
            d = p - prices[t - lookback]
            out.append(0.0 if d == 0 else side * (1.0 if d > 0 else -1.0))
    return out


def rules():
    return [(f"momentum {k}", k, 1.0) for k in MOMENTUM] + [(f"reversal {k}", k, -1.0) for k in REVERSAL]


def moments(xs):
    n = len(xs)
    mean = sum(xs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))
    m2 = sum((x - mean) ** 2 for x in xs) / n
    skew = sum((x - mean) ** 3 for x in xs) / n / m2 ** 1.5
    kurt = sum((x - mean) ** 4 for x in xs) / n / m2 ** 2
    return {"mean": mean, "sd": sd, "sr": mean / sd, "skew": skew, "kurtosis": kurt}


def case(cid, op, inputs):
    return {"schema_version": "1.0", "case_id": cid, "operation": op, "inputs": inputs}


def run(lang, batch, read_example):
    ex = read_example(EXAMPLE)["inputs"]
    prices = ex["prices"]
    names = rules()
    bt = batch(lang, [case(f"gallery-j-bt-{i:02d}", "research.backtest.run",
                           {"prices": prices, "targets": targets(prices, k, s), "lag": LAG, "half_spread_bps": HALF_SPREAD_BPS})
                      for i, (_, k, s) in enumerate(names)])
    pnl = [r["outputs"]["pnl_net"][FIRST:] for r in bt]
    stats = [moments(p) for p in pnl]
    srs = [s["sr"] for s in stats]
    best = max(range(len(srs)), key=lambda i: (srs[i], -i))
    m = sum(srs) / len(srs)
    sr_var = sum((x - m) ** 2 for x in srs) / (len(srs) - 1)
    n = len(pnl[0])
    b = stats[best]
    common = {"sr": b["sr"], "n_obs": n, "skew": b["skew"], "kurtosis": b["kurtosis"]}
    rows = [[p[i] for p in pnl] for i in range(n)]
    idx = list(range(n))
    out = batch(lang, [case("gallery-j-psr", "research.stats.psr", common),
                       case("gallery-j-dsr", "research.stats.dsr", {**common, "n_trials": len(names), "sr_variance": sr_var}),
                       case("gallery-j-pbo", "research.stats.pbo", {"performance": rows, "n_partitions": PARTITIONS}),
                       case("gallery-j-cv", "research.cv.purged_kfold", {"t0": idx, "t1": [i + 1 for i in idx],
                                                                          "n_splits": FOLDS, "embargo_pct": EMBARGO})])
    psr, dsr, pbo, cv = (r["outputs"] for r in out)
    folds = []
    for f in cv["folds"]:
        train = [moments([pnl[j][i] for i in f["train"]])["sr"] for j in range(len(names))]
        test = [moments([pnl[j][i] for i in f["test"]])["sr"] for j in range(len(names))]
        pick = max(range(len(train)), key=lambda j: (train[j], -j))
        folds.append({"test_first": f["test"][0], "test_last": f["test"][-1], "train_size": len(f["train"]),
                      "pick": pick, "train_sr": train[pick], "test_sr": test[pick],
                      "test_rank": 1 + sum(1 for x in test if x > test[pick])})
    return {"trials": [{"rule": nm, "total_net": r["outputs"]["total_net"], "trade_count": r["outputs"]["trade_count"], **s}
                       for (nm, _, _), r, s in zip(names, bt, stats)],
            "best": best, "sr_variance": sr_var, "n_obs": n, "psr": psr, "dsr": dsr, "pbo": pbo,
            "embargo_count": cv["embargo_count"], "folds": folds,
            "equity_best": bt[best]["outputs"]["equity"][FIRST - 1:],
            "equity_worst": bt[min(range(len(srs)), key=lambda i: (srs[i], i))]["outputs"]["equity"][FIRST - 1:]}


def _flat(res):
    vals = []
    for t in res["trials"]:
        vals += [t["total_net"], t["sr"]]
    vals += [res["psr"]["psr"], res["dsr"]["dsr"], res["dsr"]["sr0"], res["pbo"]["pbo"]] + res["pbo"]["logits"]
    vals += [f["test_sr"] for f in res["folds"]] + res["equity_best"]
    return vals


def agreement(results, langs):
    ref = _flat(results[langs[0]])
    worst = max(abs(a - b) for lang in langs for a, b in zip(_flat(results[lang]), ref))
    return {"values": len(ref), "largest_difference": worst}


def evidence():
    gold = ROOT / "datasets" / "golden" / "stage_j"
    doc = json.loads((ROOT / "oracle" / "OUTSIDE_J.json").read_text(encoding="utf-8"))
    rows = []
    for suite in ("backtest_j", "purgedcv_j", "rstats_j"):
        cases = json.loads((gold / f"{suite}.json").read_text(encoding="utf-8"))["cases"]
        outside = sum(1 for c in doc["suites"].get(suite, {}).get("cases", [])
                      if c["pass"] and all(x["pass"] for x in c["checks"]))
        rows.append({"suite": suite, "cases": len(cases), "outside": outside})
    return {"suites": rows}


def page(d, table, lines, status_block):
    ref = d["reference"]
    ann = math.sqrt(252)
    trows = [[t["rule"], f"{t['total_net']:.2f}", t["trade_count"], f"{t['sr'] * ann:.3f}", f"{t['skew']:.3f}", f"{t['kurtosis']:.3f}"]
             for t in ref["trials"]]
    best = ref["trials"][ref["best"]]
    frows = [[f"{f['test_first']}-{f['test_last']}", f["train_size"], ref["trials"][f["pick"]]["rule"],
              f"{f['train_sr'] * ann:.3f}", f"{f['test_sr'] * ann:.3f}", f"{f['test_rank']} of {len(ref['trials'])}"] for f in ref["folds"]]
    eq = [("Best rule in sample", list(enumerate(ref["equity_best"]))), ("Worst rule in sample", list(enumerate(ref["equity_worst"])))]
    logits = sorted(ref["pbo"]["logits"])
    lg = [("Logit of the in-sample winner", list(enumerate(logits))), ("Zero line", [(0, 0.0), (len(logits) - 1, 0.0)])]
    cap = "Synthetic driftless prices. From the Python CLI; exact values are in the data file."
    ev = [[f"`{r['suite']}`", r["cases"], r["outside"]] for r in d["evidence"]["suites"]]
    a = d["agreement"]
    below = sum(1 for x in logits if x <= 0)
    return f"""# Research workflow: from backtest to PBO

{status_block(d)}

<p class="note">A teaching example, not a trading claim. The prices are a seeded random walk with no drift, so no rule on this page has an edge: whatever looks good here is luck, and the point of the page is to show the statistics saying so.</p>

## What it is

A research study tries several rules, keeps the best and reports its Sharpe ratio. This page walks one such study through the stage J operations: twelve rules backtested with costs, the winner's probabilistic and deflated Sharpe ratios, the winner chosen inside purged cross-validation folds and scored outside them, and the probability of backtest overfitting across all twelve. Stage J, target v0.9.0 (`specifications/11-research/`).

Formally, the deflated Sharpe ratio is the probability that the true Sharpe exceeds the one the best of `N` useless trials would show, `SR0`, and PBO is the share of training and test splits in which the training winner ranks in the bottom half out of sample. [Tutorial 23](../getting-started/tutorial-23-backtest-honestly.md) and [Tutorial 24](../getting-started/tutorial-24-is-the-sharpe-real.md) explain each step on hand-sized data; [LEARN, stage J](../../LEARN.md#stage-j-backtest-overfitting-and-research-statistics) gives the derivations.

## Inputs

{len(d['inputs']['prices'])} daily closes from [`examples/{EXAMPLE}`](../../examples/{EXAMPLE}): a log-normal random walk with 1 % daily volatility, no drift, seed {SEED}, starting at 100, generated by `tools/gallery_j.py`. The repository holds no real daily price series long enough for this (the real series it records are a month of SOFR fixings and single-day curves), and none is downloaded here. Twelve rules: momentum, holding the sign of the change over the last 2, 3, 5, 10, 20, 40, 60 or 100 days, and reversal, holding the opposite sign over 2, 5, 10 or 20 days. Every rule waits {WARMUP} bars, trades one unit with lag {LAG} and pays a half-spread of {HALF_SPREAD_BPS:g} bp. Statistics use the {ref['n_obs']} bars from bar {FIRST}, where every rule can have P&L.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root, for the first rule:

```bash
rust/target/release/quantforge run < examples/{EXAMPLE}
```

The page itself is `python tools/build_gallery.py --stage-j-only`. Raw numbers: [`docs/curves/data/{SLUG}.json`](data/{SLUG}.json).

## The twelve trials

Sharpe is of daily net P&L per unit, annualised by `sqrt(252)`; kurtosis is not excess.

{table(['Rule', 'Net P&L', 'Trades', 'Annual Sharpe', 'Skew', 'Kurtosis'], trows)}

{lines("Equity of the best and worst rules", "Bar from the start of the sample", "Net P&L", eq, cap)}

## Is the winner's Sharpe real?

The best rule in sample is {best['rule']}, annual Sharpe {best['sr'] * ann:.3f} (daily {best['sr']:.5f}) over {ref['n_obs']} days.

| Statistic | Value |
|---|---|
| PSR against 0 | {ref['psr']['psr']:.4f} |
| Trials `N` | {len(ref['trials'])} |
| Variance of the trials' daily Sharpe | {ref['sr_variance']:.3g} |
| `SR0`, daily (what the best of {len(ref['trials'])} useless rules shows) | {ref['dsr']['sr0']:.5f} |
| DSR | {ref['dsr']['dsr']:.4f} |

Read the two probabilities together: the PSR asks whether the winner beats zero, the DSR whether it beats the luck of choosing among {len(ref['trials'])}. A DSR below 0.95 is not significant at 5 %.

## The winner chosen inside purged folds

{FOLDS} contiguous folds over the {ref['n_obs']} bars. Each observation's label is its bar's P&L, window `[i, i + 1]`, so the purge drops the neighbour on each side of a test block, and an embargo of {EMBARGO:g} drops the {ref['embargo_count']} indices after it, the first of which the purge has already dropped. In each fold the rule with the best training Sharpe is picked and scored on the test block.

{table(['Test bars', 'Training size', 'Rule picked', 'Training Sharpe', 'Test Sharpe', 'Test rank'], frows)}

Averaged over the folds, the picked rule's annual Sharpe is {sum(f['train_sr'] for f in ref['folds']) / len(ref['folds']) * ann:.3f} in training and {sum(f['test_sr'] for f in ref['folds']) / len(ref['folds']) * ann:.3f} on the test blocks. The fall from one to the other is the selection bias the DSR allows for.

## Probability of backtest overfitting

CSCV on the {ref['n_obs']} x {len(ref['trials'])} matrix of daily P&L in {PARTITIONS} blocks: {ref['pbo']['n_combinations']} splits, Sharpe metric. PBO = {ref['pbo']['pbo']:.4f}: in {below} of {len(logits)} splits the training winner landed at or below the median out of sample. On prices with no edge the winner's test rank is as likely to be low as high, so a PBO near one half is what noise gives; only a PBO well below one half would suggest the in-sample ranking carries over [BBLdPZ17].

{lines("Logits of the in-sample winner, sorted", "Split, sorted by logit", "Logit of relative rank", lg, cap)}

## Four-language agreement

Each CLI built these numbers on its own. Largest difference between any language and Java over {a['values']} values: {a['largest_difference']:.2g}. The moments and the rule targets are computed once in the page's Python tool; the CLIs compute every backtest, split and statistic.

## Oracle evidence and limits

The operations are checked against hand examples, one paper example and outside libraries (`oracle/OUTSIDE_J.json`, ruling J-19a):

{table(['Suite', 'Cases', 'Outside-checked'], ev)}

Limits: synthetic prices, one instrument, a fixed half-spread and no financing; the iid assumptions of PSR and DSR; daily P&L per unit rather than returns on capital. The page shows the method, not a market.
"""
