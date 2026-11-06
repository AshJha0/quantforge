# Curves gallery

The pages in `docs/curves/` are generated. Do not edit them by hand. `tools/build_gallery.py` sends cases to the CLIs, stores what comes back in `docs/curves/data/`, and writes the Markdown and inline SVG charts from that data. It holds no financial logic and uses only the standard library.

## Regenerate

Build all four CLIs as in the [Cookbook](../../COOKBOOK.md), with a Java 25 `java` first on `PATH`. On Windows, the GCC `bin` folder must be on `PATH` too. Then, from the repository root:

```bash
python tools/build_gallery.py
python tools/build_gallery.py --check
```

The first command needs all four CLIs, and stops if any exits with a failure or returns a status other than `ok`. Each data file records the commit, date and CLI versions. Commit the data and pages together. Regenerate after a change to financial code, an example or a golden file. The recorded commit is the one checked out at the run, so it precedes the commit holding the data.

## Check

CI has only Python to hand, so `--check` reruns the Python CLI and changes nothing. It fails if:

- a number differs from the committed data by more than 1e-10 plus 1e-8 relative (tolerance class `interpolation`), or 1e-2 plus 1e-6 relative for risk figures (the use case 2 limit);
- an example file, or the golden evidence counts, changed;
- a page differs from what the committed data produces.

Java, C++ and Rust figures are not rechecked here. They are as of the recorded run. The conformance workflow still tests those builds against the golden cases.

## Add a curve

Add a synthetic example to `examples/` and an entry in `CURVES`, and remove the curve from `PLANNED`. Use only operations that `quantforge operations` lists. Inputs stay labelled synthetic unless a real, redistributable source exists. Status moves to Validated only after the human review.

## Charts

Charts are inline SVG inside one `<div class="chart">` line, so Python-Markdown treats each as a raw block. Colours are CSS variables from `tools/build_site.py`, set in `style` attributes, because `var()` does not work in SVG presentation attributes. The `viewBox` is 480 wide and scales to the page, which keeps labels readable on a phone.
