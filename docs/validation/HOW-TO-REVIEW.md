# How to use the evidence pack

Owner decision, 2026-11-18: there is no second review of the curves, human or otherwise, and no sign-off step. This page keeps the steps for rebuilding the pack and for the optional AI check. What the pack holds is in [README.md](README.md).

## Rebuild the pack

1. Update the main checkout: `cd C:\Work\Claude\quantforge`, then `git checkout main` and `git pull`.
2. Rebuild the pack so it reflects the code at that point: `python tools/build_gallery.py --evidence-only`, then `python tools/validation/build_checklists.py`. Rerun the outside checks (`oracle/python/outside_validation.py`, under WSL) and the real-data round trip (`tools/validation/reconcile_official.py`, see README) if goldens or curves changed since 2026-11-18.
3. Commit any changes from step 2 on their own, so the evidence and any later notes refer to the same build.

## Where things are

| What | Location |
|---|---|
| What the pack holds | `docs/validation/README.md` |
| AI review instructions | `docs/validation/ai-review/README.md` |
| AI prompts, one per curve | `docs/validation/ai-review/<curve>.md` |
| Evidence checklists, one per curve | `docs/validation/<curve>.md` |
| Real-data results | `docs/validation/data/real-data.json` |
| Outside-library results | `oracle/OUTSIDE_VALIDATION.json` |
| Curve table (generated) | `docs/curves/README.md` |

`<curve>` is the gallery slug: `sonia-ois`, `sofr-ois`, `usd-term-3m`, `gbpusd-fx-forward`, `equity-forward`, `svi-smile`, `ssvi-surface`, `sabr`, `ois-full`, `bond-fit`, `repo`, `cross-currency`, `cds`, `dividend-borrow`, `inflation`, `caps-swaptions`, `commodities`, `sector-rating`, `funding`, `financing-term`, `liquidity`, `mbs`, `vol-surface`, `local-vol`, `swaption-cube`, `vol-term-structure`, `interpolation-methods`, `hedging-costs`, `research-workflow` (and any curve added later).

## Optional AI check

1. Open `docs/validation/ai-review/<curve>.md` and copy all of it (each file is about 30,000 characters or less).
2. Start a new ChatGPT or Gemini conversation for each curve, paste, send.
3. If the answer has no findings table or makes claims without quotes, ask: "Please give your findings as the table requested, quoting the spec line or number for each."
4. Paste the whole answer into `docs/validation/<curve>.md` below the line `<!-- Hand-filled below this line ... -->`, under a heading `## AI review (<model and version>, <YYYY-MM-DD>)`, with a triage table: finding, checked against the repository (yes/no), outcome (valid / not valid / open question).
5. Check every finding against the spec or golden it quotes before acting on it. Valid findings become open questions in the checklist or a fix in a separate PR.
6. Commit on a branch and open a PR; `python tools/validation/build_checklists.py --check` must still pass (it compares only the generated part above the line).

Suggested order: `equity-forward` first (ruling C18 on the dividend dated on `as_of`), then `sonia-ois`, `sofr-ois` and `ois-full`, which have real-data results.
