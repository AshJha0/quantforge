### Site check (G10, KR-227): all pages, 816 pages, 453 s

816 pages; views: desktop-light 1280 px, phone-light 375 px, phone-dark 375 px. Measured with tools/check_site_view.py (Playwright, Chromium); pass means `document.documentElement.scrollWidth <= viewport width` and every Mermaid diagram rendered.

| View | Pages passing | Pages failing |
|---|---:|---:|
| desktop-light | 816 | 0 |
| phone-light | 816 | 0 |
| phone-dark | 816 | 0 |

Failing pages: none.


Run on the owner's Windows laptop (local laptop, not the acceptance machine) with the installed Google Chrome, 2026-11-20, site built at commit 105f7f96; measured. Mermaid: 58 diagrams on 2 pages, 57 of them on `docs/diagrams/README.html`, all rendered in every view. The CI run (`docs.yml`, jobs docs-site-view and docs-site-view-summary) has not run yet.
