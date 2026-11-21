# Stop note: lane k-v1-a11y (2026-11-20, second round)

Branch `k-v1-a11y`, merged with `origin/k-v1` before each round. Evidence class in brackets.

**Run 44797986161 (head 801033aa) read from its logs and the 12 shard artifacts.** docs-site green. Every docs-site-a11y shard now processes all its pages: light 1/6 ran 138 pages in 24 pa11y-ci runs, 10 pages retried, 0 left unloadable (read). The line "pa11y-ci on 4 pages in 5 runs" in the log is the self-test's stand-in run, not the shard. What failed: `color-contrast` on 33 pages in each mode, 0 other rules, 0 load failures (read):

| Pages | Cause | Fix |
|---|---|---|
| 30 Curves gallery pages | text inside inline SVG charts: axe 4.2.4 cannot measure a drawn background and returns "incomplete"; pa11y 6.2.3 `lib/runners/axe.js` maps an incomplete result of serious impact to an error (read from the pa11y source at tag 6.2.3). The diagnostic step's plain `axe.run` reported no violation on these pages (read). | `tools/build_site.py` `chart_images`: each chart is a `<picture>` with light and dark SVG images, the same alt text (tested locally: 136 images valid, no unresolved colour token, widths pass on 37 Curves pages in all three views, dark screenshot checked) |
| `program/R6_EVIDENCE_HANDOVER` | bold text holding inline code, incomplete (inferred) | bold ends before the code |
| tutorials 36 and 39 | an incomplete with no element and no impact: axe reports a rule that threw that way (inferred); cause not established | none yet; the diagnostic step now prints incomplete results, rule errors and axe's reason data at 1280 x 1024 |

**Untested until the next CI run:** all three fixes under pa11y; the diagnostic output for tutorials 36 and 39. If only those two remain, the run stays red with 2 pages per mode; they are listed in `docs/known-issues.md` (G10 row), never excluded.
