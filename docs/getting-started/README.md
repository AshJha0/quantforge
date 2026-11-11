# Tutorials

Seven guided tutorials, each 10 to 15 minutes, that walk through what QuantForge already does. Each one starts from small synthetic data you can follow by hand, runs it in Python first, then sends the same operations to the Rust, Java and C++ builds, which print the same digits. Every number on every page is real output, and CI runs each page in all four languages and fails if a printed line differs (`.github/workflows/tutorial.yml`, `tools/check_tutorial.py`).

Each tutorial explains its results in the same order: the plain idea, the formal statement from the spec, then a worked example with a check you can do in your head. Each ends with notes for practitioners, common mistakes, what you just did, and references.

Do [Tutorial 1](tutorial-1-swap.md) first: it sets up the tools and builds the four command-line programs the others use. After that the order is free, except that Tutorial 6 introduces the Hull-White model that Tutorials 5 and 7 also use.

| Tutorial | What you do | Operations | Stage |
|---|---|---|---|
| [1. Price your first swap](tutorial-1-swap.md) | SOFR quotes to a curve, a swap's PV and its DV01 | `rates.ois.bootstrap`, `rates.ois.pv`, `risk.ois.dv01` | B |
| [2. Bonds and repo](tutorial-2-bonds-repo.md) | A bond off the curve, its yield, duration and convexity, a repo forward and its implied rate | `bond.price.from_curve`, `bond.yield.from_price`, `bond.price.from_yield`, `repo.forward`, `repo.implied_rate` | D |
| [3. Options and volatility](tutorial-3-options-vol.md) | Black-Scholes price and Greeks, implied volatility, a SABR smile, a vol surface | `risk.vol.greeks`, `vol.option.implied`, `vol.sabr.calibrate`, `vol.sabr.hagan`, `vol.surface.query` | C, E |
| [4. Credit](tutorial-4-credit.md) | An ISDA CDS curve, a CDS price, survival probabilities, a sector curve | `credit.cds.bootstrap`, `credit.cds.price`, `credit.curve.composite` | D |
| [5. Risk](tutorial-5-risk.md) | AAD against bump-and-revalue, historical VaR and ES with a backtest, an FRTB delta charge | `rates.shortrate.bermudan_ladder`, `risk.var.historical`, `risk.backtest.kupiec`, `risk.backtest.traffic_light`, `risk.frtb.girr_delta` | C to G |
| [6. Interest rate models](tutorial-6-hull-white.md) | A Hull-White bond option, a Jamshidian swaption, sigma calibrated to swaptions, a Bermudan swaption | `rates.shortrate.zcb_option`, `rates.shortrate.swaption`, `rates.shortrate.hw_calibrate`, `rates.shortrate.bermudan_swaption` | G |
| [7. Counterparty risk](tutorial-7-counterparty.md) | A swap's exposure profile (EE, PFE), its CVA, the effect of a collateral agreement | `xva.exposure.portfolio_hw`, `xva.exposure.collateralised`, `xva.adjustments.value` | G |

## How the scripts work

Tutorials 2 to 7 each run one script in `examples/tutorials/`. The script calls operations by their names in `specifications/name-map.json` through one helper, `examples/tutorials/qf.py`: with no argument it uses the Python package in the same process, and with a command line it sends each case to that build's `batch` command (`specifications/cli-contract.md`). So one script, unchanged, drives all four implementations, and the page shows it in full; CI checks that the listing on the page equals the file.

```bash
uv run --project python python examples/tutorials/t4_credit.py          # Python
python examples/tutorials/t4_credit.py rust/target/release/quantforge   # Rust, Java or C++
```

To check a page yourself, as CI does: `python tools/check_tutorial.py --lang rust` (all pages) or add `--page docs/getting-started/tutorial-4-credit.md`. Pages 2 to 7 use the builds that page 1 makes, so check page 1 first in a fresh clone.

## Where to go next

- [LEARN](../../LEARN.md): the maths by topic, with golden cases you can rerun.
- [COOKBOOK](../../COOKBOOK.md): commands for every operation.
- [GLOSSARY](../../GLOSSARY.md): terms, including a [section for the tutorials](../../GLOSSARY.md#tutorial-terms).
- `specifications/`: the rules each operation follows. Each tutorial names the spec pages it uses.
- [References](../references.md): every source the specs cite, with its status as the spec records it.
