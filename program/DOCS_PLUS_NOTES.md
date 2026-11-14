# Docs-plus notes (stage J docs expansion)

Code changes the docs lane needed but did not make (no product code changed on branch `stage-j-docs-plus`):

1. **No moments operation.** `docs/curves/research-workflow.md` needs the mean, standard deviation, skew and kurtosis of each rule's daily P&L to feed `research.stats.psr` and `.dsr`. No CLI operation returns them, so `tools/gallery_j.py` computes them in Python (divisor n - 1 for the standard deviation, n for the third and fourth moments, kurtosis not excess). A `research.stats.moments` operation (or moments as extra outputs of `research.backtest.run`) would let the gallery hold no statistical logic, as its guide asks.
2. **Rule targets in tooling.** The twelve momentum and reversal targets are built in `tools/gallery_j.py`. That is the strategy under test, not library logic, and is stated in the module docstring.
3. **No real daily price series in the repo.** The research workflow page uses a seeded synthetic random walk (`examples/research_workflow_j.json`). The real series the repository records (a month of SOFR fixings, single-day Treasury curves) are too short for a 400-bar study. A redistributable daily series, recorded under `oracle/LICENCES.md` terms, would let the page run on real data.
