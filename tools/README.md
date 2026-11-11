# Tools

Neutral tooling. Standard-library Python, with no financial logic, and not part of any implementation.

`python tools/test_tools.py` runs the tests.

## Recorder

The record has to start early: a 250-day history cannot be built later. Run once a day:

```bash
python tools/recorder/record.py
```

`.github/workflows/recorder.yml` runs it on GitHub Actions twice each weekday and pushes the log rows, with a gap report from `tools/recorder/gap_monitor.py`, to branch `forward-log`. The local Windows task stays as a backup; `docs/developer-guides/recorder-actions.md` explains how the two logs reconcile. Raw files go to `data/recorder/`, which git ignores, so no source's data is committed. Each source's folder also gets a `NOTICE.txt` with its required notice, which must go with any data published. Only each file's hash and size go in the forward log. `tools/recorder/sources.json` is the licence manifest: a source without its licence fields stops the run. It says plainly what was and was not read. Review it before any raw data is shared.

Public-domain sources with a `parse` entry (the Treasury par, real and bill curves and BLS CPI) also keep their parsed values in the log: each row holds the values that are new or changed and `state_sha256`, the hash of the full parsed state, so `gap_monitor.py recheck` can rebuild the state and recheck every hash. A changed past value becomes a `revision/<source>` row. Every run then writes one `study/<id>` row per study in `tools/recorder/studies.json` (R3-01 to R3-03), with "no position" until the study runs. Every row carries `sources_sha256`, the hash of the `sources.json` it ran with. `gap_monitor.py gaps --studies tools/recorder/studies.json` fails if any prereg input or study row is missing on a US business day. FRED's T5YIE and T10YIE are listed but disabled, because FRED's terms rule out storing its data; R3-03 rebuilds them from the Treasury nominal and real curves.

Sources are the US Treasury par yield curve, Bank of England SONIA, ECB reference rates, New York Fed SOFR, ECB €STR and Federal Reserve H.10. H.10 comes from the XML zip on the release page, about 2 MB a run and updated weekly, because the Fed's Build Your Package tool goes in the week of 9 November 2026. FRED is left out: its terms bar storing or archiving content, and its API needs a key.

The manifest follows the stage B data survey of 2026-11-06; `oracle/LICENCES.md` has the same reading. Raw SONIA data stays local until the Bank answers on redistribution, and ECB data may be reused only unchanged and cited.

## Curves gallery

`tools/build_gallery.py` generates `docs/curves/` from real CLI runs, and `--check` reruns the Python CLI against it. See `docs/developer-guides/curves-gallery.md`.

## References and external links

`tools/build_references.py` writes `docs/references.md` from the `## Sources` sections of the specs and the tables in `specifications/stage-e-sources.md`; `--check` fails when the page is out of date (run in `docs.yml`). `tools/check_links.py` fetches every external link in the references and the top-level pages and exits 1 only on 404 or 410. Publishers often refuse automated clients (403), which is reported, not failed. It needs the network and prints `offline: skipped` without it, so it runs by hand rather than in CI.

## Forward log

`tools/forward-log/log.jsonl` is append-only and hash-chained, using the records and chain in `specifications/01-core/asof-store.md`. Each entry carries a timestamp and the code commit.

```bash
python tools/forward-log/forward_log.py verify
```

`forward_log.py add` records a dated prediction before its outcome is known. Commit the log often: the chain shows tampering inside the file, but only a commit history shows that the whole file was not rebuilt.

## Daily workflows

`tools/workflows/` holds the real-data acceptance runs (a) EOD curves and (c) SOFR check, the sanity bands and the seeded sample book. They run daily in `.github/workflows/daily-workflows.yml`. See `docs/developer-guides/r1-infra.md`.
