# How to run the reviews (deferred)

Owner decision, 2026-11-18: the AI review and the human sign-off run at the end of stage K or after, not now. This page keeps the steps for then. The process and the rules are in [README.md](README.md).

## Before you start

1. Update the main checkout: `cd C:\Work\Claude\quantforge`, then `git checkout main` and `git pull`.
2. Rebuild the pack so it reflects the code at that point: `python tools/build_gallery.py --evidence-only`, then `python tools/validation/build_checklists.py`. Rerun the outside checks (`oracle/python/outside_validation.py`, under WSL) and the real-data round trip (`tools/validation/reconcile_official.py`, see README) if goldens or curves changed since 2026-11-18.
3. Commit any changes from step 2 before any review starts, so every reviewer sees the same evidence.

## Where things are

| What | Location |
|---|---|
| Process and rules | `docs/validation/README.md` |
| AI review instructions | `docs/validation/ai-review/README.md` |
| AI prompts, one per curve | `docs/validation/ai-review/<curve>.md` |
| Reviewer checklists, one per curve | `docs/validation/<curve>.md` |
| Real-data results | `docs/validation/data/real-data.json` |
| Outside-library results | `oracle/OUTSIDE_VALIDATION.json` |
| Status table (generated) | `docs/curves/README.md` |

`<curve>` is the gallery slug: `sonia-ois`, `sofr-ois`, `usd-term-3m`, `gbpusd-fx-forward`, `equity-forward`, `svi-smile`, `ssvi-surface`, `sabr`, `ois-full`, `bond-fit`, `repo`, `cross-currency`, `cds`, `dividend-borrow`, `inflation`, `caps-swaptions`, `commodities`, `sector-rating`, `funding`, `financing-term`, `liquidity`, `mbs`, `vol-surface`, `local-vol`, `swaption-cube`, `vol-term-structure`, `interpolation-methods`, `hedging-costs`, `research-workflow` (and any curve added later).

## 1. AI review (optional, before the human review)

1. Open `docs/validation/ai-review/<curve>.md` and copy all of it (each file is about 30,000 characters or less).
2. Start a new ChatGPT or Gemini conversation for each curve, paste, send.
3. If the answer has no findings table or makes claims without quotes, ask: "Please give your findings as the table requested, quoting the spec line or number for each."
4. Paste the whole answer into `docs/validation/<curve>.md` below the line `<!-- Hand-filled below this line ... -->`, under a heading `## AI review (<model and version>, <YYYY-MM-DD>)`, with the line "Second opinion only; not the sign-off." and a triage table: finding, checked against the repository (yes/no), outcome (valid / not valid / question for the reviewer).
5. Check every finding against the spec or golden it quotes before acting on it. Valid findings become open questions for the human reviewer or a fix in a separate PR.
6. Commit on a branch and open a PR; `python tools/validation/build_checklists.py --check` must still pass (it compares only the generated part above the line).

## 2. Human sign-off

1. Choose a named reviewer who did not write the curve.
2. The reviewer reads the checklist, the spec and rulings files it names (under `specifications/`), the gallery page (`docs/curves/<curve>.md`) and any AI review, ticks the boxes under "What to check" and answers the open questions.
3. The reviewer fills the sign-off block below the line: name, date as `YYYY-MM-DD`, verdict exactly `Validated`, `Validated with conditions` or `Not validated`, and conditions or findings.
4. Commit the signed checklist on its own (from the reviewer, or with their written approval linked).
5. In a separate commit, run `python tools/build_gallery.py --evidence-only` and `python tools/validation/build_checklists.py`. The gallery reads the verdict and changes the row to `Validated (name, date; checklist)` or `Validated with conditions (...)`. `Not validated` leaves the row; its findings become fixes, and the curve goes back to the reviewer afterwards.

Suggested order: `equity-forward` first (the reviewer confirms ruling C18 on the dividend dated on `as_of`), then `sonia-ois`, `sofr-ois` and `ois-full`, which have real-data results.
