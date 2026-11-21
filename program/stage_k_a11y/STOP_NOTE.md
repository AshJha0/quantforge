# Stop note: lane k-v1-a11y2 (2026-11-21)

Branch `k-v1-a11y2`, from `k-v1` 47072365. Not merged, no pull request. Evidence class in brackets.

**Result.** Docs run 44926203225 (workflow_dispatch on `k-v1-a11y2`, head cffcfe31) is green in every job: docs-site, docs-site-view, all 12 docs-site-a11y shards and docs-site-a11y-summary. pa11y AA passes on 861 of 861 pages in light and 861 of 861 in dark, 0 errors (read from its `a11y-summary.md`). KR-227 is met on this branch; it is met on main only after the merge and a green Docs run there.

**What was done.**

| Step | Run | Finding | Fix |
|---|---|---|---|
| Restore the jobs | | `docs-site-a11y` and `docs-site-a11y-summary` had been cut from `docs.yml` by 1263f32b ("Split") | the removed hunk applied in reverse, header comment updated |
| Tutorials 36 and 39 | 44805977858 (diagnostic) | axe-core 4.2.4 threw `Cannot read property 'filter' of undefined` in color-contrast (read). Cause: the middle of a multi-line inline `<code>` in a `<pre>` that scrolls sideways falls in a 200 px grid cell none of its line boxes touch (read from the axe source at v4.2.4; a local replay found exactly these 2 of 836 pages, measured) | `pre code{display:block}` in `tools/build_site.py` |
| First try | 44920662025 | `width:max-content` on the block made axe unable to measure 44 COOKBOOK elements (read) | dropped; the block stays as wide as the visible `<pre>` |
| README table | 44919988589 | docs-site refused a stale Status at a glance after the fuzzfix_k goldens (read) | `tools/status_glance.py --write` |
| Question bank 14 | 44922499739 | 860 of 861 pages per mode; one `<em>` "Unable to determine contrast ratio" with no reason (read): an inline element on two lines with all its own text on the first, middle in the gap between its line boxes (inferred; replay with Verdana as a stand-in font finds exactly this element, measured) | a paragraph that is one `<em>` or `<strong>` gets class `para`, shown as a block |

`tools/check_site_a11y.py --browser` now replays both axe 4.2.4 traps (rules `axe-4.2.4-grid-gap`, `axe-4.2.4-own-stack-miss`); `tools/test_tools.py` checks the CSS and the paragraph rule (90 tests pass locally). Local passes after the fixes, local laptop, not the acceptance machine: browser pass no finding on 861 pages x 2 modes, width check 861 of 861 in three views (measured). Details: `benchmarks/results/k7/a11y-local-2026-11-20.md`.

**Nothing was excluded, no rule ignored, no threshold changed.**

**For the coordinator.** Merge `k-v1-a11y2` into `k-v1` (it carries the README status table regenerated after the fuzz goldens; `k-v1` itself should fail docs-site on that table, inferred from run 44919988589). The local replay depends on fonts: the runner's fallback font wraps lines the laptop's fonts do not, so a green local pass does not prove a green CI run.
