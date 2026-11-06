# Tools

Neutral tooling. Standard-library Python, with no financial logic, and not part of any implementation.

`python tools/test_tools.py` runs the tests.

## Recorder

The record has to start early: a 250-day history cannot be built later. Run once a day:

```bash
python tools/recorder/record.py
```

Nothing schedules it yet, and it needs a machine that is on. Raw files go to `data/recorder/`, which git ignores, so no source's data is committed. Only each file's hash and size go in the forward log. `tools/recorder/sources.json` is the licence manifest: a source without its licence fields stops the run. It says plainly what was and was not read. Review it before any raw data is shared.

Sources are the US Treasury par yield curve, Bank of England SONIA and ECB reference rates. FRED is left out: its terms bar storing or archiving content, and its API needs a key.

The manifest lags the stage B data survey of 2026-11-06. It still calls the SONIA and ECB terms unsettled; `oracle/LICENCES.md` has the survey's reading. Raw SONIA data stays local until the Bank answers on redistribution, and ECB rates may be reused only unchanged and cited.

## Forward log

`tools/forward-log/log.jsonl` is append-only and hash-chained, using the records and chain in `specifications/01-core/asof-store.md`. Each entry carries a timestamp and the code commit.

```bash
python tools/forward-log/forward_log.py verify
```

`forward_log.py add` records a dated prediction before its outcome is known. Commit the log often: the chain shows tampering inside the file, but only a commit history shows that the whole file was not rebuilt.
