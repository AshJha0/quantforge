# Release annotations for v0.6.0 and v0.7.0 (R6-15)

Checked 2026-11-12 with `gh release view`: the GitHub releases v0.6.0 (published 2026-11-10) and v0.7.0 (published 2026-11-11) have **0 assets**; v0.8.0 has 7. Review finding 15 said "confirmed for v0.7.0"; both are now reproduced.

The owner (or the coordinator with the owner's yes) appends the text below to each release body. It changes release notes only; no tag or asset is touched. Command, run once per tag, after reading the current body:

```
gh release view v0.6.0 --json body --jq .body > body.md
# append the block below to body.md, then
gh release edit v0.6.0 --notes-file body.md
```

## Text for v0.6.0

> **Note added 2026-11 (v0.8.1 review):** this release has no build artefacts attached. `release.yml` did not upload wheels, jars, crates or binaries for this tag. Build from the tagged source, or use v0.8.0 or later, which carry artefacts, an SBOM and build-provenance attestations. Corrections of record for items this release listed as done (E9, G2, G4) are in the v0.8.1 CHANGELOG.

## Text for v0.7.0

> **Note added 2026-11 (v0.8.1 review):** this release has no build artefacts attached. Build from the tagged source, or use v0.8.0 or later, which carry artefacts, an SBOM and build-provenance attestations. Corrections of record for items this release listed as done (A5, Q3b) are in the v0.8.1 CHANGELOG.
