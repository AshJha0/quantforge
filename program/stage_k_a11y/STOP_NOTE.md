# Stop note: lane k-v1-a11y (2026-11-20)

Branch `k-v1-a11y`, merged with `origin/k-v1` (146102d2) before this round. Pull request #63 holds the earlier lane commits.

**State.** CI run 44791215797 was red in 14 jobs from this lane (read from the run logs and artifacts):

1. docs-site, `tools/test_tools.py`: the `a11y_fix` test imported `tools/build_site.py`, which imports `markdown`, not installed in that step. Fixed: the test puts a stand-in `markdown` module in place only when the real one is missing (`a11y_fix` uses no Markdown). Checked locally with `markdown` blocked: passes.
2. docs-site-a11y, all 12 shards: two causes.
   - Harness: the bundled Chromium (puppeteer 9.1.1 under pa11y-ci 3.1.0) lost its connection on about a third of the pages ("Protocol error: Connection closed", then "Failed to create target for page" for every later page of the run); in light 2/6 it even happened on the two-page plant site, so that shard uploaded nothing. Fixed: `tools/check_site_a11y.py --run` runs pa11y-ci in batches of 10 with a fresh browser, at concurrency 1, and runs a page whose result is a browser or protocol failure (not a WCAG error) again on its own, at most twice; a page that still cannot be loaded fails. Raw pa11y output for every batch is in the shard artifact (`raw-*`).
   - Real errors: axe `color-contrast` on the text of the SVG charts of the Curves gallery pages (11 pages light, 4 dark, in the 4 shards that uploaded) and on 2 tutorial pages (36, 39) with no element named. pa11y's JSON gives no colours, so the cause is not established. Fix tried: `main svg[role=img]{background:var(--bg);color:var(--ink)}` in `tools/build_site.py`. A failure-only diagnostic step (`tools/a11y_detail.js`, using the puppeteer and axe-core that npx already installed) prints axe's own colour figures for up to four failing pages, unnamed ones first.

**Untested until the next CI run:** the batch driver against real pa11y-ci, whether retries clear the connection losses, whether the chart CSS clears the SVG contrast errors, what the two tutorial-page errors are, the diagnostic step, and shard timing (estimated 8 to 15 minutes against a 45-minute limit).

**Next step if still red:** read `contrast-detail.txt` in a failing shard's artifact; fix the named elements in the templates or the chart generators (`tools/build_gallery.py`, `tools/gallery_e.py`, then `build_gallery.py` to regenerate); never exclude a page.
