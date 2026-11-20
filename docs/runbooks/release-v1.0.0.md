# Runbook: releasing v1.0.0

**Plain idea.** A release is a tag on a commit of `main`. Pushing the tag starts `.github/workflows/release.yml`, which reruns the four language CI workflows, builds the artefacts, signs a build-provenance attestation for each, publishes the GitHub release, and then downloads the release again and checks every attestation. Nothing goes to a package registry. Who does what: the owner merges and tags; a lane prepares the branch and never tags (lane rules).

**Formal statement.** v1.0.0 is released when all of these hold, in this order:

1. the four builds, their lock files and `tools/site_facts.json` all say `1.0.0` (`tools/check_versions.py --expect 1.0.0` exits 0);
2. `CHANGELOG.md` has a heading line that matches `^## 1\.0\.0([: ]|$)` (the `release-changelog` job refuses the tag otherwise and uses that section as the release notes);
3. the tag `v1.0.0` points at a commit of `main` whose CI is green;
4. every job of the Release run passes, `release-verify` included;
5. the docs site serves the release's pages (the site is deployed by `docs.yml` on every push to `main`, not by the tag).

Sources: `.github/workflows/release.yml` and `.github/workflows/docs.yml` (read 2026-11-20); the tag pattern `v[0-9]+.[0-9]+.[0-9]+` is the workflow's `on.push.tags`.

**State before this runbook is used (read 2026-11-20).** The last tag is v0.10.0. Stage K round 1 is on `main`, not tagged (pull requests #58 and #59), and goes out with v1.0.0 (owner decision 2026-11-20: no v0.10.1 tag). The version string on `main` is 0.10.1 in every file `tools/check_versions.py` reads. The `release-verify` job and the attested `SHA256SUMS` were added on branch `k-v1-k7` and have never run: they can run only after a tag push.

## 1. Before the tag: what the release must say

These statements are fixed by owner decisions and recorded results; the release notes and CHANGELOG keep them.

- K-2: "not met: N of 20 recorded trading days", with N from the verifier on the ledger at the tagged commit (step 1.1). The threshold is not changed.
- H-9 workload R (2026-11-18/19): timing is a recorded MISS at p99 and p99.9 in every language (local laptop, not the acceptance machine).
- Validation is self-assessment; there is no second review (owner decision 2026-11-18).
- Every open row of `docs/known-issues.md` stays open unless its closing evidence is named.

### 1.1 Count the recorded trading days (K-2)

```bash
git fetch origin paper-ledger paper-ledger-anchors forward-log
git show origin/paper-ledger:ledger/ledger.jsonl > ledger.jsonl
git show origin/forward-log:actions/log.jsonl > log.jsonl
git --work-tree=anchors-copy checkout origin/paper-ledger-anchors -- anchors
python tools/paper_daily/verify_ledger.py heights --anchors anchors-copy/anchors
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --anchors anchors-copy/anchors --forward-log log.jsonl --bitcoin-headers headers.json --require-days 20
```

`headers.json` is written by hand from the heights the `heights` command prints (`docs/developer-guides/paper-ledger.md`, "Check it yourself"). The `verify` command exits 1 until 20 days are proven; that is the expected result at v1.0.0. Take N from its output and write "not met: N of 20 recorded trading days" in the notes.

## 2. Version bump

The places that hold the version (found by `git grep` for the old version at the v0.10.0 bump, commit 2f4e51e4; read):

| File | Line |
|---|---|
| `python/pyproject.toml` | `version = "..."` |
| `python/quantforge_core/__init__.py` | fallback `__version__ = "..."` |
| `python/uv.lock` | the `quantforge-core` package entry |
| `rust/Cargo.toml` | workspace `version = "..."` |
| `rust/Cargo.lock` | the three `quantforge-*` package entries (not `rand_core`, which is also 0.10.1) |
| `java25/pom.xml` | the `quantforge` artifact's `<version>` |
| `cpp26/CMakeLists.txt` | `project(quantforge_cpp26 VERSION ...)` |
| `tools/site_facts.json` | `"version"` |

Edit the first, fourth, sixth, seventh and eighth by hand, then let the tools rewrite the lock files and check:

```bash
uv lock --project python
python tools/check_versions.py --expect 1.0.0
```

For `rust/Cargo.lock`, run `cargo update --workspace` from `rust/` (recalled from Cargo's documentation: it rewrites only the workspace members' entries), then check that `git diff rust/Cargo.lock` shows exactly the three `quantforge-*` lines. `python/quantforge_core/__init__.py` is edited by hand. Worked example: on 2026-11-20 the check prints `0.10.1` for every file and, with `--expect 1.0.0`, exits 1 with one line per file; after the bump it prints `1.0.0` eight times and exits 0.

## 3. CHANGELOG and release notes

1. Replace the heading `## Unreleased, for v1.0.0: ...` with `## 1.0.0 (YYYY-MM-DD)`. Check the release job will find it:

   ```bash
   grep -nE '^## 1\.0\.0([: ]|$)' CHANGELOG.md
   ```

   One line must print. The job copies everything from that heading to the next `## ` heading into the release notes, and appends the repository's CI minutes over the last 7 days (`tools/ci_minutes.py`).

2. Write `docs/releases/v1.0.0.md` from `docs/releases/TEMPLATE.md`. Every number names its file (template rule).
3. Update `tools/site_facts.json` (`release`, `released`, `main_state`, `next_stage`), then regenerate and check the generated pages:

   ```bash
   python tools/status_glance.py --write
   python tools/case_figures.py --check
   python tools/validation/status_ladder.py --check
   python tools/results_page.py --check
   python tools/check_known_issues.py
   python tools/check_runbooks.py
   python tools/check_hygiene.py
   ```

4. Build the site and check its anchors as `docs.yml` does: `uv run --no-project --with markdown==3.11.2 python tools/build_site.py --out site`, then `python tools/check_md_anchors.py --site site`. Both must report no broken link.

## 4. Merge, then tag

The owner merges the release pull request (one pull request for the round; `--merge`, owner standing instruction). Wait for every check on the merge commit of `main` to finish green:

```bash
gh run list --branch main --limit 20
```

Then tag the merge commit and push the tag (owner only):

```bash
git fetch origin main
git tag -a v1.0.0 -m "QuantForge v1.0.0" origin/main
git push origin v1.0.0
```

## 5. Watch the release run

```bash
gh run list --workflow release.yml --limit 1
gh run watch <run id>
```

Jobs, in order (read from `release.yml`): `release-changelog` (tag pattern, CHANGELOG section, `check_versions.py --expect`); `release-python-ci`, `release-rust-ci`, `release-java-ci`, `release-cpp-ci` (the language workflows, reused); `release-build-python`, `-rust`, `-java`, `-cpp`; `release` (SBOM, `SHA256SUMS`, attestations, `gh release create`); `release-verify`.

## 6. Verify the release as an outside user would

`release-verify` does this on a runner and uploads `attest.json` as the run artefact `release-verify`. To repeat it by hand:

```bash
gh release download v1.0.0 --repo AshJha0/quantforge --dir v1.0.0-assets
python tools/release_verify.py --dir v1.0.0-assets --repo AshJha0/quantforge --out attest.json
```

The script runs, for each asset, `gh attestation verify <file> --repo AshJha0/quantforge`, checks `SHA256SUMS` and the SBOM, and requires a copy of the first asset with its last byte flipped to fail verification. Expected output: one `verified` line per asset and one `FAILED` line for the tampered copy, exit 0.

Expected shape of a single `gh attestation verify` on success (recalled from the gh documentation, not yet observed on this repository):

```text
Loaded digest sha256:<64 hex> for file://quantforge-cli-1.0.0-linux-x86_64.tar.gz
Loaded 1 attestation from GitHub API
✓ Verification succeeded!

sha256:<64 hex> was attested by:
REPO                PREDICATE_TYPE                  WORKFLOW
AshJha0/quantforge  https://slsa.dev/provenance/v1  .github/workflows/release.yml@refs/tags/v1.0.0
```

The assets of v0.10.0 were: the CycloneDX SBOM, the C++ and Rust CLI archives, `quantforge-cli.jar`, the Python wheel and sdist, and `SHA256SUMS` (7 files; read with `gh api` on 2026-11-20). Six had an attestation; `SHA256SUMS` had none, because the workflow wrote it after the attest step (measured, `benchmarks/results/k7/v0.10.0-attestations-2026-11-20.json`). From v1.0.0 it is written first and attested with the rest.

What verification shows: the file was built by `release.yml` in this repository at the tagged commit. It does not show the code is correct.

## 7. Site check after the tag

The site at <https://ashjha0.github.io/quantforge/> is built from `main` by `docs.yml` (`docs-deploy` job). After the release merge:

```bash
gh run list --workflow docs.yml --branch main --limit 1
```

The run must be green. Then open the home page and check that it names the release from `tools/site_facts.json`, and that the results page (`docs/results.md`, built to `docs/results.html`) and the known-issues page load. The G10 layout check (ruling KR-227, confirmed 2026-11-20) is part of the same run: jobs `docs-site-view` (every page at 1280 px and at 375 px in light and dark mode, after its planted 600 px element fails) and `docs-site-view-summary`, and the dark-mode pa11y step of `docs-site`. Download the merged table and paste `site-view.md` into the release notes (`gh release edit v1.0.0 --notes-file` with the notes plus the table):

```bash
gh run download <run-id> --repo AshJha0/quantforge --name site-view --dir site-view
```

If a page fails, it is fixed or listed in `docs/known-issues.md` with its measured width; it is never left out of the check. Written 2026-11-20 before these jobs first ran in CI (inferred from the workflow file).

pa11y AA on every page (KR-227 read strictly by the coordinator, 2026-11-20) is part of the same run: jobs `docs-site-a11y` (12 shards: light and dark, 6 shards each; each first shows that pa11y-ci reports a planted contrast failure) and `docs-site-a11y-summary`, which fails if any shard failed or any page of the site was not reported on. Download the counts and paste `a11y-summary.md` into the release notes with the layout table: Split 2026-11-20: the jobs `docs-site-a11y` and `docs-site-a11y-summary` are not in `docs.yml` on main yet; they are held on branch `k-v1-a11y-ci` until every page passes (first CI runs, pull request #63: 33 pages per mode were reported for chart-text contrast that the tool could not measure, since changed to light and dark chart images; tutorials 36 and 39 still fail in both modes, cause not established). The tool, its self-test and the site fixes are on main. KR-227 stays not met.

```bash
gh run download <run-id> --repo AshJha0/quantforge --name site-a11y --dir site-a11y
```

A page with a pa11y error is fixed in the site templates (`tools/build_site.py`, `tools/site_home.html`) or listed in `docs/known-issues.md` with the rule id and page count; it is never excluded from the URL list. Written 2026-11-20 on branch `k-v1-a11y` before these jobs first ran in CI (inferred from the workflow file).

## 8. Rollback

**The release run failed before `gh release create`.** Nothing was published. Delete the tag, fix on a branch, merge, tag again:

```bash
git push origin :refs/tags/v1.0.0
git tag -d v1.0.0
```

**The release is published and something in it is wrong.** Do not move or reuse the tag: a moved tag makes the attestations name a different commit from the one users downloaded. Mark the release and fix forward:

```bash
gh release edit v1.0.0 --repo AshJha0/quantforge --prerelease --notes-file <notes with a warning at the top>
```

Then release v1.0.1 with the fix and a CHANGELOG `## 1.0.1` section that says what was wrong with v1.0.0. Deleting a published release (`gh release delete`) is the owner's decision only; the attestations stay recorded by GitHub against the digests (inferred from how attestations are stored: by subject digest, not by release).

## Limits

- Neither the tag run nor `release-verify` has ever run on v1.0.0; the first run is the release itself.
- `gh attestation verify` output above is recalled, not observed here.
- Registry publishing (G3b) is not done: owner decision 2026-11-20, no PyPI or crates.io accounts (ruling KR-226 and the dated line under it in `specifications/stage-k-rulings-k7.md`). Nothing in this runbook publishes to a registry, and `pip install quantforge` or `cargo add` from a registry will not install this project. Users install v1.0.0 from the release assets (the Python wheel, `quantforge-cli.jar`, the Rust and C++ CLI archives, each listed in `SHA256SUMS` and attested; check them with `gh attestation verify` as above) or build from source with CONTRIBUTING's commands.
